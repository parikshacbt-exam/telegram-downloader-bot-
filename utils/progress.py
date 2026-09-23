import time
import math
import asyncio
from pyrogram.errors import FloodWait, MessageNotModified

# Keep track of last update times per message
_last_update_time = {}

def humanbytes(size):
    """Format bytes into human-readable representation"""
    if not size:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = int(math.floor(math.log(size, 1024)))
    p = math.pow(1024, i)
    s = round(size / p, 2)
    return f"{s} {units[i]}"

def time_formatter(seconds):
    """Format seconds into HH:MM:SS format"""
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    res = ""
    if days > 0:
        res += f"{days}d "
    if hours > 0:
        res += f"{hours}h "
    if minutes > 0:
        res += f"{minutes}m "
    res += f"{seconds}s"
    return res

async def progress_for_pyrogram(current, total, ud_type, message, start_time):
    """
    Throttled real-time progress callback for Pyrogram upload/download.
    Edits the Telegram message at most once every 3.5 seconds to avoid FloodWait.
    """
    now = time.time()
    msg_id = f"{message.chat.id}_{message.id}_{ud_type}"
    
    last_time = _last_update_time.get(msg_id, 0)
    # Only update every 3.5 seconds or when finished (current == total)
    if (now - last_time) < 3.5 and current != total:
        return

    _last_update_time[msg_id] = now
    
    diff = now - start_time
    if diff == 0:
        diff = 1
    
    percentage = (current / total) * 100 if total > 0 else 0
    speed = current / diff
    elapsed_time = round(diff)
    eta = round((total - current) / speed) if speed > 0 else 0
    
    # Progress visual bar (10 blocks)
    filled_blocks = int(round(percentage / 10))
    empty_blocks = 10 - filled_blocks
    bar = "█" * filled_blocks + "░" * empty_blocks
    
    status_emoji = "📥" if "Download" in ud_type else "📤"
    
    progress_str = (
        f"{status_emoji} **{ud_type}**\n\n"
        f"[{bar}] `{percentage:.1f}%`\n\n"
        f"📦 **Size:** `{humanbytes(current)} / {humanbytes(total)}`\n"
        f"⚡ **Speed:** `{humanbytes(speed)}/s`\n"
        f"⏳ **ETA:** `{time_formatter(eta)}`\n"
        f"⏱️ **Elapsed:** `{time_formatter(elapsed_time)}`"
    )
    
    try:
        await message.edit_text(progress_str)
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except MessageNotModified:
        pass
    except Exception:
        pass
