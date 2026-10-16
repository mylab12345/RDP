; KB-Remote universal Inno Setup installer (Windows clients + servers)
; Build: iscc packaging\windows\kb-remote-setup.iss
; Requires: Inno Setup 6.3+ (https://jrsoftware.org/isinfo.php)
;
; The PyInstaller bundle it wraps already contains the Python runtime, Qt/
; PySide6 and every Python dependency, so the result needs no other software
; on Windows 10 1809+ / Server 2019+ (x64, and ARM64 via x64 emulation).

#define AppName "KB-Remote"
#define AppVersion "0.9.0"
#define AppPublisher "KB-Remote contributors"
#define AppURL "https://github.com/mylab12345/RDP"
#define AppExeName "KB-Remote.exe"
; Stable AppId keeps upgrades/uninstall matching across machines and versions.
#define AppId "{{7F3B1C2E-9D4A-4E7B-8C1F-2A6E5B0D9C41}"
; Anchor paths to this script so compilation works regardless of the working
; directory: CI runs from the repo root, build.ps1 from packaging\windows.
#define RepoRoot SourcePath + "\..\.."
#define SourceDir RepoRoot + "\dist\KB-Remote"
#define OutputDir RepoRoot + "\installer"
#define OutputBaseName "KB-Remote-Setup"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=auto
UsePreviousAppDir=yes
AllowNoIcons=yes
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBaseName}-{#AppVersion}-windows-x64
SetupIconFile={#RepoRoot}\src\rdpstudio\resources\icons\logo.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
CloseApplications=yes
RestartApplications=no
; Universal coverage: 64-bit Windows 10/11 and Server 2019+, native or ARM64
; (the x64 payload runs under Windows' x64 emulation on ARM64).
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
; Per-user install by default (no admin); admins can opt into all-users.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} - remote-access workbench (SSH/RDP/Local terminal)
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}
VersionInfoCopyright=MIT License

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 0,6.1
Name: "fileassoc"; Description: "Associate .rdp and .ssh config files"; GroupDescription: "File associations"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Comment: "Remote-access workbench (SSH/RDP/Local terminal)"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: quicklaunchicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Registry]
; Optional file associations (per-user, so no admin is needed).
Root: HKCU; Subkey: "Software\Classes\.rdp"; ValueType: string; ValueData: "KBRemote.RDP"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKCU; Subkey: "Software\Classes\KBRemote.RDP"; ValueType: string; ValueData: "RDP Connection File"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKCU; Subkey: "Software\Classes\KBRemote.RDP\DefaultIcon"; ValueType: string; ValueData: "{app}\{#AppExeName},0"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKCU; Subkey: "Software\Classes\KBRemote.RDP\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExeName}"" ""%1"""; Flags: uninsdeletekey; Tasks: fileassoc

Root: HKCU; Subkey: "Software\Classes\.ssh"; ValueType: string; ValueData: "KBRemote.SSH"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKCU; Subkey: "Software\Classes\KBRemote.SSH"; ValueType: string; ValueData: "SSH Config File"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKCU; Subkey: "Software\Classes\KBRemote.SSH\DefaultIcon"; ValueType: string; ValueData: "{app}\{#AppExeName},0"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKCU; Subkey: "Software\Classes\KBRemote.SSH\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExeName}"" ""%1"""; Flags: uninsdeletekey; Tasks: fileassoc
