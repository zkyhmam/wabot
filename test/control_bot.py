import logging
import re
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ForceReply, Message
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

# --- Logging Configuration ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class ControlBot:
    def __init__(self, movie_bot):
        self.movie_bot = movie_bot
        self.application = Application.builder().token("7558529929:AAFmMHm2HuqHsdqdQvl_ZLCoXn5XOPiRzfw").build()
        # Initialize operations_state with default values if not already set
        default_ops = ["share", "check", "check_cross", "check_dp", "sv_dp"]
        for op in default_ops:
            if op not in self.movie_bot.operations_state:
                self.movie_bot.operations_state[op] = {
                    "running": False,
                    "task": None,
                    "channel": None,
                    "from_channel": None,
                    "to_channel": None,
                    "track_new": False
                }
        self.setup_handlers()
        self.pending_inputs = {}  # لتخزين المدخلات المؤقتة
        self.progress_messages = {}  # لتخزين رسائل التقدم

    def is_admin(self, user_id):
        """Check if the user is the admin"""
        return user_id == self.movie_bot.config["admin_id"]

    def setup_handlers(self):
        """Setup all bot handlers"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("rm_dp", self.rm_dp_command))
        self.application.add_handler(CommandHandler("sv_dp", self.sv_dp_command))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        self.application.add_handler(MessageHandler(filters.Regex(r'^(Share|شارك)'), self.handle_share_command))
        self.application.add_handler(MessageHandler(filters.Regex(r'^(Check|فحص)\s+-from'), self.handle_check_cross_command))
        self.application.add_handler(MessageHandler(filters.Regex(r'^(Check|فحص)\s+dp'), self.handle_check_dp_command))
        self.application.add_handler(MessageHandler(filters.Regex(r'^(Check|فحص)'), self.handle_check_command))
        self.application.add_handler(MessageHandler(filters.Regex(r'^(Stop|إيقاف)'), self.handle_stop_command))
        self.application.add_handler(MessageHandler(filters.Regex(r'^/حذف_البيانات'), self.rm_dp_command))  # دعم الأمر العربي
        self.application.add_handler(MessageHandler(filters.Regex(r'^/حفظ_البيانات'), self.sv_dp_command))  # دعم الأمر العربي
        self.application.add_handler(MessageHandler(filters.REPLY & filters.TEXT, self.handle_reply))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    async def start_command(self, update: Update, context):
        """Handle /start command"""
        user = update.effective_user
        if not user or not self.is_admin(user.id):
            await update.message.reply_text("عذراً، هذا البوت مخصص للأدمن فقط.")
            return
        keyboard = [
            [InlineKeyboardButton("📊 حالة البوت", callback_data="status")],
            [InlineKeyboardButton("🔄 العمليات", callback_data="operations")],
            [InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings")],
            [InlineKeyboardButton("📋 قائمة الأوامر", callback_data="commands")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "مرحباً بك في لوحة التحكم الخاصة بـ Zaky AI.\nاختر أحد الخيارات أدناه للبدء:",
            reply_markup=reply_markup
        )
        logger.info("Start command executed")

    async def help_command(self, update: Update, context):
        """Handle /help command"""
        user = update.effective_user
        if not user or not self.is_admin(user.id):
            return
        await update.message.reply_text(
            "📋 *قائمة الأوامر المتاحة:*\n\n"
            "*شارك/Share -from [رابط] -to [رابط] [on/off]*\nنقل الفيديوهات من قناة إلى أخرى\n\n"
            "*فحص/Check -from [رابط] -to [رابط] [on/off]*\nفحص التقاطع بين قناتين ونقل الفيديوهات غير الموجودة\n\n"
            "*فحص/Check [رابط] [on/off]*\nفحص قناة وتنظيف عناوين الفيديوهات\n\n"
            "*فحص/Check dp [on/off]*\nفحص وتنظيف قاعدة بيانات الفيديوهات\n\n"
            "*حذف_البيانات/rm_dp*\nحذف قاعدة البيانات\n\n"
            "*حفظ_البيانات/sv_dp [رابط] [on/off]*\nحفظ محتوى قناة في قاعدة البيانات\n\n"
            "*إيقاف/Stop [share/check/dp/all]*\nإيقاف عملية محددة أو كل العمليات\n\n"
            "/status - عرض حالة البوت\n",
            parse_mode="Markdown"
        )
        logger.info("Help command executed")

    async def status_command(self, update: Update, context):
        """Handle /status command"""
        user = update.effective_user
        if not user or not self.is_admin(user.id):
            return
        stats = await self.movie_bot.get_stats()
        keyboard = [
            [InlineKeyboardButton("🔙", callback_data="main_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
        ]
        await update.message.reply_text(stats, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        logger.info("Status command executed")

    async def rm_dp_command(self, update: Update, context):
        """Handle rm_dp command"""
        user = update.effective_user
        if not user or not self.is_admin(user.id):
            return
        await self.movie_bot.clear_database()  # افترض أن هذه دالة في MovieBot لحذف قاعدة البيانات
        await update.message.reply_text("**تم حذف قاعدة البيانات بنجاح! 🗑️**", parse_mode="Markdown")
        logger.info("Database cleared via rm_dp command")

    async def sv_dp_command(self, update: Update, context):
        """Handle sv_dp command"""
        user = update.effective_user
        if not user or not self.is_admin(user.id):
            return
        text = update.message.text
        match = re.match(r'^(sv_dp|حفظ_البيانات)\s+(\S+)(?:\s+(on|off))?$', text, re.IGNORECASE)
        if not match:
            msg = await update.message.reply_text("أرسل لينك القناة التي تريد حفظها:", reply_markup=ForceReply())
            self.pending_inputs[user.id] = {"operation": "sv_dp", "step": "link", "message_id": msg.message_id}
            return
        channel_link, track_new = match.group(2), match.group(3) == "on" if match.group(3) else False
        await self.start_sv_dp(update, context, channel_link, track_new)

    async def start_sv_dp(self, update: Update, context, channel_link, track_new):
        """Start sv_dp operation with progress tracking"""
        if self.movie_bot.operations_state["sv_dp"]["running"]:
            await update.message.reply_text("**عملية حفظ قاعدة البيانات قيد التنفيذ بالفعل! ⏳**", parse_mode="Markdown")
            return
        progress_msg = await update.message.reply_text(f"**💾 جاري حفظ البيانات من: {channel_link}**", parse_mode="Markdown")
        self.progress_messages["sv_dp"] = progress_msg
        self.movie_bot.operations_state["sv_dp"]["running"] = True
        self.movie_bot.operations_state["sv_dp"]["channel"] = channel_link
        self.movie_bot.operations_state["sv_dp"]["track_new"] = track_new
        self.movie_bot.operations_state["sv_dp"]["task"] = asyncio.create_task(
            self.movie_bot.save_channel_to_db(channel_link, track_new, self.update_progress)
        )
        logger.info(f"Save dp started: {channel_link}, track_new={track_new}")

    async def update_progress(self, operation, completed, remaining, success, failed, duration):
        """Update progress message for an operation"""
        if operation in self.progress_messages:
            msg = self.progress_messages[operation]
            op_state = self.movie_bot.operations_state.get(operation, {})
            if operation in ["share", "check_cross"]:
                text = (
                    f"**🔄 جاري {operation} من: {op_state.get('from_channel', 'غير محدد')} إلى: {op_state.get('to_channel', 'غير محدد')}**\n"
                    f"✅ تم: {success} عنصر\n"
                    f"⏳ الوقت المنقضي: {duration} ثانية"
                )
            else:
                text = (
                    f"**{'🔍' if operation in ['check', 'check_dp'] else '💾'} جاري {operation} لـ: {op_state.get('channel', 'غير محدد')}**\n"
                    f"✅ تم: {success} عنصر\n"
                    f"⏳ الوقت المنقضي: {duration} ثانية"
                )
            keyboard = [
                [InlineKeyboardButton("⏹ إيقاف", callback_data=f"stop_{operation}")],
                [InlineKeyboardButton("🔙", callback_data="operations"), InlineKeyboardButton("🏡", callback_data="main_menu")]
            ]
            try:
                await msg.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            except Exception as e:
                logger.error(f"Failed to update progress for {operation}: {e}")

    async def button_handler(self, update: Update, context):
        """Handle button presses"""
        query = update.callback_query
        user = update.effective_user
        if not user or not self.is_admin(user.id):
            await query.answer("عذراً، هذا البوت مخصص للأدمن فقط.")
            return
        await query.answer()

        if query.data == "status":
            stats = await self.movie_bot.get_stats()
            keyboard = [
                [InlineKeyboardButton("🔙", callback_data="main_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
            ]
            await query.edit_message_text(stats, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data == "operations":
            keyboard = [
                [InlineKeyboardButton("🔄 شارك/Share", callback_data="share_menu")],
                [InlineKeyboardButton("🔍 فحص/Check", callback_data="check_menu")],
                [InlineKeyboardButton("🔍 فحص التقاطع/Check Cross", callback_data="check_cross_menu")],
                [InlineKeyboardButton("🗄️ فحص قاعدة البيانات/Check dp", callback_data="check_dp_menu")],
                [InlineKeyboardButton("💾 حفظ قاعدة البيانات/Save dp", callback_data="sv_dp_menu")],
                [InlineKeyboardButton("⏹ إيقاف الكل/Stop All", callback_data="stop_all")],
                [InlineKeyboardButton("🔙", callback_data="main_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
            ]
            await query.edit_message_text("اختر العملية:", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data == "settings":
            keyboard = [
                [InlineKeyboardButton("🔙", callback_data="main_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
            ]
            await query.edit_message_text("الإعدادات تحت التطوير حالياً ⚙️", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data == "commands":
            keyboard = [
                [InlineKeyboardButton("🔙", callback_data="main_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
            ]
            await query.edit_message_text(
                "📋 *قائمة الأوامر المتاحة:*\n\n"
                "*شارك/Share -from [رابط] -to [رابط] [on/off]*\nنقل الفيديوهات من قناة إلى أخرى\n\n"
                "*فحص/Check -from [رابط] -to [رابط] [on/off]*\nفحص التقاطع بين قناتين ونقل الفيديوهات غير الموجودة\n\n"
                "*فحص/Check [رابط] [on/off]*\nفحص قناة وتنظيف عناوين الفيديوهات\n\n"
                "*فحص/Check dp [on/off]*\nفحص وتنظيف قاعدة بيانات الفيديوهات\n\n"
                "*حذف_البيانات/rm_dp*\nحذف قاعدة البيانات\n\n"
                "*حفظ_البيانات/sv_dp [رابط] [on/off]*\nحفظ محتوى قناة في قاعدة البيانات\n\n"
                "*إيقاف/Stop [share/check/dp/all]*\nإيقاف عملية محددة أو كل العمليات\n\n"
                "/status - عرض حالة البوت\n",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif query.data == "main_menu":
            keyboard = [
                [InlineKeyboardButton("📊 حالة البوت", callback_data="status")],
                [InlineKeyboardButton("🔄 العمليات", callback_data="operations")],
                [InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings")],
                [InlineKeyboardButton("📋 قائمة الأوامر", callback_data="commands")]
            ]
            await query.edit_message_text(
                "مرحباً بك في لوحة التحكم الخاصة بـ Zaky AI.\nاختر أحد الخيارات أدناه للبدء:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif query.data == "share_menu":
            keyboard = [
                [InlineKeyboardButton("▶️ بدء/Start", callback_data="start_share")],
                [InlineKeyboardButton("⏹ إيقاف/Stop", callback_data="stop_share")],
                [InlineKeyboardButton("🔄 استمرار/Continue", callback_data="cont_share")],
                [InlineKeyboardButton("🔙", callback_data="operations"), InlineKeyboardButton("🏡", callback_data="main_menu")]
            ]
            await query.edit_message_text("إدارة شارك/Share:", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data == "start_share":
            msg = await query.message.reply_text("أرسل لينك القناة التي تريد النقل منها:", reply_markup=ForceReply())
            self.pending_inputs[user.id] = {"operation": "share", "step": "from_channel", "message_id": msg.message_id}

        elif query.data == "stop_share":
            if self.movie_bot.operations_state["share"]["running"]:
                self.movie_bot.operations_state["share"]["running"] = False
                if self.movie_bot.operations_state["share"]["task"]:
                    self.movie_bot.operations_state["share"]["task"].cancel()
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="share_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**تم إيقاف النقل! ⏹**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
                logger.info("Share stopped via button")
            else:
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="share_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**لا توجد عملية نقل جارية! ⚠️**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data == "cont_share":
            if self.movie_bot.operations_state["share"]["running"]:
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="share_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**عملية نقل قيد التنفيذ بالفعل! ⏳**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            elif "from_channel" in self.movie_bot.share_progress and "to_channel" in self.movie_bot.share_progress:
                progress_msg = await query.message.reply_text(
                    f"**🔄 جاري استكمال النقل من: {self.movie_bot.share_progress['from_channel']} إلى: {self.movie_bot.share_progress['to_channel']}**",
                    parse_mode="Markdown"
                )
                self.progress_messages["share"] = progress_msg
                self.movie_bot.operations_state["share"]["running"] = True
                self.movie_bot.operations_state["share"]["task"] = asyncio.create_task(
                    self.movie_bot.share_videos(
                        self.movie_bot.share_progress["from_channel"],
                        self.movie_bot.share_progress["to_channel"],
                        self.movie_bot.operations_state["share"].get("track_new", False),
                        self.update_progress
                    )
                )
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="share_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**تم استكمال النقل! ▶️**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
                logger.info("Share continued via button")
            else:
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="share_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**لا توجد عملية نقل سابقة لاستكمالها! ⚠️**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data == "check_menu":
            keyboard = [
                [InlineKeyboardButton("▶️ بدء/Start", callback_data="start_check")],
                [InlineKeyboardButton("⏹ إيقاف/Stop", callback_data="stop_check")],
                [InlineKeyboardButton("🔄 استمرار/Continue", callback_data="cont_check")],
                [InlineKeyboardButton("🔙", callback_data="operations"), InlineKeyboardButton("🏡", callback_data="main_menu")]
            ]
            await query.edit_message_text("إدارة فحص/Check:", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data == "start_check":
            msg = await query.message.reply_text("أرسل لينك القناة التي تريد فحصها:", reply_markup=ForceReply())
            self.pending_inputs[user.id] = {"operation": "check", "step": "channel", "message_id": msg.message_id}

        elif query.data == "stop_check":
            if self.movie_bot.operations_state["check"]["running"]:
                self.movie_bot.operations_state["check"]["running"] = False
                if self.movie_bot.operations_state["check"]["task"]:
                    self.movie_bot.operations_state["check"]["task"].cancel()
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="check_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**تم إيقاف الفحص! ⏹**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
                logger.info("Check stopped via button")
            else:
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="check_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**لا توجد عملية فحص جارية! ⚠️**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data == "cont_check":
            if self.movie_bot.operations_state["check"]["running"]:
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="check_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**عملية فحص قيد التنفيذ بالفعل! ⏳**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            elif self.movie_bot.operations_state["check"].get("channel"):
                progress_msg = await query.message.reply_text(
                    f"**🔍 جاري استكمال الفحص لـ: {self.movie_bot.operations_state['check']['channel']}**",
                    parse_mode="Markdown"
                )
                self.progress_messages["check"] = progress_msg
                self.movie_bot.operations_state["check"]["running"] = True
                self.movie_bot.operations_state["check"]["task"] = asyncio.create_task(
                    self.movie_bot.check_channel(
                        self.movie_bot.operations_state["check"]["channel"],
                        self.movie_bot.operations_state["check"].get("track_new", False),
                        self.update_progress
                    )
                )
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="check_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**تم استكمال الفحص! ▶️**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
                logger.info("Check continued via button")
            else:
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="check_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**لا توجد عملية فحص سابقة لاستكمالها! ⚠️**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data == "check_cross_menu":
            keyboard = [
                [InlineKeyboardButton("▶️ بدء/Start", callback_data="start_check_cross")],
                [InlineKeyboardButton("⏹ إيقاف/Stop", callback_data="stop_check_cross")],
                [InlineKeyboardButton("🔄 استمرار/Continue", callback_data="cont_check_cross")],
                [InlineKeyboardButton("🔙", callback_data="operations"), InlineKeyboardButton("🏡", callback_data="main_menu")]
            ]
            await query.edit_message_text("إدارة فحص التقاطع/Check Cross:", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data == "start_check_cross":
            msg = await query.message.reply_text("أرسل لينك القناة التي تريد الفحص منها:", reply_markup=ForceReply())
            self.pending_inputs[user.id] = {"operation": "check_cross", "step": "from_channel", "message_id": msg.message_id}

        elif query.data == "stop_check_cross":
            if self.movie_bot.operations_state["check_cross"]["running"]:
                self.movie_bot.operations_state["check_cross"]["running"] = False
                if self.movie_bot.operations_state["check_cross"]["task"]:
                    self.movie_bot.operations_state["check_cross"]["task"].cancel()
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="check_cross_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**تم إيقاف فحص التقاطع! ⏹**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
                logger.info("Check cross stopped via button")
            else:
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="check_cross_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**لا توجد عملية فحص تقاطع جارية! ⚠️**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data == "cont_check_cross":
            if self.movie_bot.operations_state["check_cross"]["running"]:
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="check_cross_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**عملية فحص تقاطع قيد التنفيذ بالفعل! ⏳**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            elif self.movie_bot.operations_state["check_cross"].get("from_channel") and self.movie_bot.operations_state["check_cross"].get("to_channel"):
                progress_msg = await query.message.reply_text(
                    f"**🔍 جاري استكمال فحص التقاطع من: {self.movie_bot.operations_state['check_cross']['from_channel']} إلى: {self.movie_bot.operations_state['check_cross']['to_channel']}**",
                    parse_mode="Markdown"
                )
                self.progress_messages["check_cross"] = progress_msg
                self.movie_bot.operations_state["check_cross"]["running"] = True
                self.movie_bot.operations_state["check_cross"]["task"] = asyncio.create_task(
                    self.movie_bot.check_cross_channels(
                        self.movie_bot.operations_state["check_cross"]["from_channel"],
                        self.movie_bot.operations_state["check_cross"]["to_channel"],
                        self.movie_bot.operations_state["check_cross"].get("track_new", False),
                        self.update_progress
                    )
                )
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="check_cross_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**تم استكمال فحص التقاطع! ▶️**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
                logger.info("Check cross continued via button")
            else:
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="check_cross_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**لا توجد عملية فحص تقاطع سابقة لاستكمالها! ⚠️**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data == "check_dp_menu":
            keyboard = [
                [InlineKeyboardButton("▶️ بدء/Start", callback_data="start_check_dp")],
                [InlineKeyboardButton("⏹ إيقاف/Stop", callback_data="stop_check_dp")],
                [InlineKeyboardButton("🔄 استمرار/Continue", callback_data="cont_check_dp")],
                [InlineKeyboardButton("🔙", callback_data="operations"), InlineKeyboardButton("🏡", callback_data="main_menu")]
            ]
            await query.edit_message_text("إدارة فحص قاعدة البيانات/Check dp:", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data == "start_check_dp":
            msg = await query.message.reply_text("هل تريد تتبع التغييرات؟", reply_markup=ForceReply())
            self.pending_inputs[user.id] = {"operation": "check_dp", "step": "track_changes", "message_id": msg.message_id}

        elif query.data == "stop_check_dp":
            if self.movie_bot.operations_state["check_dp"]["running"]:
                self.movie_bot.operations_state["check_dp"]["running"] = False
                if self.movie_bot.operations_state["check_dp"]["task"]:
                    self.movie_bot.operations_state["check_dp"]["task"].cancel()
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="check_dp_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**تم إيقاف تنظيف قاعدة البيانات! ⏹**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
                logger.info("Check dp stopped via button")
            else:
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="check_dp_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**لا توجد عملية تنظيف قاعدة بيانات جارية! ⚠️**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data == "cont_check_dp":
            if self.movie_bot.operations_state["check_dp"]["running"]:
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="check_dp_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**عملية تنظيف قاعدة البيانات قيد التنفيذ بالفعل! ⏳**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                progress_msg = await query.message.reply_text("**🔍 جاري استكمال تنظيف قاعدة البيانات...**", parse_mode="Markdown")
                self.progress_messages["check_dp"] = progress_msg
                self.movie_bot.operations_state["check_dp"]["running"] = True
                self.movie_bot.operations_state["check_dp"]["task"] = asyncio.create_task(
                    self.movie_bot.check_database(
                        self.movie_bot.operations_state["check_dp"].get("track_changes", False),
                        self.update_progress
                    )
                )
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="check_dp_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**تم استكمال تنظيف قاعدة البيانات! ▶️**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
                logger.info("Check dp continued via button")

        elif query.data == "sv_dp_menu":
            keyboard = [
                [InlineKeyboardButton("▶️ بدء/Start", callback_data="start_sv_dp")],
                [InlineKeyboardButton("⏹ إيقاف/Stop", callback_data="stop_sv_dp")],
                [InlineKeyboardButton("🔄 استمرار/Continue", callback_data="cont_sv_dp")],
                [InlineKeyboardButton("🔙", callback_data="operations"), InlineKeyboardButton("🏡", callback_data="main_menu")]
            ]
            await query.edit_message_text("إدارة حفظ قاعدة البيانات/Save dp:", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data == "start_sv_dp":
            msg = await query.message.reply_text("أرسل لينك القناة التي تريد حفظها:", reply_markup=ForceReply())
            self.pending_inputs[user.id] = {"operation": "sv_dp", "step": "link", "message_id": msg.message_id}

        elif query.data == "stop_sv_dp":
            if self.movie_bot.operations_state["sv_dp"]["running"]:
                self.movie_bot.operations_state["sv_dp"]["running"] = False
                if self.movie_bot.operations_state["sv_dp"]["task"]:
                    self.movie_bot.operations_state["sv_dp"]["task"].cancel()
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="sv_dp_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**تم إيقاف حفظ قاعدة البيانات! ⏹**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
                logger.info("Save dp stopped via button")
            else:
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="sv_dp_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**لا توجد عملية حفظ قاعدة بيانات جارية! ⚠️**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data == "cont_sv_dp":
            if self.movie_bot.operations_state["sv_dp"]["running"]:
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="sv_dp_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**عملية حفظ قاعدة البيانات قيد التنفيذ بالفعل! ⏳**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            elif self.movie_bot.operations_state["sv_dp"].get("channel"):
                progress_msg = await query.message.reply_text(
                    f"**💾 جاري استكمال حفظ البيانات من: {self.movie_bot.operations_state['sv_dp']['channel']}**",
                    parse_mode="Markdown"
                )
                self.progress_messages["sv_dp"] = progress_msg
                self.movie_bot.operations_state["sv_dp"]["running"] = True
                self.movie_bot.operations_state["sv_dp"]["task"] = asyncio.create_task(
                    self.movie_bot.save_channel_to_db(
                        self.movie_bot.operations_state["sv_dp"]["channel"],
                        self.movie_bot.operations_state["sv_dp"].get("track_new", False),
                        self.update_progress
                    )
                )
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="sv_dp_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**تم استكمال حفظ قاعدة البيانات! ▶️**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
                logger.info("Save dp continued via button")
            else:
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="sv_dp_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.edit_message_text("**لا توجد عملية حفظ سابقة لاستكمالها! ⚠️**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data == "stop_all":
            stopped = False
            for op in ["share", "check", "check_cross", "check_dp", "sv_dp"]:
                if self.movie_bot.operations_state[op]["running"]:
                    self.movie_bot.operations_state[op]["running"] = False
                    if self.movie_bot.operations_state[op]["task"]:
                        self.movie_bot.operations_state[op]["task"].cancel()
                    stopped = True
            keyboard = [
                [InlineKeyboardButton("🔙", callback_data="operations"), InlineKeyboardButton("🏡", callback_data="main_menu")]
            ]
            if stopped:
                await query.edit_message_text("**تم إيقاف جميع العمليات الجارية! ⏹**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
                logger.info("All operations stopped via button")
            else:
                await query.edit_message_text("**لا توجد عمليات جارية لإيقافها! ⚠️**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

        # Handle track_new button responses
        elif query.data in ["share_track_on", "share_track_off"]:
            track_new = query.data == "share_track_on"
            pending = self.pending_inputs.get(user.id, {})
            if pending.get("operation") == "share" and "from_channel" in pending and "to_channel" in pending:
                await context.bot.delete_message(chat_id=query.message.chat_id, message_id=query.message.message_id)
                progress_msg = await query.message.reply_text(
                    f"**🔄 جاري نقل الفيديوهات من: {pending['from_channel']} إلى: {pending['to_channel']}**",
                    parse_mode="Markdown"
                )
                self.progress_messages["share"] = progress_msg
                self.movie_bot.share_progress["from_channel"] = pending["from_channel"]
                self.movie_bot.share_progress["to_channel"] = pending["to_channel"]
                self.movie_bot.save_share_progress()
                self.movie_bot.operations_state["share"]["running"] = True
                self.movie_bot.operations_state["share"]["from_channel"] = pending["from_channel"]
                self.movie_bot.operations_state["share"]["to_channel"] = pending["to_channel"]
                self.movie_bot.operations_state["share"]["track_new"] = track_new
                self.movie_bot.operations_state["share"]["task"] = asyncio.create_task(
                    self.movie_bot.share_videos(pending["from_channel"], pending["to_channel"], track_new, self.update_progress)
                )
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="share_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.message.reply_text("**بدأ نقل الفيديوهات! 🔄**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
                logger.info(f"Share started: from {pending['from_channel']} to {pending['to_channel']}, track_new={track_new}")
                del self.pending_inputs[user.id]

        elif query.data in ["check_track_on", "check_track_off"]:
            track_new = query.data == "check_track_on"
            pending = self.pending_inputs.get(user.id, {})
            if pending.get("operation") == "check" and "channel" in pending:
                await context.bot.delete_message(chat_id=query.message.chat_id, message_id=query.message.message_id)
                progress_msg = await query.message.reply_text(
                    f"**🔍 جاري فحص القناة: {pending['channel']}**",
                    parse_mode="Markdown"
                )
                self.progress_messages["check"] = progress_msg
                self.movie_bot.operations_state["check"]["channel"] = pending["channel"]
                self.movie_bot.operations_state["check"]["track_new"] = track_new
                self.movie_bot.operations_state["check"]["running"] = True
                self.movie_bot.operations_state["check"]["task"] = asyncio.create_task(
                    self.movie_bot.check_channel(pending["channel"], track_new, self.update_progress)
                )
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="check_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.message.reply_text("**بدأ فحص القناة! 🔍**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
                logger.info(f"Check started: {pending['channel']}, track_new={track_new}")
                del self.pending_inputs[user.id]

        elif query.data in ["check_cross_track_on", "check_cross_track_off"]:
            track_new = query.data == "check_cross_track_on"
            pending = self.pending_inputs.get(user.id, {})
            if pending.get("operation") == "check_cross" and "from_channel" in pending and "to_channel" in pending:
                await context.bot.delete_message(chat_id=query.message.chat_id, message_id=query.message.message_id)
                progress_msg = await query.message.reply_text(
                    f"**🔍 جاري فحص التقاطع من: {pending['from_channel']} إلى: {pending['to_channel']}**",
                    parse_mode="Markdown"
                )
                self.progress_messages["check_cross"] = progress_msg
                self.movie_bot.operations_state["check_cross"]["from_channel"] = pending["from_channel"]
                self.movie_bot.operations_state["check_cross"]["to_channel"] = pending["to_channel"]
                self.movie_bot.operations_state["check_cross"]["track_new"] = track_new
                self.movie_bot.operations_state["check_cross"]["running"] = True
                self.movie_bot.operations_state["check_cross"]["task"] = asyncio.create_task(
                    self.movie_bot.check_cross_channels(pending["from_channel"], pending["to_channel"], track_new, self.update_progress)
                )
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="check_cross_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.message.reply_text("**بدأ فحص التقاطع بين القنوات! 🔍**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
                logger.info(f"Check cross started: from {pending['from_channel']} to {pending['to_channel']}, track_new={track_new}")
                del self.pending_inputs[user.id]

        elif query.data in ["sv_dp_track_on", "sv_dp_track_off"]:
            track_new = query.data == "sv_dp_track_on"
            pending = self.pending_inputs.get(user.id, {})
            if pending.get("operation") == "sv_dp" and "channel" in pending:
                await context.bot.delete_message(chat_id=query.message.chat_id, message_id=query.message.message_id)
                progress_msg = await query.message.reply_text(
                    f"**💾 جاري حفظ البيانات من: {pending['channel']}**",
                    parse_mode="Markdown"
                )
                self.progress_messages["sv_dp"] = progress_msg
                self.movie_bot.operations_state["sv_dp"]["channel"] = pending["channel"]
                self.movie_bot.operations_state["sv_dp"]["track_new"] = track_new
                self.movie_bot.operations_state["sv_dp"]["running"] = True
                self.movie_bot.operations_state["sv_dp"]["task"] = asyncio.create_task(
                    self.movie_bot.save_channel_to_db(pending["channel"], track_new, self.update_progress)
                )
                keyboard = [
                    [InlineKeyboardButton("🔙", callback_data="sv_dp_menu"), InlineKeyboardButton("🏡", callback_data="main_menu")]
                ]
                await query.message.reply_text("**بدأ حفظ البيانات! 💾**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
                logger.info(f"Save dp started: {pending['channel']}, track_new={track_new}")
                del self.pending_inputs[user.id]

    async def handle_share_command(self, update: Update, context):
        user = update.effective_user
        if not user or not self.is_admin(user.id):
            return
        text = update.message.text
        match = re.match(r'^(Share|شارك)\s+-from\s+(\S+)\s+-to\s+(\S+)(?:\s+(on|off))?$', text, re.IGNORECASE)
        if not match:
            msg = await update.message.reply_text("أرسل لينك القناة التي تريد النقل منها:", reply_markup=ForceReply())
            self.pending_inputs[user.id] = {"operation": "share", "step": "from_channel", "message_id": msg.message_id}
            return
        from_channel, to_channel, track_new = match.group(2), match.group(3), match.group(4) == "on" if match.group(4) else False
        progress_msg = await update.message.reply_text(
            f"**🔄 جاري نقل الفيديوهات من: {from_channel} إلى: {to_channel}**",
            parse_mode="Markdown"
        )
        self.progress_messages["share"] = progress_msg
        self.movie_bot.share_progress["from_channel"] = from_channel
        self.movie_bot.share_progress["to_channel"] = to_channel
        self.movie_bot.save_share_progress()
        self.movie_bot.operations_state["share"]["running"] = True
        self.movie_bot.operations_state["share"]["from_channel"] = from_channel
        self.movie_bot.operations_state["share"]["to_channel"] = to_channel
        self.movie_bot.operations_state["share"]["track_new"] = track_new
        self.movie_bot.operations_state["share"]["task"] = asyncio.create_task(
            self.movie_bot.share_videos(from_channel, to_channel, track_new, self.update_progress)
        )
        await update.message.reply_text("**بدأ نقل الفيديوهات! 🔄**", parse_mode="Markdown")
        logger.info(f"Share started: from {from_channel} to {to_channel}, track_new={track_new}")

    async def handle_check_cross_command(self, update: Update, context):
        user = update.effective_user
        if not user or not self.is_admin(user.id):
            return
        text = update.message.text
        match = re.match(r'^(Check|فحص)\s+-from\s+(\S+)\s+-to\s+(\S+)(?:\s+(on|off))?$', text, re.IGNORECASE)
        if not match:
            msg = await update.message.reply_text("أرسل لينك القناة التي تريد الفحص منها:", reply_markup=ForceReply())
            self.pending_inputs[user.id] = {"operation": "check_cross", "step": "from_channel", "message_id": msg.message_id}
            return
        from_channel, to_channel, track_new = match.group(2), match.group(3), match.group(4) == "on" if match.group(4) else False
        progress_msg = await update.message.reply_text(
            f"**🔍 جاري فحص التقاطع من: {from_channel} إلى: {to_channel}**",
            parse_mode="Markdown"
        )
        self.progress_messages["check_cross"] = progress_msg
        self.movie_bot.operations_state["check_cross"]["running"] = True
        self.movie_bot.operations_state["check_cross"]["from_channel"] = from_channel
        self.movie_bot.operations_state["check_cross"]["to_channel"] = to_channel
        self.movie_bot.operations_state["check_cross"]["track_new"] = track_new
        self.movie_bot.operations_state["check_cross"]["task"] = asyncio.create_task(
            self.movie_bot.check_cross_channels(from_channel, to_channel, track_new, self.update_progress)
        )
        await update.message.reply_text("**بدأ فحص التقاطع بين القنوات! 🔍**", parse_mode="Markdown")
        logger.info(f"Check cross started: from {from_channel} to {to_channel}, track_new={track_new}")

    async def handle_check_dp_command(self, update: Update, context):
        user = update.effective_user
        if not user or not self.is_admin(user.id):
            return
        text = update.message.text
        match = re.match(r'^(Check|فحص)\s+dp(?:\s+(on|off))?$', text, re.IGNORECASE)
        if not match:
            msg = await update.message.reply_text("هل تريد تتبع التغييرات؟", reply_markup=ForceReply())
            self.pending_inputs[user.id] = {"operation": "check_dp", "step": "track_changes", "message_id": msg.message_id}
            return
        track_changes = match.group(2) == "on" if match.group(2) else False
        progress_msg = await update.message.reply_text("**🔍 جاري تنظيف قاعدة البيانات...**", parse_mode="Markdown")
        self.progress_messages["check_dp"] = progress_msg
        self.movie_bot.operations_state["check_dp"]["running"] = True
        self.movie_bot.operations_state["check_dp"]["track_changes"] = track_changes
        self.movie_bot.operations_state["check_dp"]["task"] = asyncio.create_task(
            self.movie_bot.check_database(track_changes, self.update_progress)
        )
        await update.message.reply_text("**بدأ تنظيف قاعدة البيانات! 🔍**", parse_mode="Markdown")
        logger.info(f"Check dp started: track_changes={track_changes}")

    async def handle_check_command(self, update: Update, context):
        user = update.effective_user
        if not user or not self.is_admin(user.id):
            return
        text = update.message.text
        match = re.match(r'^(Check|فحص)\s+(\S+)(?:\s+(on|off))?$', text, re.IGNORECASE)
        if not match or "-from" in text:
            msg = await update.message.reply_text("أرسل لينك القناة التي تريد فحصها:", reply_markup=ForceReply())
            self.pending_inputs[user.id] = {"operation": "check", "step": "channel", "message_id": msg.message_id}
            return
        channel_link, track_new = match.group(2), match.group(3) == "on" if match.group(3) else False
        progress_msg = await update.message.reply_text(
            f"**🔍 جاري فحص القناة: {channel_link}**",
            parse_mode="Markdown"
        )
        self.progress_messages["check"] = progress_msg
        self.movie_bot.operations_state["check"]["running"] = True
        self.movie_bot.operations_state["check"]["channel"] = channel_link
        self.movie_bot.operations_state["check"]["track_new"] = track_new
        self.movie_bot.operations_state["check"]["task"] = asyncio.create_task(
            self.movie_bot.check_channel(channel_link, track_new, self.update_progress)
        )
        await update.message.reply_text("**بدأ فحص القناة! 🔍**", parse_mode="Markdown")
        logger.info(f"Check started: {channel_link}, track_new={track_new}")

    async def handle_stop_command(self, update: Update, context):
        user = update.effective_user
        if not user or not self.is_admin(user.id):
            return
        text = update.message.text.lower()
        if text in ["stop share", "إيقاف شارك"]:
            if self.movie_bot.operations_state["share"]["running"]:
                self.movie_bot.operations_state["share"]["running"] = False
                if self.movie_bot.operations_state["share"]["task"]:
                    self.movie_bot.operations_state["share"]["task"].cancel()
                await update.message.reply_text("**تم إيقاف النقل! ⏹**", parse_mode="Markdown")
                logger.info("Share stopped via command")
            else:
                await update.message.reply_text("**لا توجد عملية نقل جارية! ⚠️**", parse_mode="Markdown")
        elif text in ["stop check", "إيقاف فحص"]:
            if self.movie_bot.operations_state["check"]["running"]:
                self.movie_bot.operations_state["check"]["running"] = False
                if self.movie_bot.operations_state["check"]["task"]:
                    self.movie_bot.operations_state["check"]["task"].cancel()
                await update.message.reply_text("**تم إيقاف فحص القناة! ⏹**", parse_mode="Markdown")
                logger.info("Check stopped via command")
            else:
                await update.message.reply_text("**لا توجد عملية فحص جارية! ⚠️**", parse_mode="Markdown")
        elif text in ["stop", "إيقاف"]:
            stopped = False
            for op in ["share", "check", "check_cross", "check_dp", "sv_dp"]:
                if self.movie_bot.operations_state[op]["running"]:
                    self.movie_bot.operations_state[op]["running"] = False
                    if self.movie_bot.operations_state[op]["task"]:
                        self.movie_bot.operations_state[op]["task"].cancel()
                    stopped = True
            if stopped:
                await update.message.reply_text("**تم إيقاف جميع العمليات الجارية! ⏹**", parse_mode="Markdown")
                logger.info("All operations stopped via command")
            else:
                await update.message.reply_text("**لا توجد عمليات جارية لإيقافها! ⚠️**", parse_mode="Markdown")

    async def handle_reply(self, update: Update, context):
        user = update.effective_user
        if not user or not self.is_admin(user.id) or user.id not in self.pending_inputs:
            return
        text = update.message.text
        pending = self.pending_inputs[user.id]
        operation = pending["operation"]
        step = pending["step"]

        if operation == "share":
            if step == "from_channel":
                pending["from_channel"] = text
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=pending["message_id"])
                msg = await update.message.reply_text(
                    "أرسل لينك القناة التي تريد النقل إليها:",
                    reply_markup=ForceReply()
                )
                pending["message_id"] = msg.message_id
                pending["step"] = "to_channel"
            elif step == "to_channel":
                pending["to_channel"] = text
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=pending["message_id"])
                msg = await update.message.reply_text(
                    "هل تريد تتبع التغييرات؟",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🟢", callback_data="share_track_on"), InlineKeyboardButton("🔴", callback_data="share_track_off")]
                    ])
                )
                pending["message_id"] = msg.message_id
                pending["step"] = "track_new"

        elif operation == "check":
            if step == "channel":
                pending["channel"] = text
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=pending["message_id"])
                msg = await update.message.reply_text(
                    "هل تريد تتبع التغييرات؟",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🟢", callback_data="check_track_on"), InlineKeyboardButton("🔴", callback_data="check_track_off")]
                    ])
                )
                pending["message_id"] = msg.message_id
                pending["step"] = "track_new"

        elif operation == "check_cross":
            if step == "from_channel":
                pending["from_channel"] = text
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=pending["message_id"])
                msg = await update.message.reply_text(
                    "أرسل لينك القناة التي تريد الفحص إليها:",
                    reply_markup=ForceReply()
                )
                pending["message_id"] = msg.message_id
                pending["step"] = "to_channel"
            elif step == "to_channel":
                pending["to_channel"] = text
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=pending["message_id"])
                msg = await update.message.reply_text(
                    "هل تريد تتبع التغييرات؟",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🟢", callback_data="check_cross_track_on"), InlineKeyboardButton("🔴", callback_data="check_cross_track_off")]
                    ])
                )
                pending["message_id"] = msg.message_id
                pending["step"] = "track_new"

        elif operation == "check_dp":
            if step == "track_changes":
                track_changes = text.lower() in ["on", "نعم"]
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=pending["message_id"])
                progress_msg = await update.message.reply_text("**🔍 جاري تنظيف قاعدة البيانات...**", parse_mode="Markdown")
                self.progress_messages["check_dp"] = progress_msg
                self.movie_bot.operations_state["check_dp"]["track_changes"] = track_changes
                self.movie_bot.operations_state["check_dp"]["running"] = True
                self.movie_bot.operations_state["check_dp"]["task"] = asyncio.create_task(
                    self.movie_bot.check_database(track_changes, self.update_progress)
                )
                await update.message.reply_text("**بدأ تنظيف قاعدة البيانات! 🔍**", parse_mode="Markdown")
                logger.info(f"Check dp started: track_changes={track_changes}")
                del self.pending_inputs[user.id]

        elif operation == "sv_dp":
            if step == "link":
                pending["channel"] = text
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=pending["message_id"])
                msg = await update.message.reply_text(
                    "هل تريد تتبع التغييرات؟",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🟢", callback_data="sv_dp_track_on"), InlineKeyboardButton("🔴", callback_data="sv_dp_track_off")]
                    ])
                )
                pending["message_id"] = msg.message_id
                pending["step"] = "track_new"

    async def handle_message(self, update: Update, context):
        user = update.effective_user
        if not user or not self.is_admin(user.id):
            return
        await update.message.reply_text("استخدم الأوامر أو الأزرار للتحكم في البوت!")

    async def run(self):
        """Run the bot asynchronously"""
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        logger.info("Control Bot started successfully")
