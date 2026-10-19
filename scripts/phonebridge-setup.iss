; Compile with build-installer.py. No drivers, network access or app-data deletion.
#ifndef AppVersion
  #error AppVersion must be supplied
#endif
#ifndef PayloadDir
  #error PayloadDir must be supplied
#endif
#ifndef OutputDir
  #error OutputDir must be supplied
#endif

[Setup]
AppId={{57F349D5-19D9-4A01-A035-F8A6E15D785A}
AppName=PhoneBridge
AppVersion={#AppVersion}
AppVerName=PhoneBridge {#AppVersion} Preview
AppPublisher=PhoneBridge contributors
DefaultDirName={localappdata}\Programs\PhoneBridge
DefaultGroupName=PhoneBridge
DisableDirPage=no
DisableProgramGroupPage=yes
AllowNoIcons=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDir}
OutputBaseFilename=PhoneBridge-Setup-{#AppVersion}-windows-x64
UninstallDisplayIcon={app}\PhoneBridge.exe
WizardStyle=modern
Compression=lzma2/fast
SolidCompression=yes
SetupLogging=yes
CloseApplications=no
RestartApplications=no
LicenseFile={#PayloadDir}\LICENSE
InfoBeforeFile={#PayloadDir}\INSTALL-NOTES.txt
VersionInfoVersion={#AppVersion}.0

[Languages]
Name: english; MessagesFile: compiler:Default.isl
#ifdef ChineseLanguage
Name: chinesesimplified; MessagesFile: {#ChineseLanguage}
#endif

[Tasks]
Name: desktopicon; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "{#PayloadDir}\PhoneBridge.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\PhoneBridge-Android.apk"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\INSTALL-NOTES.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\INSTALLER-LICENSES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\PhoneBridge\PhoneBridge"; Filename: "{app}\PhoneBridge.exe"; WorkingDir: "{app}"; AppUserModelID: PhoneBridge.Desktop
Name: "{autoprograms}\PhoneBridge\Android APK"; Filename: "{app}\PhoneBridge-Android.apk"
Name: "{autodesktop}\PhoneBridge"; Filename: "{app}\PhoneBridge.exe"; WorkingDir: "{app}"; Tasks: desktopicon; AppUserModelID: PhoneBridge.Desktop

[Run]
Filename: "{app}\PhoneBridge.exe"; Description: "{cm:LaunchProgram,PhoneBridge}"; Flags: nowait postinstall skipifsilent

; Inno removes only the installed files/shortcuts and its uninstall record.
; Intentionally no UninstallDelete: %LOCALAPPDATA%\PhoneBridge is preserved.
