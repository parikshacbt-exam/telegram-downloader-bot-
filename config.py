import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class Config:
    # Telegram API Credentials
    API_ID = int(os.getenv("API_ID", "0"))
    API_HASH = os.getenv("API_HASH", "")
    
    # Bot Token (from @BotFather)
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    
    # Admin User IDs
    ADMIN_IDS_RAW = os.getenv("ADMIN_ID", "")
    ADMINS = []
    if ADMIN_IDS_RAW:
        for x in ADMIN_IDS_RAW.replace(",", " ").split():
            try:
                ADMINS.append(int(x.strip()))
            except ValueError:
                pass

    # Force Subscribe Channel Username
    FORCE_SUB_CHANNEL = os.getenv("FORCE_SUB_CHANNEL", "").strip()
    
    # Database URL
    MONGO_URI = os.getenv("MONGO_URI", "").strip()
    DB_NAME = os.getenv("DB_NAME", "telegram_downloader_bot")
    
    # Web Server Port
    PORT = int(os.getenv("PORT", "8080"))
    
    # Local download directory
    DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")
    
    # Terabox Cookie
    TERABOX_COOKIE = os.getenv("TERABOX_COOKIE", "").strip()

    # Max File Size Limit (Telegram limit 2 GB)
    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024
