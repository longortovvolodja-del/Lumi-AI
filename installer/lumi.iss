; Lumi AI Windows installer (Inno Setup)
#ifndef AppVersion
  #define AppVersion "0.1.1"
#endif

[Setup]
AppId={{7E7B0F9D-3B4B-4DF0-9A0B-1DCC5F0A12A4}
AppName=Lumi AI
AppVersion={#AppVersion}
AppPublisher=Lumi AI
AppPublisherURL=https://github.com/longortovvolodja-del/Lumi-AI
AppSupportURL=https://github.com/longortovvolodja-del/Lumi-AI/issues
AppUpdatesURL=https://github.com/longortovvolodja-del/Lumi-AI/releases
DefaultDirName={localappdata}\Programs\Lumi AI
DefaultGroupName=Lumi AI
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=Lumi-Internal-Setup
SetupIconFile=..\dist\lumi.ico
UninstallDisplayIcon={app}\Lumi.exe
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
MinVersion=10.0
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
WizardImageFile=..\dist\installer-wizard.bmp
WizardSmallImageFile=..\dist\installer-small.bmp
CloseApplications=force
RestartApplications=no
Uninstallable=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
; Custom welcome/finish text while keeping Inno Setup's native localized controls.
WelcomeLabel1=Добро пожаловать в установщик Lumi AI!
WelcomeLabel2=Неоновая помощница с лисёнком готова поселиться на твоём компьютере.%n%nУстановщик установит Lumi AI и сохранит твои заметки.
FinishedHeadingLabel=Lumi AI готова к запуску!
FinishedLabel=Lumi AI установлена.%n%nНажми «Готово», чтобы закрыть установщик и при желании запустить приложение.

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные задачи:"; Flags: unchecked

[Files]
Source: "..\dist\Lumi\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\LumiUpdater.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Lumi AI"; Filename: "{app}\Lumi.exe"
Name: "{autodesktop}\Lumi AI"; Filename: "{app}\Lumi.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Lumi.exe"; Description: "Запустить Lumi AI"; Flags: postinstall nowait skipifsilent
