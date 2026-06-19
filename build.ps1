# Builds the Windows executable into .\dist\YTPlaylistMP3\
#
# Usage (from this folder):  powershell -ExecutionPolicy Bypass -File .\build.ps1
#   -SkipFfmpeg   build without auto-fetching ffmpeg (it falls back to PATH)
#
# Uses python.org CPython 3.14 via the py launcher, which produces a cleaner,
# more portable Windows binary than the MSYS2 python build.
param(
    [switch]$SkipFfmpeg
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "==> Creating virtual environment (.venv)..." -ForegroundColor Cyan
if (-not (Test-Path ".venv")) {
    py -V:3.14 -m venv .venv
}

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

Write-Host "==> Installing dependencies..." -ForegroundColor Cyan
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements.txt
& $py -m pip install pyinstaller

$haveFfmpeg = (Test-Path ".\ffmpeg\ffmpeg.exe") -and (Test-Path ".\ffmpeg\ffprobe.exe")
if (-not $haveFfmpeg -and -not $SkipFfmpeg) {
    Write-Host "==> ffmpeg not found in .\ffmpeg\ -- fetching it..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "setup-ffmpeg.ps1")
    $haveFfmpeg = (Test-Path ".\ffmpeg\ffmpeg.exe") -and (Test-Path ".\ffmpeg\ffprobe.exe")
}
if ($haveFfmpeg) {
    Write-Host "==> ffmpeg will be bundled from .\ffmpeg\" -ForegroundColor Green
} else {
    Write-Host "==> Building WITHOUT bundled ffmpeg (app will rely on ffmpeg on PATH)." -ForegroundColor Yellow
}

Write-Host "==> Building executable (one-dir, no UPX)..." -ForegroundColor Cyan
& $py -m PyInstaller ytmp3.spec --clean --noconfirm

Write-Host ""
Write-Host "Done. Run: .\dist\YTPlaylistMP3\YTPlaylistMP3.exe" -ForegroundColor Green
