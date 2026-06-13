#Requires -Version 5.1
<#
.SYNOPSIS
    Empacota o STZ XML Translator como MSIX auto-assinado.
.DESCRIPTION
    1. Gera ou reutiliza certificado auto-assinado no store do usuário
    2. Exporta .cer (distribuição) e .pfx (assinatura)
    3. Gera assets de ícone nos tamanhos exigidos pelo MSIX
    4. Preenche o AppxManifest.xml com as configs abaixo
    5. Monta a pasta de staging com o output do Nuitka
    6. Roda makeappx.exe pack → .msix
    7. Roda signtool.exe sign → .msix assinado
    8. Copia .msix + .cer para ./release/
.NOTES
    Requer Windows SDK instalado (makeappx.exe / signtool.exe).
    Requer Python + Pillow no ambiente virtual (para gerar ícones).
#>

param(
    [string]$Version      = '1.0.0.0',   # 4 partes obrigatório: X.Y.Z.W
    [string]$CertPath     = '',           # CI: caminho para .pfx existente
    [string]$CertPassword = ''            # CI: senha do .pfx fornecido
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ============================================================
# CONFIGURAÇÃO — edite aqui para um novo release
# ============================================================
$AppName             = 'STZ XML Translator'
$AppId               = 'STZXMLTranslator'          # sem espaços, só letras/dígitos
# $Version vem do param() acima
$PublisherDisplayName = 'STZ Labs'
$PublisherCN         = "CN=$PublisherDisplayName"  # deve bater exatamente com o cert
$Description         = 'XML localization tool for game modders'
$ExecutableName      = 'STZXMLTranslator.exe'
$NuitkaDistFolder    = "dist\main_qt.dist"          # output do Nuitka --standalone
$PfxPasswordPlain    = 'STZBuild_msix'             # senha do .pfx (só usada em build)
$CertFriendlyName    = "$AppName Self-Signed"
# ============================================================

$ProjectRoot  = $PSScriptRoot
$StagingDir   = Join-Path $ProjectRoot 'msix-staging'
$ReleaseDir   = Join-Path $ProjectRoot 'release'
$MsixTemplate = Join-Path $ProjectRoot 'msix\AppxManifest.xml'
$MsixAssets   = Join-Path $ProjectRoot 'msix\assets'
$SourceIcon   = Join-Path $ProjectRoot 'assets\stz-xml.png'
$MsixOut      = Join-Path $ReleaseDir  "$AppId-$Version.msix"
$CerOut       = Join-Path $ReleaseDir  "$AppId.cer"
$PfxOut       = Join-Path $ProjectRoot 'msix-signing.pfx'  # fora de /release — não distribuir
$SigningPfx   = $PfxOut

# ── Funções auxiliares ──────────────────────────────────────

function Find-SdkTool {
    param([string]$ToolName)
    $sdkRoot = 'C:\Program Files (x86)\Windows Kits\10\bin'
    if (-not (Test-Path $sdkRoot)) {
        throw "Windows SDK não encontrado em '$sdkRoot'.`nInstale o Windows SDK: https://developer.microsoft.com/windows/downloads/windows-sdk/"
    }
    # Pega a versão mais recente do SDK instalada
    $tool = Get-ChildItem -Path $sdkRoot -Recurse -Filter $ToolName -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -like '*\x64\*' } |
            Sort-Object { [version]($_.FullName -replace '.*\\(\d+\.\d+\.\d+\.\d+)\\.*','$1') } -Descending |
            Select-Object -First 1
    if (-not $tool) {
        throw "'$ToolName' não encontrado no Windows SDK.`nVerifique se o SDK está instalado com suporte a ferramentas de empacotamento."
    }
    return $tool.FullName
}

function Write-Step {
    param([string]$Msg)
    Write-Host "`n==> $Msg" -ForegroundColor Cyan
}

function Write-OK {
    param([string]$Msg)
    Write-Host "    OK: $Msg" -ForegroundColor Green
}

# ── Início ──────────────────────────────────────────────────

Write-Host "`n========================================"  -ForegroundColor White
Write-Host " MSIX Build — $AppName v$Version"           -ForegroundColor White
Write-Host "========================================`n" -ForegroundColor White

