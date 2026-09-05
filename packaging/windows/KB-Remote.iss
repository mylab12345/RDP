; KB-Remote — professional Windows installer (Inno Setup 6).
;
; Prerequisites (on the Windows build machine):
;   1. pip install .[win] pyinstaller
;   2. pyinstaller packaging\rdpstudio.spec   (Release build, see build-windows.ps1)
;   3. iscc packaging\windows\KB-Remote.iss
;
; Output: a SINGLE self-contained setup exe:
;   dist\KB-Remote-Setup-<version>-x64.exe
; No Python, WSL, Docker, or manual dependency installation is required
; on the target machine. RDP uses the built-in Windows client (mstsc);
; SSH/SFTP/OpenSSH and the local shell ship inside the installer.

#define MyAppName "KB-Remote"
#define MyAppPublisher "KB-Remote contributors"
#define MyAppURL "https://github.com/mylab12345/RDP"
#define MyAppExeName "kb-remote.exe"
#define MyAppId "{A531FAD6-A0F9-469C-BF5B-769BA62B4969}"
; Version is injected by the build script (/DMyAppVersion=...); fallback for IDE builds.
#ifndef MyAppVersion
  #define MyAppVersion "0.9.0"
#endif

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} - remote-access workbench (SSH/RDP)
VersionInfoProductName={#MyAppName}
VersionInfoCopyright=Copyright (c) KB-Remote contributors. MIT License.
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
LicenseFile=..\..\LICENSE
SetupIconFile=..\..\src\rdpstudio\resources\icons\logo.ico
WizardImageFile=compiler:WizModernImage-IS.bmp
WizardSmallImageFile=compiler:WizModernSmallImage-IS.bmp
OutputDir=..\..\dist
OutputBaseFilename=KB-Remote-Setup-{#MyAppVersion}-x64
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UsePreviousAppDir=yes
UsePreviousGroup=yes
CloseApplications=yes
RestartApplications=no
AppMutex=KB-Remote-SingleInstance
ShowLanguageDialog=no
AllowNoIcons=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; PyInstaller Release output (exe + Qt/PySide6 runtime, plugins, assets).
Source: "..\..\dist\KB-Remote\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "Launch {#MyAppName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"; Comment: "Remove {#MyAppName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; Comment: "Launch {#MyAppName}"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Remove stale files from older layouts before installing the upgrade.
Type: files; Name: "{app}\rdpstudio.exe"
Type: files; Name: "{app}\KB-Remote.exe"

[UninstallDelete]
; Installer drops only binaries; user data under %APPDATA%\KB-Remote
; (sessions, vault, logs) is deliberately preserved on uninstall.
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
function IsMstscPresent(): Boolean;
var
  SysDir: string;
begin
  SysDir := ExpandConstant('{sys}\mstsc.exe');
  Result := FileExists(SysDir) or (Trim(GetEnv('SystemRoot')) <> '');
end;

function InitializeSetup(): Boolean;
var
  Ver: TWindowsVersion;
begin
  Result := True;
  GetWindowsVersionEx(Ver);
  if (Ver.Major < 10) then
  begin
    MsgBox(
      'KB-Remote requires Windows 10 or later.' + #13#10 +
      'Setup cannot continue on this version of Windows.',
      mbError, MB_OK);
    Result := False;
    exit;
  end;
  if not IsMstscPresent() then
  begin
    { Non-fatal: some stripped/server SKUs hide mstsc. SSH still works;
      RDP sessions will report the missing client gracefully. }
    MsgBox(
      'The Windows RDP client (mstsc.exe) was not detected.' + #13#10#13#10 +
      'KB-Remote will still install: SSH/SFTP and local shells work normally. ' +
      'RDP sessions need the built-in Remote Desktop client.',
      mbInformation, MB_OK);
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
end;
