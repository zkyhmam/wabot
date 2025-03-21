import re
from typing import Tuple, Optional
from telethon import events
from telethon.tl.types import Channel, Chat, User, Message
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import ChannelParticipantAdmin, ChannelParticipantCreator
from telethon.errors import ChatAdminRequiredError, ChannelPrivateError, UserNotParticipantError, MessageNotModifiedError, ChatRestrictedError


ADMIN_ID = 6988696258 #  Make sure this is consistent across files if needed
CATCH_COOLDOWN = 5 #  Make sure this is consistent across files if needed
SEARCH_COOLDOWN = 1 #  Make sure this is consistent across files if needed
TELEGRAM_MESSAGE_LIMIT = 4096 # Make sure this is consistent across files if needed


async def is_admin(self, user_id: int) -> bool:
    """التحقق مما إذا كان المستخدم هو المسؤول المعتمد"""
    return user_id == self.config["admin_id"]

async def check_bot_admin_status(self, channel_id: int) -> bool:
    """التحقق من صلاحيات البوت في القناة (لم تعد ضرورية لحساب المستخدم)"""
    return True  # دائماً True لحساب المستخدم


async def process_and_forward_message(self, message: Message, destination_channel_entity): # <--- دالة معالجة وإرسال الرسائل المشتركة
    """معالجة الرسالة قبل إرسالها للقناة الهدف (إزالة التحويل واللينكات والمعرفات)"""
    try:
        msg_text = message.text or "" #  نص الرسالة، لو مفيش نص يبقى سترينج فاضي

        # --- إزالة علامة التحويل ---
        if message.fwd_from:
            msg_text_no_fwd = re.sub(r'(?s)--------forwarded from--------.*', '', msg_text).strip() #  إزالة كل اللي بعد علامة التحويل
        else:
            msg_text_no_fwd = msg_text

        # --- إزالة اللينكات والمعرفات ---
        msg_text_cleaned = re.sub(r'https?://\S+|@\w+|t\.me/\S+', '', msg_text_no_fwd).strip() #  إزالة الروابط والمعرفات

        await self.client.send_message(destination_channel_entity, msg_text_cleaned, file=message.media, parse_mode='markdown') #  إرسال الرسالة بعد التنظيف مع الميديا + تفعيل Markdown

    except Exception as e:
        self.logger.error(f"خطأ في معالجة وإرسال الرسالة: {e}")


async def transfer_channel_content(self, source_channel_link: str, destination_channel_link: str, event: events.NewMessage.Event): # <--- دالة تحويل محتوى القناة بالكامل
    """تحويل كل محتوى قناة مصدر إلى قناة هدف"""
    try:
        source_channel_entity = await self.client.get_entity(source_channel_link)
        destination_channel_entity = await self.client.get_entity(destination_channel_link)

        if not isinstance(source_channel_entity, Channel) or not isinstance(destination_channel_entity, Channel):
            await event.respond("الروابط اللي دخلتها مش لقنوات.")
            return

        # ---  التحقق من وجود البوت في القناتين وإنه أدمن في القناة الهدف ---
        try:
            await self.client.get_participants(source_channel_entity) #  هنا بيتأكد إنه موجود في القناة المصدر
            dest_participant = await self.client(GetParticipantRequest(destination_channel_entity, await self.client.get_me())) #  هنا بيجيب معلومات مشاركة البوت في القناة الهدف
            if not isinstance(dest_participant.participant, (ChannelParticipantAdmin, ChannelParticipantCreator)): #  ويتأكد إنه أدمن أو كريتور
                await event.respond("البوت لازم يكون أدمن في القناة الهدف.")
                return
        except UserNotParticipantError:
            await event.respond("البوت مش موجود في القناة المصدر أو الهدف. تأكد اني موجود في القناتين.")
            return
        except ChatAdminRequiredError: #  في حالة القنوات الخاصة مينفعش يجيب المشاركين
            dest_participant = await self.client(GetParticipantRequest(destination_channel_entity, await self.client.get_me())) #  يحاول يجيب معلومات المشاركة تاني بس من غير جلب المشاركين كلهم
            if not isinstance(dest_participant.participant, (ChannelParticipantAdmin, ChannelParticipantCreator)): #  ويتأكد إنه أدمن أو كريتور بردو
                await event.respond("البوت لازم يكون ادمن في القناة الهدف.")
                return
        except ChannelPrivateError: #  لو القناة المصدر خاصة ومبيقدرش يدخلها
            await event.respond("القناة المصدر خاصة ومشتركينها محدودين، مينفعش أحول منها.")
            return
        except Exception as e: #  أي خطأ تاني في التحقق
            self.logger.error(f"خطأ في التحقق من القنوات: {e}")
            await event.respond(f"حصل مشكلة في التحقق من القنوات: {e}")
            return


        await event.respond(f"جاري تحويل كل محتوى قناة '{source_channel_entity.title}' لقناة '{destination_channel_entity.title}'... العملية ممكن تاخد وقت حسب حجم القناة المصدر. ⏳")

        total_messages = 0
        forwarded_messages = 0
        async for message in self.client.iter_messages(source_channel_entity, reverse=True): #  reverse=True عشان يحول بالترتيب من الأقدم للأحدث
            total_messages += 1
            await self.process_and_forward_message(message, destination_channel_entity) #  هنا بيستخدم دالة المعالجة والإرسال
            forwarded_messages += 1
            if forwarded_messages % 100 == 0: #  كل 100 رسالة يبعت نقطة عشان يوضح للمستخدم إنه شغال
                try:
                    await event.respond(".")
                except MessageNotModifiedError: #  لو الرسالة اللي بيرد عليها اتمسحت أو اتعدلت
                    pass #  بيتجاهل الخطأ ويكمل تحويل

            await asyncio.sleep(SEARCH_COOLDOWN) #  وقت انتظار بين كل رسالة والتانية

        await event.respond(f"✅ تم تحويل عدد {forwarded_messages} رسالة من قناة '{source_channel_entity.title}' لقناة '{destination_channel_entity.title}'.")


    except Exception as e:
        self.logger.error(f"خطأ في تحويل محتوى القناة: {e}")
        await event.respond(f"حصل مشكلة في تحويل محتوى القناة: {e}")

