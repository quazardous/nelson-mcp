# Install Stable Diffusion WebUI Forge - fully automated
# https://github.com/lllyasviel/stable-diffusion-webui-forge

param(
    [string]$StarterModel = "dreamshaper8"
)

$InstallDir = "$env:USERPROFILE\stable-diffusion-webui"

# --- Model catalog ---
$Models = @{
    juggernaut_xl = @{
        file = "juggernautXL_v9Lightning.safetensors"
        url  = "https://civitai.com/api/download/models/357609"
        size = "6.5 GB"
        disk = 16
    }
    dreamshaper8 = @{
        file = "dreamshaper_8.safetensors"
        url  = "https://civitai.com/api/download/models/128713?type=Model&format=SafeTensor&size=pruned&fp=fp16"
        size = "2.1 GB"
        disk = 12
    }
    dreamshaperxl = @{
        file = "dreamshaperXL_v21.safetensors"
        url  = "https://civitai.com/api/download/models/351306?type=Model&format=SafeTensor&size=pruned&fp=fp16"
        size = "6.5 GB"
        disk = 16
    }
    none = @{
        file = ""
        url  = ""
        size = "0"
        disk = 10
    }
}

$model = $Models[$StarterModel]
if (-not $model) {
    Write-Host "Unknown model: $StarterModel - falling back to juggernaut_xl" -ForegroundColor Yellow
    $StarterModel = "juggernaut_xl"
    $model = $Models[$StarterModel]
}

$RequiredGB = $model.disk
$modelSize = $model.size

Write-Host "=== Stable Diffusion WebUI Forge Installer ===" -ForegroundColor Cyan
Write-Host "Model: $StarterModel ($modelSize)"
Write-Host ""

# --- Disk space check ---
$driveLetter = $env:USERPROFILE.Substring(0,1)
$drive = Get-PSDrive -Name $driveLetter
$freeGB = [math]::Round($drive.Free / 1GB, 1)
Write-Host "Disk space: $freeGB GB free"
if ($freeGB -lt $RequiredGB) {
    Write-Host "ERROR: At least $RequiredGB GB required for this setup." -ForegroundColor Red
    Write-Host "Free up some space or choose a smaller model." -ForegroundColor Yellow
    Read-Host "Press Enter to close"
    exit 1
}
Write-Host "OK: $freeGB GB available (need $RequiredGB GB)." -ForegroundColor Green
Write-Host ""

# --- Check Git ---
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "Git not found. Please install Git first:" -ForegroundColor Red
    Write-Host "  https://git-scm.com/downloads" -ForegroundColor Yellow
    Read-Host "Press Enter to close"
    exit 1
}

# --- Install uv if not present ---
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..." -ForegroundColor Yellow
    irm https://astral.sh/uv/install.ps1 | iex
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: uv installation failed." -ForegroundColor Red
        Read-Host "Press Enter to close"
        exit 1
    }
    Write-Host "uv installed." -ForegroundColor Green
}

# --- Clone or update Forge ---
if (Test-Path $InstallDir) {
    Write-Host "Directory already exists: $InstallDir" -ForegroundColor Yellow
    Write-Host "Updating..."
    Push-Location $InstallDir
    git pull
    Pop-Location
} else {
    Write-Host "Cloning Forge into $InstallDir ..."
    git clone https://github.com/lllyasviel/stable-diffusion-webui-forge.git $InstallDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: git clone failed." -ForegroundColor Red
        Read-Host "Press Enter to close"
        exit 1
    }
}

# --- Create venv ---
$venvDir = Join-Path $InstallDir "venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host ""
    Write-Host "Creating venv with Python 3.10 via uv..." -ForegroundColor Yellow
    & uv venv --python 3.10 --seed $venvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to create venv." -ForegroundColor Red
        Read-Host "Press Enter to close"
        exit 1
    }
    Write-Host "venv created." -ForegroundColor Green
} else {
    Write-Host "venv already exists." -ForegroundColor Green
}

# --- Install dependencies ---
$reqFile = Join-Path $InstallDir "requirements_versions.txt"
if (Test-Path $reqFile) {
    Write-Host ""
    Write-Host "Installing dependencies (this may take a while)..." -ForegroundColor Yellow
    & uv pip install -p $venvPython torch==2.3.1 torchvision==0.18.1 --extra-index-url https://download.pytorch.org/whl/cu121
    & uv pip install -p $venvPython -r $reqFile
    & uv pip install -p $venvPython --no-build-isolation "https://github.com/openai/CLIP/archive/d50d76daa670286dd6cacf3bcd80b5e4823fc8e1.zip"
    & uv pip install -p $venvPython numpy==1.26.2
    Write-Host "Dependencies installed." -ForegroundColor Green
}

# --- Download model ---
if ($StarterModel -ne "none") {
    $modelsDir = Join-Path $InstallDir "models\Stable-diffusion"
    $modelFileName = $model.file
    $modelFile = Join-Path $modelsDir $modelFileName

    if (-not (Test-Path $modelsDir)) {
        New-Item -ItemType Directory -Path $modelsDir -Force | Out-Null
    }

    if (Test-Path $modelFile) {
        $sizeMB = [math]::Round((Get-Item $modelFile).Length / 1MB)
        Write-Host ""
        Write-Host "Model already exists: $modelFileName ($sizeMB MB)" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "Downloading model: $StarterModel ($modelSize)..." -ForegroundColor Yellow
        try {
            $ProgressPreference = 'SilentlyContinue'
            Invoke-WebRequest -Uri $model.url -OutFile $modelFile -UseBasicParsing
            $ProgressPreference = 'Continue'
            if (Test-Path $modelFile) {
                $sizeMB = [math]::Round((Get-Item $modelFile).Length / 1MB)
                Write-Host "Model downloaded: $modelFileName ($sizeMB MB)" -ForegroundColor Green
            }
        } catch {
            Write-Host "WARNING: Could not download model automatically." -ForegroundColor Yellow
            Write-Host "Error: $_" -ForegroundColor Yellow
            Write-Host ""
            Write-Host "Download a model manually and place it in:" -ForegroundColor Yellow
            Write-Host "  $modelsDir" -ForegroundColor Yellow
        }
    }
}

# --- Activate model if API is running ---
if ($StarterModel -ne "none" -and $modelFileName) {
    $apiUrl = "http://127.0.0.1:7860"
    try {
        $null = Invoke-WebRequest -Uri "$apiUrl/sdapi/v1/sd-models" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        Write-Host ""
        Write-Host "API is running - activating model..." -ForegroundColor Yellow
        # Refresh checkpoint list
        Invoke-WebRequest -Uri "$apiUrl/sdapi/v1/refresh-checkpoints" -Method POST -UseBasicParsing -TimeoutSec 10 -ErrorAction SilentlyContinue | Out-Null
        # Set active model
        $body = @{ sd_model_checkpoint = $modelFileName } | ConvertTo-Json
        Invoke-WebRequest -Uri "$apiUrl/sdapi/v1/options" -Method POST -Body $body -ContentType "application/json" -UseBasicParsing -TimeoutSec 120 -ErrorAction Stop | Out-Null
        Write-Host "Model activated: $modelFileName" -ForegroundColor Green
    } catch {
        Write-Host "API not running - model will be activated on next launch." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "=== Installation complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Use the 'Launch Forge' button in Nelson Options to start the WebUI." -ForegroundColor Cyan
Write-Host ""
Read-Host "Press Enter to close"
