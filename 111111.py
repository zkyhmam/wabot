# -*- coding: utf-8 -*-

import asyncio
import logging
import time
import math
import os
import re
import uuid # For unique download IDs
import json
import shutil # For checking ffmpeg/ffprobe
import subprocess # For ffmpeg/ffprobe
from datetime import datetime
from urllib.parse import quote_plus, urlparse, parse_qs

# --- Pyrogram & Related ---
from pyrogram import Client, filters, enums
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery,
    InputMediaPhoto, InputMediaVideo
)
from pyrogram.errors import FloodWait, UserNotParticipant, MessageNotModified, MessageIdInvalid

# --- HTTP & Parsing ---
import httpx
import aiohttp # <<< ADDED for download
from bs4 import BeautifulSoup

# --- Image/Video Processing ---
from PIL import Image # <<< ADDED for thumbnail processing (optional validation)

# --- Configuration ---
API_ID = 25713843
API_HASH = "311352d08811e7f5136dfb27f71014c1"
BOT_TOKEN = "7058871390:AAFUZhBao_YhdAY8AAXKL-EBWNj_P0Cv-4I"

# --- Constants ---
AKWAM_BASE_URL = "https://ak.sv"
AKWAM_SEARCH_URL = AKWAM_BASE_URL + "/search?q={query}"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
REQUEST_DELAY = 1.5 # Seconds delay between requests to the site
PROGRESS_UPDATE_INTERVAL = 2 # Seconds interval for updating progress messages
MAX_RESULTS_PER_PAGE = 5 # <<< CHANGED: Number of search results per page (buttons only)
EPISODES_PER_ROW = 4       # <<< NEW: Number of episode number buttons per row
EPISODE_ROWS_PER_PAGE = 5  # <<< NEW: Number of rows for episode buttons
EPISODES_PER_PAGE = EPISODES_PER_ROW * EPISODE_ROWS_PER_PAGE # <<< CHANGED: Max episodes per page
DOWNLOAD_PATH = "/overlay_tmp" # Download directory
MAX_CONCURRENT_DOWNLOADS = 5 # Max concurrent downloads
CHUNK_SIZE = 1024 * 1024 * 4 # 4 MB download chunk size
PROCESS_MAX_TIMEOUT = 3600 * 2 # 2 hours for download timeout
TG_MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024 # 2GB basic limit
DEVELOPER_USERNAME = "zaky1million" # <<< NEW: Developer username

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()] # Output logs to console
)
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING) # Silence pyrogram debug logs
logging.getLogger("aiohttp").setLevel(logging.WARNING) # Silence aiohttp info logs

# --- Check for ffmpeg/ffprobe ---
FFMPEG_FOUND = bool(shutil.which("ffmpeg"))
FFPROBE_FOUND = bool(shutil.which("ffprobe"))
if not FFMPEG_FOUND or not FFPROBE_FOUND:
    logger.warning("---------------------------------------------------------------")
    logger.warning("WARNING: ffmpeg or ffprobe not found in system PATH!")
    logger.warning("Thumbnail generation and metadata extraction will be skipped.")
    logger.warning("Install ffmpeg (which usually includes ffprobe) for full functionality.")
    logger.warning("---------------------------------------------------------------")