async def start_monitoring_channel(self, source_channel_link: str, destination_channel_link: str, event: events.NewMessage.Event): # <--- دالة بدء مراقبة القناة
    """بدء مراقبة قناة مصدر وتحويل الرسائل الجديدة إلى قناة هدف"""
    try:
        source_channel_entity = await self.client.get_entity(source_channel_link)
        destination_channel_entity = await self.client.get_entity(destination_channel_link)

        if not isinstance(source_channel_entity, Channel) or not isinstance(destination_channel_entity, Channel):
            await event.respond("الروابط اللي دخلتها مش لقنوات.")
            return

        # ---  التحقق من وجود البوت في القناتين وإنه أدمن في القناة الهدف (نفس التحقق بتاع التحويل) ---
        try:
            await self.client.get_participants(source_channel_entity)
            dest_participant = await self.client(GetParticipantRequest(destination_channel_entity, await self.client.get_me()))
            if not isinstance(dest_participant.participant, (ChannelParticipantAdmin, ChannelParticipantCreator)):
                await event.respond("البوت لازم يكون أدمن في القناة الهدف.")
                return
        except UserNotParticipantError:
            await event.respond("البوت مش موجود في القناة المصدر أو الهدف. تأكد اني موجود في القناتين.")
            return
        except ChatAdminRequiredError:
            dest_participant = await self.client(GetParticipantRequest(destination_channel_entity, await self.client.get_me()))
            if not isinstance(dest_participant.participant, (ChannelParticipantAdmin, ChannelParticipantCreator)):
                await event.respond("البوت لازم يكون ادمن في القناة الهدف.")
                return
        except ChannelPrivateError:
            await event.respond("القناة المصدر خاصة ومشتركينها محدودين، مينفعش أراقبها.")
            return
        except Exception as e:
            self.logger.error(f"خطأ في التحقق من القنوات للمراقبة: {e}")
            await event.respond(f"حصل مشكلة في التحقق من القنوات للمراقبة: {e}")
            return

        # ---  التحقق إذا كانت المراقبة شغالة أصلاً للـ pairing ده ---
        share_pair = (source_channel_entity.id, destination_channel_entity.id)
        if share_pair in self.monitoring_tasks:
            await event.respond("المراقبة شغالة أصلاً للقناتين دول.")
            return

        # --- حفظ معلومات المراقبة في الكونفيج ---
        monitor_info = {
            "source_channel_id": source_channel_entity.id,
            "destination_channel_id": destination_channel_entity.id,
            "source_channel_title": source_channel_entity.title,
            "destination_channel_title": destination_channel_entity.title
        }
        self.config["monitored_shares"].append(monitor_info)
        self.save_config()

        # ---  بدء مهمة المراقبة في الخلفية ---
        task = asyncio.create_task(self.monitor_channel_task(source_channel_entity, destination_channel_entity)) #  استدعاء دالة مهمة المراقبة
        self.monitoring_tasks[share_pair] = task #  حفظ المهمة في القاموس

        await event.respond(f"✅ تم تفعيل مراقبة قناة '{source_channel_entity.title}' وتحويل أي رسايل جديدة لقناة '{destination_channel_entity.title}' أول ما تنزل.")


    except Exception as e:
        self.logger.error(f"خطأ في بدء مراقبة القناة: {e}")
        await event.respond(f"حصل مشكلة في تفعيل مراقبة القناة: {e}")

