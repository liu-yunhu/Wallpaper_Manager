@echo off
REM Build script for Wallpaper Manager
REM This script builds the application into a single executable

echo ========================================
echo   Wallpaper Manager - Build Script
echo ========================================
echo.

REM Check if PyInstaller is installed
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [ERROR] PyInstaller is not installed!
    echo Installing PyInstaller...
    pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller
        pause
        exit /b 1
    )
)

echo [1/3] Cleaning previous build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo       Done!

echo.
echo [2/3] Building executable with PyInstaller...
python -m PyInstaller launcher.spec

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo       Done!

echo.
echo [3/3] Build completed successfully!
echo.
echo ========================================
echo   Build Information
echo ========================================
echo   Output: dist\WallpaperManager.exe
echo   Size:
for %%A in (dist\WallpaperManager.exe) do echo          %%~zA bytes
echo ========================================
echo.
echo Note: config.json is bundled inside the exe. On first run it is
echo copied to %%APPDATA%%\WallpaperManager\config.json and used from there.
echo.
echo You can now run: dist\WallpaperManager.exe
echo.
pause
