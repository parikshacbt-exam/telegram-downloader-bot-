import logging
from pyrogram.errors import UserNotParticipant, ChatAdminRequired
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import Config

logger = logging.getLogger(__name__)

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
    if not Config.FORCE_SUB_CHANNEL:
        return True

    channel = Config.FORCE_SUB_CHANNEL
    # Try converting to int if it's an ID
    try:
        if channel.startswith("-100") or channel.startswith("-") or channel.isdigit():
            channel = int(channel)
    except ValueError:
        pass

    try:
        member = await client.get_chat_member(channel, user_id)
        if member.status in ["creator", "administrator", "member", "restricted"]:
            return True
        return False
    except UserNotParticipant:
        return False
    except Exception as e:
        logger.warning(f"Force Sub check failed for user {user_id}: {e}")
        # If bot is not admin or channel is invalid, do not block user
        return True

async def send_force_sub_message(client, message):
    """Send Force Subscribe requirement message with Join & Try Again buttons"""
    channel = Config.FORCE_SUB_CHANNEL
    try:
        if channel.startswith("-100") or channel.startswith("-") or channel.isdigit():
            channel = int(channel)
    except ValueError:
        pass

    invite_link = await get_invite_link(client, channel)
    if not invite_link:
        if isinstance(channel, str) and not channel.startswith("-"):
            invite_link = f"https://t.me/{channel.lstrip('@')}"
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
