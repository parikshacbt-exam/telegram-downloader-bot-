import os
import time
import asyncio
import logging
import re
from utils.progress import progress_for_pyrogram

logger = logging.getLogger(__name__)

async def download_with_ytdl(url: str, output_dir: str, status_msg, start_time: float):
    """
    Download video from 1800+ supported video platforms (YouTube, Instagram, Adult sites, Facebook, Twitter, etc.)
    Returns: dict with filepath, title, duration, width, height
    """
    import yt_dlp

    loop = asyncio.get_running_loop()
    last_update = [time.time()]

    def progress_hook(d):
        if d.get('status') == 'downloading':
            now = time.time()
            if now - last_update[0] >= 3.5:
                last_update[0] = now
                current = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                if total and total > 0:
                    try:
                        asyncio.run_coroutine_threadsafe(
                            progress_for_pyrogram(current, total, "Downloading Stream", status_msg, start_time),
                            loop
                        )
                    except Exception:
                        pass

    out_template = os.path.join(output_dir, "%(id)s_%(title).60s.%(ext)s")

    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/bestvideo+bestaudio/best',
        'outtmpl': out_template,
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [progress_hook],
        'max_filesize': 2000 * 1024 * 1024,  # 2 GB Telegram Bot limit
        'noplaylist': True,
        'socket_timeout': 20,
        'retries': 3,
        'extractor_retries': 3,
        'geo_bypass': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
        }
    }

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                raise Exception("Could not extract media information from this link.")
            if 'entries' in info and info['entries']:
                info = info['entries'][0]
            filename = ydl.prepare_filename(info)
            return info, filename

    # Timeout after 6 minutes to prevent infinite hanging
    info, filepath = await asyncio.wait_for(
        loop.run_in_executor(None, _extract),
        timeout=360
    )

    # Some extractors merge into mkv or webm or mp4
    if not os.path.exists(filepath):
        base, _ = os.path.splitext(filepath)
        for ext in [".mp4", ".mkv", ".webm", ".m4v"]:
            if os.path.exists(base + ext):
                filepath = base + ext
                break

    if not os.path.exists(filepath):
        raise Exception("Downloaded media file not found on disk.")

    title = info.get("title") or "Video"
    title = re.sub(r'[\\/*?:"<>|]', "_", title)

    return {
        "filepath": filepath,
        "title": title,
        "duration": int(info.get("duration") or 0),
        "width": int(info.get("width") or 0),
        "height": int(info.get("height") or 0),
    }
