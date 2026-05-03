param(
    [switch]$DryRun,
    [switch]$SeparateWindows,
    [switch]$SingleTerminal,
    [switch]$NoBrowser,
    [int]$FrontendPort = 5173
)

# Same layout as start-dev.ps1: phone uses ngrok HTTPS -> local Vite (HTTP). Do not set VITE_DEV_HTTPS here.
$repoRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$frontendDir = Join-Path $repoRoot "frontend"
$backendScript = Join-Path $repoRoot "backend\start_server.py"
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$keysEnvFile = Join-Path $repoRoot "keys.env"
$defaultComSpec = Join-Path $env:SystemRoot "System32\cmd.exe"

function Wait-ForTcpPort {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutSeconds = 25
    )

    $hostCandidates = @($HostName, "127.0.0.1", "::1") | Select-Object -Unique

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        foreach ($hostCandidate in $hostCandidates) {
            $client = $null
            try {
                $client = [System.Net.Sockets.TcpClient]::new()
                $connectTask = $client.ConnectAsync($hostCandidate, $Port)
                if ($connectTask.Wait(500) -and $client.Connected) {
                    return $true
                }
            }
            catch {
                # Ignore and retry until timeout.
            }
            finally {
                if ($null -ne $client) {
                    $client.Dispose()
                }
            }
        }

        Start-Sleep -Milliseconds 500
    }

    return $false
}

function Get-NgrokHttpsUrl {
    param(
        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 2 -ErrorAction Stop
            if ($null -ne $response.tunnels) {
                $httpsTunnel = $response.tunnels | Where-Object { $_.public_url -match '^https://' } | Select-Object -First 1
                if ($httpsTunnel -and $httpsTunnel.public_url) {
                    return $httpsTunnel.public_url
                }
            }
        }
        catch {
            # Agent not ready yet — keep polling until deadline.
        }
        Start-Sleep -Milliseconds 500
    }
    return $null
}

function Get-GeminiApiKeyFromEnvFile {
    param(
        [string]$FilePath
    )

    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
        return $null
    }

    foreach ($rawLine in Get-Content -LiteralPath $FilePath) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            continue
        }

        $candidateValue = $line
        if ($line.StartsWith("GEMINI_API_KEY=")) {
            $candidateValue = $line.Substring("GEMINI_API_KEY=".Length).Trim()
        }

        if ($candidateValue.StartsWith('"') -and $candidateValue.EndsWith('"') -and $candidateValue.Length -ge 2) {
            $candidateValue = $candidateValue.Substring(1, $candidateValue.Length - 2)
        } elseif ($candidateValue.StartsWith("'") -and $candidateValue.EndsWith("'") -and $candidateValue.Length -ge 2) {
            $candidateValue = $candidateValue.Substring(1, $candidateValue.Length - 2)
        }

        if ($candidateValue) {
            return $candidateValue
        }
    }

    return $null
}

if (-not (Test-Path -LiteralPath $frontendDir -PathType Container)) {
    throw "Frontend directory not found: $frontendDir"
}

if (-not (Test-Path -LiteralPath $backendScript -PathType Leaf)) {
    throw "Backend entrypoint not found: $backendScript"
}

if ((-not $env:ComSpec) -or (-not (Test-Path -LiteralPath $env:ComSpec -PathType Leaf))) {
    if (Test-Path -LiteralPath $defaultComSpec -PathType Leaf) {
        $env:ComSpec = $defaultComSpec
    }
}

if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    $pythonExecutable = $venvPython
} else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) {
        throw "Python was not found. Create .venv or add python to PATH."
    }
    $pythonExecutable = $pythonCommand.Source
}

$ngrokCmd = Get-Command ngrok -ErrorAction SilentlyContinue
if ($null -eq $ngrokCmd) {
    throw "ngrok was not found in PATH. Install from https://ngrok.com/download and run: ngrok config add-authtoken <your-token>"
}

$geminiKeySource = "environment"
if (-not $env:GEMINI_API_KEY) {
    $fileApiKey = Get-GeminiApiKeyFromEnvFile -FilePath $keysEnvFile
    if ($fileApiKey) {
        $env:GEMINI_API_KEY = $fileApiKey
        $geminiKeySource = "keys.env"
    } else {
        $geminiKeySource = "not-found"
    }
}

$backendCommand = "& { Set-Location -LiteralPath '$repoRoot'; & '$pythonExecutable' '$backendScript' }"
$viteTail = if ($NoBrowser) { "npx vite" } else { "npx vite --open" }
$viteEnvLine = "`$env:VITE_DISABLE_HMR='true'"
$frontendViteCommand = "$viteEnvLine; $viteTail"
$frontendCommand = "& { Set-Location -LiteralPath '$frontendDir'; if (-not `$env:ComSpec) { `$env:ComSpec = '$defaultComSpec' }; $frontendViteCommand }"

