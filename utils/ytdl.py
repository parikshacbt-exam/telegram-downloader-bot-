import os
import time
import asyncio
import logging
import re
from utils.progress import progress_for_pyrogram

logger = logging.getLogger(__name__)

async def download_with_ytdl(url: str, output_dir: str, status_msg, start_time: float):
    """
    Download video from 1800+ supported video platforms (YouTube, Instagram, Adult sites, etc.)
    """
    import yt_dlp

    loop = asyncio.get_running_loop()
    last_update = [time.time()]

    def progress_hook(d):
        if d.get('status') == 'downloading':
            now = time.time()
            if now - last_update[0] >= 3:
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
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': out_template,
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [progress_hook],
        'max_filesize': 2000 * 1024 * 1024,
        'noplaylist': True,
    }

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                raise Exception("Could not extract media info.")
            if 'entries' in info and info['entries']:
                info = info['entries'][0]
            filename = ydl.prepare_filename(info)
            return info, filename

    info, filepath = await loop.run_in_executor(None, _extract)

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
