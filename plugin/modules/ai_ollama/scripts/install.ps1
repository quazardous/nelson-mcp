# Install Ollama and pull a starter model
# https://ollama.com

param(
    [string]$Model = "llama3.2:latest"
)

Write-Host ""
Write-Host "=== Ollama Install / Detect ===" -ForegroundColor Cyan
Write-Host ""

# --- Check if Ollama is already installed ---
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollama) {
    Write-Host "[OK] Ollama found: $($ollama.Source)" -ForegroundColor Green
    $ver = & ollama --version 2>&1
    Write-Host "     Version: $ver"
} else {
    Write-Host "[!] Ollama not found in PATH" -ForegroundColor Yellow
    Write-Host ""

    # Try winget first
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "Installing via winget..." -ForegroundColor Cyan
        winget install Ollama.Ollama --accept-package-agreements --accept-source-agreements
        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    }

    if (-not $ollama) {
        Write-Host ""
        Write-Host "Automatic install failed. Please install manually:" -ForegroundColor Red
        Write-Host "  https://ollama.com/download" -ForegroundColor White
        Write-Host ""
        Write-Host "Press Enter to close..."
        Read-Host
        exit 1
    }

    Write-Host "[OK] Ollama installed successfully" -ForegroundColor Green
}

# --- Check if Ollama is running ---
Write-Host ""
try {
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 -ErrorAction Stop
    Write-Host "[OK] Ollama server is running" -ForegroundColor Green
} catch {
    Write-Host "[!] Ollama server is not running. Starting..." -ForegroundColor Yellow
    Start-Process ollama -ArgumentList "serve" -WindowStyle Normal
    Start-Sleep -Seconds 3
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5 -ErrorAction Stop
        Write-Host "[OK] Ollama server started" -ForegroundColor Green
    } catch {
        Write-Host "[!] Could not start Ollama server" -ForegroundColor Red
    }
}

# --- List installed models ---
Write-Host ""
Write-Host "Installed models:" -ForegroundColor Cyan
try {
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3
    if ($tags.models.Count -eq 0) {
        Write-Host "  (none)" -ForegroundColor Yellow
    } else {
        foreach ($m in $tags.models) {
            $sizeMB = [math]::Round($m.size / 1MB, 0)
            Write-Host ("  {0,-30} {1,6} MB" -f $m.name, $sizeMB)
        }
    }
} catch {
    Write-Host "  (could not connect)" -ForegroundColor Red
}

# --- Pull starter model if not present ---
if ($Model -and $Model -ne "none") {
    Write-Host ""
    $installed = $false
    try {
        $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3
        foreach ($m in $tags.models) {
            if ($m.name -eq $Model) { $installed = $true; break }
        }
    } catch {}

    if ($installed) {
        Write-Host "[OK] Model '$Model' is already installed" -ForegroundColor Green
    } else {
        Write-Host "Pulling model '$Model'... (this may take a while)" -ForegroundColor Cyan
        & ollama pull $Model
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] Model '$Model' pulled successfully" -ForegroundColor Green
        } else {
            Write-Host "[!] Failed to pull model '$Model'" -ForegroundColor Red
        }
    }
}

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Cyan
Write-Host "Press Enter to close..."
Read-Host