if ($SingleTerminal -and $SeparateWindows) {
    throw "Use either -SingleTerminal or -SeparateWindows, not both."
}

# Default to separate windows so backend + frontend are visibly running. Single-terminal mode
# hides them as background jobs in the calling terminal — if that terminal dies, ngrok 502s
# silently because Vite/Flask are gone with no visible failure.
$useSingleTerminal = $SingleTerminal.IsPresent

$shellCommand = Get-Command powershell -ErrorAction SilentlyContinue
if ($null -eq $shellCommand) {
    $shellCommand = Get-Command pwsh -ErrorAction SilentlyContinue
}

if ($null -eq $shellCommand) {
    throw "No PowerShell executable found for launching separate windows."
}

$shellExecutable = $shellCommand.Source

$ngrokWindowCommand = "ngrok http $FrontendPort"

if ($DryRun) {
    Write-Host "Mode: start-dev-ngrok (Vite HTTP + ngrok HTTPS for phone)"
    Write-Host "Mode: $(if ($useSingleTerminal) { 'SingleTerminal' } else { 'SeparateWindows' })"
    Write-Host "Shell executable: $shellExecutable"
    Write-Host "GEMINI_API_KEY source: $geminiKeySource"
    Write-Host "Frontend port: $FrontendPort (ngrok forwards here)"
    Write-Host "VITE_DISABLE_HMR: true"
    Write-Host "VITE_DEV_HTTPS: not set (ngrok provides HTTPS to the phone)"
    Write-Host "Auto-open browser: $(if ($NoBrowser) { 'Disabled' } else { 'Enabled' })"
    Write-Host "Backend command: $backendCommand"
    Write-Host "Frontend command: $frontendCommand"
    Write-Host "Ngrok window command: $ngrokWindowCommand"
    Write-Host "Startup order: ngrok window -> wait for ngrok HTTPS on :4040 -> start backend + frontend (browser opens after ngrok is ready)."
    exit 0
}

if ($geminiKeySource -eq "not-found") {
    Write-Host "Warning: GEMINI_API_KEY not found in environment or keys.env."
}

function Start-NgrokWindow {
    param(
        [string]$ShellExe,
        [string]$WorkingDirectory,
        [string]$NgrokCommand
    )

    Start-Process -FilePath $ShellExe -WorkingDirectory $WorkingDirectory -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        $NgrokCommand
    ) -WindowStyle Normal | Out-Null
}

# ngrok always runs in its own window: it expects a TTY for its dashboard, and stdout-buffered jobs
# silently swallow agent errors (auth, rate-limit) and make troubleshooting impossible.
Start-NgrokWindow -ShellExe $shellExecutable -WorkingDirectory $repoRoot -NgrokCommand $ngrokWindowCommand
Write-Host "Started ngrok in a new window. Waiting for HTTPS tunnel on agent (127.0.0.1:4040)..."

$ngrokHttpsUrl = Get-NgrokHttpsUrl -TimeoutSeconds 30
if ($ngrokHttpsUrl) {
    Write-Host ""
    Write-Host "  ngrok HTTPS tunnel: $ngrokHttpsUrl" -ForegroundColor Green
    Write-Host "  Pairing QR will auto-pick this URL from the ngrok agent. No .env.local edit required."
    Write-Host ""
} else {
    Write-Host "Warning: ngrok did not expose an HTTPS tunnel within 30s." -ForegroundColor Yellow
    Write-Host "  Common causes: missing authtoken (run 'ngrok config add-authtoken <token>'), free-tier session limit, or firewall."
    Write-Host "  The pairing QR will fall back to a LAN IP and likely fail on eduroam. Check the ngrok window for errors."
}

if (-not $useSingleTerminal) {
    $backendProcess = Start-Process -FilePath $shellExecutable -WorkingDirectory $repoRoot -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        $backendCommand
    ) -WindowStyle Normal -PassThru

    $frontendProcess = Start-Process -FilePath $shellExecutable -WorkingDirectory $frontendDir -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        $frontendCommand
    ) -WindowStyle Normal -PassThru

    Write-Host "Started backend and frontend in separate PowerShell windows."
    Write-Host "Backend PID: $($backendProcess.Id)"
    Write-Host "Frontend PID: $($frontendProcess.Id)"
    Write-Host "On ngrok free, the phone browser may show an interstitial once: tap Visit Site."
    exit 0
}

