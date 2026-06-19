# Builds the Windows executable into .\dist\YTPlaylistMP3\
#
# Usage (from this folder):  powershell -ExecutionPolicy Bypass -File .\build.ps1
#
# Uses python.org CPython 3.14 via the py launcher, which produces a cleaner,
# more portable Windows binary than the MSYS2 python build.

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

Write-Host "==> Building executable (one-dir, no UPX)..." -ForegroundColor Cyan
& $py -m PyInstaller ytmp3.spec --clean --noconfirm

Write-Host ""
Write-Host "Done. Run: .\dist\YTPlaylistMP3\YTPlaylistMP3.exe" -ForegroundColor Green
Write-Host "Tip: drop ffmpeg.exe (and ffprobe.exe) into .\ffmpeg\ before building" -ForegroundColor Yellow
Write-Host "     to make the app fully self-contained." -ForegroundColor Yellow
