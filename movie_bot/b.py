import os
import asyncio
import logging
from typing import Optional, Union, Dict, List, Any
import json
import random
import string
import re
from urllib.parse import quote, urlparse
from datetime import datetime, timedelta
import sqlite3

import aiohttp
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, Message
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from telegram.constants import ParseMode
from dotenv import load_dotenv

# (بقية الكود ... - كل ما هو قبل handle_message يبقى كما هو)
# وظائف مساعدة
def is_direct_image_link(url):
    return url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))

async def search_another_image(media_data: Dict, session: aiohttp.ClientSession, original_image: str) -> str:
    try:
        media_title = media_data.get('title') or media_data.get('name', '')
        media_year = media_data.get('release_date', '')[:4] or media_data.get('first_air_date', '')[:4]
        search_query = f"{media_title} {media_year} movie poster 16:9"
        random_offset = random.randint(1, 10)
        params = {
            'key': GOOGLE_API_KEY, 'cx': GOOGLE_CSE_ID, 'q': search_query,
            'searchType': 'image', 'imgSize': 'large', 'imgType': 'photo', 'num': 1, 'start': random_offset
        }
        async with session.get(GOOGLE_SEARCH_URL, params=params) as response:
            if response.status == 200:
                data = await response.json()
                items = data.get('items', [])
                if items and items[0]['link'] != original_image and is_direct_image_link(items[0]['link']):
                    return items[0]['link']
    except Exception as e:
        logger.error(f"خطأ في البحث عن صورة بديلة: {e}")
    return original_image


