import os
import re
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Union

import requests
from bs4 import BeautifulSoup
from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, 
    CallbackQuery, InputMediaPhoto, InputMediaVideo
)
from pymongo import MongoClient
from pymongo.errors import PyMongoError

# API credentials
API_ID = 25713843
API_HASH = "311352d08811e7f5136dfb27f71014c1"
BOT_TOKEN = "7558529929:AAFmMHm2HuqHsdqdQvl_ZLCoXn5XOPiRzfw"

# MongoDB configuration
MONGO_URI = "mongodb+srv://zkyhmam:Zz462008##@cluster0.7bpsz.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["ak_sv_bot"]

# Collections
users_col = db["users"]
downloads_col = db["downloads"]
admin_col = db["admin"]
channels_col = db["channels"]
premium_col = db["premium"]
queue_col = db["queue"]
referral_col = db["referral"]
banned_col = db["banned"]

# Constants
ARCHIVE_CHANNEL_ID = -1002098707576
ADMIN_ID = 6988696258
ADMIN_USERNAME = "@Zaky1million"
DAILY_LIMIT = 60
PREMIUM_DAILY_LIMIT = 500
MOVIE_COST = 20
EPISODE_COST = 10
REFERRAL_BONUS = 20
PREMIUM_REQUIRED_REFERRALS = 50

