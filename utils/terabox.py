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

# Complete list of known Terabox domains and mirror networks
TERABOX_DOMAINS = [
    "terabox.com", "terabox.app", "teraboxapp.com", "1024tera.com", "1024terabox.com",
    "terasharelink.com", "terafileshare.com", "terasharefile.com", "terashareus.com",
    "terasharedrive.com", "teraboxlink.com", "teraboxlinke.com", "teraboxshare.com",
    "teraboxsharefile.com", "teraboxurl.com", "teraboxfree.com", "teraboxmod.app",
    "4funbox.com", "4funbox.co", "4funbox.in", "mirrobox.com", "nephobox.com",
    "freeterabox.com", "momerybox.com", "tibibox.com", "gibibox.com", "pebibox.com",
    "fancybox.in", "dubox.com", "bestclouddrive.com", "playduo.link", "dm.terabox.app",
    "dm.1024tera.com"
]

# In-memory cache for community fallback cookies
_COMMUNITY_COOKIE_CACHE = {"cookies": [], "expiry": 0}

def clean_url(url: str) -> str:
    """Clean trailing dots, ellipsis, spaces, or query noise from URL"""
    return re.sub(r'[\.…\s]+$', '', url).strip()

def is_terabox_link(url: str) -> bool:
    """Check if the provided link belongs to any Terabox domain or mirror"""
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
    
    # 1. Query parameter ?surl=... or ?shorturl=...
    surl = qs.get("surl", [""])[0] or qs.get("shorturl", [""])[0]
    
    # 2. Path parameter /s/<surl> or /share/<surl>
    if not surl:
        match = re.search(r'/(?:s|share)/([a-zA-Z0-9_\-]+)', parsed.path)
        if match:
            surl = match.group(1)
            
    # 3. Fallback to last path segment
    if not surl:
        surl = parsed.path.strip("/").split("/")[-1]
    
    return re.sub(r'[\.…\s]+$', '', surl).strip()

def get_candidate_surls(surl: str) -> list[str]:
    """Return candidates for shortcode (as-is, and with/without leading 1)"""
    candidates = [surl]
    if surl.startswith("1") and len(surl) > 1:
        candidates.append(surl[1:])
    else:
        candidates.append("1" + surl)
    return candidates

def format_terabox_cookie(cookie_raw: str) -> str:
    """Safely format and sanitize Terabox cookie string without exposing secrets"""
    if not cookie_raw:
        return ""
    cookie = cookie_raw.strip().strip("'\"").rstrip(".… ")
    if not cookie:
        return ""
    if "ndus=" in cookie:
        m = re.search(r'ndus=([^;]+)', cookie)
        ndus_val = m.group(1).strip() if m else cookie.replace("ndus=", "").strip()
    else:
        ndus_val = cookie
    ndus_val = ndus_val.strip().strip("'\"").rstrip(".… ")
    return f"ndus={ndus_val}; lang=en" if ndus_val else ""

def extract_js_token(html: str) -> str | None:
    """Multi-pattern jsToken extractor from desktop & mobile WAP HTML responses"""
    # Pattern 1: URL encoded fn%28%22...%22%29
    m = re.search(r'fn%28%22([A-Fa-f0-9]+)%22%29', html)
    if m:
        return m.group(1)
    
    # Pattern 2: eval decodeURIComponent
    m = re.search(r'eval\(decodeURIComponent\(`([^`]+)`\)\)', html)
    if m:
        try:
            decoded = urllib.parse.unquote(m.group(1))
            m2 = re.search(r'fn\("([A-Fa-f0-9]+)"\)', decoded)
            if m2:
                return m2.group(1)
        except Exception:
            pass

    # Pattern 3: direct jsToken property in JSON / script tag
    m = re.search(r'["\']?jsToken["\']?\s*[:=]\s*["\']([a-zA-Z0-9+/=_-]{16,})["\']', html)
    if m:
        return m.group(1)
        
    return None

async def get_community_fallback_cookies() -> list[str]:
    """Fetch active community cookies pool with a 5-minute local cache and 3s timeout"""
    now = time.time()
    if _COMMUNITY_COOKIE_CACHE["cookies"] and _COMMUNITY_COOKIE_CACHE["expiry"] > now:
        return _COMMUNITY_COOKIE_CACHE["cookies"]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://tera.backend.live/cookies-list", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if isinstance(data, list) and data:
                        clean_cookies = [c.strip().rstrip(";") for c in data if "ndus=" in c]
                        _COMMUNITY_COOKIE_CACHE["cookies"] = clean_cookies
                        _COMMUNITY_COOKIE_CACHE["expiry"] = now + 300
                        return clean_cookies
    except Exception as e:
        logger.debug(f"Could not fetch community cookies: {e}")
    return []

