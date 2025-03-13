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

# المفاتيح والإعدادات الأساسية
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
        self.admin_actions = []
        self.load()

    def load(self):
        try:
            if os.path.exists(USAGE_STATS_FILE):
                with open(USAGE_STATS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.users = data.get('users', {})
                    self.total_searches = data.get('total_searches', 0)
                    self.daily_searches = data.get('daily_searches', {})
                    self.admin_actions = data.get('admin_actions', [])
        except Exception as e:
            logger.error(f"خطأ في تحميل إحصائيات الاستخدام: {e}")

    def save(self):
        try:
            data = {
                'users': self.users,
                'total_searches': self.total_searches,
                'daily_searches': self.daily_searches,
                'admin_actions': self.admin_actions
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
        if user_id_str in self.users:
            self.users[user_id_str]['searches'] += 1
        self.total_searches += 1
        self.daily_searches[today] = self.daily_searches.get(today, 0) + 1
        self.save()

    def log_admin_action(self, admin_id, action):
        self.admin_actions.append({
            'admin_id': admin_id,
            'action': action,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
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
    return ["💭", "👁️", "🎬", "🍿", "🎞️", "📺", "🎦", "🔍", "📽️", "🎥"]

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
            if member.status not in ['creator', 'administrator', 'member']:
                return False
        except Exception as e:
            logger.error(f"خطأ في التحقق من اشتراك المستخدم: {e}")
    return True

# دوال معالجة TMDB والصور
async def get_image_url(media_data: Dict[str, Any], session: aiohttp.ClientSession) -> str:
    media_id = media_data.get('id')
    if media_id in poster_cache:
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
        media_year = media_data.get('release_date', '')[:4] if media_data.get('release_date') else media_data.get('first_air_date', '')[:4]
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
                if data.get('items'):
                    image_url = data['items'][0]['link']
                    poster_cache[media_id] = image_url
                    return image_url

    except Exception as e:
        logger.error(f"خطأ في الحصول على صورة: {e}")

    return "https://via.placeholder.com/1280x720?text=No+Image+Available"

async def search_tmdb(query: str, session: aiohttp.ClientSession) -> Dict:
    try:
        params = {
            'api_key': TMDB_API_KEY,
            'query': query,
            'language': 'ar-SA',
            'include_adult': 'false'
        }

        headers = {'Authorization': f'Bearer {TMDB_BEARER_TOKEN}'}

        async with session.get(f"{TMDB_BASE_URL}/search/multi", params=params, headers=headers) as response:
            data = await response.json() if response.status == 200 else await (await session.get(
                f"{TMDB_BASE_URL}/search/multi", 
                params={**params, 'language': 'en-US'}
            )).json()
            return data

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

        async with session.get(f"{TMDB_BASE_URL}/{media_type}/{media_id}", params=params) as response:
            return await response.json() if response.status == 200 else await (await session.get(
                f"{TMDB_BASE_URL}/{media_type}/{media_id}",
                params={**params, 'language': 'en-US'}
            )).json()

    except Exception as e:
        logger.error(f"خطأ في الحصول على تفاصيل الوسائط: {e}")
        return {}

async def search_another_image(media_data: Dict[str, Any], session: aiohttp.ClientSession) -> str:
    try:
        media_title = media_data.get('title') or media_data.get('name', '')
        media_year = media_data.get('release_date', '')[:4] if media_data.get('release_date') else media_data.get('first_air_date', '')[:4]
        search_query = f"{media_title} {media_year} movie poster 16:9"

        params = {
            'key': GOOGLE_API_KEY,
            'cx': GOOGLE_CSE_ID,
            'q': search_query,
            'searchType': 'image',
            'imgSize': 'large',
            'imgType': 'photo',
            'num': 1,
            'start': random.randint(1, 10)
        }

        async with session.get(GOOGLE_SEARCH_URL, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('items'):
                    return data['items'][0]['link']

    except Exception as e:
        logger.error(f"خطأ في البحث عن صورة بديلة: {e}")

    return media_data.get('poster_path', "https://via.placeholder.com/1280x720?text=No+Image+Available")

# وظائف تنسيق الرسائل
def format_media_message(media_details: Dict[str, Any], emoji: str = "💭", link: str = None) -> str:
    arabic_title = media_details.get('title') or media_details.get('name', '')
    english_title = media_details.get('original_title') or media_details.get('original_name', '')
    
    if re.match(r'^[a-zA-Z0-9\s\W]+$', arabic_title) and arabic_title != english_title:
        arabic_title, english_title = english_title, arabic_title

    overview = media_details.get('overview', 'معلومات غير متوفرة')
    
    title = f"<b><u>{arabic_title} | {english_title}</u></b>"
    watch_text = f"{emoji} للمشاهدة اضغط هنا" if not link else f'<a href="{link}">{emoji} للمشاهدة اضغط هنا</a>'
    
    return f"{title}\n\n{overview}\n\n{watch_text}"

# معالجة الأوامر
async def start_command(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    stats.add_user(user.id, user.username, user.first_name)

    if not await check_user_subscription(user.id, context):
        keyboard = [
            [InlineKeyboardButton(channel['title'], url=channel['url'])] 
            for channel in config.forced_channels
        ] + [[InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subscription")]]
        
        await update.message.reply_text(
            "⚠️ يجب الاشتراك في القنوات التالية أولاً:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if is_admin(user.id):
        keyboard = [
            [InlineKeyboardButton("➕ إضافة قناة إجبارية", callback_data="admin_add_channel"),
             InlineKeyboardButton("✏️ تعديل رسالة البداية", callback_data="admin_edit_start_message")],
            [InlineKeyboardButton("🖼️ تغيير صورة البداية", callback_data="admin_change_start_image"),
             InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
            [InlineKeyboardButton("👤 إضافة مشرف", callback_data="admin_add_admin")]
        ]
        await update.message.reply_text(
            f"👑 مرحبًا {user.first_name}، أنت مشرف!\n"
            "اختر الإجراء المطلوب:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    else:
        keyboard = [[InlineKeyboardButton("👨💻 المطور", url=f"https://t.me/{DEVELOPER_USERNAME}")]]
        try:
            await update.message.reply_photo(
                photo=config.start_image,
                caption=config.start_message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            await update.message.reply_text(config.start_message, reply_markup=InlineKeyboardMarkup(keyboard))

async def help_command(update: Update, context: CallbackContext) -> None:
    help_text = (
        "📚 <b>كيفية الاستخدام:</b>\n\n"
        "1. ابحث بأي اسم فيلم أو مسلسل\n"
        "2. اختر من النتائج\n"
        "3. أضف روابط المشاهدة\n"
        "4. غير الصور والرموز حسب الرغبة\n\n"
        "🎬 <b>أمثلة:</b>\n"
        "- Inception\n- الوحش\n- Spider-Man 2002"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

# معالجة الرسائل والبحث
async def handle_message(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    query = update.message.text.strip()
    user_id_str = str(user.id)

    # التحقق من حالة الانتظار
    if user_id_str in user_states:
        state = user_states[user_id_str]
        
        # معالجة إضافة الرابط
        if state['type'] == 'add_link':
            media_id = state['media_id']
            link = extract_url(query)
            
            if link:
                media_data[media_id]['link'] = link
                del user_states[user_id_str]
                
                # إعادة إرسال النتيجة المحدثة
                media = media_data[media_id]
                caption = format_media_message(media['details'], media['emoji'], link)
                keyboard = [
                    [InlineKeyboardButton("🔄 تغيير الرابط", callback_data=f"add_link_{media_id}"),
                     InlineKeyboardButton("🖼️ صورة أخرى", callback_data=f"another_image_{media_id}")],
                    [InlineKeyboardButton("✏️ تغيير الرمز", callback_data=f"change_emoji_{media_id}")]
                ]
                await update.message.reply_photo(
                    photo=media['image_url'],
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.HTML
                )
            else:
                keyboard = [
                    [InlineKeyboardButton("🔄 إعادة المحاولة", callback_data=f"add_link_{media_id}")],
                    [InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_link_{media_id}")]
                ]
                await update.message.reply_text(
                    "❌ الرابط غير صالح! يرجى إرسال رابط صحيح:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
            return

    # باقي معالجة الرسائل...
    # (يتم وضع الكود السابق هنا مع التعديلات اللازمة)

# معالجة ردود الأفعال
async def handle_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user

    if data == "check_subscription":
        # ... (الكود السابق)
    
    elif data.startswith("admin"):
        if not is_admin(user.id):
            await query.message.edit_text("❌ ليس لديك صلاحية المشرف!")
            return
        
        # معالجة أوامر المشرف...
        # (يتم وضع الكود السابق هنا مع التعديلات)
    
    elif data.startswith("add_link"):
        media_id = data.split('_')[-1]
        user_states[str(user.id)] = {'type': 'add_link', 'media_id': media_id}
        await query.message.reply_text("📩 أرسل رابط المشاهدة الآن:")

    elif data.startswith("another_image"):
        media_id = data.split('_')[-1]
        media = media_data[media_id]
        
        async with aiohttp.ClientSession() as session:
            new_image = await search_another_image(media['details'], session)
            media['image_url'] = new_image
            
            caption = format_media_message(media['details'], media['emoji'], media.get('link'))
            keyboard = [
                [InlineKeyboardButton("➕ إضافة رابط", callback_data=f"add_link_{media_id}"),
                 InlineKeyboardButton("🖼️ صورة أخرى", callback_data=f"another_image_{media_id}")],
                [InlineKeyboardButton("✏️ تغيير الرمز", callback_data=f"change_emoji_{media_id}")]
            ]
            await query.message.edit_media(
                InputMediaPhoto(new_image, caption=caption, parse_mode=ParseMode.HTML),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    # باقي معالجة ال callbacks...
    # (يتم وضع الكود السابق هنا مع التعديلات)

# معالجة الأخطاء
async def error_handler(update: Update, context: CallbackContext) -> None:
    logger.error(f"Error: {context.error}")
    if update.message:
        await update.message.reply_text("⚠️ حدث خطأ أثناء المعالجة، يرجى المحاولة لاحقًا.")

def main() -> None:
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # تسجيل ال handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_error_handler(error_handler)

    application.run_polling()

if __name__ == '__main__':
    main()
