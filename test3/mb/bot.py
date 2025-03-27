import asyncio
import logging
import os
import time
from datetime import datetime, timedelta
from urllib.parse import quote
import requests
from bs4 import BeautifulSoup
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, InputMediaPhoto
from pyrogram.errors import FloodWait
from pymongo import MongoClient
from concurrent.futures import ThreadPoolExecutor

API_ID = 25713843
API_HASH = "311352d08811e7f5136dfb27f71014c1"
BOT_TOKEN = "7558529929:AAFmMHm2HuqHsdqdQvl_ZLCoXn5XOPiRzfw"
MONGO_URI = "mongodb+srv://zkyhmam:Zz462008##@cluster0.7bpsz.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
ADMIN_ID = 6988696258
CHANNEL_ID = -1002098707576

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["movie_bot"]
users_collection = db["users"]
videos_collection = db["videos"]
banned_collection = db["banned"]
channels_collection = db["channels"]

executor = ThreadPoolExecutor(max_workers=5)
download_queue = asyncio.Queue()
active_downloads = {}

from languages import messages

def get_user_lang(user_id):
    user = users_collection.find_one({"user_id": user_id})
    return user["language"] if user and "language" in user else "en"

def update_points():
    for user in users_collection.find():
        if "user_id" not in user:
            continue
        now = datetime.now()
        last_reset = user.get("last_reset", now - timedelta(days=1))
        if now - last_reset >= timedelta(days=1):
            daily_points = 500 if user.get("premium", False) else 60
            users_collection.update_one(
                {"user_id": user["user_id"]},
                {"$set": {"daily_points": daily_points, "last_reset": now}}
            )

def check_points(user_id, cost):
    user = users_collection.find_one({"user_id": user_id})
    if not user:
        return False
    daily_points = user.get("daily_points", 60 if not user.get("premium", False) else 500)
    referral_points = user.get("referral_points", 0)
    total_points = daily_points + referral_points
    return total_points >= cost

def deduct_points(user_id, cost):
    user = users_collection.find_one({"user_id": user_id})
    daily_points = user.get("daily_points", 60 if not user.get("premium", False) else 500)
    referral_points = user.get("referral_points", 0)
    if daily_points >= cost:
        users_collection.update_one({"user_id": user_id}, {"$inc": {"daily_points": -cost}})
    else:
        remaining = cost - daily_points
        users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"daily_points": 0}, "$inc": {"referral_points": -remaining}}
        )

async def get_referral_link(user_id):
    bot_username = (await app.get_me()).username
    return f"https://t.me/{bot_username}?start=ref_{user_id}"

async def check_admin_status():
    try:
        member = await app.get_chat_member(CHANNEL_ID, "me")
        if member.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
            await app.send_message(ADMIN_ID, "Please promote me to admin in the channel!")
            return False
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        await app.send_message(ADMIN_ID, f"Error checking admin status: {e}")
        return False
    return True

