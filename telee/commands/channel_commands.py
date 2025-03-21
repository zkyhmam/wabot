import re
from telethon import events

ADMIN_ID = 6988696258 #  Make sure this is consistent across files if needed
TELEGRAM_MESSAGE_LIMIT = 4096 # Make sure this is consistent across files if needed


def register_handlers(bot):
    """تسجيل معالجات أوامر القنوات"""
    @bot.client.on(events.NewMessage(pattern=re.compile(r'^chls$', re.IGNORECASE), incoming=True, from_users=ADMIN_ID))
    async def list_all_channels_handler(event):
        """عرض جميع القنوات العامة التي الحساب مشترك فيها"""
        user_id = event.sender_id

        if not await bot.is_admin(user_id):
            return

        dialogs = await bot.client.get_dialogs()
        public_channels = []
        message_text = "**القنوات العامة المشترك فيها:**\n" # <--- تم حذف سطر فارغ هنا
        segment_length = 0
        counter = 1 #  عداد للقنوات

        for dialog in dialogs:
            entity = dialog.entity
            if isinstance(entity, Channel) and entity.username:
                link = f"https://t.me/{entity.username}"
                channel_info = f"{counter}- [{entity.title}]({link})\n" #  تنسيق القائمة المرقمة + رابط مضمن
                if segment_length + len(channel_info) > TELEGRAM_MESSAGE_LIMIT:
                    await event.respond(message_text, parse_mode='markdown', link_preview=False) # تعطيل المعاينة هنا
                    message_text = ""
                    segment_length = 0
                message_text += channel_info
                segment_length += len(channel_info)
                counter += 1 #  زيادة العداد


        # إرسال الجزء الأخير المتبقي
        if message_text:
            await event.respond(message_text, parse_mode='markdown', link_preview=False) # تعطيل المعاينة هنا
        else:
            await event.respond("مفيش قنوات عامة مشتركة فيها.")


    @bot.client.on(events.NewMessage(pattern=re.compile(r'^chps$', re.IGNORECASE), incoming=True, from_users=ADMIN_ID))
    async def list_private_channels_handler(event):
        """عرض جميع القنوات الخاصة التي الحساب مشترك فيها"""
        user_id = event.sender_id

        if not await bot.is_admin(user_id):
            return

        dialogs = await bot.client.get_dialogs()
        private_channels = []
        message_text = "**القنوات الخاصة المشترك فيها:**\n" # <--- تم حذف سطر فارغ هنا
        segment_length = 0
        counter = 1 #  عداد للقنوات

        for dialog in dialogs:
            entity = dialog.entity
            if isinstance(entity, Channel) and not entity.username:
                channel_link = f"https://t.me/c/{str(entity.id)[4:]}"
                channel_info = f"{counter}- [{entity.title}]({channel_link})\n" # تنسيق القائمة المرقمة + رابط مضمن
                if segment_length + len(channel_info) > TELEGRAM_MESSAGE_LIMIT:
                    await event.respond(message_text, parse_mode='markdown', link_preview=False) # تعطيل المعاينة هنا
                    message_text = ""
                    segment_length = 0
                message_text += channel_info
                segment_length += len(channel_info)
                counter += 1 #  زيادة العداد


        # إرسال الجزء الأخير المتبقي
        if message_text:
            await event.respond(message_text, parse_mode='markdown', link_preview=False) # تعطيل المعاينة هنا
        else:
            await event.respond("مفيش قنوات خاصة مشتركة فيها.")

    @bot.client.on(events.NewMessage(pattern=re.compile(r'^ch\+ (.+)$', re.IGNORECASE), incoming=True, from_users=ADMIN_ID))
    async def add_channel_handler(event):
        """إضافة قناة للمراقبة من القنوات المتاحة"""
        user_id = event.sender_id

        if not await bot.is_admin(user_id):
            return

        channel_input = event.pattern_match.group(1).strip()
        bot.logger.info(f"محاولة إضافة قناة: المدخل = '{channel_input}'")

        # ---  إضافة بسيطة: التحقق من شكل المدخل قبل أي حاجة ---
        if not channel_input.startswith(('https://t.me/', '@')):
            await event.respond("الرجاء إدخال رابط قناة صحيح أو اسم مستخدم يبدأ بـ @")
            return

        # استخراج اسم المستخدم من الرابط إذا كان رابط
        if channel_input.startswith("https://t.me/"):
            channel_input = channel_input[18:]
            bot.logger.info(f"تم استخراج اسم المستخدم من الرابط: '{channel_input}'")

        try:
            # البحث عن القناة في الدردشات الحالية
            dialogs = await bot.client.get_dialogs()
            found = False

            for dialog in dialogs:
                entity = dialog.entity
                if isinstance(entity, Channel):
                    bot.logger.info(f"فحص القناة: العنوان = '{entity.title}', اسم المستخدم = '{entity.username}', المعرف = '{entity.id}'")

                    if (
                        str(entity.id) == channel_input or
                        (entity.username and entity.username == channel_input) or
                        entity.title.lower() == channel_input.lower()
                    ):
                        # إضافة القناة إلى قائمة المراقبة
                        channel_info = {
                            "id": entity.id,
                            "username": entity.username,
                            "title": entity.title,
                            "link": f"https://t.me/{entity.username}" if entity.username else f"https://t.me/c/{str(entity.id)[4:]}"
                        }

                        # التحقق إذا كانت القناة مضافة مسبقاً
                        if any(c["id"] == entity.id for c in bot.config["monitored_channels"]):
                            await event.respond(f"القناة '{entity.title}' مضافة للمراقبة أصلاً!")
                            return

                        bot.config["monitored_channels"].append(channel_info)
                        bot.save_config()

                        await event.respond(f"تمام! قناة '{entity.title}' اضيفت للمراقبة.")
                        found = True
                        break

            if not found:
                await event.respond("لم يتم العثور على القناة. **تأكد من أنك مشترك في القناة وأن الاسم أو المعرف صحيح.**")

        except Exception as e:
            bot.logger.error(f"خطأ في إضافة القناة: {str(e)}")
            await event.respond(f"حصل مشكلة وأنا بضيف القناة: {str(e)}")

    @bot.client.on(events.NewMessage(pattern=re.compile(r'^fch\+$', re.IGNORECASE), incoming=True, from_users=ADMIN_ID)) # <---  أمر إضافة قناة عن طريق التحويل
    async def forward_add_channel_handler(event):
        """إضافة قناة للمراقبة عن طريق تحويل رسالة منها"""
        user_id = event.sender_id

        if not await bot.is_admin(user_id):
            return

        if not event.forward_from_id: #  نتأكد إن الرسالة محولة
            await event.respond("من فضلك حول رسالة من القناة اللي عاوز تضيفها عشان أقدر أضيفها للمراقبة.")
            return

        forwarded_from_id = event.forward_from_id
        try:
            channel_entity = await bot.client.get_entity(forwarded_from_id) #  نجيب الكيان من الـ ID المحول منه
            if not isinstance(channel_entity, Channel): #  نتأكد إنه قناة فعلًا
                await event.respond("الرسالة المحولة دي مش من قناة. حول رسالة من قناة عامة أو خاصة.")
                return

            # التحقق إذا كانت القناة مضافة مسبقاً
            if any(c["id"] == channel_entity.id for c in bot.config["monitored_channels"]):
                await event.respond(f"القناة '{channel_entity.title}' مضافة للمراقبة أصلاً!")
                return

            # إضافة القناة إلى قائمة المراقبة
            channel_info = {
                "id": channel_entity.id,
                "username": channel_entity.username,
                "title": channel_entity.title,
                "link": f"https://t.me/{channel_entity.username}" if channel_entity.username else f"https://t.me/c/{str(channel_entity.id)[4:]}"
            }
            bot.config["monitored_channels"].append(channel_info)
            bot.save_config()

            await event.respond(f"تمام! قناة '{channel_entity.title}' اضيفت للمراقبة عن طريق التحويل.")

        except Exception as e:
            bot.logger.error(f"خطأ في إضافة القناة عن طريق التحويل: {str(e)}")
            await event.respond(f"حصل مشكلة وأنا بضيف القناة عن طريق التحويل: {str(e)}")


    @bot.client.on(events.NewMessage(pattern=re.compile(r'^ch- (.+)$', re.IGNORECASE), incoming=True, from_users=ADMIN_ID))
    async def remove_channel_handler(event):
        """إزالة قناة من المراقبة"""
        user_id = event.sender_id

        if not await bot.is_admin(user_id):
            return

        channel_input = event.pattern_match.group(1).strip()

        try:
            # محاولة العثور على القناة إما بالرابط أو بالاسم
            removed = False
            for i, channel in enumerate(bot.config["monitored_channels"]):
                if (
                    channel_input == str(channel["id"]) or
                    channel_input == channel["username"] or
                    channel_input == channel["title"] or
                    channel_input == channel["link"]
                ):
                    removed_channel = bot.config["monitored_channels"].pop(i)
                    bot.save_config()
                    await event.respond(f"تمام! قناة '{removed_channel['title']}' اتشالت من المراقبة.")
                    removed = True
                    break

            if not removed:
                await event.respond("مش لاقي القناة دي في اللي بيتم مراقبتهم.")

        except Exception as e:
            bot.logger.error(f"خطأ في إزالة القناة: {str(e)}")
            await event.respond(f"حصل مشكلة وأنا بشيل القناة: {str(e)}")

from telethon.tl.types import Channel

