"""
KittenTTS Engine — Core TTS driver for all platforms.
Wraps KittenTTS ONNX models with voice cloning support.
"""
import os
import re
import sys
import numpy as np
import soundfile as sf
from pathlib import Path

# ── espeak setup (must happen before phonemizer import) ─────────────────────
try:
    import espeakng_loader
    from phonemizer.backend.espeak.wrapper import EspeakWrapper
    EspeakWrapper.set_library(espeakng_loader.get_library_path())
    os.environ["ESPEAK_DATA_PATH"] = espeakng_loader.get_data_path()
except Exception:
    pass

import phonemizer
import onnxruntime as ort

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR         = Path(__file__).parent.parent
MODELS_DIR       = BASE_DIR / "models"
CUSTOM_VOICES_DIR = BASE_DIR / "custom_voices"
CUSTOM_VOICES_DIR.mkdir(parents=True, exist_ok=True)

# ── Model registry ───────────────────────────────────────────────────────────
AVAILABLE_MODELS = {
    "nano_int8": {
        "name":    "Nano INT8",
        "size":    "~25 MB",
        "hf_repo": "KittenML/kitten-tts-nano-0.8-int8",
        "dir":     MODELS_DIR / "nano_int8",
    },
    "nano_fp32": {
        "name":    "Nano FP32",
        "size":    "~56 MB",
        "hf_repo": "KittenML/kitten-tts-nano-0.8",
        "dir":     MODELS_DIR / "nano_fp32",
    },
    "micro": {
        "name":    "Micro",
        "size":    "~41 MB",
        "hf_repo": "KittenML/kitten-tts-micro-0.8",
        "dir":     MODELS_DIR / "micro",
    },
    "mini": {
        "name":    "Mini",
        "size":    "~80 MB",
        "hf_repo": "KittenML/kitten-tts-mini-0.8",
        "dir":     MODELS_DIR / "mini",
    },
}

DEFAULT_VOICES       = ["Bella", "Jasper", "Luna", "Bruno", "Rosie", "Hugo", "Kiki", "Leo"]
VOICE_INTERNAL_NAMES = [
    "expr-voice-2-m", "expr-voice-2-f", "expr-voice-3-m", "expr-voice-3-f",
    "expr-voice-4-m", "expr-voice-4-f", "expr-voice-5-m", "expr-voice-5-f",
]
VOICE_MAP = dict(zip(DEFAULT_VOICES, VOICE_INTERNAL_NAMES))


# ── Text helpers ─────────────────────────────────────────────────────────────
def _tokenize(text: str) -> list:
    return re.findall(r"\w+|[^\w\s]", text)


def _ensure_punct(text: str) -> str:
    text = text.strip()
    return text if (not text or text[-1] in ".!?,;:") else text + ","


def chunk_text(text: str, max_len: int = 400) -> list:
    sentences = re.split(r"[.!?]+", text)
    chunks = []
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if len(sent) <= max_len:
            chunks.append(_ensure_punct(sent))
        else:
            words, temp = sent.split(), ""
            for word in words:
                if len(temp) + len(word) + 1 <= max_len:
                    temp = (temp + " " + word).strip()
                else:
                    if temp:
                        chunks.append(_ensure_punct(temp))
                    temp = word
            if temp:
                chunks.append(_ensure_punct(temp))
    return chunks or [_ensure_punct(text)]


class _TextCleaner:
    def __init__(self):
        _pad  = "$"
        _punc = ';:,.!?¡¿—…"«»"" '
        _let  = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        _ipa  = ("ɑɐɒæɓʙβɔɕçɗɖðʤəɘɚɛɜɝɞɟʄɡɠɢʛɦɧħɥʜɨɪʝɭɬɫɮʟɱɯɰŋɳɲɴøɵɸθœɶ"
                 "ʘɹɺɾɻʀʁɽʂʃʈʧʉʊʋⱱʌɣɤʍχʎʏʑʐʒʔʡʕʢǀǁǂǃˈˌːˑʼʴʰʱʲʷˠˤ˞↓↑→↗↘'̩'ᵻ")
        syms  = [_pad] + list(_punc) + list(_let) + list(_ipa)
        self._d = {s: i for i, s in enumerate(syms)}

    def __call__(self, text: str) -> list:
        return [self._d[c] for c in text if c in self._d]


