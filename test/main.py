import os
import logging
import asyncio
from typing import Dict, Optional, Tuple, List
import re
import json
import requests
import time
from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat, User, Message, MessageMediaDocument
from telethon.errors import FloodWaitError
import google.generativeai as genai
import threading

# --- Logging Configuration ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- API Credentials ---
API_ID = 25713843
API_HASH = "311352d08811e7f5136dfb27f71014c1"
PHONE_NUMBER = "+201514174672"

# --- Admin Info ---
ADMIN_USERNAME = "Zaky1million"
ADMIN_ID = 6988696258

# --- File Paths ---
CONFIG_FILE = "config.json"
SHARE_PROGRESS_FILE = "share_progress.json"
CHECK_PROGRESS_FILE = "check_progress.json"
SEARCH_CACHE_FILE = "search_cache.json"
SEARCH_HISTORY_FILE = "search_history.json"
VIDEO_DB_FILE = "video_database.json"
SCAN_PROGRESS_FILE = "scan_progress.json"

# --- Gemini API Token (Last Resort) ---
GEMINI_API_TOKEN = "AIzaSyC-3PFCoASRS8WpppTtbqsR599R9GdrS_I"

# --- AI Model Initialization ---
genai.configure(api_key=GEMINI_API_TOKEN)
GEMINI_MODEL = genai.GenerativeModel('models/gemini-2.0-pro-exp')

async def chat_with_ai(prompt: str, username: str = "مستخدم") -> str:
    prompt = f"""أنت Zaky AI، بوت بحث عن الأفلام.
    المستخدم @{username} يتحدث إليك.
    {prompt}
    **ملاحظة: أجب بالعربية فقط، بدون أي لغة أخرى مثل الإنجليزية.**
    **الأوامر:**
    - `start`: عرض قائمة الأوامر.
    - `stats`: عرض إحصائيات البوت.
    - `s -ch [رابط]`: تعيين قناة للبحث الدائم.
    - `Sv [رابط]`: فحص قناة وحفظ بيانات الفيديوهات محليًا.
    - `check dp`: فحص وتنظيف قاعدة البيانات.
    - `-ch -[رابط]`: تعيين قناة أرشيف (للأدمن).
    - `share -from [رابط] -to [رابط]`: نقل فيديوهات (للأدمن).
    - `stop share`: إيقاف النقل (للأدمن).
    - `cont share`: استكمال النقل (للأدمن).
    - `check [رابط]`: فحص قناة (للأدمن).
    - `stop check`: إيقاف الفحص (للأدمن).
    - `cont check`: استكمال الفحص (للأدمن).
    - `Sv stop`: إيقاف فحص القناة.
    - `Sv cont`: استكمال فحص القناة.
    - `stop`: إيقاف أي عملية جارية.
    - `Gp+ [رابط]`: إضافة جروب (للأدمن).
    - `Gp- [رابط]`: حذف جروب (للأدمن).
    - `mon`: عرض الجروبات (للأدمن).
    - أي نص بعد نقطة (مثل .هاي): رد عبر الذكاء الاصطناعي.
    - أي نص آخر: بحث عن فيلم."""

    try:
        url = f"https://api.gurusensei.workers.dev/llama?prompt={prompt}"
        response = requests.get(url, timeout=3)
        data = response.json()
        result = data.get("response", {}).get("response")
        if result:
            logger.info("Response received from GuruSensei API")
            return result
        else:
            raise ValueError("No valid response from GuruSensei API")
    except Exception as e:
        logger.warning(f"Error with GuruSensei API: {e}")

    try:
        response = GEMINI_MODEL.generate_content(prompt)
        result = response.text.strip()
        logger.info("Response received from Gemini API")
        return result
    except Exception as e:
        logger.warning(f"Error with Gemini: {e}")
        return "**عذرًا، حدثت مشكلة في الرد بالذكاء الاصطناعي! ⚠️**\n**للبحث عن فيلم: أرسل اسم الفيلم أو ID 🔍**\n**للتواصل مع الأدمن: @Zaky1million**"

