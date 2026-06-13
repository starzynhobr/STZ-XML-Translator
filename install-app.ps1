#Requires -Version 5.1
<#
.SYNOPSIS
    Instala o STZ XML Translator (MSIX auto-assinado).
.DESCRIPTION
    1. Auto-eleva para Administrador se necessário
    2. Instala o certificado .cer no Trusted Root (LocalMachine)
    3. Instala o pacote .msix com Add-AppxPackage
.NOTES
    Coloque este script na mesma pasta que o .msix e o .cer.
    Execute com duplo-clique ou: powershell -ExecutionPolicy Bypass -File install-app.ps1
#>

Set-StrictMode -Version Latest

# ── Auto-elevação para Administrador ────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
               [Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "Elevando para Administrador..." -ForegroundColor Yellow
    $args = "-ExecutionPolicy Bypass -File `"$PSCommandPath`""
    Start-Process powershell -Verb RunAs -ArgumentList $args
    exit
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "`n========================================"  -ForegroundColor White
Write-Host " Instalador STZ XML Translator"             -ForegroundColor White
Write-Host "========================================`n" -ForegroundColor White

# ── Localizar .cer ──────────────────────────────────────────
$cerFile = Get-ChildItem -Path $ScriptDir -Filter '*.cer' | Select-Object -First 1
if (-not $cerFile) {
    Write-Host "ERRO: Nenhum arquivo .cer encontrado em '$ScriptDir'." -ForegroundColor Red
    Write-Host "      Certifique-se de que o .cer está na mesma pasta que este script."
    Read-Host "`nPressione Enter para sair"
    exit 1
}

# ── Localizar .msix ─────────────────────────────────────────
$msixFile = Get-ChildItem -Path $ScriptDir -Filter '*.msix' | Select-Object -First 1
if (-not $msixFile) {
    Write-Host "ERRO: Nenhum arquivo .msix encontrado em '$ScriptDir'." -ForegroundColor Red
    Write-Host "      Certifique-se de que o .msix está na mesma pasta que este script."
    Read-Host "`nPressione Enter para sair"
    exit 1
}

Write-Host "  Certificado : $($cerFile.Name)"
Write-Host "  Pacote      : $($msixFile.Name)`n"

# ── Instalar certificado (idempotente) ──────────────────────
Write-Host "==> Verificando certificado no Trusted Root..." -ForegroundColor Cyan

$certObj    = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $cerFile.FullName
$thumbprint = $certObj.Thumbprint

$existing = Get-ChildItem Cert:\LocalMachine\Root |
            Where-Object { $_.Thumbprint -eq $thumbprint } |
            Select-Object -First 1

if ($existing) {
    Write-Host "    OK: Certificado já instalado ($thumbprint)." -ForegroundColor Green
} else {
    Write-Host "    Instalando certificado em LocalMachine\Root..." -ForegroundColor Yellow
    try {
        $store = New-Object System.Security.Cryptography.X509Certificates.X509Store(
            [System.Security.Cryptography.X509Certificates.StoreName]::Root,
            [System.Security.Cryptography.X509Certificates.StoreLocation]::LocalMachine)
        $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
        $store.Add($certObj)
        $store.Close()
        Write-Host "    OK: Certificado instalado." -ForegroundColor Green
    } catch {
        Write-Host "ERRO ao instalar certificado: $_" -ForegroundColor Red
        Read-Host "`nPressione Enter para sair"
        exit 1
    }
}

# ── Instalar pacote MSIX ────────────────────────────────────
Write-Host "`n==> Instalando pacote MSIX..." -ForegroundColor Cyan
try {
    Add-AppxPackage -Path $msixFile.FullName
    Write-Host "    OK: Pacote instalado com sucesso." -ForegroundColor Green
} catch {
    Write-Host "ERRO ao instalar pacote: $_" -ForegroundColor Red
    Write-Host "`nPossíveis causas:"
    Write-Host "  - Uma versão mais antiga ainda está instalada (desinstale primeiro)"
    Write-Host "  - O certificado não foi aceito pelo sistema"
    Write-Host "  - A versão no manifesto é menor que a instalada"
    Read-Host "`nPressione Enter para sair"
    exit 1
}

Write-Host "`n========================================"  -ForegroundColor Green
Write-Host " Instalação concluída!"                     -ForegroundColor Green
Write-Host " STZ XML Translator está no Menu Iniciar."  -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Green
Read-Host "Pressione Enter para fechar"
