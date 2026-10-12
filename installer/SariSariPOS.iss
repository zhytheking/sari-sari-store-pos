; ════════════════════════════════════════════════════════════
; Inno Setup script for Saliga Sari-Sari POS
;
; Requirements:
;   - Inno Setup 6 or newer: https://jrsoftware.org/isdl.php
;   - A prior successful PyInstaller build producing
;     dist\SariSariPOS\SariSariPOS.exe
;
; Build:
;   From the project root, after `pyinstaller run.spec`:
;       iscc installer\SariSariPOS.iss
;
; Output:
;   installer\output\SariSariPOS-Setup.exe
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
; SetupIconFile=..\frontend\web\static\assets\images\pos.ico

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
Filename: "{app}\{#MyAppExeName}"; Parameters: "--app"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM {#MyAppExeName} /F"; Flags: runhidden; RunOnceId: "KillApp"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\_internal\__pycache__"

[Code]
// ════════════════════════════════════════════════════════════
// Setup: create empty data\ and logs\ folders on first install
// ════════════════════════════════════════════════════════════
procedure CurStepChanged(CurStep: TSetupStep);
var
  DataDir, LogsDir, BackupsDir: String;
begin
  if CurStep = ssPostInstall then
  begin
    DataDir := ExpandConstant('{app}\data');
    LogsDir := ExpandConstant('{app}\logs');
    BackupsDir := ExpandConstant('{app}\data\backups');

    if not DirExists(DataDir) then
      CreateDir(DataDir);
    if not DirExists(LogsDir) then
      CreateDir(LogsDir);
    if not DirExists(BackupsDir) then
      CreateDir(BackupsDir);
  end;
end;

// ════════════════════════════════════════════════════════════
// Uninstall: ask the user before deleting the database
// ════════════════════════════════════════════════════════════
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
  Response: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{app}\data');
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
