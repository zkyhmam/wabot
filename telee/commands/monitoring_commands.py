import re
import asyncio
from telethon import events
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import ChannelParticipantAdmin, ChannelParticipantCreator
from telethon.errors import UserNotParticipantError, ChatAdminRequiredError, ChannelPrivateError

ADMIN_ID = 6988696258 #  Make sure this is consistent across files if needed

def register_handlers(bot):
    """تسجيل معالجات أوامر المراقبة والشير"""

    @bot.client.on(events.NewMessage(pattern=re.compile(r'^mon$', re.IGNORECASE), incoming=True, from_users=ADMIN_ID))
    async def list_monitored_channels_handler(event):
        """عرض قائمة القنوات والجروبات المراقبة"""
        user_id = event.sender_id

        if not await bot.is_admin(user_id):
            return

        message_text = "**القنوات والجروبات اللي بتم مراقبتها حالياً:**\n\n**القنوات:**\n"
        segment_length = 0

        if not bot.config["monitored_channels"]:
            message_text += "مفيش قنوات مضافة للمراقبة.\n"
        else:
            counter = 1 # عداد للقنوات المراقبة
            for channel in bot.config["monitored_channels"]:
                channel_info = f"{counter}- [{channel['title']}]({channel['link']})\n" # تنسيق القائمة المرقمة + رابط مضمن
                if segment_length + len(channel_info) > TELEGRAM_MESSAGE_LIMIT:
                    await event.respond(message_text)
                    message_text = "**القنوات والجروبات اللي بتم مراقبتها حالياً:**\n\n**القنوات:**\n"
                    segment_length = 0
                message_text += channel_info
                segment_length += len(channel_info)
                counter += 1 # زيادة العداد

        message_text += "\n**الجروبات المسموح بيها:**\n"

        if not bot.config["allowed_groups"]:
            message_text += "مفيش جروبات مسموح بيها.\n"
        else:
            counter = 1 # عداد للجروبات المسموح بيها
            for group in bot.config["allowed_groups"]:
                group_info = f"{counter}- [{group['title']}]({group['link']})\n" # تنسيق القائمة المرقمة + رابط مضمن
                if segment_length + len(group_info) > TELEGRAM_MESSAGE_LIMIT:
                    await event.respond(message_text)
                    message_text = "**القنوات والجروبات اللي بتم مراقبتها حالياً:**\n\n**الجروبات المسموح بيها:**\n"
                    segment_length = 0
                message_text += group_info
                segment_length += len(group_info)
                counter += 1 # زيادة العداد


        if message_text != "**القنوات والجروبات اللي بتم مراقبتها حالياً:**\n\n**القنوات:**\n\n**الجروبات المسموح بيها:**\n":
            await event.respond(message_text)
        else:
            await event.respond("مفيش قنوات ولا جروبات مضافة للمراقبة أو مسموح بيها.")

    @bot.client.on(events.NewMessage(pattern=re.compile(r'^share (.+) to (.+)( -catch (on|off))?$', re.IGNORECASE), incoming=True, from_users=ADMIN_ID))
    async def share_channel_handler(event):
        """تحويل محتوى قناة لقناة أخرى أو بدء/إيقاف المراقبة"""
        user_id = event.sender_id

        if not await bot.is_admin(user_id):
            return

        source_link = event.pattern_match.group(1).strip()
        destination_link = event.pattern_match.group(2).strip()
        catch_command = event.pattern_match.group(4) # ممكن تكون None أو "on" أو "off"

        if catch_command == "on":
            await bot.start_monitoring_channel(source_link, destination_link, event) #  استدعاء دالة بدء المراقبة
        elif catch_command == "off":
            await bot.stop_monitoring_channel(source_link, destination_link, event) #  استدعاء دالة إيقاف المراقبة
        else:
            await bot.transfer_channel_content(source_link, destination_link, event) #  في الحالة العادية، يحول المحتوى مرة واحدة


    @bot.client.on(events.NewMessage(pattern=re.compile(r'^s -ch -\s*\[(.+)\]\s*$', re.IGNORECASE), incoming=True, from_users=ADMIN_ID))
    async def set_archive_channel_handler(event):
        """تعيين قناة الأرشيف للفيديوهات"""
        user_id = event.sender_id
        if not await bot.is_admin(user_id):
            return

        channel_link_match = event.pattern_match.group(1).strip() # استخراج اللينك من الأمر

        try:
            channel_entity = await bot.client.get_entity(channel_link_match)
            if not isinstance(channel_entity, Channel):
                await event.respond("الرابط ده مش لقناة.")
                return

            bot.config["archive_channel_id"] = channel_entity.id
            bot.save_config()
            await event.respond(f"تم تعيين قناة الأرشيف بنجاح: '{channel_entity.title}'.")

        except Exception as e:
            bot.logger.error(f"خطأ في تعيين قناة الأرشيف: {e}")
            await event.respond(f"حصل مشكلة في تعيين قناة الأرشيف: {str(e)}")


    @bot.client.on(events.NewMessage(pattern=re.compile(r'^s -gp -\s*\[(.+)\]\s*$', re.IGNORECASE), incoming=True, from_users=ADMIN_ID))
    async def set_request_group_link_handler(event):
        """تعيين رابط جروب الطلبات"""
        user_id = event.sender_id
        if not await bot.is_admin(user_id):
            return

        group_link = event.pattern_match.group(1).strip() # استخراج اللينك من الأمر

        if not group_link.startswith(('https://t.me/', 't.me/')):
            await event.respond("الرجاء إدخال رابط جروب صحيح يبدأ بـ https://t.me/ أو t.me/")
            return

        bot.config["request_group_link"] = group_link
        bot.save_config()
        await event.respond(f"تم تعيين رابط جروب الطلبات بنجاح: '{group_link}'.")

from telethon.tl.types import Channel

