import logging
import asyncio
import sqlite3
from aiogram import Bot as AiogramBot, Dispatcher, types, F
from aiogram.utils.keyboard import ReplyKeyboardMarkup as AiogramReplyKeyboardMarkup, KeyboardButton as AiogramKeyboardButton
from aiogram.types import KeyboardButtonRequestUser, KeyboardButtonRequestChat, InlineKeyboardMarkup, InlineKeyboardButton
import colorlog

# إعداد السجلات مع التلوين
handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(
    '%(log_color)s%(asctime)s - %(levelname)s - %(message)s',
    log_colors={
        'DEBUG': 'cyan',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'red,bg_white',
    }
))

logging.basicConfig(
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        handler
    ]
)
logger = logging.getLogger(__name__)

# بيانات البوت
BOT_TOKEN = "7957198144:AAH4PBpm0mwpRAQ_Ek-sDNe2bDs5Xfo9W5U"

# إعداد قاعدة البيانات
con = sqlite3.connect('db.sqlite3')
try:
    with con:
        cur = con.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS Users (
        id INTEGER NOT NULL UNIQUE,
        user_id INTEGER NOT NULL UNIQUE,
        language TEXT DEFAULT 'en',
        PRIMARY KEY (id AUTOINCREMENT)
        );
    """)
except Exception as e:
    logger.error(f"Failed to create table: {e}")

def sql_code(text):
    try:
        with sqlite3.connect('db.sqlite3') as conn:
            cur = conn.cursor()
            r = cur.execute(text)
            conn.commit()
            return r.fetchall()
    except Exception as e:
        logger.error(f"SQL error: {e}")
        return None

# النصوص المترجمة
texts = {
    "en": {
        "welcome": "Welcome to Tele Info! 🎉\nUse the buttons below to get info.",
        "choose_language": "Choose your language: 🌐",
        "me_info": "Your Info: ℹ️\nUser ID: {user_id}",
        "user_info": "User Info: ℹ️\nUser ID: {user_id}",
        "bot_info": "Bot Info: ℹ️\nUser ID: {user_id}",
        "channel_private": "Private Channel Info: 📢\nChat ID: {chat_id}",
        "channel_public": "Public Channel Info: 📢\nChat ID: {chat_id}",
        "group_private": "Private Group Info: 👥\nChat ID: {chat_id}",
        "group_public": "Public Group Info: 👥\nChat ID: {chat_id}",
        "supergroup": "Super Group Info: 🚀\nChat ID: {chat_id}",
        "lang_changed": "Language changed to {lang}! ✅",
        "peer_not_found": "Sorry, I can't access this chat."
    },
    "ar": {
        "welcome": "مرحبًا بك في Tele Info! 🎉\nاستخدم الأزرار أدناه للحصول على المعلومات.",
        "choose_language": "اختر لغتك: 🌐",
        "me_info": "معلوماتك: ℹ️\nمعرف المستخدم: {user_id}",
        "user_info": "معلومات المستخدم: ℹ️\nمعرف المستخدم: {user_id}",
        "bot_info": "معلومات البوت: ℹ️\nمعرف المستخدم: {user_id}",
        "channel_private": "معلومات قناة خاصة: 📢\nمعرف الدردشة: {chat_id}",
        "channel_public": "معلومات قناة عامة: 📢\nمعرف الدردشة: {chat_id}",
        "group_private": "معلومات جروب خاص: 👥\nمعرف الدردشة: {chat_id}",
        "group_public": "معلومات جروب عام: 👥\nمعرف الدردشة: {chat_id}",
        "supergroup": "معلومات سوبر جروب: 🚀\nمعرف الدردشة: {chat_id}",
        "lang_changed": "تم تغيير اللغة إلى {lang}! ✅",
        "peer_not_found": "عذرًا، لا يمكنني الوصول إلى هذه الدردشة."
    }
}

# Aiogram Bot
aiogram_bot = AiogramBot(BOT_TOKEN)
dp = Dispatcher()

# لوحة المفاتيح الرئيسية
main_menu = AiogramReplyKeyboardMarkup(
    keyboard=[
        [AiogramKeyboardButton(text="🧑‍💻 Me")],
        [AiogramKeyboardButton(text="📢 Channel"), AiogramKeyboardButton(text="👥 Group")],
        [AiogramKeyboardButton(text="👤 User", request_user=KeyboardButtonRequestUser(request_id=6, user_is_bot=False)),
         AiogramKeyboardButton(text="🤖 Bot", request_user=KeyboardButtonRequestUser(request_id=7, user_is_bot=True))]
    ],
    resize_keyboard=True
)

# لوحات المفاتيح الفرعية
channel_menu = AiogramReplyKeyboardMarkup(
    keyboard=[
        [AiogramKeyboardButton(text="🔒 Private Channel", request_chat=KeyboardButtonRequestChat(request_id=1, chat_is_channel=True, chat_has_username=False))],
        [AiogramKeyboardButton(text="🌐 Public Channel", request_chat=KeyboardButtonRequestChat(request_id=2, chat_is_channel=True, chat_has_username=True))],
        [AiogramKeyboardButton(text="🔙 Back")]
    ],
    resize_keyboard=True
)

group_menu = AiogramReplyKeyboardMarkup(
    keyboard=[
        [AiogramKeyboardButton(text="🌐 Public Group", request_chat=KeyboardButtonRequestChat(request_id=3, chat_is_channel=False, chat_has_username=True))],
        [AiogramKeyboardButton(text="🔒 Private Group", request_chat=KeyboardButtonRequestChat(request_id=4, chat_is_channel=False, chat_has_username=False)),
         AiogramKeyboardButton(text="🚀 Super Group", request_chat=KeyboardButtonRequestChat(request_id=5, chat_is_channel=False, chat_has_username=True))],
        [AiogramKeyboardButton(text="🔙 Back")]
    ],
    resize_keyboard=True
)

# لوحة اللغة (Inline)
language_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"), 
         InlineKeyboardButton(text="🇸🇦 العربية", callback_data="lang_ar")]
    ]
)

# وظيفة لجلب أو تحديث لغة المستخدم
def get_or_set_language(user_id, lang=None):
    result = sql_code(f"SELECT language FROM Users WHERE user_id = {user_id}")
    if result is None or not result:  # لو حصل خطأ أو المستخدم مش موجود
        sql_code(f"INSERT OR IGNORE INTO Users (user_id, language) VALUES ({user_id}, 'en')")
        return "en"
    if lang:  # لو عايزين نحدث اللغة
        sql_code(f"UPDATE Users SET language = '{lang}' WHERE user_id = {user_id}")
    return result[0][0] if result else "en"

# معالجات Aiogram
@dp.message(F.text == "/start")
async def start_command(message: types.Message):
    user_id = message.from_user.id
    lang = get_or_set_language(user_id)
    logger.info(f"User {user_id} started the bot with language: {lang}")
    start_msg = await message.answer(texts[lang]["welcome"], reply_markup=main_menu)
    await message.answer(texts[lang]["choose_language"], reply_markup=language_keyboard)

@dp.message(F.text == "🧑‍💻 Me")
async def me_button(message: types.Message):
    user_id = message.from_user.id
    lang = get_or_set_language(user_id)
    logger.info(f"User {user_id} requested their own info")
    await message.reply(texts[lang]["me_info"].format(user_id=user_id), reply_markup=main_menu)

@dp.message(F.text == "📢 Channel")
async def channel_button(message: types.Message):
    user_id = message.from_user.id
    lang = get_or_set_language(user_id)
    logger.info(f"User {user_id} clicked Channel button")
    await message.reply(texts[lang]["channel_menu"], reply_markup=channel_menu)

@dp.message(F.text == "👥 Group")
async def group_button(message: types.Message):
    user_id = message.from_user.id
    lang = get_or_set_language(user_id)
    logger.info(f"User {user_id} clicked Group button")
    await message.reply(texts[lang]["group_menu"], reply_markup=group_menu)

@dp.message(F.text == "🔙 Back")
async def back_button(message: types.Message):
    user_id = message.from_user.id
    lang = get_or_set_language(user_id)
    logger.info(f"User {user_id} returned to main menu")
    await message.reply(texts[lang]["welcome"], reply_markup=main_menu)

@dp.callback_query(F.data.startswith("lang_"))
async def change_language(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    lang = callback_query.data.split("_")[1]
    lang_name = "English" if lang == "en" else "العربية"
    get_or_set_language(user_id, lang)  # تحديث اللغة في قاعدة البيانات
    logger.info(f"User {user_id} changed language to {lang}")
    # حذف رسالة اختيار اللغة
    await aiogram_bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)
    # إرسال رسالة الترحيب مع اختيار اللغة تاني
    await aiogram_bot.send_message(chat_id=callback_query.message.chat.id, text=texts[lang]["welcome"], reply_markup=main_menu)
    await aiogram_bot.send_message(chat_id=callback_query.message.chat.id, text=texts[lang]["choose_language"], reply_markup=language_keyboard)
    await callback_query.answer(texts[lang]["lang_changed"].format(lang=lang_name))

@dp.message(F.user_shared)
async def handle_user_shared(message: types.Message):
    user_id = message.from_user.id
    lang = get_or_set_language(user_id)
    logger.info(f"User {user_id} shared a user or bot")
    shared_user_id = message.user_shared.user_id
    try:
        if message.user_shared.request_id == 7:  # Bot
            await message.reply(texts[lang]["bot_info"].format(user_id=shared_user_id), reply_markup=main_menu)
            logger.info(f"User {user_id} got bot info")
        else:  # User
            await message.reply(texts[lang]["user_info"].format(user_id=shared_user_id), reply_markup=main_menu)
            logger.info(f"User {user_id} got user info")
    except Exception as e:
        logger.error(f"Error fetching user info: {e}")
        await message.reply(texts[lang]["peer_not_found"], reply_markup=main_menu)

@dp.message(F.chat_shared)
async def handle_chat_shared(message: types.Message):
    user_id = message.from_user.id
    lang = get_or_set_language(user_id)
    logger.info(f"User {user_id} shared a chat")
    chat_id = message.chat_shared.chat_id
    request_id = message.chat_shared.request_id
    
    try:
        chat = await aiogram_bot.get_chat(chat_id)
        # قنوات
        if request_id == 1 and chat.type == "channel" and not chat.username:  # Private Channel
            await message.reply(texts[lang]["channel_private"].format(chat_id=chat_id), reply_markup=channel_menu)
            logger.info(f"User {user_id} got private channel info")
        elif request_id == 2 and chat.type == "channel" and chat.username:  # Public Channel
            await message.reply(texts[lang]["channel_public"].format(chat_id=chat_id), reply_markup=channel_menu)
            logger.info(f"User {user_id} got public channel info")
        # جروبات
        elif request_id == 3 and chat.type == "group" and chat.username:  # Public Group
            await message.reply(texts[lang]["group_public"].format(chat_id=chat_id), reply_markup=group_menu)
            logger.info(f"User {user_id} got public group info")
        elif request_id == 4 and chat.type == "group" and not chat.username:  # Private Group
            await message.reply(texts[lang]["group_private"].format(chat_id=chat_id), reply_markup=group_menu)
            logger.info(f"User {user_id} got private group info")
        elif request_id == 5 and chat.type == "supergroup" and chat.username:  # Super Group
            await message.reply(texts[lang]["supergroup"].format(chat_id=chat_id), reply_markup=group_menu)
            logger.info(f"User {user_id} got supergroup info")
        else:
            await message.reply(texts[lang]["peer_not_found"], reply_markup=main_menu if request_id > 2 else channel_menu)
    except Exception as e:
        logger.error(f"Error fetching chat info: {e}")
        await message.reply(texts[lang]["peer_not_found"], reply_markup=main_menu if request_id > 2 else channel_menu)

# تشغيل البوت
async def main():
    logger.info("Starting Tele Info Bot...")
    await dp.start_polling(aiogram_bot)
    logger.info("Bot stopped.")

if __name__ == "__main__":
    asyncio.run(main())
