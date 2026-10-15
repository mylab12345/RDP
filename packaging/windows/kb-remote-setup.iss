; KB-Remote Inno Setup installer script
; Build: iscc packaging\windows\kb-remote-setup.iss
; Requires: Inno Setup 6+ (https://jrsoftware.org/isinfo.php)

#define AppName "KB-Remote"
#define AppVersion "0.9.0"
#define AppPublisher "KB-Remote contributors"
#define AppURL "https://github.com/mylab12345/RDP"
#define AppExeName "KB-Remote.exe"
#define SourceDir "dist\KB-Remote"
#define OutputDir "installer"
#define OutputBaseName "KB-Remote-Setup"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBaseName}-{#AppVersion}-windows-x86_64
SetupIconFile={#SourceDir}\rdpstudio\resources\icons\logo.ico
Compression=lzma/ultra64
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
PrivilegesRequired=lowest
DisableDirPage=no
DisableProgramGroupPage=no
CreateAppDir=yes
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} - Cross-platform remote-access workbench (SSH/RDP/Local terminal)
VersionInfoCopyright=MIT License
SignedUninstaller=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 0,6.1
Name: "fileassoc"; Description: "Associate .rdp and .ssh config files"; GroupDescription: "File associations"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Comment: "Cross-platform SSH/RDP/Local terminal workbench"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"; WorkingDir: "{app}"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: quicklaunchicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Registry]
; File associations (optional)
Root: HKCU; Subkey: "Software\Classes\.rdp"; ValueType: string; ValueData: "KBRemote.RDP"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKCU; Subkey: "Software\Classes\KBRemote.RDP"; ValueType: string; ValueData: "RDP Connection File"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKCU; Subkey: "Software\Classes\KBRemote.RDP\DefaultIcon"; ValueType: string; ValueData: "{app}\{#AppExeName},0"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKCU; Subkey: "Software\Classes\KBRemote.RDP\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExeName}"" ""%1"""; Flags: uninsdeletekey; Tasks: fileassoc

Root: HKCU; Subkey: "Software\Classes\.ssh"; ValueType: string; ValueData: "KBRemote.SSH"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKCU; Subkey: "Software\Classes\KBRemote.SSH"; ValueType: string; ValueData: "SSH Config File"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKCU; Subkey: "Software\Classes\KBRemote.SSH\DefaultIcon"; ValueType: string; ValueData: "{app}\{#AppExeName},0"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKCU; Subkey: "Software\Classes\KBRemote.SSH\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExeName}"" ""%1"""; Flags: uninsdeletekey; Tasks: fileassoc

[Code]
// Ensure KB_REMOTE_HOME is set for portable config if needed
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    // App handles its own config dir (KB_REMOTE_HOME or %LOCALAPPDATA%\KB-Remote)
  end;
end;