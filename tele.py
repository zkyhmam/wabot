import os
import asyncio
import logging
from typing import Optional, Union, Dict, List, Any
import json
import random
import string
import re
from urllib.parse import quote, urlparse
from datetime import datetime

import aiohttp
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, Message
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from telegram.constants import ParseMode
from dotenv import load_dotenv

# تحميل المتغيرات البيئية
load_dotenv()

# إعداد السجل (Logging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# المفاتيح والإعدادات الأساسية (ستأتي من ملف .env)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BEARER_TOKEN = os.getenv("TMDB_BEARER_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(id) for id in ADMIN_IDS_STR.split(',') if id.strip().isdigit()]
DEVELOPER_USERNAME = os.getenv("DEVELOPER_USERNAME", "zaky1million")
DEFAULT_START_IMAGE = os.getenv("DEFAULT_START_IMAGE", "https://i.imgur.com/dZcDEQL.jpeg")
DEFAULT_START_MESSAGE = os.getenv("DEFAULT_START_MESSAGE",
    "👋 أهلاً بك في بوت الأفلام والمسلسلات!\n\n"
    "يمكنك استخدام هذا البوت للبحث عن معلومات حول أفلامك ومسلسلاتك المفضلة.\n\n"
    "🔍 ببساطة أرسل لي اسم الفيلم أو المسلسل وسأقوم بإيجاده لك.\n\n"
    "مثال: The Godfather أو الوحش"
)

# URLs الأساسية
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/original"
GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

# ملفات البيانات
CONFIG_FILE = "config.json"
USAGE_STATS_FILE = "usage_stats.json"

# التخزين المؤقت والمتغيرات العالمية
poster_cache = {}
media_data = {}
user_states = {} # تخزين حالة المستخدم

# هياكل البيانات
class BotConfig:
    def __init__(self):
        self.forced_channels = []
        self.start_message = DEFAULT_START_MESSAGE
        self.start_image = DEFAULT_START_IMAGE

        self.load()

    def load(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.forced_channels = data.get('forced_channels', [])
                    self.start_message = data.get('start_message', DEFAULT_START_MESSAGE)
                    self.start_image = data.get('start_image', DEFAULT_START_IMAGE)
        except Exception as e:
            logger.error(f"خطأ في تحميل الإعدادات: {e}")

    def save(self):
        try:
            data = {
                'forced_channels': self.forced_channels,
                'start_message': self.start_message,
                'start_image': self.start_image
            }
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"خطأ في حفظ الإعدادات: {e}")

