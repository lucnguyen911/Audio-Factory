; ──────────────────────────────────────────────────────────────────────────────
; installer_config.iss
; ──────────────────────────────────────────────────────────────────────────────
; Inno Setup Script cho Audio Factory Premium.
; Hỗ trợ: Cài đặt thường + Silent Install (auto-update).
;
; Biên dịch: Inno Setup 6.x
;   iscc.exe installer_config.iss
;
; Tác giả: Nguyễn Văn Lực
; ──────────────────────────────────────────────────────────────────────────────

#define MyAppName "Audio Factory Premium"
#ifndef MyAppVersion
  #error MyAppVersion must be supplied from version.py by the build script
#endif
#define MyAppPublisher "Lực Nguyễn"
#define MyAppURL "https://audiofactory.app"
#define MyAppExeName "Audio Factory.exe"
#define MyAppCopyright "© 2026 Lực Nguyễn. All rights reserved."

[Setup]
; AppId duy nhất cho bản Premium (khác với các ISS cũ)
AppId={{A3F7C8D1-E5B2-4A9F-B6D1-2C8E4F5A7B9E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
AppCopyright={#MyAppCopyright}

; Thư mục cài đặt mặc định
DefaultDirName={autopf}\Audio Factory
UsePreviousAppDir=yes
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Cho phép người dùng chọn cài cho user hiện tại hoặc tất cả users
PrivilegesRequiredOverridesAllowed=dialog

; Output
OutputDir=dist
OutputBaseFilename=Audio_Factory_Premium_Setup_v{#MyAppVersion}
SetupIconFile=assets\logo.ico

; Nén tối đa
Compression=lzma2/ultra64
InternalCompressLevel=ultra
SolidCompression=yes

; Giao diện hiện đại
WizardStyle=modern
WizardSizePercent=110

; Hiển thị thông tin phiên bản trong Control Panel
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Audio Factory Premium - Bộ xử lý âm thanh chuyên nghiệp
VersionInfoCopyright={#MyAppCopyright}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

; Hỗ trợ gỡ cài đặt sạch sẽ
Uninstallable=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

; Yêu cầu đóng ứng dụng trước khi cài đặt/gỡ cài đặt
CloseApplications=yes
CloseApplicationsFilter={#MyAppExeName}
RestartApplications=no

; Hỗ trợ silent install cho auto-update
; Sử dụng: Setup.exe /VERYSILENT /DIR="C:\Program Files\Audio Factory"
AllowNoIcons=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Phím tắt Desktop — mặc định được chọn
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Sao chép duy nhất file .exe One-file vào thư mục cài đặt
Source: "dist\Audio Factory\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Phím tắt Menu Start
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "Khởi chạy Audio Factory Premium"

; Phím tắt Desktop (nếu người dùng chọn)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; Comment: "Khởi chạy Audio Factory Premium"

[Run]
; Chạy ứng dụng sau khi cài đặt (chế độ tương tác, bỏ qua nếu silent)
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\*.log"
Type: files; Name: "{app}\*.tmp"
Type: dirifempty; Name: "{app}"

; Xóa dữ liệu ứng dụng trong APPDATA (tùy chọn — yêu cầu xác nhận)
; Uncomment dòng sau nếu muốn xóa license và config khi gỡ cài đặt:
; Type: filesandordirs; Name: "{userappdata}\AudioFactory"

[UninstallRun]
; Tắt tiến trình ứng dụng trước khi gỡ cài đặt (tránh lỗi file đang dùng)
Filename: "taskkill.exe"; Parameters: "/F /IM ""{#MyAppExeName}"""; Flags: runhidden; RunOnceId: "KillApp"

[Code]
// ── Pascal Script: Kiểm tra và đóng ứng dụng đang chạy trước khi cài đặt ──

function IsAppRunning(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('tasklist.exe', '/FI "IMAGENAME eq {#MyAppExeName}" /NH', '',
       SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := (ResultCode = 0);
end;

function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  // Tự động đóng ứng dụng đang chạy khi cài silent
  if WizardSilent then
  begin
    Exec('taskkill.exe', '/F /IM "{#MyAppExeName}"', '',
         SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(1000); // Đợi 1 giây để tiến trình hoàn tất đóng
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Log cài đặt hoàn tất
    Log('Audio Factory Premium v{#MyAppVersion} installed successfully.');
  end;
end;