async def check_subscription(user_id, message):
    channels = list(channels_collection.find())
    if not channels:
        return True
    buttons = [[InlineKeyboardButton(c["name"], url=c["link"])] for c in channels]
    buttons.append([InlineKeyboardButton(messages[get_user_lang(user_id)]["start"], callback_data="start_after_sub")])
    for channel in channels:
        try:
            member = await app.get_chat_member(channel["id"], user_id)
            if member.status not in [enums.ChatMemberStatus.MEMBER, enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
                await message.reply(messages[get_user_lang(user_id)]["subscribe"], reply_markup=InlineKeyboardMarkup(buttons))
                return False
        except Exception:
            await message.reply(messages[get_user_lang(user_id)]["subscribe"], reply_markup=InlineKeyboardMarkup(buttons))
            return False
    return True

def fetch_page(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except requests.RequestException as e:
        logger.error(f"Error fetching page {url}: {e}")
        raise

def search_content(query):
    url = f"https://ak.sv/search?q={quote(query)}"
    soup = fetch_page(url)
    results = []
    for item in soup.select("div.widget[data-grid='6'] div.row div.col-lg-auto"):
        entry = item.select_one("div.entry-box")
        if not entry:
            continue
        link = entry.select_one("a.box")["href"]
        thumbnail = entry.select_one("img.lazy")["data-src"]
        title = entry.select_one("h3.entry-title a").text
        rating = entry.select_one("span.label.rating").text.strip()
        quality = entry.select_one("span.label.quality").text
        meta = entry.select("span.badge")
        year = meta[0].text if meta else "N/A"
        genres = [g.text for g in meta[1:]] if len(meta) > 1 else []
        results.append({
            "link": link, "thumbnail": thumbnail, "title": title, "rating": rating,
            "quality": quality, "year": year, "genres": genres, "type": "movie" if "/movie/" in link else "series"
        })
    return results

def get_details(url):
    soup = fetch_page(url)
    details = {
        "title": soup.select_one("h1.entry-title").text,
        "thumbnail": soup.select_one("div.col-lg-3.col-md-4 img.img-fluid")["src"],
        "rating": soup.select_one("div.font-size-16.text-white.mt-2 img[alt='IMDb']") and soup.select_one("div.font-size-16.text-white.mt-2").text.split("IMDb")[1].strip() or "N/A",
        "description": soup.select_one("div.text-white p").text if soup.select_one("div.text-white p") else "No description available",
        "trailer": soup.select_one("a[data-fancybox]")["href"] if soup.select_one("a[data-fancybox]") else None,
        "genres": [a.text for a in soup.select("a.badge.badge-pill.badge-light")]
    }
    if "/series/" in url:
        episodes = []
        for ep in soup.select("#series-episodes div.bg-primary2"):
            ep_link = ep.select_one("h2 > a")["href"]
            ep_title = ep.select_one("h2 > a").text
            ep_thumbnail = ep.select_one("img.img-fluid")["src"]
            ep_date = ep.select_one("p.entry-date").text
            episodes.append({"link": ep_link, "title": ep_title, "thumbnail": ep_thumbnail, "date": ep_date})
        details["episodes"] = episodes
    quality_tabs = soup.select("ul.header-tabs.tabs li a")
    qualities = []
    for tab in quality_tabs:
        tab_id = tab["href"].lstrip("#")
        quality = tab.text
        tab_content = soup.select_one(f"div#{tab_id}")
        download_link = tab_content.select_one("a.link-download")["href"]
        size = tab_content.select_one("span.font-size-14.mr-auto").text if tab_content.select_one("span.font-size-14.mr-auto") else "Unknown"
        qualities.append({"quality": quality, "link": download_link, "size": size})
    details["qualities"] = qualities
    return details

def get_direct_link(go_link):
    soup = fetch_page(go_link)
    download_page = soup.select_one("a.download-link")["href"]
    soup = fetch_page(download_page)
    direct_link = soup.select_one("a.link.btn.btn-light")["href"]
    return direct_link

async def process_download(user_id, content, quality, message):
    lang = get_user_lang(user_id)
    direct_link = await asyncio.get_event_loop().run_in_executor(executor, get_direct_link, quality["link"])
    file_name = f"{content['title']}_{quality['quality']}.mp4"
    video_data = videos_collection.find_one({"title": content["title"], "quality": quality["quality"]})
    
    if video_data and "file_id" in video_data:
        try:
            await app.forward_messages(user_id, CHANNEL_ID, video_data["file_id"])
            deduct_points(user_id, 20 if content["type"] == "movie" else 10)
            return
        except Exception:
            videos_collection.delete_one({"_id": video_data["_id"]})
    
    progress_msg = await message.reply(messages[lang]["downloading"].format(0))
    downloaded = 0
    total_size = int(requests.head(direct_link).headers.get("Content-Length", 0))
    start_time = time.time()
    
    with requests.get(direct_link, stream=True) as r:
        with open(file_name, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024*1024):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    percentage = (downloaded / total_size) * 100 if total_size else 0
                    elapsed = time.time() - start_time
                    speed = downloaded / elapsed / 1024 / 1024 if elapsed > 0 else 0
                    if int(elapsed) % 1 == 0:
                        await progress_msg.edit_text(messages[lang]["downloading"].format(int(percentage), speed),
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(messages[lang]["cancel"], callback_data=f"cancel_{user_id}")]]))
    
    video_msg = await app.send_video(CHANNEL_ID, file_name, thumb=content["thumbnail"],
        caption=f"{content['title']} ({quality['quality']})\n{messages[lang]['details'].format(**content)}",
        protect_content=True)
    videos_collection.insert_one({"title": content["title"], "quality": quality["quality"], "file_id": video_msg.id})
    await app.forward_messages(user_id, CHANNEL_ID, video_msg.id)
    deduct_points(user_id, 20 if content["type"] == "movie" else 10)
    await progress_msg.delete()
    os.remove(file_name)

