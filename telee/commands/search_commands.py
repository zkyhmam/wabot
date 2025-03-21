import re
from telethon import events

ADMIN_ID = 6988696258 #  Make sure this is consistent across files if needed

def register_handlers(bot):
    """تسجيل معالجات أوامر البحث"""
    @bot.client.on(events.NewMessage(pattern=re.compile(r'^f (.+)$', re.IGNORECASE), incoming=True, from_users=ADMIN_ID))
    async def manual_search_handler(event):
        """البحث اليدوي عن فيلم في القنوات المراقبة ثم الموسع من قبل المسؤول""" # <--- تعديل الوصف ليشمل الموسع أيضاً
        user_id = event.sender_id

        if not await bot.is_admin(user_id):
            return

        movie_name = event.pattern_match.group(1).strip()
        await event.respond(f"جاري البحث عن '{movie_name}'... ⏳") # <--- تعديل الرسالة

        result = await bot.search_movie(movie_name) # <---  هنا البحث هيكون في القنوات المراقبة ثم الموسع تلقائي
        if result:
            post_link, title = result
            # --- صيغة الرد الجديدة مع القلب زي ما طلبت والرابط المضمن ---
            response_message = (
                f"**فيلم : {title}**\n"
                f"**الرابط : [اضغط هنا ♥️]({post_link})**" # <--- رابط مضمن
            )
            await event.respond(response_message, parse_mode='markdown', link_preview=False)
        else:
            await event.respond(f"معلش، مش لاقي فيلم '{movie_name}' في القنوات اللي بتم مراقبتها و في كل الدردشات. 😔") # <--- تعديل الرسالة لتوضح البحث في القنوات المراقبة والموسع

            # اقتراح تحسينات البحث
            variations = bot.generate_name_variations(movie_name)
            if len(variations) > 1:
                await event.respond(f"جربت أدور كمان على: {', '.join(variations[1:])}")


    @bot.client.on(events.NewMessage(pattern=re.compile(r'^s (.+)$', re.IGNORECASE), incoming=True))
    async def user_search_video_handler(event):
        """معالجة أمر البحث عن فيديو من المستخدمين"""
        movie_name = event.pattern_match.group(1).strip()
        await event.respond(f"جاري البحث عن فيديو فيلم '{movie_name}' في كل الشاتات... 🎬")

        search_result = await bot.search_movie_everywhere_video(movie_name)
        if search_result:
            post_link, title, _ = search_result
            request_group_link = bot.config["request_group_link"] # جلب رابط جروب الطلبات من الإعدادات

            response_message = (
                f"**فيلم : {title}**\n"
                f"**الرابط : [اضغط هنا ♥️]({post_link})**\n"
            )
            if request_group_link: # إضافة سطر جروب الطلبات لو موجود
                response_message += f"جروب الطلبات : {request_group_link}"

            await event.respond(response_message, parse_mode='markdown', link_preview=False)
        else:
            await event.respond(f"معلش، مش لاقي فيديو فيلم '{movie_name}' في كل الشاتات. 😔")

