import random
import string
import re
from typing import Dict, Any
from telegram.ext import CallbackContext
from config import config
import logging

logger = logging.getLogger(__name__)

def generate_unique_id(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def is_admin(user_id):
    return user_id in config.ADMIN_IDS

def get_emoji_options():
    emojis = ["💭", "👁️", "🎬", "🍿", "🎞️", "📺", "🎦", "🔍", "📽️", "🎥"]
    return emojis

def extract_url(text):
    url_pattern = r'(https?://\S+)'
    match = re.search(url_pattern, text)
    return match.group(1) if match else None

async def check_user_subscription(user_id, context: CallbackContext):
    if not config.FORCED_CHANNELS:
        return True

    for channel in config.FORCED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=channel['id'], user_id=user_id)
            status = member.status
            if status in ['creator', 'administrator', 'member']:
                continue
            else:
                return False
        except Exception as e:
            logger.error(f"خطأ في التحقق من اشتراك المستخدم: {e}")
            continue

    return True

def format_media_message(media_data: Dict[str, Any], emoji: str = "💭") -> str:
    # الأولوية للعناوين العربية
    title = media_data.get('title') or media_data.get('name', '')
    original_title = media_data.get('original_title') or media_data.get('original_name', '')
    
    # إذا كان العنوان العربي غير متوفر
    if not title or title == original_title:
        title = original_title
        original_title = ""
    
    overview = media_data.get('overview', 'معلومات غير متوفرة')
    
    # بناء الرسالة
    message = f"<b>{title}</b>"
    if original_title:
        message += f" | {original_title}"
    
    message += f"\n\n{overview}\n\n{emoji} للمشاهدة اضغط هنا"
    return message