# --- Pyrogram Client Initialization ---
logger.info("Initializing Bot...")
app = Client(
    "akwam_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# --- Global Variables/State ---
user_states = {}
# --- Concurrency Control ---
download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
active_downloads = set() # Store unique IDs of active download tasks
# --- Track progress message update times ---
last_update_time = {} # For upload progress
last_dl_update_time = {} # For download progress

# --- HTTP Client Wrapper (for scraping) ---
http_client = httpx.AsyncClient(
    headers={"User-Agent": DEFAULT_USER_AGENT},
    follow_redirects=True,
    timeout=30.0 # Increase timeout slightly
)

# --- Utility Functions (Copied/Adapted from url.txt and helpers) ---
def humanbytes(size):
    """Converts bytes to a human-readable format."""
    if not size: return "0 B"
    power = 1024 # Use 1024 for binary prefixes
    n = 0
    Dic_powerN = {0: 'B', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
    while size >= power and n < len(Dic_powerN) - 1: # Check boundary
        size /= power
        n += 1
    return str(round(size, 2)) + " " + Dic_powerN[n]

def TimeFormatter(milliseconds: int) -> str:
    """Formats milliseconds into a human-readable time string (h:m:s)."""
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    # Format as H:MM:SS or MM:SS
    if hours > 0:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"

# --- Utility to format size (kept original, slightly different but fine) ---
def format_size(size_bytes):
    if size_bytes == 0: return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    try: i = int(math.floor(math.log(size_bytes, 1024))) if size_bytes > 0 else 0
    except ValueError: i = 0
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2) if p > 0 else 0
    i = min(i, len(size_name) - 1) # Ensure index is within bounds
    return f"{s} {size_name[i]}"

async def make_request(url: str, method: str = "GET", data=None, allow_redirects=True):
    """Makes an HTTP request (using httpx) with delay and error handling."""
    try:
        logger.info(f"Scraping Request: {url} (Method: {method})")
        await asyncio.sleep(REQUEST_DELAY) # Crucial delay for scraping

        if method.upper() == "GET":
            response = await http_client.get(url, follow_redirects=allow_redirects)
        elif method.upper() == "POST":
             response = await http_client.post(url, data=data, follow_redirects=allow_redirects)
        else:
            logger.error(f"Unsupported HTTP method: {method}")
            return None

        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        logger.info(f"Scraping successful for {url} - Status: {response.status_code}")
        return response

    except httpx.TimeoutException:
        logger.error(f"Scraping timed out for URL: {url}")
    except httpx.RequestError as e:
        logger.error(f"Scraping HTTP Request failed for URL: {url} - Error: {e}")
    except httpx.HTTPStatusError as e:
        logger.error(f"Scraping HTTP Error for URL: {url} - Status: {e.response.status_code} - Response: {e.response.text[:200]}...")
    except Exception as e:
        logger.exception(f"An unexpected error occurred during scraping request to {url}: {e}")
    return None

# --- HTML Parsing Functions (Largely Unchanged Internally) ---
# --- Add Specific HTML Parsing Functions Here (parse_search_results, parse_movie_details, etc.) ---
# --- (These functions remain the same as in the previous version you provided) ---
# --- ... [omitted for brevity, assume they are here] ...

def parse_search_results(html_content: str) -> list:
    """Parses the Akwam search results page."""
    results = []
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        result_items = soup.select('div.widget[data-grid="6"] div.widget-body div.col-lg-auto')
        logger.info(f"Found {len(result_items)} potential result items on search page.")

        for item in result_items:
            entry_box = item.find('div', class_='entry-box')
            if not entry_box: continue

            title_tag = entry_box.find('h3', class_='entry-title')
            link_tag = entry_box.find('a', class_='box')
            img_tag = entry_box.find('img', class_='lazy')
            rating_tag = entry_box.find('span', class_='label rating')
            quality_tag = entry_box.find('span', class_='label quality')
            meta_tags = entry_box.select('div.font-size-16 span.badge')

            if title_tag and link_tag and link_tag.get('href'):
                title = title_tag.get_text(strip=True)
                link = link_tag['href']
                if not link.startswith(('http://', 'https://')):
                    link = AKWAM_BASE_URL + link if link.startswith('/') else AKWAM_BASE_URL + '/' + link

                image_url = img_tag.get('data-src') if img_tag and img_tag.get('data-src') else (img_tag.get('src') if img_tag else None)
                if image_url and image_url.startswith('//'): image_url = 'https:' + image_url

                rating = rating_tag.get_text(strip=True).replace(' ', '').replace('+', '') if rating_tag else "N/A"
                rating = re.sub(r'[^\d\.]', '', rating) if rating != "N/A" else "N/A"

                quality = quality_tag.get_text(strip=True) if quality_tag else "N/A"

                year = "N/A"; genres = []
                if meta_tags:
                    year_badge = meta_tags[0]
                    if year_badge and 'badge-secondary' in year_badge.get('class', []):
                        year_match = re.search(r'\b(19|20)\d{2}\b', year_badge.get_text(strip=True))
                        year = year_match.group(0) if year_match else "N/A"
                        genres = [tag.get_text(strip=True) for tag in meta_tags[1:]]
                    else: genres = [tag.get_text(strip=True) for tag in meta_tags]

                item_type = "series" if "/series/" in link else ("movie" if "/movie/" in link else "unknown")

                results.append({
                    'title': title, 'link': link, 'image_url': image_url,
                    'rating': rating, 'quality': quality, 'year': year,
                    'genres': genres, 'type': item_type,
                })
            else: logger.warning("Skipping search item: missing title, link, or href.")
        logger.info(f"Successfully parsed {len(results)} items from search results.")
        return results
    except Exception as e:
        logger.exception(f"Error parsing search results: {e}")
        return []

def parse_movie_details(html_content: str) -> dict | None:
    """Parses the Akwam movie details page."""
    details = {}
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        title_tag = soup.find('h1', class_='entry-title')
        details['title'] = title_tag.get_text(strip=True) if title_tag else "N/A"

        poster_div = soup.find('div', class_='col-lg-3 col-md-4')
        img_tag = poster_div.find('img') if poster_div else None
        details['image_url'] = img_tag['src'] if img_tag and img_tag.has_attr('src') else None
        if details['image_url'] and details['image_url'].startswith('//'): details['image_url'] = 'https:' + details['image_url']

        info_div = soup.find('div', class_='col-lg-7')
        if info_div:
            rating_div = info_div.find('div', string=re.compile(r'10\s*/\s*\d+(\.\d+)?'))
            if rating_div:
                 rating_match = re.search(r'(\d+(\.\d+)?)\s*/\s*10', rating_div.get_text(strip=True))
                 details['rating'] = rating_match.group(1) if rating_match else "N/A"
            else: # Fallback for IMDb rating structure
                 imdb_link = info_div.find('a', href=lambda href: href and 'imdb.com' in href)
                 if imdb_link:
                    parent_div = imdb_link.parent
                    rating_match = re.search(r'(\d+(\.\d+)?)\s*/\s*10', parent_div.get_text(" ", strip=True)) if parent_div else None
                    details['rating'] = rating_match.group(1) if rating_match else "N/A"
                 else: details['rating'] = "N/A"

            meta_lines = info_div.find_all('div', class_='font-size-16 text-white mt-2')
            for line in meta_lines:
                parts = line.get_text(strip=True).split(':', 1)
                if len(parts) == 2:
                    key, value = parts[0].strip(), parts[1].strip()
                    if "اللغة" in key: details['language'] = value
                    elif "جودة الفيلم" in key:
                        q_parts = value.split('-',1); details['format'] = q_parts[0].strip(); details['quality_res'] = q_parts[1].strip() if len(q_parts) > 1 else "N/A"
                    elif "انتاج" in key: details['country'] = value
                    elif "السنة" in key: details['year'] = value
                    elif "مدة الفيلم" in key: details['duration_text'] = value

            details['genres'] = [a.get_text(strip=True) for a in info_div.select('div.d-flex a.badge-light')]
            date_divs = info_div.find_all('div', class_='font-size-14 text-muted')
            if date_divs: details['added_date'] = date_divs[0].get_text(strip=True).replace('تـ الإضافة :', '').strip()
            if len(date_divs) > 1: details['updated_date'] = date_divs[1].get_text(strip=True).replace('تـ اخر تحديث :', '').strip()

        story_header = soup.find('span', class_='header-link text-white', string='قصة الفيلم') or soup.find('h2', string=re.compile('قصة الفيلم'))
        if story_header:
            story_container = story_header.find_parent('header') or story_header
            story_div = story_container.find_next_sibling('div', class_='widget-body') if story_container else None
            if story_div:
                story_p = story_div.find('p'); story_h2_div = story_div.find('h2')
                if story_p: details['description'] = story_p.get_text("\n", strip=True)
                elif story_h2_div and story_h2_div.find('div'): details['description'] = story_h2_div.find('div').get_text("\n", strip=True)
                else: details['description'] = story_div.get_text("\n", strip=True)
            else: details['description'] = "N/A"
        else: details['description'] = "N/A" # Fallback if no story section found

        trailer_tag = soup.find('a', {'data-fancybox': ''}, href=lambda href: href and 'youtube.com' in href)
        details['trailer_url'] = trailer_tag['href'] if trailer_tag else None
        details['gallery'] = [a['href'] for a in soup.find_all('a', {'data-fancybox': 'movie-gallery'}) if a.get('href')]

        details['download_options'] = {}
        quality_tabs = soup.select('ul.header-tabs.tabs li a')
        logger.info(f"Found {len(quality_tabs)} quality tabs.")
        for tab_link in quality_tabs:
            quality_name = tab_link.get_text(strip=True); tab_id = tab_link['href'].lstrip('#')
            content_div = soup.find('div', id=tab_id) or soup.find(lambda tag: tag.name == 'div' and tag.get('id') and tab_id in tag.get('id') and 'tab-content' in tag.get('class', []))
            if not content_div: logger.warning(f"No content div for tab ID: {tab_id}"); continue

            dl_tag = content_div.find('a', class_='link-download')
            watch_tag = content_div.find('a', class_='link-show')
            size_tag = content_div.find('span', class_='font-size-14 mr-auto')
            go_link = None
            if dl_tag and dl_tag.has_attr('href') and ('go.akwam.link' in dl_tag['href'] or 'go.ak.sv' in dl_tag['href']): go_link = dl_tag['href']
            elif watch_tag and watch_tag.has_attr('href') and ('go.akwam.link' in watch_tag['href'] or 'go.ak.sv' in watch_tag['href']): go_link = watch_tag['href']

            if go_link:
                try:
                    go_link_id = urlparse(go_link).path.split('/')[-1]
                    if go_link_id: details['download_options'][quality_name] = {'go_link': go_link, 'go_link_id': go_link_id, 'size': size_tag.get_text(strip=True) if size_tag else "N/A"}
                    else: logger.warning(f"No ID from go_link: {go_link}")
                except Exception: logger.warning(f"Error extracting ID from: {go_link}", exc_info=True)
            else: logger.warning(f"No go.ak* link for quality: {quality_name}")

        details['related'] = [] # Related items parsing omitted for brevity but assumes it works
        logger.info(f"Successfully parsed details for: {details.get('title', 'N/A')}")
        return details
    except Exception as e:
        logger.exception(f"Error parsing movie details: {e}")
        return None

def parse_series_details(html_content: str) -> dict | None:
    """Parses the Akwam series details page, including episodes."""
    details = parse_movie_details(html_content) # Reuse movie parser
    if not details: return None
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        details['episodes'] = []
        episodes_section = soup.find('div', id='series-episodes')
        if episodes_section:
            episode_items = episodes_section.select('div.widget-body > div > a[href*="/episode/"], div.col-12 a[href*="/episode/"]')
            logger.info(f"Found {len(episode_items)} potential episode links.")
            for link_tag in episode_items:
                parent_item = link_tag.find_parent(class_=re.compile(r'(bg-primary|col-12|row)')) or link_tag
                title_tag = parent_item.find('h2') or parent_item.find('h3')
                ep_title = link_tag.get_text(" ", strip=True) or (title_tag.get_text(" ", strip=True) if title_tag else "N/A")
                if ep_title == "N/A": logger.warning("Skipping episode: no title."); continue

                ep_link = link_tag['href']
                if not ep_link.startswith(('http://', 'https://')): ep_link = AKWAM_BASE_URL + ep_link if ep_link.startswith('/') else AKWAM_BASE_URL + '/' + ep_link

                img_tag = parent_item.find('img', class_='img-fluid')
                ep_image = img_tag['src'] if img_tag and img_tag.has_attr('src') else None
                if ep_image and ep_image.startswith('//'): ep_image = 'https:' + ep_image

                ep_num_match = re.search(r'(?:الحلقة|حلقة)\s*:?\s*(\d+)', ep_title, re.IGNORECASE)
                ep_num = int(ep_num_match.group(1)) if ep_num_match else None

                details['episodes'].append({
                    'title': ep_title.strip(), 'link': ep_link, 'image_url': ep_image,
                    'date': (parent_item.find('p', class_='entry-date').get_text(strip=True) if parent_item.find('p', class_='entry-date') else "N/A"),
                    'number': ep_num
                })
            logger.info(f"Parsed {len(details['episodes'])} episodes (newest first).")
        else: logger.warning("Episodes section not found.")
        return details
    except Exception as e:
        logger.exception(f"Error parsing series episodes: {e}")
        return details # Return partial details

def parse_episode_details(html_content: str) -> dict | None:
    """Parses the Akwam episode details page (mainly for download options)."""
    details = {}
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        title_tag = soup.find('h1', class_='entry-title')
        details['title'] = title_tag.get_text(strip=True) if title_tag else "N/A"
        details['download_options'] = {}
        quality_tabs = soup.select('ul.header-tabs.tabs li a')
        logger.info(f"Found {len(quality_tabs)} quality tabs for episode.")
        for tab_link in quality_tabs:
            quality_name = tab_link.get_text(strip=True); tab_id = tab_link['href'].lstrip('#')
            content_div = soup.find('div', id=tab_id) or soup.find(lambda tag: tag.name == 'div' and tag.get('id') and tab_id in tag.get('id') and 'tab-content' in tag.get('class', []))
            if not content_div: logger.warning(f"No content div for tab ID: {tab_id}"); continue

            dl_tag = content_div.find('a', class_='link-download')
            watch_tag = content_div.find('a', class_='link-show')
            size_tag = content_div.find('span', class_='font-size-14 mr-auto')
            go_link = None
            if dl_tag and dl_tag.has_attr('href') and ('go.akwam.link' in dl_tag['href'] or 'go.ak.sv' in dl_tag['href']): go_link = dl_tag['href']
            elif watch_tag and watch_tag.has_attr('href') and ('go.akwam.link' in watch_tag['href'] or 'go.ak.sv' in watch_tag['href']): go_link = watch_tag['href']

            if go_link:
                try:
                    go_link_id = urlparse(go_link).path.split('/')[-1]
                    if go_link_id: details['download_options'][quality_name] = {'go_link': go_link, 'go_link_id': go_link_id, 'size': size_tag.get_text(strip=True) if size_tag else "N/A"}
                    else: logger.warning(f"No ID from go_link: {go_link}")
                except Exception: logger.warning(f"Error extracting ID from: {go_link}", exc_info=True)
            else: logger.warning(f"No go.ak* link for quality: {quality_name}")
        logger.info(f"Parsed download options for episode: {details.get('title', 'N/A')}")
        return details
    except Exception as e:
        logger.exception(f"Error parsing episode details: {e}")
        return None

def parse_go_link_page(html_content: str) -> str | None:
    """Parses the go.ak.sv or go.akwam.link interstitial page."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        # Prioritize button with specific class first
        dl_tag = soup.find('a', class_='download-link', href=lambda href: href and '/download/' in href)
        if not dl_tag: # Fallback selectors
            dl_tag = soup.select_one('div.download-timer a[href*="/download/"]') or soup.select_one('a.btn[href*="/download/"]')

        if dl_tag and dl_tag.has_attr('href'):
            ak_dl_link = dl_tag['href']
            logger.info(f"Found ak.sv download link: {ak_dl_link}")
            # Normalize URL
            if ak_dl_link.startswith('//'): ak_dl_link = 'https:' + ak_dl_link
            elif not ak_dl_link.startswith(('http://', 'https://')):
                 base_netloc = urlparse(AKWAM_BASE_URL).netloc # Use main base URL
                 ak_dl_link = f"https://{base_netloc}{ak_dl_link}" if ak_dl_link.startswith('/') else f"https://{base_netloc}/{ak_dl_link}"
            return ak_dl_link
        else:
            logger.error("Could not find the download link tag on the go.ak.* page.")
            return None
    except Exception as e:
        logger.exception(f"Error parsing go.ak.* page: {e}")
        return None

def parse_download_page(html_content: str) -> str | None:
    """Parses the ak.sv/download page to find the direct download link."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        direct_link_tag = soup.select_one('a.link.btn[href]') # Primary selector
        direct_link = None

        if direct_link_tag:
            potential_link = direct_link_tag['href']
            # Basic validation
            if 'http' in potential_link and ('down.google' in potential_link or 'downet' in potential_link or any(potential_link.lower().endswith(ext) for ext in ['.mp4', '.mkv', '.avi', '.zip', '.rar', '.wmv', '.mov'])):
                 direct_link = potential_link
                 logger.info(f"Found potential direct download link via primary selector: {direct_link}")
                 return direct_link
            else: logger.warning(f"Primary selector link invalid: {potential_link}")
        else: logger.info("Primary selector 'a.link.btn[href]' not found.")

        # Check for JS redirect (unchanged logic)
        scripts = soup.find_all('script')
        for script in scripts:
            content = script.string
            if content and 'setTimeout' in content and ('location.href' in content or 'downet.net' in content or 'down.google' in content):
                logger.info("Found JavaScript timer potentially setting the download link.")
                link_match = re.search(r"location\.href\s*=\s*['\"]([^'\"]+)['\"]", content) or \
                             re.search(r"href',\s*'([^']+)'", content) or \
                             re.search(r"\.href\s*=\s*['\"]([^'\"]+)['\"]", content)
                if link_match:
                    js_link = link_match.group(1)
                    if 'http' in js_link and ('down.google' in js_link or 'downet.net' in js_link or any(js_link.lower().endswith(ext) for ext in ['.mp4', '.mkv', '.avi', '.mov'])):
                        logger.info(f"Extracted potential link from JS: {js_link}. Signaling JS delay.")
                        return "js_delay_detected"
                    else: logger.warning(f"Extracted JS link invalid: {js_link}")
                else: logger.warning("Could not extract link from JS timer script.")
                return "js_delay_detected" # Signal delay even if extraction failed

        logger.error("Could not find direct download link or JS delay script.")
        return None
    except Exception as e:
        logger.exception(f"Error parsing ak.sv/download page: {e}")
        return None

# --- Markup Utilities ---

def create_navigation_buttons(back_callback_data=None, home_callback_data="go_home"):
    """Creates standard back and home navigation buttons."""
    row = []
    if back_callback_data:
        row.append(InlineKeyboardButton("🔙", callback_data=back_callback_data))
    if home_callback_data:
        row.append(InlineKeyboardButton("🏡", callback_data=home_callback_data))
    return row if row else None

def create_pagination_buttons(current_page: int, total_pages: int, callback_prefix: str) -> list:
    """Creates previous/next pagination buttons."""
    buttons = []
    if total_pages <= 1: return buttons # No pagination needed for single page
    row = []
    nav_prefix = f"{callback_prefix}_{current_page}" # Include current page for context
    if current_page > 1:
        row.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"{callback_prefix}_{current_page - 1}"))
    # Display page number indicator
    row.append(InlineKeyboardButton(f"📄 {current_page}/{total_pages} 📄", callback_data=f"pageinfo_{current_page}_{total_pages}"))
    if current_page < total_pages:
        row.append(InlineKeyboardButton("التالي ➡️", callback_data=f"{callback_prefix}_{current_page + 1}"))
    if row: buttons.append(row)
    return buttons

