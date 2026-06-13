; ============================================================
;  STZ XML Translator — Inno Setup Script
;  Requer: build_nuitka.bat com BUILD_MODE=standalone primeiro
;  Saida  : dist\STZXMLTranslator-Setup.exe
; ============================================================

#define AppName    "STZ XML Translator"
#define AppVersion "1.2"
#define AppPublisher "StarzynhoBR"
#define AppExeName "STZXMLTranslator.exe"
#define SourceDir  "dist\main_qt.dist"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://github.com/StarzynhoBR/STZ-XML-Translator
AppSupportURL=https://github.com/StarzynhoBR/STZ-XML-Translator/issues
AppUpdatesURL=https://github.com/StarzynhoBR/STZ-XML-Translator/releases

; Instala por usuario, sem precisar de elevacao UAC
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline dialog

DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

; Icone do installer
SetupIconFile=assets\icon.ico

; Compressao maxima
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; Saida
OutputDir=dist
OutputBaseFilename=STZXMLTranslator-Setup-{#AppVersion}
WizardStyle=modern

; Arquivo de licenca (opcional — descomente se tiver um LICENSE.txt)
; LicenseFile=LICENSE.txt

; Versao do Windows minima: 10
MinVersion=10.0

; Nao cria backup do dir de instalacao
CreateUninstallRegKey=yes
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName} {#AppVersion}

[Languages]
Name: "english";    MessagesFile: "compiler:Default.isl"
Name: "portuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Copia toda a pasta standalone gerada pelo Nuitka
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Atalho no Menu Iniciar
Name: "{group}\{#AppName}";           Filename: "{app}\{#AppExeName}"
; Atalho na area de trabalho (opcional, marcada como desmarcada por padrao)
Name: "{autodesktop}\{#AppName}";     Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; Oferece abrir o app apos instalar
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove arquivos criados pelo app em runtime (config, presets)
Type: files; Name: "{app}\config.json"
Type: files; Name: "{app}\tag_presets.json"
