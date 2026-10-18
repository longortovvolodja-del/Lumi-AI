; Lumi AI Windows installer (Inno Setup)
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{7E7B0F9D-3B4B-4DF0-9A0B-1DCC5F0A12A4}
AppName=Lumi AI
AppVersion={#AppVersion}
AppPublisher=Lumi AI
DefaultDirName={localappdata}\Programs\Lumi AI
DefaultGroupName=Lumi AI
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=Lumi-Setup-{#AppVersion}
SetupIconFile=..\assets\lumi.ico
UninstallDisplayIcon={app}\Lumi.exe
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
MinVersion=10.0
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
Uninstallable=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные задачи:"; Flags: unchecked

[Files]
Source: "..\dist\Lumi\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Lumi AI"; Filename: "{app}\Lumi.exe"
Name: "{autodesktop}\Lumi AI"; Filename: "{app}\Lumi.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Lumi.exe"; Description: "Запустить Lumi AI"; Flags: postinstall nowait skipifsilent
