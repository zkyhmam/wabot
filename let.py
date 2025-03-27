# -*- coding: utf-8 -*-

import asyncio
import logging
import time
import math
import os
import re
from urllib.parse import quote_plus, urlparse, parse_qs
import uuid # For unique download IDs

# --- Pyrogram & Related ---
from pyrogram import Client, filters, enums
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery,
    InputMediaPhoto, InputMediaVideo
)
from pyrogram.errors import FloodWait, UserNotParticipant, MessageNotModified, MessageIdInvalid

# --- HTTP & Parsing ---
import httpx
from bs4 import BeautifulSoup

# --- Configuration ---
# WARNING: Storing secrets directly in code is generally not recommended for production.
# Consider using environment variables or a config file in a real-world scenario.
API_ID = 25713843
API_HASH = "311352d08811e7f5136dfb27f71014c1"
BOT_TOKEN = "7558529929:AAFmMHm2HuqHsdqdQvl_ZLCoXn5XOPiRzfw"

# --- Constants ---
AKWAM_BASE_URL = "https://ak.sv"
AKWAM_SEARCH_URL = AKWAM_BASE_URL + "/search?q={query}"
AKWAM_RECENT_URL = AKWAM_BASE_URL + "/recent" # Added for potential future use
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
REQUEST_DELAY = 1.5 # Seconds delay between requests to the site
PROGRESS_UPDATE_INTERVAL = 2 # Seconds interval for updating progress messages
MAX_RESULTS_PER_PAGE = 6 # Number of search results per page
EPISODES_PER_PAGE = 8 # Number of episodes to show per page
DOWNLOAD_PATH = "/overlay_tmp" # <<< CHANGED: Download directory
MAX_CONCURRENT_DOWNLOADS = 5 # <<< ADDED: Max concurrent downloads

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()] # Output logs to console
)
logger = logging.getLogger(__name__)

# --- Pyrogram Client Initialization ---
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

# --- HTTP Client Wrapper ---
http_client = httpx.AsyncClient(
    headers={"User-Agent": DEFAULT_USER_AGENT},
    follow_redirects=True,
    timeout=20.0 # Increase timeout slightly
)

# --- Utility to format size ---
def format_size(size_bytes):
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    try:
        i = int(math.floor(math.log(size_bytes, 1024))) if size_bytes > 0 else 0
    except ValueError:
        i = 0
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2) if p > 0 else 0
    # Ensure index is within bounds
    i = min(i, len(size_name) - 1)
    return f"{s} {size_name[i]}"

async def make_request(url: str, method: str = "GET", data=None, allow_redirects=True):
    """Makes an HTTP request with delay and error handling."""
    try:
        logger.info(f"Requesting URL: {url} (Method: {method})")
        await asyncio.sleep(REQUEST_DELAY) # Crucial delay

        if method.upper() == "GET":
            response = await http_client.get(url, follow_redirects=allow_redirects)
        elif method.upper() == "POST":
             response = await http_client.post(url, data=data, follow_redirects=allow_redirects)
        else:
            logger.error(f"Unsupported HTTP method: {method}")
            return None

        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        logger.info(f"Request successful for {url} - Status: {response.status_code}")
        return response

    except httpx.TimeoutException:
        logger.error(f"Request timed out for URL: {url}")
    except httpx.RequestError as e:
        logger.error(f"HTTP Request failed for URL: {url} - Error: {e}")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP Error for URL: {url} - Status: {e.response.status_code} - Response: {e.response.text[:200]}...")
    except Exception as e:
        logger.exception(f"An unexpected error occurred during request to {url}: {e}")

    return None

# --- HTML Parsing Functions (Unchanged from previous version) ---

