import os
import re
import time
import asyncio
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
    "1024terabox.com", "terasharelink.com", "terabox.app", "teraboxlink.com",
    "dm.terabox.app", "terafileshare.com"
]

def clean_url(url: str) -> str:
    """Clean trailing dots, ellipsis, spaces, or query noise from URL"""
    return re.sub(r'[\.…\s]+$', '', url).strip()

def is_terabox_link(url: str) -> bool:
    """Check if the provided link is a Terabox domain link"""
    clean = clean_url(url)
    try:
        parsed = urllib.parse.urlparse(clean)
        domain = parsed.netloc.lower()
        return any(d in domain for d in TERABOX_DOMAINS)
    except Exception:
        return False

def extract_terabox_surl(url: str) -> str:
    """Extract clean surl shortcode from Terabox URL"""
    url = clean_url(url)
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    surl = qs.get("surl", [""])[0]
    if not surl and "/s/" in parsed.path:
        surl = parsed.path.split("/s/")[1].split("/")[0].split("?")[0]
    elif not surl and "/sharing/link" in parsed.path and "surl=" in parsed.query:
        surl = qs.get("surl", [""])[0]
    elif not surl:
        surl = parsed.path.strip("/").split("/")[-1]
    
    surl = re.sub(r'[\.…\s]+$', '', surl).strip()
    
    if surl.startswith("1"):
        surl = surl[1:]
    return surl.strip()

async def resolve_terabox_link(url: str):
    """
    Resolve Terabox link to extract direct downloadable stream URL, filename, and size.
    Uses:
    1. TeraboxDL Python library with TERABOX_COOKIE.
    2. Native Terabox jsToken extraction + share/list API.
    3. Fast third-party worker fallbacks with 5-second max timeout.
    """
    url = clean_url(url)
    surl = extract_terabox_surl(url)
    if not surl:
        logger.warning(f"Could not extract surl from: {url}")
        return None

    cookie_raw = Config.TERABOX_COOKIE.strip()
    cookie_str = cookie_raw
    if cookie_str and "ndus=" not in cookie_str:
        cookie_str = f"ndus={cookie_str}"
    if cookie_str and "lang=" not in cookie_str:
        cookie_str = f"lang=en; {cookie_str}"

    # Strategy 1: Use TeraboxDL library if installed and cookie configured
    if cookie_str:
        try:
            from TeraboxDL import TeraboxDL
            target_url = f"https://www.terabox.app/sharing/link?surl={surl}"
            def _call_teraboxdl():
                try:
                    tb = TeraboxDL(cookie=cookie_str)
                    return tb.get_file_info(target_url)
                except Exception as ex:
                    logger.debug(f"TeraboxDL internal error: {ex}")
                    return None

            info = await asyncio.to_thread(_call_teraboxdl)
            if info and isinstance(info, dict) and info.get("download_link") and not info.get("error"):
                logger.info(f"Resolved via TeraboxDL: {info.get('file_name')}")
                return {
                    "direct_url": info["download_link"],
                    "filename": info.get("file_name", "video.mp4"),
                    "size": int(info.get("size_bytes", 0))
                }
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"TeraboxDL strategy failed: {e}")

    # Strategy 2: Native aiohttp with jsToken extraction
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.terabox.app/"
    }
    if cookie_str:
        headers["Cookie"] = cookie_str

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            first_url = f"https://www.terabox.app/sharing/link?surl={surl}"
            js_token = None
            try:
                async with session.get(first_url, timeout=aiohttp.ClientTimeout(total=8)) as r1:
                    if r1.status == 200:
                        text = await r1.text()
                        m = re.search(r'fn%28%22(.*?)%22%29', text)
                        if m:
                            js_token = m.group(1)
            except Exception as e:
                logger.debug(f"Error getting jsToken: {e}")

            api_url = f"https://www.terabox.app/share/list?app_id=250528&shorturl={surl}&root=1"
            if js_token:
                api_url += f"&jsToken={js_token}"

            api_headers = dict(headers)
            api_headers.update({
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest",
            })

            async with session.get(api_url, headers=api_headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("errno") == 0 and data.get("list"):
                        file_item = data["list"][0]
                        dlink = file_item.get("dlink")
                        if dlink:
                            logger.info(f"Resolved via Terabox API: {file_item.get('server_filename')}")
                            return {
                                "direct_url": dlink,
                                "filename": file_item.get("server_filename", "video.mp4"),
                                "size": int(file_item.get("size", 0))
                            }
    except Exception as e:
        logger.debug(f"Native Terabox API error: {e}")

    # Strategy 3: Fast fallback public resolver (5s timeout)
    try:
        fallback_url = f"https://terabox-dl.qtcloud.workers.dev/api/get-info?shorturl={surl}"
        async with aiohttp.ClientSession() as session:
            async with session.get(fallback_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if isinstance(data, dict):
                        dlink = data.get("download_link") or data.get("download_url")
                        if not dlink and data.get("list"):
                            dlink = data["list"][0].get("dlink")
                        if dlink:
                            return {
                                "direct_url": dlink,
                                "filename": data.get("file_name") or data.get("filename") or "video.mp4",
                                "size": int(data.get("size", 0))
                            }
    except Exception:
        pass

    return None

async def download_file_with_progress(url: str, dest_path: str, status_msg, start_time):
    """
    Download a remote stream/file to local disk with live progress updates.
    Validates that the file is not a tiny 100-byte error response!
    """
    cookie_str = Config.TERABOX_COOKIE.strip()
    if cookie_str and "ndus=" not in cookie_str:
        cookie_str = f"ndus={cookie_str}"
    if cookie_str and "lang=" not in cookie_str:
        cookie_str = f"lang=en; {cookie_str}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        "Referer": "https://www.terabox.app/",
        "Accept": "*/*"
    }
    if cookie_str:
        headers["Cookie"] = cookie_str

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=3600)) as response:
            if response.status != 200:
                raise Exception(f"HTTP Error {response.status} while downloading file.")

            content_type = response.headers.get("content-type", "").lower()
            if "text/html" in content_type:
                raise Exception("Server returned a web/HTML page instead of video stream. Login/Cookie might be required.")

            total_size = int(response.headers.get("content-length", 0))
            if total_size > Config.MAX_FILE_SIZE:
                raise Exception("File size exceeds Telegram's 2 GB limit.")

            downloaded = 0
            chunk_size = 1024 * 1024  # 1 MB chunks

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
            raise Exception("File is corrupt or blocked (< 50 KB received). Please verify your TERABOX_COOKIE.")

    return dest_path
