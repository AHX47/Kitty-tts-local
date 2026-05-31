"""
voice_cloner.py — Extract speaker embeddings from audio files.
Uses Resemblyzer (primary) with a pure-NumPy fallback.
"""
from __future__ import annotations
import numpy as np
import soundfile as sf
from pathlib import Path

BASE_DIR          = Path(__file__).parent.parent
CUSTOM_VOICES_DIR = BASE_DIR / "custom_voices"
CUSTOM_VOICES_DIR.mkdir(parents=True, exist_ok=True)


def extract_embedding(audio_path: str) -> np.ndarray:
    """
    Extract a 256-dim speaker embedding from any WAV/MP3 file.
    Primary: Resemblyzer (VoiceEncoder).
    Fallback: spectral energy fingerprint.
    """
    try:
        from resemblyzer import VoiceEncoder, preprocess_wav
        enc = VoiceEncoder(device="cpu")
        wav = preprocess_wav(audio_path)
        emb = enc.embed_utterance(wav)
        return emb.astype(np.float32)
    except ImportError:
        pass
    except Exception as e:
        print(f"[voice_cloner] Resemblyzer error: {e} — using fallback")

    return _spectral_fingerprint(audio_path)


def _spectral_fingerprint(audio_path: str, n_bins: int = 256) -> np.ndarray:
    """Lightweight spectral energy fingerprint (no ML required)."""
    audio, sr = sf.read(audio_path, always_2d=True)
    audio = audio.mean(axis=1)                             # mono
    audio = audio / (np.max(np.abs(audio)) + 1e-9)        # normalise
    audio = audio[: sr * 5]                                # max 5 s
    n     = len(audio)
    if n < n_bins:
        audio = np.pad(audio, (0, n_bins - n))
        n = n_bins

    chunk  = n // n_bins
    feat   = np.array(
        [np.mean(np.abs(audio[i * chunk: (i + 1) * chunk])) for i in range(n_bins)],
        dtype=np.float32,
    )
    norm   = np.linalg.norm(feat) + 1e-9
    return feat / norm


def save_voice(name: str, embedding: np.ndarray) -> Path:
    """Persist a voice embedding to custom_voices/<name>.npz."""
    path = CUSTOM_VOICES_DIR / f"{name}.npz"
    np.savez(str(path), embedding=embedding)
    return path


def load_all_custom_voices() -> dict[str, np.ndarray]:
    """Return {name: embedding} dict for all saved voices."""
    voices = {}
    for f in CUSTOM_VOICES_DIR.glob("*.npz"):
        try:
            voices[f.stem] = np.load(f)["embedding"]
        except Exception:
            pass
    return voices


def delete_voice(name: str) -> bool:
    path = CUSTOM_VOICES_DIR / f"{name}.npz"
    if path.exists():
        path.unlink()
        return True
    return False


def list_voices() -> list[str]:
    return [f.stem for f in CUSTOM_VOICES_DIR.glob("*.npz")]