def parse_search_results(html_content: str) -> list:
    """Parses the Akwam search results page."""
    results = []
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        result_items = soup.select('div.widget[data-grid="6"] div.widget-body div.col-lg-auto')
        logger.info(f"Found {len(result_items)} potential result items on search page.")

        for item in result_items:
            entry_box = item.find('div', class_='entry-box')
            if not entry_box:
                continue

            title_tag = entry_box.find('h3', class_='entry-title')
            link_tag = entry_box.find('a', class_='box')
            img_tag = entry_box.find('img', class_='lazy')
            rating_tag = entry_box.find('span', class_='label rating')
            quality_tag = entry_box.find('span', class_='label quality')
            meta_tags = entry_box.select('div.font-size-16 span.badge')

            if title_tag and link_tag:
                title = title_tag.get_text(strip=True)
                link = link_tag.get('href')
                if link and not link.startswith(('http://', 'https://')):
                    link = AKWAM_BASE_URL + link if link.startswith('/') else AKWAM_BASE_URL + '/' + link

                image_url = img_tag.get('data-src') if img_tag and img_tag.get('data-src') else (img_tag.get('src') if img_tag else None)
                if image_url and not image_url.startswith(('http://', 'https://')):
                     pass

                rating = rating_tag.get_text(strip=True).replace(' ', '').replace('+', '') if rating_tag else "N/A"
                rating = re.sub(r'[^\d\.]', '', rating) if rating != "N/A" else "N/A"

                quality = quality_tag.get_text(strip=True) if quality_tag else "N/A"

                year = "N/A"
                genres = []
                if meta_tags:
                    # Safely access meta_tags[0]
                    if meta_tags:
                        year_badge = meta_tags[0]
                        if year_badge and 'badge-secondary' in year_badge.get('class', []):
                            year_match = re.search(r'\b(19|20)\d{2}\b', year_badge.get_text(strip=True))
                            year = year_match.group(0) if year_match else "N/A"
                            genres = [tag.get_text(strip=True) for tag in meta_tags[1:]]
                        else:
                            # If first badge is not year, assume all are genres
                            year = "N/A"
                            genres = [tag.get_text(strip=True) for tag in meta_tags]
                    else:
                        year = "N/A"
                        genres = []


                item_type = "series" if "/series/" in link else ("movie" if "/movie/" in link else "unknown")

                results.append({
                    'title': title,
                    'link': link,
                    'image_url': image_url,
                    'rating': rating,
                    'quality': quality,
                    'year': year,
                    'genres': genres,
                    'type': item_type,
                })
            else:
                logger.warning("Skipping an item in search results due to missing title or link tag.")

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

        info_div = soup.find('div', class_='col-lg-7')
        if info_div:
            rating_div = info_div.find('div', string=re.compile(r'10\s*/\s*\d+(\.\d+)?'))
            if rating_div:
                 rating_text = rating_div.get_text(strip=True)
                 rating_match = re.search(r'(\d+(\.\d+)?)\s*/\s*10', rating_text)
                 details['rating'] = rating_match.group(1) if rating_match else "N/A"
            else:
                imdb_link = info_div.find('a', href=lambda href: href and 'imdb.com' in href)
                if imdb_link:
                    rating_span = imdb_link.find_next_sibling('span', class_='mx-2')
                    details['rating'] = rating_span.get_text(strip=True).split('/')[0].strip() if rating_span else "N/A"
                else:
                    details['rating'] = "N/A"

            meta_lines = info_div.find_all('div', class_='font-size-16 text-white mt-2')
            for line in meta_lines:
                text = line.get_text(strip=True)
                parts = text.split(':', 1) # Split only once
                if len(parts) == 2:
                    key_text = parts[0].strip()
                    value_text = parts[1].strip()
                    if "اللغة" in key_text:
                        details['language'] = value_text
                    elif "جودة الفيلم" in key_text:
                        quality_parts = value_text.split('-',1)
                        details['format'] = quality_parts[0].strip() if len(quality_parts) > 0 else "N/A"
                        details['quality_res'] = quality_parts[1].strip() if len(quality_parts) > 1 else "N/A"
                    elif "انتاج" in key_text:
                        details['country'] = value_text
                    elif "السنة" in key_text:
                        details['year'] = value_text
                    elif "مدة الفيلم" in key_text:
                        details['duration'] = value_text

            details['genres'] = [a.get_text(strip=True) for a in info_div.select('div.d-flex a.badge-light')]

            date_divs = info_div.find_all('div', class_='font-size-14 text-muted')
            if len(date_divs) > 0:
                details['added_date'] = date_divs[0].get_text(strip=True).replace('تـ الإضافة :', '').strip()
            if len(date_divs) > 1:
                details['updated_date'] = date_divs[1].get_text(strip=True).replace('تـ اخر تحديث :', '').strip()


        story_header = soup.find('span', class_='header-link text-white', string='قصة الفيلم')
        if story_header:
            story_div = story_header.find_parent('header').find_next_sibling('div', class_='widget-body')
            if story_div:
                story_p = story_div.find('p')
                story_h2_div = story_div.find('h2')
                if story_p:
                    details['description'] = story_p.get_text("\n", strip=True)
                elif story_h2_div and story_h2_div.find('div'):
                    details['description'] = story_h2_div.find('div').get_text("\n", strip=True)
                else:
                    details['description'] = story_div.get_text("\n", strip=True)
            else:
                details['description'] = "N/A"
        else:
             # Fallback: Try finding description in common divs if header not found
             desc_div = soup.find('div', class_='font-size-16 text-white', string=lambda t: t and len(t) > 50) # Heuristic
             details['description'] = desc_div.get_text("\n", strip=True) if desc_div else "N/A"


        trailer_tag = soup.find('a', {'data-fancybox': ''}, href=lambda href: href and 'youtube.com' in href)
        details['trailer_url'] = trailer_tag['href'] if trailer_tag else None

        gallery_tags = soup.find_all('a', {'data-fancybox': 'movie-gallery'})
        details['gallery'] = [a['href'] for a in gallery_tags if a.get('href')]

        details['download_options'] = {}
        quality_tabs = soup.select('ul.header-tabs.tabs li a')

        logger.info(f"Found {len(quality_tabs)} quality tabs.")

        for i, tab_link in enumerate(quality_tabs):
            quality_name = tab_link.get_text(strip=True)
            tab_id = tab_link['href'].lstrip('#')
            logger.debug(f"Processing quality tab: {quality_name} (ID: {tab_id})")

            content_div = soup.find('div', id=tab_id)
            if not content_div:
                 content_div = soup.find(id=tab_id)
                 if not content_div or 'tab-content' not in content_div.get('class', []):
                     logger.warning(f"Could not find content div for tab ID: {tab_id}")
                     continue

            download_link_tag = content_div.find('a', class_='link-download')
            watch_link_tag = content_div.find('a', class_='link-show')
            file_size_tag = content_div.find('span', class_='font-size-14 mr-auto')

            go_link = None
            if download_link_tag and download_link_tag.has_attr('href') and 'go.ak.sv' in download_link_tag['href']:
                go_link = download_link_tag['href']
            elif watch_link_tag and watch_link_tag.has_attr('href') and 'go.ak.sv' in watch_link_tag['href']:
                 go_link = watch_link_tag['href']

            file_size = file_size_tag.get_text(strip=True) if file_size_tag else "N/A"

            if go_link:
                try:
                    parsed_go_link = urlparse(go_link)
                    go_link_id = parsed_go_link.path.split('/')[-1]
                    if go_link_id:
                         details['download_options'][quality_name] = {
                             'go_link': go_link,
                             'go_link_id': go_link_id,
                             'size': file_size
                         }
                         logger.debug(f"  Found go_link: {go_link} (ID: {go_link_id}), Size: {file_size}")
                    else:
                         logger.warning(f"  Could not extract ID from go_link: {go_link}")
                except Exception:
                    logger.warning(f"  Error extracting ID from go_link: {go_link}", exc_info=True)
            else:
                logger.warning(f"  No go.ak.sv link found for quality: {quality_name}")

        more_widget = soup.find('div', class_='widget-4')
        details['related'] = []
        if more_widget:
            related_items = more_widget.select('.entry-box-1')
            for item in related_items:
                 title_tag = item.find('h3', class_='entry-title')
                 link_tag = item.find('a', class_='box')
                 img_tag = item.find('img', class_='lazy')
                 if title_tag and link_tag:
                     rel_title = title_tag.get_text(strip=True)
                     rel_link = link_tag.get('href')
                     rel_image = img_tag.get('data-src') if img_tag and img_tag.has_attr('data-src') else (img_tag.get('src') if img_tag else None)
                     if rel_link and not rel_link.startswith(('http://', 'https://')):
                         rel_link = AKWAM_BASE_URL + rel_link if rel_link.startswith('/') else AKWAM_BASE_URL + '/' + rel_link

                     details['related'].append({
                         'title': rel_title,
                         'link': rel_link,
                         'image_url': rel_image
                     })


        logger.info(f"Successfully parsed details for: {details.get('title', 'N/A')}")
        return details

    except Exception as e:
        logger.exception(f"Error parsing movie details: {e}")
        return None

