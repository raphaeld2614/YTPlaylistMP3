"""
YouTube Playlist -> MP3 Downloader (tkinter GUI)

Architecture
------------
1. Selenium + Chrome WebDriver loads the (JavaScript-rendered) playlist page,
   scrolls it to force-load every entry, and scrapes the video URLs. This is the
   "web scraping with Chrome webdriver" part of the app.
2. yt-dlp downloads the best audio stream for each scraped URL and, using ffmpeg,
   converts it to an .mp3 inside a folder of the user's choosing.

A confirmation dialog is shown after scraping (so the user can see how many
videos were found and exactly where they will be saved) before any download
happens.

The GUI never blocks: scraping and downloading run on background threads and
communicate with the Tk main loop through a thread-safe queue.
"""

import os
import re
import sys
import time
import queue
import threading
import webbrowser
from urllib.parse import urlparse, parse_qs

import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

APP_TITLE = "YouTube Playlist -> MP3 Downloader"
INVALID_FS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def resource_path(relative: str) -> str:
    """Resolve a path to a bundled resource.

    Works both when running from source and when frozen by PyInstaller, where
    bundled data lives under sys._MEIPASS.
    """
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def find_ffmpeg_dir():
    """Return a directory that contains ffmpeg.exe, or None to fall back to PATH.

    Looked up, in order: bundled 'ffmpeg' dir, an 'ffmpeg' dir next to the
    executable / script, then the system PATH (handled by yt-dlp when None).
    """
    candidates = [
        resource_path("ffmpeg"),
        os.path.join(os.path.dirname(sys.executable), "ffmpeg"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "ffmpeg"),
    ]
    for d in candidates:
        if os.path.isfile(os.path.join(d, "ffmpeg.exe")):
            return d
    return None  # yt-dlp will search PATH


def sanitize_folder_name(name: str) -> str:
    name = INVALID_FS_CHARS.sub("_", (name or "").strip())
    name = name.rstrip(". ")  # Windows dislikes trailing dots/spaces
    return name or "youtube_playlist"


def clean_video_url(href: str):
    """Reduce a YouTube href to a canonical watch URL, or None if not a video."""
    if not href:
        return None
    parsed = urlparse(href)
    vid = parse_qs(parsed.query).get("v", [None])[0]
    if vid:
        return f"https://www.youtube.com/watch?v={vid}"
    return None


# --------------------------------------------------------------------------- #
# Worker: scrape the playlist with Selenium / Chrome WebDriver
# --------------------------------------------------------------------------- #

def scrape_playlist(url, emit):
    """Return (list_of_video_urls, playlist_title).

    `emit(text)` is a callback used to stream status lines back to the GUI.
    Raises on fatal errors (e.g. Chrome/driver missing).
    """
    # Imported here so the GUI can still open with a friendly message if the
    # dependency is missing.
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    emit("Starting Chrome WebDriver (headless)...")
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--mute-audio")
    options.add_argument("--window-size=1280,2200")
    options.add_argument("--lang=en-US")
    options.add_argument("--log-level=3")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])

    # Selenium 4.6+ auto-resolves the matching chromedriver via Selenium Manager.
    driver = webdriver.Chrome(options=options)
    try:
        emit("Loading playlist page...")
        driver.get(url)

        # Best-effort dismissal of the EU cookie-consent interstitial.
        try:
            btn = WebDriverWait(driver, 4).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[.//span[contains(text(),'Reject all') or contains(text(),'Accept all')]]")
                )
            )
            btn.click()
            time.sleep(1)
        except Exception:
            pass

        # Only collect links that belong to THIS playlist (its list= id), so we
        # never pick up sidebar / recommended videos. Falls back to all watch
        # links if the id can't be determined.
        target_list = parse_qs(urlparse(url).query).get("list", [None])[0]

        # YouTube's per-video element ids change often; matching the watch?v=
        # hrefs directly is far more stable than a brittle component selector.
        video_selector = "a[href*='watch?v=']"
        WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, video_selector))
        )

        def collect_urls():
            ordered, seen = [], set()
            for a in driver.find_elements(By.CSS_SELECTOR, video_selector):
                href = a.get_attribute("href") or ""
                if target_list and f"list={target_list}" not in href:
                    continue
                cleaned = clean_video_url(href)
                if cleaned and cleaned not in seen:
                    seen.add(cleaned)
                    ordered.append(cleaned)
            return ordered

        emit("Scrolling to load all videos...")
        last_count, stable = -1, 0
        while stable < 3:
            driver.execute_script(
                "window.scrollTo(0, document.documentElement.scrollHeight);"
            )
            time.sleep(1.6)
            count = len(collect_urls())
            if count == last_count:
                stable += 1
            else:
                stable, last_count = 0, count
                emit(f"  ...found {count} videos so far")

        urls = collect_urls()
        title = driver.title.replace(" - YouTube", "").strip()
        return urls, title
    finally:
        driver.quit()


