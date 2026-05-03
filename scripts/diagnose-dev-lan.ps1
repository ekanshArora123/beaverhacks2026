# Quick checks for phone / laptop dev pairing (no elevation required).
# Run from repo root:
#   powershell -ExecutionPolicy Bypass -File .\scripts\diagnose-dev-lan.ps1

Write-Host "=== WiFi profile (Public means older firewall rules often did not apply) ==="
try {
    $profiles = @(Get-NetConnectionProfile | Select-Object Name, InterfaceAlias, NetworkCategory)
    $profiles | Format-Table -AutoSize
    foreach ($p in $profiles) {
        $label = "$($p.InterfaceAlias) $($p.Name)"
        if ($label -match 'eduroam|Eduroam|University|Campus|Guest') {
            Write-Host ""
            Write-Host "WARNING: Many campus / guest networks block phone-to-laptop traffic (client isolation)." -ForegroundColor Yellow
            Write-Host "         Firewall rules cannot fix that. Use phone mobile hotspot, home WiFi, USB tethering, or ngrok." -ForegroundColor Yellow
            break
        }
    }
} catch {
    Write-Host "Could not read profiles: $_"
}

Write-Host ""
Write-Host "=== Listening on 5173 (Vite) and 5000 (Flask) ==="
try {
    Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -eq 5173 -or $_.LocalPort -eq 5000 } |
        Select-Object LocalAddress, LocalPort, OwningProcess |
        Sort-Object LocalPort |
        Format-Table -AutoSize
} catch {
    Write-Host "Could not query TCP listeners: $_"
}

Write-Host ""
Write-Host "=== GET http://127.0.0.1:5000/host-info (needs Flask running) ==="
try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:5000/host-info" -TimeoutSec 5
    Write-Host ($r | ConvertTo-Json -Compress)
} catch {
    Write-Host "FAILED: $_"
    Write-Host "Start the backend (python backend/start_server.py) so pairing can pick a LAN IP."
}

Write-Host ""
Write-Host "Default dev is HTTP — PC webcam uses http://localhost:5173."
Write-Host "For Android camera on LAN use: npm run dev:https then https://YOUR_LAN_IP:5173/mobile?code=..."
Write-Host "If NetworkCategory is Public, run scripts\allow-dev-ports-firewall.ps1 again as Administrator."
