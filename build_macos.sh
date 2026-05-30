#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Minacraft — macOS .app + DMG build script
#
# Requirements (run once):
#   pip3 install pyinstaller pygame numpy
#
# Usage:
#   chmod +x build_macos.sh && ./build_macos.sh
#
# Output: dist/Minacraft-1.0-beta.dmg
# ─────────────────────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

echo "[Minacraft] Building macOS app..."

# Regenerate icon from grass block texture
python3 - <<'PYEOF'
import os, pygame
os.chdir(os.path.dirname(os.path.abspath(__file__)) or ".")
pygame.init()
from assets import load_texture
tex = load_texture("block/grass_block_side", 512)
import pygame
s = pygame.Surface((512, 512))
s.blit(tex, (0, 0))
pygame.image.save(s, "icon_512.png")
pygame.quit()
PYEOF

mkdir -p minacraft.iconset
for s in 16 32 64 128 256 512; do
    sips -z $s $s icon_512.png --out minacraft.iconset/icon_${s}x${s}.png   &>/dev/null
    sips -z $((s*2)) $((s*2)) icon_512.png --out minacraft.iconset/icon_${s}x${s}@2x.png &>/dev/null
done
iconutil -c icns minacraft.iconset -o minacraft.icns
echo "[Minacraft] Icon created."

# Build
python3 -m PyInstaller minacraft.spec --clean --noconfirm

APP="dist/Minacraft.app"
DMG="dist/Minacraft-1.0-beta.dmg"
TMP="/tmp/minacraft_build_$$.dmg"

echo "[Minacraft] Packaging DMG..."
hdiutil create -size 300m -fs HFS+ -volname "Minacraft" -o "$TMP"
hdiutil attach "$TMP" -mountpoint /Volumes/Minacraft
cp -R "$APP" /Volumes/Minacraft/
ln -sf /Applications /Volumes/Minacraft/Applications
hdiutil detach /Volumes/Minacraft
hdiutil convert "$TMP" -format UDZO -imagekey zlib-level=9 -o "$DMG"
rm -f "$TMP"

echo ""
echo "✓ Done!  →  $DMG"
ls -lh "$DMG"
