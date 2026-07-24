#define MyAppName "Screen Translator"
#define MyAppVersion "0.1.0"
#define MyAppExeName "ScreenTranslator.exe"

[Setup]
AppId={{B4F5A7E4-0C55-4B0D-8F7A-9B7B8B1B5D17}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\ScreenTranslator
DefaultGroupName={#MyAppName}
OutputDir=..\dist\installer
OutputBaseFilename=ScreenTranslator-Setup
PrivilegesRequired=lowest
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64

[Files]
Source: "..\dist\ScreenTranslator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

