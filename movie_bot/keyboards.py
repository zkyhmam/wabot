from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from typing import Dict, Any
import data

def build_main_keyboard(media_id: str, media: Dict[str, Any]) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("➕ إضافة رابط", callback_data=f"add_link_{media_id}"),
            InlineKeyboardButton("🖼️ صورة أخرى", callback_data=f"another_image_{media_id}"),
        ],
        [InlineKeyboardButton("✏️ تغيير الرمز", callback_data=f"change_emoji_{media_id}")],
    ]
    if media.get('link'):
        keyboard[0][0] = InlineKeyboardButton("🔄 تغيير الرابط", callback_data=f"add_link_{media_id}")

    return InlineKeyboardMarkup(keyboard)

def build_admin_keyboard() -> InlineKeyboardMarkup:
      keyboard = [
            [InlineKeyboardButton("➕ إضافة قناة اشتراك إجباري", callback_data="admin_add_channel")],
            [InlineKeyboardButton("✏️ تعديل رسالة البداية", callback_data="admin_edit_start_message")],
            [InlineKeyboardButton("🖼️ تغيير صورة البداية", callback_data="admin_change_start_image")],
            [InlineKeyboardButton("📊 إحصائيات البوت", callback_data="admin_stats")],
            [InlineKeyboardButton("➕ إضافة مشرف", callback_data="admin_add_admin")]
        ]
      return InlineKeyboardMarkup(keyboard)

def build_subscription_keyboard(channels) -> InlineKeyboardMarkup:
    keyboard = []
    for channel in channels:
            keyboard.append([InlineKeyboardButton(f"📢 {channel['title']}", url=channel['url'])])

    keyboard.append([InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subscription")])
    return InlineKeyboardMarkup(keyboard)
