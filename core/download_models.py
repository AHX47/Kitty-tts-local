"""
download_models.py — Download KittenTTS ONNX models from Hugging Face.

Usage:
    python download_models.py                  # all models
    python download_models.py --model nano_int8
    python download_models.py --list
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

import requests
from tqdm import tqdm

BASE_DIR   = Path(__file__).parent.parent
MODELS_DIR = BASE_DIR / "models"

HF_BASE = "https://huggingface.co/{repo}/resolve/main/{file}"

MODELS_CONFIG: dict[str, dict] = {
    "nano_int8": {
        "name":    "Nano INT8  (~25 MB)  — fastest",
        "hf_repo": "KittenML/kitten-tts-nano-0.8-int8",
        "files":   ["model.onnx", "config.json", "voices.npz"],
        "dir":     MODELS_DIR / "nano_int8",
    },
    "nano_fp32": {
        "name":    "Nano FP32  (~56 MB)  — small & balanced",
        "hf_repo": "KittenML/kitten-tts-nano-0.8",
        "files":   ["model.onnx", "config.json", "voices.npz"],
        "dir":     MODELS_DIR / "nano_fp32",
    },
    "micro": {
        "name":    "Micro      (~41 MB)  — good quality",
        "hf_repo": "KittenML/kitten-tts-micro-0.8",
        "files":   ["model.onnx", "config.json", "voices.npz"],
        "dir":     MODELS_DIR / "micro",
    },
    "mini": {
        "name":    "Mini       (~80 MB)  — best quality",
        "hf_repo": "KittenML/kitten-tts-mini-0.8",
        "files":   ["model.onnx", "config.json", "voices.npz"],
        "dir":     MODELS_DIR / "mini",
    },
}


def _download_file(
    url:         str,
    dest:        Path,
    label:       str        = "",
    progress_cb: callable | None = None,
) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if progress_cb:
            progress_cb(f"✓ {label} (cached)")
        return True

    try:
        r     = requests.get(url, stream=True, timeout=120)
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))

        with open(dest, "wb") as fh:
            if progress_cb:
                received = 0
                for chunk in r.iter_content(chunk_size=65536):
                    fh.write(chunk)
                    received += len(chunk)
                    pct = int(received * 100 / total) if total else 0
                    progress_cb(f"↓ {label} — {pct}%  ({received/1e6:.1f} MB)")
            else:
                with tqdm(desc=f"  ↓ {label}", total=total,
                          unit="iB", unit_scale=True) as bar:
                    for chunk in r.iter_content(chunk_size=65536):
                        fh.write(chunk)
                        bar.update(len(chunk))
        return True

    except Exception as exc:
        if progress_cb:
            progress_cb(f"✗ {label}: {exc}")
        else:
            print(f"  ✗ {label}: {exc}")
        if dest.exists():
            dest.unlink()
        return False


def download_model(
    model_key:   str,
    progress_cb: callable | None = None,
    force:       bool            = False,
) -> bool:
    """Download a single model. Returns True on success."""
    cfg = MODELS_CONFIG.get(model_key)
    if not cfg:
        return False

    if not force:
        # Skip if all files already present
        all_present = all((cfg["dir"] / f).exists() for f in cfg["files"])
        if all_present:
            if progress_cb:
                progress_cb(f"✓ {cfg['name']} already downloaded")
            return True

    cfg["dir"].mkdir(parents=True, exist_ok=True)
    ok = True
    for fname in cfg["files"]:
        url  = HF_BASE.format(repo=cfg["hf_repo"], file=fname)
        dest = cfg["dir"] / fname
        if not _download_file(url, dest, f"{model_key}/{fname}", progress_cb):
            if fname == "model.onnx":
                ok = False
    return ok


def download_all(
    progress_cb: callable | None = None,
    force:       bool            = False,
) -> dict[str, bool]:
    return {k: download_model(k, progress_cb, force) for k in MODELS_CONFIG}


def model_is_ready(model_key: str) -> bool:
    cfg = MODELS_CONFIG.get(model_key, {})
    d   = cfg.get("dir", Path("/nonexistent"))
    return bool(list(d.glob("*.onnx"))) and (d / "voices.npz").exists()


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    p = argparse.ArgumentParser(description="KittenTTS model downloader")
    p.add_argument("--model",  choices=list(MODELS_CONFIG) + ["all"], default="all")
    p.add_argument("--list",   action="store_true", help="List available models")
    p.add_argument("--force",  action="store_true", help="Re-download even if cached")
    args = p.parse_args()

    if args.list:
        print("\nAvailable models:")
        for k, v in MODELS_CONFIG.items():
            status = "✓ ready" if model_is_ready(k) else "✗ not downloaded"
            print(f"  {k:12s}  {v['name']:40s}  [{status}]")
        sys.exit(0)

    if args.model == "all":
        results = download_all(force=args.force)
        for k, ok in results.items():
            print(f"  {'✓' if ok else '✗'} {k}")
    else:
        ok = download_model(args.model, force=args.force)
        print("✅ Done!" if ok else "❌ Failed")
