import logging
from pymongo import MongoClient
from telegram.ext import ContextTypes
from config import MONGO_URI, DB_CHANNEL_ID
import sqlite3
import os

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        try:
            self.mongo_client = MongoClient(MONGO_URI)
            self.db = self.mongo_client["zaky_dl"]
            self.use_mongo = True
            logger.info("[green]✅ Connected to MongoDB[/green]")
        except Exception as e:
            logger.error(f"[red]❌ Failed to connect to MongoDB: {e}[/red]")
            self.use_mongo = False
            self.local_db = sqlite3.connect("local_db.sqlite")
            self.local_db.execute("CREATE TABLE IF NOT EXISTS content (url TEXT PRIMARY KEY, link TEXT)")
            self.local_db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, join_date TEXT)")
            self.local_db.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)")
            self.local_db.commit()

    async def check_content(self, url):
        if self.use_mongo:
            result = self.db.content.find_one({"url": url})
            return result["link"] if result else None
        else:
            cursor = self.local_db.execute("SELECT link FROM content WHERE url = ?", (url,))
            result = cursor.fetchone()
            return result[0] if result else None

    async def store_content(self, url, link, context: ContextTypes.DEFAULT_TYPE, title):
        if self.use_mongo:
            self.db.content.update_one({"url": url}, {"$set": {"link": link}}, upsert=True)
        else:
            self.local_db.execute("INSERT OR REPLACE INTO content (url, link) VALUES (?, ?)", (url, link))
            self.local_db.commit()
        try:
            await context.bot.send_message(DB_CHANNEL_ID, f"💾 {title}\n{link}")
            logger.info(f"[green]💾 Stored content in channel: {url} -> {link}[/green]")
        except Exception as e:
            logger.error(f"[red]❌ Failed to store in channel: {e}[/red]")

    async def get_stats(self):
        if self.use_mongo:
            users = self.db.users.count_documents({})
        else:
            cursor = self.local_db.execute("SELECT COUNT(*) FROM users")
            users = cursor.fetchone()[0]
        return {"users": users}

    async def add_admin(self, admin_id):
        from config import ADMIN_IDS
        if admin_id not in ADMIN_IDS:
            ADMIN_IDS.append(admin_id)
            if self.use_mongo:
                self.db.admins.update_one({"id": admin_id}, {"$set": {"id": admin_id}}, upsert=True)
            else:
                self.local_db.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (f"admin_{admin_id}", str(admin_id)))
                self.local_db.commit()

    async def update_config(self, key, value):
        from config import globals
        globals()[key] = value
        if self.use_mongo:
            self.db.config.update_one({"key": key}, {"$set": {"value": value}}, upsert=True)
        else:
            self.local_db.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value)))
            self.local_db.commit()

db = Database()
check_content = db.check_content
store_content = db.store_content
get_stats = db.get_stats
add_admin = db.add_admin
update_config = db.update_config
