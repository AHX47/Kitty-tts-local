"""
audio_utils.py — Audio format conversion and helper utilities.
"""
from __future__ import annotations
import os
import tempfile
import numpy as np
import soundfile as sf
from pathlib import Path


# ── Resampling ────────────────────────────────────────────────────────────────
def resample(audio: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr:
        return audio
    try:
        import librosa
        return librosa.resample(audio, orig_sr=src_sr, target_sr=dst_sr).astype(np.float32)
    except ImportError:
        pass
    # Lightweight linear interpolation fallback
    ratio   = dst_sr / src_sr
    new_len = int(len(audio) * ratio)
    idx     = np.linspace(0, len(audio) - 1, new_len)
    return np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)


# ── Save helpers ─────────────────────────────────────────────────────────────
def save_audio(
    audio:       np.ndarray,
    path:        str,
    sample_rate: int  = 24_000,
    fmt:         str  = "wav",
) -> str:
    """
    Save *audio* to *path* in the requested *fmt* (wav | mp3 | ogg).
    Returns the final path actually written (may differ if pydub unavail).
    """
    path = str(path)
    fmt  = fmt.lower()

    if fmt == "wav":
        sf.write(path, audio, sample_rate, format="WAV")
        return path

    if fmt in ("mp3", "ogg"):
        try:
            from pydub import AudioSegment
            tmp = _tmp_wav(audio, sample_rate)
            seg = AudioSegment.from_wav(tmp)
            seg.export(path, format=fmt)
            os.unlink(tmp)
            return path
        except ImportError:
            fallback = path.rsplit(".", 1)[0] + ".wav"
            sf.write(fallback, audio, sample_rate)
            return fallback

    sf.write(path, audio, sample_rate)
    return path


def _tmp_wav(audio: np.ndarray, sr: int) -> str:
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    sf.write(path, audio, sr)
    return path


# ── Info ──────────────────────────────────────────────────────────────────────
def duration_sec(audio: np.ndarray, sr: int) -> float:
    return len(audio) / sr


def duration_str(audio: np.ndarray, sr: int = 24_000) -> str:
    s = int(duration_sec(audio, sr))
    return f"{s // 60:02d}:{s % 60:02d}"


def normalise(audio: np.ndarray) -> np.ndarray:
    m = np.max(np.abs(audio))
    return audio / m if m > 0 else audio


def waveform_bars(audio: np.ndarray, n_bars: int = 30) -> list[float]:
    """Return *n_bars* normalised energy values in [0,1] for waveform display."""
    if len(audio) == 0:
        return [0.1] * n_bars
    mono  = audio.flatten()
    chunk = max(len(mono) // n_bars, 1)
    bars  = [float(np.mean(np.abs(mono[i*chunk:(i+1)*chunk])))
             for i in range(n_bars)]
    mx    = max(bars) or 1.0
    return [b / mx for b in bars]
