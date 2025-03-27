import logging
import asyncio
import os
import time
import aiohttp
import signal
import shutil
from bs4 import BeautifulSoup
import re
from urllib.parse import quote_plus
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from playwright.async_api import async_playwright
import pymongo

# Configure logging
logging.basicConfig(
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants
API_ID = 25713843
API_HASH = "311352d08811e7f5136dfb27f71014c1"
TOKEN = "7957198144:AAH4PBpm0mwpRAQ_Ek-sDNe2bDs5Xfo9W5U"
WECIMA_BASE_URL = "https://vbn3.t4ce4ma.shop/"
DOWNLOAD_DIR = "/overlay_tmp"
CHUNK_SIZE = 20 * 1024 * 1024  # 20MB chunks
UPDATE_INTERVAL = 1  # Update every 1 second
SUB_CHANNEL_ID = -1002026172929
ADMIN_IDS = [6988696258]
MONGO_URI = "mongodb+srv://zkyhmam:Zz462008##@cluster0.7bpsz.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

# MongoDB setup
mongo_client = pymongo.MongoClient(MONGO_URI)
db = mongo_client["movie_bot"]
users_collection = db["users"]
movies_collection = db["movies"]

# Set Playwright browsers path
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/overlay_tmp/playwright_browsers"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Active downloads tracking
active_downloads = {}

# Initialize Pyrogram client
app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=TOKEN)

# Cleanup function
def cleanup_downloads():
    if os.path.exists(DOWNLOAD_DIR):
        try:
            shutil.rmtree(DOWNLOAD_DIR)
            logger.info("Deleted download directory and all files")
            os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        except Exception as e:
            logger.error(f"Error cleaning up downloads: {e}")

# Signal handler for graceful shutdown
def signal_handler(sig, frame):
    logger.info("Bot shutting down, cleaning up files...")
    cleanup_downloads()
    exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Check subscription
async def check_subscription(chat_id):
    try:
        member = await app.get_chat_member(SUB_CHANNEL_ID, chat_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# Add navigation buttons
def add_navigation_buttons():
    return [InlineKeyboardButton("🔙", callback_data="back"), InlineKeyboardButton("🏡", callback_data="home")]

# Handle /start command
@app.on_message(filters.command("start"))
async def start(client, message):
    chat_id = message.chat.id
    if not await check_subscription(chat_id):
        keyboard = [[InlineKeyboardButton("اشترك في القناة", url=f"https://t.me/{abs(SUB_CHANNEL_ID)}")]]
        await app.send_message(chat_id, "يرجى الاشتراك في القناة لاستخدام البوت!", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    keyboard = [[InlineKeyboardButton("تواصل مع المطور", url="https://t.me/zaky1million")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await app.send_message(chat_id, "Welcome! Send me a movie name to search and download. (Series not supported) 🎬", reply_markup=reply_markup)

# Search results display
async def display_results(client, chat_id, message_id, page=0):
    results = getattr(client, 'search_results', [])
    total_pages = (len(results) - 1) // 5 + 1
    start = page * 5
    end = min(start + 5, len(results))
    current_results = results[start:end]

    keyboard = [[InlineKeyboardButton(result['title'], callback_data=f"select_result_{start + i}")] for i, result in enumerate(current_results)]
    
    # Add pagination buttons
    pagination = []
    if page > 0:
        pagination.append(InlineKeyboardButton("السابق", callback_data=f"prev_page_{page - 1}"))
    if page < total_pages - 1:
        pagination.append(InlineKeyboardButton("التالي", callback_data=f"next_page_{page + 1}"))
    if pagination:
        keyboard.append(pagination)
    
    # Add navigation buttons
    keyboard.append(add_navigation_buttons())
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await app.edit_message_text(chat_id, message_id, f"اختر فيلماً (صفحة {page + 1}/{total_pages}): 🎥", reply_markup=reply_markup)

# Handle text messages
@app.on_message(filters.text)
async def handle_message(client, message):
    chat_id = message.chat.id
    if not await check_subscription(chat_id):
        await start(client, message)
        return

    query = message.text
    status_message = await app.send_message(chat_id, f"جاري البحث عن '{query}'... 🔍")
    
    results = await search_wecima(query)
    if not results:
        await app.edit_message_text(chat_id, status_message.id, "لم يتم العثور على نتائج 😔")
        return
    
    client.search_results = results
    await display_results(client, chat_id, status_message.id, 0)

# Handle callback queries
@app.on_callback_query()
async def handle_callback(client, callback_query):
    chat_id = callback_query.message.chat.id
    data = callback_query.data
    message_id = callback_query.message.id

    if not await check_subscription(chat_id):
        await start(client, callback_query.message)
        return

    if data.startswith("select_result_"):
        index = int(data.split("_")[-1])
        results = getattr(client, 'search_results', [])
        if index < len(results):
            selected_result = results[index]
            details = await get_movie_details(selected_result['url'])
            if not details or not details['download_links']:
                await app.edit_message_text(chat_id, message_id, "لا توجد روابط تحميل متاحة 😔")
                return
            client.movie_details = details
            keyboard = [[InlineKeyboardButton(link['quality'], callback_data=f"select_quality_{i}")] for i, link in enumerate(details['download_links'])]
            keyboard.append(add_navigation_buttons())
            reply_markup = InlineKeyboardMarkup(keyboard)
            await app.edit_message_text(chat_id, message_id, f"اختر جودة لـ {details['title']}: 🎬", reply_markup=reply_markup)
    
    elif data.startswith("select_quality_"):
        index = int(data.split("_")[-1])
        details = getattr(client, 'movie_details', {})
        download_links = details.get('download_links', [])
        if index < len(download_links):
            selected_link = download_links[index]
            await app.edit_message_text(chat_id, message_id, f"جاري التحميل: {details['title']} - {selected_link['quality']} ⏳")
            success = await download_movie(selected_link['url'], details['title'], chat_id)
            if not success:
                await app.send_message(chat_id, "فشل التحميل، حاول لاحقاً 😔")
    
    elif data.startswith("prev_page_"):
        page = int(data.split("_")[-1])
        await display_results(client, chat_id, message_id, page)
    
    elif data.startswith("next_page_"):
        page = int(data.split("_")[-1])
        await display_results(client, chat_id, message_id, page)
    
    elif data == "back":
        if hasattr(client, 'search_results'):
            await display_results(client, chat_id, message_id, 0)
    
    elif data == "home":
        await start(client, callback_query.message)
    
    try:
        await callback_query.answer()
    except Exception as e:
        logger.warning(f"Failed to answer callback query: {str(e)}")

# Main function
def main():
    cleanup_downloads()
    app.run()

if __name__ == "__main__":
    main()
