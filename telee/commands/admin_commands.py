import re
from telethon import events

ADMIN_ID = 6988696258 #  Make sure this is consistent across files if needed

def register_handlers(bot):
    """تسجيل معالجات الأوامر الخاصة بالمسؤول"""
    @bot.client.on(events.NewMessage(pattern=re.compile(r'^start$', re.IGNORECASE), incoming=True, from_users=ADMIN_ID))
    async def start_handler(event):
        """معالجة أمر بدء البوت"""
        user_id = event.sender_id

        if not await bot.is_admin(user_id):
            return

        await event.respond(
            "أهلاً بيك يا باشا في بوت البحث عن الأفلام! 🎬\n\n"
            "الاوامر المختصرة تحت أمرك:\n"
            "**chls** - القنوات العامة\n"
            "**chps** - القنوات الخاصة\n"
            "**gps** - الجروبات\n"
            "**ch+** [@القناة] – إضافة قناة\n"
            "**ch-** [@القناة] – إزالة قناة\n"
            "**fch+** - إضافة قناة عن طريق تحويل رسالة\n" # <--- الأمر الجديد لإضافة القناة بالتحويل
            "**gp+** [@الجروب] – إضافة جروب\n"
            "**gp-** [@الجروب] – إزالة جروب\n"
            "**mon** – القنوات والجروبات المراقبة\n"
            "**st** – حالة البوت\n"
            "**f** [اسم الفيلم] – البحث عن فيلم \n" # <---  تعديل الأمر ليقوم بالبحث في القنوات المراقبة ثم الموسع
            "**setl** [عدد السطور] - تحديد سطور البحث\n"
            "**fs** - تفعيل/إلغاء البحث الكامل\n"
            "**share [source] to [destination]** - تحويل محتوى قناة لقناة أخرى\n" # <--- أوامر الشير الجديدة
            "**share [source] to [destination] -catch on** - بدء مراقبة قناة\n"
            "**share [source] to [destination] -catch off** - إيقاف مراقبة قناة\n"
            "**s** [اسم الفيلم] - البحث عن فيديو فيلم في كل الشاتات (للمستخدمين)\n" # <--- الأمر الجديد للمستخدمين
            "**s -ch -[link]** - تعيين قناة الأرشيف للفيديوهات (للمسؤول)\n" # <--- أمر المسؤول لقناة الأرشيف
            "**s -gp -[link]** - تعيين رابط جروب الطلبات (للمسؤول)\n" # <--- أمر المسؤول لجروب الطلبات
        )

