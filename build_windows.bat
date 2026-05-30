@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM Minacraft — Windows EXE build script
REM
REM Requirements (run once):
REM   pip install pyinstaller pygame numpy
REM
REM Usage:
REM   build_windows.bat
REM
REM Output: dist\Minacraft-1.0-beta-windows.zip
REM ─────────────────────────────────────────────────────────────────────────────

echo [Minacraft] Building Windows EXE...

REM Convert .icns → .ico if not present (skip if minacraft.ico already exists)
if not exist minacraft.ico (
    echo [Minacraft] minacraft.ico not found — using default icon.
)

python -m PyInstaller minacraft.spec --clean --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller failed.
    exit /b 1
)

echo [Minacraft] Build complete: dist\Minacraft\

REM Pack into zip for distribution
cd dist
powershell -Command "Compress-Archive -Path Minacraft -DestinationPath Minacraft-1.0-beta-windows.zip -Force"
cd ..

echo [Minacraft] Done! dist\Minacraft-1.0-beta-windows.zip is ready.
