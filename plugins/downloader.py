import os
import re
import time
import asyncio
import logging
import urllib.parse
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import Config
from database import db
from utils.force_sub import is_subscribed, send_force_sub_message
from utils.progress import progress_for_pyrogram, humanbytes
from utils.terabox import is_terabox_link, extract_terabox_surl, resolve_terabox_link, download_file_with_progress
from utils.ytdl import (
    is_youtube_link,
    extract_youtube_info,
    download_youtube,
    download_with_ytdl
)

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".ts", ".m4v"]
DIRECT_FILE_EXTENSIONS = [
    ".zip", ".rar", ".7z", ".tar", ".gz", ".iso", ".apk", ".exe", ".pdf",
    ".docx", ".xlsx", ".pptx", ".mp3", ".wav", ".flac", ".ogg", ".m4a"
]

# Cache to store YouTube URLs by video ID for inline buttons
YOUTUBE_URL_CACHE = {}

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

async def auto_delete_and_notify(client: Client, chat_id: int, media_message_id: int, delay: int = 1800):
    """Wait for 30 minutes, delete media, and send regulation notice without quoting/tagging"""
    await asyncio.sleep(delay)
    try:
        await client.delete_messages(chat_id, media_message_id)
    except Exception as e:
        logger.debug(f"Could not delete message {media_message_id}: {e}")

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
            if url.endswith("...") or url.endswith("…"):
                return await status_msg.edit_text(
                    "⚠️ **अधूरा Terabox लिंक!**\n\n"
                    "आपके द्वारा भेजे गए लिंक का कुछ हिस्सा कट गया है। कृपया ब्राउज़र से पूरा लिंक कॉपी करके भेजें।"
                )

            await status_msg.edit_text("⚡ **Resolving Terabox link...** Please wait.")
            resolved = await resolve_terabox_link(url)

            if not resolved or not resolved.get("success") or not resolved.get("direct_url"):
                reason = resolved.get("reason", "इस Terabox लिंक से फ़ाइल प्राप्त नहीं हो सकी।") if resolved else "लिंक रिज़ॉल्व नहीं हो सका।"
                err_text = f"❌ **Terabox Download Error**\n\n**विवरण:** {reason}"
                if user_id in getattr(Config, "ADMINS", []):
                    current_cookie = await db.get_terabox_cookie()
                    if not current_cookie:
                        err_text += (
                            "\n\n⚙️ **Bot Admin Setup:**\n"
                            "सर्वर पर Terabox सेशन एक्टिव नहीं है। सभी यूज़र्स के लिए डाउनलोड चालू करने हेतु बॉट में भेजें:\n"
                            "`/cookie <आपकी_ndus_कुकी>`"
                        )
                return await status_msg.edit_text(err_text)

            direct_url = resolved["direct_url"]
            filename = resolved.get("filename") or "video.mp4"
            filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
            temp_download_path = os.path.join(download_dir, f"{user_id}_{int(time.time())}_{filename}")

            await status_msg.edit_text("📥 **Starting High-Speed Download...**")
            await download_file_with_progress(direct_url, temp_download_path, status_msg, time.time())
            video_duration, video_width, video_height = get_video_metadata(temp_download_path)

        # ========================================================
        # PATHWAY 2: YOUTUBE LINKS (Interactive Quality & MP3 Options)
        # ========================================================
        elif is_youtube_link(url):
            await status_msg.edit_text("⚡ **Fetching YouTube Video Details...**")
            try:
                info = await extract_youtube_info(url)
            except Exception as e:
                logger.error(f"YouTube extraction error: {e}")
                return await status_msg.edit_text(
                    "❌ **YouTube वीडियो लोड नहीं हो सका!**\n\n"
                    "कृपया सुनिश्चित करें कि वीडियो सार्वजनिक (Public) है और हटाया नहीं गया है।"
                )

            vid = info["video_id"]
            YOUTUBE_URL_CACHE[vid] = url

            title = info["title"]
            duration_str = info["duration_str"]
            channel = info["channel"]

            buttons = [
                [
                    InlineKeyboardButton("🎬 1080p (FHD)", callback_data=f"yt:1080p:{vid}"),
                    InlineKeyboardButton("🎬 720p (HD)", callback_data=f"yt:720p:{vid}")
                ],
                [
                    InlineKeyboardButton("🎬 480p (SD)", callback_data=f"yt:480p:{vid}"),
                    InlineKeyboardButton("🎬 360p (Low)", callback_data=f"yt:360p:{vid}")
                ],
                [
                    InlineKeyboardButton("🎵 MP3 Audio (Music)", callback_data=f"yt:mp3:{vid}")
                ],
                [
                    InlineKeyboardButton("❌ Cancel", callback_data=f"yt:cancel:{vid}")
                ]
            ]
            keyboard = InlineKeyboardMarkup(buttons)

            preview_text = (
                f"🎬 **{title}**\n\n"
                f"⏱️ **Duration:** `{duration_str}`\n"
                f"👤 **Channel:** `{channel}`\n\n"
                f"👇 **कृपया वीडियो क्वालिटी या MP3 ऑडियो चुनें:**"
            )
            return await status_msg.edit_text(preview_text, reply_markup=keyboard)

        # ========================================================
        # PATHWAY 3: INSTAGRAM REELS, FACEBOOK, TWITTER, ADULT SITES & DIRECT FILES
        # ========================================================
        else:
            await status_msg.edit_text("⚡ **Downloading media stream with full audio...**")
            ytdl_success = False
            video_duration = 0
            video_width = 0
            video_height = 0

            # Guaranteed Audio for Instagram & other tube platforms
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

            # Fallback for direct downloadable files (.zip, .pdf, .mp3, etc.)
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
        # UPLOAD TO TELEGRAM (For Terabox, Instagram, and Direct Files)
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
            await status_msg.edit_text("📤 **Uploading video with sound...**")
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
            await status_msg.edit_text("📤 **Uploading document file...**")
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

        # 30-minute auto-delete with clean regulation notice
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