async def download_worker():
    while True:
        user_id, content, quality, message = await download_queue.get()
        active_downloads[user_id] = True
        try:
            await process_download(user_id, content, quality, message)
        except Exception as e:
            logger.error(f"Download error for user {user_id}: {e}")
            lang = get_user_lang(user_id)
            await message.reply(messages[lang]["error"].format(str(e)))
        finally:
            del active_downloads[user_id]
            download_queue.task_done()

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    
    # Check if user is banned
    if banned_collection.find_one({"user_id": user_id}):
        await message.reply(messages[lang]["banned"])
        return

    # Check admin status in channel
    if not await check_admin_status():
        if user_id == ADMIN_ID:
            await message.reply("Bot is not admin in the channel. Please fix this!")
        return

    # Handle referral
    if "ref_" in message.text:
        ref_id = int(message.text.split("ref_")[1])
        if ref_id != user_id:
            users_collection.update_one({"user_id": ref_id}, {"$inc": {"referral_points": 20}}, upsert=True)
            ref_user = users_collection.find_one({"user_id": ref_id})
            await app.send_message(ref_id, messages[lang]["referral_bonus"].format(
                message.from_user.first_name, ref_user.get("referral_points", 0), ref_user.get("daily_points", 60)),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(messages[lang]["check_points"], callback_data="check_points")]]))

    # Check if user exists, if not prompt for language
    user = users_collection.find_one({"user_id": user_id})
    if not user:
        await message.reply(messages["en"]["select_lang"], reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("العربية", callback_data="lang_ar"), InlineKeyboardButton("English", callback_data="lang_en")]
        ]))
        return

    # Check subscription
    if not await check_subscription(user_id, message):
        return

    # Welcome message with buttons
    buttons = [
        [InlineKeyboardButton(messages[lang]["search"], switch_inline_query_current_chat="")],
        [InlineKeyboardButton(messages[lang]["help"], callback_data="help"), InlineKeyboardButton(messages[lang]["about"], callback_data="about")],
        [InlineKeyboardButton(messages[lang]["contact_admin"], url="https://t.me/Zaky1million")],
    ]
    if user_id == ADMIN_ID:
        buttons.append([InlineKeyboardButton(messages[lang]["admin_panel"], callback_data="admin_panel")])
    
    try:
        referral_link = await get_referral_link(user_id)
        await message.reply(messages[lang]["welcome"].format(referral_link),
            reply_markup=InlineKeyboardMarkup(buttons))
    except FloodWait as e:
        await asyncio.sleep(e.x)
        referral_link = await get_referral_link(user_id)
        await message.reply(messages[lang]["welcome"].format(referral_link),
            reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"lang_(ar|en)"))
async def set_language(client, callback):
    user_id = callback.from_user.id
    lang = callback.data.split("_")[1]
    users_collection.update_one({"user_id": user_id}, {"$set": {"language": lang, "daily_points": 60, "last_reset": datetime.now()}}, upsert=True)
    await callback.message.edit_text(messages[lang]["lang_set"], reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(messages[lang]["start"], callback_data="start_after_sub")]
    ]))

@app.on_callback_query(filters.regex("start_after_sub"))
async def start_after_sub(client, callback):
    user_id = callback.from_user.id
    lang = get_user_lang(user_id)
    if await check_subscription(user_id, callback.message):
        buttons = [
            [InlineKeyboardButton(messages[lang]["search"], switch_inline_query_current_chat="")],
            [InlineKeyboardButton(messages[lang]["help"], callback_data="help"), InlineKeyboardButton(messages[lang]["about"], callback_data="about")],
            [InlineKeyboardButton(messages[lang]["contact_admin"], url="https://t.me/Zaky1million")],
        ]
        if user_id == ADMIN_ID:
            buttons.append([InlineKeyboardButton(messages[lang]["admin_panel"], callback_data="admin_panel")])
        referral_link = await get_referral_link(user_id)
        await callback.message.edit_text(messages[lang]["welcome"].format(referral_link),
            reply_markup=InlineKeyboardMarkup(buttons))

