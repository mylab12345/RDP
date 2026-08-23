; Inno Setup script for KB-Remote (Windows).
; Prerequisite: run `pyinstaller packaging/rdpstudio.spec` first.
; Build:  iscc packaging\windows\KB-Remote.iss

#define MyAppName "KB-Remote"
#define MyAppVersion GetVersionNumbersString("..\..\dist\KB-Remote\kb-remote.exe")
#define MyAppPublisher "KB-Remote contributors"
#define MyAppExeName "kb-remote.exe"

[Setup]
AppId={{8C6F1B2A-77C4-4D9B-9C0D-RDPSTUDIO01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\..\dist
OutputBaseFilename=KB-Remote-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Files]
Source: "..\..\dist\KB-Remote\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nSSH/SFTP works out of the box. RDP sessions use the built-in Windows client (mstsc).
