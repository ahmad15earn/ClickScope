; Inno Setup script: a normal Windows installer that lets the user choose the install folder.
#define MyAppName "ClickScope"
#define MyAppVersion "1.0.0"

[Setup]
AppId={{B3C2A7E4-5D61-4F0B-9C1E-7A2D3E5F8A10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=ClickScope
DefaultDirName={autopf}\ClickScope
DisableDirPage=no
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\ClickScope.exe
SetupIconFile=..\assets\app.ico
OutputDir=..\installer_output
OutputBaseFilename=ClickScope-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startup"; Description: "Start ClickScope when Windows starts (recommended: it runs quietly in the background)"; GroupDescription: "Options:"

[Files]
Source: "..\dist\ClickScope.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\ClickScope"; Filename: "{app}\ClickScope.exe"
Name: "{autodesktop}\ClickScope"; Filename: "{app}\ClickScope.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "ClickScope"; ValueData: """{app}\ClickScope.exe"" --minimized"; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\ClickScope.exe"; Description: "Launch ClickScope"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im ClickScope.exe"; Flags: runhidden; RunOnceId: "StopClickScope"
