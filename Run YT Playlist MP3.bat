@echo off
rem ============================================================================
rem  Launches the YouTube Playlist -> MP3 Downloader GUI.
rem
rem  It runs the app through Python's signed pythonw.exe (no console window),
rem  which Windows Smart App Control trusts -- so it works on machines where the
rem  unsigned packaged .exe would be blocked.
rem ============================================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo Could not find .venv\Scripts\pythonw.exe
    echo Run build.ps1 once to create the environment, then try again.
    pause
    exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" "ytmp3_downloader.py"
