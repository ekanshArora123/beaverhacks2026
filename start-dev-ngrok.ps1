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

$useSingleTerminal = $SingleTerminal

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
    Write-Host "After ngrok shows an HTTPS URL, set frontend/.env.local: VITE_PAIRING_ORIGIN=<that-url> and restart Vite for tunnel QR (see frontend/.env.example)."
    Write-Host "Ngrok window command: $ngrokWindowCommand"
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
    Write-Host "Waiting for Vite on 127.0.0.1:$FrontendPort (up to 120s), then starting ngrok ..."

    if (-not (Wait-ForTcpPort -HostName "127.0.0.1" -Port $FrontendPort -TimeoutSeconds 120)) {
        Write-Host "Warning: Vite did not accept connections in time. Starting ngrok anyway - fix Vite, then restart ngrok from its window if needed."
    }

    Start-NgrokWindow -ShellExe $shellExecutable -WorkingDirectory $repoRoot -NgrokCommand $ngrokWindowCommand

    Write-Host "Started ngrok in a new window."
    Write-Host "Copy the HTTPS Forwarding URL into frontend/.env.local as VITE_PAIRING_ORIGIN=... then restart the frontend window (or run npm run dev in frontend) so the pairing QR uses the tunnel."
    Write-Host "On ngrok free, the phone browser may show an interstitial once: tap Visit Site. Vite allows common tunnel hostnames; see frontend/.env.example if you still see Blocked request."
    Write-Host "Pairing QR auto-picks ngrok HTTPS from the ngrok agent (localhost:4040) when ngrok runs; frontend/.env.local VITE_PAIRING_ORIGIN overrides if needed."
    exit 0
}

$ngrokLauncher = Start-Job -Name "beaverhacks-ngrok-launcher" -ScriptBlock {
    param($port, $shellExe, $workDir, $ngrokLine)
    $deadline = (Get-Date).AddSeconds(120)
    $ready = $false
    while ((Get-Date) -lt $deadline -and -not $ready) {
        $client = $null
        try {
            $client = [System.Net.Sockets.TcpClient]::new()
            $task = $client.ConnectAsync("127.0.0.1", $port)
            if ($task.Wait(500) -and $client.Connected) {
                $ready = $true
            }
        }
        catch {
            # Retry until deadline.
        }
        finally {
            if ($null -ne $client) {
                $client.Dispose()
            }
        }
        if (-not $ready) {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $ready) {
        Write-Output "Ngrok launcher: port $port not ready in time; start ngrok manually: $ngrokLine"
    }
    Start-Process -FilePath $shellExe -WorkingDirectory $workDir -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        $ngrokLine
    ) -WindowStyle Normal | Out-Null
} -ArgumentList $FrontendPort, $shellExecutable, $repoRoot, $ngrokWindowCommand

$backendJob = Start-Job -Name "beaverhacks-backend" -ScriptBlock {
    param($workingDirectory, $pythonPath, $scriptPath)
    Set-Location -LiteralPath $workingDirectory
    & $pythonPath $scriptPath
} -ArgumentList $repoRoot, $pythonExecutable, $backendScript

Write-Host ('Backend started in background job {0}.' -f $backendJob.Id)
Write-Host "Ngrok will open in another window once Vite is listening on port $FrontendPort."
Write-Host 'Frontend is starting in this terminal; press Ctrl+C to stop the backend job.'
Write-Host 'Pairing QR auto-reads HTTPS from ngrok (localhost:4040). To force one URL use VITE_PAIRING_ORIGIN in frontend/.env.local and restart Vite.'

try {
    Set-Location -LiteralPath $frontendDir
    if (-not $env:ComSpec) {
        $env:ComSpec = $defaultComSpec
    }
    $env:VITE_DISABLE_HMR = 'true'
    if ($NoBrowser) {
        npx vite
    }
    else {
        npx vite --open
    }
}
finally {
    if ($null -ne $backendJob) {
        Stop-Job -Job $backendJob -ErrorAction SilentlyContinue | Out-Null
        Remove-Job -Job $backendJob -Force -ErrorAction SilentlyContinue | Out-Null
    }
    if ($null -ne $ngrokLauncher) {
        Stop-Job -Job $ngrokLauncher -ErrorAction SilentlyContinue | Out-Null
        Remove-Job -Job $ngrokLauncher -Force -ErrorAction SilentlyContinue | Out-Null
    }
}