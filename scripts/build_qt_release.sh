#!/usr/bin/env bash
# Build the DamageLab Qt desktop release (macOS / Linux).
#
# Usage (from repo root or anywhere):
#     scripts/build_qt_release.sh            # uses python3 on PATH
#     PYTHON=.venv/bin/python scripts/build_qt_release.sh
#
# Artifact:
#     release/DamageLab-<version>-<platform>/   onedir (+ DamageLab.app on macOS)
#
# The build is unsigned (no code-signing certificate in this repo);
# macOS Gatekeeper may require a right-click → Open on first launch.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || PY=python

"$PY" - <<'EOF' || { echo "Error: PyInstaller is required (pip install 'pyinstaller>=6,<7')" >&2; exit 1; }
import PyInstaller  # noqa: F401
EOF

VERSION="$("$PY" -c "import sys; sys.path.insert(0,'src'); from damage_gui import __version__; print(__version__)")"
case "$(uname -s)-$(uname -m)" in
    Darwin-arm64) TAG=macos-arm64 ;;
    Darwin-*)     TAG=macos-x64 ;;
    Linux-aarch64) TAG=linux-arm64 ;;
    *)            TAG=linux-x64 ;;
esac
NAME="DamageLab-${VERSION}-${TAG}"
echo "Building ${NAME} (Qt desktop)..."

if [ "$(uname -s)" = "Darwin" ]; then
    # Generate the .icns used by the .app bundle from the bundled PNG.
    mkdir -p build
    ICONSET=build/damagelab-icon.iconset
    rm -rf "$ICONSET" && mkdir -p "$ICONSET"
    SRC_PNG=src/damage_gui/gui/assets/damagelab-icon.png
    for s in 16 32 128 256 512; do
        sips -z "$s" "$s" "$SRC_PNG" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
    done
    for s in 32 128 256 512; do
        h=$((s / 2))
        sips -z "$s" "$s" "$SRC_PNG" --out "$ICONSET/icon_${h}x${h}@2x.png" >/dev/null
    done
    iconutil -c icns "$ICONSET" -o build/damagelab-icon.icns
fi

"$PY" -m PyInstaller scripts/damagelab-qt.spec --noconfirm --clean \
    --distpath release --workpath build/qt

OUT="release/${NAME}"
mkdir -p "$OUT"
if [ "$(uname -s)" = "Darwin" ]; then
    mv "release/${NAME}.app" "$OUT/DamageLab.app"
    # The raw onedir output is redundant next to the .app bundle.
    rm -rf "$OUT/DamageLab" "$OUT/_internal"
fi
cp README.md "$OUT/README.md"
cp README.en.md "$OUT/README.en.md" 2>/dev/null || true

echo
echo "Release package created: $OUT"
if command -v codesign >/dev/null 2>&1 && [ "$(uname -s)" = "Darwin" ]; then
    if codesign --verify "$OUT/DamageLab.app" >/dev/null 2>&1; then
        echo "Code signature: verified"
    else
        echo "Code signature: unsigned local build (ad-hoc or none)"
    fi
fi
