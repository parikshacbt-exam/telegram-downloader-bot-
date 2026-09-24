from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database import db
from utils.force_sub import is_subscribed, send_force_sub_message, clean_channel_input
from config import Config

START_TEXT = """
👋 **Hello, {mention}!**

Welcome to the **High-Speed File & Video Downloader Bot**! 🚀

I can download and send files directly to you from:
🔹 **Terabox** links
🔹 **YouTube, Instagram, Facebook, Twitter**
🔹 **All Adult / 18+ video platforms**
🔹 **Direct File / Video URLs** (up to 2 GB!)

✨ **Key Features:**
• 🖼️ Custom Thumbnail Support (`/set_thumb`)
• ✍️ Custom Caption Support (`/set_caption`)
• ⚡ Live Upload & Download Progress Bar
• 📂 Supported: Videos, Audios, Zip, Documents, etc.

Send me any supported link to get started!
"""

HELP_TEXT = """
📖 **How to Use this Bot:**

1️⃣ **Download Files / Videos:**
• Just copy any Terabox, YouTube, Insta, or direct link and send it here.
• The bot will fetch and upload the file with live progress.

2️⃣ **Custom Thumbnail:**
• Send any photo to the bot to set it as your thumbnail for videos.
• `/view_thumb` - View your thumbnail.
• `/del_thumb` - Delete thumbnail.

3️⃣ **Custom Caption:**
• `/set_caption [Your Caption]` - Set custom caption.
  _Tags:_ `{filename}`, `{filesize}`
• `/view_caption` - View caption.
• `/del_caption` - Delete caption.

4️⃣ **Terabox Cookie (Admin):**
• `/cookie <ndus>` - Set or update Terabox cookie in chat.
• `/cookie` - View current cookie status & setup guide.
• `/del_cookie` - Delete stored cookie.
"""

ABOUT_TEXT = """
🤖 **About This Bot:**

• **Bot Name:** File & Video Downloader
• **Engine:** Pyrogram MTProto + TeraboxDL + yt-dlp
• **Database:** MongoDB / SQLite
• **Hosting:** 24/7 Cloud Ready
• **Version:** v2.5.0
"""

def get_start_buttons():
    buttons = [
        [
            InlineKeyboardButton("📖 Help & Guides", callback_data="help_data"),
            InlineKeyboardButton("🤖 About", callback_data="about_data")
        ]
    ]
    raw_channel = getattr(Config, "FORCE_SUB_CHANNEL", "")
    chan = clean_channel_input(raw_channel)
    if chan:
        url = f"https://t.me/{chan}" if not str(chan).startswith("-") else "https://t.me"
        buttons.append([InlineKeyboardButton("📢 Updates Channel", url=url)])
    return InlineKeyboardMarkup(buttons)

def get_back_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="start_data")]
    ])

@Client.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user = message.from_user
    await db.add_user(user.id, user.first_name, user.username or "")
    
    if not await is_subscribed(client, user.id):
        return await send_force_sub_message(client, message)
        
    await message.reply_text(
        START_TEXT.format(mention=user.mention),
        reply_markup=get_start_buttons(),
        disable_web_page_preview=True,
        quote=True
    )

@Client.on_message(filters.command("help") & filters.private)
async def help_handler(client: Client, message: Message):
    await message.reply_text(
        HELP_TEXT,
        reply_markup=get_back_button(),
        disable_web_page_preview=True,
        quote=True
    )

@Client.on_message(filters.command("about") & filters.private)
async def about_handler(client: Client, message: Message):
    await message.reply_text(
        ABOUT_TEXT,
        reply_markup=get_back_button(),
        disable_web_page_preview=True,
        quote=True
    )

@Client.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    data = query.data
    user = query.from_user

    if data == "check_sub":
        if await is_subscribed(client, user.id):
            await query.answer("✅ Thank you! Verification successful.", show_alert=True)
            try:
                await query.message.delete()
            except Exception:
                pass
            await client.send_message(
                user.id,
                START_TEXT.format(mention=user.mention),
                reply_markup=get_start_buttons(),
                disable_web_page_preview=True
            )
        else:
            await query.answer("❌ You still haven't joined! Please join the channel first.", show_alert=True)

    elif data == "help_data":
        await query.message.edit_text(
            HELP_TEXT,
            reply_markup=get_back_button(),
            disable_web_page_preview=True
        )
        await query.answer()

    elif data == "about_data":
        await query.message.edit_text(
            ABOUT_TEXT,
            reply_markup=get_back_button(),
            disable_web_page_preview=True
        )
        await query.answer()

    elif data == "start_data":
        await query.message.edit_text(
            START_TEXT.format(mention=user.mention),
            reply_markup=get_start_buttons(),
            disable_web_page_preview=True
        )
        await query.answer()
