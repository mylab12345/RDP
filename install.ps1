<#
.SYNOPSIS
    Universal KB-Remote installer for Windows clients and servers.

.DESCRIPTION
    Installs KB-Remote from a single self-contained setup executable.  The
    Python runtime, Qt/PySide6 and every Python dependency are bundled inside
    that executable, so no Python, no package manager and no other
    prerequisite is required.  The Microsoft Visual C++ runtime is checked and
    installed on demand.  A per-user install needs no administrator rights;
    run it elevated (or pass -InstallDir) for an all-users install.

    Supported: Windows 10 1809+ / Windows 11 and Windows Server 2019/2022/2025,
    on x64 and on ARM64 (through Windows' x64 emulation).

    Universal one-liner (PowerShell) - grab and run the latest release:

        powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://github.com/mylab12345/RDP/releases/latest/download/install.ps1 -OutFile $env:TEMP\kbri.ps1; & $env:TEMP\kbri.ps1"

.PARAMETER Version
    "latest" (default) or an explicit release "X.Y.Z".

.PARAMETER InstallDir
    Install location.  Defaults to %LOCALAPPDATA%\Programs\KB-Remote for a
    per-user install, or %ProgramFiles%\KB-Remote when run elevated.

.PARAMETER Interactive
    Show the graphical setup wizard instead of installing silently.

.PARAMETER NoLaunch
    Do not start KB-Remote when the install finishes.

.PARAMETER Force
    Reinstall even when the requested version is already present.

.PARAMETER FromSource
    Developer mode: build and install from this checkout with pip instead of
    downloading the prebuilt installer.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\install.ps1
    powershell -ExecutionPolicy Bypass -File .\install.ps1 -Version 0.9.1 -NoLaunch
    powershell -ExecutionPolicy Bypass -File .\install.ps1 -Interactive
#>
[CmdletBinding()]
param(
    [string]$Version = "latest",
    [string]$InstallDir = "",
    [switch]$Interactive,
    [switch]$NoLaunch,
    [switch]$Force,
    [switch]$FromSource
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$AppName  = "KB-Remote"
$ExeName  = "KB-Remote.exe"
$MinBuild = 17763  # Windows 10 1809 / Windows Server 2019

$RepoSlug = if ($env:KB_REMOTE_REPO) { $env:KB_REMOTE_REPO } else { "mylab12345/RDP" }
$RepoUrl  = "https://github.com/$RepoSlug"

function Write-Step([string]$Message) { Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message)   { Write-Host "    $Message" -ForegroundColor Green }
function Write-Note([string]$Message) { Write-Host "    $Message" -ForegroundColor Yellow }
function Fail([string]$Message) {
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

function Test-IsWindows {
    return ([System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT)
}

function Test-IsAdmin {
    try {
        $id = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = [Security.Principal.WindowsPrincipal]::new($id)
        return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch {
        return $false
    }
}

function Enable-Tls12 {
    try {
        [Net.ServicePointManager]::SecurityProtocol =
            [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    } catch {
        # PowerShell 7 already negotiates modern TLS.
    }
}

function Get-Architecture {
    $arch = "$env:PROCESSOR_ARCHITECTURE"
    if ("$env:PROCESSOR_ARCHITEW6432") { $arch = "$env:PROCESSOR_ARCHITEW6432" }
    switch ($arch.ToUpperInvariant()) {
        "AMD64" { return "x64" }
        "ARM64" { return "arm64" }
        "X86"   { return "x86" }
        default { return "x64" }
    }
}

function Assert-SupportedWindows {
    if (-not (Test-IsWindows)) { Fail "This installer only runs on Windows." }
    $build = [System.Environment]::OSVersion.Version.Build
    $arch  = Get-Architecture
    Write-Ok "Windows build $build, architecture $arch"
    if ($build -lt $MinBuild) {
        Write-Note "KB-Remote needs Windows 10 1809 / Server 2019 or newer (build $MinBuild+)."
        Write-Note "This machine reports build $build; installation will continue but may not run."
    }
}

function Install-VCRuntime {
    $sys = "$env:SystemRoot\System32"
    if ((Test-Path (Join-Path $sys "vcruntime140.dll")) -and
        (Test-Path (Join-Path $sys "vcruntime140_1.dll"))) {
        return
    }
    Write-Step "Installing Microsoft Visual C++ runtime (Qt dependency)"
    if (-not (Test-IsAdmin)) {
        Write-Note "Not elevated: skipping VC++ runtime install. If the app fails to"
        Write-Note "start, install https://aka.ms/vs/17/release/vc_redist.x64.exe once."
        return
    }
    try {
        $vc = Join-Path $env:TEMP "vc_redist.x64.exe"
        Invoke-WebRequest -UseBasicParsing -Uri "https://aka.ms/vs/17/release/vc_redist.x64.exe" -OutFile $vc
        $p = Start-Process -FilePath $vc -ArgumentList "/install", "/quiet", "/norestart" -Wait -PassThru
        if ($p.ExitCode -eq 0 -or $p.ExitCode -eq 3010) { Write-Ok "Visual C++ runtime ready." }
        else { Write-Note "VC++ runtime installer returned $($p.ExitCode); continuing." }
    } catch {
        Write-Note "Could not install the VC++ runtime automatically: $($_.Exception.Message)"
    }
}

function Get-SetupUrl {
    if ($Version -eq "latest" -or [string]::IsNullOrWhiteSpace($Version)) {
        return "$RepoUrl/releases/latest/download/KB-Remote-Setup.exe"
    }
    $v = $Version -replace '^[vV]', ''
    return "$RepoUrl/releases/download/v$v/KB-Remote-Setup-$v-windows-x64.exe"
}

function Invoke-FromSource {
    Write-Step "Building and installing KB-Remote from source"
    $root = $PSScriptRoot
    if (-not (Test-Path (Join-Path $root "pyproject.toml"))) {
        Fail "-FromSource must be run from a repository checkout."
    }
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Fail "Python 3.10+ is required for -FromSource. Install it from https://python.org"
    }
    $venv = Join-Path $root "venv"
    if (-not (Test-Path $venv)) { python -m venv $venv }
    $pip = Join-Path $venv "Scripts\pip.exe"
    & $pip install --upgrade pip setuptools wheel -q
    & $pip install -e ".[win]" -q
    Write-Ok "Installed into $venv (run $(Join-Path $venv 'Scripts\kb-remote.exe'))"
    if (-not $NoLaunch) { Start-Process (Join-Path $venv "Scripts\kb-remote.exe") }
    return
}

function Test-AlreadyInstalled {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\$AppName\$ExeName"),
        (Join-Path $env:ProgramFiles "$AppName\$ExeName")
    )
    if ("${env:ProgramFiles(x86)}") {
        $candidates += (Join-Path "${env:ProgramFiles(x86)}" "$AppName\$ExeName")
    }
    foreach ($path in $candidates) {
        if ($path -and (Test-Path $path)) { return $path }
    }
    return ""
}

function Find-InstalledExe {
    if ($InstallDir -and (Test-Path (Join-Path $InstallDir $ExeName))) {
        return (Join-Path $InstallDir $ExeName)
    }
    $found = Test-AlreadyInstalled
    if ($found) { return $found }
    return ""
}

# ---------------------------------------------------------------------------

if ($FromSource) {
    Invoke-FromSource
    exit 0
}

Assert-SupportedWindows
Enable-Tls12

$existing = Test-AlreadyInstalled
if ($existing -and -not $Force -and $Version -eq "latest") {
    Write-Note "KB-Remote already appears to be installed at $existing."
    Write-Note "Re-run with -Force to upgrade / reinstall."
}

Install-VCRuntime

$url = Get-SetupUrl
$setup = Join-Path $env:TEMP "KB-Remote-Setup.exe"
Write-Step "Downloading $AppName ($Version)"
Write-Ok "$url"
try {
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $setup
} catch {
    Fail "Download failed: $($_.Exception.Message)`nCheck your connection or pass -Version with a published release."
}

$head = [System.IO.File]::ReadAllBytes($setup)
if ($head.Length -lt 2 -or $head[0] -ne 0x4D -or $head[1] -ne 0x5A) {
    Remove-Item $setup -Force -ErrorAction SilentlyContinue
    Fail "The downloaded file is not a valid Windows executable (release asset missing?)."
}
Write-Ok ("Downloaded {0:N1} MB" -f ((Get-Item $setup).Length / 1MB))

Write-Step "Installing"
$innoArgs = @("/NORESTART", "/SP-", "/CLOSEAPPLICATIONS", "/SUPPRESSMSGBOXES")
if (-not $Interactive) { $innoArgs += "/VERYSILENT" }
if ($InstallDir)       { $innoArgs += "/DIR=`"$InstallDir`"" }
if (Test-IsAdmin)      { $innoArgs += "/ALLUSERS" } else { $innoArgs += "/CURRENTUSER" }

$proc = Start-Process -FilePath $setup -ArgumentList $innoArgs -Wait -PassThru
switch ($proc.ExitCode) {
    0     { Write-Ok "Installed." }
    3010  { Write-Note "Installed. A restart is recommended to finish." }
    1641  { Write-Note "Installed; the machine is restarting." }
    default { Fail "The setup program exited with code $($proc.ExitCode)." }
}
Remove-Item $setup -Force -ErrorAction SilentlyContinue

$exe = Find-InstalledExe
if (-not $exe) { $exe = Join-Path $env:LOCALAPPDATA "Programs\$AppName\$ExeName" }

Write-Host ""
Write-Host "$AppName is installed." -ForegroundColor Green
Write-Host "  Location: $exe"
Write-Host "  Launch  : Start menu -> $AppName  (or the shortcut on the desktop)"
Write-Host ""

if (-not $NoLaunch) {
    if (Test-Path $exe) { Start-Process $exe }
    else { Write-Note "Could not locate the executable to launch it; use the Start menu." }
}
