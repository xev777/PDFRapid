; SPDX-License-Identifier: AGPL-3.0-or-later
; Copyright (C) 2026 Fernando Erazo
; Instalador de PDFRapid (Inno Setup 6). Antes: compilar con PyInstaller (packaging\build.ps1).
#define AppName "PDFRapid"
#define AppVersion "1.0.0"
#define AppExe "PDFRapid.exe"

[Setup]
AppId={{7BFEBC81-901C-44A0-AFE4-5A902D90B808}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Fernando Erazo
AppCopyright=Copyright (C) 2026 Fernando Erazo
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\build\installer
OutputBaseFilename=PDFRapid-{#AppVersion}-setup
SetupIconFile=pdfrapid.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ChangesAssociations=yes
WizardStyle=modern

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"; InfoBeforeFile: "aviso_es.txt"
Name: "en"; MessagesFile: "compiler:Default.isl"; InfoBeforeFile: "aviso_en.txt"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "assocpdf"; Description: "{cm:AssocPdf}"; GroupDescription: "{cm:AdditionalIcons}"

[CustomMessages]
es.AssocPdf=Abrir archivos .pdf con PDFRapid
en.AssocPdf=Open .pdf files with PDFRapid

[Files]
Source: "..\build\dist\PDFRapid\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

Source: "..\docs\legal\*"; DestDir: "{app}\legal"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "THIRD_PARTY_NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Asociación .pdf (se registra como opción en «Abrir con»; Windows pide confirmar el predeterminado)
Root: HKA; Subkey: "Software\Classes\PDFRapid.Document"; ValueType: string; ValueName: ""; ValueData: "PDF"; Flags: uninsdeletekey; Tasks: assocpdf
Root: HKA; Subkey: "Software\Classes\PDFRapid.Document\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"; Tasks: assocpdf
Root: HKA; Subkey: "Software\Classes\PDFRapid.Document\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: assocpdf
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "PDFRapid.Document"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocpdf
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""; Flags: uninsdeletekey; Tasks: assocpdf

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
