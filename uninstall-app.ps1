#Requires -Version 5.1
<#
.SYNOPSIS
    Desinstala o STZ XML Translator e opcionalmente remove o certificado.
.NOTES
    Execute com duplo-clique ou: powershell -ExecutionPolicy Bypass -File uninstall-app.ps1
#>

Set-StrictMode -Version Latest

# ── Auto-elevação ────────────────────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
               [Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Start-Process powershell -Verb RunAs -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

$AppIdPrefix   = 'STZXMLTranslator'
$CertSubject   = 'CN=STZ Labs'

Write-Host "`n========================================"   -ForegroundColor White
Write-Host " Desinstalador STZ XML Translator"           -ForegroundColor White
Write-Host "========================================`n"  -ForegroundColor White

# ── Localizar e remover pacote ──────────────────────────────
Write-Host "==> Procurando pacote instalado..." -ForegroundColor Cyan

$package = Get-AppxPackage -AllUsers | Where-Object { $_.Name -like "*$AppIdPrefix*" } | Select-Object -First 1

if (-not $package) {
    Write-Host "    Nenhum pacote encontrado com ID '$AppIdPrefix'." -ForegroundColor Yellow
    Write-Host "    O app pode já ter sido desinstalado."
} else {
    Write-Host "    Encontrado: $($package.PackageFullName)" -ForegroundColor Green
    Write-Host "    Removendo..."
    try {
        Remove-AppxPackage -Package $package.PackageFullName -AllUsers
        Write-Host "    OK: Pacote removido." -ForegroundColor Green
    } catch {
        Write-Host "ERRO ao remover pacote: $_" -ForegroundColor Red
    }
}

# ── Remover certificado (opcional) ──────────────────────────
Write-Host "`n==> Verificando certificado em Trusted Root..." -ForegroundColor Cyan

$certs = Get-ChildItem Cert:\LocalMachine\Root |
         Where-Object { $_.Subject -eq $CertSubject }

if (-not $certs) {
    Write-Host "    Nenhum certificado '$CertSubject' encontrado." -ForegroundColor Yellow
} else {
    foreach ($c in $certs) {
        Write-Host "    Certificado: $($c.Thumbprint) — $($c.Subject)"
    }
    $resp = Read-Host "`n    Remover o(s) certificado(s) do Trusted Root? [s/N]"
    if ($resp -match '^[sS]$') {
        foreach ($c in $certs) {
            try {
                $store = New-Object System.Security.Cryptography.X509Certificates.X509Store(
                    [System.Security.Cryptography.X509Certificates.StoreName]::Root,
                    [System.Security.Cryptography.X509Certificates.StoreLocation]::LocalMachine)
                $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
                $store.Remove($c)
                $store.Close()
                Write-Host "    OK: Certificado $($c.Thumbprint) removido." -ForegroundColor Green
            } catch {
                Write-Host "ERRO ao remover certificado: $_" -ForegroundColor Red
            }
        }
    } else {
        Write-Host "    Certificado mantido." -ForegroundColor Yellow
    }
}

Write-Host "`n========================================"  -ForegroundColor Green
Write-Host " Desinstalação concluída."                  -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Green
Read-Host "Pressione Enter para fechar"
