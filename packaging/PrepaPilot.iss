; Build through scripts/build_release.py, which supplies a strictly staged AppDir.
; AppId MUST remain stable between releases to preserve update/uninstall identity.
#ifndef AppVersion
  #error AppVersion must be supplied by build_release.py
#endif
#ifndef AppDir
  #error AppDir must point to a clean, disposable payload
#endif
#ifndef ReleaseDir
  #error ReleaseDir must be supplied by build_release.py
#endif
#ifndef AppIcon
  #error AppIcon must be supplied by build_release.py
#endif

[Setup]
AppId={{01202F3A-A35E-4ED8-8D43-14612EE01D8F}
AppName=PrépaPilot
AppVersion={#AppVersion}
AppVerName=PrépaPilot {#AppVersion}
AppPublisher=PrépaPilot
VersionInfoVersion={#AppVersion}.0
DefaultDirName={localappdata}\Programs\PrepaPilot
DefaultGroupName=PrépaPilot
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0.17763
DisableProgramGroupPage=yes
DisableDirPage=yes
AllowNoIcons=yes
UninstallDisplayIcon={app}\PrepaPilot.exe
SetupIconFile={#AppIcon}
OutputDir={#ReleaseDir}
OutputBaseFilename=PrepaPilot-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
CloseApplicationsFilter=PrepaPilot.exe
RestartApplications=no
Uninstallable=yes
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[CustomMessages]
english.DesktopShortcut=Create a desktop shortcut
french.DesktopShortcut=Créer un raccourci sur le Bureau
english.ShortcutsGroup=Shortcuts:
french.ShortcutsGroup=Raccourcis :
english.LaunchPrepaPilot=Open PrépaPilot
french.LaunchPrepaPilot=Ouvrir PrépaPilot

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopShortcut}"; GroupDescription: "{cm:ShortcutsGroup}"; Flags: unchecked

[Files]
Source: "{#AppDir}\PrepaPilot.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#AppDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#AppDir}\GUIDE.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#AppDir}\GUIDE.en.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#AppDir}\installation.json"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\PrépaPilot"; Filename: "{app}\PrepaPilot.exe"; WorkingDir: "{app}"; AppUserModelID: "PrepaPilot.Desktop"
Name: "{autodesktop}\PrépaPilot"; Filename: "{app}\PrepaPilot.exe"; WorkingDir: "{app}"; Tasks: desktopicon; AppUserModelID: "PrepaPilot.Desktop"

[Run]
Filename: "{app}\PrepaPilot.exe"; WorkingDir: "{app}"; Description: "{cm:LaunchPrepaPilot}"; Flags: nowait postinstall skipifsilent

; No [UninstallDelete]: school data in %LOCALAPPDATA%\PrepaPilot and any
; user-created files are deliberately preserved by the normal uninstaller.
