# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller build recipe tuned to minimise Windows Defender false positives:
#   * one-DIR build (not one-FILE) -- self-extracting one-file stubs are the
#     single biggest trigger for AV heuristics.
#   * UPX disabled -- packed/compressed executables look like malware to AV.
#   * a real Windows version resource is embedded (see version.txt).
#   * windowed (no console) GUI app.
#
# Build with:  pyinstaller ytmp3.spec --clean --noconfirm

import os
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []

# Pull in data files, binaries and submodules for our two heavyweight deps so
# nothing is missing at runtime (yt-dlp's extractors, selenium-manager, etc.).
for pkg in ("yt_dlp", "selenium"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Optionally bundle ffmpeg if the user dropped it into ./ffmpeg/ next to this
# spec. Without it, the app falls back to ffmpeg on the system PATH.
for tool in ("ffmpeg.exe", "ffprobe.exe"):
    local = os.path.join("ffmpeg", tool)
    if os.path.exists(local):
        binaries.append((local, "ffmpeg"))

a = Analysis(
    ["ytmp3_downloader.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="YTPlaylistMP3",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # do NOT pack -- AV-friendly
    console=False,       # windowed GUI
    disable_windowed_traceback=False,
    version="version.txt",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="YTPlaylistMP3",
)
