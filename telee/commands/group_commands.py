import re
from telethon import events
from telethon.tl.types import Chat, Channel as TelethonChannel

ADMIN_ID = 6988696258 #  Make sure this is consistent across files if needed


def register_handlers(bot):
    """تسجيل معالجات أوامر الجروبات"""
    @bot.client.on(events.NewMessage(pattern=re.compile(r'^gps$', re.IGNORECASE), incoming=True, from_users=ADMIN_ID))
    async def list_groups_handler(event):
        """عرض المجموعات التي الحساب مشترك فيها"""
        user_id = event.sender_id

        if not await bot.is_admin(user_id):
            return

        dialogs = await bot.client.get_dialogs()
        groups = []
        message_text = "**الجروبات المشترك فيها:**\n" # <--- تم حذف سطر فارغ هنا
        segment_length = 0
        counter = 1 #  عداد للجروبات

        for dialog in dialogs:
            entity = dialog.entity
            if isinstance(entity, (Chat, TelethonChannel)) and not isinstance(entity, User):
                group_type = "جروب عام" if hasattr(entity, 'username') and entity.username else "جروب خاص"
                if hasattr(entity, 'username') and entity.username:
                    group_link = f"https://t.me/{entity.username}"
                else:
                    group_link = "رابط مش متاح"
                group_info = f"{counter}- [{entity.title}]({group_link}) ({group_type})\n" # تنسيق القائمة المرقمة + رابط مضمن

                if segment_length + len(group_info) > TELEGRAM_MESSAGE_LIMIT:
                    await event.respond(message_text, parse_mode='markdown', link_preview=False) # تعطيل المعاينة هنا
                    message_text = ""
                    segment_length = 0
                message_text += group_info
                segment_length += len(group_info)
                counter += 1 #  زيادة العداد


        # إرسال الجزء الأخير المتبقي
        if message_text:
            await event.respond(message_text, parse_mode='markdown', link_preview=False) # تعطيل المعاينة هنا
        else:
            await event.respond("مفيش جروبات مشتركة فيها.")


    @bot.client.on(events.NewMessage(pattern=re.compile(r'^gp\+ (.+)$', re.IGNORECASE), incoming=True, from_users=ADMIN_ID))
    async def add_group_handler(event):
        """إضافة مجموعة مسموح بها"""
        user_id = event.sender_id

        if not await bot.is_admin(user_id):
            return

        group_link = event.pattern_match.group(1).strip()

        try:
            group_entity = await bot.client.get_entity(group_link)
            if not isinstance(group_entity, (Chat, TelethonChannel)):
                await event.respond("الرابط اللي دخلته ده مش بتاع جروب.")
                return

            # التحقق مما إذا كانت المجموعة مضافة بالفعل
            group_info = {
                "id": group_entity.id,
                "title": group_entity.title,
                "link": group_link
            }

            # التحقق من القائمة بناءً على معرف المجموعة
            existing_groups = [g for g in bot.config["allowed_groups"] if g["id"] == group_entity.id]
            if existing_groups:
                await event.respond(f"جروب '{group_entity.title}' مضاف أصلاً!")
                return

            # إضافة المجموعة إلى القائمة
            bot.config["allowed_groups"].append(group_info)
            bot.save_config()

            await event.respond(f"تمام! جروب '{group_entity.title}' اضيف للمجموعات المسموح بيها.")

        except Exception as e:
            bot.logger.error(f"خطأ في إضافة المجموعة: {str(e)}")
            await event.respond(f"حصل مشكلة وأنا بضيف الجروب: {str(e)}")

    @bot.client.on(events.NewMessage(pattern=re.compile(r'^gp- (.+)$', re.IGNORECASE), incoming=True, from_users=ADMIN_ID))
    async def remove_group_handler(event):
        """إزالة مجموعة من القائمة المسموح بها"""
        user_id = event.sender_id

        if not await bot.is_admin(user_id):
            return

        group_input = event.pattern_match.group(1).strip()

        try:
            # محاولة العثور على المجموعة إما بالرابط أو بالاسم أو بالمعرف
            removed = False
            for i, group in enumerate(bot.config["allowed_groups"]):
                if (
                    group_input == str(group["id"]) or
                    group_input == group["title"] or
                    group_input == group["link"]
                ):
                    removed_group = bot.config["allowed_groups"].pop(i)
                    bot.save_config()
                    await event.respond(f"تمام! جروب '{removed_group['title']}' اتشال من المجموعات المسموح بيها.")
                    removed = True
                    break

            if not removed:
                await event.respond("مش لاقي الجروب ده في المجموعات المسموح بيها.")

        except Exception as e:
            bot.logger.error(f"خطأ في إزالة المجموعة: {str(e)}")
            await event.respond(f"حصل مشكلة وأنا بشيل الجروب: {str(e)}")

