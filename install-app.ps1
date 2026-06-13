#Requires -Version 5.1
<#
.SYNOPSIS
    Installs STZ XML Translator from a self-signed MSIX package.
.DESCRIPTION
    1. Requests administrator permissions when needed
    2. Installs the .cer certificate into Trusted Root (LocalMachine)
    3. Installs the .msix package with Add-AppxPackage
.NOTES
    Keep this script in the same folder as the .msix and .cer files.
    Run it by double-clicking or with: powershell -ExecutionPolicy Bypass -File install-app.ps1
#>

Set-StrictMode -Version Latest

# ── Request administrator permissions ───────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
               [Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "Requesting administrator permissions..." -ForegroundColor Yellow
    $args = "-ExecutionPolicy Bypass -File `"$PSCommandPath`""
    Start-Process powershell -Verb RunAs -ArgumentList $args
    exit
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "`n========================================"  -ForegroundColor White
Write-Host " STZ XML Translator Installer"              -ForegroundColor White
Write-Host "========================================`n" -ForegroundColor White

# ── Find .cer file ──────────────────────────────────────────
$cerFile = Get-ChildItem -Path $ScriptDir -Filter '*.cer' | Select-Object -First 1
if (-not $cerFile) {
    Write-Host "ERROR: No .cer file was found in '$ScriptDir'." -ForegroundColor Red
    Write-Host "       Make sure the .cer file is in the same folder as this script."
    Read-Host "`nPress Enter to exit"
    exit 1
}

# ── Find .msix file ─────────────────────────────────────────
$msixFile = Get-ChildItem -Path $ScriptDir -Filter '*.msix' | Select-Object -First 1
if (-not $msixFile) {
    Write-Host "ERROR: No .msix file was found in '$ScriptDir'." -ForegroundColor Red
    Write-Host "       Make sure the .msix file is in the same folder as this script."
    Read-Host "`nPress Enter to exit"
    exit 1
}

Write-Host "  Certificate : $($cerFile.Name)"
Write-Host "  Package     : $($msixFile.Name)`n"

# ── Install certificate (idempotent) ────────────────────────
Write-Host "==> Checking certificate in Trusted Root..." -ForegroundColor Cyan

$certObj    = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $cerFile.FullName
$thumbprint = $certObj.Thumbprint

$existing = Get-ChildItem Cert:\LocalMachine\Root |
            Where-Object { $_.Thumbprint -eq $thumbprint } |
            Select-Object -First 1

if ($existing) {
    Write-Host "    OK: Certificate is already installed ($thumbprint)." -ForegroundColor Green
} else {
    Write-Host "    Installing certificate into LocalMachine\Root..." -ForegroundColor Yellow
    try {
        $store = New-Object System.Security.Cryptography.X509Certificates.X509Store(
            [System.Security.Cryptography.X509Certificates.StoreName]::Root,
            [System.Security.Cryptography.X509Certificates.StoreLocation]::LocalMachine)
        $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
        $store.Add($certObj)
        $store.Close()
        Write-Host "    OK: Certificate installed." -ForegroundColor Green
    } catch {
        Write-Host "ERROR while installing certificate: $_" -ForegroundColor Red
        Read-Host "`nPress Enter to exit"
        exit 1
    }
}

# ── Install MSIX package ────────────────────────────────────
Write-Host "`n==> Installing MSIX package..." -ForegroundColor Cyan
try {
    Add-AppxPackage -Path $msixFile.FullName
    Write-Host "    OK: Package installed successfully." -ForegroundColor Green
} catch {
    Write-Host "ERROR while installing package: $_" -ForegroundColor Red
    Write-Host "`nPossible causes:"
    Write-Host "  - An older version is still installed (uninstall it first)"
    Write-Host "  - Windows did not trust the certificate"
    Write-Host "  - The manifest version is lower than the installed version"
    Read-Host "`nPress Enter to exit"
    exit 1
}

Write-Host "`n========================================"  -ForegroundColor Green
Write-Host " Installation complete!"                    -ForegroundColor Green
Write-Host " STZ XML Translator is in the Start Menu."  -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Green
Read-Host "Press Enter to close"
