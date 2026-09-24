import os
import re
import time
import asyncio
import logging
import urllib.parse
from pyrogram import Client, filters
from pyrogram.types import Message
from config import Config
from database import db
from utils.force_sub import is_subscribed, send_force_sub_message
from utils.progress import progress_for_pyrogram, humanbytes
from utils.terabox import is_terabox_link, extract_terabox_surl, resolve_terabox_link, download_file_with_progress
from utils.ytdl import download_with_ytdl

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".ts", ".m4v"]
DIRECT_FILE_EXTENSIONS = [
    ".zip", ".rar", ".7z", ".tar", ".gz", ".iso", ".apk", ".exe", ".pdf",
    ".docx", ".xlsx", ".pptx", ".mp3", ".wav", ".flac", ".ogg", ".m4a"
]

def get_filename_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    clean_path = urllib.parse.unquote(parsed.path)
    name = os.path.basename(clean_path)
    if not name or "." not in name:
        name = f"file_{int(time.time())}.mp4"
    return re.sub(r'[\\/*?:"<>|]', "_", name)

def is_direct_file_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    clean_path = urllib.parse.unquote(parsed.path).lower()
    return any(clean_path.endswith(ext) for ext in (VIDEO_EXTENSIONS + DIRECT_FILE_EXTENSIONS))

def get_video_metadata(video_path: str):
    duration = 0
    width = 0
    height = 0
    try:
        from hachoir.parser import createParser
        from hachoir.metadata import extractMetadata
        parser = createParser(video_path)
        if parser:
            metadata = extractMetadata(parser)
            if metadata:
                if metadata.has("duration"):
                    duration = int(metadata.get("duration").seconds)
                if metadata.has("width"):
                    width = int(metadata.get("width"))
                if metadata.has("height"):
                    height = int(metadata.get("height"))
            parser.close()
    except Exception as e:
        logger.debug(f"Metadata extraction error: {e}")
    return duration, width, height

async def auto_delete_and_notify(client: Client, chat_id: int, video_message_id: int, delay: int = 1800):
    """Wait for 30 minutes, delete video, and send regulation notice without quoting/tagging"""
    await asyncio.sleep(delay)
    try:
        await client.delete_messages(chat_id, video_message_id)
    except Exception as e:
        logger.debug(f"Could not delete message {video_message_id}: {e}")

    try:
        await client.send_message(
            chat_id=chat_id,
            text="⚠️ **Telegram Regulations Notice:**\n\nयह वीडियो / फ़ाइल Telegram कम्युनिटी गाइडलाइन्स व कॉपीराइट नियमों के तहत 30 मिनट पूरे होने पर चैट से हटा दी गई है।"
        )
    except Exception as e:
        logger.debug(f"Could not send delete notice: {e}")

