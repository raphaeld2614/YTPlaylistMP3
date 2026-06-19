# YouTube Playlist → MP3 Downloader

A small Windows desktop app (tkinter GUI) that:

1. Uses **Selenium + Chrome WebDriver** to scrape every video URL from a YouTube
   playlist page.
2. Shows a **confirmation dialog** (how many videos, where they'll be saved).
3. Uses **yt-dlp + ffmpeg** to download each video and convert it to an `.mp3`
   inside a folder of your choosing.

Downloading is run on background threads, so the window stays responsive, and a
progress bar + live log show what's happening.

---

## Why Selenium *and* yt-dlp?

Chrome WebDriver is great at **scraping** the JavaScript-rendered playlist page
to enumerate the videos, but a browser can't rip and transcode audio. `yt-dlp`
(with `ffmpeg`) is the reliable, standard way to actually produce MP3 files. So
the app uses each tool for what it's best at.

---

## Prerequisites

- **Google Chrome** installed and reasonably up to date. (Selenium 4.6+
  auto-downloads the matching `chromedriver` for you — no manual driver setup.)
- **ffmpeg** — required for MP3 conversion. Either:
  - put `ffmpeg.exe` (and `ffprobe.exe`) in an `ffmpeg\` folder next to the app /
    this project (recommended — makes the app self-contained), **or**
  - install ffmpeg and make sure it's on your system `PATH`.
  - Get static Windows builds from <https://www.gyan.dev/ffmpeg/builds/> (the
    "release essentials" zip) or <https://github.com/BtbN/FFmpeg-Builds/releases>.

---

## Easiest way to run (double-click launcher)

After building once (which creates the `.venv`), just use either:

- **`YT Playlist MP3 Downloader`** shortcut (on the Desktop and in this folder), or
- **`Run YT Playlist MP3.bat`**

Both start the GUI through Python's signed `pythonw.exe`, with **no console window**.

### Why not the .exe? (Smart App Control)

If your PC has **Windows 11 Smart App Control (SAC)** enabled, it blocks *every*
unsigned third-party `.exe` — not because the app is malicious, but because SAC
is a strict allowlist that only permits signed/reputation-trusted binaries.
(Self-signing does **not** satisfy SAC.) The launcher above sidesteps this
entirely because it runs the trusted, PSF-signed `pythonw.exe`.

To run the packaged `.exe` directly you would have to either turn SAC off
(**irreversible** — re-enabling requires resetting Windows) or sign the exe with
a purchased OV/EV certificate. On machines **without** SAC, the built `.exe`
runs as-is.

## Run from source (quick test)

```powershell
py -V:3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python ytmp3_downloader.py
```

## Build the Windows executable

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

The app is produced at `dist\YTPlaylistMP3\YTPlaylistMP3.exe`. Distribute the
**whole `YTPlaylistMP3` folder** (it's a one-dir build), not just the `.exe`.

---

## Avoiding Windows Defender false positives

PyInstaller apps are a common source of *false* malware flags. This project is
already configured to minimise that:

| Trigger                         | What we do instead                          |
|---------------------------------|---------------------------------------------|
| One-file self-extracting `.exe` | **One-dir build** (`COLLECT` in the spec).  |
| UPX / packed binaries           | **UPX disabled** (`upx=False`).             |
| No file metadata                | **Embedded version resource** (`version.txt`). |
| Console window / odd behavior   | Plain **windowed GUI** app.                 |

Additional steps that further reduce or eliminate flags:

- **Keep PyInstaller & deps current** — older bootloaders are more often flagged.
  If a flag persists, rebuild the PyInstaller bootloader from source.
- **Code-sign the executable.** This is the only thing that *reliably* removes
  warnings. An OV/EV code-signing certificate costs money; for personal use you
  can create a self-signed cert and trust it on your own machine:
  ```powershell
  $cert = New-SelfSignedCertificate -Type CodeSigningCert `
      -Subject "CN=YT Playlist MP3" -CertStoreLocation Cert:\CurrentUser\My
  Set-AuthenticodeSignature .\dist\YTPlaylistMP3\YTPlaylistMP3.exe $cert
  ```
- **Report false positives to Microsoft** at
  <https://www.microsoft.com/wdsi/filesubmission> so the detection is corrected.
- **Add an exclusion** for the build/output folder during development
  (Windows Security → Virus & threat protection → Manage settings → Exclusions).

> Note: these are legitimate steps to stop a benign app from being *mis*flagged.
> None of them hide actual malware — the app's full source is in this folder.

---

## Notes & limitations

- Only **public/unlisted** playlists can be scraped (private ones need a login).
- Respect YouTube's Terms of Service and copyright law; use this for content you
  are allowed to download (e.g. your own uploads or Creative-Commons material).
- Age-restricted or region-locked videos may be skipped; the log will say so.
