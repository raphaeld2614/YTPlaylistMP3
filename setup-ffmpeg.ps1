<#
.SYNOPSIS
    Downloads a static Windows ffmpeg build and places ffmpeg.exe + ffprobe.exe
    into the .\ffmpeg\ folder, so the app (and the PyInstaller build) can bundle
    them.

.DESCRIPTION
    Primary source : gyan.dev "release-essentials" build (verified via SHA-256).
    Fallback source : BtbN/FFmpeg-Builds on GitHub (used only if gyan is down).

.PARAMETER Destination
    Folder to place ffmpeg.exe / ffprobe.exe into. Default: .\ffmpeg next to this script.

.PARAMETER Force
    Re-download even if the binaries already exist.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup-ffmpeg.ps1
#>
[CmdletBinding()]
param(
    [string]$Destination = (Join-Path $PSScriptRoot "ffmpeg"),
    [switch]$Force
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$ffmpeg  = Join-Path $Destination "ffmpeg.exe"
$ffprobe = Join-Path $Destination "ffprobe.exe"

if ((Test-Path $ffmpeg) -and (Test-Path $ffprobe) -and -not $Force) {
    Write-Host "ffmpeg already present in $Destination (use -Force to re-download)." -ForegroundColor Green
    & $ffmpeg -hide_banner -version | Select-Object -First 1
    return
}

New-Item -ItemType Directory -Force -Path $Destination | Out-Null
$work = Join-Path ([System.IO.Path]::GetTempPath()) ("ffmpeg_setup_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $work | Out-Null

function Install-From-Zip {
    param([string]$ZipPath)
    Write-Host "Extracting..." -ForegroundColor Cyan
    $extract = Join-Path $work "x"
    Expand-Archive -Path $ZipPath -DestinationPath $extract -Force
    $src1 = Get-ChildItem -Path $extract -Recurse -Filter "ffmpeg.exe"  | Select-Object -First 1
    $src2 = Get-ChildItem -Path $extract -Recurse -Filter "ffprobe.exe" | Select-Object -First 1
    if (-not $src1 -or -not $src2) { throw "ffmpeg.exe / ffprobe.exe not found inside the archive." }
    Copy-Item $src1.FullName $ffmpeg  -Force
    Copy-Item $src2.FullName $ffprobe -Force
}

try {
    $zip = Join-Path $work "ffmpeg.zip"
    $usedFallback = $false
    try {
        $url    = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        $shaUrl = "$url.sha256"
        Write-Host "Downloading ffmpeg from gyan.dev..." -ForegroundColor Cyan
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing

        Write-Host "Verifying SHA-256..." -ForegroundColor Cyan
        $expected = ((Invoke-WebRequest -Uri $shaUrl -UseBasicParsing).Content -split '\s+')[0].Trim().ToLower()
        $actual   = (Get-FileHash -Path $zip -Algorithm SHA256).Hash.ToLower()
        if ($expected -and $expected -ne $actual) {
            throw "Checksum mismatch! expected=$expected actual=$actual"
        }
        Write-Host "  checksum OK" -ForegroundColor Green
    }
    catch {
        Write-Warning "gyan.dev failed ($($_.Exception.Message)). Falling back to BtbN/FFmpeg-Builds..."
        $usedFallback = $true
        $url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
        Write-Warning "  (fallback build is not checksum-verified)"
    }

    Install-From-Zip -ZipPath $zip

    Write-Host ""
    Write-Host "Installed to $Destination" -ForegroundColor Green
    & $ffmpeg -hide_banner -version | Select-Object -First 1
    if ($usedFallback) { Write-Host "(via BtbN fallback)" -ForegroundColor Yellow }
}
finally {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $work
}
