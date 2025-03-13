import os
import requests
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from bs4 import BeautifulSoup
import re
import asyncio
import aiohttp

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# توكن البوت الخاص بك من BotFather
TOKEN = "7558529929:AAFmMHm2HuqHsdqdQvl_ZLCoXn5XOPiRzfw"

# قائمة المواقع التي سيتم البحث فيها
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
        "search_url": "https://i-egybest.com/search?s={}",  # تأكد من النمط الصحيح
        "base_url": "https://i-egybest.com"
    }
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إرسال رسالة عند إصدار الأمر /start."""
    await update.message.reply_text(
        'مرحبًا! أنا بوت البحث عن الأفلام العربية. أرسل لي اسم فيلم أو مسلسل للبحث عنه.'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إرسال رسالة عند إصدار الأمر /help."""
    await update.message.reply_text('أرسل لي اسم فيلم أو مسلسل للبحث عنه في مواقع مختلفة.')

async def search_egydead(session, query):
    """البحث في موقع EgyDead."""
    results = []
    site_info = MOVIE_SITES["EgyDead"]
    search_url = site_info["search_url"].format(query)
    
    try:
        async with session.get(search_url) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # تعديل هذا الجزء حسب هيكل HTML للموقع
                movie_items = soup.select('.movie-item')
                
                for item in movie_items:
                    title_element = item.select_one('.movie-title')
                    link_element = item.select_one('a')
                    
                    if title_element and link_element:
                        title = title_element.text.strip()
                        link = link_element.get('href')
                        if not link.startswith('http'):
                            link = site_info["base_url"] + link
                        
                        results.append({
                            "title": title,
                            "link": link,
                            "source": "EgyDead"
                        })
    except Exception as e:
        logging.error(f"خطأ في البحث على EgyDead: {e}")
    
    return results

async def search_witanime(session, query):
    """البحث في موقع WitAnime."""
    results = []
    site_info = MOVIE_SITES["WitAnime"]
    search_url = site_info["search_url"].format(query)
    
    try:
        async with session.get(search_url) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # تعديل هذا الجزء حسب هيكل HTML للموقع
                anime_items = soup.select('.anime-card')
                
                for item in anime_items:
                    title_element = item.select_one('.anime-title')
                    link_element = item.select_one('a')
                    
                    if title_element and link_element:
                        title = title_element.text.strip()
                        link = link_element.get('href')
                        if not link.startswith('http'):
                            link = site_info["base_url"] + link
                        
                        results.append({
                            "title": title,
                            "link": link,
                            "source": "WitAnime"
                        })
    except Exception as e:
        logging.error(f"خطأ في البحث على WitAnime: {e}")
    
    return results

async def search_filmdoo(session, query):
    """البحث في موقع FilmDoo."""
    results = []
    site_info = MOVIE_SITES["FilmDoo"]
    search_url = site_info["search_url"].format(query)
    
    try:
        async with session.get(search_url) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # افتراض هيكل HTML، يجب التأكد
                movie_items = soup.select('.film-item')
                
                for item in movie_items:
                    title_element = item.select_one('.film-title')
                    link_element = item.select_one('a')
                    
                    if title_element and link_element:
                        title = title_element.text.strip()
                        link = link_element.get('href')
                        if not link.startswith('http'):
                            link = site_info["base_url"] + link
                        
                        results.append({
                            "title": title,
                            "link": link,
                            "source": "FilmDoo"
                        })
    except Exception as e:
        logging.error(f"خطأ في البحث على FilmDoo: {e}")
    
    return results

async def search_egybest(session, query):
    """البحث في موقع EgyBest."""
    results = []
    site_info = MOVIE_SITES["EgyBest"]
    search_url = site_info["search_url"].format(query)
    
    try:
        async with session.get(search_url) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # افتراض هيكل HTML، يجب التأكد
                movie_items = soup.select('.movie-item')
                
                for item in movie_items:
                    title_element = item.select_one('.title')
                    link_element = item.select_one('a')
                    
                    if title_element and link_element:
                        title = title_element.text.strip()
                        link = link_element.get('href')
                        if not link.startswith('http'):
                            link = site_info["base_url"] + link
                        
                        results.append({
                            "title": title,
                            "link": link,
                            "source": "EgyBest"
                        })
    except Exception as e:
        logging.error(f"خطأ في البحث على EgyBest: {e}")
    
    return results

