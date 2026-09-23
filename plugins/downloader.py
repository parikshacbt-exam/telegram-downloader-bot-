import os
import re
import time
import logging
import urllib.parse
from pyrogram import Client, filters
from pyrogram.types import Message
from config import Config
from database import db
from utils.force_sub import is_subscribed, send_force_sub_message
from utils.progress import progress_for_pyrogram, humanbytes
from utils.terabox import is_terabox_link, resolve_terabox_link, download_file_with_progress

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".ts"]

def get_filename_from_url(url: str) -> str:
    """Extract clean filename from direct URL"""
    parsed = urllib.parse.urlparse(url)
    clean_path = urllib.parse.unquote(parsed.path)
    name = os.path.basename(clean_path)
    if not name or "." not in name:
        name = f"file_{int(time.time())}.mp4"
    return re.sub(r'[\\/*?:"<>|]', "_", name)

@Client.on_message(filters.regex(r"https?://[^\s]+") & filters.private)
async def link_downloader_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Check force subscription
    if not await is_subscribed(client, user_id):
        return await send_force_sub_message(client, message)

    match = re.search(r"https?://[^\s]+", message.text)
    if not match:
        return

    url = match.group(0)
    status_msg = await message.reply_text("🔍 **Analyzing your link...**", quote=True)
    start_time = time.time()

    direct_url = url
    filename = None
    filesize = 0

    # Handle Terabox URLs
    if is_terabox_link(url):
        await status_msg.edit_text("⚡ **Resolving Terabox link...** Please wait.")
        resolved = await resolve_terabox_link(url)
        if not resolved or not resolved.get("direct_url"):
            return await status_msg.edit_text(
                "❌ **Failed to resolve Terabox link.**\n\n"
                "The link might be expired, private, or temporarily unreachable. Please try again."
            )
        direct_url = resolved["direct_url"]
        filename = resolved.get("filename") or "terabox_video.mp4"
        filesize = resolved.get("size", 0)
    else:
        filename = get_filename_from_url(url)

    # Sanitize filename
    filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
    os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)
    temp_download_path = os.path.join(Config.DOWNLOAD_DIR, f"{user_id}_{int(time.time())}_{filename}")
    temp_thumb_path = None

    try:
        # Download the file locally with progress updates
        await status_msg.edit_text("📥 **Starting Download...**")
        await download_file_with_progress(direct_url, temp_download_path, status_msg, time.time())
        
        if not os.path.exists(temp_download_path):
            return await status_msg.edit_text("❌ Download failed. The file could not be retrieved.")

        actual_size = os.path.getsize(temp_download_path)
        if actual_size > Config.MAX_FILE_SIZE:
            return await status_msg.edit_text(
                f"❌ **File too large!**\n"
                f"File size is `{humanbytes(actual_size)}`. Telegram allows maximum 2 GB for bots."
            )

        # Retrieve user's custom thumbnail
        thumb_file_id = await db.get_thumbnail(user_id)
        if thumb_file_id:
            try:
                temp_thumb_path = await client.download_media(thumb_file_id)
            except Exception as e:
                logger.warning(f"Could not download custom thumb: {e}")
                temp_thumb_path = None

        # Build caption
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

        # Upload to Telegram with progress
        upload_start = time.time()
        file_ext = os.path.splitext(filename)[1].lower()

        if file_ext in VIDEO_EXTENSIONS:
            await status_msg.edit_text("📤 **Preparing video upload...**")
            await client.send_video(
                chat_id=message.chat.id,
                video=temp_download_path,
                caption=caption,
                thumb=temp_thumb_path,
                supports_streaming=True,
                reply_to_message_id=message.id,
                progress=progress_for_pyrogram,
                progress_args=("Uploading Video", status_msg, upload_start)
            )
        else:
            await status_msg.edit_text("📤 **Preparing file upload...**")
            await client.send_document(
                chat_id=message.chat.id,
                document=temp_download_path,
                caption=caption,
                thumb=temp_thumb_path,
                reply_to_message_id=message.id,
                progress=progress_for_pyrogram,
                progress_args=("Uploading Document", status_msg, upload_start)
            )

        # Delete status message on success
        try:
            await status_msg.delete()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Downloader error: {e}")
        try:
            await status_msg.edit_text(f"❌ **Error occurred:** `{e}`")
        except Exception:
            pass

    finally:
        # Cleanup temporary files
        if os.path.exists(temp_download_path):
            try:
                os.remove(temp_download_path)
            except Exception:
                pass
        if temp_thumb_path and os.path.exists(temp_thumb_path):
            try:
                os.remove(temp_thumb_path)
            except Exception:
                pass
