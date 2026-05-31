#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# build_deb.sh — Build a .deb package for Kitten TTS (Debian / Ubuntu)
#
# Requires: fpm  →  gem install fpm
#           PyInstaller must have already built the onedir bundle:
#               python build_scripts/build_exe.py --onedir
#
# Usage:  bash build_scripts/build_deb.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_NAME="kittentts"
APP_VERSION="1.0.0"
APP_DISPLAY="Kitten TTS"
MAINTAINER="KittenTTS Developer <dev@kittentts.local>"
DESCRIPTION="Offline text-to-speech with voice cloning — KittenTTS ONNX engine"
ARCH="amd64"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
BUNDLE_DIR="$DIST_DIR/KittenTTS"
ICON_SRC="$ROOT_DIR/assets/icon.png"
DESKTOP_DIR="$ROOT_DIR/assets/linux"
DEB_OUT="$DIST_DIR/${APP_NAME}_${APP_VERSION}_${ARCH}.deb"

# ── Sanity checks ─────────────────────────────────────────────────────────────
if [ ! -d "$BUNDLE_DIR" ]; then
    echo "❌  Bundle not found: $BUNDLE_DIR"
    echo "   Run:  python build_scripts/build_exe.py --onedir"
    exit 1
fi

command -v fpm >/dev/null 2>&1 || {
    echo "❌  fpm not found. Install with:  gem install fpm"
    exit 1
}

# ── Create .desktop file ──────────────────────────────────────────────────────
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_DIR/kittentts.desktop" <<EOF
[Desktop Entry]
Name=${APP_DISPLAY}
Comment=${DESCRIPTION}
Exec=/opt/kittentts/KittenTTS
Icon=/opt/kittentts/icon.png
Terminal=false
Type=Application
Categories=AudioVideo;Audio;Accessibility;
Keywords=tts;speech;voice;
EOF

# Copy icon into bundle for packaging
if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$BUNDLE_DIR/icon.png"
fi

echo ""
echo "Building .deb package…"
echo ""

fpm \
    -s dir \
    -t deb \
    --name         "$APP_NAME" \
    --version      "$APP_VERSION" \
    --architecture "$ARCH" \
    --maintainer   "$MAINTAINER" \
    --description  "$DESCRIPTION" \
    --url          "https://github.com/KittenML/KittenTTS" \
    --license      MIT \
    --prefix       / \
    --package      "$DEB_OUT" \
    --after-install /dev/null \
    --deb-no-default-config-files \
    "$BUNDLE_DIR/=/opt/kittentts/" \
    "$DESKTOP_DIR/kittentts.desktop=/usr/share/applications/kittentts.desktop" \
    "$ICON_SRC=/usr/share/pixmaps/kittentts.png"

echo ""
echo "✅  Package created: $DEB_OUT"
echo "Install with:  sudo dpkg -i $DEB_OUT"
