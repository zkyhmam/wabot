from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import CallbackContext
import aiohttp
from typing import Dict, Any
import tmdb_api
import google_api
import utils
import data
from config import config
from keyboards import build_main_keyboard, build_admin_keyboard, build_subscription_keyboard
import logging
import os
from datetime import datetime
import json

logger = logging.getLogger(__name__)

# ملفات البيانات
CONFIG_FILE = "config.json"
USAGE_STATS_FILE = "usage_stats.json"

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
            # يمكنك هنا تجربة طريقة أخرى للتحميل أو تهيئة البيانات بشكل افتراضي إذا فشل التحميل

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
            # يمكنك هنا محاولة الحفظ بطريقة أخرى أو تخطي الحفظ مؤقتًا

    def add_user(self, user_id, username=None, first_name=None):
        user_id_str = str(user_id)
        try:
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
        except Exception as e:
            logger.error(f"خطأ في إضافة مستخدم أو تحديث بياناته: {e}")
            # يمكنك هنا إضافة معالجة إضافية للخطأ إذا لزم الأمر

    def log_search(self, user_id):
        user_id_str = str(user_id)
        today = datetime.now().strftime('%Y-%m-%d')
        try:
            if user_id_str in self.users:
                self.users[user_id_str]['searches'] += 1
                self.users[user_id_str]['last_activity'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            self.total_searches += 1

            if today not in self.daily_searches:
                self.daily_searches[today] = 0
            self.daily_searches[today] += 1

            self.save()
        except Exception as e:
            logger.error(f"خطأ في تسجيل البحث: {e}")
            # يمكنك هنا إضافة معالجة إضافية للخطأ إذا لزم الأمر

stats = UsageStats()

async def start_command(update: Update, context: CallbackContext) -> None:
    try:
        user = update.effective_user
        stats.add_user(user.id, user.username, user.first_name)
        is_subscribed = await utils.check_user_subscription(user.id, context)
        if not is_subscribed:
            keyboard = build_subscription_keyboard(config.FORCED_CHANNELS)
            await update.message.reply_text(
                "⚠️ يجب عليك الاشتراك في القناة/القنوات التالية لاستخدام البوت:\n\n"
                "اضغط على زر تحقق من الاشتراك بعد الانتهاء من الاشتراك.",
                reply_markup=keyboard
            )
            return

        if utils.is_admin(user.id):
            keyboard = build_admin_keyboard()
            await update.message.reply_text(
                f"👑 <b>وضع المشرف</b>\n\n"
                f"مرحباً {user.first_name}، أنت مشرف في هذا البوت.\n"
                f"يمكنك استخدام الأوامر التالية:",
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
        else:
            keyboard = [[InlineKeyboardButton("👨‍💻 التواصل مع المطور", url=f"https://t.me/{config.DEVELOPER_USERNAME}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            try:
                await update.message.reply_photo(
                    photo=config.DEFAULT_START_IMAGE,
                    caption=config.DEFAULT_START_MESSAGE,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"خطأ في إرسال رسالة البداية (صورة): {e}")
                await update.message.reply_text(
                    config.DEFAULT_START_MESSAGE,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
    except Exception as global_e:
        logger.error(f"خطأ في الأمر start: {global_e}")
        await update.message.reply_text("❌ حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى لاحقًا.")

async def help_command(update: Update, context: CallbackContext) -> None:
    try:
        is_subscribed = await utils.check_user_subscription(update.effective_user.id, context)

        if not is_subscribed:
            keyboard = build_subscription_keyboard(config.FORCED_CHANNELS)
            await update.message.reply_text(
                "⚠️ يجب عليك الاشتراك في القناة/القنوات التالية لاستخدام البوت:\n\n"
                "اضغط على زر تحقق من الاشتراك بعد الانتهاء من الاشتراك.",
                reply_markup=keyboard
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

        keyboard = [[InlineKeyboardButton("👨‍💻 التواصل مع المطور", url=f"https://t.me/{config.DEVELOPER_USERNAME}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(help_message, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    except Exception as global_e:
        logger.error(f"خطأ في الأمر help: {global_e}")
        await update.message.reply_text("❌ حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى لاحقًا.")


async def handle_message(update: Update, context: CallbackContext) -> None:
    try:
        user = update.effective_user
        query = update.message.text.strip()
        stats.add_user(user.id, user.username, user.first_name)
        user_id_str = str(user.id)
        user_state = await data.get_user_state(user_id_str)

        if user_state:
            try:
                if user_state.get('type') == 'admin_add_channel':
                    if user_state.get('step') == 'waiting_for_channel_id':
                        channel_id = query.strip()
                        await data.set_user_state(user_id_str, {'type': 'admin_add_channel', 'step': 'waiting_for_channel_title', 'channel_id': channel_id})
                        await update.message.reply_text("✅ تم حفظ معرف القناة، الآن أرسل عنوان القناة (مثال: قناة الأفلام)")
                        return

                    elif user_state.get('step') == 'waiting_for_channel_title':
                        channel_title = query.strip()
                        await data.set_user_state(user_id_str, {'type': 'admin_add_channel', 'step': 'waiting_for_channel_url', 'channel_id': user_state.get('channel_id'), 'channel_title': channel_title})
                        await update.message.reply_text("✅ تم حفظ عنوان القناة، الآن أرسل رابط القناة (مثال: https://t.me/channel)")
                        return

                    elif user_state.get('step') == 'waiting_for_channel_url':
                        channel_url = query.strip()
                        channel_id = user_state.get('channel_id')
                        channel_title = user_state.get('channel_title')

                        config.FORCED_CHANNELS.append({
                            'id': channel_id,
                            'title': channel_title,
                            'url': channel_url
                        })

                        try:
                            with open('config.json', mode='r', encoding='utf-8') as f:
                                config_data = json.load(f)
                        except (FileNotFoundError, json.JSONDecodeError) as e:
                            logger.error(f"خطأ في تحميل ملف config.json أو فك ترميز JSON: {e}")
                            config_data = {} # تهيئة config_data لتجنب أخطاء لاحقة
                        config_data['forced_channels'] = config.FORCED_CHANNELS
                        try:
                            with open('config.json', 'w', encoding='utf-8') as f:
                                json.dump(config_data, f, ensure_ascii=False, indent=4)
                        except Exception as e:
                            logger.error(f"خطأ في حفظ ملف config.json: {e}")

                        await data.clear_user_state(user_id_str)
                        await update.message.reply_text(f"✅ تم إضافة القناة بنجاح!")
                        return

                elif user_state.get('type') == 'admin_edit_start_message':
                    config.DEFAULT_START_MESSAGE = query
                    try:
                        with open('config.json', mode='r', encoding='utf-8') as f:
                            config_data = json.load(f)
                    except (FileNotFoundError, json.JSONDecodeError) as e:
                        logger.error(f"خطأ في تحميل ملف config.json أو فك ترميز JSON: {e}")
                        config_data = {} # تهيئة config_data لتجنب أخطاء لاحقة
                    config_data['start_message'] = config.DEFAULT_START_MESSAGE
                    try:
                        with open('config.json', 'w', encoding='utf-8') as f:
                            json.dump(config_data, f, ensure_ascii=False, indent=4)
                    except Exception as e:
                        logger.error(f"خطأ في حفظ ملف config.json: {e}")

                    await data.clear_user_state(user_id_str)
                    await update.message.reply_text("✅ تم تحديث رسالة البداية بنجاح!")
                    return

                elif user_state.get('type') == 'admin_change_start_image':
                    config.DEFAULT_START_IMAGE = query
                    try:
                        with open('config.json', mode='r', encoding='utf-8') as f:
                            config_data = json.load(f)
                    except (FileNotFoundError, json.JSONDecodeError) as e:
                        logger.error(f"خطأ في تحميل ملف config.json أو فك ترميز JSON: {e}")
                        config_data = {} # تهيئة config_data لتجنب أخطاء لاحقة
                    config_data['start_image'] = config.DEFAULT_START_IMAGE
                    try:
                        with open('config.json', 'w', encoding='utf-8') as f:
                            json.dump(config_data, f, ensure_ascii=False, indent=4)
                    except Exception as e:
                        logger.error(f"خطأ في حفظ ملف config.json: {e}")
                    await data.clear_user_state(user_id_str)
                    await update.message.reply_text("✅ تم تحديث رابط صورة البداية بنجاح!")
                    return

                elif user_state.get('type') == 'admin_add_admin':
                    try:
                        new_admin_id = int(query.strip())
                        if new_admin_id not in config.ADMIN_IDS:
                            config.ADMIN_IDS.append(new_admin_id)
                            admin_ids_str = ",".join(map(str, config.ADMIN_IDS))
                            try:
                                with open(".env", "r") as f:
                                    lines = f.readlines()
                            except FileNotFoundError as e:
                                logger.error(f"خطأ في فتح ملف .env: {e}")
                                lines = [] # تهيئة lines لتجنب أخطاء لاحقة
                            try:
                                with open(".env", "w") as f:
                                    for line in lines:
                                        if line.startswith("ADMIN_IDS="):
                                            f.write(f"ADMIN_IDS={admin_ids_str}\n")
                                        else:
                                            f.write(line)
                                    if not any(line.startswith("ADMIN_IDS=") for line in lines):
                                        f.write(f"ADMIN_IDS={admin_ids_str}\n")
                            except Exception as e:
                                logger.error(f"خطأ في كتابة ملف .env: {e}")

                            await update.message.reply_text(f"✅ تم إضافة المشرف الجديد (ID: {new_admin_id}) بنجاح!")
                        else:
                            await update.message.reply_text(f"❌ المشرف (ID: {new_admin_id}) موجود بالفعل.")

                        await data.clear_user_state(user_id_str)
                        return
                    except ValueError:
                        await update.message.reply_text("❌ الرجاء إدخال رقم صحيح فقط كمعرف المستخدم")
                        return
                elif user_state.get('type') == 'add_link':
                    media_id = user_state.get('media_id')
                    media = await data.get_media_data(media_id)

                    if not media_id or not media:
                         await update.message.reply_text("❌ حدث خطأ: لم يتم العثور على بيانات الفيلم/المسلسل.")
                         await data.clear_user_state(user_id_str)
                         return

                    extracted_link = utils.extract_url(query)
                    if extracted_link:
                        media['link'] = extracted_link
                        await data.set_media_data(media_id, media)
                        await data.clear_user_state(user_id_str)

                        message_text = utils.format_media_message(media['details'], media['emoji'])
                        caption = f"{message_text.split(' للمشاهدة')[0]} <a href='{extracted_link}'>للمشاهدة اضغط هنا</a>"
                        keyboard = build_main_keyboard(media_id, media)
                        try:
                            await update.message.reply_text(f"✅ تم حفظ الرابط بنجاح: {extracted_link}")
                            await update.message.reply_photo(
                                photo=media['image_url'],
                                caption=caption,
                                reply_markup=keyboard,
                                parse_mode=ParseMode.HTML
                            )
                        except Exception as e:
                            logger.error(f"خطأ في إرسال رسالة إضافة الرابط: {e}")
                            await update.message.reply_text("❌ حدث خطأ أثناء إرسال النتيجة مع الرابط.")

                    else:
                        keyboard = [
                            [InlineKeyboardButton("🔄 إعادة المحاولة", callback_data=f"add_link_{media_id}")],
                            [InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_link_{media_id}")]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        await update.message.reply_text("❌ الرابط غير صالح.  الرجاء إرسال رابط صحيح يبدأ بـ `http://` أو `https://`.", reply_markup=reply_markup)
                        return

                elif user_state.get('type') == 'change_emoji':
                    media_id = user_state.get('media_id')
                    new_emoji = query.strip()
                    media = await data.get_media_data(media_id)

                    if not media_id or not media:
                        await update.message.reply_text("❌ حدث خطأ: لم يتم العثور على بيانات الفيلم/المسلسل.")
                        await data.clear_user_state(user_id_str)
                        return

                    if new_emoji in utils.get_emoji_options():
                        media['emoji'] = new_emoji
                        await data.set_media_data(media_id, media)
                        await data.clear_user_state(user_id_str)

                        message_text = utils.format_media_message(media['details'], new_emoji)
                        if media['link']:
                            caption = f"{message_text.split(' للمشاهدة')[0]} <a href='{media['link']}'>للمشاهدة اضغط هنا</a>"
                        else:
                            caption = message_text

                        keyboard = build_main_keyboard(media_id, media)
                        try:
                            await update.message.reply_photo(
                                photo=media['image_url'],
                                caption=caption,
                                reply_markup=keyboard,
                                parse_mode=ParseMode.HTML
                            )
                        except Exception as e:
                            logger.error(f"خطأ في إرسال رسالة تغيير الرمز التعبيري: {e}")
                            await update.message.reply_text("❌ حدث خطأ أثناء إرسال النتيجة مع الرمز التعبيري الجديد.")
                    else:
                        await update.message.reply_text("❌ الرمز التعبيري غير صالح. الرجاء الاختيار من القائمة.")
                    return
            except Exception as state_error:
                logger.error(f"خطأ أثناء معالجة حالة المستخدم: {state_error}")
                await update.message.reply_text("❌ حدث خطأ أثناء معالجة حالتك. يرجى المحاولة مرة أخرى.")
                await data.clear_user_state(user_id_str) # مسح الحالة لتجنب تكرار الخطأ

        is_subscribed = await utils.check_user_subscription(user.id, context)
        if not is_subscribed:
            keyboard = build_subscription_keyboard(config.FORCED_CHANNELS)
            await update.message.reply_text(
                "⚠️ يجب عليك الاشتراك في القناة/القنوات التالية لاستخدام البوت:\n\n"
                "اضغط على زر تحقق من الاشتراك بعد الانتهاء من الاشتراك.",
                reply_markup=keyboard
            )
            return

        if len(query) < 2:
            await update.message.reply_text("⚠️ الرجاء إدخال اسم أطول للبحث")
            return

        searching_message = await update.message.reply_text("🔍 جاري البحث... برجاء الانتظار")

        try:
            async with aiohttp.ClientSession() as session:
                search_results = await tmdb_api.search_tmdb(query, session)
                filtered_results = [
                    item for item in search_results.get('results', [])
                    if item.get('media_type') in ['movie', 'tv'] and (item.get('poster_path') is not None or item.get('backdrop_path') is not None)
                ]

                if not filtered_results:
                    await searching_message.delete()
                    await update.message.reply_text("❌ لم يتم العثور على نتائج. حاول البحث باسم آخر.")
                    return

                if len(filtered_results) > 1:
                    buttons = []
                    for i, result in enumerate(filtered_results[:5]):
                        title = result.get('title', '') or result.get('name', '')
                        year = result.get('release_date', '')[:4] if result.get('release_date') else ''
                        if not year and result.get('first_air_date'):
                            year = result.get('first_air_date')[:4]

                        display_text = f"{title} ({year})" if year else title
                        unique_id = utils.generate_unique_id()
                        buttons.append([InlineKeyboardButton(display_text, callback_data=f"result_{unique_id}")])

                        await data.set_media_data(unique_id, {
                            'details': result,
                            'type': result.get('media_type'),
                            'image_url': None,  # سيتم تحميل الصورة لاحقًا
                            'link': None,
                            'emoji': "💭",
                        })

                    reply_markup = InlineKeyboardMarkup(buttons)
                    await searching_message.delete()
                    await update.message.reply_text("📋 وجدنا عدة نتائج. الرجاء اختيار النتيجة المطلوبة:", reply_markup=reply_markup)
                    return

                first_result = filtered_results[0]
                media_type = first_result.get('media_type')
                media_id = first_result.get('id')
                media_details = await tmdb_api.get_media_details(media_id, media_type, session)

                if not media_details:
                    await searching_message.delete()
                    await update.message.reply_text("❌ حدث خطأ أثناء جلب التفاصيل. الرجاء المحاولة مرة أخرى.")
                    return

                image_url = await google_api.get_image_url(media_details, session)
                cached_image = await data.get_cached_image_url(media_id)
                if cached_image:
                    image_url = cached_image
                else:
                    image_url = await google_api.get_image_url(media_details, session)
                    await data.cache_image_url(media_id, image_url)

                unique_id = utils.generate_unique_id()
                await data.set_media_data(unique_id, {
                    'details': media_details,
                    'type': media_type,
                    'image_url': image_url,
                    'link': None,
                    'emoji': "💭",
                })

                message_text = utils.format_media_message(media_details)
                keyboard = build_main_keyboard(unique_id, await data.get_media_data(unique_id))

                await searching_message.delete()
                try:
                    await update.message.reply_photo(
                        photo=image_url,
                        caption=message_text,
                        reply_markup=keyboard,
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.error(f"خطأ في إرسال رسالة نتيجة البحث (صورة): {e}")
                    await update.message.reply_text(message_text, reply_markup=keyboard, parse_mode=ParseMode.HTML) # إرسال نص فقط كحل بديل

        except Exception as global_error:
            logger.error(f"خطأ في معالجة الرسالة: {global_error}")
            await searching_message.delete() # حذف رسالة "جاري البحث" لتجنب تراكمها
            await update.message.reply_text("❌ حدث خطأ أثناء البحث. يرجى المحاولة مرة أخرى لاحقًا.")

async def handle_callback(update: Update, context: CallbackContext) -> None:
    try:
        query = update.callback_query
        await query.answer()

        data_parts = query.data.split('_')
        action = data_parts[0]
        user_id_str = str(query.from_user.id)

        logger.debug(f"Callback query data: {query.data}")

        if action == "check_subscription":
            try:
                is_subscribed = await utils.check_user_subscription(query.from_user.id, context)
                if is_subscribed:
                    await query.message.reply_text("✅ تم التحقق من الاشتراك. يمكنك الآن استخدام البوت!")
                else:
                    await query.message.reply_text("❌ لم يتم التحقق من الاشتراك. يرجى الاشتراك في جميع القنوات المطلوبة.")
            except Exception as e:
                logger.error(f"خطأ أثناء التحقق من الاشتراك: {e}")
                await query.message.reply_text("❌ حدث خطأ أثناء التحقق من الاشتراك. يرجى المحاولة مرة أخرى.")
            return

        if action == "result":
            media_id = data_parts[1]
            try:
                media = await data.get_media_data(media_id)

                if not media:
                    await query.message.reply_text("❌ انتهت الصلاحية أو بيانات غير موجودة")
                    return

                # جلب الصورة إذا لم تكن موجودة
                if not media['image_url']:
                    async with aiohttp.ClientSession() as session:
                        media['image_url'] = await google_api.get_image_url(media['details'], session)
                        await data.set_media_data(media_id, media)

                # عرض النتيجة
                message_text = utils.format_media_message(media['details'], media['emoji'])
                keyboard = build_main_keyboard(media_id, media)
                try:
                    await query.message.reply_photo(
                        photo=media['image_url'],
                        caption=message_text,
                        reply_markup=keyboard,
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.error(f"خطأ في إرسال نتيجة البحث (صورة) عبر callback: {e}")
                    await query.message.reply_text(message_text, reply_markup=keyboard, parse_mode=ParseMode.HTML) # إرسال نص فقط كحل بديل

            except Exception as e:
                logger.error(f"خطأ أثناء معالجة نتيجة البحث callback: {e}")
                await query.message.reply_text("❌ حدث خطأ أثناء معالجة النتيجة. يرجى المحاولة مرة أخرى.")
            return

        if action == "admin":
            try:
                if data_parts[1] == "add" and data_parts[2] == "channel":
                    await data.set_user_state(user_id_str, {'type': 'admin_add_channel', 'step': 'waiting_for_channel_id'})
                    await query.message.reply_text("أرسل مُعرف القناة (Channel ID).")
                    return

                elif data_parts[1] == "edit" and data_parts[2] == "start" and data_parts[3] == "message":
                    await data.set_user_state(user_id_str, {'type': 'admin_edit_start_message'})
                    await query.message.reply_text("أرسل رسالة البداية الجديدة.")
                    return

                elif data_parts[1] == "change" and data_parts[2] == "start" and data_parts[3] == "image":
                    await data.set_user_state(user_id_str, {'type': 'admin_change_start_image'})
                    await query.message.reply_text("أرسل رابط صورة البداية الجديدة.")
                    return

                elif data_parts[1] == "add" and data_parts[2] == "admin":
                    await data.set_user_state(user_id_str, {'type': 'admin_add_admin'})
                    await query.message.reply_text("أرسل ايدي المستخدم")
                    return

                elif data_parts[1] == "stats":
                    total_users = len(stats.users)
                    total_searches = stats.total_searches
                    today = datetime.now().strftime('%Y-%m-%d')
                    daily_searches = stats.daily_searches.get(today, 0)

                    message = (
                        f"📊 <b>إحصائيات البوت</b>\n\n"
                        f"👥 عدد المستخدمين الكلي: {total_users}\n"
                        f"🔍 إجمالي عمليات البحث: {total_searches}\n"
                        f"📆 عمليات البحث اليوم: {daily_searches}\n\n"
                        f"<b>تفاصيل المستخدمين:</b>\n"
                    )

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
                elif data_parts[1] == 'users':
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
            except Exception as admin_action_error:
                logger.error(f"خطأ أثناء معالجة إجراءات المشرف callback: {admin_action_error}")
                await query.message.reply_text("❌ حدث خطأ أثناء تنفيذ إجراء المشرف. يرجى المحاولة مرة أخرى.")
                return


        # استخراج media_id بشكل طبيعي
        media_id = data_parts[1] if len(data_parts) > 1 else None
        logger.debug(f"Extracted media_id from callback: {media_id}")
        if not media_id:
            logger.warning("media_id is None in callback!")
            await query.message.reply_text("❌ حدث خطأ في معالجة الطلب. الرجاء إعادة البحث.")
            return

        media = await data.get_media_data(media_id)
        logger.debug(f"Retrieved media data for callback: {media}")
        if not media:
            await query.message.reply_text("❌ انتهت صلاحية هذا الطلب. الرجاء إعادة البحث.")
            return


        if action == "add_link":
            try:
                await data.set_user_state(user_id_str, {'type': 'add_link', 'media_id': media_id})
                keyboard = [[InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_link_{media_id}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.message.reply_text("🔗 الرجاء إرسال رابط المشاهدة:", reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"خطأ أثناء معالجة 'add_link' callback: {e}")
                await query.message.reply_text("❌ حدث خطأ أثناء طلب الرابط. يرجى المحاولة مرة أخرى.")


        elif action == "cancel_link":
            try:
                await data.clear_user_state(user_id_str)
                await query.message.reply_text("✅ تم إلغاء إضافة الرابط")
            except Exception as e:
                logger.error(f"خطأ أثناء معالجة 'cancel_link' callback: {e}")
                await query.message.reply_text("❌ حدث خطأ أثناء الإلغاء. يرجى المحاولة مرة أخرى.")


        elif action == "another_image":
            try:
                message = await query.message.reply_text("🔄 جاري البحث عن صورة أخرى...")
                async with aiohttp.ClientSession() as session:
                    new_image_url = await google_api.search_another_image(media['details'], session)
                    media['image_url'] = new_image_url
                    await data.set_media_data(media_id, media)

                    message_text = utils.format_media_message(media['details'], media['emoji'])
                    caption = f"{message_text.split(' للمشاهدة')[0]} <a href='{media['link']}'>للمشاهدة اضغط هنا</a>" if media['link'] else message_text
                    keyboard = build_main_keyboard(media_id, media)
                    try:
                        await query.message.reply_photo(
                            photo=new_image_url,
                            caption=caption,
                            reply_markup=keyboard,
                            parse_mode=ParseMode.HTML
                        )
                    except Exception as e:
                        logger.error(f"خطأ في إرسال صورة أخرى عبر callback: {e}")
                        await query.message.reply_text("❌ حدث خطأ أثناء إرسال الصورة. يرجى المحاولة مرة أخرى.")
                await message.delete()
            except Exception as e:
                logger.error(f"خطأ أثناء معالجة 'another_image' callback: {e}")
                await query.message.reply_text("❌ حدث خطأ أثناء البحث عن صورة أخرى. يرجى المحاولة مرة أخرى.")

        elif action == "change_emoji":
            try:
                await data.set_user_state(user_id_str, {'type': 'change_emoji', 'media_id': media_id})
                emojis = utils.get_emoji_options()
                keyboard = [[InlineKeyboardButton(emoji, callback_data=f"select_emoji_{media_id}_{emoji}")] for emoji in emojis]
                keyboard.append([InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_emoji_{media_id}")])
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.message.reply_text("اختر رمزًا تعبيريًا جديدًا:", reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"خطأ أثناء معالجة 'change_emoji' callback: {e}")
                await query.message.reply_text("❌ حدث خطأ أثناء طلب تغيير الرمز. يرجى المحاولة مرة أخرى.")


        elif action == "select_emoji":
            try:
                selected_emoji = data_parts[2]
                media['emoji'] = selected_emoji
                await data.set_media_data(media_id, media)
                message_text = utils.format_media_message(media['details'], selected_emoji)
                caption = f"{message_text.split(' للمشاهدة')[0]} <a href='{media['link']}'>للمشاهدة اضغط هنا</a>" if media['link'] else message_text
                keyboard = build_main_keyboard(media_id, media)
                try:
                    await query.message.reply_photo(
                        photo=media['image_url'],
                        caption=caption,
                        reply_markup=keyboard,
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    logger.error(f"خطأ في إرسال رمز تعبيري محدد عبر callback: {e}")
                    await query.message.reply_text("❌ حدث خطأ أثناء إرسال النتيجة مع الرمز التعبيري المحدد.")
                await data.clear_user_state(user_id_str)
            except Exception as e:
                logger.error(f"خطأ أثناء معالجة 'select_emoji' callback: {e}")
                await query.message.reply_text("❌ حدث خطأ أثناء اختيار الرمز التعبيري. يرجى المحاولة مرة أخرى.")


        elif action == "cancel_emoji":
            try:
                await data.clear_user_state(user_id_str)
                await query.message.reply_text("✅ تم إلغاء تغيير الرمز التعبيري")
            except Exception as e:
                logger.error(f"خطأ أثناء معالجة 'cancel_emoji' callback: {e}")
                await query.message.reply_text("❌ حدث خطأ أثناء إلغاء تغيير الرمز. يرجى المحاولة مرة أخرى.")


        else:
            logger.warning(f"Callback query غير معالج: {query.data}")
            await query.message.reply_text("❌ حدث خطأ غير متوقع في معالجة الاستجابة.")

    except Exception as global_callback_error:
        logger.error(f"خطأ في معالجة callback: {global_callback_error}")
        await query.message.reply_text("❌ حدث خطأ غير متوقع أثناء معالجة طلبك. يرجى المحاولة مرة أخرى لاحقًا.")

