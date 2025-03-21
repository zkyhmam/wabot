import os
import logging
import asyncio
from typing import Dict, List, Set, Union, Optional, Tuple
import re
import json
from datetime import datetime, timedelta
from telethon import TelegramClient, events, sync
from telethon.tl.types import Channel, Chat, User, Message, PeerChannel, PeerChat, InputPeerChannel, MessageMediaUnsupported
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import ChannelParticipantAdmin, ChannelParticipantCreator
from telethon.errors import ChatAdminRequiredError, ChannelPrivateError, UserNotParticipantError, MessageNotModifiedError, ChatRestrictedError

import google.generativeai as genai

from utils.config_utils import load_config, save_config
from utils.search_utils import generate_name_variations, get_search_keywords, search_movie_in_channel, search_movie_monitored, search_by_hashtags, search_movie_expanded, search_movie, search_movie_everywhere_video
from utils.telegram_utils import is_admin, check_bot_admin_status, process_and_forward_message, process_and_forward_message_video, transfer_channel_content, start_monitoring_channel, stop_monitoring_channel, monitor_channel_task, is_forwardable_chat, process_video_result
from utils.hashtag_utils import generate_hashtag_variations_util
from utils.gemini_utils import recommend_movies_gemini_util

from commands import admin_commands, channel_commands, group_commands, monitoring_commands, search_commands, settings_commands, status_commands, ai_commands


logger = logging.getLogger(__name__)

# --- معلومات API ---
API_ID = 25713843
API_HASH = "311352d08811e7f5136dfb27f71014c1"
PHONE_NUMBER = "+201280779419" #  <--  تم إضافة الرقم الافتراضي هنا

# --- معلومات الأدمن ---
ADMIN_USERNAME = "Zaky1million"
ADMIN_ID = 6988696258

# --- مسارات الملفات ---
CONFIG_FILE = "config.json"

# --- تحديد وقت الانتظار بين عمليات البحث لتجنب التحديد ---
SEARCH_COOLDOWN = 1  # ثانية
# --- زيادة عدد النتائج للبحث ---
SEARCH_LIMIT = 15
# ---  وقت انتظار المراقبة بين الرسائل ---
CATCH_COOLDOWN = 5 # ثواني

# --- الحد الأقصى لطول رسالة تيليجرام ---
TELEGRAM_MESSAGE_LIMIT = 4096

# --- Gemini API Token ---
GEMINI_API_TOKEN = "AIzaSyC-3PFCoASRS8WpppTtbqsR599R9GdrS_I" #  <-- هنخليها موجودة عشان الردود الطبيعية


class MovieBot:
    def __init__(self):
        self.client = TelegramClient('user_bot_session', API_ID, API_HASH)
        self.config = load_config(CONFIG_FILE) # استخدام دالة التحميل من utils
        self.search_lock = asyncio.Lock()  # للتحكم في تزامن عمليات البحث
        self.share_lock = asyncio.Lock() #  قفل لتزامن عمليات الشير والمراقبة
        self.monitoring_tasks: Dict[Tuple[int, int], asyncio.Task] = {} # قاموس لتتبع مهام المراقبة النشطة

        # --- تهيئة Gemini للردود الطبيعية بس ---
        genai.configure(api_key=GEMINI_API_TOKEN)
        self.gemini_model = genai.GenerativeModel('models/gemini-2.0-pro-exp')

        # --- ربط الدوال المساعدة بالـ instance ---
        self.generate_name_variations = generate_name_variations
        self.get_search_keywords = get_search_keywords
        self.search_movie_in_channel = search_movie_in_channel
        self.search_movie_monitored = search_movie_monitored
        self.search_by_hashtags = search_by_hashtags
        self.search_movie_expanded = search_movie_expanded
        self.search_movie = search_movie
        self.search_movie_everywhere_video = search_movie_everywhere_video
        self.is_admin = is_admin
        self.check_bot_admin_status = check_bot_admin_status
        self.process_and_forward_message = process_and_forward_message
        self.process_and_forward_message_video = process_and_forward_message_video
        self.transfer_channel_content = transfer_channel_content
        self.start_monitoring_channel = start_monitoring_channel
        self.stop_monitoring_channel = stop_monitoring_channel
        self.monitor_channel_task = monitor_channel_task
        self.is_forwardable_chat = is_forwardable_chat
        self.process_video_result = process_video_result
        self.generate_hashtag_variations = generate_hashtag_variations_util
        self.recommend_movies_gemini = recommend_movies_gemini_util
        self.save_config = lambda: save_config(self.config, CONFIG_FILE) #  تعديل حفظ الإعدادات لاستخدام utils

    async def initialize(self):
        """تهيئة العميل وتسجيل معالجات الأحداث"""
        #  هنا طلب رقم الهاتف من الكونسول
        while True: # <---  إضافة لوب عشان نعيد طلب الرقم لو المستخدم مدخلش حاجة
            phone_number = input("من فضلك ادخل رقم هاتفك: ") #  طلب الرقم من المستخدم
            if not phone_number.strip(): #  لو المستخدم ضغط انتر بدون ما يدخل رقم
                phone_number = PHONE_NUMBER #  <-- استخدام الرقم الافتراضي هنا
                print(f"تم استخدام الرقم الافتراضي: {phone_number}") #  تنبيه المستخدم بالرقم الافتراضي
                break #  نخرج من اللوب بعد استخدام الرقم الافتراضي
            else:
                break #  لو الرقم تمام، نخرج من اللوب
        await self.client.start(phone=phone_number)
        logger.info("تم تشغيل البوت بحساب المستخدم...")

        logger.info("تم تشغيل البوت...")

        # --- تسجيل معالجات الأوامر من ملفات الأوامر ---
        admin_commands.register_handlers(self)
        channel_commands.register_handlers(self)
        group_commands.register_handlers(self)
        monitoring_commands.register_handlers(self)
        search_commands.register_handlers(self)
        settings_commands.register_handlers(self)
        status_commands.register_handlers(self)
        ai_commands.register_handlers(self)


        # --- تحميل مهام المراقبة النشطة عند بدء التشغيل ---
        logger.info("جاري تحميل مهام المراقبة النشطة من الإعدادات...")
        for monitor_info in self.config["monitored_shares"]:
            try:
                source_channel_entity = await self.client.get_entity(monitor_info["source_channel_id"])
                destination_channel_entity = await self.client.get_entity(monitor_info["destination_channel_id"])
                task = asyncio.create_task(self.monitor_channel_task(source_channel_entity, destination_channel_entity)) #  إعادة تشغيل مهمة المراقبة
                self.monitoring_tasks[(source_channel_entity.id, destination_channel_entity.id)] = task #  حفظ المهمة في القاموس
                logger.info(f"تم إعادة تشغيل مهمة مراقبة قناة '{source_channel_entity.title}' -> '{destination_channel_entity.title}'")
            except Exception as e:
                logger.error(f"خطأ في إعادة تشغيل مهمة المراقبة من الإعدادات: {e}")


        logger.info("بدء معالجة الأحداث...")
        await self.client.run_until_disconnected()

    async def run(self):
        """تشغيل البوت"""
        try:
            await self.initialize()
        except Exception as e:
            logger.error(f"فشل تشغيل البوت: {str(e)}")
        finally:
            if self.client.is_connected():
                await self.client.disconnect()
                logger.info("تم إيقاف البوت.")

