@echo off
REM ---------------------------------------------------------------------------
REM  KB-Remote universal installer for Windows (clients and servers).
REM
REM  Downloads the latest bootstrap script and runs it.  Everything needed at
REM  run time (Python, Qt) is bundled inside the setup executable the script
REM  installs, so this works on a bare Windows 10/11 or Server 2019+ machine
REM  with no other prerequisites.
REM
REM  Usage:
REM    install.cmd                      install / upgrade (silent)
REM    install.cmd -Interactive         show the setup wizard
REM    install.cmd -Version 0.9.1       install a specific release
REM    install.cmd -FromSource          build from a checkout instead
REM ---------------------------------------------------------------------------
setlocal enableextensions

set "REPO=%KB_REMOTE_REPO%"
if "%REPO%"=="" set "REPO=mylab12345/RDP"

set "URL=https://github.com/%REPO%/releases/latest/download/install.ps1"
set "PS=%TEMP%\kb-remote-install.ps1"

echo.
echo  KB-Remote universal installer
echo  ---------------------------------------------
echo  Downloading bootstrap from %URL%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing -Uri '%URL%' -OutFile '%PS%' } catch { Write-Error $_.Exception.Message; exit 1 }"
if errorlevel 1 (
  echo.
  echo  ERROR: could not download the installer. Check your network or proxy.
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS%" %*
exit /b %errorlevel%
