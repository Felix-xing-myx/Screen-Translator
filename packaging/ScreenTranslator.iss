#define MyAppName "Screen Translator"
#define MyAppVersion "1.0.4"
#define MyAppExeName "ScreenTranslator.exe"

[Setup]
AppId={{B4F5A7E4-0C55-4B0D-8F7A-9B7B8B1B5D17}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\ScreenTranslator
DisableDirPage=no
DefaultGroupName={#MyAppName}
SetupIconFile=..\src\screen_translator\assets\screen_translator.ico
UninstallDisplayIcon={app}\ScreenTranslator.exe
OutputDir=..\dist\installer
OutputBaseFilename=ScreenTranslator-Setup-v1.0.4
PrivilegesRequired=lowest
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "chinesesimp"; MessagesFile: "Languages\ChineseSimplified.isl"

[Files]
Source: "..\dist\ScreenTranslator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "startmenu"; Description: "创建开始菜单快捷方式"; GroupDescription: "附加快捷方式："; Flags: unchecked
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\screen_translator\assets\screen_translator.ico"; Tasks: startmenu
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\screen_translator\assets\screen_translator.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\ScreenTranslator"
