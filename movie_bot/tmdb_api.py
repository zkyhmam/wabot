import aiohttp
from typing import Dict, Any
from config import config
import logging

logger = logging.getLogger(__name__)

async def search_tmdb(query: str, session: aiohttp.ClientSession) -> Dict:
    try:
        params = {
            'api_key': config.TMDB_API_KEY,
            'query': query,
            'language': 'ar-SA',
            'region': 'SA',  # أضف هذه
            'include_adult': 'false'
        }

        headers = {
            'Authorization': f'Bearer {config.TMDB_BEARER_TOKEN}',
            'Content-Type': 'application/json;charset=utf-8'
        }

        async with session.get(f"{config.TMDB_BASE_URL}/search/multi", params=params, headers=headers) as response:
            if response.status != 200:
                params['language'] = 'en-US'
                async with session.get(f"{config.TMDB_BASE_URL}/search/multi", params=params, headers=headers) as en_response:
                    return await en_response.json()
            return await response.json()

    except Exception as e:
        logger.error(f"خطأ في البحث في TMDB: {e}")
        return {"results": []}

async def get_media_details(media_id: int, media_type: str, session: aiohttp.ClientSession) -> Dict:
    try:
        params = {
            'api_key': config.TMDB_API_KEY,
            'language': 'ar-SA',
            'append_to_response': 'credits,videos,images'
        }

        headers = {
            'Authorization': f'Bearer {config.TMDB_BEARER_TOKEN}',
            'Content-Type': 'application/json;charset=utf-8'
        }

        async with session.get(f"{config.TMDB_BASE_URL}/{media_type}/{media_id}", params=params, headers=headers) as response:
            if response.status != 200:
                params['language'] = 'en-US'
                async with session.get(f"{config.TMDB_BASE_URL}/{media_type}/{media_id}", params=params, headers=headers) as en_response:
                    return await en_response.json()
            return await response.json()

    except Exception as e:
        logger.error(f"خطأ في الحصول على تفاصيل الوسائط: {e}")
        return {}