async def search_all_sites(query):
    """البحث في جميع المواقع المدعومة."""
    all_results = []
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        
        # إنشاء مهام البحث لكل موقع
        tasks.append(search_egydead(session, query))
        tasks.append(search_witanime(session, query))
        tasks.append(search_filmdoo(session, query))
        tasks.append(search_egybest(session, query))
        
        # تنفيذ جميع المهام بالتوازي
        results = await asyncio.gather(*tasks)
        
        # دمج النتائج
        for site_results in results:
            all_results.extend(site_results)
    
    return all_results

async def extract_video_url(session, page_url, source):
    """استخراج رابط الفيديو من صفحة العرض."""
    try:
        async with session.get(page_url) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                if source == "EgyDead":
                    # مثال لاستخراج رابط الفيديو من EgyDead
                    video_element = soup.select_one('.video-player iframe')
                    if video_element:
                        return video_element.get('src')
                
                elif source == "WitAnime":
                    # مثال لاستخراج رابط الفيديو من WitAnime
                    video_element = soup.select_one('.video-player source')
                    if video_element:
                        return video_element.get('src')
                
                elif source == "FilmDoo":
                    # افتراض لاستخراج رابط الفيديو من FilmDoo
                    video_element = soup.select_one('.video-player source')
                    if video_element:
                        return video_element.get('src')
                
                elif source == "EgyBest":
                    # افتراض لاستخراج رابط الفيديو من EgyBest
                    iframe = soup.select_one('iframe')
                    if iframe:
                        return iframe.get('src')
                    # أو ربما رابط مباشر
                    video = soup.select_one('video source')
                    if video:
                        return video.get('src')
    
    except Exception as e:
        logging.error(f"خطأ في استخراج رابط الفيديو: {e}")
    
    return None

async def send_video_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE, video_url):
    """إرسال الفيديو إلى المستخدم."""
    try:
        # إرسال رسالة "جاري التحميل..."
        loading_message = await update.callback_query.message.reply_text("جاري تحميل الفيديو...")
        
        # إرسال الفيديو باستخدام الرابط
        await update.callback_query.message.reply_video(
            video_url,
            caption="إليك الفيديو الذي طلبته!"
        )
        
        # حذف رسالة "جاري التحميل..."
        await loading_message.delete()
        
    except Exception as e:
        logging.error(f"خطأ في إرسال الفيديو: {e}")
        await update.callback_query.message.reply_text(
            "عذرًا، لم أتمكن من إرسال الفيديو. يرجى المحاولة مرة أخرى."
        )

async def search_movies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """البحث عن الأفلام استنادًا إلى استعلام المستخدم."""
    query = update.message.text
    
    # إرسال رسالة "جاري البحث..."
    searching_message = await update.message.reply_text("جاري البحث...")
    
    # البحث في جميع المواقع
    results = await search_all_sites(query)
    
    if not results:
        await searching_message.edit_text("لم أجد أي نتائج للبحث الذي أجريته.")
        return
    
    # إنشاء أزرار لنتائج البحث
    keyboard = []
    for i, result in enumerate(results[:10]):  # الحد الأقصى 10 نتائج
        button_text = f"{result['title']} ({result['source']})"
        callback_data = f"movie_{i}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # تحديث رسالة "جاري البحث..." بنتائج البحث
    await searching_message.edit_text(
        f"وجدت {len(results)} نتيجة لـ '{query}':",
        reply_markup=reply_markup
    )
    
    # تخزين النتائج في سياق المحادثة
    context.user_data["search_results"] = results

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالجة النقرات على الأزرار."""
    query = update.callback_query
    await query.answer()
    
    # استخراج فهرس النتيجة من بيانات رد الاتصال
    if query.data.startswith("movie_"):
        index = int(query.data.split("_")[1])
        results = context.user_data.get("search_results", [])
        
        if 0 <= index < len(results):
            selected_movie = results[index]
            
            # إرسال رسالة "جاري التحميل..."
            await query.edit_message_text(f"جاري تحميل {selected_movie['title']}...")
            
            # استخراج رابط الفيديو
            async with aiohttp.ClientSession() as session:
                video_url = await extract_video_url(session, selected_movie['link'], selected_movie['source'])
            
            if video_url:
                # إرسال الفيديو إلى المستخدم
                await send_video_to_user(update, context, video_url)
            else:
                await query.edit_message_text(
                    f"عذرًا، لم أتمكن من العثور على رابط الفيديو لـ {selected_movie['title']}."
                )

def main() -> None:
    """تشغيل البوت."""
    application = ApplicationBuilder().token(TOKEN).build()
    
    # إضافة معالجات الأوامر
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # إضافة معالج للرسائل النصية
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_movies))
    
    # إضافة معالج لنقرات الأزرار
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # بدء البوت
    application.run_polling()

if __name__ == "__main__":
    main()
