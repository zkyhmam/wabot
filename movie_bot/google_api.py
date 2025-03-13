import aiohttp
from typing import Dict, Any
from config import config
import random
import logging

logger = logging.getLogger(__name__)

async def get_image_url(media_data: Dict[str, Any], session: aiohttp.ClientSession) -> str:
    media_id = media_data.get('id')
    #  لا حاجة للتحقق من التخزين المؤقت هنا، سيتم في data.py
    try:
        if media_data.get('backdrop_path'):
            return f"{config.TMDB_IMAGE_BASE_URL}{media_data['backdrop_path']}"

        if media_data.get('poster_path'):
            return f"{config.TMDB_IMAGE_BASE_URL}{media_data['poster_path']}"

        media_title = media_data.get('title') or media_data.get('name', '')
        media_year = ""

        if media_data.get('release_date'):
            media_year = media_data['release_date'][:4]
        elif media_data.get('first_air_date'):
            media_year = media_data['first_air_date'][:4]

        search_query = f"{media_title} {media_year} movie poster 16:9"

        params = {
            'key': config.GOOGLE_API_KEY,
            'cx': config.GOOGLE_CSE_ID,
            'q': search_query,
            'searchType': 'image',
            'imgSize': 'large',
            'imgType': 'photo',
            'num': 1
        }

        async with session.get(config.GOOGLE_SEARCH_URL, params=params) as response:
            if response.status == 200:
                data = await response.json()
                items = data.get('items', [])
                if items:
                    return items[0]['link']

    except Exception as e:
        logger.error(f"خطأ في الحصول على صورة: {e}")

    if media_data.get('poster_path'):
        return f"{config.TMDB_IMAGE_BASE_URL}{media_data['poster_path']}"

    return "https://via.placeholder.com/1280x720?text=No+Image+Available"

async def search_another_image(media_data: Dict[str, Any], session: aiohttp.ClientSession) -> str:
    try:
        media_title = media_data.get('title') or media_data.get('name', '')
        media_year = ""

        if media_data.get('release_date'):
            media_year = media_data['release_date'][:4]
        elif media_data.get('first_air_date'):
            media_year = media_data['first_air_date'][:4]

        search_query = f"{media_title} {media_year} movie poster 16:9"
        random_offset = random.randint(1, 10)

        params = {
            'key': config.GOOGLE_API_KEY,
            'cx': config.GOOGLE_CSE_ID,
            'q': search_query,
            'searchType': 'image',
            'imgSize': 'large',
            'imgType': 'photo',
            'num': 1,
            'start': random_offset
        }

        async with session.get(config.GOOGLE_SEARCH_URL, params=params) as response:
            if response.status == 200:
                data = await response.json()
                items = data.get('items', [])
                if items:
                    return items[0]['link']
    except Exception as e:
        logger.error(f"خطأ في البحث عن صورة بديلة: {e}")
    
    if media_data.get('backdrop_path'):
            return f"{config.TMDB_IMAGE_BASE_URL}{media_data['backdrop_path']}"    
    if media_data.get('poster_path'):
        return f"{config.TMDB_IMAGE_BASE_URL}{media_data['poster_path']}"

    return "https://via.placeholder.com/1280x720?text=No+Image+Available"
