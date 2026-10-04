; Instalador de Windows (Inno Setup). Se compila en GitHub Actions.
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{6B0E4C2A-8F3D-4C61-9E52-1A7D3B9C0F11}
AppName=LoL Coach IA
AppVersion={#AppVersion}
AppPublisher=IA-LOL
DefaultDirName={localappdata}\Programs\LoLCoach
DefaultGroupName=LoL Coach IA
DisableProgramGroupPage=yes
; Instalación por usuario: no pide permisos de administrador y permite guardar el .env.
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=LoLCoach-Instalador
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\LoLCoach.exe

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\LoLCoach.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\.env.example"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\LoL Coach IA"; Filename: "{app}\LoLCoach.exe"; WorkingDir: "{app}"
Name: "{group}\Desinstalar LoL Coach IA"; Filename: "{uninstallexe}"
Name: "{autodesktop}\LoL Coach IA"; Filename: "{app}\LoLCoach.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\LoLCoach.exe"; Description: "Abrir LoL Coach IA ahora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\.env"
Type: files; Name: "{app}\informe.md"