# --------------------------------------------------------------------------- #
# Worker: download + convert with yt-dlp
# --------------------------------------------------------------------------- #

def download_videos(urls, target_dir, quality, emit, on_progress):
    import yt_dlp

    ffmpeg_dir = find_ffmpeg_dir()
    if ffmpeg_dir:
        emit(f"Using bundled ffmpeg: {ffmpeg_dir}")
    else:
        emit("Using ffmpeg from system PATH (none bundled).")

    total = len(urls)
    completed = 0

    for index, url in enumerate(urls, start=1):
        emit(f"[{index}/{total}] {url}")

        def hook(d, _i=index):
            if d.get("status") == "downloading":
                tb = d.get("total_bytes") or d.get("total_bytes_estimate")
                frac = (d.get("downloaded_bytes", 0) / tb) if tb else 0.0
                on_progress((_i - 1 + frac) / total * 100.0)
            elif d.get("status") == "finished":
                emit("    Converting to MP3...")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(target_dir, "%(title)s.%(ext)s"),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": str(quality),
                }
            ],
            "noplaylist": True,
            "ignoreerrors": True,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [hook],
            "retries": 5,
            "fragment_retries": 5,
        }
        if ffmpeg_dir:
            ydl_opts["ffmpeg_location"] = ffmpeg_dir

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                rc = ydl.download([url])
            if rc == 0:
                completed += 1
                emit("    Done.")
            else:
                emit("    Skipped (unavailable or errored).")
        except Exception as exc:  # noqa: BLE001 - surface any per-video failure
            emit(f"    ERROR: {exc}")

        on_progress(index / total * 100.0)

    return completed, total


