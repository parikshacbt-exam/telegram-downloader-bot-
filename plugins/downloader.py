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
from utils.terabox import is_terabox_link, resolve_terabox_link, download_file_with_progress

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".ts", ".m4v"]

def get_filename_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    clean_path = urllib.parse.unquote(parsed.path)
    name = os.path.basename(clean_path)
    if not name or "." not in name:
        name = f"video_{int(time.time())}.mp4"
    return re.sub(r'[\\/*?:"<>|]', "_", name)

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

    url = match.group(0)
    status_msg = await message.reply_text("🔍 **Analyzing your link...**", quote=True)

    direct_url = url
    filename = None

    if is_terabox_link(url):
        await status_msg.edit_text("⚡ **Resolving Terabox link...** Please wait.")
        resolved = await resolve_terabox_link(url)
        if not resolved or not resolved.get("direct_url"):
            return await status_msg.edit_text(
                "❌ **Failed to resolve Terabox link.**\n\n"
                "Terabox is blocking anonymous access for this link.\n"
                "Please configure your **TERABOX_COOKIE** in Render Environment Variables to enable permanent full-speed 1GB+ downloads without login!"
            )
        direct_url = resolved["direct_url"]
        filename = resolved.get("filename") or "video.mp4"
    else:
        filename = get_filename_from_url(url)

    filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
    os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)
    temp_download_path = os.path.join(Config.DOWNLOAD_DIR, f"{user_id}_{int(time.time())}_{filename}")
    temp_thumb_path = None

    try:
        await status_msg.edit_text("📥 **Starting High-Speed Download...**")
        await download_file_with_progress(direct_url, temp_download_path, status_msg, time.time())
        
        if not os.path.exists(temp_download_path):
            return await status_msg.edit_text("❌ Download failed. The file could not be retrieved.")

        actual_size = os.path.getsize(temp_download_path)
        if actual_size > Config.MAX_FILE_SIZE:
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
        duration, width, height = get_video_metadata(temp_download_path)

        if file_ext in VIDEO_EXTENSIONS:
            await status_msg.edit_text("📤 **Preparing high-speed video stream upload...**")
            sent_media = await client.send_video(
                chat_id=message.chat.id,
                video=temp_download_path,
                caption=caption,
                thumb=temp_thumb_path,
                duration=duration,
                width=width,
                height=height,
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

        # 30 minute auto-delete: Deletes video after 30 minutes, then posts regulation message
        asyncio.create_task(auto_delete_and_notify(client, message.chat.id, sent_media.id, delay=1800))

    except Exception as e:
        logger.error(f"Downloader error: {e}")
        try:
            await status_msg.edit_text(f"❌ **Error:** `{e}`")
        except Exception:
            pass

    finally:
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
