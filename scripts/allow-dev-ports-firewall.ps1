# Opens inbound TCP 5173 (Vite) and 5000 (Flask).
# Wi‑Fi on Windows is often the "Public" profile — rules limited to Private/Domain do nothing there.
# Run from elevated PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\scripts\allow-dev-ports-firewall.ps1

#Requires -RunAsAdministrator

$ErrorActionPreference = 'Stop'

function Ensure-Rule {
    param(
        [string]$DisplayName,
        [int]$Port
    )
    Remove-NetFirewallRule -DisplayName $DisplayName -ErrorAction SilentlyContinue | Out-Null
    New-NetFirewallRule `
        -DisplayName $DisplayName `
        -Direction Inbound `
        -Protocol TCP `
        -LocalPort $Port `
        -Action Allow `
        -Profile Private, Public, Domain | Out-Null
    Write-Host "Applied: $DisplayName (TCP $Port, profiles Private + Public + Domain)"
}

Ensure-Rule -DisplayName 'BeaverHacks Vite dev (5173)' -Port 5173
Ensure-Rule -DisplayName 'BeaverHacks Flask dev (5000)' -Port 5000
Write-Host ''
Write-Host "Done. If it still fails: run scripts\diagnose-dev-lan.ps1 (no admin), set WiFi to Private in Windows, avoid guest WiFi / AP isolation."
