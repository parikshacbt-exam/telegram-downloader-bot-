from pyrogram import Client, filters
from pyrogram.types import Message
from database import db
from utils.force_sub import is_subscribed, send_force_sub_message

# ================= CUSTOM THUMBNAIL HANDLERS ================= #

@Client.on_message(filters.photo & filters.private)
async def photo_as_thumbnail_handler(client: Client, message: Message):
    """Automatically set any photo sent by user as their custom thumbnail"""
    if not await is_subscribed(client, message.from_user.id):
        return await send_force_sub_message(client, message)

    file_id = message.photo.file_id
    await db.set_thumbnail(message.from_user.id, file_id)
    await message.reply_text(
        "✅ **Custom Thumbnail Saved Successfully!**\n\n"
        "This thumbnail will now be attached to all your uploaded videos.\n"
        "Use `/view_thumb` to see it or `/del_thumb` to remove it.",
        quote=True
    )

@Client.on_message(filters.command(["set_thumb", "setthumb"]) & filters.private)
async def set_thumb_command_handler(client: Client, message: Message):
    if not await is_subscribed(client, message.from_user.id):
        return await send_force_sub_message(client, message)

    replied = message.reply_to_message
    if replied and replied.photo:
        file_id = replied.photo.file_id
        await db.set_thumbnail(message.from_user.id, file_id)
        return await message.reply_text("✅ **Custom Thumbnail Saved Successfully!**", quote=True)

    await message.reply_text(
        "📸 **How to set Custom Thumbnail:**\n\n"
        "Simply send a photo directly to this chat, or reply to any photo with `/set_thumb`.",
        quote=True
    )

@Client.on_message(filters.command(["view_thumb", "viewthumb"]) & filters.private)
async def view_thumb_handler(client: Client, message: Message):
    if not await is_subscribed(client, message.from_user.id):
        return await send_force_sub_message(client, message)

    thumb = await db.get_thumbnail(message.from_user.id)
    if thumb:
        await message.reply_photo(
            photo=thumb,
            caption="🖼️ **Here is your current saved Custom Thumbnail.**\nUse `/del_thumb` to remove it.",
            quote=True
        )
    else:
        await message.reply_text("ℹ️ You don't have any custom thumbnail set.\nSend a photo to set one!", quote=True)

@Client.on_message(filters.command(["del_thumb", "delthumb"]) & filters.private)
async def del_thumb_handler(client: Client, message: Message):
    if not await is_subscribed(client, message.from_user.id):
        return await send_force_sub_message(client, message)

    await db.del_thumbnail(message.from_user.id)
    await message.reply_text("🗑️ **Custom Thumbnail Deleted Successfully!**", quote=True)

# ================= CUSTOM CAPTION HANDLERS ================= #

@Client.on_message(filters.command(["set_caption", "setcaption"]) & filters.private)
async def set_caption_handler(client: Client, message: Message):
    if not await is_subscribed(client, message.from_user.id):
        return await send_force_sub_message(client, message)

    if len(message.command) < 2:
        return await message.reply_text(
            "📝 **Usage:** `/set_caption Your Caption Here`\n\n"
            "**Supported Dynamic Tags:**\n"
            "• `{filename}` - Insert original file name\n"
            "• `{filesize}` - Insert formatted file size\n\n"
            "**Example:**\n"
            "`/set_caption 🎬 File: {filename}\n📦 Size: {filesize}\nJoin: @MyChannel`",
            quote=True
        )

    caption = message.text.split(None, 1)[1]
    await db.set_caption(message.from_user.id, caption)
    await message.reply_text(
        f"✅ **Custom Caption Saved Successfully!**\n\n"
        f"**Preview:**\n\n{caption}",
        quote=True
    )

@Client.on_message(filters.command(["view_caption", "viewcaption"]) & filters.private)
async def view_caption_handler(client: Client, message: Message):
    if not await is_subscribed(client, message.from_user.id):
        return await send_force_sub_message(client, message)

    caption = await db.get_caption(message.from_user.id)
    if caption:
        await message.reply_text(
            f"📝 **Your Current Custom Caption:**\n\n`{caption}`\n\n"
            "Use `/del_caption` to remove it.",
            quote=True
        )
    else:
        await message.reply_text(
            "ℹ️ You haven't set any custom caption yet.\n"
            "Use `/set_caption [text]` to set one.",
            quote=True
        )

@Client.on_message(filters.command(["del_caption", "delcaption"]) & filters.private)
async def del_caption_handler(client: Client, message: Message):
    if not await is_subscribed(client, message.from_user.id):
        return await send_force_sub_message(client, message)

    await db.del_caption(message.from_user.id)
    await message.reply_text("🗑️ **Custom Caption Deleted Successfully!**", quote=True)
