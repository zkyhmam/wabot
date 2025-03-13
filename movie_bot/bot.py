from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, CallbackContext, ExtBot
from telegram import Update
import logging
from config import config
import handlers
import asyncio
from telegram.constants import ParseMode
import nest_asyncio
nest_asyncio.apply()

# إعداد السجل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def error_handler(update: Update, context: CallbackContext) -> None:
    logger.error(f"حدث خطأ: {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ حدث خطأ أثناء معالجة طلبك.  الرجاء المحاولة مرة أخرى لاحقًا."
            )
    except:
        pass

async def main() -> None:
    application = Application.builder().token(config.TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", handlers.start_command))
    application.add_handler(CommandHandler("help", handlers.help_command))
    application.add_handler(CommandHandler("admin_users", handlers.handle_callback))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message))
    application.add_handler(CallbackQueryHandler(handlers.handle_callback))

    application.add_error_handler(error_handler)

    print("Bot is running...")
    await application.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
