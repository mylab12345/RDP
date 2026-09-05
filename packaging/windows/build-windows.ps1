# KB-Remote — Release build for Windows (run on the Windows build machine).
#
# Produces the single distributable installer:
#   dist\KB-Remote-Setup-<version>-x64.exe
#
# Steps: clean -> venv/pip Release install -> PyInstaller (frozen exe,
# version-stamped, no console) -> Inno Setup compile -> smoke test.
#
# Usage (PowerShell, from the repo root):
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build-windows.ps1
# Options:
#   -SkipInstaller   stop after the PyInstaller app bundle (no Inno Setup step)
#   -NoSmokeTest     skip the `--version` smoke test of the frozen exe

param(
  [switch]$SkipInstaller,
  [switch]$NoSmokeTest
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $root

function Say($msg) { Write-Host "== $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Error $msg; exit 1 }

# --- version (single source of truth: src/rdpstudio/__init__.py) -------------
$init = Get-Content (Join-Path $root "src\rdpstudio\__init__.py") -Raw
if ($init -notmatch '__version__\s*=\s*"([^"]+)"') { Fail "Cannot parse __version__" }
$Version = $Matches[1]
Say "KB-Remote $Version — Release build (x64)"

# --- locate python ------------------------------------------------------------
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if (-not $py) { Fail "Python 3.10+ not found. Install from https://python.org (check 'Add to PATH')." }
$PythonExe = $py.Source

# --- clean --------------------------------------------------------------------
Say "Cleaning previous build output"
Remove-Item -Recurse -Force (Join-Path $root "build") -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force (Join-Path $root "dist") -ErrorAction SilentlyContinue

# --- Release install ----------------------------------------------------------
Say "Installing Release dependencies"
if ($py.Name -eq "py.exe") {
  & $PythonExe -3 -m pip install --quiet --upgrade pip
  & $PythonExe -3 -m pip install --quiet ".[win]" pyinstaller
} else {
  & $PythonExe -m pip install --quiet --upgrade pip
  & $PythonExe -m pip install --quiet ".[win]" pyinstaller
}
if ($LASTEXITCODE -ne 0) { Fail "pip install failed" }

# --- frozen app bundle --------------------------------------------------------
Say "Running PyInstaller (Release, version-stamped exe)"
& $PythonExe -m PyInstaller --noconfirm --clean packaging/rdpstudio.spec
if ($LASTEXITCODE -ne 0) { Fail "PyInstaller failed" }
$FrozenExe = Join-Path $root "dist\KB-Remote\kb-remote.exe"
if (-not (Test-Path $FrozenExe)) { Fail "Frozen exe not found: $FrozenExe" }

if (-not $NoSmokeTest) {
  Say "Smoke test: frozen exe --version"
  & $FrozenExe --version
  if ($LASTEXITCODE -ne 0) { Fail "Smoke test failed ($FrozenExe --version)" }
}

if ($SkipInstaller) {
  Say "Done (app bundle only): dist\KB-Remote\"
  exit 0
}

# --- Inno Setup ---------------------------------------------------------------
$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) {
  $isccPath = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
  if (Test-Path $isccPath) { Set-Alias iscc $isccPath } else { Fail "Inno Setup 6 not found. Install from https://jrsoftware.org/isinfo.php" }
}
Say "Compiling installer with Inno Setup"
iscc "/DMyAppVersion=$Version" "packaging\windows\KB-Remote.iss"
if ($LASTEXITCODE -ne 0) { Fail "Inno Setup compile failed" }

$Setup = Join-Path $root "dist\KB-Remote-Setup-$Version-x64.exe"
if (-not (Test-Path $Setup)) { Fail "Installer not produced" }
Say ""
Say "Done: $Setup"
Say "Install:  Start-Process '$Setup'"
Say "Silent:   '$Setup' /VERYSILENT /NORESTART"