# ========================================================
# CALLBACK QUERY HANDLER FOR YOUTUBE QUALITY & MP3
# ========================================================
@Client.on_callback_query(filters.regex(r"^yt:"))
async def youtube_callback_handler(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    data_parts = query.data.split(":")
    if len(data_parts) < 3:
        return await query.answer("Invalid request.", show_alert=True)

    _, format_choice, vid = data_parts

    if format_choice == "cancel":
        await query.answer("Cancelled.")
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    url = YOUTUBE_URL_CACHE.get(vid)
    if not url:
        url = f"https://www.youtube.com/watch?v={vid}"

    status_msg = query.message
    if format_choice == "mp3":
        await status_msg.edit_text("🎵 **Starting YouTube MP3 conversion...** Please wait.")
    else:
        await status_msg.edit_text(f"📥 **Downloading YouTube Video ({format_choice})...** Please wait.")

    download_dir = getattr(Config, "DOWNLOAD_DIR", "downloads")
    os.makedirs(download_dir, exist_ok=True)
    temp_download_path = None
    temp_thumb_path = None

    try:
        res = await download_youtube(url, download_dir, format_choice, status_msg, time.time())
        temp_download_path = res["filepath"]
        filename = os.path.basename(temp_download_path)
        actual_size = os.path.getsize(temp_download_path)
        title = res["title"]
        channel = res["channel"]
        duration = res["duration"]
        is_audio = res["is_audio"]

        max_size = getattr(Config, "MAX_FILE_SIZE", 2 * 1024 * 1024 * 1024)
        if actual_size > max_size:
            return await status_msg.edit_text(
                f"❌ **File too large!**\n"
                f"File size is `{humanbytes(actual_size)}`. Telegram allows maximum 2 GB for bots."
            )

        # Check custom thumbnail
        thumb_file_id = await db.get_thumbnail(user_id)
        if thumb_file_id:
            try:
                temp_thumb_path = await client.download_media(thumb_file_id)
            except Exception:
                temp_thumb_path = None

        upload_start = time.time()
        bot_username = client.me.username if client.me and client.me.username else "FileDownloader"

        if is_audio:
            await status_msg.edit_text("📤 **Uploading MP3 Audio...**")
            sent_media = await client.send_audio(
                chat_id=query.message.chat.id,
                audio=temp_download_path,
                caption=f"🎵 **{title}**\n📦 **Size:** `{humanbytes(actual_size)}`\n⚡ **Downloaded via @{bot_username}**",
                title=title,
                performer=channel,
                duration=duration,
                thumb=temp_thumb_path,
                progress=progress_for_pyrogram,
                progress_args=("Uploading MP3", status_msg, upload_start)
            )
        else:
            await status_msg.edit_text(f"📤 **Uploading {format_choice} Video...**")
            custom_caption = await db.get_caption(user_id)
            if custom_caption:
                caption = custom_caption.replace("{filename}", filename).replace("{filesize}", humanbytes(actual_size))
            else:
                caption = (
                    f"📁 **Filename:** `{filename}`\n"
                    f"📦 **Size:** `{humanbytes(actual_size)}`\n\n"
                    f"⚡ **Downloaded via @{bot_username}**"
                )

            sent_media = await client.send_video(
                chat_id=query.message.chat.id,
                video=temp_download_path,
                caption=caption,
                thumb=temp_thumb_path,
                duration=duration,
                width=res["width"],
                height=res["height"],
                supports_streaming=True,
                progress=progress_for_pyrogram,
                progress_args=("Uploading Video", status_msg, upload_start)
            )

        try:
            await status_msg.delete()
        except Exception:
            pass

        # 30-minute auto-delete with clean regulation notice
        asyncio.create_task(auto_delete_and_notify(client, query.message.chat.id, sent_media.id, delay=1800))

    except Exception as e:
        logger.error(f"YouTube download callback error: {e}")
        try:
            await status_msg.edit_text(f"❌ **Download Error:** `{e}`")
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
