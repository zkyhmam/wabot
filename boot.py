import asyncio
from playwright.async_api import async_playwright
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# توكن البوت
TOKEN = "7558529929:AAFmMHm2HuqHsdqdQvl_ZLCoXn5XOPiRzfw"

# قائمة المواقع
SITES = {
    "EgyDead": {
        "url": "https://egydead.space/",
        "search_url": "https://egydead.space/search?s={query}",
        "selectors": {"results": "article.post", "title": "h2.title a", "link": "h2.title a"}
    },
    "WitAnime": {
        "url": "https://witanime.com/",
        "search_url": "https://witanime.com/?search_param=animes&s={query}",
        "selectors": {"results": "div.anime-card-container", "title": "h3", "link": "a"}
    },
    "FilmDoo": {
        "url": "https://www.filmdoo.com/",
        "search_url": "https://www.filmdoo.com/search?query={query}",
        "selectors": {"results": "div.film-card", "title": "h3", "link": "a"}
    },
    "EgyBest": {
        "url": "https://i-egybest.com/",
        "search_url": "https://i-egybest.com/search?s={query}",
        "selectors": {"results": "div.movie", "title": "h2 a", "link": "h2 a"}
    }
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("مرحبًا! اكتب اسم فيلم للبحث عنه.")

async def search_movies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.message.text
    msg = await update.message.reply_text(f"جاري البحث عن: {query}...")
    
    results = await scrape_sites(query)
    
    if not results:
        await msg.edit_text("لم يتم العثور على نتائج.")
        return
    
    keyboard = [[InlineKeyboardButton(f"{r['site']}: {r['title']}", callback_data=f"movie_{i}")] 
                for i, r in enumerate(results[:10])]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.user_data["search_results"] = results
    await msg.edit_text("نتائج البحث:", reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    index = int(query.data.split("_")[1])
    results = context.user_data.get("search_results", [])
    if 0 <= index < len(results):
        result = results[index]
        await query.message.edit_text(f"تم اختيار: {result['title']} من {result['site']}\nرابط: {result['link']}")

async def scrape_sites(query):
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        
        for site_name, site_info in SITES.items():
            try:
                page = await context.new_page()
                search_url = site_info['search_url'].format(query=query)
                await page.goto(search_url, timeout=60000)
                await page.wait_for_load_state("networkidle")
                
                elements = await page.query_selector_all(site_info['selectors']['results'])
                for element in elements:
                    title_elem = await element.query_selector(site_info['selectors']['title'])
                    link_elem = await element.query_selector(site_info['selectors']['link'])
                    title = await title_elem.inner_text() if title_elem else "بدون عنوان"
                    link = await link_elem.get_attribute('href') if link_elem else None
                    if link and not link.startswith('http'):
                        link = site_info['url'].rstrip('/') + '/' + link.lstrip('/')
                    results.append({"site": site_name, "title": title, "link": link})
                await page.close()
            except Exception as e:
                print(f"خطأ في {site_name}: {e}")
        await browser.close()
    return results

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_movies))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_polling()

if __name__ == "__main__":
    main()
