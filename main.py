import sys, os, asyncio, logging
from aiohttp import web

# Event loop fix for Python 3.10+ / 3.12 / 3.14
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from pyrogram import Client, idle
from pyrogram.errors import FloodWait
from config import Config
from database import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger("Bot")

# Keep-alive web server for 24/7 hosting
async def run_web():
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="OK"))
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logger.info(f"Keep-alive web server active on port {port}")

async def main():
    await db.init()
    os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)
    await run_web()

    # Safe verification of TERABOX_COOKIE (without exposing secret value)
    cookie = await db.get_terabox_cookie()
    if cookie:
        logger.info("TERABOX_COOKIE configured: YES")
        logger.info(f"TERABOX_COOKIE length: {len(cookie)}")
    else:
        logger.warning("TERABOX_COOKIE configured: NO")

    bot = Client(
        "bot_session",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        bot_token=Config.BOT_TOKEN,
        plugins=dict(root="plugins")
    )

    while True:
        try:
            await bot.start()
            break
        except FloodWait as e:
            logger.warning(f"Telegram FloodWait on login: sleeping for {e.value + 5}s...")
            await asyncio.sleep(e.value + 5)

    me = await bot.get_me()
    logger.info(f"Bot started successfully as @{me.username}")
    await idle()
    await bot.stop()

if __name__ == "__main__":
    loop.run_until_complete(main())
