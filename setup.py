"""
setup.py — Install the KittenTTS-Studio core package.
Allows `import core` from both Flet and PyQt5 apps
when the project is installed as a Python package.

Usage:
    pip install -e .    # editable / development install
    pip install .       # regular install
"""
from setuptools import setup, find_packages

setup(
    name="kittentts-studio",
    version="1.0.0",
    description="Kitten TTS Studio — offline TTS with voice cloning",
    author="KittenTTS Developer",
    python_requires=">=3.10",
    packages=find_packages(include=["core", "core.*"]),
    install_requires=[
        "onnxruntime>=1.17.0",
        "numpy>=1.24.0",
        "soundfile>=0.12.0",
        "phonemizer>=3.2.1",
        "espeakng-loader>=0.1.0",
        "resemblyzer>=0.1.1.dev0",
        "requests>=2.31.0",
        "tqdm>=4.66.0",
        "pydub>=0.25.1",
    ],
    extras_require={
        "flet":  ["flet>=0.24.0", "flet-audio>=0.24.0"],
        "qt":    ["PyQt5>=5.15.10"],
        "audio": ["librosa>=0.10.0"],
        "build": ["pyinstaller>=6.3.0"],
        "all":   ["flet>=0.24.0", "flet-audio>=0.24.0",
                  "PyQt5>=5.15.10", "librosa>=0.10.0",
                  "pyinstaller>=6.3.0"],
    },
)
