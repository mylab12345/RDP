# RDP Studio - Windows installer (PowerShell).
# Creates a private venv, installs the app, adds a Start Menu shortcut.
#
# Run from a PowerShell window inside the checkout:
#   powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$VenvDir = if ($env:RDPSTUDIO_VENV) { $env:RDPSTUDIO_VENV } else { "$env:LOCALAPPDATA\RDPStudio\venv" }
$LinkDir = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\RDP Studio"

function Say($msg) { Write-Host "== $msg" -ForegroundColor Cyan }

# --- locate python -----------------------------------------------------------
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if (-not $py) {
    Write-Error "Python 3.10+ not found. Install from https://python.org (check 'Add to PATH')."
    exit 1
}
$PythonExe = $py.Source

Say "Creating virtualenv in $VenvDir"
if (-not (Test-Path "$VenvDir\Scripts\python.exe")) {
    if ($py.Name -eq "py.exe") { & $PythonExe -3 -m venv $VenvDir }
    else { & $PythonExe -m venv $VenvDir }
}

Say "Installing RDP Studio"
$venvPy = "$VenvDir\Scripts\python.exe"
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet .
if ($LASTEXITCODE -ne 0) { Write-Error "pip install failed"; exit 1 }

# optional ConPTY local shells
& $venvPy -m pip install --quiet pywinpty 2>$null
if ($LASTEXITCODE -ne 0) { Say "(pywinpty skipped - local shells use cmd fallback)" }

Say "Creating Start Menu shortcut"
New-Item -ItemType Directory -Force -Path $LinkDir | Out-Null
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateCertificate = $null
$Shortcut = $WshShell.CreateShortcut("$LinkDir\RDP Studio.lnk")
$Shortcut.TargetPath = "$VenvDir\Scripts\rdpstudio.exe"
$Shortcut.WorkingDirectory = "$env:USERPROFILE"
$Shortcut.IconLocation = "$VenvDir\Scripts\rdpstudio.exe,0"
$Shortcut.Save()

Say "Adding to user PATH (if missing)"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$VenvDir\Scripts*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$VenvDir\Scripts", "User")
    Say "PATH updated - open a new terminal to use 'rdpstudio'"
}

Say ""
Say "Done. Launch 'RDP Studio' from the Start Menu, or run: rdpstudio"
Say "RDP sessions use the built-in Windows client (mstsc)."
