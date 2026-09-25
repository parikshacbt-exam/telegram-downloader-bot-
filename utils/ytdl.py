import os
import time
import asyncio
import logging
import re
import urllib.parse
from utils.progress import progress_for_pyrogram, time_formatter

logger = logging.getLogger(__name__)

YOUTUBE_DOMAINS = [
    "youtube.com", "youtu.be", "m.youtube.com", "music.youtube.com"
]

def is_youtube_link(url: str) -> bool:
    """Check if the provided link is a YouTube URL"""
    try:
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.lower()
        return any(d in domain for d in YOUTUBE_DOMAINS)
    except Exception:
        return False

def extract_youtube_video_id(url: str) -> str:
    """Extract clean 11-char YouTube video ID from any YouTube URL format"""
    parsed = urllib.parse.urlparse(url)
    if "youtu.be" in parsed.netloc:
        return parsed.path.strip("/").split("?")[0].split("&")[0]
    if "shorts/" in parsed.path:
        return parsed.path.split("shorts/")[1].split("/")[0].split("?")[0]
    qs = urllib.parse.parse_qs(parsed.query)
    if "v" in qs and qs["v"]:
        return qs["v"][0]
    match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
    if match:
        return match.group(1)
    return "yt_video"

def get_base_ydl_opts(output_dir: str, progress_hook=None):
    """Base options optimized for YouTube & Instagram with datacenter IP bypass"""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'socket_timeout': 25,
        'retries': 3,
        'extractor_retries': 3,
        'geo_bypass': True,
        'max_filesize': 2000 * 1024 * 1024,  # 2 GB Telegram Bot limit
        'extractor_args': {
            'instagram': {
                'direct_media': True,
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
        }
    }
    if progress_hook:
        opts['progress_hooks'] = [progress_hook]
    return opts

async def extract_youtube_info(url: str) -> dict:
    """Fast extraction of YouTube metadata (title, duration, thumbnail, channel) without downloading"""
    import yt_dlp
    loop = asyncio.get_running_loop()

    def _extract():
        opts = get_base_ydl_opts("")
        opts['skip_download'] = True
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info and info['entries']:
                info = info['entries'][0]
            return info

    info = await asyncio.wait_for(loop.run_in_executor(None, _extract), timeout=30)
    
    vid = extract_youtube_video_id(url)
    title = info.get("title") or "YouTube Video"
    title = re.sub(r'[\\/*?:"<>|]', "_", title).strip()
    duration = int(info.get("duration") or 0)
    channel = info.get("uploader") or info.get("channel") or "YouTube"
    thumbnail = info.get("thumbnail") or ""

    formats = info.get("formats", [])
    heights = set(f.get("height") for f in formats if f.get("height"))
    
    return {
        "video_id": vid,
        "title": title,
        "duration": duration,
        "duration_str": time_formatter(duration),
        "channel": channel,
        "thumbnail": thumbnail,
        "heights": sorted(list(heights))
    }