@app.on_inline_query()
async def inline_search(client, inline_query):
    query = inline_query.query.strip()
    if not query:
        await inline_query.answer([], switch_pm_text=messages[get_user_lang(inline_query.from_user.id)]["search_prompt"], switch_pm_parameter="search")
        return
    try:
        results = await asyncio.get_event_loop().run_in_executor(executor, search_content, query)
        answers = []
        for i, result in enumerate(results[:50]):
            answers.append(
                InlineQueryResultPhoto(
                    photo_url=result["thumbnail"],
                    title=result["title"],
                    description=f"{result['rating']} | {result['quality']} | {result['year']}",
                    caption=f"{result['title']}\n{messages[get_user_lang(inline_query.from_user.id)]['details'].format(**result)}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(messages[get_user_lang(inline_query.from_user.id)]["details"], callback_data=f"details_{i}_{query}")]
                    ])
                )
            )
        await inline_query.answer(answers, cache_time=0)
    except Exception as e:
        logger.error(f"Inline search error: {e}")
        await inline_query.answer([], switch_pm_text=messages[get_user_lang(inline_query.from_user.id)]["error"].format(str(e)), switch_pm_parameter="error")

@app.on_callback_query(filters.regex(r"details_\d+_.+"))
async def show_details(client, callback):
    user_id = callback.from_user.id
    lang = get_user_lang(user_id)
    if banned_collection.find_one({"user_id": user_id}):
        await callback.answer(messages[lang]["banned"], show_alert=True)
        return
    index, query = map(str, callback.data.split("_")[1:])
    results = await asyncio.get_event_loop().run_in_executor(executor, search_content, query)
    content = results[int(index)]
    details = await asyncio.get_event_loop().run_in_executor(executor, get_details, content["link"])
    buttons = [[InlineKeyboardButton(q["quality"], callback_data=f"download_{index}_{query}_{i}")] for i, q in enumerate(details["qualities"])]
    if content["type"] == "series":
        buttons.append([InlineKeyboardButton(messages[lang]["episodes"], callback_data=f"episodes_{index}_{query}")])
    buttons.append([InlineKeyboardButton(messages[lang]["back"], callback_data=f"back_{query}")])
    await callback.message.edit_media(
        InputMediaPhoto(details["thumbnail"], caption=f"{details['title']}\n{messages[lang]['details'].format(**details)}"),
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_callback_query(filters.regex(r"download_\d+_.+_\d+"))
async def start_download(client, callback):
    user_id = callback.from_user.id
    lang = get_user_lang(user_id)
    if banned_collection.find_one({"user_id": user_id}):
        await callback.answer(messages[lang]["banned"], show_alert=True)
        return
    index, query, q_index = map(str, callback.data.split("_")[1:])
    results = await asyncio.get_event_loop().run_in_executor(executor, search_content, query)
    content = results[int(index)]
    details = await asyncio.get_event_loop().run_in_executor(executor, get_details, content["link"])
    quality = details["qualities"][int(q_index)]
    cost = 20 if content["type"] == "movie" else 10
    user = users_collection.find_one({"user_id": user_id})
    if not check_points(user_id, cost):
        await callback.message.reply(messages[lang]["no_points"].format("https://t.me/Zaky1million"),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(messages[lang]["premium"], url="https://t.me/Zaky1million")]]))
        return
    if user.get("premium", False):
        await process_download(user_id, {**content, **details}, quality, callback.message)
    else:
        if user_id in active_downloads:
            await callback.answer(messages[lang]["queue_busy"], show_alert=True)
            return
        await download_queue.put((user_id, {**content, **details}, quality, callback.message))
        await callback.answer(messages[lang]["queue_added"], show_alert=True)

@app.on_callback_query(filters.regex(r"cancel_\d+"))
async def cancel_download(client, callback):
    user_id = int(callback.data.split("_")[1])
    lang = get_user_lang(user_id)
    if user_id in active_downloads:
        del active_downloads[user_id]
        await callback.message.edit_text(messages[lang]["download_cancelled"])
    else:
        await callback.answer(messages[lang]["no_download"], show_alert=True)

