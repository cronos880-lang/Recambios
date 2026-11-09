#define MyAppName "Recambios"
#define MyAppVersion "0.2.6"
#define MyAppExeName "Recambios.exe"

[Setup]
; Conserva el AppId de las versiones anteriores para actualizar en el mismo lugar.
AppId={{B874EAAE-F55C-4324-BDE2-05F54E782D47}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} V{#MyAppVersion}
DefaultDirName={localappdata}\Programs\Recambios
DefaultGroupName=Recambios
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
UsePreviousAppDir=yes
OutputDir=salida_instalador
OutputBaseFilename=Recambios_Instalador_V0_2_6_WebView2_Maximizado_Restauracion_Windows
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=recambios.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
DisableProgramGroupPage=yes
DisableDirPage=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear icono en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "dist\Recambios\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Bootstrapper auténtico, descargado y validado durante la compilación en Windows.
Source: "prerequisitos\MicrosoftEdgeWebView2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: WebView2Missing

[Icons]
Name: "{autoprograms}\Recambios"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\Recambios"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; WorkingDir: "{app}"

[Run]
Filename: "{tmp}\MicrosoftEdgeWebView2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Instalando Microsoft WebView2 Runtime..."; Flags: runhidden waituntilterminated; Check: WebView2Missing
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir Recambios"; Flags: nowait postinstall skipifsilent; Check: WebView2Installed

[Code]
function HasWebView2AtRoot(RootKey: Integer): Boolean;
var
  Version: String;
begin
  Result := RegQueryStringValue(
    RootKey,
    'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'pv', Version
  ) and (Version <> '') and (Version <> '0.0.0.0');
end;

function WebView2Installed: Boolean;
begin
  Result := HasWebView2AtRoot(HKCU) or HasWebView2AtRoot(HKLM32);
end;

function WebView2Missing: Boolean;
begin
  Result := not WebView2Installed;
end;
