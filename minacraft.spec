# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Minacraft.

macOS:  python3 -m PyInstaller minacraft.spec
Windows: python -m PyInstaller minacraft.spec   (run on a Windows machine)
"""
import sys
from pathlib import Path

block_cipher = None

# ── Source files ───────────────────────────────────────────────────────────────
src = Path(SPECPATH)          # directory of this .spec file = project root

# ── Data files to bundle ───────────────────────────────────────────────────────
# Tuples: (source_path, destination_folder_inside_bundle)
datas = [
    # Faithful 32x texture + sound pack (the entire minecraft sub-tree)
    (str(src / "resources"), "resources"),
    # AI-generated textures
    (str(src / "generated_textures"), "generated_textures"),
]

# ── Hidden imports pygame might need ──────────────────────────────────────────
hiddenimports = [
    "pygame",
    "pygame.mixer",
    "pygame.font",
    "pygame.image",
    "numpy",
    "numpy.core",
]

a = Analysis(
    [str(src / "main.py")],
    pathex=[str(src)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",        # launcher uses tkinter but game does not
        "matplotlib",
        "scipy",
        "PIL",
        "cv2",
        "IPython",
        "jupyter",
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Minacraft",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,            # no terminal window
    icon=str(src / "minacraft.icns") if sys.platform == "darwin"
         else str(src / "minacraft.ico") if (src / "minacraft.ico").exists()
         else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Minacraft",
)

# ── macOS .app bundle ─────────────────────────────────────────────────────────
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Minacraft.app",
        icon=str(src / "minacraft.icns"),
        bundle_identifier="com.minacraft.game",
        info_plist={
            "CFBundleName":              "Minacraft",
            "CFBundleDisplayName":       "Minacraft",
            "CFBundleVersion":           "1.0.0",
            "CFBundleShortVersionString":"1.0-beta",
            "NSHighResolutionCapable":   True,
            "LSMinimumSystemVersion":    "10.13.0",
            "NSMicrophoneUsageDescription": "",
        },
    )