@app.on_callback_query(filters.regex(r"episodes_\d+_.+"))
async def show_episodes(client, callback):
    user_id = callback.from_user.id
    lang = get_user_lang(user_id)
    index, query = map(str, callback.data.split("_")[1:])
    results = await asyncio.get_event_loop().run_in_executor(executor, search_content, query)
    content = results[int(index)]
    details = await asyncio.get_event_loop().run_in_executor(executor, get_details, content["link"])
    buttons = [[InlineKeyboardButton(ep["title"], callback_data=f"ep_details_{index}_{query}_{i}")] for i, ep in enumerate(details["episodes"])]
    buttons.append([InlineKeyboardButton(messages[lang]["back"], callback_data=f"details_{index}_{query}")])
    await callback.message.edit_media(
        InputMediaPhoto(details["thumbnail"], caption=f"{details['title']}\n{messages[lang]['episodes_list']}"),
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_callback_query(filters.regex(r"ep_details_\d+_.+_\d+"))
async def episode_details(client, callback):
    user_id = callback.from_user.id
    lang = get_user_lang(user_id)
    index, query, ep_index = map(str, callback.data.split("_")[1:])
    results = await asyncio.get_event_loop().run_in_executor(executor, search_content, query)
    content = results[int(index)]
    details = await asyncio.get_event_loop().run_in_executor(executor, get_details, content["link"])
    episode = details["episodes"][int(ep_index)]
    ep_details = await asyncio.get_event_loop().run_in_executor(executor, get_details, episode["link"])
    buttons = [[InlineKeyboardButton(q["quality"], callback_data=f"download_{index}_{query}_{i}_ep_{ep_index}")] for i, q in enumerate(ep_details["qualities"])]
    buttons.append([InlineKeyboardButton(messages[lang]["back"], callback_data=f"episodes_{index}_{query}")])
    await callback.message.edit_media(
        InputMediaPhoto(ep_details["thumbnail"], caption=f"{ep_details['title']}\n{messages[lang]['details'].format(**ep_details)}"),
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_callback_query(filters.regex(r"download_\d+_.+_\d+_ep_\d+"))
async def download_episode(client, callback):
    user_id = callback.from_user.id
    lang = get_user_lang(user_id)
    if banned_collection.find_one({"user_id": user_id}):
        await callback.answer(messages[lang]["banned"], show_alert=True)
        return
    index, query, q_index, ep_index = map(str, callback.data.split("_")[1:4] + [callback.data.split("_")[-1]])
    results = await asyncio.get_event_loop().run_in_executor(executor, search_content, query)
    content = results[int(index)]
    details = await asyncio.get_event_loop().run_in_executor(executor, get_details, content["link"])
    episode = details["episodes"][int(ep_index)]
    ep_details = await asyncio.get_event_loop().run_in_executor(executor, get_details, episode["link"])
    quality = ep_details["qualities"][int(q_index)]
    if not check_points(user_id, 10):
        await callback.message.reply(messages[lang]["no_points"].format("https://t.me/Zaky1million"),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(messages[lang]["premium"], url="https://t.me/Zaky1million")]]))
        return
    if users_collection.find_one({"user_id": user_id}).get("premium", False):
        await process_download(user_id, {**content, **ep_details}, quality, callback.message)
    else:
        if user_id in active_downloads:
            await callback.answer(messages[lang]["queue_busy"], show_alert=True)
            return
        await download_queue.put((user_id, {**content, **ep_details}, quality, callback.message))
        await callback.answer(messages[lang]["queue_added"], show_alert=True)

@app.on_callback_query(filters.regex(r"back_.+"))
async def back_to_results(client, callback):
    query = callback.data.split("_")[1]
    lang = get_user_lang(callback.from_user.id)
    results = await asyncio.get_event_loop().run_in_executor(executor, search_content, query)
    buttons = [[InlineKeyboardButton(r["title"], callback_data=f"details_{i}_{query}")] for i, r in enumerate(results[:10])]
    await callback.message.edit_text(messages[lang]["search_results"].format(query), reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("check_points"))
async def check_points_handler(client, callback):
    user_id = callback.from_user.id
    lang = get_user_lang(user_id)
    user = users_collection.find_one({"user_id": user_id})
    await callback.answer(messages[lang]["points_status"].format(user.get("daily_points", 60), user.get("referral_points", 0)), show_alert=True)

