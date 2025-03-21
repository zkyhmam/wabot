#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import os
import sys
import signal
import traceback
from datetime import datetime
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.error import TelegramError, NetworkError
from handlers import start, search, button_handler
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box
from rich.logging import RichHandler
from pyfiglet import Figlet
import time

# تهيئة Rich Console
console = Console()

# عرض البانر الاحترافي
def display_banner():
    fig = Figlet(font='slant')
    banner = fig.renderText('ZAKY DL')
    styled_banner = Text()
    for line in banner.split('\n'):
        styled_banner.append(line + '\n', style="bold cyan")
    console.print(Panel(
        styled_banner,
        box=box.DOUBLE,
        border_style="green",
        title="[bold yellow]ZAKY Download Bot[/bold yellow]",
        subtitle=f"[bold blue]Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/bold blue]"
    ))

# إعداد التسجيل
def setup_logging():
    rich_handler = RichHandler(rich_tracebacks=True, markup=True, show_time=True, show_path=False)
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"bot_{datetime.now().strftime('%Y%m%d')}.log")
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger = logging.getLogger('zaky_dl_bot')
    logger.setLevel(logging.INFO)
    logger.addHandler(rich_handler)
    logger.addHandler(file_handler)
    logging.captureWarnings(True)
    return logger

# معالجة الأخطاء
class ErrorHandler:
    def __init__(self, logger):
        self.logger = logger

    def handle_error(self, update, context):
        error_trace = traceback.format_exc()
        self.logger.error(f"Update {update} caused error:\n{error_trace}")
        if isinstance(context.error, NetworkError):
            self.logger.warning("Network error occurred. Retrying in 10 seconds...")
            time.sleep(10)
        elif isinstance(context.error, TelegramError):
            self.logger.error(f"Telegram API Error: {context.error}")
        else:
            self.logger.critical(f"Unhandled exception: {context.error}")

# إغلاق البوت برفق
def signal_handler(sig, frame):
    console.print("[bold red]Shutdown signal received. Closing bot gracefully...[/bold red]")
    sys.exit(0)

def main():
    display_banner()
    logger = setup_logging()
    logger.info("Initializing ZAKY DL Telegram Bot...")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        application = Application.builder().token("7558529929:AAFmMHm2HuqHsdqdQvl_ZLCoXn5XOPiRzfw").build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search))
        application.add_handler(CallbackQueryHandler(button_handler))
        error_handler = ErrorHandler(logger)
        application.add_error_handler(error_handler.handle_error)

        with console.status("[bold green]Starting bot...[/bold green]"):
            time.sleep(1)
        console.print(Panel(
            "[bold green]Bot is now online and ready to serve![/bold green]",
            box=box.ROUNDED,
            border_style="green"
        ))
        logger.info("Bot is running and listening for updates")
        application.run_polling(allowed_updates=["message", "callback_query"])

    except Exception as e:
        error_trace = traceback.format_exc()
        logger.critical(f"Critical error during startup: {e}\n{error_trace}")
        console.print(Panel(
            f"[bold red]FATAL ERROR: {e}[/bold red]",
            box=box.HEAVY,
            border_style="red"
        ))
        sys.exit(1)

if __name__ == "__main__":
    main()
