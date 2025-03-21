import re
import os
from datetime import datetime
from telethon import events

ADMIN_ID = 6988696258 #  Make sure this is consistent across files if needed
CONFIG_FILE = "config.json" # Make sure this is consistent across files if needed


def register_handlers(bot):
    """تسجيل معالج أمر الحالة"""
    @bot.client.on(events.NewMessage(pattern=re.compile(r'^st$', re.IGNORECASE), incoming=True, from_users=ADMIN_ID))
    async def status_handler(event):
        """عرض حالة البوت"""
        user_id = event.sender_id

        if not await bot.is_admin(user_id):
            return

        num_channels = len(bot.config["monitored_channels"])
        num_groups = len(bot.config["allowed_groups"])
        last_config_update = datetime.fromtimestamp(os.path.getmtime(CONFIG_FILE)).strftime('%Y-%m-%d %H:%M:%S') if os.path.exists(CONFIG_FILE) else "مش عارف أجيب تاريخ التحديث"

        status_message = (
            "**حالة البوت دلوقتي**\n\n"
            f"اسم البوت: Zaky AI\n" # <---  تم تعديل اسم البوت هنا
            f"عدد القنوات اللي بتم مراقبتها: {num_channels}\n"
            f"عدد الجروبات المسموح بيها: {num_groups}\n"
            f"آخر تحديث للإعدادات: {last_config_update}\n"
            f"طريقة البحث: البحث المتعدد في القنوات (كلمات وهاشتاجات) + بحث موسع في كل الدردشات + تم إلغاء نظام حفظ نتائج البحث (دلوقتي البحث بيتم في كل مرة من جديد)\n" # <--- تم تعديل هنا
            f"عدد الرسايل اللي بتتراجع: 200 رسالة للبحث بالكلمات، 50 رسالة للبحث بالهاشتاج\n"
            f"عدد سطور البحث: {bot.config['search_lines_limit']} سطر\n"
            f"البحث في الرسالة كاملة: {'متفعل' if bot.config['search_full_message'] else 'متعطل'}\n"
            f"Gemini AI: **متاح للردود الطبيعية فقط** ✅\n" # <--- تم تعديل هنا
            "**أوامر جديدة:**\n" # <---  إضافة قسم الأوامر الجديدة في الحالة
            "  - `fch+` (إضافة قناة عن طريق التحويل)\n" # <--- إضافة الأمر الجديد في الحالة
            "  - `share [source] to [destination]`\n"
            "  - `share [source] to [destination] -catch on`\n"
            "  - `share [source] to [destination] -catch off`\n"
            "  - `s [اسم الفيلم]` (بحث فيديو في كل الشاتات)\n" # <--- إضافة أمر البحث الجديد في الحالة
            "  - `s -ch -[link]` (تعيين قناة الأرشيف)\n" # <--- إضافة أمر قناة الأرشيف في الحالة
            "  - `s -gp -[link]` (تعيين رابط جروب الطلبات)\n" # <--- إضافة أمر جروب الطلبات في الحالة
            "البوت شغال تمام الحمد لله. ✅"
        )
        await event.respond(status_message, parse_mode='markdown')