@app.on_callback_query(filters.regex("help"))
async def help_handler(client, callback):
    lang = get_user_lang(callback.from_user.id)
    await callback.message.edit_text(messages[lang]["help_text"], reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(messages[lang]["back"], callback_data="start_after_sub")]
    ]))

@app.on_callback_query(filters.regex("about"))
async def about_handler(client, callback):
    lang = get_user_lang(callback.from_user.id)
    await callback.message.edit_text(messages[lang]["about_text"], reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(messages[lang]["back"], callback_data="start_after_sub")]
    ]))

@app.on_callback_query(filters.regex("admin_panel"))
async def admin_panel(client, callback):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Access denied!", show_alert=True)
        return
    lang = get_user_lang(callback.from_user.id)
    await callback.message.edit_text(messages[lang]["admin_panel_text"], reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(messages[lang]["add_channel"], callback_data="add_channel")],
        [InlineKeyboardButton(messages[lang]["add_premium"], callback_data="add_premium")],
        [InlineKeyboardButton(messages[lang]["add_points"], callback_data="add_points")],
        [InlineKeyboardButton(messages[lang]["search_users"], callback_data="search_users")],
        [InlineKeyboardButton(messages[lang]["banned_users"], callback_data="banned_users")],
        [InlineKeyboardButton(messages[lang]["back"], callback_data="start_after_sub")]
    ]))

@app.on_callback_query(filters.regex("add_channel"))
async def add_channel(client, callback):
    if callback.from_user.id != ADMIN_ID:
        return
    lang = get_user_lang(callback.from_user.id)
    await callback.message.edit_text(messages[lang]["enter_channel"], reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(messages[lang]["back"], callback_data="admin_panel")]
    ]))
    await app.set_chat_state(callback.from_user.id, "add_channel")

@app.on_callback_query(filters.regex("add_premium"))
async def add_premium(client, callback):
    if callback.from_user.id != ADMIN_ID:
        return
    lang = get_user_lang(callback.from_user.id)
    await callback.message.edit_text(messages[lang]["enter_user_id"], reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(messages[lang]["back"], callback_data="admin_panel")]
    ]))
    await app.set_chat_state(callback.from_user.id, "add_premium")

@app.on_callback_query(filters.regex("add_points"))
async def add_points(client, callback):
    if callback.from_user.id != ADMIN_ID:
        return
    lang = get_user_lang(callback.from_user.id)
    await callback.message.edit_text(messages[lang]["enter_user_points"], reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(messages[lang]["back"], callback_data="admin_panel")]
    ]))
    await app.set_chat_state(callback.from_user.id, "add_points")

@app.on_callback_query(filters.regex("search_users"))
async def search_users(client, callback):
    if callback.from_user.id != ADMIN_ID:
        return
    lang = get_user_lang(callback.from_user.id)
    await callback.message.edit_text(messages[lang]["enter_search_query"], reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(messages[lang]["back"], callback_data="admin_panel")]
    ]))
    await app.set_chat_state(callback.from_user.id, "search_users")

@app.on_callback_query(filters.regex("banned_users"))
async def banned_users(client, callback):
    if callback.from_user.id != ADMIN_ID:
        return
    lang = get_user_lang(callback.from_user.id)
    banned = list(banned_collection.find())
    buttons = [[InlineKeyboardButton(f"{u['user_id']}", callback_data=f"unban_{u['user_id']}")] for u in banned[:10]]
    buttons.append([InlineKeyboardButton(messages[lang]["back"], callback_data="admin_panel")])
    await callback.message.edit_text(messages[lang]["banned_list"], reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"unban_\d+"))
async def unban_user(client, callback):
    if callback.from_user.id != ADMIN_ID:
        return
    user_id = int(callback.data.split("_")[1])
    lang = get_user_lang(callback.from_user.id)
    await callback.message.edit_text(messages[lang]["confirm_unban"], reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(messages[lang]["yes"], callback_data=f"confirm_unban_{user_id}"),
         InlineKeyboardButton(messages[lang]["no"], callback_data="banned_users")]
    ]))

