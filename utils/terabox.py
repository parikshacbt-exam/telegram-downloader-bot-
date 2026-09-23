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
    "1024terabox.com", "terasharelink.com", "terabox.app", "teraboxlink.com"
]

def is_terabox_link(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()
    return any(d in domain for d in TERABOX_DOMAINS)

def is_diskwala_link(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()
    return "diskwala" in domain

def extract_terabox_surl(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    surl = qs.get("surl", [""])[0]
    if not surl and "/s/" in parsed.path:
        surl = parsed.path.split("/s/")[1].split("/")[0].split("?")[0]
    elif not surl and "/sharing/link" in parsed.path and "surl=" in parsed.query:
        surl = qs.get("surl", [""])[0]
    elif not surl:
        surl = parsed.path.strip("/").split("/")[-1]
    
    if surl.startswith("1"):
        surl = surl[1:]
    return surl.strip()

async def resolve_terabox_link(url: str):
    surl = extract_terabox_surl(url)
    if not surl:
        return None

    cookie_str = Config.TERABOX_COOKIE.strip()
    if cookie_str and "ndus=" not in cookie_str:
        cookie_str = f"ndus={cookie_str}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.terabox.app/"
    }
    if cookie_str:
        headers["Cookie"] = cookie_str

    async with aiohttp.ClientSession(headers=headers) as session:
        if cookie_str:
            api_url = f"https://www.terabox.app/share/list?app_id=250528&shorturl={surl}&root=1"
            try:
                async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("errno") == 0 and data.get("list"):
                            file_item = data["list"][0]
                            dlink = file_item.get("dlink")
                            if dlink:
                                return {
                                    "direct_url": dlink,
                                    "filename": file_item.get("server_filename", "video.mp4"),
                                    "size": int(file_item.get("size", 0))
                                }
            except Exception as e:
                logger.warning(f"Terabox official API failed: {e}")

        worker_urls = [
            f"https://tbx-proxy.shakir-ansarii075.workers.dev/?mode=resolve&surl={surl}&raw=1",
            f"https://terabox-dl.qtcloud.workers.dev/api/get-info?shorturl={surl}"
        ]

        for w_url in worker_urls:
            try:
                async with session.get(w_url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, dict):
                            if "list" in data and len(data["list"]) > 0:
                                f = data["list"][0]
                                if f.get("dlink"):
                                    return {
                                        "direct_url": f["dlink"],
                                        "filename": f.get("server_filename", "video.mp4"),
                                        "size": int(f.get("size", 0))
                                    }
                            elif "download_link" in data:
                                return {
                                    "direct_url": data["download_link"],
                                    "filename": data.get("filename", "video.mp4"),
                                    "size": int(data.get("size", 0))
                                }
                            elif "download_url" in data:
                                return {
                                    "direct_url": data["download_url"],
                                    "filename": data.get("file_name", "video.mp4"),
                                    "size": int(data.get("size", 0))
                                }
            except Exception:
                pass

    return None

async def download_file_with_progress(url: str, dest_path: str, status_msg, start_time):
    cookie_str = Config.TERABOX_COOKIE.strip()
    if cookie_str and "ndus=" not in cookie_str:
        cookie_str = f"ndus={cookie_str}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.terabox.app/"
    }
    if cookie_str:
        headers["Cookie"] = cookie_str

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=3600)) as response:
            if response.status != 200:
                raise Exception(f"HTTP Error {response.status} while downloading file.")

            content_type = response.headers.get("content-type", "").lower()
            if "text/html" in content_type:
                raise Exception("Terabox returned an HTML error/login page. Please configure your TERABOX_COOKIE.")

            total_size = int(response.headers.get("content-length", 0))
            if total_size > Config.MAX_FILE_SIZE:
                raise Exception(f"File size exceeds Telegram's 2 GB limit.")

            downloaded = 0
            chunk_size = 1024 * 1024

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

    if os.path.exists(dest_path):
        actual_size = os.path.getsize(dest_path)
        if actual_size < 50 * 1024:
            os.remove(dest_path)
            raise Exception("Terabox blocked the download (Login required). Please add your TERABOX_COOKIE in Render Environment Variables.")

    return dest_path
