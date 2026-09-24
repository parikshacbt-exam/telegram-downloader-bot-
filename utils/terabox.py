import os
import re
import time
import json
import asyncio
import logging
import urllib.parse
import aiohttp
import aiofiles
from config import Config
from database import db
from utils.progress import progress_for_pyrogram

logger = logging.getLogger(__name__)

TERABOX_DOMAINS = [
    "terabox.com", "teraboxapp.com", "1024tera.com", "teraboxshare.com",
    "4funbox.com", "mirrobox.com", "nephobox.com", "freeterabox.com",
    "1024terabox.com", "terasharelink.com", "terabox.app", "teraboxlink.com",
    "dm.terabox.app", "terafileshare.com", "terasharefile.com"
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
    """Extract clean surl shortcode from Terabox URL without destroying leading 1"""
    url = clean_url(url)
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    surl = qs.get("surl", [""])[0]
    if not surl and "/s/" in parsed.path:
        surl = parsed.path.split("/s/")[1].split("/")[0].split("?")[0]
    elif not surl and ("sharing/link" in parsed.path or "filelist" in parsed.path) and "surl=" in parsed.query:
        surl = qs.get("surl", [""])[0]
    elif not surl:
        surl = parsed.path.strip("/").split("/")[-1]
    
    surl = re.sub(r'[\.…\s]+$', '', surl).strip()
    return surl

def get_candidate_surls(surl: str) -> list[str]:
    """Return candidates for shortcode (as-is, and with/without leading 1)"""
    candidates = [surl]
    if surl.startswith("1") and len(surl) > 1:
        candidates.append(surl[1:])
    else:
        candidates.append("1" + surl)
    return candidates

async def resolve_terabox_link(url: str):
    """
    Resolve Terabox link to extract direct downloadable stream URL, filename, and size.
    Uses multi-strategy resolution:
    1. Native Terabox Desktop API with jsToken + Cookie
    2. Mobile WAP __INITIAL_STATE__ extraction
    3. Fast Worker Fallback Resolvers (4s timeout)
    """
    url = clean_url(url)
    surl = extract_terabox_surl(url)
    if not surl:
        logger.warning(f"Could not extract surl from: {url}")
        return None

    # Load cookie dynamically from DB (set via /cookie) or Config fallback
    cookie_raw = await db.get_terabox_cookie()
    cookie_str = cookie_raw.strip().strip("'\"").rstrip(".… ")
    if cookie_str and "ndus=" not in cookie_str:
        cookie_str = f"ndus={cookie_str}"
    if cookie_str and "lang=" not in cookie_str:
        cookie_str = f"lang=en; {cookie_str}"

    candidate_surls = get_candidate_surls(surl)

    # =========================================================================
    # Strategy 1: Native Desktop API with extracted jsToken (Best & Most Stable)
    # =========================================================================
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
            for cand in candidate_surls:
                first_url = f"https://www.terabox.app/sharing/link?surl={cand}"
                js_token = None
                try:
                    async with session.get(first_url, timeout=aiohttp.ClientTimeout(total=6)) as r1:
                        if r1.status == 200:
                            text = await r1.text()
                            m = re.search(r'fn%28%22(.*?)%22%29', text)
                            if m:
                                js_token = m.group(1)
                except Exception as e:
                    logger.debug(f"First request error for {cand}: {e}")

                api_url = f"https://www.terabox.app/share/list?app_id=250528&shorturl={cand}&root=1"
                if js_token:
                    api_url += f"&jsToken={js_token}"

                api_headers = dict(headers)
                api_headers.update({
                    "Accept": "application/json, text/plain, */*",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": first_url
                })

                try:
                    async with session.get(api_url, headers=api_headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("errno") == 0 and data.get("list"):
                                file_item = data["list"][0]
                                dlink = file_item.get("dlink")
                                if dlink:
                                    logger.info(f"Resolved via Desktop API: {file_item.get('server_filename')}")
                                    return {
                                        "direct_url": dlink,
                                        "filename": file_item.get("server_filename", "video.mp4"),
                                        "size": int(file_item.get("size", 0))
                                    }
                except Exception as e:
                    logger.debug(f"Share list API error for {cand}: {e}")
    except Exception as e:
        logger.debug(f"Native Desktop Strategy error: {e}")

    # =========================================================================
    # Strategy 2: Mobile WAP __INITIAL_STATE__ Extraction
    # =========================================================================
    try:
        wap_headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.terabox.app/"
        }
        if cookie_str:
            wap_headers["Cookie"] = cookie_str

        async with aiohttp.ClientSession(headers=wap_headers) as session:
            for cand in candidate_surls:
                wap_url = f"https://www.terabox.app/wap/share/filelist?surl={cand}"
                try:
                    async with session.get(wap_url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                        if resp.status == 200:
                            html = await resp.text()
                            m = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', html, re.DOTALL)
                            if m:
                                state = json.loads(m.group(1))
                                share_data = state.get("share", {})
                                file_list = share_data.get("fileList", [])
                                if file_list:
                                    f = file_list[0]
                                    dlink = f.get("dlink")
                                    if dlink:
                                        logger.info(f"Resolved via WAP state: {f.get('server_filename')}")
                                        return {
                                            "direct_url": dlink,
                                            "filename": f.get("server_filename", "video.mp4"),
                                            "size": int(f.get("size", 0))
                                        }

                                    fs_id = f.get("fs_id")
                                    js_token = state.get("jsToken")
                                    share_info = share_data.get("shareInfo", {})
                                    shareid = share_info.get("shareid")
                                    uk = share_info.get("uk")
                                    sign = share_info.get("sign")
                                    timestamp = share_info.get("timestamp")

                                    if fs_id and js_token and shareid and sign and timestamp:
                                        dl_api = (
                                            f"https://www.terabox.app/share/download?app_id=250528&web=1&channel=dubox"
                                            f"&clienttype=0&jsToken={js_token}&shareid={shareid}&sign={sign}"
                                            f"&timestamp={timestamp}&primaryid={shareid}&uk={uk}&product=share"
                                            f"&nozip=0&fid_list=[{fs_id}]"
                                        )
                                        async with session.get(dl_api, timeout=aiohttp.ClientTimeout(total=6)) as dl_resp:
                                            if dl_resp.status == 200:
                                                dl_data = await dl_resp.json()
                                                if dl_data.get("errno") == 0 and dl_data.get("dlink"):
                                                    return {
                                                        "direct_url": dl_data["dlink"],
                                                        "filename": f.get("server_filename", "video.mp4"),
                                                        "size": int(f.get("size", 0))
                                                    }
                except Exception as e:
                    logger.debug(f"WAP error for {cand}: {e}")
    except Exception as e:
        logger.debug(f"WAP resolution strategy failed: {e}")

    # =========================================================================
    # Strategy 3: Fast Worker Fallback Resolvers (Strict 4s timeout)
    # =========================================================================
    worker_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    try:
        async with aiohttp.ClientSession(headers=worker_headers) as session:
            # Check mn-bots worker
            try:
                mn_url = f"https://terabox-api.mn-bots.workers.dev/download?url={urllib.parse.quote(url)}"
                async with session.get(mn_url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("success") and (data.get("download_link") or data.get("direct_download_url")):
                            dlink = data.get("download_link") or data.get("direct_download_url")
                            return {
                                "direct_url": dlink,
                                "filename": data.get("filename") or "video.mp4",
                                "size": int(data.get("size", 0))
                            }
            except Exception:
                pass

            # Check tbx-proxy worker
            for cand in candidate_surls:
                try:
                    tbx_url = f"https://tbx-proxy.shakir-ansarii075.workers.dev/?mode=resolve&surl={cand}"
                    async with session.get(tbx_url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if isinstance(data, dict) and data.get("data"):
                                item = data["data"]
                                if item.get("dlink"):
                                    return {
                                        "direct_url": item["dlink"],
                                        "filename": item.get("name") or "video.mp4",
                                        "size": int(item.get("size", 0))
                                    }
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"Worker fallback error: {e}")

    return None

async def download_file_with_progress(url: str, dest_path: str, status_msg, start_time):
    """
    Download a remote stream/file to local disk with live progress updates.
    Validates that the file is not an HTML error response.
    """
    cookie_raw = await db.get_terabox_cookie()
    cookie_str = cookie_raw.strip().strip("'\"").rstrip(".… ")
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
                raise Exception("Server returned a web/HTML page instead of video stream. Authentication or fresh cookie might be required.")

            total_size = int(response.headers.get("content-length", 0))
            max_size = getattr(Config, "MAX_FILE_SIZE", 2 * 1024 * 1024 * 1024)
            if total_size > max_size:
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
        if actual_size < 10 * 1024:
            os.remove(dest_path)
            raise Exception("File is corrupt or blocked (< 10 KB received). Please check your TERABOX_COOKIE.")

    return dest_path