# --- UPDATED: Search Results Formatting ---
def format_search_results_page(results: list, page: int, total_pages: int, query: str) -> tuple[str, InlineKeyboardMarkup]:
    """Formats search results for display (Buttons Only)."""
    if not results:
        return "**لم يتم العثور على نتائج.**", InlineKeyboardMarkup([create_navigation_buttons(home_callback_data="go_home")])

    # Only show title and pagination info in the message
    text = f"**نتائج البحث عن \"{query}\"** (صفحة {page}/{total_pages})"
    buttons = []

    # Add info button
    buttons.append([InlineKeyboardButton("🤔 اختر من نتائج البحث أدناه ⬇️", callback_data="alert_choose_search")])

    start_index = (page - 1) * MAX_RESULTS_PER_PAGE
    end_index = start_index + MAX_RESULTS_PER_PAGE
    current_results = results[start_index:end_index]

    # Create buttons for each result
    for i, result in enumerate(current_results):
        full_result_index = start_index + i
        item_type_icon = "🎬" if result['type'] == 'movie' else ("📺" if result['type'] == 'series' else "❓")
        year_str = f"({result['year']})" if result['year'] != "N/A" else ""
        # Try to fit title, year, and icon. Truncation might still happen. Max button text length is ~64 bytes.
        button_text = f"{item_type_icon} {result['title']} {year_str}"
        # Truncate intelligently if needed (though Telegram might do it anyway)
        max_len = 60
        if len(button_text.encode('utf-8')) > max_len:
            # Simple truncation for now
            button_text = button_text[:max_len-3] + "..."

        callback_safe_query = quote_plus(query)[:30] # Query context needed if we want 'back'
        buttons.append([InlineKeyboardButton(
             button_text,
             # Include current search page in view callback for back navigation
             callback_data=f"view_{full_result_index}_{page}_{callback_safe_query}"
        )])

    # Add pagination
    pagination_rows = create_pagination_buttons(page, total_pages, f"searchpage_{callback_safe_query}")
    buttons.extend(pagination_rows)

    # Add Home navigation button
    nav_row = create_navigation_buttons(home_callback_data="go_home")
    if nav_row: buttons.append(nav_row)

    return text, InlineKeyboardMarkup(buttons)

# --- UPDATED: Movie Details Formatting ---
def format_movie_details(details: dict, search_page: int) -> tuple[str, InlineKeyboardMarkup, str | None]:
    """Formats movie details for display."""
    text = f"🎬 **{details.get('title', 'N/A')}**\n\n"
    if details.get('year'): text += f"🗓️ السنة: `{details['year']}`\n"
    if details.get('rating', 'N/A') != 'N/A': text += f"⭐ التقييم: `{details['rating']}/10`\n"
    if details.get('duration_text'): text += f"⏱️ المدة: `{details['duration_text']}`\n"
    # Optional: Add genres, country, etc. if needed
    # text += f"🏴 الدولة: {details.get('country', 'N/A')}\n"
    if details.get('genres'): text += f"🎭 النوع: {', '.join(details['genres'])}\n"

    desc = details.get('description', '')
    if desc and desc != "N/A":
        text += f"\n**📝 القصة:**\n{desc[:500]}{'...' if len(desc) > 500 else ''}\n"

    buttons = []
    # Download Options
    if details.get('download_options'):
        text += "\n**💾 خيارات التحميل:**"
        quality_buttons = []
        for quality, data in details['download_options'].items():
            size_str = f" ({data['size']})" if data.get('size', 'N/A') != "N/A" else ""
            # Append go_link_id to identify which quality was chosen
            quality_callback = f"quality_{data['go_link_id']}"
            quality_buttons.append(
                InlineKeyboardButton(f"{quality}{size_str}", callback_data=quality_callback)
            )
        # Arrange buttons in rows of 2
        for i in range(0, len(quality_buttons), 2): buttons.append(quality_buttons[i:i+2])
    else:
        buttons.append([InlineKeyboardButton("⚠️ لا توجد روابط تحميل", callback_data="no_links")])

    # Trailer Button
    if details.get('trailer_url'):
        buttons.append([InlineKeyboardButton("🍿 مشاهدة التريلر", url=details['trailer_url'])])

    # Navigation Buttons - Pass search page for back context
    nav_row = create_navigation_buttons(back_callback_data=f"back_srch_{search_page}", home_callback_data="go_home")
    if nav_row: buttons.append(nav_row)

    image_url = details.get('image_url')
    return text, InlineKeyboardMarkup(buttons), image_url

# --- UPDATED: Series Details Formatting ---
def format_series_details(details: dict, user_id: int, episode_page: int = 1, search_page: int = 1) -> tuple[str, InlineKeyboardMarkup, str | None]:
    """Formats series details, focusing on episode list with pagination."""
    text = f"📺 **{details.get('title', 'N/A')}**\n\n"
    if details.get('year'): text += f"🗓️ السنة: `{details['year']}`\n"
    if details.get('rating', 'N/A') != 'N/A': text += f"⭐ التقييم: `{details['rating']}/10`\n"
    if details.get('genres'): text += f"🎭 النوع: {', '.join(details['genres'])}\n"

    desc = details.get('description', '')
    if desc and desc != "N/A":
        text += f"\n**📝 القصة:**\n{desc[:250]}{'...' if len(desc) > 250 else ''}\n"

    buttons = []
    episodes = details.get('episodes', [])
    total_episodes = len(episodes)

    if total_episodes > 0:
        total_episode_pages = math.ceil(total_episodes / EPISODES_PER_PAGE)
        episode_page = max(1, min(episode_page, total_episode_pages))

        start_index = (episode_page - 1) * EPISODES_PER_PAGE
        end_index = start_index + EPISODES_PER_PAGE
        current_episodes = episodes[start_index:end_index]

        text += f"\n**🎬 الحلقات ({total_episodes}) - صفحة {episode_page}/{total_episode_pages}:**\n"

        # Add info button
        buttons.append([InlineKeyboardButton("🤔 اختر رقم الحلقة من الأزرار أدناه ⬇️", callback_data="alert_choose_episode")])

        # Create episode number buttons
        episode_rows = []
        current_row = []
        for i, episode in enumerate(current_episodes):
            global_index = start_index + i
            # Display episode number. Use global index as fallback (newest first index).
            ep_num_str = str(episode['number']) if episode.get('number') is not None else str(total_episodes - global_index)

            # Store current episode page and search page for back navigation from episode details
            episode_context_id = user_states.get(user_id, {}).get('current_view_context', 'ctx_error')
            callback_data = f"episode_{global_index}_{episode_page}_{search_page}" # Pass context

            current_row.append(InlineKeyboardButton(ep_num_str, callback_data=callback_data))
            if len(current_row) == EPISODES_PER_ROW:
                episode_rows.append(current_row)
                current_row = []
        if current_row: # Add remaining buttons if not a full row
            episode_rows.append(current_row)

        buttons.extend(episode_rows) # Add all episode button rows

        # Add pagination for episodes
        # Pass search_page context in pagination callback prefix if needed later
        pagination_rows = create_pagination_buttons(episode_page, total_episode_pages, f"epspage_{episode_context_id}_{search_page}")
        buttons.extend(pagination_rows)
    else:
        text += "\n**لا توجد حلقات متاحة لهذا المسلسل بعد.**"

    # Trailer Button
    if details.get('trailer_url'):
        buttons.append([InlineKeyboardButton("🍿 مشاهدة التريلر", url=details['trailer_url'])])

    # Navigation Buttons - Pass search page context
    nav_row = create_navigation_buttons(back_callback_data=f"back_srch_{search_page}", home_callback_data="go_home")
    if nav_row: buttons.append(nav_row)

    image_url = details.get('image_url')
    return text, InlineKeyboardMarkup(buttons), image_url