# ── 1. Localizar ferramentas do SDK ─────────────────────────
Write-Step "Localizando ferramentas do Windows SDK..."
$MakeAppx = Find-SdkTool 'makeappx.exe'
$SignTool  = Find-SdkTool 'signtool.exe'
Write-OK "makeappx : $MakeAppx"
Write-OK "signtool : $SignTool"

# ── 2. Certificado auto-assinado (idempotente) ──────────────
Write-Step "Verificando certificado de assinatura..."

if ($CertPath -ne '') {
    # CI mode: carrega .pfx existente em vez de gerar um novo certificado
    Write-Host "    Carregando certificado de: $CertPath" -ForegroundColor Yellow
    if ([string]::IsNullOrWhiteSpace($CertPassword)) {
        throw "CertPassword é obrigatório quando CertPath é informado."
    }
    $pfxBytes    = [System.IO.File]::ReadAllBytes($CertPath)
    $cert        = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new(
                       $pfxBytes, $CertPassword,
                       [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::Exportable)
    $PfxPasswordPlain = $CertPassword
    $SigningPfx = (Resolve-Path $CertPath).Path
    Write-OK "Certificado carregado: $($cert.Thumbprint)"
} else {
    # Modo local: gera ou reutiliza certificado auto-assinado no store do usuário
    $cert = Get-ChildItem Cert:\CurrentUser\My -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Subject -eq $PublisherCN -and
                ($_.EnhancedKeyUsageList | Where-Object { $_.ObjectId -eq '1.3.6.1.5.5.7.3.3' })
            } | Select-Object -First 1

    if ($cert) {
        Write-OK "Certificado existente reutilizado: $($cert.Thumbprint)"
    } else {
        Write-Host "    Gerando novo certificado auto-assinado..." -ForegroundColor Yellow
        $cert = New-SelfSignedCertificate `
            -Subject          $PublisherCN `
            -CertStoreLocation 'Cert:\CurrentUser\My' `
            -Type             CodeSigning `
            -KeyUsage         DigitalSignature `
            -FriendlyName     $CertFriendlyName `
            -NotAfter         (Get-Date).AddYears(5)
        Write-OK "Certificado criado: $($cert.Thumbprint)"
    }
}

# ── 3. Exportar .cer (chave pública — para distribuição) ────
Write-Step "Exportando certificado público (.cer)..."
if (-not (Test-Path $ReleaseDir)) { New-Item -ItemType Directory $ReleaseDir | Out-Null }
Export-Certificate -Cert $cert -FilePath $CerOut -Type CERT | Out-Null
Write-OK $CerOut

# ── 4. Exportar .pfx (chave privada — somente para build) ───
if ($CertPath -ne '') {
    Write-Step "Usando chave de assinatura fornecida (.pfx)..."
    Write-OK "$SigningPfx  [fornecido pelo CI]"
} else {
    Write-Step "Exportando chave de assinatura (.pfx)..."
    $PfxPassword = ConvertTo-SecureString -String $PfxPasswordPlain -Force -AsPlainText
    Export-PfxCertificate -Cert $cert -FilePath $PfxOut -Password $PfxPassword | Out-Null
    Write-OK "$PfxOut  [NÃO distribua este arquivo]"
}

# ── 5. Gerar assets de ícone (via Python + Pillow) ──────────
Write-Step "Gerando assets de ícone para MSIX..."
if (-not (Test-Path $SourceIcon)) {
    throw "Ícone fonte não encontrado: $SourceIcon`nAdicione 'assets\stz-xml.png' ao projeto."
}
if (-not (Test-Path $MsixAssets)) { New-Item -ItemType Directory $MsixAssets | Out-Null }

$pythonScript = @"
from PIL import Image
import os
src = Image.open(r'$($SourceIcon.Replace('\','\\'))').convert('RGBA')
specs = [(44,'Square44x44Logo'),(150,'Square150x150Logo'),(50,'StoreLogo')]
for size, name in specs:
    img = src.resize((size,size), Image.LANCZOS)
    img.save(os.path.join(r'$($MsixAssets.Replace('\','\\'))', name + '.png'))
print('Assets gerados com sucesso.')
"@

# Ativa o venv se disponível
$venvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$pythonExe  = if (Test-Path $venvPython) { $venvPython } else { 'python' }
& $pythonExe -c $pythonScript
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar assets. Verifique se Pillow está instalado." }
Write-OK "Square44x44Logo.png, Square150x150Logo.png, StoreLogo.png"

