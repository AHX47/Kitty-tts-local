#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# build_appimage.sh — Build a portable .AppImage for Kitten TTS (Linux)
#
# Requires:
#   • appimagetool: https://github.com/AppImage/AppImageKit/releases
#     Place it at ~/bin/appimagetool or add to PATH.
#   • PyInstaller onedir bundle already built:
#     python build_scripts/build_exe.py --onedir
#
# Usage:  bash build_scripts/build_appimage.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_NAME="KittenTTS"
APP_VERSION="1.0.0"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
BUNDLE_DIR="$DIST_DIR/KittenTTS"          # PyInstaller onedir output
APPDIR="$DIST_DIR/${APP_NAME}.AppDir"
OUTPUT="$DIST_DIR/${APP_NAME}-${APP_VERSION}-x86_64.AppImage"
ICON_SRC="$ROOT_DIR/assets/icon.png"

# ── Check prerequisites ────────────────────────────────────────────────────────
if [ ! -d "$BUNDLE_DIR" ]; then
    echo "❌  Bundle not found: $BUNDLE_DIR"
    echo "   Run:  python build_scripts/build_exe.py --onedir"
    exit 1
fi

APPIMAGETOOL=$(command -v appimagetool || echo "$HOME/bin/appimagetool")
if [ ! -x "$APPIMAGETOOL" ]; then
    echo "❌  appimagetool not found."
    echo "   Download from https://github.com/AppImage/AppImageKit/releases"
    echo "   and place as ~/bin/appimagetool with execute permission."
    exit 1
fi

# ── Build AppDir ───────────────────────────────────────────────────────────────
echo "Building AppDir at $APPDIR …"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# Copy bundle
cp -r "$BUNDLE_DIR/." "$APPDIR/usr/bin/"

# Icon
if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$APPDIR/usr/share/icons/hicolor/256x256/apps/kittentts.png"
    cp "$ICON_SRC" "$APPDIR/kittentts.png"
fi

# Desktop file
cat > "$APPDIR/kittentts.desktop" <<EOF
[Desktop Entry]
Name=Kitten TTS
Comment=Offline TTS with voice cloning
Exec=KittenTTS
Icon=kittentts
Terminal=false
Type=Application
Categories=AudioVideo;Audio;
EOF

# AppRun launcher
cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
export LD_LIBRARY_PATH="$HERE/usr/bin:${LD_LIBRARY_PATH:-}"
exec "$HERE/usr/bin/KittenTTS" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

# ── Package with appimagetool ─────────────────────────────────────────────────
echo "Packaging AppImage…"
ARCH=x86_64 "$APPIMAGETOOL" "$APPDIR" "$OUTPUT"

echo ""
echo "✅  AppImage created: $OUTPUT"
echo "Run with:  chmod +x '$OUTPUT' && '$OUTPUT'"
