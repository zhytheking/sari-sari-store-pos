@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ============================================================
echo   BUILDING SALIGA SARI-SARI STORE POS
echo ============================================================
echo.

:: ── 1. Activate venv ──
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo   [ERROR] No virtual environment found.
    pause
    exit /b 1
)

:: ── 2. Verify run.spec exists ──
if not exist "run.spec" (
    echo   [ERROR] run.spec not found.
    pause
    exit /b 1
)

:: ── 3. Clean previous build ──
echo   [1/5] Cleaning previous build...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
echo         Done.

:: ── 4. PyInstaller ──
echo.
echo   [2/5] Running PyInstaller...
pyinstaller run.spec --noconfirm --clean
if errorlevel 1 (
    echo   [ERROR] PyInstaller failed. See output above.
    pause
    exit /b 1
)

if not exist "dist\SariSariPOS\SariSariPOS.exe" (
    echo   [ERROR] SariSariPOS.exe not found after build.
    pause
    exit /b 1
)
echo         Done. Exe at: dist\SariSariPOS\SariSariPOS.exe

:: ── 5. Verify folder structure ──
echo.
echo   [3/5] Verifying frozen app structure...
if not exist "dist\SariSariPOS\_internal" (
    echo         [WARN] _internal folder missing.
)

set "TPL_OK="
if exist "dist\SariSariPOS\_internal\frontend\web\templates" set "TPL_OK=1"
if defined TPL_OK (
    echo         Templates: OK
) else (
    echo         [WARN] Templates not bundled. GUI may not work.
)

set "STATIC_OK="
if exist "dist\SariSariPOS\_internal\frontend\web\static" set "STATIC_OK=1"
if defined STATIC_OK (
    echo         Static assets: OK
) else (
    echo         [WARN] Static assets not bundled.
)

set "MIG_OK="
if exist "dist\SariSariPOS\_internal\backend\database\migrations\sql" set "MIG_OK=1"
if defined MIG_OK (
    echo         Migrations: OK
) else (
    echo         [WARN] Migrations not bundled.
)

:: ── 6. Copy .env ──
echo.
echo   [4/5] Copying .env (if present)...
if exist ".env" (
    copy /y ".env" "dist\SariSariPOS\.env" >nul
    echo         .env copied.
) else (
    echo         [WARN] No .env file.
    if exist ".env.example" (
        copy /y ".env.example" "dist\SariSariPOS\.env" >nul
        echo         .env.example copied as .env.
    )
)

:: ── 7. Inno Setup ──
echo.
echo   [5/5] Building installer...

set "ISCC_PATH="

:: Check PATH first
for %%I in (iscc.exe) do set "ISCC_PATH=%%~$PATH:I"

:: Fall back to default install locations
if not defined ISCC_PATH (
    if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
        set "ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    )
)
if not defined ISCC_PATH (
    if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
        set "ISCC_PATH=%ProgramFiles%\Inno Setup 6\ISCC.exe"
    )
)

if not defined ISCC_PATH (
    echo         [SKIP] Inno Setup not found.
    echo         Install from https://jrsoftware.org/isdl.php
    echo         Then re-run build.bat.
) else (
    echo         Using: !ISCC_PATH!
    if not exist "installer" mkdir "installer"
    "!ISCC_PATH!" "installer\SariSariPOS.iss"
    if errorlevel 1 (
        echo         [ERROR] Inno Setup failed. See output above.
    ) else (
        echo         Installer built: installer\output\SariSariPOS-Setup.exe
    )
)

echo.
echo ============================================================
echo   BUILD COMPLETE
echo ============================================================
echo.
echo   Portable exe:  dist\SariSariPOS\SariSariPOS.exe
if exist "installer\output\SariSariPOS-Setup.exe" (
    echo   Installer:     installer\output\SariSariPOS-Setup.exe
) else (
    echo   Installer:     NOT BUILT
)
echo.
echo   To test the portable version:
echo     cd dist\SariSariPOS
echo     SariSariPOS.exe --app
echo.
pause