# ── 6. Preencher AppxManifest.xml ───────────────────────────
Write-Step "Preenchendo AppxManifest.xml..."
$manifest = Get-Content $MsixTemplate -Raw -Encoding UTF8
$manifest = $manifest `
    -replace '\{\{AppId\}\}',               $AppId `
    -replace '\{\{Version\}\}',             $Version `
    -replace '\{\{PublisherCN\}\}',         $PublisherCN `
    -replace '\{\{PublisherDisplayName\}\}',$PublisherDisplayName `
    -replace '\{\{AppName\}\}',             $AppName `
    -replace '\{\{Description\}\}',         $Description `
    -replace '\{\{ExecutableName\}\}',      $ExecutableName
Write-OK "Manifest preenchido."

# ── 7. Montar pasta de staging ──────────────────────────────
Write-Step "Montando pasta de staging..."
$NuitkaFullPath = Join-Path $ProjectRoot $NuitkaDistFolder
if (-not (Test-Path $NuitkaFullPath)) {
    throw "Output do Nuitka não encontrado: $NuitkaFullPath`nRode build_nuitka.bat com BUILD_MODE=standalone primeiro."
}
if (Test-Path $StagingDir) { Remove-Item $StagingDir -Recurse -Force }
New-Item -ItemType Directory $StagingDir | Out-Null

# Copia todos os arquivos do Nuitka para a raiz do staging
Copy-Item -Path "$NuitkaFullPath\*" -Destination $StagingDir -Recurse

# Garante que subpasta assets existe no staging e copia ícones MSIX
$stagingAssets = Join-Path $StagingDir 'assets'
if (-not (Test-Path $stagingAssets)) { New-Item -ItemType Directory $stagingAssets | Out-Null }
Copy-Item "$MsixAssets\*" $stagingAssets

# Salva manifest preenchido no staging
$manifest | Set-Content (Join-Path $StagingDir 'AppxManifest.xml') -Encoding UTF8

Write-OK "Staging: $StagingDir"
Write-OK "Arquivos: $((Get-ChildItem $StagingDir -Recurse -File).Count) itens"

# ── 8. makeappx pack ────────────────────────────────────────
Write-Step "Empacotando com makeappx..."
if (Test-Path $MsixOut) { Remove-Item $MsixOut -Force }
& $MakeAppx pack /d $StagingDir /p $MsixOut /nv /o
if ($LASTEXITCODE -ne 0) { throw "makeappx falhou (exit $LASTEXITCODE)." }
Write-OK $MsixOut

# ── 9. signtool sign ────────────────────────────────────────
Write-Step "Assinando MSIX com signtool..."
& $SignTool sign /fd SHA256 /a /f $SigningPfx /p $PfxPasswordPlain $MsixOut
if ($LASTEXITCODE -ne 0) { throw "signtool falhou (exit $LASTEXITCODE)." }
Write-OK "MSIX assinado com SHA256."

# ── 10. Copiar install-app.ps1 para release\ ────────────────
Write-Step "Copiando install-app.ps1 para release\..."
$InstallScript = Join-Path $ProjectRoot 'install-app.ps1'
if (Test-Path $InstallScript) {
    Copy-Item $InstallScript (Join-Path $ReleaseDir 'install-app.ps1') -Force
    Write-OK (Join-Path $ReleaseDir 'install-app.ps1')
} else {
    Write-Host "    Aviso: install-app.ps1 não encontrado na raiz do projeto." -ForegroundColor Yellow
}

# ── 11. Limpeza ─────────────────────────────────────────────
Write-Step "Limpando staging e .pfx temporário..."
Remove-Item $StagingDir -Recurse -Force
if (($CertPath -eq '') -and (Test-Path $PfxOut)) {
    Remove-Item $PfxOut -Force
}
Write-OK "Limpo."

# ── Resumo ──────────────────────────────────────────────────
$InstallOut = Join-Path $ReleaseDir 'install-app.ps1'
Write-Host "`n========================================"  -ForegroundColor Green
Write-Host " Build MSIX concluído com sucesso!"         -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Green
Write-Host "  MSIX    : $MsixOut"
Write-Host "  Cert    : $CerOut"
Write-Host "  Install : $InstallOut"
Write-Host "`n  Para instalar: execute install-app.ps1 na pasta release\"
Write-Host "  Ou copie toda a pasta release\ para o usuario.`n"
