import aiohttp
import logging
from config import TMDB_API_KEY, TMDB_BEARER_TOKEN

logger = logging.getLogger(__name__)

async def get_movie_info(query):
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {TMDB_BEARER_TOKEN}"}
        url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={query}"
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                logger.error(f"[red]Failed to fetch TMDb data: {response.status}[/red]")
                return None
            data = await response.json()
            if data["results"]:
                movie = data["results"][0]
                return {
                    "title": movie["title"],
                    "overview": movie["overview"],
                    "poster": f"https://image.tmdb.org/t/p/w500{movie['poster_path']}" if movie["poster_path"] else None
                }
            return None
