param(
    [switch]$DryRun
)

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendDir = Join-Path $repoRoot "frontend"
$backendScript = Join-Path $repoRoot "backend\start_server.py"
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $frontendDir -PathType Container)) {
    throw "Frontend directory not found: $frontendDir"
}

if (-not (Test-Path -LiteralPath $backendScript -PathType Leaf)) {
    throw "Backend entrypoint not found: $backendScript"
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

$backendCommand = "& { Set-Location -LiteralPath '$repoRoot'; & '$pythonExecutable' '$backendScript' }"
$frontendCommand = "& { Set-Location -LiteralPath '$frontendDir'; npm run dev }"

if ($DryRun) {
    Write-Host "Backend command: $backendCommand"
    Write-Host "Frontend command: $frontendCommand"
    exit 0
}

Start-Process powershell -WorkingDirectory $repoRoot -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    $backendCommand
) | Out-Null

Start-Process powershell -WorkingDirectory $frontendDir -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    $frontendCommand
) | Out-Null

Write-Host "Started backend and frontend in separate PowerShell windows."