@Client.on_message(filters.regex(r"https?://[^\s]+") & filters.private)
async def link_downloader_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    if not await is_subscribed(client, user_id):
        return await send_force_sub_message(client, message)

    match = re.search(r"https?://[^\s]+", message.text)
    if not match:
        return

    url = match.group(0).strip()
    status_msg = await message.reply_text("🔍 **Analyzing your link...**", quote=True)
    
    temp_download_path = None
    temp_thumb_path = None
    download_dir = getattr(Config, "DOWNLOAD_DIR", "downloads")
    os.makedirs(download_dir, exist_ok=True)

    try:
        # ========================================================
        # PATHWAY 1: TERABOX LINKS
        # ========================================================
        if is_terabox_link(url):
            # Check if link was accidentally cut off by user
            if url.endswith("...") or url.endswith("…"):
                return await status_msg.edit_text(
                    "⚠️ **अधूरा Terabox लिंक (Incomplete Link)!**\n\n"
                    f"आपने जो लिंक भेजा है उसके अंत में `...` है:\n`{url}`\n\n"
                    "💡 **समाधान:** कृपया ब्राउज़र के एड्रेस बार से पूरा असली लिंक कॉपी करके यहाँ भेजें।"
                )

            await status_msg.edit_text("⚡ **Resolving Terabox link...** Please wait.")
            resolved = await resolve_terabox_link(url)

            if not resolved or not resolved.get("success") or not resolved.get("direct_url"):
                reason = resolved.get("reason", "लिंक रिज़ॉल्व नहीं हो सका।") if resolved else "लिंक रिज़ॉल्व नहीं हो सका।"
                help_tip = resolved.get("help_tip", "") if resolved else ""
                
                err_text = f"❌ **Terabox Link Resolve Error**\n\n**कारण:** {reason}"
                if help_tip:
                    err_text += f"\n\n{help_tip}"
                return await status_msg.edit_text(err_text)

            direct_url = resolved["direct_url"]
            filename = resolved.get("filename") or "video.mp4"
            filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
            temp_download_path = os.path.join(download_dir, f"{user_id}_{int(time.time())}_{filename}")

            await status_msg.edit_text("📥 **Starting High-Speed Download...**")
            await download_file_with_progress(direct_url, temp_download_path, status_msg, time.time())
            video_duration, video_width, video_height = get_video_metadata(temp_download_path)

        # ========================================================
        # PATHWAY 2: ALL OTHER VIDEOS & FILES (YouTube, Insta, Adult tube sites, direct files)
        # ========================================================
        else:
            await status_msg.edit_text("⚡ **Fetching video stream information...**")
            ytdl_success = False
            video_duration = 0
            video_width = 0
            video_height = 0

            # First try universal yt-dlp downloader (supports 1800+ sites)
            try:
                ytdl_res = await download_with_ytdl(url, download_dir, status_msg, time.time())
                temp_download_path = ytdl_res["filepath"]
                filename = os.path.basename(temp_download_path)
                video_duration = ytdl_res["duration"]
                video_width = ytdl_res["width"]
                video_height = ytdl_res["height"]
                ytdl_success = True
            except Exception as ytdl_err:
                logger.info(f"yt-dlp could not handle link ({ytdl_err})")

            # If yt-dlp could not handle it, check if it is a direct file link (.zip, .pdf, direct .mp4)
            if not ytdl_success:
                if is_direct_file_url(url):
                    filename = get_filename_from_url(url)
                    temp_download_path = os.path.join(download_dir, f"{user_id}_{int(time.time())}_{filename}")
                    await status_msg.edit_text("📥 **Starting Direct File Download...**")
                    await download_file_with_progress(url, temp_download_path, status_msg, time.time())
                    video_duration, video_width, video_height = get_video_metadata(temp_download_path)
                else:
                    return await status_msg.edit_text(
                        "❌ **इस लिंक से वीडियो या फ़ाइल डाउनलोड नहीं हो सकी!**\n\n"
                        "कृपया सुनिश्चित करें कि लिंक सही और सार्वजनिक (public) है।"
                    )

        # ========================================================
        # UPLOAD TO TELEGRAM
        # ========================================================
        if not temp_download_path or not os.path.exists(temp_download_path):
            return await status_msg.edit_text("❌ Download failed. The file could not be retrieved.")

        actual_size = os.path.getsize(temp_download_path)
        max_size = getattr(Config, "MAX_FILE_SIZE", 2 * 1024 * 1024 * 1024)
        if actual_size > max_size:
            return await status_msg.edit_text(
                f"❌ **File too large!**\n"
                f"File size is `{humanbytes(actual_size)}`. Telegram allows maximum 2 GB for bots."
            )

        thumb_file_id = await db.get_thumbnail(user_id)
        if thumb_file_id:
            try:
                temp_thumb_path = await client.download_media(thumb_file_id)
            except Exception:
                temp_thumb_path = None

        custom_caption = await db.get_caption(user_id)
        if custom_caption:
            caption = custom_caption.replace("{filename}", filename).replace("{filesize}", humanbytes(actual_size))
        else:
            bot_username = client.me.username if client.me and client.me.username else "FileDownloader"
            caption = (
                f"📁 **Filename:** `{filename}`\n"
                f"📦 **Size:** `{humanbytes(actual_size)}`\n\n"
                f"⚡ **Downloaded via @{bot_username}**"
            )

        upload_start = time.time()
        file_ext = os.path.splitext(filename)[1].lower()

        if file_ext in VIDEO_EXTENSIONS:
            await status_msg.edit_text("📤 **Preparing high-speed video stream upload...**")
            sent_media = await client.send_video(
                chat_id=message.chat.id,
                video=temp_download_path,
                caption=caption,
                thumb=temp_thumb_path,
                duration=video_duration,
                width=video_width,
                height=video_height,
                supports_streaming=True,
                reply_to_message_id=message.id,
                progress=progress_for_pyrogram,
                progress_args=("Uploading Video", status_msg, upload_start)
            )
        else:
            await status_msg.edit_text("📤 **Preparing high-speed file upload...**")
            sent_media = await client.send_document(
                chat_id=message.chat.id,
                document=temp_download_path,
                caption=caption,
                thumb=temp_thumb_path,
                reply_to_message_id=message.id,
                progress=progress_for_pyrogram,
                progress_args=("Uploading Document", status_msg, upload_start)
            )

        try:
            await status_msg.delete()
        except Exception:
            pass

        # 30-minute auto-delete: Clean deletion with untagged regulations notice
        asyncio.create_task(auto_delete_and_notify(client, message.chat.id, sent_media.id, delay=1800))

    except Exception as e:
        logger.error(f"Downloader error: {e}")
        try:
            await status_msg.edit_text(f"❌ **Error:** `{e}`")
        except Exception:
            pass

    finally:
        if temp_download_path and os.path.exists(temp_download_path):
            try:
                os.remove(temp_download_path)
            except Exception:
                pass
        if temp_thumb_path and os.path.exists(temp_thumb_path):
            try:
                os.remove(temp_thumb_path)
            except Exception:
                pass
