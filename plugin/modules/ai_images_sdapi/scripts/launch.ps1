# Launch Stable Diffusion WebUI Forge with --api flag (uses uv for deps)
param(
    [string]$WebUIDir
)

if (-not $WebUIDir -or -not (Test-Path $WebUIDir)) {
    Write-Host "ERROR: WebUI directory not found: $WebUIDir" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: uv not found. Install it from https://docs.astral.sh/uv/" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host "=== Launching Stable Diffusion WebUI Forge ===" -ForegroundColor Cyan
Write-Host "Directory: $WebUIDir"
Write-Host ""

Set-Location $WebUIDir

$venvDir = Join-Path $WebUIDir "venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

# Create venv with uv if it doesn't exist
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating venv with Python 3.10 via uv..." -ForegroundColor Yellow
    & uv venv --python 3.10 --seed $venvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to create venv." -ForegroundColor Red
        Read-Host "Press Enter to close"
        exit 1
    }
    Write-Host "venv created." -ForegroundColor Green
}

Write-Host "Using Python: $venvPython" -ForegroundColor Green

# Install dependencies via uv pip
$reqFile = Join-Path $WebUIDir "requirements_versions.txt"
if (Test-Path $reqFile) {
    Write-Host "Installing dependencies via uv pip..." -ForegroundColor Yellow
    & uv pip install -p $venvPython torch==2.3.1 torchvision==0.18.1 --extra-index-url https://download.pytorch.org/whl/cu121
    & uv pip install -p $venvPython -r $reqFile
    & uv pip install -p $venvPython --no-build-isolation "https://github.com/openai/CLIP/archive/d50d76daa670286dd6cacf3bcd80b5e4823fc8e1.zip"
    # Force numpy to pinned version (scikit-image needs matching binary)
    & uv pip install -p $venvPython numpy==1.26.2
    Write-Host ""
}

# Launch
$launchPy = Join-Path $WebUIDir "launch.py"
if (-not (Test-Path $launchPy)) {
    Write-Host "ERROR: launch.py not found in $WebUIDir" -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host "Starting: launch.py --api" -ForegroundColor Cyan
Write-Host ""

# Clean environment to avoid conflicts with LibreOffice's Python
$env:PYTHONHOME = $null
$env:PYTHONPATH = $null
$env:VIRTUAL_ENV = $null

& $venvPython $launchPy --api

Write-Host ""
Write-Host "WebUI exited." -ForegroundColor Yellow
Read-Host "Press Enter to close"