def parse_series_details(html_content: str) -> dict | None:
    """Parses the Akwam series details page, including episodes."""
    details = parse_movie_details(html_content) # Reuse movie parser for common fields
    if not details:
        return None

    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        details['episodes'] = []
        episodes_section = soup.find('div', id='series-episodes')
        if episodes_section:
            episode_items = episodes_section.select('div.widget-body > div[class*="bg-primary"], div.widget-body div.col-12')
            logger.info(f"Found {len(episode_items)} potential episode blocks using selector.")

            for item in episode_items:
                link_tag = item.find('a', href=lambda href: href and ('/episode/' in href or '/watch/' in href)) # Allow /watch/ too
                title_tag = item.find('h2') or item.find('h3')
                date_tag = item.find('p', class_='entry-date')
                img_tag = item.find('img', class_='img-fluid')

                ep_title = "N/A"
                if link_tag and title_tag and link_tag in title_tag:
                    ep_title = title_tag.get_text(strip=True)
                elif link_tag:
                    ep_title = link_tag.get_text(strip=True)
                    if not ep_title and link_tag.find('h2'):
                         ep_title = link_tag.find('h2').get_text(strip=True)
                    elif not ep_title and title_tag:
                         ep_title = title_tag.get_text(strip=True)
                elif title_tag:
                    ep_title = title_tag.get_text(strip=True)
                    link_tag = None
                else:
                    # Try finding title in other common tags if primary fails
                    alt_title_tag = item.find(class_='font-size-18') or item.find(class_='entry-title')
                    if alt_title_tag:
                        ep_title = alt_title_tag.get_text(strip=True)
                        if not link_tag: link_tag = alt_title_tag.find('a') # Maybe link is inside here
                    else:
                        logger.warning("Skipping an episode item due to missing title.")
                        continue

                if link_tag and link_tag.has_attr('href'):
                    ep_link = link_tag['href']
                    if ep_link and not ep_link.startswith(('http://', 'https://')):
                       ep_link = AKWAM_BASE_URL + ep_link if ep_link.startswith('/') else AKWAM_BASE_URL + '/' + ep_link
                else:
                    # Try finding link elsewhere if not found yet
                    fallback_link_tag = item.find('a', class_='d-flex') # Another common pattern
                    if fallback_link_tag and fallback_link_tag.has_attr('href') and ('/episode/' in fallback_link_tag['href'] or '/watch/' in fallback_link_tag['href']):
                         ep_link = fallback_link_tag['href']
                         if ep_link and not ep_link.startswith(('http://', 'https://')):
                             ep_link = AKWAM_BASE_URL + ep_link if ep_link.startswith('/') else AKWAM_BASE_URL + '/' + ep_link
                    else:
                        ep_link = None
                        logger.warning(f"Skipping episode '{ep_title}' due to missing link href.")
                        continue

                ep_image = img_tag['src'] if img_tag and img_tag.has_attr('src') else None
                ep_date = date_tag.get_text(strip=True) if date_tag else "N/A"

                ep_num_match = re.search(r'(?:الحلقة|حلقة)\s*:?\s*(\d+)', ep_title, re.IGNORECASE)
                ep_num = int(ep_num_match.group(1)) if ep_num_match else None

                details['episodes'].append({
                    'title': ep_title,
                    'link': ep_link,
                    'image_url': ep_image,
                    'date': ep_date,
                    'number': ep_num
                })

            logger.info(f"Keeping original episode order (likely newest first). Found {len(details['episodes'])} episodes.")

        else:
            logger.warning("Episodes section (#series-episodes or similar) not found.")

        logger.info(f"Successfully parsed series details and {len(details['episodes'])} episodes for: {details.get('title', 'N/A')}")
        return details

    except Exception as e:
        logger.exception(f"Error parsing series details/episodes: {e}")
        return details # Return potentially partial details

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

        for i, tab_link in enumerate(quality_tabs):
            quality_name = tab_link.get_text(strip=True)
            tab_id = tab_link['href'].lstrip('#')
            logger.debug(f"Processing quality tab: {quality_name} (ID: {tab_id})")

            content_div = soup.find('div', id=tab_id)
            if not content_div:
                 content_div = soup.find(id=tab_id)
                 if not content_div or 'tab-content' not in content_div.get('class', []):
                     logger.warning(f"Could not find content div for tab ID: {tab_id}")
                     continue

            download_link_tag = content_div.find('a', class_='link-download')
            watch_link_tag = content_div.find('a', class_='link-show')
            file_size_tag = content_div.find('span', class_='font-size-14 mr-auto')

            go_link = None
            if download_link_tag and download_link_tag.has_attr('href') and 'go.ak.sv' in download_link_tag['href']:
                go_link = download_link_tag['href']
            elif watch_link_tag and watch_link_tag.has_attr('href') and 'go.ak.sv' in watch_link_tag['href']:
                 go_link = watch_link_tag['href']

            file_size = file_size_tag.get_text(strip=True) if file_size_tag else "N/A"

            if go_link:
                try:
                    parsed_go_link = urlparse(go_link)
                    go_link_id = parsed_go_link.path.split('/')[-1]
                    if go_link_id:
                         details['download_options'][quality_name] = {
                             'go_link': go_link,
                             'go_link_id': go_link_id,
                             'size': file_size
                         }
                         logger.debug(f"  Found go_link: {go_link} (ID: {go_link_id}), Size: {file_size}")
                    else:
                         logger.warning(f"  Could not extract ID from go_link: {go_link}")
                except Exception:
                    logger.warning(f"  Error extracting ID from go_link: {go_link}", exc_info=True)
            else:
                logger.warning(f"  No go.ak.sv link found for quality: {quality_name}")


        logger.info(f"Successfully parsed download options for episode: {details.get('title', 'N/A')}")
        return details

    except Exception as e:
        logger.exception(f"Error parsing episode details: {e}")
        return None

def parse_go_link_page(html_content: str) -> str | None:
    """Parses the go.ak.sv interstitial page to find the ak.sv/download link."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        download_link_tag = soup.find('a', class_='download-link', href=lambda href: href and '/download/' in href)
        if download_link_tag and download_link_tag.has_attr('href'):
            ak_download_link = download_link_tag['href']
            logger.info(f"Found ak.sv download link: {ak_download_link}")
            if ak_download_link.startswith('//'):
                ak_download_link = 'https:' + ak_download_link
            elif not ak_download_link.startswith(('http://', 'https://')):
                 parsed_base = urlparse(AKWAM_BASE_URL)
                 scheme = parsed_base.scheme or 'https'
                 netloc = parsed_base.netloc or urlparse(AKWAM_BASE_URL).netloc # Ensure netloc is present
                 ak_download_link = f"{scheme}://{netloc}{ak_download_link}" if ak_download_link.startswith('/') else f"{scheme}://{netloc}/{ak_download_link}"

            return ak_download_link
        else:
            # Fallback: Check for alternative button structures if needed
            logger.error("Could not find the 'a.download-link' tag on the go.ak.sv page.")
            return None
    except Exception as e:
        logger.exception(f"Error parsing go.ak.sv page: {e}")
        return None

def parse_download_page(html_content: str) -> str | None:
    """Parses the ak.sv/download page to find the direct download link."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        direct_link_tag = soup.select_one('div.btn-loader a.link.btn.btn-light')
        direct_link = None
        if direct_link_tag and direct_link_tag.has_attr('href'):
            potential_link = direct_link_tag['href']
            # Stricter validation for direct link
            if 'downet.net' in potential_link or any(potential_link.lower().endswith(ext) for ext in ['.mp4', '.mkv', '.avi', '.zip', '.rar', '.wmv']):
                 direct_link = potential_link
                 logger.info(f"Found direct download link via primary selector: {direct_link}")
                 return direct_link # Found a good link, return it
            else:
                 logger.warning(f"Primary selector found a link, but it doesn't look like a direct download link: {potential_link}")

        # If primary selector fails or link is invalid, check for JS
        scripts = soup.find_all('script')
        timeout_script = None
        for script in scripts:
            script_content = script.string
            if script_content and 'setTimeout' in script_content and ('location.href' in script_content or 'downet.net' in script_content):
                    timeout_script = script_content
                    break

        if timeout_script:
                logger.warning("Found JavaScript timer potentially setting the download link.")
                # Attempt to extract the link from the script
                link_match = re.search(r"location\.href\s*=\s*'([^']+)'", timeout_script)
                if not link_match:
                    link_match = re.search(r"href',\s*'([^']+)'", timeout_script) # Another pattern
                if link_match:
                    js_link = link_match.group(1)
                    if 'downet.net' in js_link or any(js_link.lower().endswith(ext) for ext in ['.mp4', '.mkv', '.avi']):
                        logger.info(f"Extracted potential link from JS: {js_link}. Signaling JS delay.")
                        return "js_delay_detected" # Signal delay is needed
                logger.error("Could not extract valid link from JS timer script on download page.")
                return "js_delay_detected" # Signal delay even if extraction failed, worth retrying

        logger.error("Could not find the direct download link tag or a JS delay script on the download page.")
        return None
    except Exception as e:
        logger.exception(f"Error parsing ak.sv/download page: {e}")
        return None

# --- Markup Utilities (Unchanged) ---

