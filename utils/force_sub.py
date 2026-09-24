import logging
from pyrogram.errors import UserNotParticipant
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import Config

logger = logging.getLogger(__name__)

def clean_channel_input(channel_raw):
    """Clean channel input: handles IDs, @username, or https://t.me/username"""
    if not channel_raw:
        return None
    val = str(channel_raw).strip()
    if val.startswith("-100") or val.startswith("-") or (val.isdigit() and len(val) > 5):
        try:
            return int(val)
        except ValueError:
            pass
    if "t.me/" in val:
        val = val.split("t.me/")[-1].split("/")[0].split("?")[0]
    val = val.lstrip("@").strip()
    return val if val else None

async def get_invite_link(client, channel_id):
    """Retrieve or export an invite link for the force sub channel"""
    try:
        chat = await client.get_chat(channel_id)
        if chat.username:
            return f"https://t.me/{chat.username}"
        if chat.invite_link:
            return chat.invite_link
        return await client.export_chat_invite_link(channel_id)
    except Exception as e:
        logger.error(f"Error getting invite link for {channel_id}: {e}")
        return None

async def is_subscribed(client, user_id: int) -> bool:
    """Check if user has joined the force subscribe channel"""
    raw_channel = getattr(Config, "FORCE_SUB_CHANNEL", "")
    channel = clean_channel_input(raw_channel)
    if not channel:
        return True

    try:
        member = await client.get_chat_member(channel, user_id)
        status_str = str(member.status).lower().split(".")[-1]
        
        # If user left or was banned, they are not subscribed
        if status_str in ["left", "banned", "kicked"]:
            return False
        
        # All other statuses: owner, creator, administrator, member, restricted -> SUBSCRIBED
        return True
    except UserNotParticipant:
        return False
    except Exception as e:
        logger.warning(f"Force Sub check bypassed for user {user_id} due to error: {e}")
        # If bot is not admin or channel is misconfigured, never block users
        return True

async def send_force_sub_message(client, message):
    """Send Force Subscribe requirement message with Join & Try Again buttons"""
    raw_channel = getattr(Config, "FORCE_SUB_CHANNEL", "")
    channel = clean_channel_input(raw_channel)
    if not channel:
        return True

    invite_link = await get_invite_link(client, channel)
    if not invite_link:
        if isinstance(channel, str) and not str(channel).startswith("-"):
            invite_link = f"https://t.me/{channel}"
        else:
            invite_link = "https://t.me"

    buttons = [
        [InlineKeyboardButton("📢 Join Channel", url=invite_link)],
        [InlineKeyboardButton("🔄 Try Again", callback_data="check_sub")]
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    
    text = (
        "⚠️ **Access Denied!**\n\n"
        "You must join our Updates Channel before using this bot.\n"
        "Click the button below to join, then click **'Try Again'** to continue!"
    )
    
    return await message.reply_text(text, reply_markup=keyboard, quote=True)
