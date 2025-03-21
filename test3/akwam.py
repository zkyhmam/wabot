import logging
import asyncio
import aiohttp
import random
import re
from typing import List, Optional, Tuple, Dict
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote_plus
from dataclasses import dataclass

# إعداد التسجيل مع ألوان ANSI
class ColoredFormatter(logging.Formatter):
    COLORS = {
        'INFO': '\033[92m',    # أخضر
        'WARNING': '\033[93m', # أصفر
        'ERROR': '\033[91m',   # أحمر
        'CRITICAL': '\033[95m',# بنفسجي
        'DEBUG': '\033[94m',   # أزرق
        'NAME': '\033[38;5;208m', # برتقالي لـ AkwamScraper
        'MSG': '\033[96m',     # لبني (Light Cyan) للتعليمات
        'RESET': '\033[0m'     # إعادة تعيين
    }

    def format(self, record):
        log_message = super().format(record)
        color_level = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        color_name = self.COLORS['NAME']
        color_msg = self.COLORS['MSG']
        return f"{color_level}[{record.asctime}] {record.levelname:<8}{self.COLORS['RESET']} {color_name}{record.name}{self.COLORS['RESET']} - {color_msg}{record.message}{self.COLORS['RESET']}"

logger = logging.getLogger("AkwamScraper")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = ColoredFormatter(datefmt='%m/%d/%y %H:%M:%S')
handler.setFormatter(formatter)
logger.addHandler(handler)

# كلاسات البيانات
@dataclass
class AkwamSearchResult:
    title: str
    url: str
    thumbnail: Optional[str] = None
    year: Optional[int] = None
    type: Optional[str] = None

@dataclass
class AkwamQualityLink:
    resolution: str
    size: Optional[str]
    url: str
    server_name: str
    direct_url: Optional[str] = None

@dataclass
class AkwamVideoDetails:
    title: str
    url: str
    thumbnail: Optional[str] = None
    year: Optional[int] = None
    description: Optional[str] = None
    qualities: Optional[List[AkwamQualityLink]] = None

    def __post_init__(self):
        if self.qualities is None:
            self.qualities = []

# إعدادات وثوابت
class AkwamConfig:
    BASE_URL = "https://ak.sv/"
    SEARCH_PATH = "search"
    RETRY_COUNT = 3
    TIMEOUT = 20
    REQUEST_DELAY = (1, 3)
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
    ]
    HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
        "Referer": BASE_URL,
    }
    SELECTOR_RESULT_CARD = ['.entry-box', '.movie-card', '.item', '.entry', '.post']
    QUALITY_PATTERNS = [
        re.compile(r'(\d+)p', re.IGNORECASE),
        re.compile(r'(\d+\.\d+|\d+)\s*[GgMm][Bb]', re.IGNORECASE),
    ]
    TYPE_KEYWORDS = ['film', 'series', 'movie']

# عميل HTTP
class HttpClient:
    def __init__(self):
        self.session = None

    async def init_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()

    def _get_random_headers(self) -> Dict[str, str]:
        headers = AkwamConfig.HEADERS.copy()
        headers["User-Agent"] = random.choice(AkwamConfig.USER_AGENTS)
        return headers

    async def get(self, url: str, **kwargs) -> Tuple[int, str]:
        await self.init_session()
        headers = self._get_random_headers()
        kwargs.setdefault("headers", headers)
        kwargs.setdefault("timeout", aiohttp.ClientTimeout(total=AkwamConfig.TIMEOUT))

        delay = random.uniform(*AkwamConfig.REQUEST_DELAY)
        await asyncio.sleep(delay)

        for attempt in range(AkwamConfig.RETRY_COUNT):
            try:
                async with self.session.get(url, **kwargs) as response:
                    status = response.status
                    content = await response.text()
                    logger.info(f"GET request to {url[:100]} - Status: {status}")
                    if status == 200:
                        return status, content
                    logger.warning(f"Request failed (status {status}) - Attempt {attempt+1}")
                    await asyncio.sleep(random.uniform(1, 5))
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"Error in request to {url}: {str(e)} - Attempt {attempt+1}")
                await asyncio.sleep(random.uniform(2, 5))
        logger.error(f"All request attempts failed for {url}")
        return None, None

