import os
import logging
from urllib.parse import urljoin
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import asyncio

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = "7558529929:AAFmMHm2HuqHsdqdQvl_ZLCoXn5XOPiRzfw"  # تأكد من صحة التوكن

MOVIE_SITES = {
    "EgyDead": {
        "search_url": "https://egydead.space/search?s={}",
        "base_url": "https://egydead.space",
        "selectors": {
            "items": ".movie-item",
            "title": "h2 a",
            "link": "h2 a"
        }
    },
    "WitAnime": {
        "search_url": "https://witanime.com/?search_param=animes&s={}",
        "base_url": "https://witanime.com",
        "selectors": {
            "items": ".anime-card",
            "title": ".anime-title",
            "link": "a"
        }
    }
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('مرحبًا! أرسل اسم فيلم أو مسلسل للبحث عنه.')

async def search_site(page, site, query):
    results = []
    site_config = MOVIE_SITES[site]
    try:
        url = site_config["search_url"].format(query)
        await page.goto(url, wait_until="networkidle", timeout=20000)
        
        # انتظار تحميل العناصر
        await page.wait_for_selector(site_config["selectors"]["items"], timeout=10000)
        
        items = await page.query_selector_all(site_config["selectors"]["items"])
        
        for item in items:
            try:
                title_element = await item.query_selector(site_config["selectors"]["title"])
                link_element = await item.query_selector(site_config["selectors"]["link"])
                
                title = await title_element.inner_text()
                link = await link_element.get_attribute("href")
                
                if not link.startswith("http"):
                    link = urljoin(site_config["base_url"], link)
                
                results.append({
                    "title": title.strip(),
                    "link": link,
                    "source": site
                })
            except Exception as e:
                logger.error(f"Error processing item: {str(e)}")
                
    except Exception as e:
        logger.error(f"Error searching {site}: {str(e)}")
    
    return results

async def search_all_sites(query):
    all_results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for site in MOVIE_SITES:
            try:
                page = await browser.new_page()
                results = await search_site(page, site, query)
                all_results.extend(results)
            finally:
                await page.close()
        await browser.close()
    return all_results

async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    msg = await update.message.reply_text("🔍 جاري البحث...")
    
    try:
        results = await search_all_sites(query)
        if not results:
            return await msg.edit_text("⚠️ لم يتم العثور على نتائج")
        
        # إنشاء أزرار النتائج
        buttons = [
            [InlineKeyboardButton(
                f"{res['title']} ({res['source']})", 
                callback_data=f"result_{i}"
            )]
            for i, res in enumerate(results[:8])
        ]
        
        await msg.edit_text(
            f"🎬 نتائج البحث ({len(results)}):",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        context.user_data["results"] = results
        
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        await msg.edit_text("❌ حدث خطأ أثناء البحث")

async def handle_result_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data.startswith("result_"):
        index = int(data.split("_")[1])
        results = context.user_data.get("results", [])
        
        if 0 <= index < len(results):
            selected = results[index]
            await query.edit_message_text(f"⏳ جاري جلب التفاصيل لـ {selected['title']}...")
            
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch()
                    page = await browser.new_page()
                    await page.goto(selected["link"], wait_until="networkidle")
                    
                    # استخراج محتوى الفيديو حسب الموقع
                    if selected["source"] == "EgyDead":
                        iframe = await page.query_selector("iframe")
                        video_url = await iframe.get_attribute("src") if iframe else None
                    elif selected["source"] == "WitAnime":
                        video_element = await page.query_selector("video source")
                        video_url = await video_element.get_attribute("src") if video_element else None
                    
                    await browser.close()
                
                if video_url:
                    await query.message.reply_video(video_url, caption=selected["title"])
                else:
                    await query.message.reply_text("⚠️ لم يتم العثور على رابط التشغيل")
            except Exception as e:
                logger.error(f"Playback error: {str(e)}")
                await query.message.reply_text("❌ حدث خطأ أثناء جلب المحتوى")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search))
    app.add_handler(CallbackQueryHandler(handle_result_selection))
    
    app.run_polling()

if __name__ == "__main__":
    main()
