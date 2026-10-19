# Icarus Agent Universal Installer for Windows
# Run with: irm https://raw.githubusercontent.com/AchillesLabs/icarus-agent/main/install.ps1 | iex

$ErrorActionPreference = 'Stop'

Write-Host "  ___                                 _                    _   " -ForegroundColor Cyan
Write-Host " |_ _|___ __ _ _ _ _  _ ___   /\_/\  /_\   __ _ ___ _ _  _| |_ " -ForegroundColor Cyan
Write-Host "  | |/ _ / _` | '_| || (_-<  ( o.o )/ _ \ / _` / -_) ' \|  _| " -ForegroundColor Cyan
Write-Host " |___\___\__,_|_|  \_,_/__/   > ^ </_/ \_\__, \___|_||_|\__| " -ForegroundColor Cyan
Write-Host "                                          |___/                " -ForegroundColor Cyan
Write-Host "        Autonomous Personal Executive Agent (Jarvis)          " -ForegroundColor Yellow
Write-Host ""

Write-Host "==> Checking dependencies..." -ForegroundColor Cyan

# 1. Ensure uv is installed
$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uvCmd) {
    Write-Host "==> Installing uv package manager..." -ForegroundColor Yellow
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

    # Refresh PATH in current session
    $cargoBin = "$env:USERPROFILE\.cargo\bin"
    $localBin = "$env:USERPROFILE\.local\bin"
    if (Test-Path $cargoBin) {
        $env:PATH = "$cargoBin;$env:PATH"
    }
    if (Test-Path $localBin) {
        $env:PATH = "$localBin;$env:PATH"
    }

    $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uvCmd) {
        Write-Error "uv was installed but could not be resolved in PATH. Please restart PowerShell and re-run."
        exit 1
    }
}

$uvVersion = & uv --version
Write-Host "==> uv is ready: $uvVersion" -ForegroundColor Green

# 2. Install icarus-agent via uv tool
$PackageSpec = if ($env:ICARUS_PACKAGE_SPEC) { $env:ICARUS_PACKAGE_SPEC } else { "icarus-agent" }
Write-Host "==> Installing Icarus Agent ($PackageSpec)..." -ForegroundColor Cyan
& uv tool install --force $PackageSpec

Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host "       Icarus Agent successfully installed!                    " -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "To start your autonomous personal assistant, run:" -ForegroundColor White
Write-Host "    icarus           (Full-Screen Interactive TUI Workspace)" -ForegroundColor Cyan
Write-Host "    icarus doctor    (Verify local storage and credentials)" -ForegroundColor Cyan
Write-Host "    icarus init      (Configure your AI provider API key)" -ForegroundColor Cyan
Write-Host ""