def create_pagination_buttons(current_page: int, total_pages: int, callback_prefix: str) -> list:
    """Creates previous/next pagination buttons."""
    buttons = []
    if total_pages <= 1:
        return buttons
    row = []
    if current_page > 1:
        row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"{callback_prefix}_{current_page - 1}"))
    if current_page < total_pages:
        row.append(InlineKeyboardButton("Next ➡️", callback_data=f"{callback_prefix}_{current_page + 1}"))
    if row:
        buttons.append(row)
    return buttons

def format_search_results_page(results: list, page: int, total_pages: int, query: str) -> tuple[str, InlineKeyboardMarkup]:
    """Formats search results for display in Telegram."""
    if not results:
        return "No results found.", None

    text = f"🔍 Search Results for \"**{query}**\" (Page {page}/{total_pages}):\n\n"
    buttons = []
    start_index = (page - 1) * MAX_RESULTS_PER_PAGE
    end_index = start_index + MAX_RESULTS_PER_PAGE
    current_results = results[start_index:end_index]

    for i, result in enumerate(current_results):
        index = start_index + i + 1
        item_type_icon = "🎬" if result['type'] == 'movie' else ("📺" if result['type'] == 'series' else "❓")
        rating_str = f"⭐ {result['rating']}" if result['rating'] != "N/A" else ""
        year_str = f"({result['year']})" if result['year'] != "N/A" else ""
        quality_str = f"[{result['quality']}]" if result['quality'] != "N/A" else ""
        genres_str = ", ".join(result['genres'][:2])

        text += f"{index}. {item_type_icon} **{result['title']}** {year_str} {rating_str} {quality_str}\n"
        if genres_str:
            text += f"   Genres: {genres_str}\n"
        text += "\n"

        full_result_index = start_index + i
        callback_safe_query = quote_plus(query)[:30]
        buttons.append([InlineKeyboardButton(
             f"{index}. {result['title'][:30]}...",
             callback_data=f"view_{full_result_index}_{callback_safe_query}"
        )])

    pagination_rows = create_pagination_buttons(page, total_pages, f"searchpage_{callback_safe_query}")
    buttons.extend(pagination_rows)

    return text, InlineKeyboardMarkup(buttons)

def format_movie_details(details: dict) -> tuple[str, InlineKeyboardMarkup, str | None]:
    """Formats movie details for display."""
    text = f"🎬 **{details.get('title', 'N/A')}**\n\n"
    text += f"⭐ Rating: {details.get('rating', 'N/A')}/10\n"
    text += f"🗓️ Year: {details.get('year', 'N/A')}\n"
    text += f"⏱️ Duration: {details.get('duration', 'N/A')}\n"
    text += f"🏴 Country: {details.get('country', 'N/A')}\n"
    text += f"🗣️ Language: {details.get('language', 'N/A')}\n"
    text += f"🎞️ Format/Quality: {details.get('format', 'N/A')} / {details.get('quality_res', 'N/A')}\n"
    if details.get('genres'):
        text += f"🎭 Genres: {', '.join(details['genres'])}\n"
    desc = details.get('description', 'N/A')
    text += f"\n**📝 Description:**\n{desc[:500]}{'...' if len(desc) > 500 else ''}\n"

    buttons = []
    if details.get('download_options'):
        quality_buttons = []
        for quality, data in details['download_options'].items():
            size_str = f" ({data['size']})" if data['size'] != "N/A" else ""
            # Append go_link_id to identify which quality was chosen
            quality_callback = f"quality_{data['go_link_id']}"
            quality_buttons.append(
                InlineKeyboardButton(f"💾 {quality}{size_str}", callback_data=quality_callback)
            )
        for i in range(0, len(quality_buttons), 2):
             buttons.append(quality_buttons[i:i+2])
    else:
        buttons.append([InlineKeyboardButton("⚠️ No Download Links Found", callback_data="no_links")])

    if details.get('trailer_url'):
        buttons.append([InlineKeyboardButton("🎬 Watch Trailer", url=details['trailer_url'])])

    return text, InlineKeyboardMarkup(buttons), details.get('image_url')

def format_series_details(details: dict, user_id: int, episode_page: int = 1) -> tuple[str, InlineKeyboardMarkup, str | None]:
    """Formats series details, focusing on episode list with pagination."""
    text = f"📺 **{details.get('title', 'N/A')}**\n\n"
    text += f"⭐ Rating: {details.get('rating', 'N/A')}/10\n"
    text += f"🗓️ Year: {details.get('year', 'N/A')}\n"
    if details.get('genres'):
        text += f"🎭 Genres: {', '.join(details['genres'])}\n"
    desc = details.get('description', 'N/A')
    text += f"\n**📝 Description:**\n{desc[:250]}{'...' if len(desc) > 250 else ''}\n"

    buttons = []
    episodes = details.get('episodes', [])
    total_episodes = len(episodes)

    if total_episodes > 0:
        total_episode_pages = math.ceil(total_episodes / EPISODES_PER_PAGE)
        episode_page = max(1, min(episode_page, total_episode_pages))

        start_index = (episode_page - 1) * EPISODES_PER_PAGE
        end_index = start_index + EPISODES_PER_PAGE
        current_episodes = episodes[start_index:end_index]

        text += f"\n**🎬 Episodes ({total_episodes}) - Page {episode_page}/{total_episode_pages}:**\n"

        for i, episode in enumerate(current_episodes):
            global_index = start_index + i
            ep_num_str = f"Ep {episode['number']}" if episode.get('number') is not None else f"#{total_episodes - global_index}"
            # Use global index for selecting the specific episode
            buttons.append([InlineKeyboardButton(
                f"{ep_num_str}: {episode['title'][:35]}...",
                callback_data=f"episode_{global_index}"
            )])

        series_context_id = user_states.get(user_id, {}).get('current_view_context', 'ctx_error')
        pagination_rows = create_pagination_buttons(episode_page, total_episode_pages, f"epspage_{series_context_id}")
        buttons.extend(pagination_rows)
    else:
        text += "\n**🎬 No episodes found for this series yet.**"


    if details.get('trailer_url'):
        buttons.append([InlineKeyboardButton("🎬 Watch Trailer", url=details['trailer_url'])])

    # Add Back button to search results?
    # Needs reliable way to know which search result this was or store search context better.
    # Example (might be unreliable if user searches again):
    # last_query = user_states.get(user_id, {}).get("last_query")
    # if last_query:
    #     callback_safe_query = quote_plus(last_query)[:30]
    #     buttons.append([InlineKeyboardButton("🔙 Back to Search", callback_data=f"searchpage_{callback_safe_query}_1")])


    return text, InlineKeyboardMarkup(buttons), details.get('image_url')

def format_episode_details(details: dict, user_id: int) -> tuple[str, InlineKeyboardMarkup, str | None]:
    """Formats episode details, focusing on quality selection."""
    text = f"🎬 **{details.get('title', 'N/A')}**\n\n"
    text += "Select quality to download:\n" # Changed text slightly

    buttons = []
    if details.get('download_options'):
        quality_buttons = []
        for quality, data in details['download_options'].items():
            size_str = f" ({data['size']})" if data['size'] != "N/A" else ""
            # Append go_link_id
            quality_callback = f"quality_{data['go_link_id']}"
            quality_buttons.append(
                InlineKeyboardButton(f"💾 {quality}{size_str}", callback_data=quality_callback)
            )
        for i in range(0, len(quality_buttons), 2):
             buttons.append(quality_buttons[i:i+2])
    else:
        buttons.append([InlineKeyboardButton("⚠️ No Download Links Found", callback_data="no_links")])

    # Add Back button to episode list
    stored_context_id = user_states.get(user_id, {}).get('current_view_context')
    stored_ep_index = user_states.get(user_id, {}).get('current_episode_index_viewed') # Need to store this index
    if stored_context_id and stored_ep_index is not None:
        # Calculate which page this episode was on
        episode_page = math.ceil((stored_ep_index + 1) / EPISODES_PER_PAGE)
        back_callback = f"epspage_{stored_context_id}_{episode_page}"
        buttons.append([InlineKeyboardButton("🔙 Back to Episodes", callback_data=back_callback)])

    return text, InlineKeyboardMarkup(buttons), None

