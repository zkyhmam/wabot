import re
from telethon import events

ADMIN_ID = 6988696258 #  Make sure this is consistent across files if needed

def register_handlers(bot):
    """تسجيل معالجات أوامر الإعدادات"""
    @bot.client.on(events.NewMessage(pattern=re.compile(r'^setl (\d+)$', re.IGNORECASE), incoming=True, from_users=ADMIN_ID))
    async def set_search_lines_handler(event):
        """تحديد عدد سطور البحث"""
        user_id = event.sender_id

        if not await bot.is_admin(user_id):
            return

        lines_limit = event.pattern_match.group(1)
        if not lines_limit.isdigit() or int(lines_limit) <= 0:
            await event.respond("عدد سطور البحث لازم يكون رقم صحيح موجب.")
            return

        bot.config["search_lines_limit"] = int(lines_limit)
        bot.save_config()
        await event.respond(f"تمام! عدد سطور البحث اتغير لـ {lines_limit} سطر.")

    @bot.client.on(events.NewMessage(pattern=re.compile(r'^fs$', re.IGNORECASE), incoming=True, from_users=ADMIN_ID))
    async def toggle_full_search_handler(event):
        """تفعيل أو إلغاء البحث في الرسالة كاملة"""
        user_id = event.sender_id

        if not await bot.is_admin(user_id):
            return

        bot.config["search_full_message"] = not bot.config["search_full_message"]
        bot.save_config()
        status = "متفعل" if bot.config["search_full_message"] else "متعطل"
        await event.respond(f"تمام! وضع البحث في الرسالة كاملة دلوقتي {status}.")

