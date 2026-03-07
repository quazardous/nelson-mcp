# Stop Stable Diffusion WebUI Forge
param(
    [string]$Endpoint = "http://127.0.0.1:7860"
)

Write-Host "=== Stopping Forge ===" -ForegroundColor Cyan
Write-Host "Endpoint: $Endpoint"
Write-Host ""

# Check if running
try {
    $null = Invoke-WebRequest -Uri "$Endpoint/sdapi/v1/sd-models" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
} catch {
    Write-Host "Forge is not running at $Endpoint" -ForegroundColor Yellow
    Read-Host "Press Enter to close"
    exit 0
}

# Find python processes running launch.py
$procs = Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -match "launch\.py"
}

if ($procs) {
    foreach ($p in $procs) {
        Write-Host "Stopping PID $($p.ProcessId): $($p.CommandLine)" -ForegroundColor Yellow
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }

    # Wait and verify
    Start-Sleep -Seconds 2
    try {
        $null = Invoke-WebRequest -Uri "$Endpoint/sdapi/v1/sd-models" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        Write-Host "WARNING: Forge may still be running." -ForegroundColor Red
    } catch {
        Write-Host "Forge stopped." -ForegroundColor Green
    }
} else {
    Write-Host "No launch.py process found. Forge may be running externally." -ForegroundColor Yellow
}

Write-Host ""
Read-Host "Press Enter to close"