class MovieBot:
    def __init__(self):
        self.client = TelegramClient('user_bot_session', API_ID, API_HASH)
        self.config = self.load_config()
        self.share_progress = self.load_share_progress()
        self.check_progress = self.load_check_progress()
        self.scan_progress = self.load_scan_progress()
        self.search_cache = self.load_search_cache()
        self.search_history = self.load_search_history()
        self.video_db = self.load_video_db()
        self.search_lock = asyncio.Lock()
        self.conversation_history: Dict[int, List[Dict]] = {}
        self.operations_state = {
            "share": {"running": False, "from_channel": None, "to_channel": None, "transferred_count": 0, "start_time": None, "task": None, "last_message_id": 0, "track_new": False},
            "check": {"running": False, "channel": None, "checked_count": 0, "cleaned_count": 0, "start_time": None, "task": None, "track_new": False},
            "scan": {"running": False, "channel": None, "scanned_count": 0, "saved_count": 0, "start_time": None, "task": None, "last_title": ""},
            "check_cross": {"running": False, "from_channel": None, "to_channel": None, "checked_count": 0, "transferred_count": 0, "start_time": None, "task": None, "last_message_id": 0},
            "check_dp": {"running": False, "track_changes": False, "start_time": None, "checked_count": 0, "cleaned_count": 0, "last_id": 0, "task": None}
        }
        self.allowed_groups = self.config.get("allowed_groups", [])
        self.search_channel = self.config.get("search_channel", None)
        self.scan_status_message = None
        self.search_status_message = None

    def load_config(self) -> Dict:
        if not os.path.exists(CONFIG_FILE):
            default_config = {"admin_id": ADMIN_ID, "admin_username": ADMIN_USERNAME, "archive_channel_id": None, "allowed_groups": [], "search_channel": None}
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=4)
            return default_config
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_config(self):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=4)

    def load_search_cache(self) -> Dict:
        if not os.path.exists(SEARCH_CACHE_FILE):
            with open(SEARCH_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=4)
        with open(SEARCH_CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_search_cache(self):
        with open(SEARCH_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.search_cache, f, ensure_ascii=False, indent=4)

    def load_search_history(self) -> Dict:
        if not os.path.exists(SEARCH_HISTORY_FILE):
            with open(SEARCH_HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=4)
        with open(SEARCH_HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_search_history(self):
        with open(SEARCH_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.search_history, f, ensure_ascii=False, indent=4)

    def load_video_db(self) -> Dict:
        if not os.path.exists(VIDEO_DB_FILE):
            with open(VIDEO_DB_FILE, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=4)
        with open(VIDEO_DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_video_db(self):
        with open(VIDEO_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.video_db, f, ensure_ascii=False, indent=4)

    def load_share_progress(self) -> Dict:
        default_progress = {"last_message_id": 0, "from_channel": None, "to_channel": None}
        if not os.path.exists(SHARE_PROGRESS_FILE):
            with open(SHARE_PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_progress, f, ensure_ascii=False, indent=4)
            return default_progress
        with open(SHARE_PROGRESS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for key in default_progress:
                if key not in data:
                    data[key] = default_progress[key]
            return data

    def save_share_progress(self):
        with open(SHARE_PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.share_progress, f, ensure_ascii=False, indent=4)

    def load_check_progress(self) -> Dict:
        default_progress = {"last_checked_id": 0}
        if not os.path.exists(CHECK_PROGRESS_FILE):
            with open(CHECK_PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_progress, f, ensure_ascii=False, indent=4)
            return default_progress
        with open(CHECK_PROGRESS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for key in default_progress:
                if key not in data:
                    data[key] = default_progress[key]
            return data

    def save_check_progress(self):
        with open(CHECK_PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.check_progress, f, ensure_ascii=False, indent=4)

    def load_scan_progress(self) -> Dict:
        default_progress = {"last_message_id": 0}
        if not os.path.exists(SCAN_PROGRESS_FILE):
            with open(SCAN_PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_progress, f, ensure_ascii=False, indent=4)
            return default_progress
        with open(SCAN_PROGRESS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for key in default_progress:
                if key not in data:
                    data[key] = default_progress[key]
            return data

    def save_scan_progress(self):
        with open(SCAN_PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.scan_progress, f, ensure_ascii=False, indent=4)

    async def is_admin(self, user_id: int, username: str = None) -> bool:
        if user_id == self.config["admin_id"]:
            return True
        if username and username.lower() == self.config["admin_username"].lower():
            return True
        return False

    async def notify_admin(self, message: str, is_search_notification: bool = False):
        try:
            admin_entity = await self.client.get_entity(self.config["admin_id"])
            if is_search_notification:
                self.search_status_message = await self.client.send_message(admin_entity, message, parse_mode='markdown', link_preview=False)
                logger.info(f"Admin notified (search): {message}")
            elif self.scan_status_message:
                await self.client.edit_message(admin_entity, self.scan_status_message, message, parse_mode='markdown', link_preview=False)
                logger.info(f"Admin notified: {message}")
            else:
                self.scan_status_message = await self.client.send_message(admin_entity, message, parse_mode='markdown', link_preview=False)
                logger.info(f"Admin notified: {message}")
        except FloodWaitError as e:
            logger.warning(f"FloodWaitError: Waiting {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
            await self.notify_admin(message, is_search_notification)
        except Exception as e:
            logger.error(f"Failed to notify admin: {str(e)}")

    def clean_title(self, title: str) -> str:
        if not title:
            return ""
        title = re.sub(r'https?://\S+', '', title)  # حذف الروابط
        title = re.sub(r'@\w+', '', title)  # حذف معرفات المستخدمين
        title = re.sub(r'[\*\[\]\|\\/`\<\>\(\)\!\.\?\"\'\-\_]', '', title)  # حذف الرموز الإضافية
        title = re.sub(r'[➲:•▪▫●►]+', '', title)  # حذف الرموز الأصلية
        return re.sub(r'\s+', ' ', title).strip()

    async def check_cross_channels(self, from_channel: str, to_channel: str, track_new: bool = False):
        self.operations_state["check_cross"]["running"] = True
        self.operations_state["check_cross"]["from_channel"] = from_channel
        self.operations_state["check_cross"]["to_channel"] = to_channel
        self.operations_state["check_cross"]["start_time"] = time.time()
        self.operations_state["check_cross"]["track_new"] = track_new
        checked_count = 0
        transferred_count = 0
        last_message_id = self.operations_state["check_cross"].get("last_message_id", 0)

        try:
            to_entity = await self.client.get_entity(to_channel)
            permissions = await self.client.get_permissions(to_entity, self.client.get_me())
            if not permissions.post_messages or not permissions.edit_messages:
                await self.notify_admin(f"**🚫 Insufficient permissions in target channel: {to_entity.title}**")
                self.operations_state["check_cross"]["running"] = False
                return

            from_entity = await self.client.get_entity(from_channel)
            logger.info(f"Starting cross-channel check from '{from_entity.title}' to '{to_entity.title}'")

            to_channel_videos = {}
            async for message in self.client.iter_messages(to_entity, limit=None):
                if not self.operations_state["check_cross"]["running"]:
                    logger.info("Cross-channel check stopped by admin")
                    break
                if message.media and isinstance(message.media, MessageMediaDocument) and message.media.document.mime_type.startswith('video/'):
                    title = self.clean_title(message.text) if message.text else f"Video without title (ID: {message.id})"
                    to_channel_videos[title.lower()] = message.id
                if len(to_channel_videos) % 100 == 0 and len(to_channel_videos) > 0:
                    await asyncio.sleep(2.5)
                if len(to_channel_videos) % 500 == 0 and len(to_channel_videos) > 0:
                    await asyncio.sleep(10)

            logger.info(f"Collected {len(to_channel_videos)} videos from target channel")

            async for message in self.client.iter_messages(from_entity, min_id=last_message_id, reverse=True):
                if not self.operations_state["check_cross"]["running"]:
                    logger.info("Cross-channel check stopped by admin")
                    break
                checked_count += 1
                self.operations_state["check_cross"]["last_message_id"] = message.id

                if message.media and isinstance(message.media, MessageMediaDocument) and message.media.document.mime_type.startswith('video/'):
                    title = self.clean_title(message.text) if message.text else f"Video without title (ID: {message.id})"
                    if title.lower() not in to_channel_videos:
                        await self.client.send_file(to_entity, message.media, caption=title, link_preview=False)
                        transferred_count += 1
                        video_id = str(message.id)
                        self.video_db[video_id] = {"title": title, "channel": from_channel}
                        self.save_video_db()
                        logger.info(f"Transferred video: '{title}' (ID: {message.id})")

                if checked_count % 100 == 0:
                    elapsed_time = int(time.time() - self.operations_state["check_cross"]["start_time"])
                    await self.notify_admin(
                        f"**🔍 جاري فحص التقاطع بين القنوات**\n"
                        f"**✅ تم فحص: {checked_count} فيديو**\n"
                        f"**🔄 تم نقل: {transferred_count} فيديو**\n"
                        f"**⏳ الوقت المنقضي: {elapsed_time} ثانية**"
                    )
                    await asyncio.sleep(2.5)
                if checked_count % 500 == 0:
                    await asyncio.sleep(10)

            if self.operations_state["check_cross"]["running"] and not track_new:
                elapsed_time = int(time.time() - self.operations_state["check_cross"]["start_time"])
                await self.notify_admin(
                    f"**✅ اكتمل فحص التقاطع بين القنوات**\n"
                    f"**📊 الإحصائيات النهائية:**\n"
                    f"**✅ تم فحص: {checked_count} فيديو**\n"
                    f"**🔄 تم نقل: {transferred_count} فيديو**\n"
                    f"**⏳ الوقت الكلي: {elapsed_time} ثانية**"
                )
                self.operations_state["check_cross"]["running"] = False
                logger.info(f"Cross-channel check completed: {checked_count} checked, {transferred_count} transferred")
                if track_new:
                    await self.notify_admin(f"**🔄 تتبع الفيديوهات الجديدة مفعل من: {from_entity.title} إلى: {to_entity.title}**")

        except Exception as e:
            await self.notify_admin(f"**🚫 Error during cross-channel check: {str(e)}**")
            logger.error(f"Cross-channel check error: {str(e)}")
            self.operations_state["check_cross"]["running"] = False

        self.operations_state["check_cross"]["checked_count"] = checked_count
        self.operations_state["check_cross"]["transferred_count"] = transferred_count

    async def share_videos(self, from_channel: str, to_channel: str, track_new: bool = False):
        self.operations_state["share"]["running"] = True
        self.operations_state["share"]["from_channel"] = from_channel
        self.operations_state["share"]["to_channel"] = to_channel
        self.operations_state["share"]["start_time"] = time.time()
        self.operations_state["share"]["track_new"] = track_new
        transferred_count = self.operations_state["share"]["transferred_count"]
        last_message_id = self.share_progress.get("last_message_id", 0)

        try:
            from_entity = await self.client.get_entity(from_channel)
            to_entity = await self.client.get_entity(to_channel)
            permissions = await self.client.get_permissions(to_entity, self.client.get_me())
            if not permissions.post_messages or not permissions.edit_messages:
                await self.notify_admin(f"**🚫 Insufficient permissions in target channel: {to_entity.title}**")
                self.operations_state["share"]["running"] = False
                return

            logger.info(f"Starting video share from '{from_entity.title}' to '{to_entity.title}' from ID {last_message_id}")

            to_channel_videos = {}
            async for message in self.client.iter_messages(to_entity, limit=None):
                if not self.operations_state["share"]["running"]:
                    logger.info("Share stopped by admin")
                    break
                if message.media and isinstance(message.media, MessageMediaDocument) and message.media.document.mime_type.startswith('video/'):
                    title = self.clean_title(message.text) if message.text else f"Video without title (ID: {message.id})"
                    to_channel_videos[title.lower()] = message.id
                if len(to_channel_videos) % 100 == 0 and len(to_channel_videos) > 0:
                    await asyncio.sleep(2.5)
                if len(to_channel_videos) % 500 == 0 and len(to_channel_videos) > 0:
                    await asyncio.sleep(10)

            logger.info(f"Collected {len(to_channel_videos)} videos from target channel")

            async for message in self.client.iter_messages(from_entity, min_id=last_message_id, reverse=True):
                if not self.operations_state["share"]["running"]:
                    logger.info("Share stopped by admin")
                    break
                if message.media and isinstance(message.media, MessageMediaDocument) and message.media.document.mime_type.startswith('video/'):
                    title = self.clean_title(message.text) if message.text else f"Video without title (ID: {message.id})"
                    if title.lower() not in to_channel_videos:
                        await self.client.send_file(to_entity, message.media, caption=title, link_preview=False)
                        transferred_count += 1
                        video_id = str(message.id)
                        self.video_db[video_id] = {"title": title, "channel": from_channel}
                        self.save_video_db()
                        logger.info(f"Transferred video: '{title}' (ID: {message.id})")

                self.share_progress["last_message_id"] = message.id
                self.save_share_progress()

                if transferred_count % 100 == 0 and transferred_count > 0:
                    elapsed_time = int(time.time() - self.operations_state["share"]["start_time"])
                    await self.notify_admin(
                        f"**🔄 جاري نقل الفيديوهات من: {from_entity.title} إلى: {to_entity.title}**\n"
                        f"**✅ تم النقل: {transferred_count} فيديو**\n"
                        f"**⏳ الوقت المنقضي: {elapsed_time} ثانية**"
                    )
                    await asyncio.sleep(2.5)
                if transferred_count % 500 == 0 and transferred_count > 0:
                    await asyncio.sleep(10)

            if self.operations_state["share"]["running"] and not track_new:
                elapsed_time = int(time.time() - self.operations_state["share"]["start_time"])
                await self.notify_admin(
                    f"**✅ اكتمل نقل الفيديوهات من: {from_entity.title} إلى: {to_entity.title}**\n"
                    f"**📊 الإحصائيات النهائية:**\n"
                    f"**✅ تم النقل: {transferred_count} فيديو**\n"
                    f"**⏳ الوقت الكلي: {elapsed_time} ثانية**"
                )
                self.operations_state["share"]["running"] = False
                logger.info(f"Share completed: {transferred_count} transferred")
                if track_new:
                    await self.notify_admin(f"**🔄 تتبع الفيديوهات الجديدة مفعل من: {from_entity.title} إلى: {to_entity.title}**")

        except Exception as e:
            await self.notify_admin(f"**🚫 Error during video share: {str(e)}**")
            logger.error(f"Share error: {str(e)}")
            self.operations_state["share"]["running"] = False

        self.operations_state["share"]["transferred_count"] = transferred_count

    async def check_channel(self, channel_link: str, track_new: bool = False):
        self.operations_state["check"]["running"] = True
        self.operations_state["check"]["channel"] = channel_link
        self.operations_state["check"]["track_new"] = track_new
        self.operations_state["check"]["start_time"] = time.time()
        checked_count = 0
        cleaned_count = 0
        last_message_id = self.check_progress.get("last_checked_id", 0)

        try:
            channel_entity = await self.client.get_entity(channel_link)
            permissions = await self.client.get_permissions(channel_entity, self.client.get_me())
            if not permissions.post_messages or not permissions.edit_messages:
                await self.notify_admin(f"**🚫 Insufficient permissions in channel: {channel_entity.title}**")
                self.operations_state["check"]["running"] = False
                return

            logger.info(f"Starting channel check for '{channel_entity.title}' from ID {last_message_id}")

            async for message in self.client.iter_messages(channel_entity, min_id=last_message_id, reverse=True):
                if not self.operations_state["check"]["running"]:
                    logger.info("Channel check stopped by admin")
                    break
                checked_count += 1
                self.check_progress["last_checked_id"] = message.id
                self.save_check_progress()

                if message.media and isinstance(message.media, MessageMediaDocument) and message.media.document.mime_type.startswith('video/'):
                    original_title = message.text if message.text else f"Video without title (ID: {message.id})"
                    cleaned_title = self.clean_title(original_title)
                    if cleaned_title != original_title:
                        try:
                            await self.client.edit_message(channel_entity, message.id, cleaned_title)
                            cleaned_count += 1
                            logger.info(f"Cleaned video title: '{cleaned_title}' (ID: {message.id})")
                        except Exception as e:
                            logger.error(f"Error editing video title: {str(e)}")
                    video_id = str(message.id)
                    self.video_db[video_id] = {"title": cleaned_title, "channel": channel_link}
                    self.save_video_db()

                if checked_count % 100 == 0:
                    elapsed_time = int(time.time() - self.operations_state["check"]["start_time"])
                    await self.notify_admin(
                        f"**🔍 جاري فحص قناة: {channel_entity.title}**\n"
                        f"**✅ تم فحص: {checked_count} رسالة**\n"
                        f"**🧹 تم تنظيف: {cleaned_count} عنوان**\n"
                        f"**⏳ الوقت المنقضي: {elapsed_time} ثانية**"
                    )
                    await asyncio.sleep(2.5)
                if checked_count % 500 == 0:
                    await asyncio.sleep(10)

            if self.operations_state["check"]["running"] and not track_new:
                elapsed_time = int(time.time() - self.operations_state["check"]["start_time"])
                await self.notify_admin(
                    f"**✅ اكتمل فحص قناة: {channel_entity.title}**\n"
                    f"**📊 الإحصائيات النهائية:**\n"
                    f"**✅ تم فحص: {checked_count} رسالة**\n"
                    f"**🧹 تم تنظيف: {cleaned_count} عنوان**\n"
                    f"**⏳ الوقت الكلي: {elapsed_time} ثانية**"
                )
                self.operations_state["check"]["running"] = False
                logger.info(f"Check completed: {checked_count} checked, {cleaned_count} cleaned")
                if track_new:
                    await self.notify_admin(f"**🔍 تتبع الرسائل الجديدة مفعل في قناة: {channel_entity.title}**")

        except Exception as e:
            await self.notify_admin(f"**🚫 Error during channel check: {str(e)}**")
            logger.error(f"Check error: {str(e)}")
            self.operations_state["check"]["running"] = False

        self.operations_state["check"]["checked_count"] = checked_count
        self.operations_state["check"]["cleaned_count"] = cleaned_count

    async def check_database(self, track_changes: bool = False):
        self.operations_state["check_dp"]["running"] = True
        self.operations_state["check_dp"]["track_changes"] = track_changes
        self.operations_state["check_dp"]["start_time"] = time.time()
        checked_count = 0
        cleaned_count = 0
        last_id = self.operations_state["check_dp"].get("last_id", 0)

        try:
            if not os.path.exists(VIDEO_DB_FILE) or not os.access(VIDEO_DB_FILE, os.R_OK | os.W_OK):
                await self.notify_admin("**🚫 Insufficient permissions to access database file**")
                self.operations_state["check_dp"]["running"] = False
                return

            logger.info("Starting database cleanup")
            video_ids = list(self.video_db.keys())
            if last_id > 0:
                try:
                    start_index = video_ids.index(str(last_id)) + 1
                    video_ids = video_ids[start_index:]
                except ValueError:
                    pass

            for video_id in video_ids:
                if not self.operations_state["check_dp"]["running"]:
                    logger.info("Database cleanup stopped by admin")
                    break
                checked_count += 1
                self.operations_state["check_dp"]["last_id"] = video_id
                data = self.video_db[video_id]
                original_title = data["title"]
                cleaned_title = self.clean_title(original_title)
                if cleaned_title != original_title:
                    self.video_db[video_id]["title"] = cleaned_title
                    cleaned_count += 1
                    self.save_video_db()
                    logger.info(f"Cleaned video title: '{cleaned_title}' (ID: {video_id})")

                if checked_count % 1000 == 0:
                    elapsed_time = int(time.time() - self.operations_state["check_dp"]["start_time"])
                    await self.notify_admin(
                        f"**🔍 جاري تنظيف قاعدة البيانات**\n"
                        f"**✅ تم فحص: {checked_count}/{len(self.video_db)} فيديو**\n"
                        f"**🧹 تم تنظيف: {cleaned_count} عنوان**\n"
                        f"**⏳ الوقت المنقضي: {elapsed_time} ثانية**"
                    )

            if self.operations_state["check_dp"]["running"] and not track_changes:
                elapsed_time = int(time.time() - self.operations_state["check_dp"]["start_time"])
                await self.notify_admin(
                    f"**✅ اكتمل تنظيف قاعدة البيانات**\n"
                    f"**📊 الإحصائيات النهائية:**\n"
                    f"**✅ تم فحص: {checked_count}/{len(self.video_db)} فيديو**\n"
                    f"**🧹 تم تنظيف: {cleaned_count} عنوان**\n"
                    f"**⏳ الوقت الكلي: {elapsed_time} ثانية**"
                )
                self.operations_state["check_dp"]["running"] = False
                logger.info(f"Database cleanup completed: {checked_count} checked, {cleaned_count} cleaned")
                if track_changes:
                    await self.notify_admin("**🔍 تتبع التغييرات في قاعدة البيانات مفعل**")

        except Exception as e:
            await self.notify_admin(f"**🚫 Error during database cleanup: {str(e)}**")
            logger.error(f"Database check error: {str(e)}")
            self.operations_state["check_dp"]["running"] = False

        self.operations_state["check_dp"]["checked_count"] = checked_count
        self.operations_state["check_dp"]["cleaned_count"] = cleaned_count

    async def scan_channel(self, channel_link: str):
        self.operations_state["scan"]["running"] = True
        self.operations_state["scan"]["channel"] = channel_link
        self.operations_state["scan"]["start_time"] = time.time()
        scanned_count = 0
        saved_count = 0
        last_title = ""

        self.scan_progress["last_message_id"] = 0
        self.save_scan_progress()

        try:
            channel_entity = await self.client.get_entity(channel_link)
            logger.info(f"Starting full scan of '{channel_entity.title}' from oldest to newest")

            async for message in self.client.iter_messages(channel_entity, reverse=True):
                if not self.operations_state["scan"]["running"]:
                    logger.info("Scan stopped by admin")
                    break
                scanned_count += 1
                if message.media and isinstance(message.media, MessageMediaDocument) and message.media.document.mime_type.startswith('video/'):
                    video_id = str(message.id)
                    if video_id not in self.video_db:
                        title = self.clean_title(message.text) if message.text else f"Video without title (ID: {video_id})"
                        self.video_db[video_id] = {"title": title, "channel": channel_link}
                        saved_count += 1
                        last_title = title
                        self.scan_progress["last_message_id"] = message.id
                        self.save_video_db()
                        self.save_scan_progress()

                if scanned_count % 100 == 0:
                    elapsed_time = int(time.time() - self.operations_state["scan"]["start_time"])
                    await self.notify_admin(
                        f"**🔍 جاري فحص القناة: {channel_entity.title}**\n"
                        f"**✅ تم فحص: {scanned_count} رسالة**\n"
                        f"**💾 تم حفظ: {saved_count} فيديو**\n"
                        f"**📌 آخر عنوان محفوظ: {last_title or 'لا يوجد'}**\n"
                        f"**⏳ الوقت المنقضي: {elapsed_time} ثانية**"
                    )

            if self.operations_state["scan"]["running"]:
                elapsed_time = int(time.time() - self.operations_state["scan"]["start_time"])
                await self.notify_admin(
                    f"**✅ اكتمل فحص القناة: {channel_entity.title}**\n"
                    f"**📊 الإحصائيات النهائية:**\n"
                    f"**✅ تم فحص: {scanned_count} رسالة**\n"
                    f"**💾 تم حفظ: {saved_count} فيديو**\n"
                    f"**📌 آخر عنوان محفوظ: {last_title or 'لا يوجد'}**\n"
                    f"**⏳ الوقت الكلي: {elapsed_time} ثانية**"
                )
                self.operations_state["scan"]["running"] = False
                logger.info(f"Scan completed: {scanned_count} scanned, {saved_count} saved")

        except Exception as e:
            await self.notify_admin(f"**🚫 Error during channel scan: {str(e)}**")
            logger.error(f"Scan error: {str(e)}")
            self.operations_state["scan"]["running"] = False

        self.operations_state["scan"]["scanned_count"] = scanned_count
        self.operations_state["scan"]["saved_count"] = saved_count
        self.operations_state["scan"]["last_title"] = last_title

    async def monitor_new_videos(self, event):
        if not self.search_channel or event.chat_id != (await self.client.get_entity(self.search_channel)).id:
            return
        message = event.message
        if message.media and isinstance(message.media, MessageMediaDocument) and message.media.document.mime_type.startswith('video/'):
            video_id = str(message.id)
            if video_id not in self.video_db:
                title = self.clean_title(message.text) if message.text else f"Video without title (ID: {video_id})"
                self.video_db[video_id] = {"title": title, "channel": self.search_channel}
                self.scan_progress["last_message_id"] = message.id
                self.operations_state["scan"]["last_title"] = title
                self.operations_state["scan"]["saved_count"] += 1
                self.save_video_db()
                self.save_scan_progress()
                logger.info(f"New video added to database: '{title}' (ID: {video_id})")
                await self.notify_admin(f"**✅ تم إضافة فيديو جديد إلى قاعدة البيانات: {title} (ID: {video_id})**")

            if self.operations_state["share"]["running"] and self.operations_state["share"]["from_channel"] == self.search_channel and self.operations_state["share"]["track_new"]:
                to_entity = await self.client.get_entity(self.operations_state["share"]["to_channel"])
                await self.client.send_file(to_entity, message.media, caption=self.clean_title(message.text), link_preview=False)
                self.operations_state["share"]["transferred_count"] += 1
                self.share_progress["last_message_id"] = message.id
                self.save_share_progress()
                logger.info(f"New video transferred: '{message.text}' (ID: {message.id})")

            if self.operations_state["check_cross"]["running"] and self.operations_state["check_cross"]["from_channel"] == self.search_channel and self.operations_state["check_cross"]["track_new"]:
                to_entity = await self.client.get_entity(self.operations_state["check_cross"]["to_channel"])
                to_channel_videos = {}
                async for msg in self.client.iter_messages(to_entity, limit=None):
                    if msg.media and isinstance(msg.media, MessageMediaDocument) and msg.media.document.mime_type.startswith('video/'):
                        title = self.clean_title(msg.text) if msg.text else f"Video without title (ID: {msg.id})"
                        to_channel_videos[title.lower()] = msg.id
                title = self.clean_title(message.text) if message.text else f"Video without title (ID: {message.id})"
                if title.lower() not in to_channel_videos:
                    await self.client.send_file(to_entity, message.media, caption=title, link_preview=False)
                    self.operations_state["check_cross"]["transferred_count"] += 1
                    self.operations_state["check_cross"]["last_message_id"] = message.id
                    self.video_db[video_id] = {"title": title, "channel": self.search_channel}
                    self.save_video_db()
                    logger.info(f"New video transferred in cross-check: '{title}' (ID: {message.id})")

    async def search_in_database(self, query: str) -> List[Tuple[str, str]]:
        results = []
        if query.isdigit():
            if query in self.video_db:
                results.append((self.video_db[query]["title"], query))
        else:
            for video_id, data in self.video_db.items():
                if query.lower() in data["title"].lower():
                    results.append((data["title"], video_id))
        return results

    async def get_video_from_channel(self, video_id: str) -> Optional[Message]:
        try:
            channel_entity = await self.client.get_entity(self.search_channel)
            message = await self.client.get_messages(channel_entity, ids=int(video_id))
            if message and message.media and isinstance(message.media, MessageMediaDocument) and message.media.document.mime_type.startswith('video/'):
                return message
            return None
        except Exception as e:
            logger.error(f"Error retrieving video ID {video_id}: {str(e)}")
            return None

    async def verify_with_gemini(self, search_term: str, result_text: str, username: str) -> bool:
        prompt = f"""أنت Zaky AI، بوت بحث عن الأفلام.
        - المستخدم @{username} طلب البحث عن: '{search_term}'.
        - تم العثور على نتيجة تحتوي على النص: '{result_text}'.
        تحقق مما إذا كانت النتيجة تتطابق مع الطلب:
        - إذا كانت تتطابق، أجب بـ 'نعم'.
        - إذا لم تتطابق، أجب بـ 'لا'.
        أجب فقط بـ 'نعم' أو 'لا':"""
        response = await chat_with_ai(prompt, username)
        return response.strip().lower() == "نعم"

    async def get_gemini_caption(self, movie_name: str, original_title: str, username: str) -> str:
        prompt = f"""أنت Zaky AI، بوت بحث عن الأفلام. اكتب وصفًا قصيرًا جدًا (جملة أو اثنتين بحد أقصى 150 حرفًا) لفيلم بالعربية فقط.
        - يجب أن يحتوي الوصف على اسم الفيلم بالعربية والإنجليزية بخط عريض باستخدام Markdown (مثل **فروزن** - **Frozen**).
        - اسم الفيلم هو: '{movie_name}'.
        أجب فقط بالوصف في Markdown:"""
        caption = await chat_with_ai(prompt, username)
        if len(caption) > 150:
            caption = caption[:147] + "..."
        if "مشكلة" in caption or not caption.strip():
            return f"**{original_title}** - **{original_title}**\n**قصة الفيلم غير متوفرة حالياً ♥️**"
        return caption

    async def process_video_result(self, message: Message, movie_name: str, message_id: int, username: str) -> Tuple[str, str, Message]:
        archive_channel_id = self.config["archive_channel_id"]
        if not archive_channel_id:
            logger.warning(f"Archive channel not set for @{username}")
            return None, None, None

        try:
            archive_channel_entity = await self.client.get_entity(archive_channel_id)
            caption = await self.get_gemini_caption(movie_name, message.text, username)
            sent_message = await self.client.send_file(
                archive_channel_entity,
                file=message.media,
                caption=caption,
                parse_mode='markdown',
                link_preview=False
            )
            post_link = f"https://t.me/archive4mv/{sent_message.id}"
            logger.info(f"Video sent to archive: '{post_link}' (ID: {message_id})")
            return post_link, movie_name, sent_message
        except Exception as e:
            logger.error(f"Error processing video: {str(e)}")
            return None, None, None

    async def get_stats(self) -> str:
        active_ops = sum(1 for op in self.operations_state.values() if op["running"])
        closed_ops = len(self.operations_state) - active_ops
        video_db_size = os.path.getsize(VIDEO_DB_FILE) / 1024 if os.path.exists(VIDEO_DB_FILE) else 0
        search_cache_size = os.path.getsize(SEARCH_CACHE_FILE) / 1024 if os.path.exists(SEARCH_CACHE_FILE) else 0
        search_history_size = os.path.getsize(SEARCH_HISTORY_FILE) / 1024 if os.path.exists(SEARCH_HISTORY_FILE) else 0

        return (
            f"**📊 إحصائيات البوت**\n"
            f"**🔧 الحالة العامة:**\n"
            f"**✅ العمليات النشطة: {active_ops}**\n"
            f"**⏹ العمليات المغلقة: {closed_ops}**\n\n"
            f"**🔍 إحصائيات أمر Sv (فحص القناة):**\n"
            f"**📌 القناة: {self.operations_state['scan']['channel'] or 'غير محددة'}**\n"
            f"**✅ تم فحص: {self.operations_state['scan']['scanned_count']} رسالة**\n"
            f"**💾 تم حفظ: {self.operations_state['scan']['saved_count']} فيديو**\n"
            f"**📍 آخر عنوان محفوظ: {self.operations_state['scan']['last_title'] or 'لا يوجد'}**\n\n"
            f"**🔄 إحصائيات أمر Share (النقل):**\n"
            f"**📌 من القناة: {self.operations_state['share']['from_channel'] or 'غير محددة'}**\n"
            f"**📌 إلى القناة: {self.operations_state['share']['to_channel'] or 'غير محددة'}**\n"
            f"**✅ تم النقل: {self.operations_state['share']['transferred_count']} فيديو**\n"
            f"**📍 آخر ID منقول: {self.share_progress.get('last_message_id', 0)}**\n\n"
            f"**🔍 إحصائيات أمر Check (الفحص):**\n"
            f"**📌 القناة: {self.operations_state['check']['channel'] or 'غير محددة'}**\n"
            f"**✅ تم فحص: {self.operations_state['check']['checked_count']} رسالة**\n"
            f"**🗑️ تم تنظيف: {self.operations_state['check']['cleaned_count']} عنوان**\n\n"
            f"**🔍 إحصائيات أمر Check Cross:**\n"
            f"**📌 من القناة: {self.operations_state['check_cross']['from_channel'] or 'غير محددة'}**\n"
            f"**📌 إلى القناة: {self.operations_state['check_cross']['to_channel'] or 'غير محددة'}**\n"
            f"**✅ تم فحص: {self.operations_state['check_cross']['checked_count']} فيديو**\n"
            f"**🔄 تم نقل: {self.operations_state['check_cross']['transferred_count']} فيديو**\n\n"
            f"**🔍 إحصائيات أمر Check dp:**\n"
            f"**✅ تم فحص: {self.operations_state['check_dp']['checked_count']} فيديو**\n"
            f"**🗑️ تم تنظيف: {self.operations_state['check_dp']['cleaned_count']} عنوان**\n\n"
            f"**📂 إحصائيات الملفات:**\n"
            f"**📜 قاعدة البيانات: {len(self.video_db)} فيديو ({video_db_size:.2f} كيلوبايت)**\n"
            f"**🔍 ذاكرة البحث: {len(self.search_cache)} نتيجة ({search_cache_size:.2f} كيلوبايت)**\n"
            f"**📋 سجل البحث: {len(self.search_history)} استعلام ({search_history_size:.2f} كيلوبايت)**"
        )

    async def initialize(self):
        await self.client.start(phone=PHONE_NUMBER)
        await self.check_functions()
        logger.info("Bot started with user account")

        if self.operations_state["share"]["running"] and self.share_progress["from_channel"] and self.share_progress["to_channel"]:
            self.operations_state["share"]["task"] = asyncio.create_task(
                self.share_videos(self.share_progress["from_channel"], self.share_progress["to_channel"], self.operations_state["share"]["track_new"])
            )
            logger.info("Resumed share operation on startup")

        if self.operations_state["scan"]["running"] and self.operations_state["scan"]["channel"]:
            self.scan_status_message = None
            self.operations_state["scan"]["task"] = asyncio.create_task(
                self.scan_channel(self.operations_state["scan"]["channel"])
            )
            logger.info("Resumed scan operation on startup")

        if self.operations_state["check"]["running"] and self.operations_state["check"]["channel"]:
            self.scan_status_message = None
            self.operations_state["check"]["task"] = asyncio.create_task(
                self.check_channel(self.operations_state["check"]["channel"], self.operations_state["check"]["track_new"])
            )
            logger.info("Resumed check operation on startup")

        if self.operations_state["check_cross"]["running"] and self.operations_state["check_cross"]["from_channel"] and self.operations_state["check_cross"]["to_channel"]:
            self.operations_state["check_cross"]["task"] = asyncio.create_task(
                self.check_cross_channels(self.operations_state["check_cross"]["from_channel"], self.operations_state["check_cross"]["to_channel"], self.operations_state["check_cross"]["track_new"])
            )
            logger.info("Resumed check_cross operation on startup")

        if self.operations_state["check_dp"]["running"]:
            self.scan_status_message = None
            self.operations_state["check_dp"]["task"] = asyncio.create_task(
                self.check_database(self.operations_state["check_dp"]["track_changes"])
            )
            logger.info("Resumed database check operation on startup")

        @self.client.on(events.NewMessage)
        async def handle_commands(event):
            sender = await event.get_sender()
            username = sender.username if sender.username else "مستخدم"
            text = event.message.text.strip()
            is_admin_user = await self.is_admin(sender.id, username)

            if text.lower() == "start":
                await event.respond(
                    "**أهلاً! أنا Zaky AI، بوت للبحث عن الأفلام 🎥**\n"
                    "**الأوامر المتاحة:**\n"
                    "**- `start`: عرض هذه القائمة**\n"
                    "**- `stats`: عرض إحصائيات البوت**\n"
                    "**- `s -ch [رابط]`: تعيين قناة للبحث الدائم**\n"
                    "**- `Sv [رابط]`: فحص قناة وحفظ بيانات الفيديوهات محليًا**\n"
                    "**- `check dp [on/off]`: فحص وتنظيف قاعدة البيانات**\n"
                    "**- `-ch -[رابط]`: تعيين قناة أرشيف (للأدمن)**\n"
                    "**- `share -from [رابط] -to [رابط] [on/off]`: نقل فيديوهات (للأدمن)**\n"
                    "**- `check -from [رابط] -to [رابط] [on/off]`: فحص ونقل الفيديوهات غير الموجودة (للأدمن)**\n"
                    "**- `stop share`: إيقاف النقل (للأدمن)**\n"
                    "**- `cont share`: استكمال النقل (للأدمن)**\n"
                    "**- `check [رابط] [on/off]`: فحص قناة (للأدمن)**\n"
                    "**- `stop check`: إيقاف الفحص (للأدمن)**\n"
                    "**- `cont check`: استكمال الفحص (للأدمن)**\n"
                    "**- `Sv stop`: إيقاف فحص القناة**\n"
                    "**- `Sv cont`: استكمال فحص القناة**\n"
                    "**- `stop`: إيقاف أي عملية جارية**\n"
                    "**- `Gp+ [رابط]`: إضافة جروب (للأدمن)**\n"
                    "**- `Gp- [رابط]`: حذف جروب (للأدمن)**\n"
                    "**- `mon`: عرض الجروبات (للأدمن)**\n"
                    "**- أي نص بعد نقطة (مثل .هاي): رد عبر الذكاء الاصطناعي (للأدمن)**\n"
                    "**- أي نص آخر: بحث عن فيلم**\n"
                    "**للتواصل مع الأدمن: @Zaky1million**",
                    parse_mode='markdown',
                    link_preview=False
                )
                return

            if text.lower() == "stats":
                stats = await self.get_stats()
                await event.respond(stats, parse_mode='markdown', link_preview=False)
                return

            if not is_admin_user:
                return

            if re.match(r'^s\s+-ch\s+(\S+)$', text, re.IGNORECASE):
                channel_link = re.match(r'^s\s+-ch\s+(\S+)$', text, re.IGNORECASE).group(1)
                try:
                    channel_entity = await self.client.get_entity(channel_link)
                    if not isinstance(channel_entity, Channel):
                        await event.respond("**هذا الرابط ليس قناة! ⚠️**", parse_mode='markdown', link_preview=False)
                        return
                    self.search_channel = channel_link
                    self.config["search_channel"] = channel_link
                    self.save_config()
                    await event.respond(f"**تم تعيين قناة البحث إلى: '{channel_entity.title}' ✅**", parse_mode='markdown', link_preview=False)
                    logger.info(f"Search channel set: '{channel_entity.title}' by @{username}")
                except Exception as e:
                    await event.respond("**خطأ في تعيين القناة! ⚠️**", parse_mode='markdown', link_preview=False)
                    logger.error(f"Error setting search channel: {e}")

            elif re.match(r'^Sv\s+(\S+)$', text, re.IGNORECASE):
                channel_link = re.match(r'^Sv\s+(\S+)$', text, re.IGNORECASE).group(1)
                if self.operations_state["scan"]["running"]:
                    await event.respond("**عملية فحص قناة قيد التنفيذ بالفعل! ⏳**", parse_mode='markdown', link_preview=False)
                    return
                self.scan_status_message = None
                self.operations_state["scan"]["task"] = asyncio.create_task(self.scan_channel(channel_link))

            elif text.lower() == "sv stop":
                if self.operations_state["scan"]["running"]:
                    self.operations_state["scan"]["running"] = False
                    if self.operations_state["scan"]["task"]:
                        self.operations_state["scan"]["task"].cancel()
                    await event.respond("**تم إيقاف فحص القناة! ⏹**", parse_mode='markdown', link_preview=False)
                    logger.info(f"Scan stopped by @{username}")
                else:
                    await event.respond("**لا توجد عملية فحص جارية! ⚠️**", parse_mode='markdown', link_preview=False)

            elif text.lower() == "sv cont":
                if self.operations_state["scan"]["running"]:
                    await event.respond("**عملية فحص قناة قيد التنفيذ بالفعل! ⏳**", parse_mode='markdown', link_preview=False)
                elif self.operations_state["scan"]["channel"]:
                    self.scan_status_message = None
                    self.operations_state["scan"]["task"] = asyncio.create_task(self.scan_channel(self.operations_state["scan"]["channel"]))
                    await event.respond("**تم استكمال فحص القناة! ▶️**", parse_mode='markdown', link_preview=False)
                    logger.info(f"Scan continued by @{username}")
                else:
                    await event.respond("**لا توجد عملية فحص سابقة لاستكمالها! ⚠️**", parse_mode='markdown', link_preview=False)

            elif re.match(r'^check\s+-from\s+(\S+)\s+-to\s+(\S+)(?:\s+(on|off))?$', text, re.IGNORECASE):
                match = re.match(r'^check\s+-from\s+(\S+)\s+-to\s+(\S+)(?:\s+(on|off))?$', text, re.IGNORECASE)
                from_channel = match.group(1)
                to_channel = match.group(2)
                track_new = match.group(3) == "on" if match.group(3) else False
                if self.operations_state["check_cross"]["running"]:
                    await event.respond("**عملية فحص تقاطع قيد التنفيذ بالفعل! ⏳**", parse_mode='markdown', link_preview=False)
                    return
                self.operations_state["check_cross"]["task"] = asyncio.create_task(self.check_cross_channels(from_channel, to_channel, track_new))
                await event.respond("**بدأ فحص التقاطع بين القنوات! 🔍**", parse_mode='markdown', link_preview=False)

            elif re.match(r'^share\s+-from\s+(\S+)\s+-to\s+(\S+)(?:\s+(on|off))?$', text, re.IGNORECASE):
                match = re.match(r'^share\s+-from\s+(\S+)\s+-to\s+(\S+)(?:\s+(on|off))?$', text, re.IGNORECASE)
                from_channel = match.group(1)
                to_channel = match.group(2)
                track_new = match.group(3) == "on" if match.group(3) else False
                if self.operations_state["share"]["running"]:
                    await event.respond("**عملية نقل قيد التنفيذ بالفعل! ⏳**", parse_mode='markdown', link_preview=False)
                    return
                self.share_progress["from_channel"] = from_channel
                self.share_progress["to_channel"] = to_channel
                self.save_share_progress()
                self.operations_state["share"]["task"] = asyncio.create_task(self.share_videos(from_channel, to_channel, track_new))
                await event.respond("**بدأ نقل الفيديوهات! 🔄**", parse_mode='markdown', link_preview=False)

            elif text.lower() == "stop share":
                if self.operations_state["share"]["running"]:
                    self.operations_state["share"]["running"] = False
                    if self.operations_state["share"]["task"]:
                        self.operations_state["share"]["task"].cancel()
                    await event.respond("**تم إيقاف النقل! ⏹**", parse_mode='markdown', link_preview=False)
                    logger.info(f"Share stopped by @{username}")
                else:
                    await event.respond("**لا توجد عملية نقل جارية! ⚠️**", parse_mode='markdown', link_preview=False)

            elif text.lower() == "cont share":
                if self.operations_state["share"]["running"]:
                    await event.respond("**عملية نقل قيد التنفيذ بالفعل! ⏳**", parse_mode='markdown', link_preview=False)
                elif "from_channel" in self.share_progress and self.share_progress["from_channel"] and "to_channel" in self.share_progress and self.share_progress["to_channel"]:
                    self.operations_state["share"]["task"] = asyncio.create_task(
                        self.share_videos(self.share_progress["from_channel"], self.share_progress["to_channel"], self.operations_state["share"]["track_new"])
                    )
                    await event.respond("**تم استكمال النقل! ▶️**", parse_mode='markdown', link_preview=False)
                    logger.info(f"Share continued by @{username}")
                else:
                    await event.respond("**لا توجد عملية نقل سابقة لاستكمالها! ⚠️**", parse_mode='markdown', link_preview=False)

            elif re.match(r'^check\s+(\S+)(?:\s+(on|off))?$', text, re.IGNORECASE):
                match = re.match(r'^check\s+(\S+)(?:\s+(on|off))?$', text, re.IGNORECASE)
                channel_link = match.group(1)
                track_new = match.group(2) == "on" if match.group(2) else False
                if self.operations_state["check"]["running"]:
                    await event.respond("**عملية فحص قيد التنفيذ بالفعل! ⏳**", parse_mode='markdown', link_preview=False)
                    return
                self.operations_state["check"]["task"] = asyncio.create_task(self.check_channel(channel_link, track_new))
                await event.respond("**بدأ فحص القناة! 🔍**", parse_mode='markdown', link_preview=False)

            elif text.lower() == "stop check":
                if self.operations_state["check"]["running"]:
                    self.operations_state["check"]["running"] = False
                    if self.operations_state["check"]["task"]:
                        self.operations_state["check"]["task"].cancel()
                    await event.respond("**تم إيقاف فحص القناة! ⏹**", parse_mode='markdown', link_preview=False)
                    logger.info(f"Check stopped by @{username}")
                else:
                    await event.respond("**لا توجد عملية فحص جارية! ⚠️**", parse_mode='markdown', link_preview=False)

            elif text.lower() == "cont check":
                if self.operations_state["check"]["running"]:
                    await event.respond("**عملية فحص قيد التنفيذ بالفعل! ⏳**", parse_mode='markdown', link_preview=False)
                elif self.operations_state["check"]["channel"]:
                    self.scan_status_message = None
                    self.operations_state["check"]["task"] = asyncio.create_task(
                        self.check_channel(self.operations_state["check"]["channel"], self.operations_state["check"]["track_new"])
                    )
                    await event.respond("**تم استكمال فحص القناة! ▶️**", parse_mode='markdown', link_preview=False)
                    logger.info(f"Check continued by @{username}")
                else:
                    await event.respond("**لا توجد عملية فحص سابقة لاستكمالها! ⚠️**", parse_mode='markdown', link_preview=False)

            elif re.match(r'^check\s+dp(?:\s+(on|off))?$', text, re.IGNORECASE):
                match = re.match(r'^check\s+dp(?:\s+(on|off))?$', text, re.IGNORECASE)
                track_changes = match.group(1) == "on" if match.group(1) else False
                if self.operations_state["check_dp"]["running"]:
                    await event.respond("**عملية فحص قاعدة البيانات قيد التنفيذ بالفعل! ⏳**", parse_mode='markdown', link_preview=False)
                    return
                self.scan_status_message = None
                self.operations_state["check_dp"]["task"] = asyncio.create_task(self.check_database(track_changes))
                await event.respond("**بدأ تنظيف قاعدة البيانات! 🔍**", parse_mode='markdown', link_preview=False)

            elif text.lower() == "stop":
                stopped = False
                for op in ["share", "check", "scan", "check_cross", "check_dp"]:
                    if self.operations_state[op]["running"]:
                        self.operations_state[op]["running"] = False
                        if self.operations_state[op]["task"]:
                            self.operations_state[op]["task"].cancel()
                        stopped = True
                if stopped:
                    await event.respond("**تم إيقاف جميع العمليات الجارية! ⏹**", parse_mode='markdown', link_preview=False)
                    logger.info(f"All operations stopped by @{username}")
                else:
                    await event.respond("**لا توجد عمليات جارية لإيقافها! ⚠️**", parse_mode='markdown', link_preview=False)

        @self.client.on(events.NewMessage)
        async def handle_all_messages(event):
            chat = await event.get_chat()
            sender = await event.get_sender()
            username = sender.username if sender.username else "مستخدم"
            is_admin_user = await self.is_admin(sender.id, username)
            text = event.message.text.strip()

            if isinstance(chat, Channel):
                return
            if isinstance(chat, Chat) and chat.id not in self.allowed_groups:
                return

            if isinstance(chat, User) and is_admin_user and text.startswith('.'):
                response = await chat_with_ai(text[1:].strip(), username)
                await event.respond(f"**{response}**", parse_mode='markdown', link_preview=False)
                logger.info(f"AI response sent to @{username}")
                return

            command_prefixes = ["start", "stats", "sv ", "s -ch", "-ch -", "share ", "stop", "cont", "check ", "gp+", "gp-", "mon"]
            if any(text.lower().startswith(cmd) for cmd in command_prefixes):
                return

            query = self.clean_title(text)
            if not query:
                return

            initial_msg = await event.respond(f"**جاري البحث عن '{query}' 🔍**", parse_mode='markdown', link_preview=False)

            if not self.search_channel:
                await initial_msg.edit("**عذرًا، لم يتم تحديد قناة بحث! سيتم حل المشكلة قريبًا ⚠️**", parse_mode='markdown', link_preview=False)
                await self.notify_admin(f"**🚫 Search channel not set by @{username}**", is_search_notification=True)
                return
            if not self.video_db:
                await initial_msg.edit("**عذرًا، قاعدة بيانات الفيديوهات غير جاهزة بعد! استخدم Sv [رابط] لتحديثها ⚠️**", parse_mode='markdown', link_preview=False)
                await self.notify_admin(f"**🚫 Database empty, @{username} tried searching for '{query}'**", is_search_notification=True)
                return

            if query in self.search_cache:
                post_link = self.search_cache[query]["link"]
                title = self.search_cache[query]["title"]
                await initial_msg.edit(f"**فيلم: [{title}]({post_link})**\n**الرابط: [اضغط هنا ♥️]({post_link})**", parse_mode='markdown', link_preview=False)
                logger.info(f"Cached result sent for '{query}' to @{username}")
                return

            search_results = await self.search_in_database(query)
            if search_results:
                if len(search_results) == 1:
                    title, video_id = search_results[0]
                    message = await self.get_video_from_channel(video_id)
                    if message:
                        post_link, title, sent_message = await self.process_video_result(message, title, int(video_id), username)
                        if post_link:
                            await initial_msg.edit(
                                f"**فيلم: [{title}]({post_link})**\n**الرابط: [اضغط هنا ♥️]({post_link})**",
                                parse_mode='markdown',
                                link_preview=False
                            )
                            self.search_cache[query] = {"link": post_link, "title": title}
                            self.save_search_cache()
                            logger.info(f"Single result sent and cached for '{query}'")
                        else:
                            await initial_msg.edit("**خطأ أثناء التحويل إلى الأرشيف ❌**", parse_mode='markdown', link_preview=False)
                    else:
                        await initial_msg.edit(f"**لم يتم العثور على الفيديو في القناة! ❌**", parse_mode='markdown', link_preview=False)
                else:
                    response = f"**نتائج البحث عن: {query} 🔍**\n\n**دوس على الـ ID الخاص بالنتيجة التي تريدها وسيتم نسخه، ثم ارسله اليّ ✏️**\n\n"
                    emoji_numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
                    for i, (title, video_id) in enumerate(search_results[:10], 0):
                        response += f"{emoji_numbers[i]} Film: {title}\n🆔 ID: `{video_id}`\n\n"
                    response += "**تحت اسم الفيلم في كود ID ، دوس عليه و هيتم نسخ الـ ID ده و ابعته للبحث بدقة! 📌**"
                    await initial_msg.edit(response, parse_mode='markdown', link_preview=False)
                    logger.info(f"Multiple results sent for '{query}'")
            else:
                await initial_msg.edit(f"**لم أجد فيديو لـ '{query}' ❌**", parse_mode='markdown', link_preview=False)
                await self.notify_admin(f"**🚫 @{username} searched for '{query}' with no results**", is_search_notification=True)
                logger.info(f"No results found for '{query}'")

        @self.client.on(events.NewMessage)
        async def monitor(event):
            await self.monitor_new_videos(event)

        logger.info("Event handlers started")
        await self.client.run_until_disconnected()

    async def check_functions(self):
        logger.info("Checking critical functions")
        try:
            await self.client.get_me()
            logger.info("TelegramClient connection is working")
        except Exception as e:
            logger.error(f"TelegramClient connection failed: {str(e)}")
        try:
            await self.notify_admin("**اختبار وظيفة الإشعار**")
            logger.info("notify_admin function is working")
        except Exception as e:
            logger.error(f"notify_admin function failed: {str(e)}")

    async def check_ai(self):
        try:
            await chat_with_ai("اختبار", "test_user")
            logger.info("chat_with_ai function is working")
        except Exception as e:
            logger.error(f"chat_with_ai function failed: {str(e)}")

    async def run(self):
        try:
            await self.initialize()
        except Exception as e:
            logger.error(f"Failed to run bot: {str(e)}")

if __name__ == '__main__':
    bot = MovieBot()
    from control_bot import ControlBot
    control_bot = ControlBot(bot)

    async def main():
        await asyncio.gather(
            bot.initialize(),
            control_bot.run()
        )

    asyncio.run(main())
