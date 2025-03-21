from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply, InputMediaPhoto
from telegram.ext import ContextTypes
import logging
import aiohttp
import os
from akwam import search_akwam, get_video_details, get_direct_download_link, AkwamSearchResult
from database import check_content, store_content, get_stats, add_admin, update_config
from config import GIF_START, GIF_SUCCESS, GIF_FAIL, SUB_CHANNEL_ID, ADMIN_IDS, DB_CHANNEL_ID
from utils import is_subscribed, resolve_channel_id
from tmdb import get_movie_info

# إعداد التسجيل مع ألوان ANSI
class ColoredFormatter(logging.Formatter):
    COLORS = {
        'INFO': '\033[92m',    # أخضر
        'WARNING': '\033[93m', # أصفر
        'ERROR': '\033[91m',   # أحمر
        'CRITICAL': '\033[95m',# بنفسجي
        'RESET': '\033[0m'     # إعادة تعيين
    }

    def format(self, record):
        log_message = super().format(record)
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        return f"{color}{log_message}{self.COLORS['RESET']}"

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = ColoredFormatter(
    '%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    datefmt='%m/%d/%y %H:%M:%S'
)
handler.setFormatter(formatter)
logger.addHandler(handler)

user_sessions = {}
download_tasks = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not await is_subscribed(context, user.id, SUB_CHANNEL_ID):
        await update.message.reply_text("📢 Please subscribe to the channel first: @ChannelLink")
        return
    await update.message.reply_animation(GIF_START, caption=f"🎬 Welcome {user.first_name}! Send a movie name 🌟")
    user_sessions[user.id] = {"state": "start"}
    if user.id in ADMIN_IDS:
        keyboard = [
            [InlineKeyboardButton("📊 Stats", callback_data="stats"), InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings")],
            [InlineKeyboardButton("❤️ Quote", callback_data="quote")]
        ]
        await update.message.reply_text("👑 Welcome Admin!", reply_markup=InlineKeyboardMarkup(keyboard))
    logger.info(f"🚀 User started: {user.id}")

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_subscribed(context, user_id, SUB_CHANNEL_ID):
        await update.message.reply_text("📢 Please subscribe to the channel first: @ChannelLink")
        return
    query = update.message.text.strip()
    if user_sessions.get(user_id, {}).get("state") in ["set_gif_start", "set_db_channel", "set_sub_channel", "add_admin"]:
        await handle_admin_input(update, context)
        return
    await update.message.reply_text(f"🔎 Searching for: {query} ⏳")
    results = await search_akwam(query)
    if not results:
        await update.message.reply_animation(GIF_FAIL, caption="😔 No results found!")
        return
    user_sessions[user_id] = {"state": "results", "query": query, "results": results}
    keyboard = []
    for i, r in enumerate(results[:10]):
        keyboard.append([InlineKeyboardButton(f"{r.title}", callback_data=f"result:{i}")])
    keyboard.append([InlineKeyboardButton("🔍 New Search", callback_data="new_search")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back"), InlineKeyboardButton("🏡 Home", callback_data="home")])
    await update.message.reply_animation(GIF_SUCCESS, caption="🎥 Search Results:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    session = user_sessions.get(user_id, {"state": "start"})
    data = query.data

    try:
        if data == "home":
            await query.edit_message_caption(caption="🎬 Send a movie name 🌟", reply_markup=InlineKeyboardMarkup([]))
            session["state"] = "start"
        elif data == "new_search":
            await query.edit_message_caption(caption="📽️ Send a new movie name 🍿", reply_markup=InlineKeyboardMarkup([]))
            session["state"] = "start"
        elif data == "back":
            if session["state"] == "details":
                await show_results(query, session)
            elif session["state"] == "admin":
                await query.edit_message_text(text="👑 Welcome Admin!", reply_markup=admin_main_menu())
        elif data == "stats":
            if user_id in ADMIN_IDS:
                stats = await get_stats()
                await query.edit_message_text(text=f"📊 Stats:\nUsers: {stats['users']}", reply_markup=admin_main_menu())
        elif data == "admin_settings":
            if user_id in ADMIN_IDS:
                session["state"] = "admin"
                await query.edit_message_text(text="⚙️ Admin Settings:", reply_markup=admin_settings_menu())
        elif data in ["set_gif_start", "set_db_channel", "set_sub_channel", "add_admin"]:
            session["state"] = data
            prompts = {
                "set_gif_start": "📎 Send the new start GIF link:",
                "set_db_channel": "📎 Send the new archive channel ID or link:",
                "set_sub_channel": "📎 Send the new subscription channel ID or link:",
                "add_admin": "📎 Send the new admin ID or username:"
            }
            await query.message.reply_text(prompts[data], reply_markup=ForceReply(selective=True))
        elif data.startswith("result:"):
            idx = int(data.split(":")[1])
            result = session["results"][idx]
            details = await get_video_details(result)
            tmdb_info = await get_movie_info(result.title)
            session["state"] = "details"
            session["selected"] = details
            keyboard = []
            if details and details.qualities:
                for i, q in enumerate(details.qualities):
                    quality_label = f"{q.resolution} ({q.size or 'Unknown'})"
                    keyboard.append([InlineKeyboardButton(quality_label, callback_data=f"quality:{i}")])
            keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back"), InlineKeyboardButton("🏡 Home", callback_data="home")])
            caption = f"🎬 {tmdb_info.get('title', details.title)}\n"
            if tmdb_info and tmdb_info.get("overview"):
                caption += f"📝 {tmdb_info['overview'][:200]}...\n"
            caption += "Select Quality:"
            poster_url = f"https://image.tmdb.org/t/p/w1280{tmdb_info.get('backdrop_path')}" if tmdb_info and tmdb_info.get('backdrop_path') else details.thumbnail
            await query.edit_message_media(
                media=InputMediaPhoto(media=poster_url or GIF_SUCCESS, caption=caption),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif data.startswith("quality:"):
            idx = int(data.split(":")[1])
            quality = session["selected"].qualities[idx]
            direct_link = await check_content(quality.url) or await get_direct_download_link(quality)
            if direct_link:
                await start_download(query, context, direct_link, session["selected"].title, quality)
            else:
                await query.edit_message_media(
                    media=InputMediaPhoto(GIF_FAIL, caption="😔 Failed to extract link!"),
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏡 Home", callback_data="home")]])
                )
        elif data.startswith("cancel_download:"):
            task_id = data.split(":")[1]
            if task_id in download_tasks:
                download_tasks[task_id]["cancelled"] = True
                await query.edit_message_caption(caption="❌ Download cancelled!", reply_markup=InlineKeyboardMarkup([]))
                if os.path.exists(download_tasks[task_id]["file_path"]):
                    os.remove(download_tasks[task_id]["file_path"])
                del download_tasks[task_id]
    except Exception as e:
        logger.error(f"Error handling button '{data}': {str(e)}")
        await query.edit_message_media(
            media=InputMediaPhoto(GIF_FAIL, caption="❌ An error occurred, try again!"),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏡 Home", callback_data="home")]])
        )

async def start_download(query, context, url, title, quality):
    user_id = query.from_user.id
    task_id = f"{user_id}_{query.message.message_id}"
    file_path = f"downloads/{title}_{quality.resolution}.mp4"
    os.makedirs("downloads", exist_ok=True)
    
    download_tasks[task_id] = {"cancelled": False, "file_path": file_path}
    message = await query.edit_message_caption(
        caption=f"⬇️ Downloading {title} ({quality.resolution})...\nProgress: 0%",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_download:{task_id}")]])
    )

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                await message.edit_caption(caption="❌ Failed to start download!", reply_markup=InlineKeyboardMarkup([]))
                return

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            chunk_size = 1024 * 1024  # 1MB chunks

            with open(file_path, 'wb') as f:
                async for chunk in response.content.iter_chunked(chunk_size):
                    if download_tasks.get(task_id, {}).get("cancelled"):
                        break
                    downloaded += len(chunk)
                    f.write(chunk)
                    if total_size > 0:
                        progress = int((downloaded / total_size) * 100)
                        await message.edit_caption(
                            caption=f"⬇️ Downloading {title} ({quality.resolution})...\nProgress: {progress}%",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_download:{task_id}")]])
                        )
                    await asyncio.sleep(1)  # تحديث كل ثانية

            if not download_tasks.get(task_id, {}).get("cancelled"):
                await message.edit_caption(
                    caption=f"✅ Download completed!\nFile: {file_path}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏡 Home", callback_data="home")]])
                )
            else:
                if os.path.exists(file_path):
                    os.remove(file_path)

async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = user_sessions.get(user_id, {})
    text = update.message.text.strip()

    if session["state"] == "set_gif_start":
        await update_config("GIF_START", text)
        await update.message.reply_text("✅ Start GIF updated!", reply_markup=admin_settings_menu())
    elif session["state"] == "set_db_channel":
        channel_id = await resolve_channel_id(context, text)
        if channel_id:
            await update_config("DB_CHANNEL_ID", channel_id)
            await update.message.reply_text("✅ Archive channel updated!", reply_markup=admin_settings_menu())
        else:
            await update.message.reply_text("❌ Invalid channel ID, try again:", reply_markup=ForceReply(selective=True))
            return
    elif session["state"] == "set_sub_channel":
        channel_id = await resolve_channel_id(context, text)
        ifκό

        if channel_id:
            await update_config("SUB_CHANNEL_ID", channel_id)
            await update.message.reply_text("✅ Subscription channel updated!", reply_markup=admin_settings_menu())
        else:
            await update.message.reply_text("❌ Invalid channel ID, try again:", reply_markup=ForceReply(selective=True))
            return
    elif session["state"] == "add_admin":
        admin_id = int(text) if text.isdigit() else None
        if admin_id:
            await add_admin(admin_id)
            await update.message.reply_text("✅ Admin added!", reply_markup=admin_settings_menu())
        else:
            await update.message.reply_text("❌ Invalid ID or username, try again:", reply_markup=ForceReply(selective=True))
            return
    session["state"] = "admin"

async def show_results(query, session):
    keyboard = []
    for i, r in enumerate(session["results"][:10]):
        keyboard.append([InlineKeyboardButton(f"{r.title}", callback_data=f"result:{i}")])
    keyboard.append([InlineKeyboardButton("🔍 New Search", callback_data="new_search")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back"), InlineKeyboardButton("🏡 Home", callback_data="home")])
    await query.edit_message_media(
        media=InputMediaPhoto(GIF_SUCCESS, caption="🎥 Search Results:"),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    session["state"] = "results"

def admin_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Stats", callback_data="stats"), InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings")],
        [InlineKeyboardButton("❤️ Quote", callback_data="quote")]
    ])

def admin_settings_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📎 Change Start GIF", callback_data="set_gif_start")],
        [InlineKeyboardButton("📎 Change Archive Channel", callback_data="set_db_channel")],
        [InlineKeyboardButton("📎 Change Subscription Channel", callback_data="set_sub_channel")],
        [InlineKeyboardButton("👑 Add Admin", callback_data="add_admin")],
        [InlineKeyboardButton("🔙 Back", callback_data="back")]
    ])
