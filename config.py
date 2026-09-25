import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class Config:
    # Telegram API Credentials (from my.telegram.org)
    API_ID = int(os.getenv("API_ID", "0"))
    API_HASH = os.getenv("API_HASH", "")
    
    # Bot Token (from @BotFather)
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    
    # Admin User IDs (supports ADMIN_ID, ADMIN_IDS, OWNER_ID, ADMIN)
    ADMIN_IDS_RAW = (
        os.getenv("ADMIN_ID") or
        os.getenv("ADMIN_IDS") or
        os.getenv("OWNER_ID") or
        os.getenv("ADMIN") or
        ""
    ).strip()
    ADMINS = []
    if ADMIN_IDS_RAW:
        for x in ADMIN_IDS_RAW.replace(",", " ").split():
            try:
                ADMINS.append(int(x.strip()))
            except ValueError:
                pass

    # Force Subscribe Channel Username (without @) or Channel ID (e.g. -100xxxxxxxxxx)
    FORCE_SUB_CHANNEL = os.getenv("FORCE_SUB_CHANNEL", "").strip()
    
    # Database URL: MongoDB Atlas URI (Recommended for cloud hosting)
    # If empty, automatically falls back to local SQLite database (downloader.db)
    MONGO_URI = os.getenv("MONGO_URI", "").strip()
    DB_NAME = os.getenv("DB_NAME", "telegram_downloader_bot")
    
    # Web Server Port for 24/7 Hosting Health Checks (Render / Koyeb)
    PORT = int(os.getenv("PORT", "8080"))
    
    # Local download directory for processing files
    DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")
    
    # Terabox Cookie (supports TERABOX_COOKIE, NDUS, ndus, COOKIE, COOKIES, TERABOX_NDUS, TERABOXCOOKIE, TERA_COOKIE)
    TERABOX_COOKIE = (
        os.getenv("TERABOX_COOKIE") or
        os.getenv("NDUS") or
        os.getenv("ndus") or
        os.getenv("COOKIE") or
        os.getenv("COOKIES") or
        os.getenv("TERABOX_NDUS") or
        os.getenv("TERABOXCOOKIE") or
        os.getenv("TERA_COOKIE") or
        os.getenv("TERA_NDUS") or
        ""
    ).strip()

    # Max File Size Limit (Telegram free bot limit is 2 GB)
    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB in bytes
