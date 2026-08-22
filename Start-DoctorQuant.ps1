[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = 'C:\conda2\python.exe'
$Port = 8000

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Doctor Quant requires Python at $Python. Install/configure it before starting Doctor Quant."
}

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    throw "Port $Port is already in use by PID $($listener[0].OwningProcess). Stop that process or choose another port."
}

Push-Location $Root
try {
    if (-not $SkipTests) {
        & $Python -m unittest discover -s tests -q
        if ($LASTEXITCODE -ne 0) { throw 'Doctor Quant tests failed; the server was not started.' }
    }

    # Child environment: HOST=127.0.0.1, PORT=8000. Never expose the local prototype to the network.
    $env:HOST = '127.0.0.1'
    $env:PORT = "$Port"
    $process = Start-Process -FilePath $Python -ArgumentList 'server.py' -WorkingDirectory $Root -PassThru -WindowStyle Hidden

    $deadline = (Get-Date).AddSeconds(15)
    $healthy = $false
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/healthz" -TimeoutSec 2
            $healthy = $response.StatusCode -eq 200
        } catch {
            Start-Sleep -Milliseconds 250
        }
    } while (-not $healthy -and (Get-Date) -lt $deadline)

    if (-not $healthy) {
        if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
        throw 'Doctor Quant did not pass its local health check within 15 seconds.'
    }

    Write-Output "Doctor Quant_PID=$($process.Id)"
    Write-Output "Doctor Quant_URL=http://127.0.0.1:$Port"
    Write-Output "STOP=Stop-Process -Id $($process.Id)"
    if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port" }
} finally {
    Pop-Location
}