class UsageStats:
    def __init__(self):
        self.users = {}
        self.total_searches = 0
        self.daily_searches = {}

        self.load()

    def load(self):
        try:
            if os.path.exists(USAGE_STATS_FILE):
                with open(USAGE_STATS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.users = data.get('users', {})
                    self.total_searches = data.get('total_searches', 0)
                    self.daily_searches = data.get('daily_searches', {})
        except Exception as e:
            logger.error(f"خطأ في تحميل إحصائيات الاستخدام: {e}")

    def save(self):
        try:
            data = {
                'users': self.users,
                'total_searches': self.total_searches,
                'daily_searches': self.daily_searches
            }
            with open(USAGE_STATS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"خطأ في حفظ إحصائيات الاستخدام: {e}")

    def add_user(self, user_id, username=None, first_name=None):
        user_id_str = str(user_id)
        if user_id_str not in self.users:
            self.users[user_id_str] = {
                'username': username,
                'first_name': first_name,
                'join_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'searches': 0,
                'last_activity': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        else:
            self.users[user_id_str]['last_activity'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if username:
                self.users[user_id_str]['username'] = username
            if first_name:
                self.users[user_id_str]['first_name'] = first_name

        self.save()

    def log_search(self, user_id):
        user_id_str = str(user_id)
        today = datetime.now().strftime('%Y-%m-%d')

        # تحديث إحصائيات المستخدم
        if user_id_str in self.users:
            self.users[user_id_str]['searches'] += 1
            self.users[user_id_str]['last_activity'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # تحديث إجمالي البحث
        self.total_searches += 1

        # تحديث البحث اليومي
        if today not in self.daily_searches:
            self.daily_searches[today] = 0
        self.daily_searches[today] += 1

        self.save()

# إنشاء كائنات البيانات
config = BotConfig()
stats = UsageStats()

# وظائف مساعدة
def generate_unique_id(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_emoji_options():
    emojis = ["💭", "👁️", "🎬", "🍿", "🎞️", "📺", "🎦", "🔍", "📽️", "🎥"]
    return emojis

def extract_url(text):
    url_pattern = r'(https?://\S+)'
    match = re.search(url_pattern, text)
    return match.group(1) if match else None

async def check_user_subscription(user_id, context):
    if not config.forced_channels:
        return True

    for channel in config.forced_channels:
        try:
            member = await context.bot.get_chat_member(chat_id=channel['id'], user_id=user_id)
            status = member.status
            if status in ['creator', 'administrator', 'member']:
                continue
            else:
                return False
        except Exception as e:
            logger.error(f"خطأ في التحقق من اشتراك المستخدم: {e}")
            continue

    return True

# دوال معالجة TMDB والصور
async def get_image_url(media_data: Dict[str, Any], session: aiohttp.ClientSession) -> str:
    media_id = media_data.get('id')

    if media_id in poster_cache:
        logger.info(f"استخدام صورة مخزنة للوسائط {media_id}")
        return poster_cache[media_id]

    try:
        if media_data.get('backdrop_path'):
            image_url = f"{TMDB_IMAGE_BASE_URL}{media_data['backdrop_path']}"
            poster_cache[media_id] = image_url
            return image_url

        if media_data.get('poster_path'):
            image_url = f"{TMDB_IMAGE_BASE_URL}{media_data['poster_path']}"
            poster_cache[media_id] = image_url
            return image_url

        media_title = media_data.get('title') or media_data.get('name', '')
        media_year = ""

        if media_data.get('release_date'):
            media_year = media_data['release_date'][:4]
        elif media_data.get('first_air_date'):
            media_year = media_data['first_air_date'][:4]

        search_query = f"{media_title} {media_year} movie poster 16:9"

        params = {
            'key': GOOGLE_API_KEY,
            'cx': GOOGLE_CSE_ID,
            'q': search_query,
            'searchType': 'image',
            'imgSize': 'large',
            'imgType': 'photo',
            'num': 1
        }

        async with session.get(GOOGLE_SEARCH_URL, params=params) as response:
            if response.status == 200:
                data = await response.json()
                items = data.get('items', [])
                if items:
                    image_url = items[0]['link']
                    poster_cache[media_id] = image_url
                    return image_url

    except Exception as e:
        logger.error(f"خطأ في الحصول على صورة: {e}")

    if media_data.get('poster_path'):
        image_url = f"{TMDB_IMAGE_BASE_URL}{media_data['poster_path']}"
        poster_cache[media_id] = image_url
        return image_url

    return "https://via.placeholder.com/1280x720?text=No+Image+Available"

async def search_tmdb(query: str, session: aiohttp.ClientSession) -> Dict:
    try:
        params = {
            'api_key': TMDB_API_KEY,
            'query': query,
            'language': 'ar-SA',
            'include_adult': 'false'
        }

        headers = {
            'Authorization': f'Bearer {TMDB_BEARER_TOKEN}',
            'Content-Type': 'application/json;charset=utf-8'
        }

        async with session.get(f"{TMDB_BASE_URL}/search/multi", params=params, headers=headers) as response:
            if response.status != 200:
                params['language'] = 'en-US'
                async with session.get(f"{TMDB_BASE_URL}/search/multi", params=params, headers=headers) as en_response:
                    return await en_response.json()
            return await response.json()

    except Exception as e:
        logger.error(f"خطأ في البحث في TMDB: {e}")
        return {"results": []}

async def get_media_details(media_id: int, media_type: str, session: aiohttp.ClientSession) -> Dict:
    try:
        params = {
            'api_key': TMDB_API_KEY,
            'language': 'ar-SA',
            'append_to_response': 'credits,videos,images'
        }

        headers = {
            'Authorization': f'Bearer {TMDB_BEARER_TOKEN}',
            'Content-Type': 'application/json;charset=utf-8'
        }

        async with session.get(f"{TMDB_BASE_URL}/{media_type}/{media_id}", params=params, headers=headers) as response:
            if response.status != 200:
                params['language'] = 'en-US'
                async with session.get(f"{TMDB_BASE_URL}/{media_type}/{media_id}", params=params, headers=headers) as en_response:
                    return await en_response.json()
            return await response.json()

    except Exception as e:
        logger.error(f"خطأ في الحصول على تفاصيل الوسائط: {e}")
        return {}

async def search_another_image(media_data: Dict[str, Any], session: aiohttp.ClientSession) -> str:
    try:
        media_title = media_data.get('title') or media_data.get('name', '')
        media_year = ""

        if media_data.get('release_date'):
            media_year = media_data['release_date'][:4]
        elif media_data.get('first_air_date'):
            media_year = media_data['first_air_date'][:4]

        search_query = f"{media_title} {media_year} movie poster 16:9"

        random_offset = random.randint(1, 10)

        params = {
            'key': GOOGLE_API_KEY,
            'cx': GOOGLE_CSE_ID,
            'q': search_query,
            'searchType': 'image',
            'imgSize': 'large',
            'imgType': 'photo',
            'num': 1,
            'start': random_offset
        }

        async with session.get(GOOGLE_SEARCH_URL, params=params) as response:
            if response.status == 200:
                data = await response.json()
                items = data.get('items', [])
                if items:
                    return items[0]['link']

    except Exception as e:
        logger.error(f"خطأ في البحث عن صورة بديلة: {e}")

    if media_data.get('backdrop_path'):
        return f"{TMDB_IMAGE_BASE_URL}{media_data['backdrop_path']}"
    elif media_data.get('poster_path'):
        return f"{TMDB_IMAGE_BASE_URL}{media_data['poster_path']}"

    return "https://via.placeholder.com/1280x720?text=No+Image+Available"

# وظائف تنسيق الرسائل
def format_media_message(media_data: Dict[str, Any], emoji: str = "💭") -> str:
    # الحصول على العناوين العربية والإنجليزية
    arabic_title = media_data.get('title') or media_data.get('name', '')
    english_title = media_data.get('original_title') or media_data.get('original_name', '')

    # استخدام العنوان الأصلي إذا كان العنوان الرئيسي بالإنجليزية والعكس
    if re.match(r'^[a-zA-Z0-9\s\W]+$', arabic_title) and arabic_title != english_title:
        arabic_title, english_title = english_title, arabic_title

    # جلب الوصف
    overview = media_data.get('overview', 'معلومات غير متوفرة')

    # تنسيق الرسالة (مع تسطير)
    title = f"<u>{arabic_title} | {english_title}</u>"  #  تسطير العنوان باستخدام HTML
    message = f"{title}\n\n{overview}\n\n{emoji} للمشاهدة اضغط هنا"

    return message

# معالجة الأوامر
async def start_command(update: Update, context: CallbackContext) -> None:
    user = update.effective_user

    # تسجيل المستخدم الجديد
    stats.add_user(user.id, user.username, user.first_name)

    # التحقق من الاشتراك الإجباري
    is_subscribed = await check_user_subscription(user.id, context)

    if not is_subscribed:
        keyboard = []
        for channel in config.forced_channels:
            keyboard.append([InlineKeyboardButton(f"📢 {channel['title']}", url=channel['url'])])

        keyboard.append([InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subscription")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "⚠️ يجب عليك الاشتراك في القناة/القنوات التالية لاستخدام البوت:\n\n"
            "اضغط على زر تحقق من الاشتراك بعد الانتهاء من الاشتراك.",
            reply_markup=reply_markup
        )
        return

    # التحقق إذا كان المستخدم من المشرفين
    if is_admin(user.id):
        keyboard = [
            [InlineKeyboardButton("➕ إضافة قناة اشتراك إجباري", callback_data="admin_add_channel")],
            [InlineKeyboardButton("✏️ تعديل رسالة البداية", callback_data="admin_edit_start_message")],
            [InlineKeyboardButton("🖼️ تغيير صورة البداية", callback_data="admin_change_start_image")],
            [InlineKeyboardButton("📊 إحصائيات البوت", callback_data="admin_stats")],
            [InlineKeyboardButton("➕ إضافة مشرف", callback_data="admin_add_admin")]
        ]

        admin_reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"👑 <b>وضع المشرف</b>\n\n"
            f"مرحباً {user.first_name}، أنت مشرف في هذا البوت.\n"
            f"يمكنك استخدام الأوامر التالية:",
            reply_markup=admin_reply_markup,
            parse_mode=ParseMode.HTML
        )
    else: # مستخدم عادي
        # إرسال رسالة الترحيب العادية
        keyboard = [[InlineKeyboardButton("👨‍💻 التواصل مع المطور", url=f"https://t.me/{DEVELOPER_USERNAME}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await update.message.reply_photo(
                photo=config.start_image,
                caption=config.start_message,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"خطأ في إرسال رسالة البداية: {e}")
            await update.message.reply_text(
                config.start_message,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )

async def help_command(update: Update, context: CallbackContext) -> None:
    # التحقق من الاشتراك الإجباري
    is_subscribed = await check_user_subscription(update.effective_user.id, context)

    if not is_subscribed:
        keyboard = []
        for channel in config.forced_channels:
            keyboard.append([InlineKeyboardButton(f"📢 {channel['title']}", url=channel['url'])])

        keyboard.append([InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subscription")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "⚠️ يجب عليك الاشتراك في القناة/القنوات التالية لاستخدام البوت:\n\n"
            "اضغط على زر تحقق من الاشتراك بعد الانتهاء من الاشتراك.",
            reply_markup=reply_markup
        )
        return

    help_message = (
        "📌 <b>كيفية استخدام البوت:</b>\n\n"
        "1️⃣ للبحث عن فيلم أو مسلسل، أرسل اسمه فقط.\n"
        "2️⃣ يمكنك البحث باللغة العربية أو الإنجليزية.\n"
        "3️⃣ للبحث عن فيلم محدد، يمكنك إضافة سنة الإصدار بعد اسم الفيلم.\n"
        "4️⃣ بعد عرض النتيجة، يمكنك إضافة رابط المشاهدة من خلال الضغط على زر 'إضافة رابط'.\n"
        "5️⃣ يمكنك البحث عن صورة أخرى بالضغط على زر 'صورة أخرى'.\n"
        "6️⃣ يمكنك تغيير الرمز التعبيري قبل 'للمشاهدة اضغط هنا' بالضغط على زر 'تغيير الرمز'.\n\n"
        "🔸 <b>أمثلة:</b>\n"
        "- Inception\n"
        "- الوحش\n"
        "- Spider-Man 2002\n"
        "- مسلسل الاختيار"
    )

    keyboard = [[InlineKeyboardButton("👨‍💻 التواصل مع المطور", url=f"https://t.me/{DEVELOPER_USERNAME}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(help_message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

# معالجة الرسائل والبحث
async def handle_message(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    query = update.message.text.strip()

    # تسجيل المستخدم
    stats.add_user(user.id, user.username, user.first_name)

    # التحقق إذا كان المستخدم في انتظار إدخال شيء
    user_id_str = str(user.id)

    # التحقق من حالة انتظار المستخدم
    if user_id_str in user_states:
        state = user_states[user_id_str]

        if state.get('type') == 'admin_add_channel':
            # معالجة إضافة قناة اشتراك إجباري
            if state.get('step') == 'waiting_for_channel_id':
                # حفظ معرف القناة
                channel_id = query.strip()
                user_states[user_id_str]['channel_id'] = channel_id
                user_states[user_id_str]['step'] = 'waiting_for_channel_title'

                await update.message.reply_text("✅ تم حفظ معرف القناة، الآن أرسل عنوان القناة (مثال: قناة الأفلام)")
                return

            elif state.get('step') == 'waiting_for_channel_title':
                # حفظ عنوان القناة
                channel_title = query.strip()
                user_states[user_id_str]['channel_title'] = channel_title
                user_states[user_id_str]['step'] = 'waiting_for_channel_url'

                await update.message.reply_text("✅ تم حفظ عنوان القناة، الآن أرسل رابط القناة (مثال: https://t.me/channel)")
                return

            elif state.get('step') == 'waiting_for_channel_url':
                # حفظ رابط القناة وإنهاء العملية
                channel_url = query.strip()
                channel_id = user_states[user_id_str].get('channel_id')
                channel_title = user_states[user_id_str].get('channel_title')

                config.forced_channels.append({
                    'id': channel_id,
                    'title': channel_title,
                    'url': channel_url
                })

                config.save()

                # إنهاء حالة الانتظار
                del user_states[user_id_str]

                await update.message.reply_text(f"✅ تم إضافة القناة بنجاح!")
                return

        elif state.get('type') == 'admin_edit_start_message':
            # تحديث رسالة البداية
            config.start_message = query
            config.save()

            # إنهاء حالة الانتظار
            del user_states[user_id_str]

            await update.message.reply_text("✅ تم تحديث رسالة البداية بنجاح!")
            return

        elif state.get('type') == 'admin_change_start_image':
            # تحديث صورة البداية من رابط
            config.start_image = query
            config.save()

            # إنهاء حالة الانتظار
            del user_states[user_id_str]

            await update.message.reply_text("✅ تم تحديث رابط صورة البداية بنجاح!")
            return

        elif state.get('type') == 'admin_add_admin':
            # إضافة مشرف جديد
            try:
                new_admin_id = int(query.strip())
                if new_admin_id not in ADMIN_IDS:
                    ADMIN_IDS.append(new_admin_id)

                    # تحديث البيئة (بشكل صحيح)
                    admin_ids_str = ",".join(map(str, ADMIN_IDS))
                    with open(".env", "r") as f:
                        lines = f.readlines()
                    with open(".env", "w") as f:
                        for line in lines:
                            if line.startswith("ADMIN_IDS="):
                                f.write(f"ADMIN_IDS={admin_ids_str}\n")
                            else:
                                f.write(line)
                        # لو مش موجود
                        if not any(line.startswith("ADMIN_IDS=") for line in lines):
                            f.write(f"ADMIN_IDS={admin_ids_str}\n")


                    await update.message.reply_text(f"✅ تم إضافة المشرف الجديد (ID: {new_admin_id}) بنجاح!")
                else:
                    await update.message.reply_text(f"❌ المشرف (ID: {new_admin_id}) موجود بالفعل.")

                # إنهاء حالة الانتظار
                del user_states[user_id_str]
                return
            except ValueError:
                await update.message.reply_text("❌ الرجاء إدخال رقم صحيح فقط كمعرف المستخدم")
                return

        elif state.get('type') == 'add_link':
            # معالجة إضافة رابط
            media_id = state.get('media_id')
            if not media_id or media_id not in media_data:
                await update.message.reply_text("❌ حدث خطأ: لم يتم العثور على بيانات الفيلم/المسلسل.")
                if user_id_str in user_states:
                    del user_states[user_id_str]
                return

            extracted_link = extract_url(query)
            if extracted_link:
                # حفظ الرابط
                media_data[media_id]['link'] = extracted_link
                del user_states[user_id_str]

                # تحديث الرسالة (مع رابط تشعبي)
                message_text = format_media_message(media_data[media_id]['details'], media_data[media_id]['emoji'])
                caption = f"{message_text.split(' للمشاهدة')[0]} <a href='{extracted_link}'>للمشاهدة اضغط هنا</a>"

                keyboard = [
                    [
                        InlineKeyboardButton("🔄 تغيير الرابط", callback_data=f"add_link_{media_id}"),
                        InlineKeyboardButton("🖼️ صورة أخرى", callback_data=f"another_image_{media_id}"),
                    ],
                    [InlineKeyboardButton("✏️ تغيير الرمز", callback_data=f"change_emoji_{media_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text(f"✅ تم حفظ الرابط بنجاح: {extracted_link}")

                # إرسال الصورة مع التسمية التوضيحية (caption) المحدثة
                await update.message.reply_photo(
                    photo=media_data[media_id]['image_url'],
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML  #  هام:  لتفعيل الروابط التشعبية والتسطير
                )
            else:
                # رابط غير صالح
                keyboard = [
                    [InlineKeyboardButton("🔄 إعادة المحاولة", callback_data=f"add_link_{media_id}")],
                    [InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_link_{media_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text("❌ الرابط غير صالح.  الرجاء إرسال رابط صحيح يبدأ بـ `http://` أو `https://`.", reply_markup=reply_markup)
            return

        elif state.get('type') == 'change_emoji':
            # معالجة تغيير الإيموجي
            media_id = state.get('media_id')
            new_emoji = query.strip()

            if not media_id or media_id not in media_data:
                await update.message.reply_text("❌ حدث خطأ: لم يتم العثور على بيانات الفيلم/المسلسل.")
                if user_id_str in user_states:
                    del user_states[user_id_str]
                return

            if new_emoji in get_emoji_options():
                media_data[media_id]['emoji'] = new_emoji
                del user_states[user_id_str]

                # تحديث الرسالة
                message_text = format_media_message(media_data[media_id]['details'], new_emoji)
                if media_data[media_id]['link']:
                    caption = f"{message_text.split(' للمشاهدة')[0]} <a href='{media_data[media_id]['link']}'>للمشاهدة اضغط هنا</a>"
                else:
                    caption = message_text

                keyboard = [
                    [
                        InlineKeyboardButton("➕ إضافة رابط", callback_data=f"add_link_{media_id}"),
                        InlineKeyboardButton("🖼️ صورة أخرى", callback_data=f"another_image_{media_id}"),
                    ],
                    [InlineKeyboardButton("✏️ تغيير الرمز", callback_data=f"change_emoji_{media_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_photo(
                    photo=media_data[media_id]['image_url'],
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML  #  هام لتفعيل التنسيق
                )

            else:
                # رمز تعبيري غير صالح
                await update.message.reply_text("❌ الرمز التعبيري غير صالح.  الرجاء الاختيار من القائمة.")
            return

    # التحقق من الاشتراك الإجباري (خارج user_states)
    is_subscribed = await check_user_subscription(user.id, context)
    if not is_subscribed:
        keyboard = []
        for channel in config.forced_channels:
            keyboard.append([InlineKeyboardButton(f"📢 {channel['title']}", url=channel['url'])])
        keyboard.append([InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subscription")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "⚠️ يجب عليك الاشتراك في القناة/القنوات التالية لاستخدام البوت:\n\n"
            "اضغط على زر تحقق من الاشتراك بعد الانتهاء من الاشتراك.",
            reply_markup=reply_markup
        )
        return

    # إذا لم يكن المستخدم في حالة انتظار، قم بالبحث عن الفيلم/المسلسل
    if len(query) < 2:
        await update.message.reply_text("⚠️ الرجاء إدخال اسم أطول للبحث")
        return

    searching_message = await update.message.reply_text("🔍 جاري البحث... برجاء الانتظار")

    async with aiohttp.ClientSession() as session:
        search_results = await search_tmdb(query, session)

        filtered_results = [
            item for item in search_results.get('results', [])
            if item.get('media_type') in ['movie', 'tv'] and (item.get('poster_path') is not None or item.get('backdrop_path') is not None)
        ]

        if not filtered_results:
            await searching_message.edit_text("❌ لم يتم العثور على نتائج. حاول البحث باسم آخر.")
            return

        first_result = filtered_results[0]
        media_type = first_result.get('media_type')
        media_id = first_result.get('id')

        media_details = await get_media_details(media_id, media_type, session)

        if not media_details:
            await searching_message.edit_text("❌ حدث خطأ أثناء جلب التفاصيل. الرجاء المحاولة مرة أخرى.")
            return

        image_url = await get_image_url(media_details, session)
        unique_id = generate_unique_id()

        # تخزين البيانات (مع الرمز التعبيري الافتراضي)
        media_data[unique_id] = {
            'details': media_details,
            'type': media_type,
            'image_url': image_url,
            'link': None,
            'emoji': "💭",
        }

        message_text = format_media_message(media_details, "💭") #  استخدام format_media_message

        keyboard = [
            [
                InlineKeyboardButton("➕ إضافة رابط", callback_data=f"add_link_{unique_id}"),
                InlineKeyboardButton("🖼️ صورة أخرى", callback_data=f"another_image_{unique_id}")
            ],
            [InlineKeyboardButton("✏️ تغيير الرمز", callback_data=f"change_emoji_{unique_id}")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await searching_message.delete()

        # إرسال الصورة مع التسمية التوضيحية (caption) المنسقة
        try:
            await update.message.reply_photo(
                photo=image_url,
                caption=message_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML  #  هام:  لتفعيل التسطير
            )
        except Exception as e:
            logger.error(f"فشل إرسال الرسالة المنسقة ب HTML، محاولة الإرسال ب Markdown: {e}")
            #  إذا فشل HTML، استخدم Markdown
            message_text = format_media_message(media_details, "💭").replace("<u>", "__").replace("</u>", "__")
            await update.message.reply_photo(
                photo=image_url,
                caption=message_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN  # Markdown
            )

# معالجة ردود الأفعال (Callback Queries)
async def handle_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()  # مهم: إعلام Telegram بأن الرد قد تم استقباله

    data = query.data
    user_id_str = str(query.from_user.id)

    parts = data.split('_')
    action = parts[0]

    if action == "check_subscription":
        # التحقق من الاشتراك وتحديث الرسالة
        is_subscribed = await check_user_subscription(query.from_user.id, context)
        if is_subscribed:
            await query.message.edit_text("✅ تم التحقق من الاشتراك. يمكنك الآن استخدام البوت!")
        else:
            await query.message.edit_text("❌ لم يتم التحقق من الاشتراك. يرجى الاشتراك في جميع القنوات المطلوبة.")
        return

    if action == "admin":
        # أوامر المشرف
        if parts[1] == "add" and parts[2] == "channel":
            # بدء عملية إضافة قناة
            user_states[user_id_str] = {'type': 'admin_add_channel', 'step': 'waiting_for_channel_id'}
            await query.message.reply_text("أرسل مُعرف القناة (Channel ID).")
            return

        elif parts[1] == "edit" and parts[2] == "start" and parts[3] == "message":
            # بدء عملية تعديل رسالة البداية
            user_states[user_id_str] = {'type': 'admin_edit_start_message'}
            await query.message.reply_text("أرسل رسالة البداية الجديدة.")
            return

        elif parts[1] == "change" and parts[2] == "start" and parts[3] == "image":
            # بدء عملية تغيير صورة البداية
            user_states[user_id_str] = {'type': 'admin_change_start_image'}
            await query.message.reply_text("أرسل رابط صورة البداية الجديدة.")
            return

        elif parts[1] == "add" and parts[2] == "admin":
            user_states[user_id_str] = {'type':'admin_add_admin'}
            await query.message.reply_text("أرسل ايدي المستخدم")
            return

        elif parts[1] == "stats":
            # عرض إحصائيات البوت
            total_users = len(stats.users)
            total_searches = stats.total_searches
            today = datetime.now().strftime('%Y-%m-%d')
            daily_searches = stats.daily_searches.get(today, 0)

            message = (
                f"📊 <b>إحصائيات البوت</b>\n\n"
                f"عدد المستخدمين: {total_users}\n"
                f"إجمالي عمليات البحث: {total_searches}\n"
                f"عمليات البحث اليوم ({today}): {daily_searches}\n\n"
                f"<b>تفاصيل المستخدمين:</b>\n"
            )

            # إضافة تفاصيل المستخدمين (أول 10 مستخدمين مثلاً)
            for i, (user_id, user_data) in enumerate(stats.users.items()):
                if i >= 10:
                    break
                username = user_data.get('username', 'غير متوفر')
                first_name = user_data.get('first_name', 'غير متوفر')
                searches = user_data.get('searches', 0)
                message += f"- {first_name} (@{username}) - عمليات البحث: {searches}\n"
            message += "\n/admin_users لعرض كل المستخدمين"

            await query.message.reply_text(message, parse_mode=ParseMode.HTML)
            return

        elif parts[1] == 'users':
            message = ""
            for i, (user_id, user_data) in enumerate(stats.users.items()):
                username = user_data.get('username', 'غير متوفر')
                first_name = user_data.get('first_name', 'غير متوفر')
                searches = user_data.get('searches', 0)
                message += f"- {first_name} (@{username}) - عمليات البحث: {searches}\n"
            messages = [message[i:i + 4096] for i in range(0, len(message), 4096)]
            for msg in messages:
                await context.bot.send_message(chat_id=query.from_user.id, text=msg)
            return


    #  إذا لم يكن إجراءً من إجراءات المشرف، فمن المفترض أنه إجراء متعلق بالوسائط
    if len(parts) < 3:
        return

    media_id = parts[2]

    if media_id not in media_data:
        await query.edit_message_caption(
            caption="❌ انتهت صلاحية هذا الطلب.  الرجاء إعادة البحث.",
            parse_mode=ParseMode.HTML
        )
        return

    current_media = media_data[media_id]


    if action == "add_link":
        # طلب رابط من المستخدم
        user_states[user_id_str] = {'type': 'add_link', 'media_id': media_id}
        keyboard = [[InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_link_{media_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("🔗 الرجاء إرسال رابط المشاهدة:", reply_markup=reply_markup)
        return

    elif action == "cancel_link":
        # إلغاء إضافة الرابط
        if user_id_str in user_states:
            del user_states[user_id_str]
        await query.message.edit_text("✅ تم إلغاء إضافة الرابط")
        return

    elif action == "another_image":
        # البحث عن صورة أخرى
        message = await query.message.reply_text("🔄 جاري البحث عن صورة أخرى...")
        async with aiohttp.ClientSession() as session:
            new_image_url = await search_another_image(current_media['details'], session)
            current_media['image_url'] = new_image_url

            # تحديث الرسالة بالصورة الجديدة
            message_text = format_media_message(current_media['details'], current_media['emoji'])
            if current_media['link']:
                caption = f"{message_text.split(' للمشاهدة')[0]} <a href='{current_media['link']}'>للمشاهدة اضغط هنا</a>"
            else:
                caption = message_text

            keyboard = [
                [
                    InlineKeyboardButton("➕ إضافة رابط", callback_data=f"add_link_{media_id}"),
                    InlineKeyboardButton("🖼️ صورة أخرى", callback_data=f"another_image_{media_id}"),
                ],
                [InlineKeyboardButton("✏️ تغيير الرمز", callback_data=f"change_emoji_{media_id}")]
            ]
            if current_media['link']:
                keyboard[0][0] = InlineKeyboardButton("🔄 تغيير الرابط", callback_data=f"add_link_{media_id}")
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.message.reply_photo(
                photo=new_image_url,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
            await message.delete()
        return

    elif action == "change_emoji":
        # عرض قائمة الرموز التعبيرية
        user_states[user_id_str] = {'type': 'change_emoji', 'media_id': media_id}
        emojis = get_emoji_options()
        keyboard = [[InlineKeyboardButton(emoji, callback_data=f"select_emoji_{media_id}_{emoji}")] for emoji in emojis]
        keyboard.append([InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_emoji_{media_id}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("اختر رمزًا تعبيريًا جديدًا:", reply_markup=reply_markup)
        return

    elif action == "select_emoji":
        # اختيار رمز تعبيري
        selected_emoji = parts[3]
        current_media['emoji'] = selected_emoji

        # تحديث الرسالة بالرمز الجديد
        message_text = format_media_message(current_media['details'], selected_emoji)
        if current_media['link']:
            caption = f"{message_text.split(' للمشاهدة')[0]} <a href='{current_media['link']}'>للمشاهدة اضغط هنا</a>"
        else:
            caption = message_text

        keyboard = [
            [
                InlineKeyboardButton("➕ إضافة رابط", callback_data=f"add_link_{media_id}"),
                InlineKeyboardButton("🖼️ صورة أخرى", callback_data=f"another_image_{media_id}"),
            ],
            [InlineKeyboardButton("✏️ تغيير الرمز", callback_data=f"change_emoji_{media_id}")]
        ]
        if current_media['link']:
            keyboard[0][0] = InlineKeyboardButton("🔄 تغيير الرابط", callback_data=f"add_link_{media_id}")
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_photo(
            photo=current_media['image_url'],
            caption=caption,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

        if user_id_str in user_states:
            del user_states[user_id_str]
        return

    elif action == "cancel_emoji":
        # إلغاء تغيير الرمز التعبيري
        if user_id_str in user_states:
            del user_states[user_id_str]
        await query.message.edit_text("✅ تم إلغاء تغيير الرمز التعبيري")
        return

    logger.warning(f"Callback query غير معالج: {data}") # تسجيل ال callback الغير معالج

# معالجة الأخطاء
async def error_handler(update: Update, context: CallbackContext) -> None:
    logger.error(f"حدث خطأ: {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ حدث خطأ أثناء معالجة طلبك.  الرجاء المحاولة مرة أخرى لاحقًا."
            )
    except:
        pass

# الدالة الرئيسية
def main() -> None:
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin_users", handle_callback)) #  أمر المشرف

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_error_handler(error_handler)

    application.run_polling()

if __name__ == '__main__':
    main()
