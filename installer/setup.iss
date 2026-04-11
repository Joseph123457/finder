; Inno Setup script for JeAn Finder
; Build: iscc setup.iss
; Prerequisite: `pyinstaller build.spec` executed, resulting in dist\JeAnFinder\

#define AppName       "JeAn Finder"
#define AppVersion    "0.1.0"
#define AppPublisher  "JeAn Finder"
#define AppExe        "JeAnFinder.exe"

[Setup]
AppId={{7C1E5A8C-4D2B-4E57-9A1F-0F3C2D9A4F10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\JeAnFinder
DefaultGroupName=JeAn Finder
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=JeAnFinder_Setup_{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#AppExe}
; 한국어 우선
ShowLanguageDialog=auto

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\JeAnFinder\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
