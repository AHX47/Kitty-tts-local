# 🐱 Kitten TTS Studio

**أداة توليد صوت بشري محلية 100% مع استنساخ الصوت**
Full-stack offline TTS app — Android · Web · Windows · Linux

---

## 📁 Project Structure

```
KittenTTS-Studio/
│
├── core/                        ← Shared engine (all platforms)
│   ├── __init__.py
│   ├── tts_engine.py            ← KittenTTS ONNX wrapper + voice cloning
│   ├── voice_cloner.py          ← Resemblyzer embedding extraction
│   ├── audio_utils.py           ← Format conversion, waveform helpers
│   └── download_models.py       ← HuggingFace model downloader
│
├── flet_app/                    ← Flet cross-platform app
│   ├── main.py                  ← Full chat UI (Android / Web / Desktop)
│   ├── requirements.txt
│   └── pubspec.yaml             ← Flutter build config (Android APK)
│
├── pyqt5_app/                   ← PyQt5 desktop app (Windows / Linux)
│   ├── main_qt.py               ← Full desktop UI with audio player
│   ├── requirements_qt.txt
│   └── build_scripts/
│       ├── build_exe.py         ← PyInstaller → .exe / Linux binary
│       ├── build_deb.sh         ← fpm → .deb package
│       └── build_appimage.sh    ← appimagetool → .AppImage
│
├── models/                      ← Downloaded ONNX models (auto-created)
│   ├── nano_int8/               ← ~25 MB fastest
│   ├── nano_fp32/               ← ~56 MB balanced
│   ├── micro/                   ← ~41 MB good quality
│   └── mini/                    ← ~80 MB best quality
│
├── custom_voices/               ← Your cloned voices (.npz files)
├── assets/                      ← Icons, fonts
├── requirements.txt             ← Unified deps (all platforms)
└── setup.py
```

---

## ⚡ Quick Start

### 1. Install dependencies

```bash
# Clone this repo or extract the zip
cd KittenTTS-Studio

# Install the core package (editable)
pip install -e ".[all]" --break-system-packages

# Or install only what you need:
pip install -e ".[flet]"   # Flet app only
pip install -e ".[qt]"     # PyQt5 app only
```

### 2. Download models

```bash
# Download all 4 models (one-time, ~200 MB total)
python core/download_models.py

# Or download a specific model only:
python core/download_models.py --model nano_int8   # fastest (~25 MB)
python core/download_models.py --model mini        # best quality (~80 MB)

# List available models and their status:
python core/download_models.py --list
```

### 3. Run the Flet app (cross-platform)

```bash
cd flet_app
python main.py
```

Opens as a desktop window. Use `--web` for browser mode:

```bash
flet run main.py --web --port 8080
```

### 4. Run the PyQt5 desktop app (Windows / Linux)

```bash
cd pyqt5_app
python main_qt.py
```

---
### Test
<video controls src="assets/sounds/kittentts_1.mp3" width="300" height="40"></video>
<audio src="assets/sounds/kittentts_1.wav" controls width="320" height="40"></audio>


## 📱 Build Android APK

### Prerequisites

```bash
# Install Flutter SDK: https://flutter.dev/docs/get-started/install
# Install Flet CLI
pip install flet --break-system-packages

# Verify
flet --version
flutter doctor
```

### Build APK

```bash
cd flet_app

# One-time: download models BEFORE building (they'll be bundled inside APK)
python ../core/download_models.py --model nano_int8   # recommended for mobile

# Copy models into assets so Flet bundles them
mkdir -p assets/models
cp -r ../models/nano_int8 assets/models/

# Build APK
flet build apk --project kitten_tts

# Output: build/apk/kitten_tts.apk
```

### On-device model path

In the Flet app, models are loaded from:
- **Bundled (in APK)**: `assets/models/` — accessible via `flet.app.assets_dir`
- **Downloaded at first run**: stored in app's internal storage

Adjust `MODELS_DIR` in `core/tts_engine.py` for runtime path detection:

```python
import flet as ft

def get_models_dir() -> Path:
    """Resolve correct models path on any platform."""
    if hasattr(ft, 'app') and ft.app.assets_dir:
        return Path(ft.app.assets_dir) / "models"
    return Path(__file__).parent.parent / "models"
```

---

## 🪟 Build Windows .exe

```bash
# Install PyInstaller
pip install pyinstaller --break-system-packages

# Build (from project root)
python pyqt5_app/build_scripts/build_exe.py

# For folder bundle (easier to debug):
python pyqt5_app/build_scripts/build_exe.py --onedir

# Output: dist/KittenTTS.exe  (or dist/KittenTTS/ folder)
```

---

## 🐧 Build Linux .deb (Debian / Ubuntu)

