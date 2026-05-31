"""KittenTTS-Studio — shared core package."""
from .tts_engine    import TTSEngine, AVAILABLE_MODELS, DEFAULT_VOICES, MODELS_DIR
from .voice_cloner  import extract_embedding, save_voice, load_all_custom_voices, delete_voice
from .audio_utils   import resample, save_audio, duration_str, waveform_bars, normalise
from .download_models import download_model, download_all, model_is_ready, MODELS_CONFIG

__all__ = [
    "TTSEngine", "AVAILABLE_MODELS", "DEFAULT_VOICES", "MODELS_DIR",
    "extract_embedding", "save_voice", "load_all_custom_voices", "delete_voice",
    "resample", "save_audio", "duration_str", "waveform_bars", "normalise",
    "download_model", "download_all", "model_is_ready", "MODELS_CONFIG",
]
