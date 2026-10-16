<#>
.SYNOPSIS
    Build KB-Remote Windows installer (PyInstaller + Inno Setup)

.DESCRIPTION
    1. Creates venv, installs deps + PyInstaller
    2. Builds onedir bundle with PyInstaller
    3. Builds NSIS/Inno Setup installer
    Output: installer\KB-Remote-Setup-<version>-windows-x64.exe
            installer\KB-Remote-Setup.exe  (+ install.ps1 / install.cmd)

.PREREQUISITES
    - Windows 10/11 / Server 2019+
    - Python 3.10+ in PATH
    - Inno Setup 6.3+ (https://jrsoftware.org/isinfo.php) in PATH as 'iscc'
    - Git (for version tag)

.EXAMPLE
    .\build.ps1
    .\build.ps1 -Version 0.9.1 -SignTool "C:\Path\signtool.exe" -CertThumbprint "ABC123"
#>

param(
    [string]$Version = "",
    [string]$SignTool = "",
    [string]$CertThumbprint = "",
    [switch]$SkipPyInstaller,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Get-Item -Path ".\" -Verbose).FullName
$SrcDir = Join-Path $RepoRoot "src"
$PackagingDir = Join-Path $RepoRoot "packaging"
$WindowsPackagingDir = Join-Path $PackagingDir "windows"
$DistDir = Join-Path $RepoRoot "dist"
$InstallerDir = Join-Path $RepoRoot "installer"
$VenvDir = Join-Path $RepoRoot "venv"
$PyInstallerSpec = Join-Path $WindowsPackagingDir "rdpstudio-windows.spec"
$InnoSpec = Join-Path $WindowsPackagingDir "kb-remote-setup.iss"

function Get-Version {
    if ($Version) { return $Version }
    # Try to get from git tag
    $tag = git describe --tags --abbrev=0 2>$null
    if ($tag -match '^v?(\d+\.\d+\.\d+)') { return $matches[1] }
    # Fallback to pyproject.toml
    $pyproject = Get-Content (Join-Path $RepoRoot "pyproject.toml") -Raw
    if ($pyproject -match 'version\s*=\s*"(\d+\.\d+\.\d+)"') { return $matches[1] }
    return "0.9.0"
}

$AppVersion = Get-Version
Write-Host "Building KB-Remote v$AppVersion" -ForegroundColor Cyan

# Ensure dirs exist
if (-not (Test-Path $DistDir)) { New-Item -ItemType Directory -Path $DistDir | Out-Null }
if (-not (Test-Path $InstallerDir)) { New-Item -ItemType Directory -Path $InstallerDir | Out-Null }

# 1. Setup venv and install deps
if (-not $SkipPyInstaller) {
    Write-Host "Setting up Python venv..." -ForegroundColor Yellow
    if (-not (Test-Path $VenvDir)) {
        python -m venv $VenvDir
    }
    $pip = Join-Path $VenvDir "Scripts\pip.exe"
    & $pip install --upgrade pip setuptools wheel -q
    Write-Host "Installing KB-Remote [win] + PyInstaller..." -ForegroundColor Yellow
    & $pip install -e . pyinstaller ".[win]" -q
}

# 2. Run PyInstaller
if (-not $SkipPyInstaller) {
    Write-Host "Running PyInstaller..." -ForegroundColor Yellow
    $pyinstaller = Join-Path $VenvDir "Scripts\pyinstaller.exe"
    if (-not (Test-Path $pyinstaller)) {
        $pyinstaller = "pyinstaller"
    }
    # Clean previous build
    if (Test-Path (Join-Path $DistDir "KB-Remote")) {
        Remove-Item (Join-Path $DistDir "KB-Remote") -Recurse -Force
    }
    Set-Location $RepoRoot
    & $pyinstaller --clean $PyInstallerSpec
    if (-not (Test-Path (Join-Path $DistDir "KB-Remote\KB-Remote.exe"))) {
        throw "PyInstaller failed: KB-Remote.exe not found in dist\KB-Remote"
    }
    Write-Host "PyInstaller bundle ready at dist\KB-Remote" -ForegroundColor Green
}

# 3. Build Inno Setup installer
if (-not $SkipInstaller) {
    Write-Host "Building Inno Setup installer..." -ForegroundColor Yellow
    $iscc = Get-Command "iscc" -ErrorAction SilentlyContinue
    if (-not $iscc) {
        # Common install locations
        $candidates = @(
            "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "${env:ProgramFiles}\Inno Setup 5\ISCC.exe",
            "${env:ProgramFiles(x86)}\Inno Setup 5\ISCC.exe"
        )
        foreach ($c in $candidates) {
            if (Test-Path $c) { $iscc = $c; break }
        }
    }
    if (-not $iscc) {
        throw "Inno Setup compiler (iscc) not found. Install Inno Setup 6+ from https://jrsoftware.org/isinfo.php"
    }

    # Update version in .iss (AppVersion)
    $issContent = Get-Content $InnoSpec -Raw
    $issContent = $issContent -replace '#define AppVersion ".*"', "#define AppVersion `"$AppVersion`""
    $issContent | Set-Content $InnoSpec -Encoding UTF8

    $isccArgs = @($InnoSpec)
    if ($SignTool -and $CertThumbprint) {
        $isccArgs += "/S$SignTool", "/SCertThumbprint=$CertThumbprint"
    }

    Set-Location $WindowsPackagingDir
    & $iscc @isccArgs

    $installerPattern = "KB-Remote-Setup-${AppVersion}-windows-x64.exe"
    $installerPath = Join-Path $InstallerDir $installerPattern
    if (Test-Path $installerPath) {
        Write-Host "Installer created: $installerPath" -ForegroundColor Green
        Write-Host "Size: {0:N2} MB" -f ((Get-Item $installerPath).Length / 1MB)
        # Stable names so the one universal link keeps working release to
        # release: .../releases/latest/download/KB-Remote-Setup.exe
        Copy-Item $installerPath (Join-Path $InstallerDir "KB-Remote-Setup.exe") -Force
        Copy-Item (Join-Path $RepoRoot "install.ps1") (Join-Path $InstallerDir "install.ps1") -Force
        Copy-Item (Join-Path $WindowsPackagingDir "install.cmd") (Join-Path $InstallerDir "install.cmd") -Force
    } else {
        # Try to find any matching file
        $found = Get-ChildItem $InstallerDir -Filter "KB-Remote-Setup-*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($found) {
            Write-Host "Installer created: $($found.FullName)" -ForegroundColor Green
        } else {
            throw "Installer not found in $InstallerDir"
        }
    }
}

Write-Host "`n=== Build complete ===" -ForegroundColor Cyan
Write-Host "Bundle: dist\KB-Remote\KB-Remote.exe"
Write-Host "Installer: installer\KB-Remote-Setup-${AppVersion}-windows-x64.exe"
Write-Host "Stable : installer\KB-Remote-Setup.exe (publish as a release asset)"