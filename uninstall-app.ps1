#Requires -Version 5.1
<#
.SYNOPSIS
    Uninstalls STZ XML Translator and can optionally remove its certificate.
.NOTES
    Run it by double-clicking or with: powershell -ExecutionPolicy Bypass -File uninstall-app.ps1
#>

Set-StrictMode -Version Latest

# ── Request administrator permissions ───────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
               [Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Start-Process powershell -Verb RunAs -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

$AppIdPrefix   = 'STZXMLTranslator'
$CertSubject   = 'CN=STZ Labs'

Write-Host "`n========================================"   -ForegroundColor White
Write-Host " STZ XML Translator Uninstaller"             -ForegroundColor White
Write-Host "========================================`n"  -ForegroundColor White

# ── Find and remove package ─────────────────────────────────
Write-Host "==> Looking for installed package..." -ForegroundColor Cyan

$package = Get-AppxPackage -AllUsers | Where-Object { $_.Name -like "*$AppIdPrefix*" } | Select-Object -First 1

if (-not $package) {
    Write-Host "    No package found with ID '$AppIdPrefix'." -ForegroundColor Yellow
    Write-Host "    The app may already be uninstalled."
} else {
    Write-Host "    Found: $($package.PackageFullName)" -ForegroundColor Green
    Write-Host "    Removing..."
    try {
        Remove-AppxPackage -Package $package.PackageFullName -AllUsers
        Write-Host "    OK: Package removed." -ForegroundColor Green
    } catch {
        Write-Host "ERROR while removing package: $_" -ForegroundColor Red
    }
}

# ── Remove certificate (optional) ───────────────────────────
Write-Host "`n==> Checking certificate in Trusted Root..." -ForegroundColor Cyan

$certs = Get-ChildItem Cert:\LocalMachine\Root |
         Where-Object { $_.Subject -eq $CertSubject }

if (-not $certs) {
    Write-Host "    No '$CertSubject' certificate was found." -ForegroundColor Yellow
} else {
    foreach ($c in $certs) {
        Write-Host "    Certificate: $($c.Thumbprint) - $($c.Subject)"
    }
    $resp = Read-Host "`n    Remove certificate(s) from Trusted Root? [y/N]"
    if ($resp -match '^[yYsS]$') {
        foreach ($c in $certs) {
            try {
                $store = New-Object System.Security.Cryptography.X509Certificates.X509Store(
                    [System.Security.Cryptography.X509Certificates.StoreName]::Root,
                    [System.Security.Cryptography.X509Certificates.StoreLocation]::LocalMachine)
                $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
                $store.Remove($c)
                $store.Close()
                Write-Host "    OK: Certificate $($c.Thumbprint) removed." -ForegroundColor Green
            } catch {
                Write-Host "ERROR while removing certificate: $_" -ForegroundColor Red
            }
        }
    } else {
        Write-Host "    Certificate kept." -ForegroundColor Yellow
    }
}

Write-Host "`n========================================"  -ForegroundColor Green
Write-Host " Uninstall complete."                       -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Green
Read-Host "Press Enter to close"