# محلل HTML
class HtmlParser:
    @staticmethod
    def _get_absolute_url(relative_url: str) -> Optional[str]:
        if not relative_url:
            return None
        if relative_url.startswith(('http://', 'https://')):
            return relative_url
        return urljoin(AkwamConfig.BASE_URL, relative_url)

    @staticmethod
    def _extract_text(element) -> Optional[str]:
        return element.get_text(strip=True) if element else None

    @staticmethod
    async def extract_search_results(html_content: str) -> List[AkwamSearchResult]:
        if not html_content:
            logger.warning("No HTML content to extract search results")
            return []

        soup = BeautifulSoup(html_content, 'html.parser')
        results = []

        cards = None
        for selector in AkwamConfig.SELECTOR_RESULT_CARD:
            cards = soup.select(selector)
            if cards:
                logger.info(f"Found {len(cards)} cards using selector: {selector}")
                break

        if not cards:
            logger.warning("No results found - No matching elements")
            logger.debug(f"Page preview: {html_content[:300]}...")
            return []

        logger.info(f"Found {len(cards)} potential results")
        for card in cards:
            try:
                link_elem = card.select_one('a')
                url = HtmlParser._get_absolute_url(link_elem.get('href')) if link_elem else None
                if not url or 'movie' not in url.lower():
                    continue

                title_elem = card.select_one('h2.entry-title a')
                title = HtmlParser._extract_text(title_elem) or url.split('/')[-1].replace('-', ' ').title()

                img_elem = card.select_one('img')
                thumbnail = HtmlParser._get_absolute_url(img_elem.get('src') or img_elem.get('data-src')) if img_elem else None

                year_match = re.search(r'(19|20)\d{2}', title or '')
                year = int(year_match.group()) if year_match else None

                type_text = None
                for keyword in AkwamConfig.TYPE_KEYWORDS:
                    if keyword.lower() in title.lower():
                        type_text = keyword
                        break

                results.append(AkwamSearchResult(
                    title=title,
                    url=url,
                    thumbnail=thumbnail,
                    year=year,
                    type=type_text
                ))
                logger.debug(f"Added result: {title} - {url}")
            except Exception as e:
                logger.error(f"Error while extracting card: {str(e)}")

        logger.info(f"Search completed: Found {len(results)} results")
        return results

    @staticmethod
    async def extract_video_details(html_content: str, url: str) -> Tuple[Optional[AkwamVideoDetails], Optional[str]]:
        if not html_content:
            logger.warning(f"No HTML content to extract details from {url}")
            return None, None

        soup = BeautifulSoup(html_content, 'html.parser')
        try:
            title_elem = soup.select_one('h1.title')
            title = HtmlParser._extract_text(title_elem) or "Unknown Title"

            img_elem = soup.select_one('.poster img')
            thumbnail = HtmlParser._get_absolute_url(img_elem.get('src') or img_elem.get('data-src')) if img_elem else None

            desc_elem = soup.select_one('.description')
            description = HtmlParser._extract_text(desc_elem)

            year_match = re.search(r'(19|20)\d{2}', title or description or '')
            year = int(year_match.group()) if year_match else None

            download_link = soup.find('a', href=lambda href: href and 'go.ak.sv/link' in href)
            download_url = HtmlParser._get_absolute_url(download_link.get('href')) if download_link else None

            details = AkwamVideoDetails(
                title=title,
                url=url,
                thumbnail=thumbnail,
                year=year,
                description=description
            )
            logger.info(f"Extracted video details: {title}")
            return details, download_url
        except Exception as e:
            logger.error(f"Error while extracting video details from {url}: {str(e)}")
            return None, None

    @staticmethod
    async def extract_quality_links(html_content: str, base_url: str) -> List[AkwamQualityLink]:
        if not html_content:
            logger.warning(f"No HTML content to extract links from {base_url}")
            return []

        soup = BeautifulSoup(html_content, 'html.parser')
        quality_links = []
        try:
            links = soup.find_all('a', href=lambda href: href and ('download' in href or '.mp4' in href))
            for link in links:
                url = HtmlParser._get_absolute_url(link.get('href'))
                text = HtmlParser._extract_text(link) or ""

                resolution = None
                size = None
                for pattern in AkwamConfig.QUALITY_PATTERNS:
                    if match := pattern.search(text):
                        if 'p' in match.group(0).lower():
                            resolution = match.group(0)
                        else:
                            size = match.group(0)

                # إذا لم يتم العثور على جودة أو حجم، استخدام قيم افتراضية بناءً على الرابط
                if not resolution:
                    resolution = "720p" if "720" in url else "1080p" if "1080" in url else "Unknown"
                if not size:
                    size = "Unknown"

                server_name = "Akwam Server"
                quality_links.append(AkwamQualityLink(
                    resolution=resolution,
                    size=size,
                    url=url,
                    server_name=server_name
                ))
                logger.debug(f"Added quality link: {resolution} - {size} - {url}")
            logger.info(f"Extracted {len(quality_links)} quality links")
            return quality_links
        except Exception as e:
            logger.error(f"Error while extracting links from {base_url}: {str(e)}")
            return []

    @staticmethod
    async def extract_direct_link(html_content: str, quality_url: str) -> Optional[str]:
        if not html_content:
            logger.warning(f"No HTML content to extract direct link from {quality_url}")
            return None

        soup = BeautifulSoup(html_content, 'html.parser')
        try:
            direct_link = soup.find('a', href=lambda href: href and href.endswith('.mp4'))
            if direct_link:
                direct_url = HtmlParser._get_absolute_url(direct_link.get('href'))
                logger.info(f"Extracted direct link: {direct_url}")
                return direct_url
            logger.warning(f"No direct link found in {quality_url}")
            return None
        except Exception as e:
            logger.error(f"Error while extracting direct link from {quality_url}: {str(e)}")
            return None

