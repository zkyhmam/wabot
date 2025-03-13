from typing import Dict, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

poster_cache: Dict[int, str] = {}
media_data: Dict[str, Dict[str, Any]] = {}
user_states: Dict[str, Dict[str, Any]] = {}

async def get_cached_image_url(media_id: int) -> str | None:
    return poster_cache.get(media_id)

async def cache_image_url(media_id: int, image_url: str):
    poster_cache[media_id] = image_url

async def get_media_data(media_id: str) -> Dict[str, Any] | None:
    data = media_data.get(media_id)
    if data and datetime.fromisoformat(data['expiry']) > datetime.now():
        return data
    return None

async def set_media_data(media_id: str, data: Dict[str, Any]):
    data['expiry'] = (datetime.now() + timedelta(hours=24)).isoformat()
    media_data[media_id] = data

async def clear_media_data(media_id: str):
    if media_id in media_data:
        del media_data[media_id]

async def get_user_state(user_id: str) -> Dict[str, Any] | None:
    return user_states.get(user_id)

async def set_user_state(user_id: str, state: Dict[str, Any]):
    user_states[user_id] = state

async def clear_user_state(user_id: str):
    if user_id in user_states:
        del user_states[user_id]