# --- UPDATED: Episode Details Formatting ---
def format_episode_details(details: dict, user_id: int, episode_list_page: int, search_page: int) -> tuple[str, InlineKeyboardMarkup, str | None]:
    """Formats episode details, focusing on quality selection."""
    # Try to get series title from stored state for better context
    series_title = user_states.get(user_id, {}).get('current_details', {}).get('title', '')
    episode_title = details.get('title', 'الحلقة') # Fallback title
    full_title = f"{series_title} - {episode_title}" if series_title else episode_title

    text = f"🎬 **{full_title}**\n\n"
    text += "**💾 اختر الجودة المطلوبة للتحميل:**"

    buttons = []
    if details.get('download_options'):
        quality_buttons = []
        for quality, data in details['download_options'].items():
            size_str = f" ({data['size']})" if data.get('size', 'N/A') != "N/A" else ""
            # Include context in quality callback for potential future use
            quality_callback = f"quality_{data['go_link_id']}_{episode_list_page}_{search_page}"
            quality_buttons.append(
                InlineKeyboardButton(f"{quality}{size_str}", callback_data=quality_callback)
            )
        for i in range(0, len(quality_buttons), 2): buttons.append(quality_buttons[i:i+2])
    else:
        buttons.append([InlineKeyboardButton("⚠️ لا توجد روابط تحميل", callback_data="no_links")])

    # Navigation Buttons
    # Generate callback data to go back to the correct episode list page
    stored_context_id = user_states.get(user_id, {}).get('current_view_context', 'ctx_error')
    back_to_eps_callback = f"back_eps_{stored_context_id}_{episode_list_page}_{search_page}"
    nav_row = create_navigation_buttons(back_callback_data=back_to_eps_callback, home_callback_data="go_home")
    if nav_row: buttons.append(nav_row)

    # Image URL is usually not relevant on this page
    return text, InlineKeyboardMarkup(buttons), None


# --- Progress Callback (Pyrogram Upload - English) ---
async def progress_callback(current, total, message: Message, task_name: str, start_time: float):
    """Updates the message with UPLOAD progress information."""
    global last_update_time
    now = time.time()
    message_identifier = message.id

    if message_identifier not in last_update_time: last_update_time[message_identifier] = 0
    if now - last_update_time.get(message_identifier, 0) < PROGRESS_UPDATE_INTERVAL: return
    last_update_time[message_identifier] = now

    try:
        percentage = current * 100 / total if total > 0 else 0
        speed = current / (now - start_time) if (now - start_time) > 0 else 0
        elapsed_time = now - start_time
        eta = (total - current) / speed if speed > 0 else 0

        bar_length = 10
        filled_length = int(bar_length * current // total) if total > 0 else 0
        bar = '█' * filled_length + ' ' * (bar_length - filled_length)

        progress_text = (
            f"**⬆️ {task_name}**\n" # Changed Icon
            f"`[{bar}] {percentage:.1f}%`\n"
            f"**Progress:** {humanbytes(current)} / {humanbytes(total)}\n"
            f"**Speed:** {humanbytes(speed)}/s\n"
            f"**ETA:** {TimeFormatter(eta * 1000)}\n"
        )

        await message.edit_text(progress_text)

    except MessageNotModified: pass
    except FloodWait as e:
        logger.warning(f"Flood wait of {e.value} seconds during upload progress update.")
        await asyncio.sleep(e.value + 1) # Add buffer
    except MessageIdInvalid:
        logger.warning(f"Upload progress update failed: Message {message_identifier} not found.")
        if message_identifier in last_update_time: del last_update_time[message_identifier]
    except Exception as e:
        logger.exception(f"Error in upload progress callback for message {message_identifier}: {e}")


# --- UPDATED: Download Coroutine using aiohttp (Disable SSL Verify) ---
async def download_file_aiohttp(url: str, file_path: str, progress_msg: Message) -> bool:
    """Downloads a file using aiohttp with detailed progress updates."""
    global last_dl_update_time
    downloaded_size = 0
    display_message = ""
    start_time = time.time()
    session = None
    response = None

    message_identifier = progress_msg.id
    last_dl_update_time[message_identifier] = start_time
    item_title_guess = progress_msg.text.splitlines()[0].split(':')[-1].strip() if progress_msg.text else "File"


    logger.info(f"Starting aiohttp download: {url} -> {file_path}")
    # --- SSL Verification Disabled ---
    ssl_context = False # Disables SSL verification
    logger.warning("---------------------------------------------------------------")
    logger.warning("WARNING: SSL certificate verification is DISABLED for downloads!")
    logger.warning("This is insecure and potentially exposes downloads to MITM attacks.")
    logger.warning("---------------------------------------------------------------")

    try:
        connector = aiohttp.TCPConnector(ssl=ssl_context, limit_per_host=10) # Disable SSL check here
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=PROCESS_MAX_TIMEOUT), headers={"User-Agent": DEFAULT_USER_AGENT}, allow_redirects=True) as response:
                if response.status >= 400:
                    logger.error(f"aiohttp download failed: HTTP {response.status} for {url}")
                    err_text = await response.text(encoding='utf-8', errors='ignore')
                    await progress_msg.edit_text(f"❌ **فشل التحميل (خطأ HTTP {response.status}) لـ {item_title_guess}**.\n`{err_text[:200]}`")
                    return False

                total_size = int(response.headers.get("Content-Length", 0))
                content_type = response.headers.get("Content-Type", "")
                logger.info(f"Download details: Size={humanbytes(total_size)}, Type={content_type}")

                if "text/html" in content_type and total_size < 1024 * 10: # Slightly larger check for error pages
                     html_content = await response.text(encoding='utf-8', errors='ignore')
                     logger.error(f"Download failed: Received HTML page. Content: {html_content[:500]}")
                     await progress_msg.edit_text(f"❌ **فشل التحميل: تم استقبال صفحة خطأ بدلاً من الملف لـ {item_title_guess}**.")
                     return False

                os.makedirs(os.path.dirname(file_path), exist_ok=True)

                with open(file_path, "wb") as f_handle:
                    async for chunk in response.content.iter_chunked(CHUNK_SIZE): # Use iter_chunked
                        if not chunk: break
                        f_handle.write(chunk)
                        downloaded_size += len(chunk)
                        now = time.time()

                        if now - last_dl_update_time.get(message_identifier, 0) >= PROGRESS_UPDATE_INTERVAL or (total_size > 0 and downloaded_size == total_size):
                             if total_size > 0:
                                 percentage = downloaded_size * 100 / total_size
                                 speed = downloaded_size / (now - start_time) if (now - start_time) > 0 else 0
                                 elapsed_time = now - start_time
                                 eta = (total_size - downloaded_size) / speed if speed > 0 else 0
                                 bar_length = 10
                                 filled_length = int(bar_length * downloaded_size // total_size)
                                 bar = '█' * filled_length + ' ' * (bar_length - filled_length)

                                 # Progress message in English
                                 current_message = (
                                    f"**📥 Downloading: {item_title_guess}**\n"
                                    f"`[{bar}] {percentage:.1f}%`\n"
                                    f"**Progress:** {humanbytes(downloaded_size)} / {humanbytes(total_size)}\n"
                                    f"**Speed:** {humanbytes(speed)}/s\n"
                                    f"**ETA:** {TimeFormatter(eta * 1000)}\n"
                                 )

                                 if current_message != display_message:
                                     try:
                                         await progress_msg.edit_text(current_message)
                                         display_message = current_message
                                         last_dl_update_time[message_identifier] = now
                                     except MessageNotModified: pass
                                     except FloodWait as e: await asyncio.sleep(e.value + 1)
                                     except MessageIdInvalid: logger.warning(f"DL progress fail: Msg {message_identifier} gone."); return False
                                     except Exception as e_edit: logger.exception(f"Error updating DL progress: {e_edit}")
                             else: # Unknown size
                                 speed = downloaded_size / (now - start_time) if (now - start_time) > 0 else 0
                                 current_message = (
                                    f"**📥 Downloading: {item_title_guess}**\n"
                                    f"**Progress:** {humanbytes(downloaded_size)}\n"
                                    f"**Speed:** {humanbytes(speed)}/s\n"
                                    f"_(Total size unknown)_"
                                 )
                                 if current_message != display_message:
                                      try:
                                         await progress_msg.edit_text(current_message)
                                         display_message = current_message
                                         last_dl_update_time[message_identifier] = now
                                      except Exception: pass # Ignore errors for unknown size

                logger.info(f"aiohttp download complete: {file_path} ({humanbytes(downloaded_size)})")
                if total_size > 0 and downloaded_size < total_size * 0.99: # Allow small diffs
                     logger.warning(f"Downloaded size mismatch! Expected {total_size}, Got {downloaded_size}")
                     # await progress_msg.reply_text(f"⚠️ **تحذير: حجم الملف المحمل لـ {item_title_guess} غير مطابق للحجم المتوقع. قد يكون الملف غير مكتمل.**")


                # Final 100% update
                if total_size > 0:
                    bar = '█' * 10
                    final_message = (
                        f"**📥 Download Complete: {item_title_guess}**\n"
                        f"`[{bar}] 100.0%`\n"
                        f"{humanbytes(total_size)} / {humanbytes(total_size)}\n"
                        f"**Time:** {TimeFormatter((time.time() - start_time) * 1000)}\n"
                        f"✅ Done."
                    )
                    try: await progress_msg.edit_text(final_message)
                    except Exception: pass

                return True

    except asyncio.TimeoutError:
        logger.error(f"aiohttp download timed out after {PROCESS_MAX_TIMEOUT}s for {url}")
        try: await progress_msg.edit_text(f"❌ **فشل التحميل: انتهت مهلة الاتصال لـ {item_title_guess}**.")
        except Exception: pass
        return False
    except aiohttp.ClientError as e:
        # Log the specific error, especially SSL errors
        logger.error(f"aiohttp ClientError during download of {url}: {e}")
        error_msg = str(e)
        # Provide more specific feedback for common errors if SSL is disabled
        if isinstance(e, aiohttp.ClientConnectorError) and "Cannot connect to host" in error_msg:
             display_error = f"لا يمكن الاتصال بالخادم: `{urlparse(url).netloc}`"
        elif isinstance(e, aiohttp.ClientSSLError):
             display_error = f"خطأ SSL (بالرغم من تعطيل التحقق): {error_msg}"
        else:
             display_error = f"خطأ في الاتصال بالشبكة: {error_msg}"

        try: await progress_msg.edit_text(f"❌ **فشل التحميل لـ {item_title_guess}**\n{display_error}")
        except Exception: pass
        return False
    except OSError as e:
         logger.error(f"File system error during download: {e}")
         try: await progress_msg.edit_text(f"❌ **خطأ في نظام الملفات لـ {item_title_guess}**: {e.strerror}. تحقق من المساحة/الأذونات في `{DOWNLOAD_PATH}`.")
         except: pass
         return False
    except Exception as e:
        logger.exception(f"Unexpected error during aiohttp download of {url}: {e}")
        try: await progress_msg.edit_text(f"❌ **حدث خطأ غير متوقع أثناء تحميل {item_title_guess}**.")
        except Exception: pass
        return False
    finally:
        # No need to manually release response with async with session.get
        # Session is closed by async with aiohttp.ClientSession
        if message_identifier in last_dl_update_time:
            try: del last_dl_update_time[message_identifier]
            except KeyError: pass


# --- Get Video Metadata using ffprobe ---
async def get_video_metadata(file_path: str) -> dict | None:
    """Extracts video duration, width, and height using ffprobe."""
    if not FFPROBE_FOUND: logger.warning("ffprobe not found, skipping metadata."); return None
    try:
        command = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration",
            "-of", "default=noprint_wrappers=1:nokey=1", file_path
        ]
        logger.info(f"Running ffprobe: {' '.join(command)}")
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(f"ffprobe failed ({process.returncode}). Stderr: {stderr.decode().strip()}")
            # Try JSON fallback
            command = [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height,duration", "-print_format", "json", file_path
            ]
            logger.info(f"Retrying ffprobe with JSON...")
            process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                 try:
                     data = json.loads(stdout.decode())
                     stream = data.get("streams", [{}])[0]
                     width = int(stream.get("width", 0)); height = int(stream.get("height", 0))
                     duration = math.ceil(float(stream.get("duration", "0")))
                     if width > 0 and height > 0 and duration > 0:
                         logger.info(f"Metadata (JSON): W={width}, H={height}, D={duration}s")
                         return {"width": width, "height": height, "duration": duration}
                 except Exception as json_e: logger.error(f"Failed to parse ffprobe JSON: {json_e}")
            return None # Failed both methods

        output = stdout.decode().strip().split('\n')
        if len(output) >= 3: # Expect at least width, height, duration
             try:
                 width = int(output[0])
                 height = int(output[1])
                 duration_str = output[2]
                 duration = math.ceil(float(duration_str)) # Duration is usually in seconds
                 if width <=0 or height <= 0 or duration <= 0: raise ValueError("Invalid dimensions/duration")
                 logger.info(f"Metadata extracted: Width={width}, Height={height}, Duration={duration}s")
                 return {"width": width, "height": height, "duration": duration}
             except (ValueError, IndexError) as parse_err:
                 logger.error(f"ffprobe output parsing failed: {parse_err}. Output: {output}")
                 return None
        else:
            logger.error(f"ffprobe output unexpected format. Output: {output}")
            return None
    except FileNotFoundError: logger.error("ffprobe not found."); return None
    except Exception as e: logger.exception(f"Error running ffprobe: {e}"); return None

