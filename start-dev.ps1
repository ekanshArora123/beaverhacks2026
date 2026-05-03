param(
    [switch]$DryRun,
    [switch]$SeparateWindows,
    [switch]$SingleTerminal,
    [switch]$NoBrowser,
    [switch]$DevHttps
)

# $PSScriptRoot is reliable when running the .ps1 file; fall back for unusual invocation modes.
$repoRoot = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$frontendDir = Join-Path $repoRoot "frontend"
$backendScript = Join-Path $repoRoot "backend\start_server.py"
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$keysEnvFile = Join-Path $repoRoot "keys.env"
$frontendHost = "localhost"
$frontendPort = 5173
$frontendScheme = if ($DevHttps) { "https" } else { "http" }
$frontendUrl = "${frontendScheme}://${frontendHost}:${frontendPort}"
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

function Open-FrontendBrowser {
    param(
        [string]$Url,
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutSeconds = 25
    )

    if (Wait-ForTcpPort -HostName $HostName -Port $Port -TimeoutSeconds $TimeoutSeconds) {
        Start-Process $Url
        Write-Host "Opened frontend GUI at $Url"
        return $true
    }

    Write-Host "Warning: frontend did not start on $Url within $TimeoutSeconds seconds. Attempting browser open anyway."
    Start-Process $Url
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
if ($DevHttps) {
    $viteEnvLine += "; `$env:VITE_DEV_HTTPS='true'"
}
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

if ($DryRun) {
    Write-Host "Mode: $(if ($useSingleTerminal) { 'SingleTerminal' } else { 'SeparateWindows' })"
    Write-Host "Shell executable: $shellExecutable"
    Write-Host "GEMINI_API_KEY source: $geminiKeySource"
    Write-Host "Frontend URL: $frontendUrl"
    Write-Host "Dev HTTPS (phone camera on LAN): $(if ($DevHttps) { 'yes' } else { 'no - use -DevHttps or npm run dev:https for that' })"
    Write-Host "VITE_DISABLE_HMR: true (better phone / LAN loading)"
    Write-Host "Auto-open browser: $(if ($NoBrowser) { 'Disabled' } else { 'Enabled' })"
    Write-Host "Backend command: $backendCommand"
    Write-Host "Frontend command: $frontendCommand"
    exit 0
}

if ($geminiKeySource -eq "not-found") {
    Write-Host "Warning: GEMINI_API_KEY not found in environment or keys.env."
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
    Write-Host "Phone pairing: VITE_DISABLE_HMR=true. For Android camera/mic over LAN use -DevHttps or npm run dev:https (HTTPS)."
    Write-Host "If the phone still cannot load: scripts\\allow-dev-ports-firewall.ps1 as Administrator once."

    exit 0
}

$backendJob = Start-Job -Name "beaverhacks-backend" -ScriptBlock {
    param($workingDirectory, $pythonPath, $scriptPath)
    Set-Location -LiteralPath $workingDirectory
    & $pythonPath $scriptPath
} -ArgumentList $repoRoot, $pythonExecutable, $backendScript

Write-Host "Backend started in background job $($backendJob.Id)."
Write-Host "Frontend is starting in the current terminal. Press Ctrl+C to stop both."
Write-Host "VITE_DISABLE_HMR=true (phone-friendly). Firewall: scripts\\allow-dev-ports-firewall.ps1 as Admin if needed."

try {
    Set-Location -LiteralPath $frontendDir
    if (-not $env:ComSpec) {
        $env:ComSpec = $defaultComSpec
    }
    $env:VITE_DISABLE_HMR = 'true'
    if ($DevHttps) {
        $env:VITE_DEV_HTTPS = 'true'
    }
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
}
