; Particle Lab v2.2 — Inno Setup script
; Output: dist\ParticleLab_v2.2_Setup.exe (~320 MB)
;
; End-user flow:
;   1. Download ParticleLab_v2.2_Setup.exe
;   2. Double-click → Korean install wizard → Next → Install
;   3. No admin prompt (lowest privileges, per-user install to %LOCALAPPDATA%\Programs)
;   4. Desktop + Start menu shortcut to "Particle Lab v2" (with app icon)
;   5. Click shortcut → app launches (browser tab opens to UI)
;   6. Uninstall via Control Panel / Settings > Apps

#define MyAppName "Particle Lab v2"
#define MyAppVersion "2.2.0"
#define MyAppPublisher "Sejong University Particle Analysis Lab"
#define MyAppExeName "Particle Lab v2.exe"

[Setup]
AppId={{B7F9C2A3-4D8E-4F1A-9B6C-7E8F1A2B3C4D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppSupportURL=https://github.com/anthropics/claude-code
VersionInfoVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist
OutputBaseFilename=ParticleLab_v2.2_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\app.ico
SetupIconFile=app.ico
ShowLanguageDialog=no
LanguageDetectionMethod=none

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 아이콘 만들기"; GroupDescription: "추가 작업:"; Flags: checkedonce

[Files]
; 전체 휴대용 번들 — runtime\python\, runtime\node\, runtime\site-packages\, app\, basic_pt\, *.py, Particle Lab v2.exe, STOP.bat, ...
Source: "dist\Particle_lab_v2_win\*"; DestDir: "{app}"; Excludes: "logs\*,.DS_Store,.streamlit,__pycache__"; Flags: ignoreversion recursesubdirs createallsubdirs
; .next 는 Mac SMB 공유에서 Hidden 속성으로 보여 와일드카드 *가 놓침 — 명시적 라인.
; Next.js standalone 실행에 필요한 모든 것을 standalone/ 안에 평면 복사.
Source: "dist\Particle_lab_v2_win\app\frontend\.next\standalone\server.js"; DestDir: "{app}\app\frontend\.next\standalone"; Flags: ignoreversion
Source: "dist\Particle_lab_v2_win\app\frontend\.next\standalone\package.json"; DestDir: "{app}\app\frontend\.next\standalone"; Flags: ignoreversion
Source: "dist\Particle_lab_v2_win\app\frontend\.next\standalone\node_modules\*"; DestDir: "{app}\app\frontend\.next\standalone\node_modules"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\Particle_lab_v2_win\app\frontend\.next\standalone\.next\*"; DestDir: "{app}\app\frontend\.next\standalone\.next"; Flags: ignoreversion recursesubdirs createallsubdirs
; public/ may or may not exist
Source: "dist\Particle_lab_v2_win\app\frontend\.next\standalone\public\*"; DestDir: "{app}\app\frontend\.next\standalone\public"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\app.ico"
Name: "{autoprograms}\{#MyAppName} 종료"; Filename: "{app}\STOP.bat"; WorkingDir: "{app}"; IconFilename: "{sys}\shell32.dll"; IconIndex: 27
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\app.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; 제거 전에 백그라운드 프로세스 정리
Filename: "{app}\STOP.bat"; Flags: runhidden; RunOnceId: "StopServers"

[UninstallDelete]
; 로그, 세션, 캐시는 자동 정리
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\app\backend\data\uploads"
Type: filesandordirs; Name: "{app}\app\backend\data\sessions"
Type: filesandordirs; Name: "{app}\app\data\sessions"
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
