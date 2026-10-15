@echo off
REM KB-Remote Windows build script (cmd/bat version)
REM Usage: build.bat [version]

setlocal enabledelayedexpansion

set REPO_ROOT=%~dp0..
set SRC_DIR=%REPO_ROOT%\src
set PACKAGING_DIR=%REPO_ROOT%\packaging
set WINDOWS_PACKAGING_DIR=%PACKAGING_DIR%\windows
set DIST_DIR=%REPO_ROOT%\dist
set INSTALLER_DIR=%REPO_ROOT%\installer
set VENV_DIR=%REPO_ROOT%\venv
set PYINSTALLER_SPEC=%WINDOWS_PACKAGING_DIR%\rdpstudio-windows.spec
set INNO_SPEC=%WINDOWS_PACKAGING_DIR%\kb-remote-setup.iss

REM Get version
set VERSION=%1
if "%VERSION%"=="" (
    for /f "tokens=2 delims==" %%i in ('git describe --tags --abbrev=0 2^>nul') do set VERSION=%%i
    if "%VERSION%"=="" (
        for /f "tokens=2 delims==" %%i in ('findstr /r "version\s*=" %REPO_ROOT%\pyproject.toml') do set VERSION=%%i
        set VERSION=%VERSION:"=%
    )
)
if "%VERSION%"=="" set VERSION=0.9.0

echo Building KB-Remote v%VERSION%

REM Ensure dirs exist
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"
if not exist "%INSTALLER_DIR%" mkdir "%INSTALLER_DIR%"

REM 1. Setup venv and install deps
echo Setting up Python venv...
if not exist "%VENV_DIR%" (
    python -m venv "%VENV_DIR%"
)
"%VENV_DIR%\Scripts\pip.exe" install --upgrade pip setuptools wheel -q
echo Installing KB-Remote [win] + PyInstaller...
"%VENV_DIR%\Scripts\pip.exe" install -e . pyinstaller ".[win]" -q

REM 2. Run PyInstaller
echo Running PyInstaller...
cd /d %REPO_ROOT%
if exist "%DIST_DIR%\KB-Remote" rmdir /s /q "%DIST_DIR%\KB-Remote"
"%VENV_DIR%\Scripts\pyinstaller.exe" --clean "%PYINSTALLER_SPEC%"
if not exist "%DIST_DIR%\KB-Remote\KB-Remote.exe" (
    echo ERROR: PyInstaller failed - KB-Remote.exe not found
    exit /b 1
)
echo PyInstaller bundle ready at dist\KB-Remote

REM 3. Build Inno Setup installer
echo Building Inno Setup installer...
where iscc >nul 2>nul
if errorlevel 1 (
    set ISCC=
    for %%p in (
        "%ProgramFiles%\Inno Setup 6\ISCC.exe"
        "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
        "%ProgramFiles%\Inno Setup 5\ISCC.exe"
        "%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe"
    ) do if exist "%%p" set ISCC=%%p
    if "%ISCC%"=="" (
        echo ERROR: Inno Setup compiler (iscc) not found.
        echo Install Inno Setup 6+ from https://jrsoftware.org/isinfo.php
        exit /b 1
    )
) else (
    set ISCC=iscc
)

REM Update version in .iss
powershell -Command "(gc '%INNO_SPEC%' -Raw) -replace '#define AppVersion \".*\"', '#define AppVersion \"%VERSION%\"' | sc '%INNO_SPEC%' -Encoding UTF8"

cd /d "%WINDOWS_PACKAGING_DIR%"
"%ISCC%" "%INNO_SPEC%"

set INSTALLER_NAME=KB-Remote-Setup-%VERSION%-windows-x86_64.exe
if exist "%INSTALLER_DIR%\%INSTALLER_NAME%" (
    echo.
    echo ==== Build complete ====
    echo Bundle: dist\KB-Remote\KB-Remote.exe
    echo Installer: installer\%INSTALLER_NAME%
    for %%f in ("%INSTALLER_DIR%\%INSTALLER_NAME%") do echo Size: %%~zf bytes
) else (
    echo WARNING: Installer not found at expected path
    dir "%INSTALLER_DIR%\KB-Remote-Setup-*.exe"
)