async def stop_monitoring_channel(self, source_channel_link: str, destination_channel_link: str, event: events.NewMessage.Event): # <--- دالة إيقاف مراقبة القناة
    """إيقاف مراقبة قناة مصدر"""
    try:
        source_channel_entity = await self.client.get_entity(source_channel_link)
        destination_channel_entity = await self.client.get_entity(destination_link)

        if not isinstance(source_channel_entity, Channel) or not isinstance(destination_channel_entity, Channel):
            await event.respond("الروابط اللي دخلتها مش لقنوات.")
            return

        share_pair = (source_channel_entity.id, destination_channel_entity.id)
        if share_pair in self.monitoring_tasks:
            task = self.monitoring_tasks.pop(share_pair) #  جلب مهمة المراقبة من القاموس وحذفها
            task.cancel() #  إلغاء المهمة
            self.logger.info(f"تم إلغاء مهمة المراقبة للقناتين: {source_channel_entity.title} -> {destination_channel_entity.title}")

            # --- حذف معلومات المراقبة من الكونفيج ---
            self.config["monitored_shares"] = [
                monitor for monitor in self.config["monitored_shares"]
                if not (monitor["source_channel_id"] == source_channel_entity.id and monitor["destination_channel_id"] == destination_channel_entity.id)
            ]
            self.save_config()


            await event.respond(f"✅ تم إيقاف مراقبة قناة '{source_channel_entity.title}' والتحويل لقناة '{destination_channel_entity.title}'.")
        else:
            await event.respond("المراقبة مش شغالة أصلاً للقناتين دول.")

    except Exception as e:
        self.logger.error(f"خطأ في إيقاف مراقبة القناة: {e}")
        await event.respond(f"حصل مشكلة في إيقاف مراقبة القناة: {e}")

async def monitor_channel_task(self, source_channel_entity, destination_channel_entity): # <--- مهمة المراقبة اللي بتشتغل في الخلفية
    """مهمة مراقبة قناة وتحويل الرسائل الجديدة"""
    source_channel_id = source_channel_entity.id #  حفظ معرف القناة المصدر هنا عشان هنستخدمه كتير

    last_message_id = None #  لتتبع آخر رسالة تم تحويلها

    self.logger.info(f"بدء مهمة مراقبة قناة '{source_channel_entity.title}' -> '{destination_channel_entity.title}'")
    while True:
        try:
            async for message in self.client.iter_messages(source_channel_entity, limit=1, reverse=True): #  limit=1 يعني بيجيب آخر رسالة بس، reverse=True عشان الأحدث الأول
                if message and message.id != last_message_id: #  لو فيه رسالة جديدة ومختلفة عن آخر رسالة تم تحويلها
                    self.logger.info(f"رسالة جديدة في قناة '{source_channel_entity.title}': {message.id} - '{message.text[:50]}'") #  تسجيل الرسالة الجديدة

                    await self.process_and_forward_message(message, destination_channel_entity) #  معالجة وإرسال الرسالة الجديدة

                    last_message_id = message.id #  تحديث آخر رسالة تم تحويلها
                else:
                    pass #  لو مفيش رسايل جديدة أو هي نفس آخر رسالة، ميعملش حاجة

            await asyncio.sleep(CATCH_COOLDOWN) #  وقت انتظار بين كل تشييك على الرسائل
        except asyncio.CancelledError: #  في حالة إلغاء المهمة
            self.logger.info(f"تم إلغاء مهمة مراقبة قناة '{source_channel_entity.title}' -> '{destination_channel_entity.title}'") #  تسجيل الإلغاء
            break #  الخروج من اللوب وإنهاء المهمة
        except Exception as e: #  أي خطأ تاني أثناء المراقبة
            self.logger.error(f"خطأ في مهمة مراقبة قناة '{source_channel_entity.title}' -> '{destination_channel_entity.title}': {e}") #  تسجيل الخطأ
            await asyncio.sleep(CATCH_COOLDOWN * 2) #  وقت انتظار أطول في حالة الخطأ


