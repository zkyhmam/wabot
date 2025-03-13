import os
from dotenv import load_dotenv
from typing import List, Dict, Any

load_dotenv()

class Config:
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
    TMDB_API_KEY: str = os.getenv("TMDB_API_KEY", "")
    TMDB_BEARER_TOKEN: str = os.getenv("TMDB_BEARER_TOKEN", "")
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    GOOGLE_CSE_ID: str = os.getenv("GOOGLE_CSE_ID", "")
    ADMIN_IDS: List[int] = [int(id) for id in os.getenv("ADMIN_IDS", "").split(',') if id.strip().isdigit()]
    DEVELOPER_USERNAME: str = os.getenv("DEVELOPER_USERNAME", "zaky1million")
    DEFAULT_START_IMAGE: str = os.getenv("DEFAULT_START_IMAGE", "https://i.imgur.com/dZcDEQL.jpeg")
    DEFAULT_START_MESSAGE: str = os.getenv("DEFAULT_START_MESSAGE",
        "👋 أهلاً بك في بوت الأفلام والمسلسلات!\n\n"
        "يمكنك استخدام هذا البوت للبحث عن معلومات حول أفلامك ومسلسلاتك المفضلة.\n\n"
        "🔍 ببساطة أرسل لي اسم الفيلم أو المسلسل وسأقوم بإيجاده لك.\n\n"
        "مثال: The Godfather أو الوحش"
    )
    TMDB_BASE_URL: str = "https://api.themoviedb.org/3"
    TMDB_IMAGE_BASE_URL: str = "https://image.tmdb.org/t/p/original"
    GOOGLE_SEARCH_URL: str = "https://www.googleapis.com/customsearch/v1"
    FORCED_CHANNELS: List[Dict[str, str]] = []  # تمت إضافة هذه

config = Config()