# --- Progress Callback (Unchanged) ---
async def progress_callback(current, total, message: Message, task_name: str, start_time: float):
    """Updates the message with progress information."""
    global last_update_time
    now = time.time()
    message_identifier = message.id

    if message_identifier not in last_update_time:
        last_update_time[message_identifier] = 0

    if now - last_update_time[message_identifier] < PROGRESS_UPDATE_INTERVAL:
        return
    last_update_time[message_identifier] = now

    try:
        percentage = current * 100 / total if total > 0 else 0
        speed = current / (now - start_time) if (now - start_time) > 0 else 0
        elapsed_time = now - start_time

        bar_length = 10
        filled_length = int(bar_length * current // total) if total > 0 else 0
        bar = '█' * filled_length + ' ' * (bar_length - filled_length)

        progress_text = (
            f"**{task_name}**\n"
            f"[{bar}] {percentage:.1f}%\n"
            f"{format_size(current)} / {format_size(total)}\n"
            # f"Speed: {format_size(speed)}/s\n"
            f"Elapsed: {time.strftime('%H:%M:%S', time.gmtime(elapsed_time))}\n"
        )

        await message.edit_text(progress_text)

    except MessageNotModified:
        pass
    except FloodWait as e:
        logger.warning(f"Flood wait of {e.value} seconds during progress update.")
        await asyncio.sleep(e.value)
    except MessageIdInvalid:
        logger.warning(f"Progress update failed: Message {message_identifier} not found (likely deleted).")
        # Remove from tracking if message is invalid
        if message_identifier in last_update_time:
             del last_update_time[message_identifier]
    except Exception as e:
        logger.exception(f"Error in progress callback for message {message_identifier}: {e}")

last_update_time = {}

# --- Bot Handlers (Main Logic) ---

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    """Handles the /start command."""
    user_id = message.from_user.id
    logger.info(f"Received /start command from user {user_id}")
    welcome_text = (
        f"Welcome to the Akwam Bot!\n\n"
        f"Use me to search for movies and series on {AKWAM_BASE_URL}.\n"
        f"Simply send me the name of the movie or series you're looking for.\n\n"
        f"Downloads are saved to `{DOWNLOAD_PATH}` temporarily.\n"
        f"Max concurrent downloads: {MAX_CONCURRENT_DOWNLOADS}."
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("❓ Help", callback_data="help")]])
    await message.reply_text(welcome_text, reply_markup=keyboard, disable_web_page_preview=True)
    if user_id in user_states:
        del user_states[user_id]
    user_states[user_id] = {} # Initialize state

@app.on_message(filters.private & filters.text & ~filters.command("start"))
async def search_handler(client: Client, message: Message):
    """Handles text messages as search queries."""
    query = message.text.strip()
    user_id = message.from_user.id
    logger.info(f"Received search query: '{query}' from user {user_id}")

    if not query:
        await message.reply_text("Please enter a movie or series name to search.")
        return

    status_message = await message.reply_text(f"🔎 Searching for \"**{query}**\"...")

    search_url = AKWAM_SEARCH_URL.format(query=quote_plus(query))
    response = await make_request(search_url)

    if not response or not response.content:
        await status_message.edit_text("❌ Error fetching search results. The website might be down or blocking requests.")
        return

    results = parse_search_results(response.text)

    if not results:
        await status_message.edit_text(f"😕 No results found for \"**{query}**\". Try a different name.")
        return

    # Ensure user state exists
    if user_id not in user_states:
        user_states[user_id] = {}
    user_states[user_id]["last_search_results"] = results
    user_states[user_id]["last_query"] = query

    total_results = len(results)
    total_pages = math.ceil(total_results / MAX_RESULTS_PER_PAGE)
    current_page = 1

    text, keyboard = format_search_results_page(results, current_page, total_pages, query)

    try:
        await status_message.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
    except MessageNotModified:
         pass
    except Exception as e:
         logger.exception("Error sending search results")
         await status_message.edit_text("❌ An error occurred while displaying search results.")