# Initialize Pyrogram client
app = Client("ak_sv_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Language dictionaries
LANGUAGES = {
    "en": {
        "start": "🚀 Welcome to AK.SV Downloader Bot!\n\n"
                "🔍 Search and download movies/series directly from ak.sv\n"
                "🎬 Get high-quality content with direct download links\n\n"
                "Please select your preferred language:",
        "help": "🤖 <b>Bot Help</b>\n\n"
               "🔍 <b>How to use:</b>\n"
               "1. Use /search command or click the search button\n"
               "2. Enter the movie/series name\n"
               "3. Select from results\n"
               "4. Choose quality\n"
               "5. Download starts automatically\n\n"
               "📊 <b>Limits:</b>\n"
               "- Regular users: 60 points daily (20 per movie, 10 per episode)\n"
               "- Premium users: 500 points daily with priority downloads\n\n"
               "💎 <b>Premium Features:</b>\n"
               "- Higher daily limit\n"
               "- Priority in download queue\n"
               "- Ability to forward/save content\n\n"
               "📢 <b>Referral Program:</b>\n"
               "Invite friends using your referral link and get 20 points for each new user!",
        "about": "ℹ️ <b>About AK.SV Downloader Bot</b>\n\n"
                "📅 <b>Version:</b> 2.0\n"
                "👨‍💻 <b>Developer:</b> @Zaky1million\n"
                "🌐 <b>Source:</b> ak.sv\n\n"
                "This bot helps you search and download movies/series from ak.sv directly to Telegram.",
        "select_lang": "Please select your preferred language:",
        "lang_set": "✅ Language set to English",
        "search_prompt": "🔍 Enter the movie/series name you want to search:",
        "search_results": "🎬 <b>Search Results:</b>\n\n",
        "no_results": "❌ No results found. Please try another search term.",
        "movie_info": "🎬 <b>{title}</b>\n\n"
                    "⭐ <b>Rating:</b> {rating}\n"
                    "📅 <b>Year:</b> {year}\n"
                    "🎭 <b>Genres:</b> {genres}\n"
                    "📝 <b>Plot:</b> {plot}\n\n"
                    "Select quality:",
        "series_info": "📺 <b>{title}</b>\n\n"
                     "⭐ <b>Rating:</b> {rating}\n"
                     "📅 <b>Year:</b> {year}\n"
                     "🎭 <b>Genres:</b> {genres}\n"
                     "📝 <b>Plot:</b> {plot}\n\n"
                     "Select episode:",
        "episode_info": "📺 <b>{title}</b>\n\n"
                       "🔄 <b>Episode:</b> {episode}\n"
                       "📅 <b>Added:</b> {date}\n\n"
                       "Select quality:",
        "quality_btn": "📦 {quality} ({size})",
        "download_started": "⬇️ <b>Download started:</b> {title}\n"
                          "📦 <b>Quality:</b> {quality}\n"
                          "📊 <b>Progress:</b> {progress}%\n"
                          "⏳ <b>Time left:</b> {time_left}",
        "download_complete": "✅ <b>Download complete:</b> {title}\n"
                           "📦 <b>Quality:</b> {quality}\n"
                           "📊 <b>Size:</b> {size}",
        "download_error": "❌ <b>Download failed:</b> {title}\n"
                         "⚠️ Please try again later.",
        "daily_limit": "⚠️ <b>Daily Limit Reached</b>\n\n"
                     "You've used your daily points limit (60 points).\n"
                     "Movies cost 20 points, episodes cost 10 points.\n\n"
                     "💎 Upgrade to Premium for higher limits (500 points daily)!\n"
                     "📢 Or invite friends using your referral link to earn more points.",
        "points_info": "📊 <b>Points Information</b>\n\n"
                     "💰 <b>Daily Points:</b> {daily_points}/{daily_limit}\n"
                     "🎬 <b>Movies Downloaded:</b> {movies}\n"
                     "📺 <b>Episodes Downloaded:</b> {episodes}\n"
                     "👥 <b>Referrals:</b> {referrals}\n"
                     "💎 <b>Premium Status:</b> {premium_status}\n\n"
                     "🔗 <b>Your Referral Link:</b> {referral_link}",
        "referral_success": "🎉 <b>New Referral!</b>\n\n"
                          "👤 <b>New User:</b> {new_user}\n"
                          "💰 <b>Bonus Added:</b> +{bonus} points\n"
                          "📊 <b>Total Referrals:</b> {total_refs}\n"
                          "🏆 <b>Total Bonus:</b> {total_bonus} points",
        "premium_info": "💎 <b>Premium Subscription</b>\n\n"
                      "✨ <b>Status:</b> Active\n"
                      "📅 <b>Expires:</b> {expiry_date}\n"
                      "💰 <b>Daily Limit:</b> 500 points\n"
                      "📊 <b>Monthly Limit:</b> 10,000 points\n\n"
                      "Enjoy priority downloads and higher limits!",
        "not_premium": "⚠️ <b>Premium Required</b>\n\n"
                     "This feature is only available for premium users.\n\n"
                     "💎 Contact @Zaky1million to upgrade your account!",
        "join_channel": "📢 <b>Join Required</b>\n\n"
                      "Please join our channel to use this bot:\n"
                      "{channel_link}\n\n"
                      "After joining, click the button below to verify.",
        "channel_verified": "✅ <b>Verification Complete</b>\n\n"
                          "Thank you for joining! You can now use the bot.",
        "admin_menu": "👨‍💻 <b>Admin Panel</b>\n\n"
                    "Select an option:",
        "add_channel": "📢 <b>Add Mandatory Channel</b>\n\n"
                     "Send the channel username or ID (e.g., @channel or -100123456789):",
        "channel_added": "✅ <b>Channel Added</b>\n\n"
                       "Users will now need to join this channel to use the bot.",
        "add_premium": "💎 <b>Add Premium Subscription</b>\n\n"
                     "Send the user ID or username (e.g., 123456789 or @username):",
        "premium_added": "✅ <b>Premium Added</b>\n\n"
                       "User {user} now has premium access until {expiry_date}.",
        "add_points": "💰 <b>Add Points</b>\n\n"
                     "Send the user ID or username and points (e.g., 123456789 100):",
        "points_added": "✅ <b>Points Added</b>\n\n"
                       "User {user} received +{points} points.",
        "search_user": "🔍 <b>Search User</b>\n\n"
                      "Send the user ID or username to search:",
        "user_info": "👤 <b>User Information</b>\n\n"
                    "🆔 <b>ID:</b> {id}\n"
                    "👤 <b>Username:</b> @{username}\n"
                    "🌐 <b>Language:</b> {language}\n"
                    "💰 <b>Points:</b> {points}\n"
                    "🎬 <b>Movies:</b> {movies}\n"
                    "📺 <b>Episodes:</b> {episodes}\n"
                    "👥 <b>Referrals:</b> {referrals}\n"
                    "💎 <b>Premium:</b> {premium}\n"
                    "⏳ <b>Premium Expiry:</b> {premium_expiry}\n"
                    "🚫 <b>Banned:</b> {banned}",
        "ban_user": "🚫 <b>Ban User</b>\n\n"
                   "Are you sure you want to ban this user?\n\n"
                   "👤 <b>User:</b> {user}",
        "user_banned": "✅ <b>User Banned</b>\n\n"
                      "User {user} has been banned from using the bot.",
        "unban_user": "🔓 <b>Unban User</b>\n\n"
                     "Are you sure you want to unban this user?\n\n"
                     "👤 <b>User:</b> {user}",
        "user_unbanned": "✅ <b>User Unbanned</b>\n\n"
                        "User {user} can now use the bot again.",
        "banned_users": "🚫 <b>Banned Users</b>\n\n"
                      "Select a user to unban:",
        "no_banned_users": "✅ <b>No Banned Users</b>\n\n"
                         "There are currently no banned users.",
        "queue_position": "⏳ <b>Download Queue</b>\n\n"
                        "Your position in queue: {position}\n"
                        "Estimated wait time: {time} minutes",
        "download_cancelled": "❌ <b>Download Cancelled</b>\n\n"
                            "Your download has been cancelled.",
        "premium_expired": "⚠️ <b>Premium Expired</b>\n\n"
                          "Your premium subscription has expired.\n\n"
                          "💎 Contact @Zaky1million to renew your subscription!",
        "premium_almost_expired": "⚠️ <b>Premium Expiring Soon</b>\n\n"
                                "Your premium subscription expires in {days} days.\n\n"
                                "💎 Contact @Zaky1million to renew your subscription!",
        "referral_goal": "🎉 <b>Referral Goal Achieved!</b>\n\n"
                       "You've invited {count} users and earned a free premium subscription!\n\n"
                       "💎 <b>Premium Active Until:</b> {expiry_date}",
        "button_search": "🔍 Search",
        "button_help": "ℹ️ Help",
        "button_about": "📝 About",
        "button_points": "💰 Points",
        "button_referral": "👥 Referral",
        "button_premium": "💎 Premium",
        "button_admin": "👨‍💻 Admin",
        "button_cancel": "❌ Cancel",
        "button_confirm": "✅ Confirm",
        "button_back": "🔙 Back",
        "button_next": "▶️ Next",
        "button_previous": "◀️ Previous",
        "button_download": "⬇️ Download",
        "button_cancel_download": "❌ Cancel Download",
        "button_join": "📢 Join Channel",
        "button_verify": "✅ Verify",
        "button_lang_en": "🇬🇧 English",
        "button_lang_ar": "🇸🇦 العربية",
        "button_add_channel": "📢 Add Channel",
        "button_add_premium": "💎 Add Premium",
        "button_add_points": "💰 Add Points",
        "button_search_user": "🔍 Search User",
        "button_banned_users": "🚫 Banned Users",
        "button_ban": "🚫 Ban",
        "button_unban": "🔓 Unban",
        "button_yes": "✅ Yes",
        "button_no": "❌ No"
    },
    "ar": {
        "start": "🚀 مرحبًا بك في بوت تحميل AK.SV!\n\n"
                "🔍 ابحث وحمل الأفلام/المسلسلات مباشرة من ak.sv\n"
                "🎬 احصل على محتوى عالي الجودة مع روابط تحميل مباشرة\n\n"
                "الرجاء اختيار اللغة المفضلة:",
        "help": "🤖 <b>مساعدة البوت</b>\n\n"
               "🔍 <b>طريقة الاستخدام:</b>\n"
               "1. استخدم أمر /search أو اضغط على زر البحث\n"
               "2. أدخل اسم الفيلم/المسلسل\n"
               "3. اختر من النتائج\n"
               "4. اختر الجودة\n"
               "5. سيبدأ التحميل تلقائيًا\n\n"
               "📊 <b>الحدود:</b>\n"
               "- المستخدمون العاديون: 60 نقطة يوميًا (20 لكل فيلم، 10 لكل حلقة)\n"
               "- المستخدمون المميزون: 500 نقطة يوميًا مع أولوية في التحميل\n\n"
               "💎 <b>ميزات الاشتراك المميز:</b>\n"
               "- حد يومي أعلى\n"
               "- أولوية في طابور التحميل\n"
               "- القدرة على إعادة توجيه/حفظ المحتوى\n\n"
               "📢 <b>برنامج الإحالة:</b>\n"
               "قم بدعوة الأصدقاء باستخدام رابط الإحالة الخاص بك واحصل على 20 نقطة لكل مستخدم جديد!",
        "about": "ℹ️ <b>حول بوت تحميل AK.SV</b>\n\n"
                "📅 <b>الإصدار:</b> 2.0\n"
                "👨‍💻 <b>المطور:</b> @Zaky1million\n"
                "🌐 <b>المصدر:</b> ak.sv\n\n"
                "هذا البوت يساعدك في البحث وتحميل الأفلام/المسلسلات من ak.sv مباشرة إلى التليجرام.",
        "select_lang": "الرجاء اختيار اللغة المفضلة:",
        "lang_set": "✅ تم تعيين اللغة إلى العربية",
        "search_prompt": "🔍 أدخل اسم الفيلم/المسلسل الذي تريد البحث عنه:",
        "search_results": "🎬 <b>نتائج البحث:</b>\n\n",
        "no_results": "❌ لم يتم العثور على نتائج. الرجاء المحاولة بمصطلح بحث آخر.",
        "movie_info": "🎬 <b>{title}</b>\n\n"
                    "⭐ <b>التقييم:</b> {rating}\n"
                    "📅 <b>السنة:</b> {year}\n"
                    "🎭 <b>التصنيفات:</b> {genres}\n"
                    "📝 <b>القصة:</b> {plot}\n\n"
                    "اختر الجودة:",
        "series_info": "📺 <b>{title}</b>\n\n"
                     "⭐ <b>التقييم:</b> {rating}\n"
                     "📅 <b>السنة:</b> {year}\n"
                     "🎭 <b>التصنيفات:</b> {genres}\n"
                     "📝 <b>القصة:</b> {plot}\n\n"
                     "اختر الحلقة:",
        "episode_info": "📺 <b>{title}</b>\n\n"
                       "🔄 <b>الحلقة:</b> {episode}\n"
                       "📅 <b>تاريخ الإضافة:</b> {date}\n\n"
                       "اختر الجودة:",
        "quality_btn": "📦 {quality} ({size})",
        "download_started": "⬇️ <b>بدأ التحميل:</b> {title}\n"
                          "📦 <b>الجودة:</b> {quality}\n"
                          "📊 <b>التقدم:</b> {progress}%\n"
                          "⏳ <b>الوقت المتبقي:</b> {time_left}",
        "download_complete": "✅ <b>اكتمل التحميل:</b> {title}\n"
                           "📦 <b>الجودة:</b> {quality}\n"
                           "📊 <b>الحجم:</b> {size}",
        "download_error": "❌ <b>فشل التحميل:</b> {title}\n"
                         "⚠️ يرجى المحاولة مرة أخرى لاحقًا.",
        "daily_limit": "⚠️ <b>تم الوصول إلى الحد اليومي</b>\n\n"
                     "لقد استخدمت حد النقاط اليومي (60 نقطة).\n"
                     "الأفلام تكلف 20 نقطة، الحلقات تكلف 10 نقاط.\n\n"
                     "💎 قم بالترقية إلى الاشتراك المميز لحدود أعلى (500 نقطة يوميًا)!\n"
                     "📢 أو قم بدعوة الأصدقاء باستخدام رابط الإحالة الخاص بك لكسب المزيد من النقاط.",
        "points_info": "📊 <b>معلومات النقاط</b>\n\n"
                     "💰 <b>النقاط اليومية:</b> {daily_points}/{daily_limit}\n"
                     "🎬 <b>الأفلام المحملة:</b> {movies}\n"
                     "📺 <b>الحلقات المحملة:</b> {episodes}\n"
                     "👥 <b>الإحالات:</b> {referrals}\n"
                     "💎 <b>حالة الاشتراك المميز:</b> {premium_status}\n\n"
                     "🔗 <b>رابط الإحالة الخاص بك:</b> {referral_link}",
        "referral_success": "🎉 <b>إحالة جديدة!</b>\n\n"
                          "👤 <b>مستخدم جديد:</b> {new_user}\n"
                          "💰 <b>تمت إضافة المكافأة:</b> +{bonus} نقطة\n"
                          "📊 <b>إجمالي الإحالات:</b> {total_refs}\n"
                          "🏆 <b>إجمالي المكافأة:</b> {total_bonus} نقطة",
        "premium_info": "💎 <b>الاشتراك المميز</b>\n\n"
                      "✨ <b>الحالة:</b> نشط\n"
                      "📅 <b>تاريخ الانتهاء:</b> {expiry_date}\n"
                      "💰 <b>الحد اليومي:</b> 500 نقطة\n"
                      "📊 <b>الحد الشهري:</b> 10,000 نقطة\n\n"
                      "استمتع بأولوية التحميل وحدود أعلى!",
        "not_premium": "⚠️ <b>الاشتراك المميز مطلوب</b>\n\n"
                     "هذه الميزة متاحة فقط للمستخدمين المميزين.\n\n"
                     "💎 تواصل مع @Zaky1million لترقية حسابك!",
        "join_channel": "📢 <b>يجب الانضمام</b>\n\n"
                      "الرجاء الانضمام إلى قناتنا لاستخدام هذا البوت:\n"
                      "{channel_link}\n\n"
                      "بعد الانضمام، اضغط على الزر أدناه للتحقق.",
        "channel_verified": "✅ <b>اكتمل التحقق</b>\n\n"
                          "شكرًا للانضمام! يمكنك الآن استخدام البوت.",
        "admin_menu": "👨‍💻 <b>لوحة المشرف</b>\n\n"
                    "اختر خيارًا:",
        "add_channel": "📢 <b>إضافة قناة إجبارية</b>\n\n"
                     "أرسل اسم المستخدم أو معرف القناة (مثال: @channel أو -100123456789):",
        "channel_added": "✅ <b>تمت إضافة القناة</b>\n\n"
                       "سيحتاج المستخدمون الآن للانضمام إلى هذه القناة لاستخدام البوت.",
        "add_premium": "💎 <b>إضافة اشتراك مميز</b>\n\n"
                     "أرسل معرف المستخدم أو اسم المستخدم (مثال: 123456789 أو @username):",
        "premium_added": "✅ <b>تمت إضافة الاشتراك المميز</b>\n\n"
                       "المستخدم {user} لديه الآن وصول مميز حتى {expiry_date}.",
        "add_points": "💰 <b>إضافة نقاط</b>\n\n"
                     "أرسل معرف المستخدم أو اسم المستخدم والنقاط (مثال: 123456789 100):",
        "points_added": "✅ <b>تمت إضافة النقاط</b>\n\n"
                       "المستخدم {user} حصل على +{points} نقطة.",
        "search_user": "🔍 <b>بحث عن مستخدم</b>\n\n"
                      "أرسل معرف المستخدم أو اسم المستخدم للبحث:",
        "user_info": "👤 <b>معلومات المستخدم</b>\n\n"
                    "🆔 <b>المعرف:</b> {id}\n"
                    "👤 <b>اسم المستخدم:</b> @{username}\n"
                    "🌐 <b>اللغة:</b> {language}\n"
                    "💰 <b>النقاط:</b> {points}\n"
                    "🎬 <b>الأفلام:</b> {movies}\n"
                    "📺 <b>الحلقات:</b> {episodes}\n"
                    "👥 <b>الإحالات:</b> {referrals}\n"
                    "💎 <b>المميز:</b> {premium}\n"
                    "⏳ <b>انتهاء الاشتراك المميز:</b> {premium_expiry}\n"
                    "🚫 <b>محظور:</b> {banned}",
        "ban_user": "🚫 <b>حظر مستخدم</b>\n\n"
                   "هل أنت متأكد أنك تريد حظر هذا المستخدم؟\n\n"
                   "👤 <b>المستخدم:</b> {user}",
        "user_banned": "✅ <b>تم حظر المستخدم</b>\n\n"
                      "المستخدم {user} تم حظره من استخدام البوت.",
        "unban_user": "🔓 <b>إلغاء حظر مستخدم</b>\n\n"
                     "هل أنت متأكد أنك تريد إلغاء حظر هذا المستخدم؟\n\n"
                     "👤 <b>المستخدم:</b> {user}",
        "user_unbanned": "✅ <b>تم إلغاء حظر المستخدم</b>\n\n"
                        "المستخدم {user} يمكنه الآن استخدام البوت مرة أخرى.",
        "banned_users": "🚫 <b>المستخدمون المحظورون</b>\n\n"
                      "اختر مستخدمًا لإلغاء حظره:",
        "no_banned_users": "✅ <b>لا يوجد مستخدمون محظورون</b>\n\n"
                         "لا يوجد مستخدمون محظورون حاليًا.",
        "queue_position": "⏳ <b>طابور التحميل</b>\n\n"
                        "موقعك في الطابور: {position}\n"
                        "الوقت المتوقع للانتظار: {time} دقائق",
        "download_cancelled": "❌ <b>تم إلغاء التحميل</b>\n\n"
                            "تم إلغاء تحميلك.",
        "premium_expired": "⚠️ <b>انتهى الاشتراك المميز</b>\n\n"
                          "انتهت صلاحية اشتراكك المميز.\n\n"
                          "💎 تواصل مع @Zaky1million لتجديد اشتراكك!",
        "premium_almost_expired": "⚠️ <b>الاشتراك المميز على وشك الانتهاء</b>\n\n"
                                "اشتراكك المميز سينتهي خلال {days} أيام.\n\n"
                                "💎 تواصل مع @Zaky1million لتجديد اشتراكك!",
        "referral_goal": "🎉 <b>تم تحقيق هدف الإحالات!</b>\n\n"
                       "لقد قمت بدعوة {count} مستخدم وحصلت على اشتراك مميز مجاني!\n\n"
                       "💎 <b>الاشتراك المميز نشط حتى:</b> {expiry_date}",
        "button_search": "🔍 بحث",
        "button_help": "ℹ️ مساعدة",
        "button_about": "📝 حول",
        "button_points": "💰 نقاط",
        "button_referral": "👥 إحالة",
        "button_premium": "💎 مميز",
        "button_admin": "👨‍💻 مشرف",
        "button_cancel": "❌ إلغاء",
        "button_confirm": "✅ تأكيد",
        "button_back": "🔙 رجوع",
        "button_next": "▶️ التالي",
        "button_previous": "◀️ السابق",
        "button_download": "⬇️ تحميل",
        "button_cancel_download": "❌ إلغاء التحميل",
        "button_join": "📢 الانضمام للقناة",
        "button_verify": "✅ تحقق",
        "button_lang_en": "🇬🇧 English",
        "button_lang_ar": "🇸🇦 العربية",
        "button_add_channel": "📢 إضافة قناة",
        "button_add_premium": "💎 إضافة مميز",
        "button_add_points": "💰 إضافة نقاط",
        "button_search_user": "🔍 بحث عن مستخدم",
        "button_banned_users": "🚫 المستخدمون المحظورون",
        "button_ban": "🚫 حظر",
        "button_unban": "🔓 إلغاء حظر",
        "button_yes": "✅ نعم",
        "button_no": "❌ لا"
    }
}

# Helper functions
def get_user_lang(user_id: int) -> str:
    user = users_col.find_one({"user_id": user_id})
    return user.get("language", "en") if user else "en"

def get_string(user_id: int, key: str, **kwargs) -> str:
    lang = get_user_lang(user_id)
    string = LANGUAGES[lang].get(key, LANGUAGES["en"].get(key, key))
    return string.format(**kwargs) if kwargs else string

def create_keyboard(buttons: List[List[Dict[str, str]]], user_id: int) -> InlineKeyboardMarkup:
    lang = get_user_lang(user_id)
    keyboard = []
    for row in buttons:
        keyboard_row = []
        for button in row:
            text = LANGUAGES[lang].get(button["text"], button["text"])
            callback_data = button.get("callback_data", "")
            url = button.get("url", "")
            if url:
                keyboard_row.append(InlineKeyboardButton(text, url=url))
            else:
                keyboard_row.append(InlineKeyboardButton(text, callback_data=callback_data))
        keyboard.append(keyboard_row)
    return InlineKeyboardMarkup(keyboard)

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def is_premium(user_id: int) -> bool:
    user = users_col.find_one({"user_id": user_id})
    if not user:
        return False
    if user.get("is_premium", False):
        expiry = user.get("premium_expiry")
        if expiry and expiry > datetime.now():
            return True
        else:
            users_col.update_one({"user_id": user_id}, {"$set": {"is_premium": False}})
    return False

def has_daily_points(user_id: int) -> bool:
    user = users_col.find_one({"user_id": user_id})
    if not user:
        return False
    
    # Reset daily points if it's a new day
    last_updated = user.get("last_updated", datetime.now())
    if (datetime.now() - last_updated).days >= 1:
        users_col.update_one(
            {"user_id": user_id},
            {"$set": {"daily_points": 0, "last_updated": datetime.now()}}
        )
        return True
    
    daily_limit = PREMIUM_DAILY_LIMIT if is_premium(user_id) else DAILY_LIMIT
    return user.get("daily_points", 0) < daily_limit

def deduct_points(user_id: int, points: int) -> bool:
    user = users_col.find_one({"user_id": user_id})
    if not user:
        return False
    
    daily_limit = PREMIUM_DAILY_LIMIT if is_premium(user_id) else DAILY_LIMIT
    if user.get("daily_points", 0) + points > daily_limit:
        return False
    
    users_col.update_one(
        {"user_id": user_id},
        {
            "$inc": {"daily_points": points, "total_points": points},
            "$set": {"last_updated": datetime.now()}
        }
    )
    return True

def get_user_points(user_id: int) -> Dict[str, int]:
    user = users_col.find_one({"user_id": user_id})
    if not user:
        return {"daily_points": 0, "total_points": 0, "daily_limit": DAILY_LIMIT}
    
    daily_limit = PREMIUM_DAILY_LIMIT if is_premium(user_id) else DAILY_LIMIT
    return {
        "daily_points": user.get("daily_points", 0),
        "total_points": user.get("total_points", 0),
        "daily_limit": daily_limit
    }

def add_referral(referrer_id: int, referred_id: int) -> bool:
    # Check if this referral already exists
    if referral_col.find_one({"referrer_id": referrer_id, "referred_id": referred_id}):
        return False
    
    # Add the referral
    referral_col.insert_one({
        "referrer_id": referrer_id,
        "referred_id": referred_id,
        "date": datetime.now()
    })
    
    # Update user's referral count and add bonus points
    users_col.update_one(
        {"user_id": referrer_id},
        {
            "$inc": {"referrals": 1, "referral_points": REFERRAL_BONUS},
            "$push": {"referred_users": referred_id}
        }
    )
    
    # Check if user reached premium referral goal
    user = users_col.find_one({"user_id": referrer_id})
    if user and user.get("referrals", 0) >= PREMIUM_REQUIRED_REFERRALS and not is_premium(referrer_id):
        expiry_date = datetime.now() + timedelta(days=30)
        users_col.update_one(
            {"user_id": referrer_id},
            {"$set": {"is_premium": True, "premium_expiry": expiry_date}}
        )
    
    return True

def get_referral_link(user_id: int) -> str:
    return f"https://t.me/{(app.get_me()).username}?start=ref_{user_id}"

def check_mandatory_channels(user_id: int) -> Tuple[bool, List[Dict[str, str]]]:
    channels = list(channels_col.find())
    if not channels:
        return True, []
    
    unjoined_channels = []
    for channel in channels:
        try:
            member = app.get_chat_member(int(channel["channel_id"]), user_id)
            if member.status in [enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.BANNED]:
                unjoined_channels.append({
                    "channel_id": channel["channel_id"],
                    "title": channel.get("title", "Channel"),
                    "username": channel.get("username", "")
                })
        except Exception:
            unjoined_channels.append({
                "channel_id": channel["channel_id"],
                "title": channel.get("title", "Channel"),
                "username": channel.get("username", "")
            })
    
    return len(unjoined_channels) == 0, unjoined_channels

def add_to_queue(user_id: int, callback_data: str) -> int:
    # Premium users don't go in queue
    if is_premium(user_id):
        return 0
    
    # Check if user is already in queue
    existing = queue_col.find_one({"user_id": user_id})
    if existing:
        return existing["position"]
    
    # Get current queue length
    count = queue_col.count_documents({})
    position = count + 1
    
    # Add to queue
    queue_col.insert_one({
        "user_id": user_id,
        "position": position,
        "callback_data": callback_data,
        "added_at": datetime.now()
    })
    
    return position

def remove_from_queue(user_id: int):
    queue_col.delete_one({"user_id": user_id})

def get_queue_position(user_id: int) -> int:
    if is_premium(user_id):
        return 0
    
    user_in_queue = queue_col.find_one({"user_id": user_id})
    if not user_in_queue:
        return 0
    
    # Count how many users are before this one
    position = queue_col.count_documents({
        "position": {"$lt": user_in_queue["position"]}
    }) + 1
    
    return position

def get_estimated_wait_time(position: int) -> int:
    # Average download time is ~3 minutes
    return (position - 1) * 3

def check_cached_download(title: str) -> Union[Dict[str, str], None]:
    return downloads_col.find_one({"title": title})

def add_cached_download(title: str, file_id: str, file_size: int, quality: str):
    downloads_col.update_one(
        {"title": title},
        {
            "$set": {
                "file_id": file_id,
                "file_size": file_size,
                "quality": quality,
                "last_accessed": datetime.now()
            }
        },
        upsert=True
    )

def remove_cached_download(title: str):
    downloads_col.delete_one({"title": title})

# Web scraping functions
async def search_ak_sv(query: str) -> List[Dict[str, str]]:
    url = f"https://ak.sv/search?q={requests.utils.quote(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        items = soup.select('div.entry-box')
        
        for item in items:
            title_elem = item.select_one('h3.entry-title a')
            if not title_elem:
                continue
                
            title = title_elem.text.strip()
            link = title_elem['href']
            
            img_elem = item.select_one('img.lazy')
            image = img_elem['data-src'] if img_elem and 'data-src' in img_elem.attrs else None
            
            rating_elem = item.select_one('span.label.rating')
            rating = rating_elem.text.strip() if rating_elem else "N/A"
            
            quality_elem = item.select_one('span.label.quality')
            quality = quality_elem.text.strip() if quality_elem else "N/A"
            
            badges = item.select('span.badge')
            year = badges[0].text.strip() if badges else "N/A"
            genres = ", ".join([badge.text.strip() for badge in badges[1:]]) if len(badges) > 1 else "N/A"
            
            media_type = "movie" if "/movie/" in link else "series"
            
            results.append({
                "title": title,
                "link": link,
                "image": image,
                "rating": rating,
                "quality": quality,
                "year": year,
                "genres": genres,
                "type": media_type
            })
        
        return results
    
    except Exception as e:
        print(f"Error searching ak.sv: {e}")
        return []

async def get_movie_details(url: str) -> Dict[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        title = soup.select_one('h1.entry-title').text.strip()
        
        img_elem = soup.select_one('div.col-lg-3.col-md-4 img.img-fluid')
        image = img_elem['src'] if img_elem and 'src' in img_elem.attrs else None
        
        rating_elem = soup.select_one('div.font-size-16.text-white.mt-2 img[alt="IMDb"]')
        rating = rating_elem.find_next_sibling(text=True).strip() if rating_elem else "N/A"
        
        info_elems = soup.select('div.font-size-16.text-white.mt-2')
        info = {}
        for elem in info_elems:
            text = elem.text.strip()
            if ":" in text:
                key, value = text.split(":", 1)
                info[key.strip()] = value.strip()
        
        plot_elem = soup.select_one('div.text-white p')
        plot = plot_elem.text.strip() if plot_elem else "N/A"
        
        trailer_elem = soup.select_one('a[data-fancybox]')
        trailer = trailer_elem['href'] if trailer_elem and 'href' in trailer_elem.attrs else None
        
        gallery_elems = soup.select('a[data-fancybox="movie-gallery"]')
        gallery = [elem['href'] for elem in gallery_elems] if gallery_elems else []
        
        # Get download qualities
        qualities = []
        tabs = soup.select('ul.header-tabs.tabs li a')
        tab_contents = soup.select('div.tab-content')
        
        for tab, content in zip(tabs, tab_contents):
            quality = tab.text.strip()
            tab_id = tab['href'].replace('#', '')
            
            download_link = content.select_one(f'div#{tab_id} a.link-download')
            if download_link and 'href' in download_link.attrs:
                size_elem = download_link.select_one('span.font-size-14.mr-auto')
                size = size_elem.text.strip() if size_elem else "N/A"
                
                qualities.append({
                    "quality": quality,
                    "size": size,
                    "link": download_link['href']
                })
        
        return {
            "title": title,
            "image": image,
            "rating": rating,
            "info": info,
            "plot": plot,
            "trailer": trailer,
            "gallery": gallery,
            "qualities": qualities
        }
    
    except Exception as e:
        print(f"Error getting movie details: {e}")
        return {}

async def get_series_details(url: str) -> Dict[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        title = soup.select_one('h1.entry-title').text.strip()
        
        img_elem = soup.select_one('div.col-lg-3.col-md-4 img.img-fluid')
        image = img_elem['src'] if img_elem and 'src' in img_elem.attrs else None
        
        rating_elem = soup.select_one('div.font-size-16.text-white.mt-2 img[alt="IMDb"]')
        rating = rating_elem.find_next_sibling(text=True).strip() if rating_elem else "N/A"
        
        info_elems = soup.select('div.font-size-16.text-white.mt-2')
        info = {}
        for elem in info_elems:
            text = elem.text.strip()
            if ":" in text:
                key, value = text.split(":", 1)
                info[key.strip()] = value.strip()
        
        plot_elem = soup.select_one('div.text-white p')
        plot = plot_elem.text.strip() if plot_elem else "N/A"
        
        trailer_elem = soup.select_one('a[data-fancybox]')
        trailer = trailer_elem['href'] if trailer_elem and 'href' in trailer_elem.attrs else None
        
        gallery_elems = soup.select('a[data-fancybox="movie-gallery"]')
        gallery = [elem['href'] for elem in gallery_elems] if gallery_elems else []
        
        # Get episodes
        episodes = []
        episode_elems = soup.select('div#series-episodes div.bg-primary2')
        
        for ep in episode_elems:
            title_elem = ep.select_one('h2 a')
            if not title_elem:
                continue
                
            ep_title = title_elem.text.strip()
            ep_link = title_elem['href']
            
            img_elem = ep.select_one('img.img-fluid')
            ep_image = img_elem['src'] if img_elem and 'src' in img_elem.attrs else None
            
            date_elem = ep.select_one('p.entry-date')
            ep_date = date_elem.text.strip() if date_elem else "N/A"
            
            episodes.append({
                "title": ep_title,
                "link": ep_link,
                "image": ep_image,
                "date": ep_date
            })
        
        return {
            "title": title,
            "image": image,
            "rating": rating,
            "info": info,
            "plot": plot,
            "trailer": trailer,
            "gallery": gallery,
            "episodes": episodes
        }
    
    except Exception as e:
        print(f"Error getting series details: {e}")
        return {}

async def get_download_link(go_url: str) -> Union[str, None]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        # Step 1: Get intermediate download page from go.ak.sv
        response = requests.get(go_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        download_link = soup.select_one('a.download-link')
        if not download_link or 'href' not in download_link.attrs:
            return None
        
        intermediate_url = download_link['href']
        
        # Step 2: Get direct download link from ak.sv/download
        response = requests.get(intermediate_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        direct_link = soup.select_one('div.btn-loader a.link.btn.btn-light')
        if not direct_link or 'href' not in direct_link.attrs:
            return None
        
        return direct_link['href']
    
    except Exception as e:
        print(f"Error getting download link: {e}")
        return None

# Bot handlers
@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    args = message.text.split()
    
    # Check if user is banned
    if banned_col.find_one({"user_id": user_id}):
        await message.reply(get_string(user_id, "user_banned", user=user_id))
        return
    
    # Check if this is a referral link
    if len(args) > 1 and args[1].startswith("ref_"):
        referrer_id = int(args[1][4:])
        if referrer_id != user_id:
            add_referral(referrer_id, user_id)
            
            # Notify referrer
            try:
                await app.send_message(
                    referrer_id,
                    get_string(referrer_id, "referral_success", 
                             new_user=user_id, 
                             bonus=REFERRAL_BONUS,
                             total_refs=users_col.find_one({"user_id": referrer_id}).get("referrals", 0),
                             total_bonus=users_col.find_one({"user_id": referrer_id}).get("referral_points", 0))
                )
            except Exception:
                pass
    
    # Check if user exists, if not create
    if not users_col.find_one({"user_id": user_id}):
        users_col.insert_one({
            "user_id": user_id,
            "username": message.from_user.username,
            "first_name": message.from_user.first_name,
            "last_name": message.from_user.last_name,
            "language": "en",
            "daily_points": 0,
            "total_points": 0,
            "movies_downloaded": 0,
            "episodes_downloaded": 0,
            "referrals": 0,
            "referral_points": 0,
            "referred_users": [],
            "is_premium": False,
            "premium_expiry": None,
            "last_updated": datetime.now(),
            "joined_at": datetime.now()
        })
    
    # Check mandatory channels
    joined, unjoined_channels = check_mandatory_channels(user_id)
    if not joined:
        buttons = []
        for channel in unjoined_channels:
            if channel.get("username"):
                url = f"https://t.me/{channel['username']}"
            else:
                url = f"tg://resolve?domain={channel['channel_id']}"
            
            buttons.append([{
                "text": get_string(user_id, "button_join"),
                "url": url
            }])
        
        buttons.append([{
            "text": get_string(user_id, "button_verify"),
            "callback_data": "verify_channels"
        }])
        
        await message.reply(
            get_string(user_id, "join_channel", channel_link=unjoined_channels[0].get("username", unjoined_channels[0].get("title", ""))),
            reply_markup=create_keyboard(buttons, user_id)
        )
        return
    
    # Check if language is set
    user = users_col.find_one({"user_id": user_id})
    if not user or "language" not in user:
        buttons = [
            [{"text": "button_lang_en", "callback_data": "set_lang_en"}],
            [{"text": "button_lang_ar", "callback_data": "set_lang_ar"}]
        ]
        await message.reply(
            get_string(user_id, "select_lang"),
            reply_markup=create_keyboard(buttons, user_id)
        )
        return
    
    # Main menu
    buttons = [
        [{"text": "button_search", "callback_data": "search"}],
        [
            {"text": "button_help", "callback_data": "help"},
            {"text": "button_about", "callback_data": "about"}
        ],
        [
            {"text": "button_points", "callback_data": "points"},
            {"text": "button_referral", "callback_data": "referral"}
        ]
    ]
    
    if is_premium(user_id):
        buttons[2].append({"text": "button_premium", "callback_data": "premium_info"})
    
    if is_admin(user_id):
        buttons.append([{"text": "button_admin", "callback_data": "admin_menu"}])
    
    await message.reply(
        get_string(user_id, "start"),
        reply_markup=create_keyboard(buttons, user_id)
    )

@app.on_callback_query(filters.regex("^set_lang_"))
async def set_language(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    lang = callback_query.data.split("_")[-1]
    
    users_col.update_one({"user_id": user_id}, {"$set": {"language": lang}})
    
    await callback_query.answer(get_string(user_id, "lang_set"))
    await start_command(client, callback_query.message)

@app.on_callback_query(filters.regex("^verify_channels$"))
async def verify_channels(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    joined, unjoined_channels = check_mandatory_channels(user_id)
    
    if joined:
        await callback_query.answer(get_string(user_id, "channel_verified"))
        await start_command(client, callback_query.message)
    else:
        await callback_query.answer(get_string(user_id, "join_channel", channel_link=unjoined_channels[0].get("username", unjoined_channels[0].get("title", ""))), show_alert=True)

@app.on_callback_query(filters.regex("^search$"))
async def search_command(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    await callback_query.message.reply(get_string(user_id, "search_prompt"))
    await callback_query.answer()

@app.on_message(filters.text & filters.private & ~filters.command)
async def handle_search(client: Client, message: Message):
    user_id = message.from_user.id
    query = message.text.strip()
    
    # Check if this is a response to search prompt
    if not hasattr(message, "reply_to_message") or not message.reply_to_message or \
       not message.reply_to_message.text or not message.reply_to_message.text.startswith(get_string(user_id, "search_prompt")[:10]):
        return
    
    # Rest of your handler code...
    # Check if user is banned
    if banned_col.find_one({"user_id": user_id}):
        await message.reply(get_string(user_id, "user_banned", user=user_id))
        return
    
    # Check daily points
    if not has_daily_points(user_id):
        buttons = [
            [{"text": "button_premium", "callback_data": "premium_info"}],
            [{"text": "button_points", "callback_data": "points"}]
        ]
        await message.reply(
            get_string(user_id, "daily_limit"),
            reply_markup=create_keyboard(buttons, user_id)
        )
        return
    
    # Show searching message
    msg = await message.reply("🔍 Searching...")
    
    # Perform search
    results = await search_ak_sv(query)
    
    if not results:
        await msg.edit_text(get_string(user_id, "no_results"))
        return
    
    # Prepare results for display
    text = get_string(user_id, "search_results")
    buttons = []
    
    for i, result in enumerate(results[:10]):  # Limit to 10 results
        text += f"{i+1}. {result['title']} ({result['year']}) - {result['rating']}\n"
        buttons.append([{
            "text": f"{i+1}. {result['title']} ({result['year']})",
            "callback_data": f"result_{i}"
        }])
    
    # Add navigation buttons if more than 10 results
    if len(results) > 10:
        buttons.append([
            {"text": "button_previous", "callback_data": "results_prev_0"},
            {"text": "button_next", "callback_data": "results_next_10"}
        ])
    
    # Store results in user data for later reference
    users_col.update_one(
        {"user_id": user_id},
        {"$set": {"search_results": results[:50], "search_query": query}}
    )
    
    await msg.edit_text(text, reply_markup=create_keyboard(buttons, user_id))

@app.on_callback_query(filters.regex("^result_"))
async def show_result(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    result_index = int(callback_query.data.split("_")[1])
    
    # Get user's search results
    user = users_col.find_one({"user_id": user_id})
    if not user or "search_results" not in user:
        await callback_query.answer(get_string(user_id, "no_results"), show_alert=True)
        return
    
    results = user["search_results"]
    if result_index >= len(results):
        await callback_query.answer(get_string(user_id, "no_results"), show_alert=True)
        return
    
    result = results[result_index]
    
    # Check if it's a movie or series
    if result["type"] == "movie":
        # Get movie details
        details = await get_movie_details(result["link"])
        if not details:
            await callback_query.answer(get_string(user_id, "download_error", title=result["title"]), show_alert=True)
            return
        
        # Prepare quality buttons
        buttons = []
        for quality in details["qualities"]:
            buttons.append([{
                "text": get_string(user_id, "quality_btn", quality=quality["quality"], size=quality["size"]),
                "callback_data": f"download_{result_index}_{quality['quality']}"
            }])
        
        buttons.append([{"text": "button_back", "callback_data": "back_to_results"}])
        
        # Send movie info with image
        caption = get_string(user_id, "movie_info",
                           title=details["title"],
                           rating=details["rating"],
                           year=details["info"].get("Year", "N/A"),
                           genres=details["info"].get("Genres", "N/A"),
                           plot=details["plot"])
        
        if details["image"]:
            try:
                await callback_query.message.reply_photo(
                    photo=details["image"],
                    caption=caption,
                    reply_markup=create_keyboard(buttons, user_id)
                )
                await callback_query.message.delete()
            except Exception:
                await callback_query.message.edit_text(
                    caption,
                    reply_markup=create_keyboard(buttons, user_id)
                )
        else:
            await callback_query.message.edit_text(
                caption,
                reply_markup=create_keyboard(buttons, user_id)
            )
    
    else:  # Series
        # Get series details
        details = await get_series_details(result["link"])
        if not details:
            await callback_query.answer(get_string(user_id, "download_error", title=result["title"]), show_alert=True)
            return
        
        # Prepare episode buttons
        buttons = []
        for i, episode in enumerate(details["episodes"][:10]):  # Limit to 10 episodes
            buttons.append([{
                "text": f"{i+1}. {episode['title']}",
                "callback_data": f"episode_{result_index}_{i}"
            }])
        
        # Add navigation buttons if more than 10 episodes
        if len(details["episodes"]) > 10:
            buttons.append([
                {"text": "button_previous", "callback_data": f"episodes_prev_{result_index}_0"},
                {"text": "button_next", "callback_data": f"episodes_next_{result_index}_10"}
            ])
        
        buttons.append([{"text": "button_back", "callback_data": "back_to_results"}])
        
        # Send series info with image
        caption = get_string(user_id, "series_info",
                           title=details["title"],
                           rating=details["rating"],
                           year=details["info"].get("Year", "N/A"),
                           genres=details["info"].get("Genres", "N/A"),
                           plot=details["plot"])
        
        if details["image"]:
            try:
                await callback_query.message.reply_photo(
                    photo=details["image"],
                    caption=caption,
                    reply_markup=create_keyboard(buttons, user_id)
                )
                await callback_query.message.delete()
            except Exception:
                await callback_query.message.edit_text(
                    caption,
                    reply_markup=create_keyboard(buttons, user_id)
                )
        else:
            await callback_query.message.edit_text(
                caption,
                reply_markup=create_keyboard(buttons, user_id)
            )
    
    await callback_query.answer()

@app.on_callback_query(filters.regex("^episode_"))
async def show_episode(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data_parts = callback_query.data.split("_")
    result_index = int(data_parts[1])
    episode_index = int(data_parts[2])
    
    # Get user's search results
    user = users_col.find_one({"user_id": user_id})
    if not user or "search_results" not in user:
        await callback_query.answer(get_string(user_id, "no_results"), show_alert=True)
        return
    
    results = user["search_results"]
    if result_index >= len(results):
        await callback_query.answer(get_string(user_id, "no_results"), show_alert=True)
        return
    
    result = results[result_index]
    
    # Get series details
    details = await get_series_details(result["link"])
    if not details or episode_index >= len(details["episodes"]):
        await callback_query.answer(get_string(user_id, "download_error", title=result["title"]), show_alert=True)
        return
    
    episode = details["episodes"][episode_index]
    
    # Get episode details
    episode_details = await get_movie_details(episode["link"])
    if not episode_details:
        await callback_query.answer(get_string(user_id, "download_error", title=episode["title"]), show_alert=True)
        return
    
    # Prepare quality buttons
    buttons = []
    for quality in episode_details["qualities"]:
        buttons.append([{
            "text": get_string(user_id, "quality_btn", quality=quality["quality"], size=quality["size"]),
            "callback_data": f"download_ep_{result_index}_{episode_index}_{quality['quality']}"
        }])
    
    buttons.append([{"text": "button_back", "callback_data": f"back_to_episodes_{result_index}"}])
    
    # Send episode info with image
    caption = get_string(user_id, "episode_info",
                       title=episode_details["title"],
                       episode=episode["title"],
                       date=episode["date"])
    
    if episode["image"]:
        try:
            await callback_query.message.reply_photo(
                photo=episode["image"],
                caption=caption,
                reply_markup=create_keyboard(buttons, user_id)
            )
            await callback_query.message.delete()
        except Exception:
            await callback_query.message.edit_text(
                caption,
                reply_markup=create_keyboard(buttons, user_id)
            )
    else:
        await callback_query.message.edit_text(
            caption,
            reply_markup=create_keyboard(buttons, user_id)
        )
    
    await callback_query.answer()

@app.on_callback_query(filters.regex("^download_"))
async def handle_download(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data_parts = callback_query.data.split("_")
    
    # Check if user is banned
    if banned_col.find_one({"user_id": user_id}):
        await callback_query.answer(get_string(user_id, "user_banned", user=user_id), show_alert=True)
        return
    
    # Check daily points
    if not has_daily_points(user_id):
        buttons = [
            [{"text": "button_premium", "callback_data": "premium_info"}],
            [{"text": "button_points", "callback_data": "points"}]
        ]
        await callback_query.message.reply(
            get_string(user_id, "daily_limit"),
            reply_markup=create_keyboard(buttons, user_id)
        )
        await callback_query.answer()
        return
    
    # Get user's search results
    user = users_col.find_one({"user_id": user_id})
    if not user or "search_results" not in user:
        await callback_query.answer(get_string(user_id, "no_results"), show_alert=True)
        return
    
    results = user["search_results"]
    
    if data_parts[1] == "ep":  # Episode download
        result_index = int(data_parts[2])
        episode_index = int(data_parts[3])
        quality = "_".join(data_parts[4:])
        
        if result_index >= len(results):
            await callback_query.answer(get_string(user_id, "no_results"), show_alert=True)
            return
        
        result = results[result_index]
        
        # Get series details
        details = await get_series_details(result["link"])
        if not details or episode_index >= len(details["episodes"]):
            await callback_query.answer(get_string(user_id, "download_error", title=result["title"]), show_alert=True)
            return
        
        episode = details["episodes"][episode_index]
        
        # Get episode details
        episode_details = await get_movie_details(episode["link"])
        if not episode_details:
            await callback_query.answer(get_string(user_id, "download_error", title=episode["title"]), show_alert=True)
            return
        
        # Find the selected quality
        selected_quality = None
        for q in episode_details["qualities"]:
            if q["quality"] == quality:
                selected_quality = q
                break
        
        if not selected_quality:
            await callback_query.answer(get_string(user_id, "download_error", title=episode["title"]), show_alert=True)
            return
        
        title = f"{result['title']} - {episode['title']}"
        cost = EPISODE_COST
    
    else:  # Movie download
        result_index = int(data_parts[1])
        quality = "_".join(data_parts[2:])
        
        if result_index >= len(results):
            await callback_query.answer(get_string(user_id, "no_results"), show_alert=True)
            return
        
        result = results[result_index]
        
        # Get movie details
        details = await get_movie_details(result["link"])
        if not details:
            await callback_query.answer(get_string(user_id, "download_error", title=result["title"]), show_alert=True)
            return
        
        # Find the selected quality
        selected_quality = None
        for q in details["qualities"]:
            if q["quality"] == quality:
                selected_quality = q
                break
        
        if not selected_quality:
            await callback_query.answer(get_string(user_id, "download_error", title=result["title"]), show_alert=True)
            return
        
        title = result["title"]
        cost = MOVIE_COST
    
    # Check if already downloaded and cached
    cached = check_cached_download(title)
    if cached and cached["quality"] == quality:
        # Deduct points
        if not deduct_points(user_id, cost):
            await callback_query.answer(get_string(user_id, "daily_limit"), show_alert=True)
            return
        
        # Update download counts
        if data_parts[1] == "ep":
            users_col.update_one({"user_id": user_id}, {"$inc": {"episodes_downloaded": 1}})
        else:
            users_col.update_one({"user_id": user_id}, {"$inc": {"movies_downloaded": 1}})
        
        # Send cached file
        try:
            await callback_query.message.reply_video(
                cached["file_id"],
                caption=get_string(user_id, "download_complete", 
                                title=title, 
                                quality=quality, 
                                size=selected_quality["size"]),
                protect_content=not is_premium(user_id)
            )
            await callback_query.message.delete()
        except Exception as e:
            print(f"Error sending cached file: {e}")
            remove_cached_download(title)
            await callback_query.answer(get_string(user_id, "download_error", title=title), show_alert=True)
        
        await callback_query.answer()
        return
    
    # Add to download queue if not premium
    if not is_premium(user_id):
        position = add_to_queue(user_id, callback_query.data)
        if position > 1:
            wait_time = get_estimated_wait_time(position)
            await callback_query.answer(
                get_string(user_id, "queue_position", position=position, time=wait_time),
                show_alert=True
            )
            return
    
    # Deduct points
    if not deduct_points(user_id, cost):
        await callback_query.answer(get_string(user_id, "daily_limit"), show_alert=True)
        return
    
    # Update download counts
    if data_parts[1] == "ep":
        users_col.update_one({"user_id": user_id}, {"$inc": {"episodes_downloaded": 1}})
    else:
        users_col.update_one({"user_id": user_id}, {"$inc": {"movies_downloaded": 1}})
    
    # Show download started message
    progress_msg = await callback_query.message.reply(
        get_string(user_id, "download_started", 
                  title=title, 
                  quality=quality, 
                  progress=0, 
                  time_left="Calculating...")
    )
    
    # Add cancel button
    cancel_button = create_keyboard([
        [{"text": "button_cancel_download", "callback_data": f"cancel_download_{progress_msg.id}"}]
    ], user_id)
    
    await progress_msg.edit_reply_markup(reply_markup=cancel_button)
    
    # Get download link
    download_link = await get_download_link(selected_quality["link"])
    if not download_link:
        await progress_msg.edit_text(get_string(user_id, "download_error", title=title))
        await callback_query.answer()
        return
    
    # Download the file
    try:
        # Simulate download progress
        for progress in range(10, 101, 10):
            await asyncio.sleep(1)  # Simulate download time
            await progress_msg.edit_text(
                get_string(user_id, "download_started", 
                          title=title, 
                          quality=quality, 
                          progress=progress, 
                          time_left=f"{10 - progress//10} seconds"),
                reply_markup=cancel_button
            )
        
        # Download the actual file
        response = requests.get(download_link, stream=True)
        response.raise_for_status()
        
        # Get file size
        file_size = int(response.headers.get('content-length', 0))
        
        # Save to temporary file
        temp_file = f"temp_{user_id}_{int(time.time())}.mp4"
        with open(temp_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # Upload to Telegram
        await progress_msg.edit_text(get_string(user_id, "download_complete", 
                                   title=title, 
                                   quality=quality, 
                                   size=selected_quality["size"]))
        
        # Send to archive channel first
        archive_msg = await app.send_video(
            ARCHIVE_CHANNEL_ID,
            temp_file,
            caption=f"{title} [{quality}]",
            progress=update_progress,
            progress_args=(progress_msg, user_id, title, quality)
        )
        
        # Send to user
        await callback_query.message.reply_video(
            archive_msg.video.file_id,
            caption=get_string(user_id, "download_complete", 
                            title=title, 
                            quality=quality, 
                            size=selected_quality["size"]),
            protect_content=not is_premium(user_id)
        )
        
        # Cache the download
        add_cached_download(title, archive_msg.video.file_id, file_size, quality)
        
        # Delete temp file
        os.remove(temp_file)
        
        # Delete progress message
        await progress_msg.delete()
        
        # Delete original message if possible
        try:
            await callback_query.message.delete()
        except Exception:
            pass
    
    except Exception as e:
        print(f"Error downloading file: {e}")
        await progress_msg.edit_text(get_string(user_id, "download_error", title=title))
    
    finally:
        # Remove from queue if not premium
        if not is_premium(user_id):
            remove_from_queue(user_id)
        
        # Delete temp file if it exists
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    await callback_query.answer()

async def update_progress(current, total, progress_msg, user_id, title, quality):
    progress = (current / total) * 100
    await progress_msg.edit_text(
        get_string(user_id, "download_started", 
                  title=title, 
                  quality=quality, 
                  progress=int(progress), 
                  time_left="Calculating...")
    )

@app.on_callback_query(filters.regex("^cancel_download_"))
async def cancel_download(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    msg_id = int(callback_query.data.split("_")[-1])
    
    # Find the progress message
    try:
        await app.delete_messages(user_id, msg_id)
    except Exception:
        pass
    
    # Remove from queue if not premium
    if not is_premium(user_id):
        remove_from_queue(user_id)
    
    await callback_query.answer(get_string(user_id, "download_cancelled"))

@app.on_callback_query(filters.regex("^back_to_"))
async def back_to_results(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data_parts = callback_query.data.split("_")
    
    if data_parts[2] == "results":  # Back to search results
        # Get user's search results
        user = users_col.find_one({"user_id": user_id})
        if not user or "search_results" not in user or "search_query" not in user:
            await callback_query.answer(get_string(user_id, "no_results"), show_alert=True)
            return
        
        results = user["search_results"]
        query = user["search_query"]
        
        # Prepare results for display
        text = get_string(user_id, "search_results")
        buttons = []
        
        for i, result in enumerate(results[:10]):  # Limit to 10 results
            text += f"{i+1}. {result['title']} ({result['year']}) - {result['rating']}\n"
            buttons.append([{
                "text": f"{i+1}. {result['title']} ({result['year']})",
                "callback_data": f"result_{i}"
            }])
        
        # Add navigation buttons if more than 10 results
        if len(results) > 10:
            buttons.append([
                {"text": "button_previous", "callback_data": "results_prev_0"},
                {"text": "button_next", "callback_data": "results_next_10"}
            ])
        
        await callback_query.message.edit_text(text, reply_markup=create_keyboard(buttons, user_id))
    
    elif data_parts[2] == "episodes":  # Back to episodes list
        result_index = int(data_parts[3])
        
        # Get user's search results
        user = users_col.find_one({"user_id": user_id})
        if not user or "search_results" not in user:
            await callback_query.answer(get_string(user_id, "no_results"), show_alert=True)
            return
        
        results = user["search_results"]
        if result_index >= len(results):
            await callback_query.answer(get_string(user_id, "no_results"), show_alert=True)
            return
        
        result = results[result_index]
        
        # Get series details
        details = await get_series_details(result["link"])
        if not details:
            await callback_query.answer(get_string(user_id, "download_error", title=result["title"]), show_alert=True)
            return
        
        # Prepare episode buttons
        buttons = []
        for i, episode in enumerate(details["episodes"][:10]):  # Limit to 10 episodes
            buttons.append([{
                "text": f"{i+1}. {episode['title']}",
                "callback_data": f"episode_{result_index}_{i}"
            }])
        
        # Add navigation buttons if more than 10 episodes
        if len(details["episodes"]) > 10:
            buttons.append([
                {"text": "button_previous", "callback_data": f"episodes_prev_{result_index}_0"},
                {"text": "button_next", "callback_data": f"episodes_next_{result_index}_10"}
            ])
        
        buttons.append([{"text": "button_back", "callback_data": "back_to_results"}])
        
        # Edit message
        caption = get_string(user_id, "series_info",
                           title=details["title"],
                           rating=details["rating"],
                           year=details["info"].get("Year", "N/A"),
                           genres=details["info"].get("Genres", "N/A"),
                           plot=details["plot"])
        
        if details["image"]:
            try:
                await callback_query.message.reply_photo(
                    photo=details["image"],
                    caption=caption,
                    reply_markup=create_keyboard(buttons, user_id)
                )
                await callback_query.message.delete()
            except Exception:
                await callback_query.message.edit_text(
                    caption,
                    reply_markup=create_keyboard(buttons, user_id)
                )
        else:
            await callback_query.message.edit_text(
                caption,
                reply_markup=create_keyboard(buttons, user_id)
            )
    
    await callback_query.answer()

@app.on_callback_query(filters.regex("^help$"))
async def help_command(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    buttons = [
        [{"text": "button_premium", "callback_data": "premium_info"}],
        [{"text": "button_back", "callback_data": "back_to_start"}]
    ]
    await callback_query.message.edit_text(
        get_string(user_id, "help"),
        reply_markup=create_keyboard(buttons, user_id)
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex("^about$"))
async def about_command(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    buttons = [
        [{"text": "button_back", "callback_data": "back_to_start"}]
    ]
    await callback_query.message.edit_text(
        get_string(user_id, "about"),
        reply_markup=create_keyboard(buttons, user_id)
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex("^points$"))
async def points_command(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    points = get_user_points(user_id)
    
    buttons = [
        [{"text": "button_referral", "callback_data": "referral"}],
        [{"text": "button_premium", "callback_data": "premium_info"}],
        [{"text": "button_back", "callback_data": "back_to_start"}]
    ]
    
    await callback_query.message.edit_text(
        get_string(user_id, "points_info",
                  daily_points=points["daily_points"],
                  daily_limit=points["daily_limit"],
                  movies=users_col.find_one({"user_id": user_id}).get("movies_downloaded", 0),
                  episodes=users_col.find_one({"user_id": user_id}).get("episodes_downloaded", 0),
                  referrals=users_col.find_one({"user_id": user_id}).get("referrals", 0),
                  premium_status="Active" if is_premium(user_id) else "Inactive",
                  referral_link=get_referral_link(user_id)),
        reply_markup=create_keyboard(buttons, user_id)
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex("^referral$"))
async def referral_command(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    user = users_col.find_one({"user_id": user_id})
    
    buttons = [
        [{"text": "button_back", "callback_data": "back_to_start"}]
    ]
    
    await callback_query.message.edit_text(
        get_string(user_id, "points_info",
                  daily_points=user.get("daily_points", 0),
                  daily_limit=PREMIUM_DAILY_LIMIT if is_premium(user_id) else DAILY_LIMIT,
                  movies=user.get("movies_downloaded", 0),
                  episodes=user.get("episodes_downloaded", 0),
                  referrals=user.get("referrals", 0),
                  premium_status="Active" if is_premium(user_id) else "Inactive",
                  referral_link=get_referral_link(user_id)),
        reply_markup=create_keyboard(buttons, user_id)
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex("^premium_info$"))
async def premium_info_command(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    if is_premium(user_id):
        user = users_col.find_one({"user_id": user_id})
        expiry_date = user["premium_expiry"].strftime("%Y-%m-%d") if user.get("premium_expiry") else "N/A"
        
        buttons = [
            [{"text": "button_back", "callback_data": "back_to_start"}]
        ]
        
        await callback_query.message.edit_text(
            get_string(user_id, "premium_info", expiry_date=expiry_date),
            reply_markup=create_keyboard(buttons, user_id)
        )
    else:
        buttons = [
            [{"text": "Contact Admin", "url": f"https://t.me/{ADMIN_USERNAME[1:]}"}],
            [{"text": "button_back", "callback_data": "back_to_start"}]
        ]
        
        await callback_query.message.edit_text(
            get_string(user_id, "not_premium"),
            reply_markup=create_keyboard(buttons, user_id)
        )
    
    await callback_query.answer()

@app.on_callback_query(filters.regex("^admin_menu$"))
async def admin_menu(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    if not is_admin(user_id):
        await callback_query.answer(get_string(user_id, "not_premium"), show_alert=True)
        return
    
    buttons = [
        [{"text": "button_add_channel", "callback_data": "add_channel"}],
        [{"text": "button_add_premium", "callback_data": "add_premium"}],
        [{"text": "button_add_points", "callback_data": "add_points"}],
        [{"text": "button_search_user", "callback_data": "search_user"}],
        [{"text": "button_banned_users", "callback_data": "banned_users"}],
        [{"text": "button_back", "callback_data": "back_to_start"}]
    ]
    
    await callback_query.message.edit_text(
        get_string(user_id, "admin_menu"),
        reply_markup=create_keyboard(buttons, user_id)
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex("^add_channel$"))
async def add_channel_command(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    if not is_admin(user_id):
        await callback_query.answer(get_string(user_id, "not_premium"), show_alert=True)
        return
    
    await callback_query.message.reply(get_string(user_id, "add_channel"))
    await callback_query.answer()

@app.on_message(filters.text & filters.regex(r'^(@|-\d+)') & filters.private & filters.user(ADMIN_ID))
async def handle_add_channel(client: Client, message: Message):
    user_id = message.from_user.id
    channel_input = message.text.strip()
    
    try:
        if channel_input.startswith('@'):
            chat = await app.get_chat(channel_input)
        else:
            chat = await app.get_chat(int(channel_input))
        
        channels_col.insert_one({
            "channel_id": str(chat.id),
            "title": chat.title,
            "username": chat.username,
            "added_by": user_id,
            "added_at": datetime.now()
        })
        
        await message.reply(get_string(user_id, "channel_added"))
    except Exception as e:
        await message.reply(f"Error adding channel: {e}")

@app.on_callback_query(filters.regex("^add_premium$"))
async def add_premium_command(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    if not is_admin(user_id):
        await callback_query.answer(get_string(user_id, "not_premium"), show_alert=True)
        return
    
    await callback_query.message.reply(get_string(user_id, "add_premium"))
    await callback_query.answer()

@app.on_message(filters.text & filters.regex(r'^(@|\d+)') & filters.private & filters.user(ADMIN_ID))
async def handle_add_premium(client: Client, message: Message):
    user_id = message.from_user.id
    user_input = message.text.strip()
    
    try:
        if user_input.startswith('@'):
            user = await app.get_users(user_input)
        else:
            user = await app.get_users(int(user_input))
        
        expiry_date = datetime.now() + timedelta(days=30)
        users_col.update_one(
            {"user_id": user.id},
            {"$set": {"is_premium": True, "premium_expiry": expiry_date}}
        )
        
        await message.reply(get_string(user_id, "premium_added", user=user.mention, expiry_date=expiry_date.strftime("%Y-%m-%d")))
        
        # Notify user
        try:
            await app.send_message(
                user.id,
                get_string(user.id, "premium_info", expiry_date=expiry_date.strftime("%Y-%m-%d"))
            )
        except Exception:
            pass
    except Exception as e:
        await message.reply(f"Error adding premium: {e}")

@app.on_callback_query(filters.regex("^add_points$"))
async def add_points_command(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    if not is_admin(user_id):
        await callback_query.answer(get_string(user_id, "not_premium"), show_alert=True)
        return
    
    await callback_query.message.reply(get_string(user_id, "add_points"))
    await callback_query.answer()

@app.on_message(filters.text & filters.regex(r'^(@|\d+)\s+\d+$') & filters.private & filters.user(ADMIN_ID))
async def handle_add_points(client: Client, message: Message):
    user_id = message.from_user.id
    parts = message.text.strip().split()
    
    try:
        if parts[0].startswith('@'):
            user = await app.get_users(parts[0])
        else:
            user = await app.get_users(int(parts[0]))
        
        points = int(parts[1])
        users_col.update_one(
            {"user_id": user.id},
            {"$inc": {"total_points": points}}
        )
        
        await message.reply(get_string(user_id, "points_added", user=user.mention, points=points))
        
        # Notify user
        try:
            await app.send_message(
                user.id,
                get_string(user.id, "points_info",
                          daily_points=users_col.find_one({"user_id": user.id}).get("daily_points", 0),
                          daily_limit=PREMIUM_DAILY_LIMIT if is_premium(user.id) else DAILY_LIMIT,
                          movies=users_col.find_one({"user_id": user.id}).get("movies_downloaded", 0),
                          episodes=users_col.find_one({"user_id": user.id}).get("episodes_downloaded", 0),
                          referrals=users_col.find_one({"user_id": user.id}).get("referrals", 0),
                          premium_status="Active" if is_premium(user.id) else "Inactive",
                          referral_link=get_referral_link(user.id)))
        except Exception:
            pass
    except Exception as e:
        await message.reply(f"Error adding points: {e}")

@app.on_callback_query(filters.regex("^search_user$"))
async def search_user_command(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    if not is_admin(user_id):
        await callback_query.answer(get_string(user_id, "not_premium"), show_alert=True)
        return
    
    await callback_query.message.reply(get_string(user_id, "search_user"))
    await callback_query.answer()

@app.on_message(filters.text & filters.regex(r'^(@|\d+)') & filters.private & filters.user(ADMIN_ID))
async def handle_search_user(client: Client, message: Message):
    user_id = message.from_user.id
    user_input = message.text.strip()
    
    try:
        if user_input.startswith('@'):
            user = await app.get_users(user_input)
        else:
            user = await app.get_users(int(user_input))
        
        user_data = users_col.find_one({"user_id": user.id})
        if not user_data:
            await message.reply("User not found in database.")
            return
        
        premium_expiry = user_data.get("premium_expiry", "N/A")
        if premium_expiry != "N/A":
            premium_expiry = premium_expiry.strftime("%Y-%m-%d")
        
        await message.reply(get_string(user_id, "user_info",
                           id=user.id,
                           username=user.username or "N/A",
                           language=user_data.get("language", "en"),
                           points=user_data.get("total_points", 0),
                           movies=user_data.get("movies_downloaded", 0),
                           episodes=user_data.get("episodes_downloaded", 0),
                           referrals=user_data.get("referrals", 0),
                           premium="Yes" if user_data.get("is_premium", False) else "No",
                           premium_expiry=premium_expiry,
                           banned="Yes" if banned_col.find_one({"user_id": user.id}) else "No"))
        
        # Add ban/unban button
        if banned_col.find_one({"user_id": user.id}):
            buttons = [[{"text": "button_unban", "callback_data": f"unban_{user.id}"}]]
        else:
            buttons = [[{"text": "button_ban", "callback_data": f"ban_{user.id}"}]]
        
        await message.reply(
            get_string(user_id, "ban_user", user=user.mention) if not banned_col.find_one({"user_id": user.id}) else get_string(user_id, "unban_user", user=user.mention),
            reply_markup=create_keyboard(buttons, user_id)
        )
    except Exception as e:
        await message.reply(f"Error searching user: {e}")

@app.on_callback_query(filters.regex("^banned_users$"))
async def banned_users_command(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    if not is_admin(user_id):
        await callback_query.answer(get_string(user_id, "not_premium"), show_alert=True)
        return
    
    banned_users = list(banned_col.find())
    if not banned_users:
        await callback_query.message.edit_text(
            get_string(user_id, "no_banned_users"),
            reply_markup=create_keyboard([[{"text": "button_back", "callback_data": "admin_menu"}]], user_id)
        )
        await callback_query.answer()
        return
    
    buttons = []
    for user in banned_users[:10]:  # Limit to 10 users per page
        try:
            tg_user = await app.get_users(user["user_id"])
            buttons.append([{
                "text": tg_user.first_name,
                "callback_data": f"unban_{user['user_id']}"
            }])
        except Exception:
            buttons.append([{
                "text": str(user["user_id"]),
                "callback_data": f"unban_{user['user_id']}"
            }])
    
    buttons.append([{"text": "button_back", "callback_data": "admin_menu"}])
    
    await callback_query.message.edit_text(
        get_string(user_id, "banned_users"),
        reply_markup=create_keyboard(buttons, user_id)
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex("^ban_"))
async def ban_user_command(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    target_user_id = int(callback_query.data.split("_")[1])
    
    if not is_admin(user_id):
        await callback_query.answer(get_string(user_id, "not_premium"), show_alert=True)
        return
    
    banned_col.insert_one({
        "user_id": target_user_id,
        "banned_by": user_id,
        "banned_at": datetime.now()
    })
    
    try:
        target_user = await app.get_users(target_user_id)
        await callback_query.message.edit_text(
            get_string(user_id, "user_banned", user=target_user.mention),
            reply_markup=create_keyboard([[{"text": "button_back", "callback_data": "admin_menu"}]], user_id)
        )
    except Exception:
        await callback_query.message.edit_text(
            get_string(user_id, "user_banned", user=target_user_id),
            reply_markup=create_keyboard([[{"text": "button_back", "callback_data": "admin_menu"}]], user_id)
        )
    
    await callback_query.answer()

@app.on_callback_query(filters.regex("^unban_"))
async def unban_user_command(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    target_user_id = int(callback_query.data.split("_")[1])
    
    if not is_admin(user_id):
        await callback_query.answer(get_string(user_id, "not_premium"), show_alert=True)
        return
    
    banned_col.delete_one({"user_id": target_user_id})
    
    try:
        target_user = await app.get_users(target_user_id)
        await callback_query.message.edit_text(
            get_string(user_id, "user_unbanned", user=target_user.mention),
            reply_markup=create_keyboard([[{"text": "button_back", "callback_data": "admin_menu"}]], user_id)
        )
    except Exception:
        await callback_query.message.edit_text(
            get_string(user_id, "user_unbanned", user=target_user_id),
            reply_markup=create_keyboard([[{"text": "button_back", "callback_data": "admin_menu"}]], user_id)
        )
    
    await callback_query.answer()

@app.on_callback_query(filters.regex("^back_to_start$"))
async def back_to_start(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    buttons = [
        [{"text": "button_search", "callback_data": "search"}],
        [
            {"text": "button_help", "callback_data": "help"},
            {"text": "button_about", "callback_data": "about"}
        ],
        [
            {"text": "button_points", "callback_data": "points"},
            {"text": "button_referral", "callback_data": "referral"}
        ]
    ]
    
    if is_premium(user_id):
        buttons[2].append({"text": "button_premium", "callback_data": "premium_info"})
    
    if is_admin(user_id):
        buttons.append([{"text": "button_admin", "callback_data": "admin_menu"}])
    
    await callback_query.message.edit_text(
        get_string(user_id, "start"),
        reply_markup=create_keyboard(buttons, user_id)
    )
    await callback_query.answer()

# Start the bot
print("Bot is running...")
app.run()