# --- Generate Thumbnail using ffmpeg ---
async def generate_thumbnail(file_path: str, thumb_path: str, duration: int | None) -> str | None:
    """Generates a thumbnail from the middle of the video using ffmpeg."""
    if not FFMPEG_FOUND: logger.warning("ffmpeg not found, skipping thumbnail."); return None
    if duration is None or duration <= 1: logger.warning("Invalid duration, cannot generate thumbnail."); return None

    midpoint = duration // 2
    os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
    try:
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", # Less verbose
            "-ss", str(midpoint), "-i", file_path, "-y",
            "-vframes", "1", "-vf", "scale=320:-1", # Scale width to 320px
            thumb_path
        ]
        logger.info(f"Running ffmpeg for thumbnail...") # Command logged before if needed
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(f"ffmpeg failed ({process.returncode}). Stderr: {stderr.decode().strip()}")
            return None
        if not os.path.exists(thumb_path) or os.path.getsize(thumb_path) == 0:
             logger.error(f"ffmpeg ran but thumbnail '{thumb_path}' missing or empty.")
             return None

        # Optional Pillow validation (can be slow)
        # try:
        #     Image.open(thumb_path).verify()
        # except Exception as pil_e:
        #      logger.warning(f"Generated thumb '{thumb_path}' might be corrupted (Pillow: {pil_e}).")
        #      # Return path anyway? Or None? Let's return it.

        logger.info(f"Thumbnail generated successfully: {thumb_path}")
        return thumb_path

    except FileNotFoundError: logger.error("ffmpeg not found."); return None
    except Exception as e: logger.exception(f"Error running ffmpeg for thumbnail: {e}"); return None


# --- Bot Handlers ---

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    """Handles the /start command."""
    user = message.from_user
    logger.info(f"Received /start command from user {user.id} ({user.username})")
    welcome_text = (
        f"👋 **أهلاً بك {user.mention} في بوت أكوام!**\n\n"
        f"يمكنك استخدامي للبحث عن الأفلام والمسلسلات من موقع `{AKWAM_BASE_URL}` وتحميلها.\n\n"
        f"ℹ️ **كيفية الاستخدام:**\n"
        f"فقط أرسل اسم الفيلم أو المسلسل الذي تبحث عنه.\n\n"
        f"📥 يتم حفظ التحميلات مؤقتًا في `{DOWNLOAD_PATH}`.\n"
        f"⚙️ الحد الأقصى للتحميلات المتزامنة: `{MAX_CONCURRENT_DOWNLOADS}`.\n\n"
        f"⚠️ **ملاحظة:** إنشاء الصور المصغرة للفيديو يتطلب تثبيت `ffmpeg` على الخادم.\n\n"
        f"🧑‍💻 **للتواصل مع المطور:** @{DEVELOPER_USERNAME}"
    )
    # Simple keyboard for start
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⭐ تواصل مع المطور ⭐", url=f"https://t.me/{DEVELOPER_USERNAME}")],
        [InlineKeyboardButton("❓ مساعدة", callback_data="help")]
    ])
    await message.reply_text(welcome_text, reply_markup=keyboard, disable_web_page_preview=True)
    # Reset user state
    if user.id in user_states: del user_states[user.id]
    user_states[user.id] = {"navigation_history": ["home"]} # Start history

@app.on_message(filters.command("help") & filters.private)
async def help_handler(client: Client, message: Message):
    """Handles the /help command."""
    help_text = (
        f"❓ **المساعدة**\n\n"
        f"1.  **للبحث:** أرسل اسم الفيلم أو المسلسل.\n"
        f"2.  ستظهر لك النتائج كأزرار.\n"
        f"3.  اضغط على زر النتيجة لعرض التفاصيل وخيارات التحميل.\n"
        f"4.  اختر الجودة المطلوبة لبدء التحميل.\n\n"
        f"🔄 استخدم الأزرار ⬅️ و ➡️ للتنقل بين الصفحات.\n"
        f"🔙 للرجوع خطوة للوراء.\n"
        f"🏡 للعودة إلى البداية.\n\n"
        f"🧑‍💻 **للتواصل مع المطور:** @{DEVELOPER_USERNAME}"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⭐ تواصل مع المطور ⭐", url=f"https://t.me/{DEVELOPER_USERNAME}")],
        [InlineKeyboardButton("🏡 العودة للرئيسية", callback_data="go_home")]
    ])
    await message.reply_text(help_text, reply_markup=keyboard, disable_web_page_preview=True)


@app.on_message(filters.private & filters.text & ~filters.command(["start", "help"]))
async def search_handler(client: Client, message: Message):
    """Handles text messages as search queries."""
    query = message.text.strip()
    user_id = message.from_user.id
    logger.info(f"Received search query: '{query}' from user {user_id}")

    if not query:
        await message.reply_text("**يرجى إدخال اسم فيلم أو مسلسل للبحث عنه.**")
        return

    status_message = await message.reply_text(f"**🔎 جاري البحث عن \"{query}\"...**")

    search_url = AKWAM_SEARCH_URL.format(query=quote_plus(query))
    response = await make_request(search_url) # Uses httpx for scraping

    if not response or not response.content:
        await status_message.edit_text("**❌ حدث خطأ أثناء جلب نتائج البحث. قد يكون الموقع معطلاً أو يحظر الطلبات.**")
        return

    results = parse_search_results(response.text)

    if not results:
        await status_message.edit_text(f"**😕 لم يتم العثور على نتائج لـ \"{query}\". حاول البحث باسم مختلف.**")
        return

    # Store results and query in user state
    if user_id not in user_states: user_states[user_id] = {}
    user_states[user_id]["last_search_results"] = results
    user_states[user_id]["last_query"] = query
    user_states[user_id]["current_search_page"] = 1 # Reset to page 1 for new search
    # Update navigation history
    user_states[user_id]["navigation_history"] = ["home", "search_1"]


    total_results = len(results)
    total_pages = math.ceil(total_results / MAX_RESULTS_PER_PAGE)
    current_page = 1

    text, keyboard = format_search_results_page(results, current_page, total_pages, query)

    try:
        # Send search results (buttons only)
        await status_message.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
    except MessageNotModified: pass
    except Exception as e:
         logger.exception("Error sending search results")
         await status_message.edit_text("**❌ حدث خطأ أثناء عرض نتائج البحث.**")