# معالجة الرسائل (مع التعديلات)
async def handle_message(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    query = update.message.text.strip()
    user_id_str = str(user.id)
    stats.add_user(user.id, user.username, user.first_name)

    state = load_user_state(user_id_str)

    # معالجة إضافة الرابط
    if state and state.get('type') == 'add_link':
        media_id = state.get('media_id')
        media = load_media_data(media_id)
        if not media:
            await update.message.reply_text("❌ انتهت صلاحية الطلب.")
            delete_user_state(user_id_str)
            return
        link = extract_url(query)
        if link:
            save_media_data(media_id, media['details'], media['type'], media['image_url'], link, media['emoji'], media['message_id'])
            delete_user_state(user_id_str)
            caption = f"{format_media_message(media['details'], media['emoji']).split(' للمشاهدة')[0]} <a href='{link}'>للمشاهدة اضغط هنا</a>"
            keyboard = [
                [InlineKeyboardButton("🔄 تغيير الرابط", callback_data=f"add_link_{media_id}"),
                 InlineKeyboardButton("🖼️ صورة أخرى", callback_data=f"another_image_{media_id}")],
                [InlineKeyboardButton("✏️ تغيير الرمز", callback_data=f"change_emoji_{media_id}")],
                [InlineKeyboardButton("❤️ إضافة إلى المفضلة", callback_data=f"add_fav_{media_id}_{media['type']}")] # زر إضافة إلى المفضلة

            ]
            await context.bot.edit_message_media(
                chat_id=update.effective_chat.id,
                message_id=media['message_id'],
                media=InputMediaPhoto(media['image_url'], caption=caption, parse_mode=ParseMode.HTML),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            # حذف رسالة المستخدم بعد إضافة الرابط **************************
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)

        else:
            await update.message.reply_text("❌ رابط غير صالح. أرسل رابطًا يبدأ بـ http:// أو https://")
        return

    # معالجة البحث المتقدم بالاسم
    if state and state.get('type') == 'search_by_name':
        delete_user_state(user_id_str)  # إنهاء حالة البحث بالاسم
        await perform_search(update, context, query)  # إجراء البحث العادي
        return
    #معالجة البحث المتقدم بالسنة
    if state and state.get('type') == 'search_by_year':
        delete_user_state(user_id_str)
        try:
            year = int(query)
            if 1900 <= year <= datetime.now().year:
                await perform_search(update, context, "", year=year)
            else:
                await update.message.reply_text("❌ سنة غير صالحة.  يجب أن تكون بين 1900 والسنة الحالية.")
        except ValueError:
            await update.message.reply_text("❌ أدخل رقمًا يمثل السنة.")
        return

    # معالجة البحث المتقدم بالتقييم (TMDB لا يدعم البحث بالتقييم مباشرة)
    if state and state.get('type') == 'search_by_rating':
        await update.message.reply_text("❌ البحث بالتقييم غير مدعوم حاليًا عبر TMDB.")
        delete_user_state(user_id_str)
        return

    # معالجة البحث المتقدم بالنوع
    if state and state.get('type') == 'search_by_genre':
        delete_user_state(user_id_str)
        await perform_search(update, context, "", genre=query)  # إجراء البحث مع تحديد النوع
        return

    # التحقق من الاشتراك (قبل البحث العادي)
    if not await check_user_subscription(user.id, context):
        keyboard = [[InlineKeyboardButton(f"📢 {ch['title']}", url=ch['url'])] for ch in config.forced_channels]
        keyboard.append([InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subscription")])
        await update.message.reply_text("⚠️ يجب الاشتراك في القنوات:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # التحقق من طول الاستعلام (قبل البحث العادي)
    if len(query) < 2 and not (state and (state.get('type') == 'search_by_year' or state.get('type') == 'search_by_genre')):
        await update.message.reply_text("⚠️ أدخل اسمًا أطول للبحث")
        return

    # البحث العادي (إذا لم يكن هناك حالة بحث متقدم)
    if not state or state.get('type') != 'add_link':
       await perform_search(update, context, query)


# وظيفة البحث (لتوحيد عملية البحث)
async def perform_search(update: Update, context: CallbackContext, query: str, year: Optional[int] = None, genre: Optional[str] = None):

    msg = await update.message.reply_text("🔍 جاري البحث...")
    async with aiohttp.ClientSession() as session:
        user_id_str = str(update.effective_user.id)
        media_type = load_user_state(user_id_str).get('media_type', 'movie')
        results = await search_tmdb(query, media_type, session, year, genre)
        filtered = [r for r in results.get('results', []) if r.get('poster_path') or r.get('backdrop_path')]

        if not filtered:
            await msg.edit_text("❌ لم يتم العثور على نتائج.")
            return

        result = filtered[0]
        details = await get_media_details(result['id'], media_type, session)
        if not details:
            await msg.edit_text("❌ خطأ في جلب التفاصيل.")
            return

        image_url = await get_image_url(details, session)
        media_id = generate_unique_id()
        message = await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=image_url,
            caption=format_media_message(details),
            parse_mode=ParseMode.HTML
        )
        save_media_data(media_id, details, media_type, image_url, message_id=str(message.message_id))

        # أزرار الإجراءات
        keyboard = [
            [InlineKeyboardButton("➕ إضافة رابط" if not None else "🔄 تغيير الرابط", callback_data=f"add_link_{media_id}"),
             InlineKeyboardButton("🖼️ صورة أخرى", callback_data=f"another_image_{media_id}")],
            [InlineKeyboardButton("✏️ تغيير الرمز", callback_data=f"change_emoji_{media_id}")],
            [InlineKeyboardButton("❤️ إضافة إلى المفضلة", callback_data=f"add_fav_{media_id}_{media_type}")],  # إضافة إلى المفضلة
            [InlineKeyboardButton("⭐ تقييم", callback_data=f"show_rating_{media_id}")]  # زر إظهار التقييم
        ]

        # إضافة زر "الإعلان التشويقي" إذا كان متاحًا
        videos = details.get('videos', {}).get('results', [])
        if videos:
            video_url = f"https://www.youtube.com/watch?v={videos[0]['key']}"
            keyboard.append([InlineKeyboardButton("🎥 الإعلان التشويقي", url=video_url)])
        # إضافة زر "اقتراحات"
        keyboard.append([InlineKeyboardButton("💡 اقتراحات", callback_data=f"get_rec_{media_id}_{media_type}")])


        await context.bot.edit_message_reply_markup(
            chat_id=update.effective_chat.id,
            message_id=message.message_id,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await msg.delete()

# معالجة استدعاءات الأزرار (Callback Query Handler)
async def handle_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id_str = str(query.from_user.id)

    # التحقق من الاشتراك
    if data == "check_subscription":
        if await check_user_subscription(query.from_user.id, context):
            await query.edit_message_text("✅ تم التحقق من الاشتراك!")
        else:
            await query.edit_message_text("❌ لم تكمل الاشتراك بعد.")
        return

    # استئناف البحث
    if data == "resume_search":
        user_state = load_user_state(user_id_str)
        if user_state and user_state.get('type') == 'search':
            await query.edit_message_text("📝 أرسل اسم الفيلم أو المسلسل:")
        return

    # إلغاء البحث
    if data == "cancel_search":
        delete_user_state(user_id_str)
        await query.edit_message_text("❌ تم إلغاء البحث.")
        await start_command(update, context)  # العودة إلى قائمة البداية
        return

    #  search_movie و search_tv
    if data.startswith("search_"):
        media_type = data.split("_")[1]
        save_user_state(user_id_str, {'type': 'search', 'media_type': media_type})
        await query.edit_message_media(
            media=InputMediaPhoto(
                media=config.start_image,
                caption=f"📝 أرسل اسم {'الفيلم' if media_type == 'movie' else 'المسلسل'} للبحث.",
                parse_mode=ParseMode.MARKDOWN
            )
        )
        return
      # أوامر البحث المتقدم
    if data == "advanced_search":
        await advanced_search(update, context)
        return

    if data == "search_by_name":
        await search_by_name_handler(update,context)
        return

    if data == "search_by_year":
        await search_by_year_handler(update, context)
        return

    if data == "search_by_rating":
       await search_by_rating_handler(update, context)
       return

    if data == "search_by_genre":
        await search_by_genre_handler(update, context)
        return

    # معالجة الأزرار المتعلقة بالوسائط
    parts = data.split('_')
    action = '_'.join(parts[:2])
    if len(parts) < 3:
        return
    media_id = parts[2]
    media = load_media_data(media_id)
    if not media:
        await query.edit_message_caption(caption="❌ انتهت صلاحية الطلب.", parse_mode=ParseMode.HTML)
        return

    # إضافة/تغيير الرابط
    if action == "add_link":
        save_user_state(user_id_str, {'type': 'add_link', 'media_id': media_id})
        await query.edit_message_caption(caption="🔗 أرسل رابط المشاهدة:", parse_mode=ParseMode.HTML)
        return

    # صورة أخرى
    elif action == "another_image":
        async with aiohttp.ClientSession() as session:
            new_image_url = await search_another_image(media['details'], session, media['image_url'])
            if not new_image_url or new_image_url == media['image_url']:
                new_image_url = "https://via.placeholder.com/1280x720?text=New+Image+Not+Found"
            save_media_data(media_id, media['details'], media['type'], new_image_url, media['link'], media['emoji'], media['message_id'])
            caption = format_media_message(media['details'], media['emoji'])
            if media['link']:
                caption = f"{caption.split(' للمشاهدة')[0]} <a href='{media['link']}'>للمشاهدة اضغط هنا</a>"
            keyboard = [
                [InlineKeyboardButton("➕ إضافة رابط" if not media['link'] else "🔄 تغيير الرابط", callback_data=f"add_link_{media_id}"),
                 InlineKeyboardButton("🖼️ صورة أخرى", callback_data=f"another_image_{media_id}")],
                [InlineKeyboardButton("✏️ تغيير الرمز", callback_data=f"change_emoji_{media_id}")],
                [InlineKeyboardButton("❤️ إضافة إلى المفضلة", callback_data=f"add_fav_{media_id}_{media['type']}")] # إضافة إلى المفضلة
            ]
            await query.edit_message_media(
                media=InputMediaPhoto(new_image_url, caption=caption, parse_mode=ParseMode.HTML),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return

    # تغيير الرمز التعبيري
    elif action == "change_emoji":
        save_user_state(user_id_str, {'type': 'change_emoji', 'media_id': media_id})
        emojis = get_emoji_options()
        keyboard = [[InlineKeyboardButton(e, callback_data=f"select_emoji_{media_id}_{e}")] for e in emojis]
        await query.edit_message_caption(caption="🎨 اختر رمزًا جديدًا:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # اختيار الرمز التعبيري
    elif action == "select_emoji":
        emoji = parts[3]
        save_media_data(media_id, media['details'], media['type'], media['image_url'], media['link'], emoji, media['message_id'])
        caption = format_media_message(media['details'], emoji)
        if media['link']:
            caption = f"{caption.split(' للمشاهدة')[0]} <a href='{media['link']}'>للمشاهدة اضغط هنا</a>"
        keyboard = [
            [InlineKeyboardButton("➕ إضافة رابط" if not media['link'] else "🔄 تغيير الرابط", callback_data=f"add_link_{media_id}"),
             InlineKeyboardButton("🖼️ صورة أخرى", callback_data=f"another_image_{media_id}")],
            [InlineKeyboardButton("✏️ تغيير الرمز", callback_data=f"change_emoji_{media_id}")],
            [InlineKeyboardButton("❤️ إضافة إلى المفضلة", callback_data=f"add_fav_{media_id}_{media['type']}")]  # إضافة إلى المفضلة
        ]
        await query.edit_message_media(
            media=InputMediaPhoto(media['image_url'], caption=caption, parse_mode=ParseMode.HTML),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        delete_user_state(user_id_str)
        return

     # إضافة إلى/إزالة من المفضلة
    if action == "add_fav":
        add_to_favorites(user_id_str, media_id)
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❤️ تمت الإضافة للمفضلة", callback_data=f"remove_fav_{media_id}")]
            ])
        )
        return

    if action == "remove_fav":
        remove_from_favorites(user_id_str, media_id)
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ إضافة إلى المفضلة", callback_data=f"add_fav_{media_id}_{media['type']}")]
            ])
        )
        return
    # عرض قائمة المفضلة
    if data == "view_favorites":
      favorites = get_user_favorites(user_id_str)
      if not favorites:
          await query.edit_message_text("❌ قائمة المفضلة فارغة.")
          return

      favorites_text = "⭐ **مفضلتي:**\n\n"
      for fav_id in favorites:
          fav_media = load_media_data(fav_id)
          if fav_media:
              title = fav_media['details'].get('title') or fav_media['details'].get('name', 'غير معروف')
              favorites_text += f"- {title} (`{fav_media['type']}`)\n"

      await query.edit_message_text(favorites_text, parse_mode=ParseMode.MARKDOWN)
      return

    # إظهار/إخفاء أزرار التقييم
    if action == "show_rating":
        keyboard = [
            [InlineKeyboardButton("⭐", callback_data=f"rate_{media_id}_1"),
             InlineKeyboardButton("⭐⭐", callback_data=f"rate_{media_id}_2"),
             InlineKeyboardButton("⭐⭐⭐", callback_data=f"rate_{media_id}_3"),
             InlineKeyboardButton("⭐⭐⭐⭐", callback_data=f"rate_{media_id}_4"),
             InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data=f"rate_{media_id}_5")]
        ]
        # إضافة زر الرجوع لإخفاء التقييم
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"hide_rating_{media_id}")])
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if action == "hide_rating":
        # إعادة الأزرار الأصلية (بدون أزرار التقييم)
        keyboard = [
            [InlineKeyboardButton("➕ إضافة رابط" if not media['link'] else "🔄 تغيير الرابط", callback_data=f"add_link_{media_id}"),
             InlineKeyboardButton("🖼️ صورة أخرى", callback_data=f"another_image_{media_id}")],
            [InlineKeyboardButton("✏️ تغيير الرمز", callback_data=f"change_emoji_{media_id}")],
            [InlineKeyboardButton("❤️ إضافة إلى المفضلة", callback_data=f"add_fav_{media_id}_{media['type']}")]
        ]
        videos = media['details'].get('videos', {}).get('results', [])
        if videos:
            video_url = f"https://www.youtube.com/watch?v={videos[0]['key']}"
            keyboard.append([InlineKeyboardButton("🎥 الإعلان التشويقي", url=video_url)])
        keyboard.append([InlineKeyboardButton("💡 اقتراحات", callback_data=f"get_rec_{media_id}_{media['type']}")])

        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # تقييم الوسائط
    if action == "rate":
        rating = int(parts[3])

        # تحديث تقييم الوسائط
        save_media_data(media_id, media['details'], media['type'], media['image_url'], media['link'], media['emoji'], media['message_id'], rating)

        await query.answer(f"شكرًا! لقد قيمت هذا بـ {rating} من 5 نجوم")
        # إزالة أزرار التقييم بعد التصويت
        await context.bot.edit_message_reply_markup(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            reply_markup=InlineKeyboardMarkup([])  # أزرار فارغة
        )

        return

    # جلب الاقتراحات
    if action == "get_rec":
        media_type = parts[3]
        async with aiohttp.ClientSession() as session:
            recommendations = await get_recommendations(media_id, media_type, session)

            if not recommendations:
                await query.edit_message_text("❌ لم يتم العثور على اقتراحات مشابهة.")
                return

            keyboard = []
            for rec in recommendations:
                title = rec.get('title') or rec.get('name', 'غير معروف')
                rec_media_id = str(rec['id'])  # تحويل معرّف الاقتراح إلى نص
                keyboard.append([InlineKeyboardButton(title, callback_data=f"view_{rec_media_id}_{media_type}")])

            keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"back_to_details_{media_id}")]) # زر الرجوع

            await query.edit_message_text(
                "🎬 إليك بعض الاقتراحات المشابهة:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return
    # عرض تفاصيل الاقتراح
    if action == "view":
        rec_media_id = parts[2]
        rec_media_type = parts[3]
        async with aiohttp.ClientSession() as session:
            rec_details = await get_media_details(int(rec_media_id), rec_media_type, session)  # تحويل المعرف إلى عدد صحيح
            if not rec_details:
                await query.edit_message_text("❌ خطأ في جلب تفاصيل الاقتراح.")
                return

            rec_image_url = await get_image_url(rec_details, session)
            rec_unique_id = generate_unique_id()  # إنشاء معرف فريد للاقتراح
            message = await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=rec_image_url,
                caption=format_media_message(rec_details),
                parse_mode=ParseMode.HTML
            )
            save_media_data(rec_unique_id, rec_details, rec_media_type, rec_image_url, message_id=str(message.message_id))

            keyboard = [
                [InlineKeyboardButton("➕ إضافة رابط" if not None else "🔄 تغيير الرابط", callback_data=f"add_link_{rec_unique_id}"),
                InlineKeyboardButton("🖼️ صورة أخرى", callback_data=f"another_image_{rec_unique_id}")],
                [InlineKeyboardButton("✏️ تغيير الرمز", callback_data=f"change_emoji_{rec_unique_id}")],
                [InlineKeyboardButton("❤️ إضافة إلى المفضلة", callback_data=f"add_fav_{rec_unique_id}_{rec_media_type}")],
                [InlineKeyboardButton("⭐ تقييم", callback_data=f"show_rating_{rec_unique_id}")]
            ]

            videos = rec_details.get('videos', {}).get('results', [])
            if videos:
                video_url = f"https://www.youtube.com/watch?v={videos[0]['key']}"
                keyboard.append([InlineKeyboardButton("🎥 الإعلان التشويقي", url=video_url)])
            keyboard.append([InlineKeyboardButton("💡 اقتراحات", callback_data=f"get_rec_{rec_unique_id}_{rec_media_type}")])
            # زر الرجوع إلى تفاصيل الفيلم/المسلسل الأصلي
            keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"back_to_details_{media_id}")])

            await context.bot.edit_message_reply_markup(
                chat_id=query.message.chat_id,
                message_id=message.message_id,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        await query.message.delete() #حذف الرسالة الي فيها الاقتراحات

        return

    # زر الرجوع إلى تفاصيل الفيلم/المسلسل الأصلي
    if action == "back_to_details":
        # media_id = parts[2] #  media_id  موجودة بالفعل
        # media = load_media_data(media_id) # media موجود بالفعل

        caption = format_media_message(media['details'], media['emoji'])
        if media['link']:
            caption = f"{caption.split(' للمشاهدة')[0]} <a href='{media['link']}'>للمشاهدة اضغط هنا</a>"

        keyboard = [
            [InlineKeyboardButton("➕ إضافة رابط" if not media['link'] else "🔄 تغيير الرابط", callback_data=f"add_link_{media_id}"),
            InlineKeyboardButton("🖼️ صورة أخرى", callback_data=f"another_image_{media_id}")],
            [InlineKeyboardButton("✏️ تغيير الرمز", callback_data=f"change_emoji_{media_id}")],
            [InlineKeyboardButton("❤️ إضافة إلى المفضلة", callback_data=f"add_fav_{media_id}_{media['type']}")]
        ]
        videos = media['details'].get('videos', {}).get('results', [])
        if videos:
             video_url = f"https://www.youtube.com/watch?v={videos[0]['key']}"
             keyboard.append([InlineKeyboardButton("🎥 الإعلان التشويقي", url=video_url)])
        keyboard.append([InlineKeyboardButton("💡 اقتراحات", callback_data=f"get_rec_{media_id}_{media['type']}")])
        keyboard.append([InlineKeyboardButton("⭐ تقييم", callback_data=f"show_rating_{media_id}")]) #ارجاع زر التقيم

        await query.edit_message_media(
             media=InputMediaPhoto(media['image_url'], caption=caption, parse_mode=ParseMode.HTML),
             reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return


# معالجة الأخطاء (مع التحسينات)
async def error_handler(update: Update, context: CallbackContext) -> None:
    logger.error(f"خطأ {context.error} في التحديث {update}")

    # تحديد نوع الخطأ وتوفير معلومات أكثر تفصيلاً
    error_type = type(context.error).__name__
    error_message = str(context.error)

    # إرسال تقرير الخطأ للمطورين إذا كان خطأ حرجًا
    if error_type in ['KeyError', 'IndexError', 'TypeError', 'sqlite3.OperationalError']:
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"⚠️ خطأ حرج:\n{error_type}: {error_message}\n\nالتفاصيل:\n```{update}```",  # استخدام Markdown لعرض أفضل
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                pass

    # الرد على المستخدم بشكل مناسب
    if update and update.effective_message:
        if error_type == 'NetworkError':
            await update.effective_message.reply_text("⚠️ حدث خطأ في الاتصال بالشبكة. يرجى المحاولة لاحقًا.")
        elif error_type == 'BadRequest':
            if "Wrong type of the web page content" in error_message:
                await update.effective_message.reply_text("⚠️ الرابط الذي أرسلته ليس رابطًا مباشرًا لصورة.  يرجى إرسال رابط ينتهي بـ .jpg أو .png أو امتداد صورة آخر.")
            else:
                await update.effective_message.reply_text("⚠️ طلب غير صحيح. يرجى التحقق من المدخلات.")

        elif error_type == 'TimedOut':
            await update.effective_message.reply_text("⚠️ انتهت مهلة الطلب. يرجى المحاولة مرة أخرى.")

        elif error_type == 'TelegramAPIError':
            if "message to edit not found" in error_message:
                await update.effective_message.reply_text("⚠️ انتهت صلاحية الجلسة.  يرجى إعادة البحث.") #او  start
            else:
                await update.effective_message.reply_text("⚠️ حدث خطأ في تيليجرام. يرجى المحاولة لاحقًا.")


        else:
            await update.effective_message.reply_text("⚠️ حدث خطأ غير متوقع. جاري العمل على حله.")

    elif update and update.callback_query:
        # أخطاء CallbackQuery (إذا لم يكن هناك رسالة مرتبطة)
        if error_type == 'BadRequest' and "message can't be edited" in error_message:
             await update.callback_query.answer("⚠️ انتهت صلاحية هذا الزر.", show_alert=True)
        else:
             await update.callback_query.answer("⚠️ حدث خطأ غير متوقع.", show_alert=True)


# وظيفة الإحصائيات للمشرفين
async def admin_statistics(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ هذا الأمر للمشرفين فقط.")
        return

    total_users = len(stats.users)
    active_users = sum(1 for u in stats.users.values() if datetime.now().strftime('%Y-%m-%d') in u.get('last_activity', ''))
    total_searches = stats.total_searches

    #  رسم بياني بسيط للإحصائيات (يمكن تحسينه باستخدام مكتبات خارجية)
    stats_text = (
        f"📊 **إحصائيات البوت**\n\n"
        f"👥 إجمالي المستخدمين: {total_users}\n"
        f"👤 المستخدمون النشطون اليوم: {active_users}\n"
        f"🔍 إجمالي عمليات البحث: {total_searches}\n"
        f"📈 متوسط البحث لكل مستخدم: {total_searches/total_users:.1f}\n\n"
        f"الإحصائيات اليومية للأسبوع الماضي:\n"
    )

    # إضافة بيانات الأسبوع الماضي
    last_7_days = sorted(stats.daily_searches.keys())[-7:]
    for day in last_7_days:
        stats_text += f"- {day}: {stats.daily_searches.get(day, 0)} بحث\n"

    await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)


# وظيفة إرسال الإشعارات (للمشرفين)
async def send_notification_to_users(context: CallbackContext, message: str) -> None:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM user_states")  # يمكن تحسينها لاستهداف مستخدمين معينين
    users = c.fetchall()
    conn.close()

    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user[0],
                text=message
            )
            logger.info(f"تم إرسال إشعار للمستخدم {user[0]}")
        except Exception as e:
            logger.error(f"خطأ في إرسال إشعار للمستخدم {user[0]}: {e}")

# أوامر المشرفين
async def admin_add_channel(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
         return
    user_id = update.effective_user.id
    save_user_state(str(user_id), {'type': 'add_channel'})
    await update.message.reply_text("أرسل معرف القناة واسمها (مفصولين بمسافة):")

async def admin_edit_start_message(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    user_id = update.effective_user.id
    save_user_state(str(user_id), {'type': 'edit_start_message'})
    await update.message.reply_text("أرسل رسالة البداية الجديدة:")

async def admin_change_start_image(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        return
    user_id = update.effective_user.id
    save_user_state(str(user_id), {'type': 'change_start_image'})
    await update.message.reply_text("أرسل رابط الصورة الجديدة:")

async def handle_admin_commands(update: Update, context: CallbackContext):
     user = update.effective_user
     user_id_str = str(user.id)
     state = load_user_state(user_id_str)
     text = update.message.text

     if state and state.get('type') == 'add_channel':
        try:
            channel_id, channel_title = text.split(" ", 1)  # فصل المعرف والاسم
            channel_id = int(channel_id)  # تحويل المعرف إلى عدد صحيح
            config.forced_channels.append({'id': channel_id, 'title': channel_title, 'url': f'https://t.me/c/{str(channel_id)[4:]}'})  # إضافة القناة
            config.save()
            await update.message.reply_text(f"تمت إضافة القناة: {channel_title} ({channel_id})")
        except ValueError:
            await update.message.reply_text("خطأ: تأكد من إدخال معرف القناة (رقم) واسم القناة مفصولين بمسافة.")
        finally:
            delete_user_state(user_id_str)

     elif state and state.get('type') == 'edit_start_message':
        config.start_message = text
        config.save()
        await update.message.reply_text("تم تحديث رسالة البداية.")
        delete_user_state(user_id_str)

     elif state and state.get('type') == 'change_start_image':
        if is_direct_image_link(text):  # استخدام الدالة المساعدة
            config.start_image = text
            config.save()
            await update.message.reply_text("تم تحديث صورة البداية.")
        else:
            await update.message.reply_text("خطأ: أرسل رابط صورة صالح (مباشر).")

# أوامر المستخدمين الإضافية
async def favorites_command(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    favorites = get_user_favorites(user_id)

    if not favorites:
        await update.message.reply_text("❌ قائمة المفضلة فارغة.")
        return

    favorites_text = "⭐ **مفضلتي:**\n\n"
    for fav_id in favorites:
        fav_media = load_media_data(fav_id)
        if fav_media:
            title = fav_media['details'].get('title') or fav_media['details'].get('name', 'غير معروف')
            favorites_text += f"- {title} (`{fav_media['type']}`)\n"

    await update.message.reply_text(favorites_text, parse_mode=ParseMode.MARKDOWN)
# main
def main() -> None:
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # معالجة الأوامر
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("fav", favorites_command))  # أمر المفضلة
    # معالجة الرسائل (بما في ذلك أوامر المشرفين)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(r'^-?\d+\s+.*$'), handle_admin_commands)) # لالتقاط رسائل المشرفين الخاصة بإضافة القنوات
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_commands)) # لالتقاط رسائل المشرفين

    # معالجة استدعاءات الأزرار
    application.add_handler(CallbackQueryHandler(handle_callback))

    # معالجة الأخطاء
    application.add_error_handler(error_handler)

    # استعادة الجلسة عند بدء التشغيل
    # application.add_handler(StartupHandler(recover_session)) # غير مدعوم رسميًا

    # تشغيل البوت
    application.run_polling()

if __name__ == '__main__':
    main()
