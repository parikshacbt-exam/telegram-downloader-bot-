import sys
import asyncio

# Fix for Python 3.10+ / 3.12 / 3.14 where asyncio requires explicit event loop on thread
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

import os
import logging
from aiohttp import web
from pyrogram import Client, idle
from config import Config
from database import db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s"
)
logger = logging.getLogger("Main")

# ================= EMBEDDED WEB SERVER FOR 24/7 HOSTING ================= #
routes = web.RouteTableDef()

@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response({
        "status": "online",
        "service": "Telegram File & Video Downloader Bot",
        "version": "2.0.0"
    })

async def web_server():
    app = web.Application()
    app.add_routes(routes)
    return app

# ================= MAIN BOT ENTRY POINT ================= #
async def start_bot():
    logger.info("Initializing Database...")
    await db.init()

    # Verify credentials
    if not Config.BOT_TOKEN or not Config.API_ID or not Config.API_HASH:
        logger.error("BOT_TOKEN, API_ID, or API_HASH is missing in environment variables!")
        print("\n" + "="*60)
        print("ERROR: Please set BOT_TOKEN, API_ID, and API_HASH in your .env file!")
        print("="*60 + "\n")
        return

    logger.info("Starting Telegram Bot Client (Pure Bot Token Mode)...")
    bot = Client(
        name="FileDownloaderBot",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        bot_token=Config.BOT_TOKEN,
        plugins=dict(root="plugins"),
        workdir="downloads"
    )

    await bot.start()
    bot_info = await bot.get_me()
    logger.info(f"Bot started successfully as @{bot_info.username} [ID: {bot_info.id}]")

    # Start health check server for Render/Koyeb 24/7 hosting
    app = await web_server()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", Config.PORT)
    await site.start()
    logger.info(f"Web server running on 0.0.0.0:{Config.PORT} for 24/7 health checks.")

    logger.info("Bot is now running 24/7! Press Ctrl+C to stop.")
    await idle()

    # Graceful shutdown
    logger.info("Stopping Bot...")
    await bot.stop()
    await runner.cleanup()
    logger.info("Bot stopped cleanly.")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(start_bot())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Exiting.")