# ── TTSEngine ────────────────────────────────────────────────────────────────
class TTSEngine:
    """Thread-safe KittenTTS ONNX engine with voice-cloning support."""

    SAMPLE_RATE = 24_000

    def __init__(self):
        self.session:      ort.InferenceSession | None = None
        self.voices_data:  np.lib.npyio.NpzFile | None = None
        self._phonemizer   = None
        self._cleaner      = _TextCleaner()
        self.current_model: str | None = None
        self.custom_voices: dict[str, np.ndarray] = {}
        self.reload_custom_voices()

    # ── Model management ─────────────────────────────────────────────────────
    def is_model_ready(self, model_key: str) -> bool:
        info = AVAILABLE_MODELS.get(model_key, {})
        d    = info.get("dir", Path())
        return bool(list(d.glob("*.onnx"))) and (d / "voices.npz").exists()

    def load_model(self, model_key: str, progress_cb=None) -> bool:
        """Load a KittenTTS model. Returns True on success."""
        if model_key not in AVAILABLE_MODELS:
            return False
        d = AVAILABLE_MODELS[model_key]["dir"]
        onnx_files = list(d.glob("*.onnx"))
        voices_file = d / "voices.npz"
        if not onnx_files or not voices_file.exists():
            return False

        if progress_cb:
            progress_cb("Loading ONNX model…")
        self.session     = ort.InferenceSession(str(onnx_files[0]),
                                                providers=["CPUExecutionProvider"])
        self.voices_data = np.load(str(voices_file))

        if progress_cb:
            progress_cb("Initialising phonemizer…")
        self._phonemizer = phonemizer.backend.EspeakBackend(
            language="en-us", preserve_punctuation=True, with_stress=True
        )
        self.current_model = model_key
        return True

    # ── Voice management ─────────────────────────────────────────────────────
    def reload_custom_voices(self):
        self.custom_voices = {}
        for f in CUSTOM_VOICES_DIR.glob("*.npz"):
            try:
                data = np.load(f)
                self.custom_voices[f.stem] = data["embedding"]
            except Exception:
                pass

    def all_voices(self) -> list[str]:
        return DEFAULT_VOICES + list(self.custom_voices.keys())

    # ── Audio generation ─────────────────────────────────────────────────────
    def generate(self, text: str, voice: str = "Bella", speed: float = 1.0) -> np.ndarray:
        if not self.session or self.voices_data is None:
            raise RuntimeError("No model loaded — call load_model() first.")
        parts = [self._gen_chunk(c, voice, speed) for c in chunk_text(text)]
        return np.concatenate(parts, axis=-1) if parts else np.zeros(0, dtype=np.float32)

    def _gen_chunk(self, text: str, voice: str, speed: float) -> np.ndarray:
        # Phonemise
        ph   = self._phonemizer.phonemize([text])[0]
        toks = self._cleaner(" ".join(_tokenize(ph)))
        toks = [0] + toks + [10, 0]
        input_ids = np.array([toks], dtype=np.int64)

        # Style / speaker embedding
        ref_s = self._get_style(voice, text)

        outputs = self.session.run(None, {
            "input_ids": input_ids,
            "style":     ref_s,
            "speed":     np.array([speed], dtype=np.float32),
        })
        return outputs[0][..., :-5000]

    def _get_style(self, voice: str, text: str) -> np.ndarray:
        if voice in VOICE_MAP:
            vdata = self.voices_data[VOICE_MAP[voice]]
            idx   = min(len(text), vdata.shape[0] - 1)
            return vdata[idx:idx+1]
        if voice in self.custom_voices:
            return self._adapt_embedding(self.custom_voices[voice], text)
        raise ValueError(f"Unknown voice: '{voice}'")

    def _adapt_embedding(self, emb: np.ndarray, text: str) -> np.ndarray:
        """Resize a custom Resemblyzer/WeSpeaker embedding to model style dim."""
        ref     = self.voices_data[VOICE_INTERNAL_NAMES[0]]
        idx     = min(len(text), ref.shape[0] - 1)
        sdim    = ref[idx:idx+1].shape[1]
        flat    = emb.flatten()
        if len(flat) >= sdim:
            adapted = flat[:sdim]
        else:
            reps    = sdim // len(flat) + 1
            adapted = np.tile(flat, reps)[:sdim]
        return adapted.reshape(1, sdim).astype(np.float32)

    # ── File I/O ─────────────────────────────────────────────────────────────
    def save_wav(self, audio: np.ndarray, path: str):
        sf.write(path, audio, self.SAMPLE_RATE)

    @staticmethod
    def duration_str(audio: np.ndarray, sr: int = 24_000) -> str:
        secs = int(len(audio) / sr)
        return f"{secs // 60:02d}:{secs % 60:02d}"