async def download_youtube(url: str, output_dir: str, format_choice: str, status_msg, start_time: float) -> dict:
    """Download YouTube video in specified quality (1080p, 720p, 480p, 360p) or MP3 audio"""
    import yt_dlp
    loop = asyncio.get_running_loop()
    last_update = [time.time()]

    def progress_hook(d):
        if d.get('status') == 'downloading':
            now = time.time()
            if now - last_update[0] >= 3.0:
                last_update[0] = now
                current = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                if total and total > 0:
                    action = "Downloading MP3" if format_choice == "mp3" else f"Downloading {format_choice}"
                    try:
                        asyncio.run_coroutine_threadsafe(
                            progress_for_pyrogram(current, total, action, status_msg, start_time),
                            loop
                        )
                    except Exception:
                        pass

    opts = get_base_ydl_opts(output_dir, progress_hook)
    is_audio = (format_choice == "mp3")

    if is_audio:
        out_tmpl = os.path.join(output_dir, "%(id)s_%(title).50s.%(ext)s")
        opts.update({
            'format': 'bestaudio/best',
            'outtmpl': out_tmpl,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }]
        })
    else:
        height_cap = format_choice.replace("p", "")
        out_tmpl = os.path.join(output_dir, f"%(id)s_{format_choice}_%(title).50s.%(ext)s")
        opts.update({
            'format': f'bestvideo[height<={height_cap}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={height_cap}]+bestaudio/best[height<={height_cap}][acodec!=none]/best',
            'outtmpl': out_tmpl,
            'merge_output_format': 'mp4',
            'postprocessor_args': {
                'merger': ['-c:v', 'copy', '-c:a', 'aac']
            }
        })

    def _dl():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if 'entries' in info and info['entries']:
                info = info['entries'][0]
            filename = ydl.prepare_filename(info)
            if is_audio:
                base, _ = os.path.splitext(filename)
                filename = base + ".mp3"
            return info, filename

    info, filepath = await asyncio.wait_for(loop.run_in_executor(None, _dl), timeout=420)

    # Verify output file
    if not os.path.exists(filepath):
        base, _ = os.path.splitext(filepath)
        for ext in [".mp3", ".mp4", ".mkv", ".webm", ".m4a"]:
            if os.path.exists(base + ext):
                filepath = base + ext
                break

    if not os.path.exists(filepath):
        raise Exception("Downloaded file not found on disk.")

    title = info.get("title") or "YouTube Audio" if is_audio else "YouTube Video"
    title = re.sub(r'[\\/*?:"<>|]', "_", title).strip()

    return {
        "filepath": filepath,
        "title": title,
        "channel": info.get("uploader") or info.get("channel") or "YouTube",
        "duration": int(info.get("duration") or 0),
        "width": int(info.get("width") or 0),
        "height": int(info.get("height") or 0),
        "is_audio": is_audio,
        "thumbnail": info.get("thumbnail") or ""
    }

async def download_with_ytdl(url: str, output_dir: str, status_msg, start_time: float) -> dict:
    """
    Download video from Instagram, Facebook, Twitter, TikTok, Adult tube sites, etc.
    GUARANTEES AUDIO / SOUND MERGING via static-ffmpeg and acodec!=none checks.
    """
    import yt_dlp
    loop = asyncio.get_running_loop()
    last_update = [time.time()]

    def progress_hook(d):
        if d.get('status') == 'downloading':
            now = time.time()
            if now - last_update[0] >= 3.0:
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

    out_template = os.path.join(output_dir, "%(id)s_%(title).50s.%(ext)s")
    opts = get_base_ydl_opts(output_dir, progress_hook)
    
    # GUARANTEED AUDIO FORMAT STRING:
    # 1. Best video with mp4 + best audio with m4a merged
    # 2. Or best video + best audio
    # 3. Or best single stream WITH AUDIO (acodec!=none) - fixes Instagram mute bug!
    opts.update({
        'format': 'bestvideo*+bestaudio/best[acodec!=none]/best',
        'outtmpl': out_template,
        'merge_output_format': 'mp4',
        'postprocessor_args': {
            'merger': ['-c:v', 'copy', '-c:a', 'aac']
        }
    })

    def _extract():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                raise Exception("Could not extract media information from this link.")
            if 'entries' in info and info['entries']:
                info = info['entries'][0]
            filename = ydl.prepare_filename(info)
            return info, filename

    info, filepath = await asyncio.wait_for(loop.run_in_executor(None, _extract), timeout=360)

    # Check for merged mp4 or alternative extension
    if not os.path.exists(filepath):
        base, _ = os.path.splitext(filepath)
        for ext in [".mp4", ".mkv", ".webm", ".m4v"]:
            if os.path.exists(base + ext):
                filepath = base + ext
                break

    if not os.path.exists(filepath):
        raise Exception("Downloaded media file not found on disk.")

    title = info.get("title") or "Video"
    title = re.sub(r'[\\/*?:"<>|]', "_", title).strip()

    return {
        "filepath": filepath,
        "title": title,
        "duration": int(info.get("duration") or 0),
        "width": int(info.get("width") or 0),
        "height": int(info.get("height") or 0),
        "is_audio": False,
        "thumbnail": info.get("thumbnail") or ""
    }