# --------------------------------------------------------------------------- #
# GUI
# --------------------------------------------------------------------------- #

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.q: "queue.Queue[tuple]" = queue.Queue()
        self.busy = False

        # Carried between the scrape thread and the (main-thread) confirmation.
        self._parent_dir = ""
        self._folder_pref = ""
        self._quality = 192

        root.title(APP_TITLE)
        root.geometry("680x560")
        root.minsize(620, 500)

        self._build_ui()
        self.root.after(100, self._poll_queue)

    # -- UI construction --------------------------------------------------- #
    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}
        frm = ttk.Frame(self.root, padding=12)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text=APP_TITLE, font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )

        ttk.Label(frm, text="Playlist URL:").grid(row=1, column=0, sticky="w", **pad)
        self.url_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.url_var).grid(
            row=1, column=1, columnspan=2, sticky="ew", **pad
        )

        ttk.Label(frm, text="Save to folder:").grid(row=2, column=0, sticky="w", **pad)
        self.dir_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.dir_var).grid(row=2, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="Browse...", command=self._browse).grid(
            row=2, column=2, sticky="ew", **pad
        )

        ttk.Label(frm, text="Subfolder name:").grid(row=3, column=0, sticky="w", **pad)
        self.folder_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.folder_var).grid(row=3, column=1, sticky="ew", **pad)
        ttk.Label(frm, text="(optional)").grid(row=3, column=2, sticky="w", **pad)

        ttk.Label(frm, text="MP3 quality (kbps):").grid(row=4, column=0, sticky="w", **pad)
        self.quality_var = tk.StringVar(value="192")
        ttk.Combobox(
            frm,
            textvariable=self.quality_var,
            values=["128", "192", "256", "320"],
            state="readonly",
            width=8,
        ).grid(row=4, column=1, sticky="w", **pad)

        self.start_btn = ttk.Button(frm, text="Start", command=self._on_start)
        self.start_btn.grid(row=5, column=0, columnspan=3, sticky="ew", **pad)

        self.progress = ttk.Progressbar(frm, mode="determinate", maximum=100)
        self.progress.grid(row=6, column=0, columnspan=3, sticky="ew", **pad)

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(frm, textvariable=self.status_var).grid(
            row=7, column=0, columnspan=3, sticky="w", **pad
        )

        log_frame = ttk.Frame(frm)
        log_frame.grid(row=8, column=0, columnspan=3, sticky="nsew", **pad)
        frm.rowconfigure(8, weight=1)
        self.log = tk.Text(log_frame, height=12, wrap="word", state="disabled")
        self.log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(log_frame, command=self.log.yview)
        sb.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=sb.set)

    # -- small UI helpers -------------------------------------------------- #
    def _browse(self):
        chosen = filedialog.askdirectory(title="Choose where to save the MP3s")
        if chosen:
            self.dir_var.set(chosen)

    def _append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_busy(self, busy):
        self.busy = busy
        self.start_btn.configure(state="disabled" if busy else "normal")

    # -- queue plumbing (worker threads -> main thread) -------------------- #
    def _emit(self, text):
        self.q.put(("log", text))

    def _progress(self, value):
        self.q.put(("progress", value))

    def _poll_queue(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._append_log(msg[1])
                elif kind == "progress":
                    self.progress["value"] = msg[1]
                elif kind == "status":
                    self.status_var.set(msg[1])
                elif kind == "scrape_done":
                    self._on_scrape_done(msg[1], msg[2])
                elif kind == "scrape_error":
                    self._on_worker_error(msg[1])
                elif kind == "finished":
                    self._on_finished(msg[1], msg[2], msg[3])
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    # -- event handlers ---------------------------------------------------- #
    def _on_start(self):
        if self.busy:
            return
        url = self.url_var.get().strip()
        parent = self.dir_var.get().strip()

        if not url:
            messagebox.showwarning(APP_TITLE, "Please enter a YouTube playlist URL.")
            return
        if "list=" not in url:
            if not messagebox.askyesno(
                APP_TITLE,
                "That URL does not look like a playlist (no 'list=' parameter).\n\n"
                "Try to scrape it anyway?",
            ):
                return
        if not parent or not os.path.isdir(parent):
            messagebox.showwarning(APP_TITLE, "Please choose a valid destination folder.")
            return

        self._parent_dir = parent
        self._folder_pref = self.folder_var.get().strip()
        try:
            self._quality = int(self.quality_var.get())
        except ValueError:
            self._quality = 192

        self._set_busy(True)
        self.progress["value"] = 0
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.status_var.set("Scraping playlist...")

        threading.Thread(target=self._scrape_thread, args=(url,), daemon=True).start()

    def _scrape_thread(self, url):
        try:
            urls, title = scrape_playlist(url, self._emit)
            self.q.put(("scrape_done", urls, title))
        except Exception as exc:  # noqa: BLE001
            self.q.put(("scrape_error", str(exc)))

    def _on_scrape_done(self, urls, title):
        if not urls:
            self.status_var.set("No videos found.")
            messagebox.showinfo(
                APP_TITLE,
                "No videos were found on that page. The playlist may be private, "
                "empty, or the page layout changed.",
            )
            self._set_busy(False)
            return

        folder = sanitize_folder_name(self._folder_pref or title)
        target_dir = os.path.join(self._parent_dir, folder)

        # ---- Confirmation menu before downloading ---- #
        confirmed = messagebox.askyesno(
            "Confirm download",
            f"Found {len(urls)} video(s).\n\n"
            f"They will be downloaded as MP3 ({self._quality} kbps) into:\n\n"
            f"{target_dir}\n\n"
            f"Proceed with the download?",
            icon="question",
        )
        if not confirmed:
            self.status_var.set("Cancelled.")
            self._append_log("Download cancelled by user.")
            self._set_busy(False)
            return

        try:
            os.makedirs(target_dir, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Could not create folder:\n{exc}")
            self._set_busy(False)
            return

        self.status_var.set(f"Downloading {len(urls)} video(s)...")
        threading.Thread(
            target=self._download_thread,
            args=(urls, target_dir),
            daemon=True,
        ).start()

    def _download_thread(self, urls, target_dir):
        try:
            completed, total = download_videos(
                urls, target_dir, self._quality, self._emit, self._progress
            )
            self.q.put(("finished", completed, total, target_dir))
        except Exception as exc:  # noqa: BLE001
            self.q.put(("scrape_error", str(exc)))

    def _on_finished(self, completed, total, target_dir):
        self.progress["value"] = 100
        self.status_var.set(f"Finished: {completed}/{total} downloaded.")
        self._set_busy(False)
        if messagebox.askyesno(
            APP_TITLE,
            f"Done! {completed} of {total} video(s) saved as MP3 in:\n\n"
            f"{target_dir}\n\nOpen the folder now?",
        ):
            try:
                os.startfile(target_dir)  # type: ignore[attr-defined]
            except Exception:
                webbrowser.open(target_dir)

    def _on_worker_error(self, message):
        self.status_var.set("Error.")
        self._append_log("ERROR: " + message)
        self._set_busy(False)
        hint = ""
        low = message.lower()
        if "chromedriver" in low or "chrome" in low or "session not created" in low:
            hint = "\n\nMake sure Google Chrome is installed and up to date."
        elif "ffmpeg" in low:
            hint = "\n\nffmpeg was not found. See the README for how to provide it."
        messagebox.showerror(APP_TITLE, message + hint)


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")  # nicer native look on Windows
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