async def process_video_result(self, channel_entity, message, movie_name):
    """معالجة نتيجة البحث عن فيديو وتحويلها وإرجاع الرابط"""
    archive_channel_id = self.config["archive_channel_id"]
    if not archive_channel_id:
        self.logger.warning("قناة الأرشيف مش متظبطة. الفيديو مش هيتحول.")
        return None  # قناة الأرشيف مش متظبطة

    archive_channel_entity = await self.client.get_entity(archive_channel_id)
    if not isinstance(archive_channel_entity, Channel):
        self.logger.error("الكيان المحدد كقناة أرشيف مش قناة.")
        return None

    post_link, title, _ = await self.process_and_forward_message_video(message, archive_channel_entity, movie_name)
    self.logger.info(f"تم تحويل الفيديو '{movie_name}' من '{channel_entity.title}' إلى قناة الأرشيف.")
    return post_link, title, message # إرجاع رابط المنشور وكائن الرسالة

async def is_forwardable_chat(self, chat_entity):
    """التحقق إذا كان الشات يسمح بتحويل الرسائل"""
    try:
        if isinstance(chat_entity, Channel):
            # القنوات العامة والخاصة غالبا بتقبل التحويل إلا لو مقفولة بخصائص معينة
            return True
        elif isinstance(chat_entity, Chat):
            # الجروبات العامة والخاصة
            chat = await self.client.get_entity(chat_entity)
            if chat.noforwards: # هنا بنتحقق من خاصية منع التحويل للجروب
                return False
            return True
        elif isinstance(chat_entity, User):
            # الشاتات الخاصة بتقبل التحويل
            return True
    except Exception as e:
        self.logger.error(f"خطأ في فحص قابلية التحويل للشات '{chat_entity.title if hasattr(chat_entity, 'title') else chat_entity.id}': {e}")
    return False # في حالة الشك، بنرجع False كإجراء وقائي


async def process_and_forward_message_video(self, message: Message, destination_channel_entity, search_keyword): # <--- دالة معالجة وإرسال الرسائل الفيديو المشتركة
    """معالجة رسالة الفيديو قبل إرسالها لقناة الأرشيف (إزالة التحويل واللينكات والمعرفات وتعديل الوصف)"""
    try:
        msg_text = message.text or "" #  نص الرسالة، لو مفيش نص يبقى سترينج فاضي

        # --- إزالة علامة التحويل ---
        if message.fwd_from:
            msg_text_no_fwd = re.sub(r'(?s)--------forwarded from--------.*', '', msg_text).strip() #  إزالة كل اللي بعد علامة التحويل
        else:
            msg_text_no_fwd = msg_text

        # --- إزالة اللينكات والمعرفات ---
        msg_text_cleaned = re.sub(r'https?://\S+|@\w+|t\.me/\S+', '', msg_text_no_fwd).strip() #  إزالة الروابط والمعرفات

        # --- إنشاء الوصف الجديد ---
        new_caption = f"**فيلم : {search_keyword} ♥️**"

        sent_message = await self.client.send_file(destination_channel_entity, file=message.media, caption=new_caption, parse_mode='markdown') #  إرسال الفيديو بعد التنظيف مع الميديا والوصف الجديد + تفعيل Markdown
        post_link = f"https://t.me/c/{str(destination_channel_entity.id)[4:]}/{sent_message.id}" # رابط الرسالة المرسلة في قناة الأرشيف
        title = search_keyword # العنوان هو الكلمة المفتاحية للبحث

        return post_link, title, sent_message # إرجاع الرابط والعنوان وكائن الرسالة

    except Exception as e:
        self.logger.error(f"خطأ في معالجة وإرسال رسالة الفيديو: {e}")
        return None, None, None

