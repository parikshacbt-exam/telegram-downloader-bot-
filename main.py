import sys, os, asyncio, logging
from aiohttp import web

# Event loop fix for Python 3.10+ / 3.12 / 3.14
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from pyrogram import Client, idle
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
    bot = Client(
        "bot",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        bot_token=Config.BOT_TOKEN,
        plugins=dict(root="plugins"),
        in_memory=True
    )
    await bot.start()
    me = await bot.get_me()
    logger.info(f"Bot started successfully as @{me.username}")
    await idle()
    await bot.stop()

if __name__ == "__main__":
    loop.run_until_complete(main())
