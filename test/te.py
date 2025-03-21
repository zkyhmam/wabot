import os
import logging
import re
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, filters, MessageHandler

# --- تكوين السجلات ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- توكن البوت ---
BOT_TOKEN = "7558529929:AAFmMHm2HuqHsdqdQvl_ZLCoXn5XOPiRzfw"

# --- معلومات المشرف ---
ADMIN_USERNAME = "Zaky1million"
ADMIN_ID = 6988696258

# --- مسارات الملفات والقنوات ---
VIDEO_DB_FILE = "video_database.json"
MANAGER_CHANNEL_LINK = "https://t.me/+r5KJwURUUWI1ZWZk"
ARCHIVE_CHANNEL_LINK = "https://t.me/archive4mv"
ARCHIVE_CHANNEL_USERNAME = "@archive4mv"

class SearchBot:
    def __init__(self):
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.video_db = self.load_video_db()
        # self.manager_channel_id = None
        # self.archive_channel_id = None
        # self.is_bot_in_manager = False
        # self.is_bot_in_archive = False
        # self.has_post_permission_archive = False
        # self.has_read_permission_manager = False

    def load_video_db(self) -> dict:
        """تحميل قاعدة بيانات الفيديو من ملف JSON"""
        if not os.path.exists(VIDEO_DB_FILE):
            logger.warning(f"⚠️ {VIDEO_DB_FILE} غير موجود!")
            return {}
        try:
            with open(VIDEO_DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"⚠️ خطأ في قراءة {VIDEO_DB_FILE}: {str(e)}")
            return {}

    def clean_title(self, title: str) -> str:
        """تنظيف عنوان الفيلم من الروابط والعلامات غير المرغوبة"""
        if not title:
            return ""
        title = re.sub(r'https?://\S+', '', title)
        title = re.sub(r'@\w+', '', title)
        title = re.sub(r'\*{1,2}', '', title)
        title = re.sub(r'[➲:•▪▫●►]+', '', title)
        return re.sub(r'\s+', ' ', title).strip()

    async def is_admin(self, user_id: int, username: str = None) -> bool:
        """التحقق مما إذا كان المستخدم مشرفًا"""
        return user_id == ADMIN_ID or (username and username.lower() == ADMIN_USERNAME.lower())

    # async def check_channels_status(self, context: ContextTypes.DEFAULT_TYPE):
    #     """التحقق من حالة البوت في قناتي المصدر والأرشيف"""
    #     bot = await context.bot.get_me()
    #
    #     # التحقق من قناة المصدر (Manager Channel)
    #     try:
    #         manager_chat = await context.bot.get_chat(MANAGER_CHANNEL_LINK)
    #         self.manager_channel_id = manager_chat.id
    #         manager_member = await context.bot.get_chat_member(chat_id=manager_chat.id, user_id=bot.id)
    #         self.is_bot_in_manager = True
    #         self.has_read_permission_manager = manager_member.status in ['administrator', 'creator', 'member']
    #         logger.info(f"✅ البوت في قناة المصدر مع صلاحية القراءة: {self.has_read_permission_manager}")
    #     except Exception as e:
    #         self.is_bot_in_manager = False
    #         self.has_read_permission_manager = False
    #         logger.error(f"🚫 خطأ في التحقق من قناة المصدر: {str(e)}")
    #
    #     # التحقق من قناة الأرشيف
    #     try:
    #         archive_chat = await context.bot.get_chat(ARCHIVE_CHANNEL_USERNAME)
    #         self.archive_channel_id = archive_chat.id
    #         archive_member = await context.bot.get_chat_member(chat_id=archive_chat.id, user_id=bot.id)
    #         self.is_bot_in_archive = True
    #         self.has_post_permission_archive = archive_member.status in ['administrator', 'creator'] and getattr(archive_member, 'can_post_messages', False)
    #         logger.info(f"✅ البوت في قناة الأرشيف مع صلاحية النشر: {self.has_post_permission_archive}")
    #     except Exception as e:
    #         self.is_bot_in_archive = False
    #         self.has_post_permission_archive = False
    #         logger.error(f"🚫 خطأ في التحقق من قناة الأرشيف: {str(e)}")

    async def search_in_database(self, query: str) -> list:
        """البحث في قاعدة البيانات عن فيلم بالاسم أو المعرف"""
        results = []
        if query.isdigit():
            if query in self.video_db:
                results.append((self.video_db[query]["title"], query))
        else:
            query_lower = query.lower()
            for video_id, data in self.video_db.items():
                if query_lower in data["title"].lower():
                    results.append((data["title"], video_id))
        results.sort(key=lambda x: len(query) / len(x[0]) if len(x[0]) > 0 else 0, reverse=True)
        return results[:10]  # حد أقصى 10 نتائج

    async def process_video_result(self, video_id: str, context: ContextTypes.DEFAULT_TYPE) -> tuple:
        """جلب الفيديو من قناة المصدر وتحويله إلى الأرشيف"""
        # if not self.is_bot_in_manager or not self.has_read_permission_manager:
        #     logger.error("🚫 البوت ليس في قناة المصدر أو ليس لديه صلاحية القراءة")
        #     return None, None
        # if not self.is_bot_in_archive or not self.has_post_permission_archive:
        #     logger.error("🚫 البوت ليس في قناة الأرشيف أو ليس لديه صلاحية النشر")
        #     return None, None

        try:
            # جلب الفيديو من قناة المصدر
            message = await context.bot.forward_message(
                chat_id=MANAGER_CHANNEL_LINK,
                from_chat_id=MANAGER_CHANNEL_LINK,
                message_id=int(video_id)
            )
            if not message.video:
                logger.error(f"🚫 الفيديو بمعرف {video_id} غير موجود في قناة المصدر")
                return None, None

            title = self.clean_title(self.video_db.get(video_id, {}).get("title", "فيلم بدون عنوان"))

            # تحويل الفيديو إلى قناة الأرشيف
            sent_message = await context.bot.send_video(
                chat_id=ARCHIVE_CHANNEL_USERNAME,
                video=message.video.file_id,
                caption=f"**{title}**",
                parse_mode="Markdown"
            )
            post_link = f"https://t.me/{ARCHIVE_CHANNEL_USERNAME.lstrip('@')}/{sent_message.message_id}"
            logger.info(f"✅ تم تحويل الفيديو {video_id} إلى الأرشيف: {post_link}")
            return post_link, title
        except Exception as e:
            logger.error(f"🚫 خطأ في معالجة الفيديو {video_id}: {str(e)}")
            return None, None

    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """عرض القائمة الرئيسية"""
        buttons = [
            [InlineKeyboardButton("🔍 بحث عن فيلم", callback_data="search_movie")],
            [InlineKeyboardButton("📚 قناة الأرشيف", url=ARCHIVE_CHANNEL_LINK)]
        ]
        user_id = update.effective_user.id if update.effective_user else None
        username = update.effective_user.username if update.effective_user else None
        if user_id and await self.is_admin(user_id, username):
            buttons.append([InlineKeyboardButton("⚙️ لوحة الأدمن", callback_data="admin_settings")])

        text = "**🎬 مرحبًا بك في بوت البحث عن الأفلام!**\n\nاختر خيارًا من الأزرار أدناه:"
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج أمر البدء"""
        if not update.message:
            return
        # await self.check_channels_status(context)

        # if not self.is_bot_in_manager or not self.has_read_permission_manager:
        #     await update.message.reply_text(
        #         "**🚫 البوت غير مضاف إلى قناة المصدر أو ليس لديه صلاحية القراءة!**\n\nأضف البوت إلى القناة:",
        #         reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("قناة المصدر", url=MANAGER_CHANNEL_LINK)]]),
        #         parse_mode="Markdown"
        #     )
        #     return
        # if not self.is_bot_in_archive or not self.has_post_permission_archive:
        #     await update.message.reply_text(
        #         "**🚫 البوت غير مضاف إلى قناة الأرشيف أو ليس لديه صلاحية النشر!**\n\nأضف البوت إلى القناة:",
        #         reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("قناة الأرشيف", url=ARCHIVE_CHANNEL_LINK)]]),
        #         parse_mode="Markdown"
        #     )
        #     return
        await self.show_main_menu(update, context)

    async def admin_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """عرض قائمة الأدمن"""
        if not update.callback_query or not await self.is_admin(update.effective_user.id, update.effective_user.username):
            await update.callback_query.answer("🚫 هذا القسم للأدمن فقط!")
            return await self.show_main_menu(update, context)

        buttons = [
            [InlineKeyboardButton("📊 إحصائيات البوت", callback_data="bot_stats")],
            [InlineKeyboardButton("🏠 العودة إلى القائمة", callback_data="main_menu")]
        ]
        await update.callback_query.edit_message_text(
            "**⚙️ لوحة تحكم الأدمن**\n\nاختر خيارًا:",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )

    async def get_bot_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """عرض إحصائيات البوت"""
        if not update.callback_query or not await self.is_admin(update.effective_user.id, update.effective_user.username):
            return await self.show_main_menu(update, context)

        video_count = len(self.video_db)
        stats = (
            f"**📊 إحصائيات البوت**\n\n"
            f"• عدد الأفلام: {video_count}\n"
            f"• قناة المصدر: {MANAGER_CHANNEL_LINK}\n"
            f"• قناة الأرشيف: {ARCHIVE_CHANNEL_USERNAME}\n"
            # f"• حالة قناة المصدر: {'✅ متصل' if self.is_bot_in_manager else '❌ غير متصل'}\n"
            # f"• صلاحية القراءة: {'✅ متاحة' if self.has_read_permission_manager else '❌ غير متاحة'}\n"
            # f"• حالة قناة الأرشيف: {'✅ متصل' if self.is_bot_in_archive else '❌ غير متصل'}\n"
            # f"• صلاحية النشر: {'✅ متاحة' if self.has_post_permission_archive else '❌ غير متاحة'}"
        )
        await update.callback_query.edit_message_text(
            stats,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 العودة", callback_data="admin_settings")]]),
            parse_mode="Markdown"
        )

    async def handle_search_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """طلب إدخال استعلام البحث"""
        await update.callback_query.edit_message_text(
            "**🔍 أدخل اسم الفيلم للبحث:**\n\nأرسل اسم الفيلم في رسالة جديدة.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 العودة", callback_data="main_menu")]]),
            parse_mode="Markdown"
        )
        context.user_data['waiting_for'] = 'search_query'

    async def process_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة البحث وإظهار النتائج بأزرار"""
        if not update.message or 'waiting_for' not in context.user_data or context.user_data['waiting_for'] != 'search_query':
            return

        query = self.clean_title(update.message.text)
        if not query:
            await update.message.reply_text(
                "**🚫 يرجى إدخال اسم فيلم صالح!**",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔍 بحث جديد", callback_data="search_movie")]]),
                parse_mode="Markdown"
            )
            return

        sent_message = await update.message.reply_text("**🔍 جاري البحث...**", parse_mode="Markdown")
        search_results = await self.search_in_database(query)

        if not search_results:
            await sent_message.edit_text(
                f"**🚫 لم يتم العثور على نتائج لـ '{query}'!**\n\nجرب كلمات أخرى.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔍 بحث جديد", callback_data="search_movie")]]),
                parse_mode="Markdown"
            )
            return

        if len(search_results) == 1:
            title, video_id = search_results[0]
            post_link, title = await self.process_video_result(video_id, context)
            if post_link:
                await sent_message.edit_text(
                    f"**🎬 فيلم: [{title}]({post_link})**\n**🔗 الرابط: [اضغط هنا ♥️]({post_link})**",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔍 بحث جديد", callback_data="search_movie")]]),
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )
            else:
                await sent_message.edit_text(
                    "**🚫 خطأ في جلب الفيديو!**",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔍 بحث جديد", callback_data="search_movie")]]),
                    parse_mode="Markdown"
                )
        else:
            response = f"**نتائج البحث عن: {query} 🔍**\n\n"
            emoji_numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            buttons = []
            for i, (title, video_id) in enumerate(search_results):
                response += f"{emoji_numbers[i]} {title}\n\n"
                display_title = title[:25] + "..." if len(title) > 25 else title
                buttons.append([InlineKeyboardButton(f"{emoji_numbers[i]} {display_title}", callback_data=f"video_{video_id}")])
            buttons.append([InlineKeyboardButton("🏠 العودة", callback_data="main_menu")])
            await sent_message.edit_text(response, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")

        del context.user_data['waiting_for']

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الضغط على الأزرار"""
        if not update.callback_query:
            return

        data = update.callback_query.data
        username = update.callback_query.from_user.username or "مستخدم"

        try:
            if data == "main_menu":
                await self.show_main_menu(update, context)
            elif data == "search_movie":
                await self.handle_search_query(update, context)
            elif data == "admin_settings":
                await self.admin_menu(update, context)
            elif data == "bot_stats":
                await self.get_bot_stats(update, context)
            elif data.startswith("video_"):
                video_id = data.split("_")[1]
                post_link, title = await self.process_video_result(video_id, context)
                if post_link:
                    await update.callback_query.edit_message_text(
                        f"**🎬 فيلم: [{title}]({post_link})**\n**🔗 الرابط: [اضغط هنا ♥️]({post_link})**",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔍 بحث جديد", callback_data="search_movie")]]),
                        parse_mode="Markdown",
                        disable_web_page_preview=True
                    )
                else:
                    await update.callback_query.edit_message_text(
                        "**🚫 خطأ في جلب الفيديو!**",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔍 بحث جديد", callback_data="search_movie")]]),
                        parse_mode="Markdown"
                    )
            else:
                await update.callback_query.answer("🚫 خيار غير معروف!")
        except Exception as e:
            logger.error(f"🚫 خطأ في معالجة '{data}' من @{username}: {str(e)}")
            await update.callback_query.edit_message_text(
                "**🚫 حدث خطأ أثناء المعالجة!**",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 العودة", callback_data="main_menu")]]),
                parse_mode="Markdown"
            )

    def setup_handlers(self):
        """إعداد معالجات الأحداث"""
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_search))
        logger.info("✅ تم إعداد معالجات الأحداث")

    def run(self):
        """تشغيل البوت"""
        self.setup_handlers()
        logger.info("🚀 البوت يعمل الآن...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    bot = SearchBot()
    bot.run()

