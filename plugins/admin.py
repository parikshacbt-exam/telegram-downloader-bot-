import time
import asyncio
import psutil
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated
from config import Config
from database import db
from utils.progress import humanbytes, time_formatter

logger = logging.getLogger(__name__)
BOT_START_TIME = time.time()

def is_admin(user_id: int) -> bool:
    return user_id in Config.ADMINS

@Client.on_message(filters.command("stats") & filters.private)
async def stats_handler(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return await message.reply_text("⛔ You are not authorized to use admin commands.", quote=True)

    status_msg = await message.reply_text("⏳ Gathering system statistics...", quote=True)
    
    total_users = await db.total_users_count()
    uptime = time_formatter(time.time() - BOT_START_TIME)
    
    # System metrics
    cpu_usage = psutil.cpu_percent()
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    stats_text = (
        "📊 **Bot Admin Dashboard**\n\n"
        f"👥 **Total Registered Users:** `{total_users}`\n"
        f"⏱️ **Bot Uptime:** `{uptime}`\n\n"
        "🖥️ **System Health:**\n"
        f"• **CPU Usage:** `{cpu_usage}%`\n"
        f"• **RAM Usage:** `{ram.percent}%` ({humanbytes(ram.used)} / {humanbytes(ram.total)})\n"
        f"• **Disk Usage:** `{disk.percent}%` ({humanbytes(disk.used)} / {humanbytes(disk.total)})\n"
    )

    await status_msg.edit_text(stats_text)

@Client.on_message(filters.command("broadcast") & filters.private)
async def broadcast_handler(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return await message.reply_text("⛔ You are not authorized to use admin commands.", quote=True)

    # Broadcast message can either be a reply to any message or text after command
    broadcast_msg = message.reply_to_message
    if not broadcast_msg and len(message.command) < 2:
        return await message.reply_text(
            "📢 **Usage:**\n"
            "• Reply to any message with `/broadcast` to forward/copy it to all users.\n"
            "• Or use `/broadcast Your Message Text Here`",
            quote=True
        )

    users = await db.get_all_users()
    total_users = len(users)
    if total_users == 0:
        return await message.reply_text("⚠️ No users found in database to broadcast to.", quote=True)

    progress_msg = await message.reply_text(f"🚀 **Broadcast Started...**\nTotal recipients: `{total_users}`", quote=True)
    
    success = 0
    failed = 0
    blocked = 0
    start_time = time.time()
    last_update = time.time()

    for i, user_id in enumerate(users):
        try:
            if broadcast_msg:
                await broadcast_msg.copy(chat_id=user_id)
            else:
                text_to_send = message.text.split(None, 1)[1]
                await client.send_message(chat_id=user_id, text=text_to_send)
            success += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            # Retry once after sleep
            try:
                if broadcast_msg:
                    await broadcast_msg.copy(chat_id=user_id)
                else:
                    await client.send_message(chat_id=user_id, text=text_to_send)
                success += 1
            except Exception:
                failed += 1
        except UserIsBlocked:
            blocked += 1
        except InputUserDeactivated:
            failed += 1
        except Exception as e:
            logger.debug(f"Broadcast error for {user_id}: {e}")
            failed += 1

        # Periodic update every 4 seconds
        if time.time() - last_update > 4 or (i + 1) == total_users:
            last_update = time.time()
            try:
                await progress_msg.edit_text(
                    "📢 **Broadcasting in Progress...**\n\n"
                    f"👥 **Progress:** `{i + 1} / {total_users}`\n"
                    f"✅ **Sent:** `{success}`\n"
                    f"🚫 **Blocked:** `{blocked}`\n"
                    f"❌ **Failed:** `{failed}`"
                )
            except Exception:
                pass
        
        await asyncio.sleep(0.05)  # Small delay to keep telegram happy

    time_taken = time_formatter(time.time() - start_time)
    await progress_msg.edit_text(
        "✅ **Broadcast Completed!**\n\n"
        f"⏱️ **Time Taken:** `{time_taken}`\n"
        f"👥 **Total Targets:** `{total_users}`\n"
        f"✅ **Delivered:** `{success}`\n"
        f"🚫 **Blocked:** `{blocked}`\n"
        f"❌ **Failed:** `{failed}`"
    )