@app.on_callback_query()
async def callback_handler(client: Client, callback_query: CallbackQuery):
    """Handles all inline button presses."""
    data = callback_query.data
    message = callback_query.message
    user_id = callback_query.from_user.id
    logger.info(f"Callback query received: '{data}' from user {user_id}")

    if user_id not in user_states:
         user_states[user_id] = {}

    try:
        # --- Search Pagination ---
        if data.startswith("searchpage_"):
            parts = data.split("_")
            page = int(parts[-1])
            query_encoded = "_".join(parts[1:-1])

            stored_query = user_states.get(user_id, {}).get("last_query")
            if not stored_query or "last_search_results" not in user_states.get(user_id, {}):
                await callback_query.answer("Search results expired. Please search again.", show_alert=True)
                try: await message.delete()
                except: pass
                return

            logger.info(f"Handling search pagination: Query='{stored_query}', Page={page}")

            results = user_states[user_id]["last_search_results"]
            total_results = len(results)
            total_pages = math.ceil(total_results / MAX_RESULTS_PER_PAGE)

            if not 1 <= page <= total_pages:
                 await callback_query.answer("Invalid page number.", show_alert=True)
                 return

            text, keyboard = format_search_results_page(results, page, total_pages, stored_query)
            await message.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
            await callback_query.answer()

        # --- View Details (Movie/Series) ---
        elif data.startswith("view_"):
            parts = data.split("_")
            result_index = int(parts[1])
            query_encoded = "_".join(parts[2:])

            stored_query = user_states.get(user_id, {}).get("last_query")
            if not stored_query or "last_search_results" not in user_states.get(user_id, {}):
                await callback_query.answer("Result data expired. Please search again.", show_alert=True)
                return

            logger.info(f"Handling view details: Index={result_index}, Query='{stored_query}'")

            results = user_states[user_id]["last_search_results"]
            if not 0 <= result_index < len(results):
                 await callback_query.answer("Invalid result selected.", show_alert=True)
                 return

            selected_item = results[result_index]
            item_link = selected_item['link']
            item_type = selected_item['type']

            view_context_id = f"{result_index}_{hash(item_link)%10000}"
            user_states[user_id]['current_view_context'] = view_context_id
            user_states[user_id]['current_item_index_viewed'] = result_index # Store index for back button context
            logger.info(f"Set view context ID: {view_context_id}")


            await callback_query.answer(f"Fetching details for {selected_item['title']}...")
            try:
                 await message.delete()
            except: pass # Ignore if deletion fails
            status_message = await client.send_message(user_id, f"⏳ Fetching details for **{selected_item['title']}**...")

            response = await make_request(item_link)
            if not response or not response.content:
                await status_message.edit_text("❌ Error fetching details.")
                return

            details = None
            text = "❌ Error parsing details."
            keyboard = None
            image_url = selected_item.get('image_url')

            details_parsed_ok = False
            if item_type == "movie":
                details = parse_movie_details(response.text)
                if details:
                    text, keyboard, image_url_detail = format_movie_details(details)
                    image_url = image_url_detail or image_url
                    user_states[user_id]['current_details'] = details
                    user_states[user_id]['current_item_link'] = item_link # Store link
                    details_parsed_ok = True
            elif item_type == "series":
                details = parse_series_details(response.text)
                if details:
                    text, keyboard, image_url_detail = format_series_details(details, user_id, episode_page=1)
                    image_url = image_url_detail or image_url
                    user_states[user_id]['current_details'] = details
                    user_states[user_id]['current_item_link'] = item_link # Store link
                    details_parsed_ok = True

            if not details_parsed_ok:
                 text = "❌ Error parsing details."
                 keyboard = None

            # Send result
            try:
                await status_message.delete()
                if image_url:
                    await client.send_photo(
                        chat_id=user_id, photo=image_url, caption=text,
                        reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN
                    )
                else:
                     await client.send_message(
                        chat_id=user_id, text=text, reply_markup=keyboard,
                        disable_web_page_preview=True, parse_mode=enums.ParseMode.MARKDOWN
                     )
            except Exception as send_err:
                 logger.warning(f"Failed to send details (photo: {bool(image_url)}): {send_err}. Sending text fallback.")
                 try:
                    # Ensure status_message exists before trying to edit
                    await client.edit_message_text(user_id, status_message.id, text, reply_markup=keyboard,
                                               disable_web_page_preview=True, parse_mode=enums.ParseMode.MARKDOWN)
                 except: # Fallback: send new message if edit fails
                      await client.send_message(user_id, text, reply_markup=keyboard,
                                               disable_web_page_preview=True, parse_mode=enums.ParseMode.MARKDOWN)


        # --- Episode Pagination ---
        elif data.startswith("epspage_"):
            parts = data.split("_")
            page = int(parts[-1])
            context_id_from_callback = "_".join(parts[1:-1])

            stored_context_id = user_states.get(user_id, {}).get('current_view_context')
            if not stored_context_id or context_id_from_callback != stored_context_id:
                 await callback_query.answer("Episode list context mismatch or expired.", show_alert=True)
                 return

            logger.info(f"Handling episode pagination: Context='{stored_context_id}', Page={page}")

            details = user_states.get(user_id, {}).get('current_details')
            if not details or "episodes" not in details:
                await callback_query.answer("Series data expired.", show_alert=True)
                return

            total_episodes = len(details.get('episodes', []))
            total_episode_pages = math.ceil(total_episodes / EPISODES_PER_PAGE)

            if not 1 <= page <= total_episode_pages:
                 await callback_query.answer("Invalid episode page.", show_alert=True)
                 return

            try:
                text, keyboard, _ = format_series_details(details, user_id, episode_page=page)
                if message.photo:
                    await message.edit_caption(caption=text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
                else:
                    await message.edit_text(text=text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN, disable_web_page_preview=True)
                await callback_query.answer(f"Page {page}")
            except MessageNotModified:
                await callback_query.answer()
            except Exception as e:
                logger.error(f"Error editing message for episode pagination: {e}")
                await callback_query.answer("Error updating page.", show_alert=True)


        # --- View Episode Details ---
        elif data.startswith("episode_"):
            global_episode_index = int(data.split("_")[1])
            logger.info(f"Handling view episode: Global Index={global_episode_index}")

            current_details = user_states.get(user_id, {}).get('current_details')
            if not current_details or "episodes" not in current_details:
                await callback_query.answer("Series/Episode data expired.", show_alert=True)
                return

            episodes = current_details['episodes']
            if not 0 <= global_episode_index < len(episodes):
                 await callback_query.answer("Invalid episode selected.", show_alert=True)
                 return

            selected_episode = episodes[global_episode_index]
            episode_link = selected_episode['link']
            episode_title = selected_episode['title']
            user_states[user_id]['current_episode_index_viewed'] = global_episode_index # Store for back button

            await callback_query.answer(f"Fetching details for {episode_title}...")
            try: await message.delete()
            except: pass
            status_message = await client.send_message(user_id, f"⏳ Fetching details for **{episode_title}**...")

            response = await make_request(episode_link)
            if not response or not response.content:
                await status_message.edit_text("❌ Error fetching episode details.")
                return

            episode_dl_details = parse_episode_details(response.text)
            if episode_dl_details:
                 # Add episode title to details for clarity if needed elsewhere
                 episode_dl_details['full_title'] = episode_title
                 user_states[user_id]['current_episode_details'] = episode_dl_details # Store episode download options

                 text, keyboard, _ = format_episode_details(episode_dl_details, user_id)
                 await status_message.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
            else:
                 await status_message.edit_text("❌ Error parsing episode download options.")


        # --- Select Quality & Start Download --- <<< MODIFIED SIGNIFICANTLY
        elif data.startswith("quality_"):
            go_link_id = data.split("_")[1]
            logger.info(f"Handling quality selection: GoLinkID={go_link_id}")

            # --- Check Concurrency Limit ---
            if len(active_downloads) >= MAX_CONCURRENT_DOWNLOADS:
                 await callback_query.answer(f"⚠️ Download limit ({MAX_CONCURRENT_DOWNLOADS}) reached. Please wait for active downloads to finish.", show_alert=True)
                 return

            # --- Get Item Details for Caption/Filename ---
            # Determine if it's a movie or episode from the state
            item_details = None
            current_ep_details = user_states.get(user_id, {}).get('current_episode_details')
            current_main_details = user_states.get(user_id, {}).get('current_details')

            if current_ep_details and current_ep_details.get('download_options') and any(d['go_link_id'] == go_link_id for d in current_ep_details['download_options'].values()):
                 # It's likely an episode quality selection
                 item_details = {
                     'title': current_ep_details.get('full_title', 'Episode'), # Use full title if stored
                     'image_url': current_main_details.get('image_url') if current_main_details else None,
                     # Add other relevant details if needed from current_main_details or current_ep_details
                 }
                 # Find the selected quality name and size
                 selected_quality = next((q for q, d in current_ep_details['download_options'].items() if d['go_link_id'] == go_link_id), None)
                 if selected_quality: item_details['quality'] = selected_quality

            elif current_main_details and current_main_details.get('download_options') and any(d['go_link_id'] == go_link_id for d in current_main_details['download_options'].values()):
                  # It's likely a movie quality selection
                  item_details = current_main_details # Use the main movie details
                  selected_quality = next((q for q, d in current_main_details['download_options'].items() if d['go_link_id'] == go_link_id), None)
                  if selected_quality: item_details['quality'] = selected_quality
            else:
                  logger.warning(f"Could not determine context (movie/episode) for go_link_id {go_link_id}. Using generic title.")
                  item_details = {'title': f'Download_{go_link_id}'} # Fallback title

            item_title_for_status = item_details.get('title', 'File')[:50]

            await callback_query.answer("⏳ Preparing download...", show_alert=False)
            # Edit the quality selection message to show link extraction steps
            # *** DO NOT DELETE the message with buttons ***
            status_message = await message.edit_text(f"**Step 1/3:** Accessing gateway link for *{item_title_for_status}*...", reply_markup=None) # Remove buttons from *this* message

            go_link = f"http://go.ak.sv/link/{go_link_id}"

            # --- Step 1: Go.ak.sv -> ak.sv/download ---
            go_response = await make_request(go_link)
            if not go_response or not go_response.content:
                await status_message.edit_text(f"❌ Error accessing gateway link (go.ak.sv) for *{item_title_for_status}*.")
                return # Stop here

            ak_download_link = parse_go_link_page(go_response.text)
            if not ak_download_link:
                debug_html = go_response.text[:500] if go_response.text else "Empty response"
                logger.error(f"Failed to parse go.ak.sv page. HTML start: {debug_html}")
                await status_message.edit_text(f"❌ Error parsing gateway page for *{item_title_for_status}*.")
                return # Stop here

            await status_message.edit_text(f"**Step 2/3:** Accessing download page for *{item_title_for_status}*...")
            logger.info(f"Intermediate download link: {ak_download_link}")

            # --- Step 2: ak.sv/download -> Direct Link Page ---
            download_page_response = await make_request(ak_download_link)
            if not download_page_response or not download_page_response.content:
                await status_message.edit_text(f"❌ Error accessing final download page for *{item_title_for_status}*.")
                return # Stop here

            # --- Step 3: Parse Direct Link (Handle Potential Delay) ---
            await status_message.edit_text(f"**Step 3/3:** Parsing final link for *{item_title_for_status}*...")
            direct_link = parse_download_page(download_page_response.text)

            js_delay_wait_seconds = 7
            if direct_link == "js_delay_detected":
                 logger.info(f"JS delay detected. Waiting {js_delay_wait_seconds}s before re-checking {ak_download_link}...")
                 await status_message.edit_text(f"**Step 3/3:** Detected delay for *{item_title_for_status}*. Waiting {js_delay_wait_seconds}s...")
                 await asyncio.sleep(js_delay_wait_seconds)
                 logger.info(f"Re-requesting {ak_download_link} after delay...")
                 download_page_response_retry = await make_request(ak_download_link)
                 if download_page_response_retry and download_page_response_retry.content:
                     direct_link = parse_download_page(download_page_response_retry.text)
                     if direct_link == "js_delay_detected":
                          logger.warning("Still detected JS delay after waiting. Parsing likely failed.")
                          direct_link = None
                 else:
                     logger.error("Failed to re-request download page after delay.")
                     direct_link = None

            if not direct_link or direct_link == "js_delay_detected":
                 debug_html_dl = download_page_response.text[:500] if download_page_response.text else "Empty response"
                 logger.error(f"Failed to parse final download page. HTML start: {debug_html_dl}")
                 await status_message.edit_text(f"❌ Error parsing final download page for *{item_title_for_status}*. Link not found.")
                 return # Stop here

            await status_message.edit_text(f"✅ Link Found for *{item_title_for_status}*. Adding to download queue...")
            logger.info(f"Direct download link extracted: {direct_link}")

            # --- Add to Queue and Start Download Task ---
            download_id = str(uuid.uuid4()) # Unique ID for this download task
            active_downloads.add(download_id)
            logger.info(f"Added download {download_id} to active set. Total active: {len(active_downloads)}")

            # Send a *new* message that will be used for download progress
            dl_status_msg = await client.send_message(
                chat_id=user_id,
                text=f"⏳ Queued: **{item_title_for_status}**..."
            )

            # Delete the "Step 3/3..." message now that queue message is sent
            try:
                await status_message.delete()
            except: pass

            # Start the download in the background
            asyncio.create_task(download_and_send_video_wrapper(
                client=client,
                user_id=user_id,
                url=direct_link,
                item_details=item_details.copy(), # Pass a copy
                progress_msg=dl_status_msg,
                download_id=download_id
            ))

        # --- Other Callbacks ---
        elif data == "help":
            await callback_query.answer("Send me a movie/series name to search.\nUse /start to reset.", show_alert=True)
        elif data == "no_links":
            await callback_query.answer("No download links were found for this item/quality.", show_alert=True)
        else:
            logger.warning(f"Unhandled callback data: {data}")
            await callback_query.answer("Action not recognized.", show_alert=True) # Keep it brief

    except MessageNotModified:
        logger.debug("Message not modified, skipping edit.")
        try: await callback_query.answer()
        except: pass
    except FloodWait as e:
        logger.warning(f"Flood wait triggered: {e.value} seconds. Sleeping.")
        await asyncio.sleep(e.value)
    except MessageIdInvalid:
         logger.warning("Callback failed: Original message ID invalid (likely deleted).")
         try: await callback_query.answer("Message not found.", show_alert=True)
         except: pass
    except Exception as e:
        logger.exception(f"Error handling callback query data '{data}': {e}")
        try:
            if "MESSAGE_ID_INVALID" not in str(e):
                 await callback_query.answer("An error occurred.", show_alert=True)
            else: await callback_query.answer()
        except: pass


# --- Download Wrapper for Concurrency ---
async def download_and_send_video_wrapper(client: Client, user_id: int, url: str, item_details: dict, progress_msg: Message, download_id: str):
    """Acquires semaphore and calls the main download function."""
    try:
        logger.info(f"Waiting for semaphore for download {download_id}...")
        async with download_semaphore:
            logger.info(f"Semaphore acquired for download {download_id}. Starting download...")
            await download_and_send_video(client, user_id, url, item_details, progress_msg)
    except Exception as e:
        logger.exception(f"Error in download wrapper for {download_id}: {e}")
        try:
            # Try to inform user about the failure via the progress message
             await progress_msg.edit_text(f"❌ Critical error occurred during download setup for **{item_details.get('title', 'File')}**.")
        except:
             pass # Ignore if editing fails
    finally:
        # Ensure the download ID is removed from the active set
        if download_id in active_downloads:
            active_downloads.remove(download_id)
            logger.info(f"Removed download {download_id} from active set. Total active: {len(active_downloads)}")

# --- Helper: Download and Send Video (Core Logic) ---
async def download_and_send_video(client: Client, user_id: int, url: str, item_details: dict, progress_msg: Message):
    """Downloads video from URL and sends it to Telegram with progress.
       Uses progress_msg for updates and deletes it on completion/error.
       Downloads to DOWNLOAD_PATH.
    """
    global last_update_time
    start_time = time.time()
    message_identifier = progress_msg.id # Use progress message ID for tracking its updates
    last_update_time[message_identifier] = start_time

    item_title = item_details.get('title', 'Unknown File')

    # --- Prepare File Path ---
    file_path = None
    thumb_path = None
    try:
        parsed_path = urlparse(url).path
        base_name = parsed_path.split('/')[-1] if parsed_path else f"video_{int(time.time())}"
        safe_base_name = re.sub(r'[\\/*?:"<>|]', "", base_name)
        # Add quality to filename if available
        quality_tag = item_details.get('quality')
        if quality_tag:
             name_part, ext_part = os.path.splitext(safe_base_name)
             safe_base_name = f"{name_part}_{quality_tag}{ext_part}"

        if not any(safe_base_name.lower().endswith(ext) for ext in ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.zip', '.rar']):
            safe_base_name += ".mp4" # Default extension

        file_path = os.path.join(DOWNLOAD_PATH, safe_base_name)
        logger.info(f"Download path set to: {file_path}")

        # Ensure target directory exists (handle potential permission errors)
        try:
            os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        except OSError as e:
             logger.error(f"Failed to create download directory {DOWNLOAD_PATH}: {e}")
             await progress_msg.edit_text(f"❌ Download Error: Cannot create directory `{DOWNLOAD_PATH}`. Check permissions.")
             return

        await progress_msg.edit_text(f"📥 Starting download: **{item_title}**...")
        downloaded_size = 0
        total_size = 0

        # --- Download ---
        # Use a separate client for long downloads? Maybe not necessary yet.
        async with http_client.stream("GET", url, timeout=None, follow_redirects=True) as response:
            if response.status_code >= 400:
                 logger.error(f"HTTP error {response.status_code} downloading {url}")
                 err_text = response.text[:200] if response.text else ""
                 await progress_msg.edit_text(f"❌ Download failed (HTTP {response.status_code}) for **{item_title}**.\n`{err_text}`")
                 return

            total_size = int(response.headers.get('content-length', 0))
            logger.info(f"Downloading {file_path} ({format_size(total_size)})")

            # Check available disk space (basic check, might not be accurate on all systems)
            try:
                statvfs = os.statvfs(DOWNLOAD_PATH)
                available_space = statvfs.f_frsize * statvfs.f_bavail
                if total_size > 0 and available_space < total_size * 1.05: # Add 5% buffer
                     logger.warning(f"Insufficient disk space in {DOWNLOAD_PATH}. Available: {format_size(available_space)}, Needed: {format_size(total_size)}")
                     await progress_msg.edit_text(f"❌ Download Error: Insufficient disk space in `{DOWNLOAD_PATH}` for **{item_title}**.")
                     return
            except Exception as disk_err:
                 logger.warning(f"Could not check disk space for {DOWNLOAD_PATH}: {disk_err}")


            with open(file_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=1024*1024): # 1MB chunks
                    if not chunk: break
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    if total_size > 0:
                         await progress_callback(downloaded_size, total_size, progress_msg, f"Downloading: {item_title[:20]}...", start_time)

        if downloaded_size == 0: # Check if file is empty
             # Try reading link headers if content-length was 0
             final_url = str(response.url)
             async with httpx.AsyncClient(timeout=15.0) as head_client:
                 try:
                    head_res = await head_client.head(final_url, follow_redirects=True)
                    real_size = int(head_res.headers.get('content-length', 0))
                    if real_size > 0:
                        logger.warning(f"Downloaded 0 bytes but HEAD request shows size {format_size(real_size)}. Link might be problematic.")
                        await progress_msg.edit_text(f"⚠️ Download Warning: Received 0 bytes for **{item_title}**. The link might be faulty or require browser access.")
                        # Keep file for inspection? Or delete? Let's delete.
                        if os.path.exists(file_path): os.remove(file_path)
                        return
                 except Exception as head_err:
                     logger.warning(f"HEAD request failed for {final_url}: {head_err}")

             logger.error(f"Download resulted in empty file for {url}. Link might be faulty.")
             await progress_msg.edit_text(f"❌ Download failed (empty file received) for **{item_title}**. Link may be faulty.")
             if os.path.exists(file_path): os.remove(file_path) # Clean up empty file
             return

        logger.info(f"Download complete: {file_path} ({format_size(downloaded_size)})")
        await progress_msg.edit_text(f"⬆️ Uploading: **{item_title}** ({format_size(downloaded_size)})...")

        # --- Upload ---
        start_time = time.time() # Reset for upload
        last_update_time[message_identifier] = start_time

        caption = f"**{item_title}**\n"
        if item_details.get('year'): caption += f"Year: {item_details['year']}\n"
        if item_details.get('rating'): caption += f"Rating: {item_details['rating']}/10\n"
        if item_details.get('quality'): caption += f"Quality: {item_details['quality']}\n"
        caption = caption[:1020]

        thumbnail_url = item_details.get('image_url')
        if thumbnail_url:
             try:
                 logger.info(f"Downloading thumbnail: {thumbnail_url}")
                 async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as thumb_client:
                     thumb_res = await thumb_client.get(thumbnail_url)
                     thumb_res.raise_for_status()
                     if thumb_res.content:
                         thumb_path = os.path.join(DOWNLOAD_PATH, f"thumb_{message_identifier}.jpg") # Save thumb in tmp too
                         with open(thumb_path, "wb") as tf:
                             tf.write(thumb_res.content)
                         logger.info(f"Thumbnail saved: {thumb_path}")
                     else: thumb_path = None
             except Exception as thumb_err:
                 logger.warning(f"Failed to download thumbnail: {thumb_err}")
                 thumb_path = None

        logger.info(f"Starting upload of {file_path}")
        await client.send_video(
            chat_id=user_id,
            video=file_path,
            caption=caption,
            thumb=thumb_path,
            supports_streaming=True,
            progress=progress_callback,
            progress_args=(progress_msg, f"Uploading: {item_title[:20]}...", start_time)
        )
        logger.info(f"Video uploaded successfully: {safe_base_name}")
        await progress_msg.delete() # Clean up status message *after* successful upload

    except httpx.HTTPStatusError as e:
         logger.error(f"HTTP error {e.response.status_code} during download stream: {e}")
         try: await progress_msg.edit_text(f"❌ Download failed (HTTP {e.response.status_code}) for **{item_title}**.")
         except: pass
    except httpx.RequestError as e:
         logger.error(f"Request error during download stream: {e}")
         try: await progress_msg.edit_text(f"❌ Download failed (Connection error) for **{item_title}**.")
         except: pass
    except OSError as e:
         logger.error(f"File system error during download/upload: {e}")
         try: await progress_msg.edit_text(f"❌ File System Error for **{item_title}**: {e.strerror}. Check disk space/permissions in `{DOWNLOAD_PATH}`.")
         except: pass
    except Exception as e:
        logger.exception(f"Error during download/upload for {item_title}: {e}")
        try: await progress_msg.edit_text(f"❌ An error occurred during download/upload for **{item_title}**.")
        except: pass # Ignore if editing fails
    finally:
        # --- Cleanup ---
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Cleaned up video file: {file_path}")
            if thumb_path and os.path.exists(thumb_path):
                 os.remove(thumb_path)
                 logger.debug(f"Cleaned up thumbnail file: {thumb_path}")
        except OSError as e:
             logger.error(f"Error cleaning up file: {e}")
        # Clean up progress tracking state
        if message_identifier in last_update_time:
             try: del last_update_time[message_identifier]
             except KeyError: pass


# --- Main Execution ---
if __name__ == "__main__":
    logger.info("Bot starting...")
    # --- Ensure download directory exists ---
    try:
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        logger.info(f"Download directory set to: {DOWNLOAD_PATH}")
        # Basic write test
        test_file = os.path.join(DOWNLOAD_PATH, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        logger.info(f"Write access to {DOWNLOAD_PATH} confirmed.")
    except OSError as e:
        logger.error(f"CRITICAL ERROR: Failed to create or write to download directory {DOWNLOAD_PATH}: {e}")
        logger.error("Downloads will fail. Please check directory permissions and path validity.")
        # Optionally exit if directory is essential
        # exit(1)
    except Exception as e:
         logger.error(f"CRITICAL ERROR: Unexpected error checking download directory {DOWNLOAD_PATH}: {e}")
         # exit(1)


    # Run the bot
    try:
        app.run()
    except Exception as e:
        logger.exception(f"Bot crashed: {e}")
    finally:
        logger.info("Bot stopped.")
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                 # Schedule client close on the running loop
                 loop.create_task(http_client.aclose())
                 # Give it a moment to process
                 # loop.run_until_complete(asyncio.sleep(0.1)) # May not work reliably in finally
            else:
                 asyncio.run(http_client.aclose())
            logger.info("HTTP client closed.")
        except Exception as ce:
             logger.error(f"Error closing HTTP client: {ce}")