async def resolve_terabox_link(url: str) -> dict:
    """
    Resolve Terabox link to extract direct downloadable stream URL, filename, and size.
    Uses multi-strategy resolver:
      1. Desktop API with extracted jsToken (primary configured cookie)
      2. Mobile WAP __INITIAL_STATE__ extraction
      3. Community active cookie pool fallback
      4. Cloudflare Worker resolvers fallback
    Returns:
        dict: {"success": True, "direct_url": str, "filename": str, "size": int}
        OR
        dict: {"success": False, "reason": str, "code": str, "help_tip": str}
    """
    url = clean_url(url)
    surl = extract_terabox_surl(url)
    if not surl:
        return {
            "success": False,
            "code": "INVALID_URL",
            "reason": "URL से Terabox shortcode (surl) नहीं निकाला जा सका।",
            "help_tip": "कृपया सुनिश्चित करें कि लिंक सही फॉर्मेट में है।"
        }

    # Load cookie dynamically from DB (set via /cookie) or Config fallback
    cookie_raw = await db.get_terabox_cookie()
    cookie_str = format_terabox_cookie(cookie_raw)

    candidate_surls = get_candidate_surls(surl)
    last_errno = None

    # Base headers matching modern Chromium/Edge
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.terabox.app/"
    }
    if cookie_str:
        headers["Cookie"] = cookie_str

    # =========================================================================
    # Strategy 1: Desktop API with extracted jsToken
    # =========================================================================
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            for cand in candidate_surls:
                first_url = f"https://www.terabox.app/sharing/link?surl={cand}"
                js_token = None
                try:
                    async with session.get(first_url, timeout=aiohttp.ClientTimeout(total=5)) as r1:
                        if r1.status == 200:
                            text = await r1.text()
                            js_token = extract_js_token(text)
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
                    async with session.get(api_url, headers=api_headers, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            errno = data.get("errno")
                            if errno == 0 and data.get("list"):
                                file_item = data["list"][0]
                                dlink = file_item.get("dlink")
                                if dlink:
                                    logger.info(f"Resolved via Desktop API: {file_item.get('server_filename')}")
                                    return {
                                        "success": True,
                                        "direct_url": dlink,
                                        "filename": file_item.get("server_filename", "video.mp4"),
                                        "size": int(file_item.get("size", 0))
                                    }
                            elif errno is not None:
                                last_errno = errno
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
                    async with session.get(wap_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
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
                                            "success": True,
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
                                        async with session.get(dl_api, timeout=aiohttp.ClientTimeout(total=5)) as dl_resp:
                                            if dl_resp.status == 200:
                                                dl_data = await dl_resp.json()
                                                if dl_data.get("errno") == 0 and dl_data.get("dlink"):
                                                    return {
                                                        "success": True,
                                                        "direct_url": dl_data["dlink"],
                                                        "filename": f.get("server_filename", "video.mp4"),
                                                        "size": int(f.get("size", 0))
                                                    }
                except Exception as e:
                    logger.debug(f"WAP error for {cand}: {e}")
    except Exception as e:
        logger.debug(f"WAP resolution strategy failed: {e}")

    # =========================================================================
    # Strategy 3: Community Cookie Pool Fallback (When primary cookie missing/expired)
    # =========================================================================
    if last_errno in (105, None):
        community_cookies = await get_community_fallback_cookies()
        if community_cookies:
            logger.info("Testing community cookie pool fallback...")
            try:
                # Try up to 3 community cookies
                for c_cand in community_cookies[:3]:
                    c_hdr = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
                        "Accept": "application/json, text/plain, */*",
                        "Cookie": f"{c_cand}; lang=en",
                        "Referer": "https://www.terabox.app/"
                    }
                    async with aiohttp.ClientSession(headers=c_hdr) as session:
                        for cand in candidate_surls:
                            api_url = f"https://www.terabox.app/share/list?app_id=250528&shorturl={cand}&root=1"
                            try:
                                async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                                    if resp.status == 200:
                                        data = await resp.json()
                                        if data.get("errno") == 0 and data.get("list"):
                                            file_item = data["list"][0]
                                            if file_item.get("dlink"):
                                                logger.info(f"Resolved via Community Cookie: {file_item.get('server_filename')}")
                                                return {
                                                    "success": True,
                                                    "direct_url": file_item["dlink"],
                                                    "filename": file_item.get("server_filename", "video.mp4"),
                                                    "size": int(file_item.get("size", 0))
                                                }
                            except Exception:
                                pass
            except Exception as e:
                logger.debug(f"Community cookie fallback error: {e}")

    # =========================================================================
    # Strategy 4: Fast Cloudflare Worker Fallback Resolvers (Strict 4s timeout)
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
                                "success": True,
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
                                        "success": True,
                                        "direct_url": item["dlink"],
                                        "filename": item.get("name") or "video.mp4",
                                        "size": int(item.get("size", 0))
                                    }
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"Worker fallback error: {e}")

    # =========================================================================
    # Error classification and clear guidance
    # =========================================================================
    if last_errno == 105:
        return {
            "success": False,
            "code": "NEED_LOGIN",
            "reason": "यह Terabox फ़ाइल प्राइवेट है या Terabox सर्वर द्वारा लॉगिन प्रतिबंधित है।"
        }
    elif last_errno == 140:
        return {
            "success": False,
            "code": "NOT_FOUND",
            "reason": "यह फ़ाइल Terabox सर्वर पर मौजूद नहीं है, हटा दी गई है, या लिंक एक्सपायर हो चुका है।"
        }
    elif last_errno == 400210:
        return {
            "success": False,
            "code": "NEED_VERIFY",
            "reason": "Terabox सर्वर ने सुरक्षा सत्यापन (Cloudflare/Captcha Challenge) मांगा है।"
        }

    return {
        "success": False,
        "code": "UNKNOWN",
        "reason": "Terabox लिंक रिज़ॉल्व नहीं हो सका (सर्वर सुरक्षा प्रतिबंध या लिंक एक्सपायर हो सकता है)।"
    }

async def download_file_with_progress(url: str, dest_path: str, status_msg, start_time):
    """
    Download a remote stream/file to local disk with live progress updates.
    Validates that the file is not an HTML error response.
    """
    cookie_raw = await db.get_terabox_cookie()
    cookie_str = format_terabox_cookie(cookie_raw)

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
                raise Exception("Terabox server returned an HTML error page instead of video stream (link may be expired or protected).")

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
            raise Exception("File is corrupt or blocked (< 10 KB received). Link may be expired or inaccessible.")

    return dest_path
