import os
import re
import time
import logging
import urllib.parse
import aiohttp
import aiofiles
from config import Config
from utils.progress import progress_for_pyrogram

logger = logging.getLogger(__name__)

TERABOX_DOMAINS = [
    "terabox.com", "teraboxapp.com", "1024tera.com", "teraboxshare.com",
    "4funbox.com", "mirrobox.com", "nephobox.com", "freeterabox.com",
    "1024terabox.com", "terasharelink.com"
]

def is_terabox_link(url: str) -> bool:
    """Check if the provided link is a Terabox domain link"""
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()
    return any(d in domain for d in TERABOX_DOMAINS)

def is_diskwala_link(url: str) -> bool:
    """Check if the provided link is Diskwala"""
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()
    return "diskwala" in domain

async def resolve_terabox_link(url: str):
    """
    Resolve Terabox link to extract direct downloadable stream URL, filename, and size.
    Uses API resolver with robust fallbacks.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # Try configured API endpoint
    api_url = Config.TERABOX_API_URL
    params = {"url": url}
    
    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            async with session.get(api_url, params=params, timeout=aiohttp.ClientTimeout(total=25)) as response:
                if response.status == 200:
                    data = await response.json()
                    # Handle common API response schemas
                    # Schema 1: {"download_url": ..., "file_name": ..., "size": ...}
                    # Schema 2: {"status": "success", "result": [{"url": ..., "title": ...}]}
                    if isinstance(data, dict):
                        if "download_url" in data:
                            return {
                                "direct_url": data["download_url"],
                                "filename": data.get("file_name", "video.mp4"),
                                "size": data.get("size", 0)
                            }
                        elif "response" in data and isinstance(data["response"], list) and len(data["response"]) > 0:
                            item = data["response"][0]
                            return {
                                "direct_url": item.get("resolutions", {}).get("Fast Download") or item.get("download_link"),
                                "filename": item.get("title", "video.mp4"),
                                "size": item.get("size", 0)
                            }
                        elif "url" in data:
                            return {
                                "direct_url": data["url"],
                                "filename": data.get("filename", data.get("title", "downloaded_file.mp4")),
                                "size": data.get("size", 0)
                            }
        except Exception as e:
            logger.warning(f"Resolver {api_url} failed: {e}")

        # Secondary fallback public resolver
        fallback_api = f"https://terabox-dl.qtcloud.workers.dev/api/get-info?shorturl={url.split('/')[-1]}"
        try:
            async with session.get(fallback_api, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "download_link" in data:
                        return {
                            "direct_url": data["download_link"],
                            "filename": data.get("filename", "video.mp4"),
                            "size": data.get("size", 0)
                        }
        except Exception as e:
            logger.warning(f"Fallback resolver failed: {e}")

    return None

async def download_file_with_progress(url: str, dest_path: str, status_msg, start_time):
    """
    Download a remote stream/file to local disk with live progress updates.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=3600)) as response:
            if response.status != 200:
                raise Exception(f"HTTP Error {response.status} while downloading file.")

            total_size = int(response.headers.get("content-length", 0))
            if total_size > Config.MAX_FILE_SIZE:
                raise Exception(f"File size ({total_size} bytes) exceeds Telegram's 2 GB limit.")

            downloaded = 0
            chunk_size = 1024 * 512  # 512 KB chunks

            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            async with aiofiles.open(dest_path, "wb") as f:
                async for chunk in response.content.iter_chunked(chunk_size):
                    await f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        await progress_for_pyrogram(
                            downloaded,
                            total_size,
                            "Downloading File",
                            status_msg,
                            start_time
                        )

    return dest_path