# --- UPDATED Callback Handler ---
@app.on_callback_query()
async def callback_handler(client: Client, callback_query: CallbackQuery):
    """Handles all inline button presses."""
    data = callback_query.data
    message = callback_query.message
    user = callback_query.from_user
    user_id = user.id
    logger.info(f"Callback query: '{data}' from user {user_id} ({user.username})")

    # Ensure user state exists
    if user_id not in user_states: user_states[user_id] = {"navigation_history": ["home"]}

    try:
        # --- Navigation: Go Home ---
        if data == "go_home":
            await callback_query.answer("🏡 العودة إلى البداية...")
            # Simulate /start command behavior
            await message.delete() # Delete current message
            await start_handler(client, message) # Send start message
            user_states[user_id]["navigation_history"] = ["home"] # Reset history
            return

        # --- Navigation: Go Back (Simple - needs improvement for complex state) ---
        # This simple back needs more robust state management (navigation stack)
        # For now, specific back buttons are handled below

        # --- Info Alerts ---
        elif data == "alert_choose_search":
            await callback_query.answer(
                "ℹ️ هذه هي نتائج البحث التي تم العثور عليها.\n"
                "اضغط على زر النتيجة لعرض التفاصيل.\n"
                "استخدم أزرار ⬅️ و ➡️ للتنقل بين الصفحات.",
                show_alert=True
            )
            return # Don't process further

        elif data == "alert_choose_episode":
            await callback_query.answer(
                "ℹ️ اضغط على رقم الحلقة المطلوبة لعرض خيارات التحميل الخاصة بها.",
                show_alert=True
            )
            return # Don't process further

        elif data.startswith("pageinfo_"):
             parts = data.split("_")
             await callback_query.answer(f"📄 أنت في الصفحة {parts[1]} من {parts[2]}", show_alert=False)
             return


        # --- Search Pagination ---
        elif data.startswith("searchpage_"):
            parts = data.split("_")
            page = int(parts[-1])
            query_encoded = "_".join(parts[1:-1]) # Get query context

            stored_query = user_states.get(user_id, {}).get("last_query")
            results = user_states.get(user_id, {}).get("last_search_results")

            if not stored_query or not results:
                await callback_query.answer("⚠️ انتهت صلاحية نتائج البحث. يرجى البحث مرة أخرى.", show_alert=True)
                try: await message.delete()
                except: pass
                return

            logger.info(f"Navigating search results: Query='{stored_query}', Page={page}")
            total_results = len(results)
            total_pages = math.ceil(total_results / MAX_RESULTS_PER_PAGE)

            if not 1 <= page <= total_pages:
                 await callback_query.answer("⚠️ رقم الصفحة غير صالح.", show_alert=True)
                 return

            user_states[user_id]["current_search_page"] = page # Update current page
            user_states[user_id]["navigation_history"].append(f"search_{page}") # Add to history

            text, keyboard = format_search_results_page(results, page, total_pages, stored_query)
            await message.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
            await callback_query.answer(f"📄 الصفحة {page}")

        # --- View Details (Movie/Series) ---
        elif data.startswith("view_"):
            parts = data.split("_")
            result_index = int(parts[1])
            search_page = int(parts[2]) # Get search page from callback
            # query_encoded = "_".join(parts[3:]) # Not strictly needed if using stored query

            stored_query = user_states.get(user_id, {}).get("last_query")
            results = user_states.get(user_id, {}).get("last_search_results")

            if not stored_query or not results:
                await callback_query.answer("⚠️ انتهت صلاحية بيانات النتائج. يرجى البحث مرة أخرى.", show_alert=True)
                return

            logger.info(f"Viewing details: Index={result_index}, From Search Page={search_page}")

            if not 0 <= result_index < len(results):
                 await callback_query.answer("⚠️ النتيجة المحددة غير صالحة.", show_alert=True)
                 return

            selected_item = results[result_index]
            item_link = selected_item['link']
            item_type = selected_item['type']

            # Generate context ID based on index and link hash
            view_context_id = f"{result_index}_{hash(item_link)%10000}"
            user_states[user_id]['current_view_context'] = view_context_id
            user_states[user_id]['current_search_page'] = search_page # Store the page we came from

            await callback_query.answer(f"⏳ جاري جلب تفاصيل {selected_item['title']}...")
            try: await message.delete() # Delete search results message
            except: pass
            status_message = await client.send_message(user_id, f"**⏳ جاري جلب تفاصيل {selected_item['title']}...**")

            response = await make_request(item_link) # Use httpx for scraping
            if not response or not response.content:
                await status_message.edit_text("**❌ حدث خطأ أثناء جلب التفاصيل.**")
                return

            details = None; text = "❌ خطأ في تحليل التفاصيل."; keyboard = None
            image_url = selected_item.get('image_url') # Fallback image
            details_parsed_ok = False

            if item_type == "movie":
                details = parse_movie_details(response.text)
                if details:
                    text, keyboard, image_url_detail = format_movie_details(details, search_page) # Pass search_page for back button
                    if image_url_detail: image_url = image_url_detail
                    user_states[user_id]['current_details'] = details
                    user_states[user_id]['current_item_link'] = item_link
                    user_states[user_id]['navigation_history'].append(f"movie_{view_context_id}")
                    details_parsed_ok = True
            elif item_type == "series":
                details = parse_series_details(response.text)
                if details:
                    # Start episode list on page 1, pass search_page for back button
                    text, keyboard, image_url_detail = format_series_details(details, user_id, episode_page=1, search_page=search_page)
                    if image_url_detail: image_url = image_url_detail
                    user_states[user_id]['current_details'] = details
                    user_states[user_id]['current_item_link'] = item_link
                    user_states[user_id]['current_episode_page'] = 1 # Store current episode page
                    user_states[user_id]['navigation_history'].append(f"series_{view_context_id}_ep_1")
                    details_parsed_ok = True

            if not details_parsed_ok:
                 await status_message.edit_text(text) # Show parsing error
                 return

            # Send result (photo or text)
            try:
                await status_message.delete() # Delete "Fetching..." message
                # Store the new message ID for potential future edits (like back navigation)
                sent_msg = None
                if image_url:
                    sent_msg = await client.send_photo(
                        chat_id=user_id, photo=image_url, caption=text,
                        reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN
                    )
                else:
                     sent_msg = await client.send_message(
                        chat_id=user_id, text=text, reply_markup=keyboard,
                        disable_web_page_preview=True, parse_mode=enums.ParseMode.MARKDOWN
                     )
                if sent_msg: user_states[user_id]['last_message_id'] = sent_msg.id

            except Exception as send_err:
                 logger.warning(f"Failed to send details (photo: {bool(image_url)}): {send_err}. Sending text fallback.")
                 try:
                    sent_msg = await client.send_message(user_id, text, reply_markup=keyboard,
                                               disable_web_page_preview=True, parse_mode=enums.ParseMode.MARKDOWN)
                    if sent_msg: user_states[user_id]['last_message_id'] = sent_msg.id
                 except Exception as fallback_err:
                    logger.error(f"Failed to send text fallback message: {fallback_err}")

        # --- Back from Movie/Series Details to Search Results ---
        elif data.startswith("back_srch_"):
            search_page = int(data.split("_")[-1])
            stored_query = user_states.get(user_id, {}).get("last_query")
            results = user_states.get(user_id, {}).get("last_search_results")

            if not stored_query or not results:
                await callback_query.answer("⚠️ انتهت صلاحية نتائج البحث. ابحث مرة أخرى.", show_alert=True)
                await message.delete()
                await start_handler(client, message) # Go home as fallback
                return

            await callback_query.answer(f"🔙 الرجوع لنتائج البحث (صفحة {search_page})...")
            total_results = len(results)
            total_pages = math.ceil(total_results / MAX_RESULTS_PER_PAGE)
            search_page = max(1, min(search_page, total_pages)) # Ensure valid page

            user_states[user_id]["current_search_page"] = search_page
            # Pop history back to the search state (basic implementation)
            while user_states[user_id]["navigation_history"][-1] != "home" and not user_states[user_id]["navigation_history"][-1].startswith("search"):
                 user_states[user_id]["navigation_history"].pop()
            if not user_states[user_id]["navigation_history"][-1].startswith("search"): # If only home left
                user_states[user_id]["navigation_history"].append(f"search_{search_page}") # Add it back

            text, keyboard = format_search_results_page(results, search_page, total_pages, stored_query)
            # Edit the current message (which was details) back to search results
            # If original was photo, need to delete and resend text. Let's always delete and resend text for simplicity.
            await message.delete()
            sent_msg = await client.send_message(user_id, text, reply_markup=keyboard, disable_web_page_preview=True)
            user_states[user_id]['last_message_id'] = sent_msg.id


        # --- Episode List Pagination ---
        elif data.startswith("epspage_"):
            parts = data.split("_")
            page = int(parts[-1])
            search_page = int(parts[-2]) # Get search page context
            context_id_from_callback = "_".join(parts[1:-2])

            stored_context_id = user_states.get(user_id, {}).get('current_view_context')
            details = user_states.get(user_id, {}).get('current_details')

            if not stored_context_id or context_id_from_callback != stored_context_id:
                 await callback_query.answer("⚠️ عدم تطابق سياق قائمة الحلقات أو انتهاء صلاحيته.", show_alert=True)
                 return
            if not details or "episodes" not in details:
                await callback_query.answer("⚠️ انتهت صلاحية بيانات المسلسل.", show_alert=True)
                return

            logger.info(f"Navigating episode list: Context='{stored_context_id}', Page={page}")
            total_episodes = len(details.get('episodes', []))
            total_episode_pages = math.ceil(total_episodes / EPISODES_PER_PAGE)

            if not 1 <= page <= total_episode_pages:
                 await callback_query.answer("⚠️ رقم صفحة الحلقة غير صالح.", show_alert=True)
                 return

            user_states[user_id]['current_episode_page'] = page # Update current page
            # Update history: replace last episode page state
            if user_states[user_id]["navigation_history"][-1].startswith("series_"):
                 user_states[user_id]["navigation_history"][-1] = f"series_{stored_context_id}_ep_{page}"
            else: # Should not happen if flow is correct
                 user_states[user_id]["navigation_history"].append(f"series_{stored_context_id}_ep_{page}")


            try:
                # Pass search_page context when formatting
                text, keyboard, _ = format_series_details(details, user_id, episode_page=page, search_page=search_page)
                # Edit caption if original message was photo, else edit text
                if message.photo:
                    await message.edit_caption(caption=text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
                else:
                    await message.edit_text(text=text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN, disable_web_page_preview=True)
                await callback_query.answer(f"📄 صفحة الحلقة {page}")
            except MessageNotModified: await callback_query.answer()
            except Exception as e:
                logger.error(f"Error editing message for episode pagination: {e}")
                await callback_query.answer("⚠️ حدث خطأ أثناء تحديث الصفحة.", show_alert=True)


        # --- View Episode Details (Select Episode Number) ---
        elif data.startswith("episode_"):
            parts = data.split("_")
            global_episode_index = int(parts[1])
            episode_list_page = int(parts[2]) # Get episode list page context
            search_page = int(parts[3]) # Get search page context

            logger.info(f"Viewing episode details: Global Index={global_episode_index}, From Ep Page={episode_list_page}, From Search Page={search_page}")

            current_series_details = user_states.get(user_id, {}).get('current_details') # Series details
            if not current_series_details or "episodes" not in current_series_details:
                await callback_query.answer("⚠️ انتهت صلاحية بيانات المسلسل/الحلقات.", show_alert=True)
                return

            episodes = current_series_details['episodes']
            if not 0 <= global_episode_index < len(episodes):
                 await callback_query.answer("⚠️ الحلقة المحددة غير صالحة.", show_alert=True)
                 return

            selected_episode = episodes[global_episode_index]
            episode_link = selected_episode['link']
            episode_title = selected_episode['title']
            # Store context for back navigation
            user_states[user_id]['current_episode_index_viewed'] = global_episode_index
            user_states[user_id]['current_episode_page'] = episode_list_page # Make sure this is stored
            user_states[user_id]['current_search_page'] = search_page

            await callback_query.answer(f"⏳ جاري جلب تفاصيل {episode_title}...")
            try: await message.delete() # Delete series details message
            except: pass
            status_message = await client.send_message(user_id, f"**⏳ جاري جلب تفاصيل {episode_title}...**")

            response = await make_request(episode_link) # Use httpx for scraping
            if not response or not response.content:
                await status_message.edit_text("**❌ حدث خطأ أثناء جلب تفاصيل الحلقة.**")
                return

            episode_dl_details = parse_episode_details(response.text)
            if episode_dl_details:
                 episode_dl_details['full_title'] = episode_title # Store full title
                 # Use image from series details as fallback
                 episode_dl_details['image_url'] = selected_episode.get('image_url') or current_series_details.get('image_url')
                 user_states[user_id]['current_episode_details'] = episode_dl_details # Store for download step
                 user_states[user_id]['navigation_history'].append(f"episode_{global_episode_index}")


                 # Pass episode_list_page and search_page context
                 text, keyboard, _ = format_episode_details(episode_dl_details, user_id, episode_list_page, search_page)
                 # Send as new message
                 sent_msg = await status_message.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
                 user_states[user_id]['last_message_id'] = sent_msg.id
            else:
                 await status_message.edit_text("**❌ حدث خطأ في تحليل خيارات تحميل الحلقة.**")


        # --- Back from Episode Details to Episode List ---
        elif data.startswith("back_eps_"):
            parts = data.split("_")
            episode_list_page = int(parts[-2])
            search_page = int(parts[-1])
            stored_context_id = "_".join(parts[2:-2]) # Reconstruct context id

            current_series_details = user_states.get(user_id, {}).get('current_details')
            view_context_id = user_states.get(user_id, {}).get('current_view_context')

            if not current_series_details or not view_context_id or stored_context_id != view_context_id:
                await callback_query.answer("⚠️ انتهت صلاحية بيانات المسلسل أو السياق غير متطابق.", show_alert=True)
                await message.delete()
                await start_handler(client, message) # Go home fallback
                return

            await callback_query.answer(f"🔙 الرجوع لقائمة الحلقات (صفحة {episode_list_page})...")
            user_states[user_id]['current_episode_page'] = episode_list_page
            # Pop history back to the series state
            if user_states[user_id]["navigation_history"][-1].startswith("episode_"):
                user_states[user_id]["navigation_history"].pop()


            try:
                # Pass search_page context when formatting series details
                text, keyboard, image_url = format_series_details(current_series_details, user_id, episode_list_page, search_page)
                # Edit the episode details message back to series details
                # If original had photo, edit caption, else edit text. Need to know original type.
                # Let's delete and resend for consistency.
                await message.delete()
                sent_msg = None
                if image_url:
                     sent_msg = await client.send_photo(user_id, photo=image_url, caption=text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
                else:
                     sent_msg = await client.send_message(user_id, text=text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN, disable_web_page_preview=True)
                if sent_msg: user_states[user_id]['last_message_id'] = sent_msg.id

            except Exception as e:
                logger.error(f"Error going back to episode list: {e}")
                await callback_query.answer("⚠️ حدث خطأ أثناء الرجوع.", show_alert=True)


        # --- Select Quality & Start Download ---
        elif data.startswith("quality_"):
            parts = data.split("_")
            go_link_id = parts[1]
            # Get context if passed (optional for now)
            # episode_list_page = int(parts[2]) if len(parts) > 2 else 1
            # search_page = int(parts[3]) if len(parts) > 3 else 1
            logger.info(f"Handling quality selection: GoLinkID={go_link_id}")

            if len(active_downloads) >= MAX_CONCURRENT_DOWNLOADS:
                 await callback_query.answer(f"⚠️ تم الوصول للحد الأقصى للتحميلات ({MAX_CONCURRENT_DOWNLOADS}). يرجى الانتظار.", show_alert=True)
                 return

            # --- Get Item Details (Movie or Episode) ---
            item_details_for_dl = None; selected_quality_name = "Unknown Quality"; go_link_url = None
            current_ep_details = user_states.get(user_id, {}).get('current_episode_details')
            current_main_details = user_states.get(user_id, {}).get('current_details') # Movie or Series

            # Check episode first
            if current_ep_details and current_ep_details.get('download_options'):
                for q_name, q_data in current_ep_details['download_options'].items():
                    if q_data['go_link_id'] == go_link_id:
                        item_details_for_dl = {
                            'title': current_ep_details.get('full_title', f'Episode_{go_link_id}'),
                            'image_url': current_ep_details.get('image_url'),
                            'quality': q_name, 'size': q_data.get('size', 'N/A'),
                            'year': current_main_details.get('year') if current_main_details else None, # Add year from series if exists
                        }
                        selected_quality_name = q_name; go_link_url = q_data.get('go_link'); break
            # Check movie if not found in episode
            if not item_details_for_dl and current_main_details and current_main_details.get('download_options'):
                 for q_name, q_data in current_main_details['download_options'].items():
                    if q_data['go_link_id'] == go_link_id:
                        item_details_for_dl = current_main_details.copy(); item_details_for_dl['quality'] = q_name; item_details_for_dl['size'] = q_data.get('size', 'N/A')
                        selected_quality_name = q_name; go_link_url = q_data.get('go_link'); break

            if not item_details_for_dl:
                logger.error(f"Could not find context for go_link_id {go_link_id}.")
                await callback_query.answer("❌ **خطأ: لم يتم العثور على تفاصيل التحميل. حاول مرة أخرى.**", show_alert=True)
                return

            item_title_for_status = item_details_for_dl.get('title', f'File_{go_link_id}')[:60]
            item_quality_for_status = item_details_for_dl.get('quality', selected_quality_name)
            item_size_str = f"({item_details_for_dl.get('size', 'N/A')})" if item_details_for_dl.get('size', 'N/A') != 'N/A' else ""

            await callback_query.answer(f"⏳ جاري تحضير الرابط: {item_quality_for_status} {item_size_str}", show_alert=False)

            # --- Edit message to show link extraction steps ---
            status_message = None
            try:
                step1_text = f"**{item_title_for_status}**\n({item_quality_for_status} {item_size_str})\n\n**الخطوة 1/3:** الوصول إلى رابط البوابة..."
                if message.photo: status_message = await message.edit_caption(caption=step1_text, reply_markup=None)
                else: status_message = await message.edit_text(step1_text, reply_markup=None, disable_web_page_preview=True)
            except MessageNotModified: status_message = message
            except Exception as e_edit:
                 logger.error(f"Error editing message for step 1: {e_edit}")
                 status_message = await client.send_message(user_id, f"**{item_title_for_status}**\n({item_quality_for_status} {item_size_str})\n\n**الخطوة 1/3:** الوصول إلى رابط البوابة...")

            # --- Step 1: Go Link -> ak.sv/download Link ---
            if not go_link_url or not go_link_url.startswith('http'):
                 go_link_url = f"https://go.akwam.link/link/{go_link_id}" # Default structure
                 logger.info(f"Constructed go link URL: {go_link_url}")

            go_response = await make_request(go_link_url) # httpx
            if not go_response or not go_response.content:
                await status_message.edit_text(f"**{item_title_for_status}**\n\n❌ **خطأ في الوصول إلى رابط البوابة ({go_link_url}). قد يكون الموقع معطلاً.**")
                return

            ak_download_link = parse_go_link_page(go_response.text)
            if not ak_download_link:
                logger.error(f"Failed to parse go.ak.* page. HTML: {go_response.text[:500]}")
                await status_message.edit_text(f"**{item_title_for_status}**\n\n❌ **خطأ في تحليل صفحة البوابة. ربما تغير هيكل الموقع.**")
                return

            await status_message.edit_text(f"**{item_title_for_status}**\n({item_quality_for_status} {item_size_str})\n\n**الخطوة 2/3:** الوصول إلى صفحة التحميل...")
            logger.info(f"Intermediate download link: {ak_download_link}")

            # --- Step 2: ak.sv/download -> Direct Link Page ---
            download_page_response = await make_request(ak_download_link) # httpx
            if not download_page_response or not download_page_response.content:
                await status_message.edit_text(f"**{item_title_for_status}**\n\n❌ **خطأ في الوصول إلى صفحة التحميل النهائية ({ak_download_link}).**")
                return

            # --- Step 3: Parse Direct Link (Handle Delay) ---
            await status_message.edit_text(f"**{item_title_for_status}**\n({item_quality_for_status} {item_size_str})\n\n**الخطوة 3/3:** تحليل الرابط النهائي...")
            direct_link = parse_download_page(download_page_response.text)

            js_delay_wait_seconds = 8
            if direct_link == "js_delay_detected":
                 logger.info(f"JS delay detected. Waiting {js_delay_wait_seconds}s...")
                 await status_message.edit_text(f"**{item_title_for_status}**\n({item_quality_for_status} {item_size_str})\n\n**الخطوة 3/3:** تم اكتشاف تأخير... انتظار {js_delay_wait_seconds} ثانية...")
                 await asyncio.sleep(js_delay_wait_seconds)
                 logger.info(f"Re-requesting {ak_download_link} after delay...")
                 download_page_response_retry = await make_request(ak_download_link) # httpx
                 if download_page_response_retry and download_page_response_retry.content:
                     direct_link = parse_download_page(download_page_response_retry.text)
                     if direct_link == "js_delay_detected": logger.warning("Still detected JS delay."); direct_link = None
                 else: logger.error("Failed to re-request download page."); direct_link = None

            if not direct_link or direct_link == "js_delay_detected":
                 logger.error(f"Failed to parse final download page. HTML: {download_page_response.text[:500]}")
                 await status_message.edit_text(f"**{item_title_for_status}**\n\n❌ **خطأ في تحليل صفحة التحميل النهائية. لم يتم العثور على الرابط أو تغير هيكل الموقع.**")
                 return

            # --- Link Found - Prepare for Download ---
            await status_message.edit_text(f"**{item_title_for_status}**\n({item_quality_for_status} {item_size_str})\n\n✅ **تم العثور على الرابط! جاري الإضافة إلى قائمة التحميل...**")
            logger.info(f"Direct download link extracted: {direct_link}")

            # --- Add to Queue and Start Download Task ---
            download_id = str(uuid.uuid4())
            active_downloads.add(download_id)
            logger.info(f"Added download {download_id} to active set ({len(active_downloads)} total).")

            # Send NEW message for progress
            dl_status_msg = await client.send_message(
                chat_id=user_id,
                text=f"**⏳ في قائمة الانتظار: {item_title_for_status}**\n({item_quality_for_status} {item_size_str})"
            )

            # Delete the link extraction message
            try: await status_message.delete()
            except: pass

            # Start background task
            asyncio.create_task(download_and_upload_wrapper(
                client=client, user_id=user_id, url=direct_link,
                item_details=item_details_for_dl.copy(), # Pass copy
                progress_msg=dl_status_msg, download_id=download_id
            ))

        # --- Other Callbacks ---
        elif data == "help":
            await callback_query.answer("❓ أرسل اسم الفيلم/المسلسل للبحث أو استخدم الأزرار للتنقل.", show_alert=True)
        elif data == "no_links":
            await callback_query.answer("⚠️ لم يتم العثور على روابط تحميل لهذا العنصر/الجودة.", show_alert=True)
        else:
            logger.warning(f"Unhandled callback data: {data}")
            await callback_query.answer() # Answer silently

    # --- General Error Handling ---
    except MessageNotModified:
        logger.debug("Message not modified, skipping edit.")
        try: await callback_query.answer()
        except: pass
    except FloodWait as e:
        logger.warning(f"Flood wait triggered: {e.value} seconds. Sleeping.")
        await asyncio.sleep(e.value + 1)
    except MessageIdInvalid:
         logger.warning("Callback failed: Original message ID invalid (likely deleted).")
         try: await callback_query.answer("⚠️ لم يتم العثور على الرسالة الأصلية.", show_alert=True)
         except: pass
    except Exception as e:
        logger.exception(f"Error handling callback query data '{data}': {e}")
        try:
            # Avoid alert for common navigation errors if message deleted
            if "MESSAGE_ID_INVALID" not in str(e) and "message to edit not found" not in str(e).lower():
                 await callback_query.answer("❌ حدث خطأ أثناء معالجة هذا الإجراء.", show_alert=True)
            else: await callback_query.answer()
        except: pass


# --- Download & Upload Wrapper ---
async def download_and_upload_wrapper(client: Client, user_id: int, url: str, item_details: dict, progress_msg: Message, download_id: str):
    """Acquires semaphore, downloads using aiohttp, gets meta, generates thumb, and uploads."""
    file_path = None; thumb_path = None; metadata = None
    item_title = item_details.get('title', 'Unknown File')
    item_quality = item_details.get('quality', '')
    item_size = item_details.get('size', 'N/A')
    short_title = f"{item_title[:35]}.. ({item_quality})" if len(item_title) > 35 else f"{item_title} ({item_quality})"
    size_str = f" ({item_size})" if item_size != 'N/A' else ""

    try:
        logger.info(f"Waiting for semaphore for download {download_id} ({short_title})...")
        async with download_semaphore:
            logger.info(f"Semaphore acquired for {download_id}. Starting process...")
            start_process_time = time.time()

            # --- 1. Define File Paths ---
            parsed_path = urlparse(url).path
            base_name = parsed_path.split('/')[-1] if parsed_path else f"video_{int(time.time())}"
            safe_base_name = re.sub(r'[\\/*?:"<>|]', "_", base_name)
            quality_tag = item_quality.replace(" ", "_") if item_quality else ""
            name_part, ext_part = os.path.splitext(safe_base_name)
            if not ext_part or len(ext_part) > 5: ext_part = ".mp4" # Ensure valid extension
            if quality_tag: safe_base_name = f"{name_part}_{quality_tag}{ext_part}"
            else: safe_base_name = f"{name_part}{ext_part}"

            unique_id_part = download_id[:8]
            file_path = os.path.join(DOWNLOAD_PATH, f"{unique_id_part}_{safe_base_name}")
            thumb_path_temp = os.path.join(DOWNLOAD_PATH, f"thumb_{unique_id_part}.jpg")
            logger.info(f"Download path: {file_path}")
            logger.info(f"Thumbnail path: {thumb_path_temp}")

            # --- 2. Download File ---
            # Update progress message before starting download
            await progress_msg.edit_text(f"**📥 جاري التحميل: {item_title}**\n({item_quality}{size_str})")
            download_success = await download_file_aiohttp(url, file_path, progress_msg)

            if not download_success:
                logger.error(f"Download failed for {download_id} ({short_title}). Aborting.")
                # Error message should already be in progress_msg
                if os.path.exists(file_path):
                     try: os.remove(file_path)
                     except OSError as e: logger.error(f"Error removing failed download {file_path}: {e}")
                return # Exit

            # --- 3. Get Metadata ---
            if os.path.exists(file_path) and os.path.getsize(file_path) > 1024:
                try: await progress_msg.edit_text(f"**⚙️ جاري استخراج البيانات الوصفية لـ {short_title}...**")
                except MessageNotModified: pass
                metadata = await get_video_metadata(file_path)
                if metadata: logger.info(f"Metadata found for {download_id}: {metadata}")
                else: logger.warning(f"Could not get metadata for {download_id}."); metadata = {"width": 0, "height": 0, "duration": 0}
            else:
                 logger.error(f"Downloaded file '{file_path}' missing or empty. Aborting upload.")
                 await progress_msg.edit_text(f"❌ **خطأ: الملف المحمل لـ {short_title} فارغ أو مفقود.**")
                 return

            # --- 4. Generate Thumbnail ---
            if metadata and metadata.get("duration", 0) > 0:
                try: await progress_msg.edit_text(f"**🖼️ جاري إنشاء صورة مصغرة لـ {short_title}...**")
                except MessageNotModified: pass
                thumb_path = await generate_thumbnail(file_path, thumb_path_temp, metadata["duration"])
                if thumb_path: logger.info(f"Thumbnail generated for {download_id}: {thumb_path}")
                else: logger.warning(f"Could not generate thumbnail for {download_id}.")
            else: logger.warning(f"Skipping thumbnail for {download_id} (missing/invalid duration).")

            # --- 5. Upload File ---
            file_size = os.path.getsize(file_path)
            # Check TG Max Size
            if file_size > TG_MAX_FILE_SIZE:
                logger.error(f"File size ({humanbytes(file_size)}) exceeds Telegram limit ({humanbytes(TG_MAX_FILE_SIZE)}) for {download_id}.")
                await progress_msg.edit_text(f"❌ **فشل الرفع: حجم الملف {humanbytes(file_size)} يتجاوز حد تيليجرام ({humanbytes(TG_MAX_FILE_SIZE)}) لـ {short_title}.**")
                return

            try: await progress_msg.edit_text(f"**⬆️ جاري الرفع: {short_title}**\n({humanbytes(file_size)})")
            except MessageNotModified: pass
            upload_start_time = time.time()
            last_update_time[progress_msg.id] = upload_start_time # Reset for upload progress

            # Build Caption
            caption = f"**{item_title}**\nالجودة: `{item_quality}`"
            if item_details.get('year'): caption += f" | السنة: `{item_details['year']}`"
            if metadata and metadata.get('duration', 0) > 0:
                 caption += f"\nالمدة: `{TimeFormatter(metadata['duration'] * 1000)}`"
            if metadata and metadata.get('width', 0) > 0:
                 caption += f" | الأبعاد: `{metadata['width']}x{metadata['height']}`"
            caption += f"\n\nDownloaded via @{client.me.username}" # Bot credit
            caption = caption[:1020] # Ensure caption limit

            try:
                sent_message = await client.send_video(
                    chat_id=user_id, video=file_path, caption=caption,
                    thumb=thumb_path, # None if failed
                    duration=metadata.get("duration", 0), width=metadata.get("width", 0), height=metadata.get("height", 0),
                    supports_streaming=True,
                    progress=progress_callback, # Upload progress func
                    progress_args=(progress_msg, f"Uploading: {short_title}", upload_start_time)
                )
                upload_duration = time.time() - upload_start_time
                total_duration = time.time() - start_process_time
                logger.info(f"Video uploaded for {download_id} in {TimeFormatter(upload_duration*1000)}. Total time: {TimeFormatter(total_duration*1000)}")
                await progress_msg.delete() # Delete progress message on success

            except FloodWait as e:
                 logger.warning(f"Flood wait ({e.value}s) during upload.")
                 await asyncio.sleep(e.value + 1)
                 try: await progress_msg.edit_text(f"⚠️ **توقف الرفع مؤقتًا بسبب الضغط ({e.value} ثانية) لـ {short_title}. قد تحتاج لإعادة المحاولة.**")
                 except Exception: pass
            except Exception as e_upload:
                 logger.exception(f"Error during Pyrogram upload for {download_id}: {e_upload}")
                 try: await progress_msg.edit_text(f"❌ **فشل رفع الملف لـ {short_title}**: `{e_upload}`")
                 except Exception: pass

    except Exception as e_wrapper:
        logger.exception(f"Error in download/upload wrapper for {download_id} ({short_title}): {e_wrapper}")
        try:
             await progress_msg.edit_text(f"❌ **حدث خطأ حرج أثناء معالجة {short_title}**.")
        except: pass
    finally:
        # --- Cleanup ---
        try:
            if file_path and os.path.exists(file_path): os.remove(file_path); logger.debug(f"Cleaned video: {file_path}")
            if thumb_path and os.path.exists(thumb_path): os.remove(thumb_path); logger.debug(f"Cleaned thumb: {thumb_path}")
            elif thumb_path_temp and os.path.exists(thumb_path_temp): os.remove(thumb_path_temp); logger.debug(f"Cleaned temp thumb: {thumb_path_temp}")
        except OSError as e_clean: logger.error(f"Error cleaning up files for {download_id}: {e_clean}")

        # Clean up progress tracking state
        if progress_msg and progress_msg.id in last_update_time: del last_update_time[progress_msg.id]
        if progress_msg and progress_msg.id in last_dl_update_time: del last_dl_update_time[progress_msg.id]

        # Remove from active downloads
        if download_id in active_downloads:
            active_downloads.remove(download_id)
            logger.info(f"Removed {download_id} from active set ({len(active_downloads)} remaining).")


# --- Main Execution ---
if __name__ == "__main__":
    logger.info("Bot starting...")
    # Ensure download directory exists
    try:
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        logger.info(f"Download directory: {DOWNLOAD_PATH}")
        test_file = os.path.join(DOWNLOAD_PATH, ".write_test"); open(test_file, "w").write("test"); os.remove(test_file)
        logger.info(f"Write access confirmed: {DOWNLOAD_PATH}")
    except OSError as e:
        logger.critical(f"CRITICAL ERROR: Cannot create/write to {DOWNLOAD_PATH}: {e}. Downloads will fail.")
        exit(1)
    except Exception as e:
         logger.critical(f"CRITICAL ERROR: Checking {DOWNLOAD_PATH}: {e}")
         exit(1)

    if not FFMPEG_FOUND or not FFPROBE_FOUND:
         logger.warning("Reminder: ffmpeg/ffprobe not found. Thumbnails/Metadata limited.")

    # Set bot commands (optional)
    # asyncio.run(app.set_bot_commands([
    #     BotCommand("start", "البدء / إعادة التشغيل"),
    #     BotCommand("help", "عرض المساعدة")
    # ]))
    # logger.info("Bot commands set.")


    # Run the bot using app.run()
    try:
        logger.info("Bot Started!")
        app.run() # Use app.run() to start the client and block until stopped
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopping...")
    except Exception as e:
        logger.exception(f"Bot crashed: {e}")
    finally:
        logger.info("Bot stopped.")
        # Gracefully close the httpx client
        try:
             async def close_http():
                 await http_client.aclose()
                 logger.info("HTTP scraping client closed.")
             # Run the async close function
             asyncio.run(close_http())
        except Exception as ce:
             logger.error(f"Error closing HTTP scraping client: {ce}")
