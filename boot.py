import os
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import asyncio

# إعداد التسجيل لتتبع الأخطاء والمعلومات
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# توكن البوت من BotFather (استبدله بالتوكن الخاص بك)
TOKEN = "7558529929:AAFmMHm2HuqHsdqdQvl_ZLCoXn5XOPiRzfw"

# قائمة المواقع التي سيتم البحث فيها مع روابط البحث والقاعدة
MOVIE_SITES = {
    "EgyDead": {
        "search_url": "https://egydead.space/search?s={}",
        "base_url": "https://egydead.space"
    },
    "WitAnime": {
        "search_url": "https://witanime.com/?search_param=animes&s={}",
        "base_url": "https://witanime.com"
    },
    "FilmDoo": {
        "search_url": "https://www.filmdoo.com/search?query={}",
        "base_url": "https://www.filmdoo.com"
    },
    "EgyBest": {
        "search_url": "https://i-egybest.com/search?s={}",
        "base_url": "https://i-egybest.com"
    }
}

# معالجة أمر /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إرسال رسالة ترحيب عند تشغيل البوت."""
    await update.message.reply_text(
        'مرحبًا! أنا بوت البحث عن الأفلام العربية. أرسل لي اسم فيلم أو مسلسل للبحث عنه.'
    )

# معالجة أمر /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إرسال تعليمات عند طلب المساعدة."""
    await update.message.reply_text('أرسل لي اسم فيلم أو مسلسل للبحث عنه في مواقع مختلفة.')

# دالة البحث في موقع واحد باستخدام Playwright
async def search_site(page, site, query):
    """البحث في موقع معين واستخراج النتائج."""
    results = []
    site_info = MOVIE_SITES[site]
    search_url = site_info["search_url"].format(query)
    
    try:
        # تحميل صفحة البحث
        await page.goto(search_url, wait_until="networkidle")
        logger.info(f"تم تحميل صفحة البحث بنجاح لـ {site}: {search_url}")
        
        # اختيار المحددات بناءً على الموقع
        if site == "EgyDead":
            movie_items = await page.query_selector_all('.movie-item')
        elif site == "WitAnime":
            movie_items = await page.query_selector_all('.anime-card')
        elif site == "FilmDoo":
            movie_items = await page.query_selector_all('.film-item')
        elif site == "EgyBest":
            movie_items = await page.query_selector_all('.movie-item')
        
        # استخراج العنوان والرابط من كل عنصر
        for item in movie_items:
            title_element = await item.query_selector('.movie-title, .anime-title, .title')
            link_element = await item.query_selector('a')
            
            if title_element and link_element:
                title = await title_element.inner_text()
                link = await link_element.get_attribute('href')
                if not link.startswith('http'):
                    link = site_info["base_url"] + link
                results.append({
                    "title": title.strip(),
                    "link": link,
                    "source": site
                })
                logger.info(f"تم العثور على: {title} من {site}")
    except PlaywrightTimeoutError:
        logger.error(f"انتهى وقت الانتظار أثناء تحميل {search_url}")
    except Exception as e:
        logger.error(f"خطأ أثناء البحث في {site}: {str(e)}")
    
    return results

# البحث في جميع المواقع
async def search_all_sites(query):
    """البحث في جميع المواقع المدعومة."""
    all_results = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        tasks = [search_site(page, site, query) for site in MOVIE_SITES]
        results = await asyncio.gather(*tasks)
        
        for site_results in results:
            all_results.extend(site_results)
        
        await browser.close()
    
    return all_results

# استخراج رابط الفيديو من صفحة العرض
async def extract_video_url(page, page_url, source):
    """استخراج رابط الفيديو من صفحة الفيلم."""
    try:
        await page.goto(page_url, wait_until="networkidle")
        logger.info(f"تم تحميل صفحة الفيلم: {page_url}")
        
        if source == "EgyDead":
            iframe = await page.query_selector('.video-player iframe')
            if iframe:
                return await iframe.get_attribute('src')
        elif source == "WitAnime":
            source_element = await page.query_selector('.video-player source')
            if source_element:
                return await source_element.get_attribute('src')
        elif source == "FilmDoo":
            source_element = await page.query_selector('.video-player source')
            if source_element:
                return await source_element.get_attribute('src')
        elif source == "EgyBest":
            iframe = await page.query_selector('iframe')
            if iframe:
                return await iframe.get_attribute('src')
            video = await page.query_selector('video source')
            if video:
                return await video.get_attribute('src')
    except PlaywrightTimeoutError:
        logger.error(f"انتهى وقت الانتظار أثناء تحميل {page_url}")
    except Exception as e:
        logger.error(f"خطأ في استخراج رابط الفيديو من {page_url}: {str(e)}")
    
    return None

# إرسال الفيديو للمستخدم
async def send_video_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE, video_url):
    """إرسال رابط الفيديو للمستخدم."""
    try:
        loading_message = await update.callback_query.message.reply_text("جاري تحميل الفيديو...")
        await update.callback_query.message.reply_video(
            video_url,
            caption="إليك الفيديو الذي طلبته!"
        )
        await loading_message.delete()
    except Exception as e:
        logger.error(f"خطأ في إرسال الفيديو: {str(e)}")
        await update.callback_query.message.reply_text(
            "عذرًا، لم أتمكن من إرسال الفيديو. حاول مرة أخرى."
        )

# معالجة استعلام البحث من المستخدم
async def search_movies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """البحث عن الأفلام بناءً على استعلام المستخدم."""
    query = update.message.text
    searching_message = await update.message.reply_text("جاري البحث...")
    
    results = await search_all_sites(query)
    
    if not results:
        await searching_message.edit_text("لم أجد أي نتائج لبحثك.")
        return
    
    keyboard = [
        [InlineKeyboardButton(f"{result['title']} ({result['source']})", callback_data=f"movie_{i}")]
        for i, result in enumerate(results[:10])  # حد أقصى 10 نتائج
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await searching_message.edit_text(
        f"وجدت {len(results)} نتيجة لـ '{query}':",
        reply_markup=reply_markup
    )
    context.user_data["search_results"] = results

# معالجة النقر على الأزرار
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """التعامل مع اختيار المستخدم من النتائج."""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("movie_"):
        index = int(query.data.split("_")[1])
        results = context.user_data.get("search_results", [])
        
        if 0 <= index < len(results):
            selected_movie = results[index]
            await query.edit_message_text(f"جاري تحميل {selected_movie['title']}...")
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                video_url = await extract_video_url(page, selected_movie['link'], selected_movie['source'])
                await browser.close()
            
            if video_url:
                await send_video_to_user(update, context, video_url)
            else:
                await query.edit_message_text(
                    f"عذرًا، لم أتمكن من العثور على رابط الفيديو لـ {selected_movie['title']}."
                )

# تشغيل البوت
def main() -> None:
    """الدالة الرئيسية لتشغيل البوت."""
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_movies))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    application.run_polling()

if __name__ == "__main__":
    main()