```bash
# Step 1: Build the PyInstaller bundle first
python pyqt5_app/build_scripts/build_exe.py --onedir

# Step 2: Install fpm (requires Ruby)
gem install fpm

# Step 3: Build .deb
bash pyqt5_app/build_scripts/build_deb.sh

# Output: dist/kittentts_1.0.0_amd64.deb
# Install:
sudo dpkg -i dist/kittentts_1.0.0_amd64.deb
```

---

## 🐧 Build Linux .AppImage (portable, no install needed)

```bash
# Step 1: Build PyInstaller bundle
python pyqt5_app/build_scripts/build_exe.py --onedir

# Step 2: Download appimagetool
wget -O ~/bin/appimagetool \
  "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
chmod +x ~/bin/appimagetool

# Step 3: Build AppImage
bash pyqt5_app/build_scripts/build_appimage.sh

# Output: dist/KittenTTS-1.0.0-x86_64.AppImage
# Run:
chmod +x dist/KittenTTS-1.0.0-x86_64.AppImage
./dist/KittenTTS-1.0.0-x86_64.AppImage
```

---

## 🎙 Voice Cloning — Step by Step

### Method A — From the UI

1. Open the app → tap ⚙ Settings → **Clone New Voice**
2. Pick a WAV file (minimum 5 seconds of clear speech)
3. Enter a name (e.g. "صوتي العربي")
4. Click **Extract & Save** — the embedding is computed locally
5. The new voice appears immediately in the Voice list

### Method B — Python script

```python
from core.voice_cloner import extract_embedding, save_voice

# Extract 256-dim speaker embedding using Resemblyzer
emb = extract_embedding("my_audio.wav")

# Save to custom_voices/my_voice.npz
save_voice("my_voice", emb)

print(f"Embedding shape: {emb.shape}")  # (256,)
```

### Method C — Generate TTS with a custom voice directly

```python
from core.tts_engine import TTSEngine

engine = TTSEngine()
engine.load_model("nano_int8")

# Generate with a default voice
audio = engine.generate("Hello, world!", voice="Bella")

# Generate with a cloned voice (auto-loaded from custom_voices/)
audio = engine.generate("Hello, world!", voice="my_voice")

engine.save_wav(audio, "output.wav")
```

---

## 🧠 Architecture Overview

```
User text
    ↓
TTSEngine.generate()
    ├─ chunk_text()         — split long text into ≤400 char chunks
    ├─ phonemizer           — English → IPA phonemes (espeak-ng)
    ├─ TextCleaner          — phonemes → token IDs
    ├─ _get_style()         ─┬─ DEFAULT voices → voices.npz lookup
    │                        └─ CUSTOM voices  → _adapt_embedding()
    └─ ONNX session.run()   — CPU inference
         ↓
    numpy float32 audio @ 24 kHz
         ↓
    AudioUtils.save_audio() — WAV / MP3 / OGG with optional resampling
```

---

## 🎛 Available Models

| Key         | Name       | Size   | Quality    | Speed      |
|-------------|------------|--------|------------|------------|
| `nano_int8` | Nano INT8  | ~25 MB | ★★☆☆☆      | Fastest ⚡  |
| `nano_fp32` | Nano FP32  | ~56 MB | ★★★☆☆      | Fast       |
| `micro`     | Micro      | ~41 MB | ★★★★☆      | Balanced   |
| `mini`      | Mini       | ~80 MB | ★★★★★      | Best 🏆     |

All models run on **CPU only** (`onnxruntime` — no GPU required).

---

## 🎤 Default Voices

`Bella · Jasper · Luna · Bruno · Rosie · Hugo · Kiki · Leo`

Plus any voices you clone and save in `custom_voices/`.

---

## 🔧 System Requirements

| Platform | Min. RAM | Storage    | OS                     |
|----------|----------|------------|------------------------|
| Android  | 2 GB     | 200 MB     | Android 8+             |
| Windows  | 4 GB     | 300 MB     | Windows 10/11 x64      |
| Linux    | 4 GB     | 300 MB     | Ubuntu 20.04+ / Arch   |
| Web      | —        | server-side| Any modern browser     |

**Dependencies:**
- Python ≥ 3.10
- espeak-ng (installed automatically via `espeakng-loader`)
- ffmpeg (optional, required for MP3/OGG export via pydub)

---

## ❓ Troubleshooting

| Problem | Solution |
|---|---|
| `espeak` not found | `pip install espeakng-loader` or `sudo apt install espeak-ng` |
| Model not found | Run `python core/download_models.py` |
| `resemblyzer` install fails | `pip install resemblyzer --no-build-isolation` |
| MP3 export fails | Install ffmpeg: `sudo apt install ffmpeg` |
| APK crashes on launch | Ensure `nano_int8` model is in `assets/models/nano_int8/` |
| PyQt5 display issues on Linux | `export QT_QPA_PLATFORM=xcb` |

---

## 📄 License

MIT — KittenML/KittenTTS engine · Studio wrapper by Abdo
