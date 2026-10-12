; ════════════════════════════════════════════════════════════
; Inno Setup script for Saliga Sari-Sari POS
; ════════════════════════════════════════════════════════════

#define MyAppName "Saliga Sari-Sari Store POS"
#define MyAppShortName "SariSariPOS"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Group 2 Development Team"
#define MyAppExeName "SariSariPOS.exe"
#define MyBuildDir "..\dist\SariSariPOS"

[Setup]
AppId={{9C4D3F1A-8B2E-4A7D-9F1C-3D5E7A8B9C0D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppShortName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename={#MyAppShortName}-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce
Name: "startmenu"; Description: "Create a Start Menu entry"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce

[Files]
Source: "{#MyBuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\.env.example"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--app"; Tasks: startmenu
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"; Tasks: startmenu
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--app"; Tasks: desktopicon

[Run]
; IMPORTANT: runascurrentuser launches the app as the logged-in user,
; NOT as the admin who ran the installer. This is required so the app
; can write to %LOCALAPPDATA% without elevation.
Filename: "{app}\{#MyAppExeName}"; Parameters: "--app"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent runascurrentuser

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM {#MyAppExeName} /F"; Flags: runhidden; RunOnceId: "KillApp"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\_internal\__pycache__"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  DataDir, LogsDir, BackupsDir: String;
begin
  if CurStep = ssPostInstall then
  begin
    ; Ensure per-user data folder exists
    DataDir := ExpandConstant('{localappdata}\SariSariPOS');
    LogsDir := ExpandConstant('{localappdata}\SariSariPOS\logs');
    BackupsDir := ExpandConstant('{localappdata}\SariSariPOS\backups');

    if not DirExists(DataDir) then
      CreateDir(DataDir);
    if not DirExists(LogsDir) then
      CreateDir(LogsDir);
    if not DirExists(BackupsDir) then
      CreateDir(BackupsDir);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
  Response: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\SariSariPOS');
    if DirExists(DataDir) then
    begin
      Response := MsgBox(
        'Do you want to delete your POS data (sales history, users, products)?' + #13#10 + #13#10 +
        'Choose No if you want to keep the data to restore later.',
        mbConfirmation, MB_YESNO or MB_DEFBUTTON2
      );
      if Response = IDYES then
      begin
        DelTree(DataDir, True, True, True);
      end;
    end;
  end;
end;
