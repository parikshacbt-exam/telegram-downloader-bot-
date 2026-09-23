import logging
import aiosqlite
from config import Config

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.use_mongo = bool(Config.MONGO_URI)
        self.mongo_client = None
        self.db = None
        self.users_col = None
        self.sqlite_db_path = "downloader.db"

    async def init(self):
        """Initialize connection to either MongoDB or SQLite"""
        if self.use_mongo:
            try:
                from motor.motor_asyncio import AsyncIOMotorClient
                self.mongo_client = AsyncIOMotorClient(Config.MONGO_URI)
                self.db = self.mongo_client[Config.DB_NAME]
                self.users_col = self.db["users"]
                # Test connection
                await self.mongo_client.server_info()
                logger.info("Successfully connected to MongoDB Atlas!")
                return
            except Exception as e:
                logger.warning(f"Failed to connect to MongoDB ({e}). Falling back to local SQLite.")
                self.use_mongo = False

        # SQLite Fallback
        async with aiosqlite.connect(self.sqlite_db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    name TEXT,
                    username TEXT,
                    thumbnail TEXT DEFAULT NULL,
                    caption TEXT DEFAULT NULL
                )
            """)
            await db.commit()
        logger.info(f"Initialized local SQLite database: {self.sqlite_db_path}")

    async def add_user(self, user_id: int, name: str = "", username: str = ""):
        """Save a new user or update basic details"""
        if self.use_mongo:
            try:
                await self.users_col.update_one(
                    {"_id": user_id},
                    {"$set": {"name": name, "username": username}},
                    upsert=True
                )
            except Exception as e:
                logger.error(f"MongoDB add_user error: {e}")
        else:
            async with aiosqlite.connect(self.sqlite_db_path) as db:
                await db.execute("""
                    INSERT INTO users (user_id, name, username)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET name=excluded.name, username=excluded.username
                """, (user_id, name, username))
                await db.commit()

    async def get_all_users(self):
        """Retrieve list of all registered user IDs"""
        users = []
        if self.use_mongo:
            try:
                cursor = self.users_col.find({}, {"_id": 1})
                async for doc in cursor:
                    users.append(doc["_id"])
            except Exception as e:
                logger.error(f"MongoDB get_all_users error: {e}")
        else:
            async with aiosqlite.connect(self.sqlite_db_path) as db:
                async with db.execute("SELECT user_id FROM users") as cursor:
                    rows = await cursor.fetchall()
                    users = [row[0] for row in rows]
        return users

    async def total_users_count(self) -> int:
        """Count total registered users"""
        if self.use_mongo:
            try:
                return await self.users_col.count_documents({})
            except Exception as e:
                logger.error(f"MongoDB total_users_count error: {e}")
                return 0
        else:
            async with aiosqlite.connect(self.sqlite_db_path) as db:
                async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else 0

    async def set_thumbnail(self, user_id: int, file_id: str):
        """Set user's custom thumbnail file_id"""
        if self.use_mongo:
            await self.users_col.update_one(
                {"_id": user_id},
                {"$set": {"thumbnail": file_id}},
                upsert=True
            )
        else:
            async with aiosqlite.connect(self.sqlite_db_path) as db:
                await db.execute("""
                    INSERT INTO users (user_id, thumbnail) VALUES (?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET thumbnail=excluded.thumbnail
                """, (user_id, file_id))
                await db.commit()

    async def get_thumbnail(self, user_id: int):
        """Get user's custom thumbnail file_id"""
        if self.use_mongo:
            doc = await self.users_col.find_one({"_id": user_id}, {"thumbnail": 1})
            return doc.get("thumbnail") if doc else None
        else:
            async with aiosqlite.connect(self.sqlite_db_path) as db:
                async with db.execute("SELECT thumbnail FROM users WHERE user_id = ?", (user_id,)) as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row and row[0] else None

    async def del_thumbnail(self, user_id: int):
        """Remove user's custom thumbnail"""
        if self.use_mongo:
            await self.users_col.update_one(
                {"_id": user_id},
                {"$unset": {"thumbnail": ""}}
            )
        else:
            async with aiosqlite.connect(self.sqlite_db_path) as db:
                await db.execute("UPDATE users SET thumbnail = NULL WHERE user_id = ?", (user_id,))
                await db.commit()

    async def set_caption(self, user_id: int, caption: str):
        """Set user's custom caption template"""
        if self.use_mongo:
            await self.users_col.update_one(
                {"_id": user_id},
                {"$set": {"caption": caption}},
                upsert=True
            )
        else:
            async with aiosqlite.connect(self.sqlite_db_path) as db:
                await db.execute("""
                    INSERT INTO users (user_id, caption) VALUES (?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET caption=excluded.caption
                """, (user_id, caption))
                await db.commit()

    async def get_caption(self, user_id: int):
        """Get user's custom caption"""
        if self.use_mongo:
            doc = await self.users_col.find_one({"_id": user_id}, {"caption": 1})
            return doc.get("caption") if doc else None
        else:
            async with aiosqlite.connect(self.sqlite_db_path) as db:
                async with db.execute("SELECT caption FROM users WHERE user_id = ?", (user_id,)) as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row and row[0] else None

    async def del_caption(self, user_id: int):
        """Remove user's custom caption"""
        if self.use_mongo:
            await self.users_col.update_one(
                {"_id": user_id},
                {"$unset": {"caption": ""}}
            )
        else:
            async with aiosqlite.connect(self.sqlite_db_path) as db:
                await db.execute("UPDATE users SET caption = NULL WHERE user_id = ?", (user_id,))
                await db.commit()

db = Database()
