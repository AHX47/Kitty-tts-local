"""
build_exe.py — PyInstaller build script for Kitten TTS
Generates a single-file executable (.exe on Windows, ELF binary on Linux).

Usage:
    python build_scripts/build_exe.py
    python build_scripts/build_exe.py --onedir     # folder instead of single file
    python build_scripts/build_exe.py --clean      # clean dist/ and build/ first
"""
from __future__ import annotations
import os
import sys
import shutil
import argparse
import subprocess
from pathlib import Path

ROOT       = Path(__file__).resolve().parent.parent          # project root
PYQT5_DIR  = ROOT / "pyqt5_app"
MAIN_SCRIPT = PYQT5_DIR / "main_qt.py"
DIST_DIR   = ROOT / "dist"
BUILD_DIR  = ROOT / "build"
ICON_WIN   = ROOT / "assets" / "icon.ico"
ICON_LINUX = ROOT / "assets" / "icon.png"
APP_NAME   = "KittenTTS"


def build(onedir: bool = False, clean: bool = False):
    if clean:
        for d in [DIST_DIR, BUILD_DIR]:
            if d.exists():
                shutil.rmtree(d)
                print(f"Cleaned: {d}")

    is_win = sys.platform.startswith("win")
    icon   = ICON_WIN if (is_win and ICON_WIN.exists()) else (
             ICON_LINUX if ICON_LINUX.exists() else None)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR),
        "--noconfirm",
        "--clean",
        # Include core package
        "--add-data", f"{ROOT / 'core'}:core",
        # Include models directory (pre-downloaded)
        "--add-data", f"{ROOT / 'models'}:models",
        # Include custom_voices directory
        "--add-data", f"{ROOT / 'custom_voices'}:custom_voices",
        # Hidden imports
        "--hidden-import", "onnxruntime",
        "--hidden-import", "soundfile",
        "--hidden-import", "phonemizer",
        "--hidden-import", "resemblyzer",
        "--hidden-import", "numpy",
        "--hidden-import", "PyQt5.QtMultimedia",
        "--hidden-import", "PyQt5.QtMultimediaWidgets",
    ]

    if not onedir:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    if is_win:
        cmd.append("--windowed")     # no console window on Windows

    if icon:
        cmd += ["--icon", str(icon)]

    cmd.append(str(MAIN_SCRIPT))

    print(f"\n{'='*60}")
    print(f" Building {APP_NAME} ({'onefile' if not onedir else 'onedir'})")
    print(f"{'='*60}\n")
    print("Command:", " ".join(cmd))
    print()

    result = subprocess.run(cmd, cwd=str(ROOT))

    if result.returncode == 0:
        exe = (DIST_DIR / APP_NAME).with_suffix(".exe" if is_win else "")
        if not exe.exists():
            exe = DIST_DIR / APP_NAME / (APP_NAME + (".exe" if is_win else ""))
        print(f"\n✅  Build successful!")
        print(f"   Output: {exe}")
    else:
        print("\n❌  Build failed — check output above.")
        sys.exit(1)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Build KittenTTS executable")
    p.add_argument("--onedir", action="store_true",
                   help="Build one-directory bundle instead of single file")
    p.add_argument("--clean",  action="store_true",
                   help="Remove dist/ and build/ before building")
    args = p.parse_args()
    build(args.onedir, args.clean)