@app.on_callback_query(filters.regex(r"confirm_unban_\d+"))
async def confirm_unban(client, callback):
    if callback.from_user.id != ADMIN_ID:
        return
    user_id = int(callback.data.split("_")[2])
    lang = get_user_lang(callback.from_user.id)
    banned_collection.delete_one({"user_id": user_id})
    await callback.message.edit_text(messages[lang]["unbanned"], reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(messages[lang]["back"], callback_data="banned_users")]
    ]))

@app.on_message(filters.private & filters.text)
async def handle_admin_commands(client, message):
    if message.from_user.id != ADMIN_ID:
        return
    state = await app.get_chat_state(message.from_user.id)
    lang = get_user_lang(message.from_user.id)
    if state == "add_channel":
        try:
            channel_id = int(message.text.split("/")[-1].replace("@", ""))
            channel = await app.get_chat(channel_id)
            channels_collection.insert_one({"id": channel_id, "name": channel.title, "link": message.text})
            await message.reply(messages[lang]["channel_added"], reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(messages[lang]["back"], callback_data="admin_panel")]
            ]))
        except Exception as e:
            await message.reply(messages[lang]["error"].format(e))
    elif state == "add_premium":
        user_id = message.text.replace("@", "")
        try:
            user_id = int(user_id) if user_id.isdigit() else (await app.get_users(user_id)).id
            if not users_collection.find_one({"user_id": user_id}):
                await message.reply(messages[lang]["user_not_found"])
                return
            users_collection.update_one({"user_id": user_id}, {"$set": {"premium": True, "premium_expiry": datetime.now() + timedelta(days=30)}})
            await message.reply(messages[lang]["premium_added"], reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(messages[lang]["back"], callback_data="admin_panel")]
            ]))
        except Exception as e:
            await message.reply(messages[lang]["error"].format(e))
    elif state == "add_points":
        try:
            user_id, points = message.text.split()
            user_id = int(user_id) if user_id.isdigit() else (await app.get_users(user_id.replace("@", ""))).id
            points = int(points)
            if not users_collection.find_one({"user_id": user_id}):
                await message.reply(messages[lang]["user_not_found"])
                return
            users_collection.update_one({"user_id": user_id}, {"$inc": {"daily_points": points}})
            await message.reply(messages[lang]["points_added"], reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(messages[lang]["back"], callback_data="admin_panel")]
            ]))
        except Exception as e:
            await message.reply(messages[lang]["error"].format(e))
    elif state == "search_users":
        query = message.text
        users = list(users_collection.find({"$or": [{"user_id": {"$regex": query}}, {"language": {"$regex": query}}]}))
        buttons = [[InlineKeyboardButton(str(u["user_id"]), callback_data=f"user_info_{u['user_id']}")] for u in users[:10]]
        buttons.append([InlineKeyboardButton(messages[lang]["back"], callback_data="admin_panel")])
        await message.reply(messages[lang]["search_results_users"], reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"user_info_\d+"))
async def user_info(client, callback):
    if callback.from_user.id != ADMIN_ID:
        return
    user_id = int(callback.data.split("_")[2])
    lang = get_user_lang(callback.from_user.id)
    user = users_collection.find_one({"user_id": user_id})
    if not user:
        await callback.message.edit_text(messages[lang]["user_not_found"])
        return
    info = messages[lang]["user_info"].format(
        user_id=user["user_id"], daily_points=user.get("daily_points", 60),
        referral_points=user.get("referral_points", 0), premium="Yes" if user.get("premium") else "No"
    )
    await callback.message.edit_text(info, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(messages[lang]["ban"], callback_data=f"ban_{user_id}")],
        [InlineKeyboardButton(messages[lang]["back"], callback_data="search_users")]
    ]))

@app.on_callback_query(filters.regex(r"ban_\d+"))
async def ban_user(client, callback):
    if callback.from_user.id != ADMIN_ID:
        return
    user_id = int(callback.data.split("_")[1])
    lang = get_user_lang(callback.from_user.id)
    banned_collection.insert_one({"user_id": user_id})
    await callback.message.edit_text(messages[lang]["user_banned"], reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(messages[lang]["back"], callback_data="search_users")]
    ]))

async def main():
    update_points()
    asyncio.create_task(download_worker())
    await app.start()
    logger.info("Bot started!")
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