# دوال رئيسية
async def search_akwam(query: str) -> List[AkwamSearchResult]:
    client = HttpClient()
    search_url = f"{AkwamConfig.BASE_URL}{AkwamConfig.SEARCH_PATH}?q={quote_plus(query)}"
    status, content = await client.get(search_url)
    await client.close_session()

    if status == 200:
        return await HtmlParser.extract_search_results(content)
    logger.error(f"Search failed for '{query}' - Status: {status}")
    return []

async def get_video_details(search_result: AkwamSearchResult) -> Optional[AkwamVideoDetails]:
    client = HttpClient()
    status, content = await client.get(search_result.url)
    if status == 200:
        details, download_url = await HtmlParser.extract_video_details(content, search_result.url)
        if details and download_url:
            status, download_content = await client.get(download_url)
            if status == 200:
                details.qualities = await HtmlParser.extract_quality_links(download_content, download_url)
                for quality in details.qualities:
                    status, quality_content = await client.get(quality.url)
                    if status == 200:
                        direct_link = await HtmlParser.extract_direct_link(quality_content, quality.url)
                        quality.direct_url = direct_link
            await client.close_session()
            return details
        await client.close_session()
        return details
    logger.error(f"Failed to access details for '{search_result.title}' - Status: {status}")
    await client.close_session()
    return None

async def get_direct_download_link(quality: AkwamQualityLink) -> Optional[str]:
    if quality.direct_url:
        return quality.direct_url

    client = HttpClient()
    status, content = await client.get(quality.url)
    if status == 200:
        direct_link = await HtmlParser.extract_direct_link(content, quality.url)
        await client.close_session()
        return direct_link
    logger.warning(f"Failed to extract direct link for {quality.url} - Status: {status}")
    await client.close_session()
    return None
