import asyncio
import logging
from bot import MovieBot

# --- تكوين التسجيل ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

if __name__ == '__main__':
    bot = MovieBot()
    asyncio.run(bot.run())

