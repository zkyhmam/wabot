import re
from telethon import events

ADMIN_USERNAME = "Zaky1million" #  Make sure this is consistent across files if needed
ADMIN_ID = 6988696258 #  Make sure this is consistent across files if needed


def register_handlers(bot):
    """تسجيل معالجات أوامر الذكاء الاصطناعي"""
    @bot.client.on(events.NewMessage(pattern=re.compile(r'^(ai|Ai|AI) (.+)$', re.IGNORECASE), incoming=True, from_users=ADMIN_ID)) # <---  تعديل المعالج بحيث يرد فقط على رسائل المسؤول في الخاص
    async def ai_response_handler(event):
        """معالجة الرسائل التي تبدأ بـ 'ai' أو 'Ai' أو 'AI' للردود الطبيعية من Gemini (للمسؤول فقط في الخاص)"""
        request_prefix = event.pattern_match.group(1) #  جزء البادئة (ai, Ai, AI)
        request_text = event.pattern_match.group(2).strip() #  باقي الرسالة بعد البادئة
        user_id = event.sender_id

        if not await bot.is_admin(user_id): # <--- التحقق من أن المستخدم هو المسؤول في الخاص
            return #  لو مش المسؤول، منتجاهل الرسالة

        full_request_text = f"{request_prefix} {request_text}" #  تكوين النص الكامل عشان التسجيل

        chat = await event.get_chat()
        chat_title = "شات خاص" if event.is_private else chat.title #  عنوان الشات للتسجيل

        bot.logger.info(f"رسالة Gemini مطلوبة من: {user_id} في: {chat_title} (ID: {chat.id}) - النص: '{full_request_text}'")


        try:
            # ---  Prompt للرد الطبيعي ---
            if "فيلم الرجل الحديدي اكتب ايه" in request_text.lower(): # <---  Prompt سؤال "اكتب ايه"
                prompt = f"""أنت بوت متخصص في البحث عن الأفلام والمسلسلات. اسمك 'Zaky AI'.
                لما المستخدم يسألك عن طريقة البحث عن فيلم معين زي 'فيلم الرجل الحديدي' وإيه الكلمات اللي المفروض يكتبها عشان يلاقي الفيلم، مهمتك توجهه لأفضل طريقة بحث عشان نتائج البحث تكون دقيقة.
                ردك المفروض يكون: عشان تلاقي فيلم 'الرجل الحديدي'، الأفضل تكتب اسم الفيلم بالانجليزي: 'Iron Man'. أو ممكن تستخدم كلمة مفتاحية زي 'Marvel' في البحث. ولو كتبت الاسم ده في أي جروب أنا موجود فيه، هحاول ألاقيهولك في القنوات اللي بتم مراقبتها."""
            elif "iron man" in request_text.lower(): # <---  Prompt سؤال "iron man" بعد ai
                prompt = f"""أنت بوت متخصص في البحث عن الأفلام والمسلسلات. اسمك 'Zaky AI'.
                لما المستخدم يكتب اسم فيلم معين زي 'iron man' بعد كلمة 'Ai'، مهمتك توضحله الفرق بين استخدام 'Ai' للأسئلة والأوامر، وبين البحث عن فيلم.
                ردك المفروض يكون: أهلاً! أنا Zaky AI بوت البحث عن الأفلام، تحت أمرك لو بتدور على أي فيلم. عشان أقدر أبحثلك عن فيلم 'iron man' بشكل صحيح، يفضل تكتب اسم الفيلم في أي جروب أنا موجود فيه، وأنا هحاول الاقيه في القنوات اللي بتم مراقبتها. لو كتبت اسم الفيلم في رسالة خاصة ليا مش هقدر أبحث عنه."""
            else: # <---  Prompt للردود الطبيعية العامة
                prompt = f"""أنت بوت متخصص في البحث عن الأفلام والمسلسلات. اسمك 'Zaky AI'.
                لما المستخدم يسألك أي سؤال يبدأ بـ '{request_prefix}'، مهمتك ترد رد طبيعي ومفيد، كأنك بتساعده يعرف أكتر عن البوت أو إمكانياته.
                ممكن المستخدم يسألك عن طريقة البحث، أو إيه الأوامر المتاحة، أو أي حاجة تانية ليها علاقة بالبوت.

                مثال لردودك:
                - 'أهلاً! أنا Zaky AI بوت البحث عن الأفلام، تحت أمرك لو بتدور على أي فيلم.'
                - 'ممكن تبحث عن فيلم معين بكتابة اسم الفيلم (يفضل يكون بالانجليزي وبدون أخطاء إملائية) في أي جروب أنا موجود فيه، وأنا هحاول الاقيه في القنوات اللي بتم مراقبتها.'
                - 'لو عاوز تعرف أوامر البوت، ممكن تبعت كلمة 'start' في رسالة خاصة ليا.'

                دلوقتي، المسؤول ({ADMIN_USERNAME}) بعتلك الرسالة دي بعد البادئة '{request_prefix}': '{request_text}'
                ردك المفروض يكون:""" #  Prompt للردود الطبيعية

            response = bot.gemini_model.generate_content(prompt)
            ai_response_text = response.text.strip()


            await event.reply(ai_response_text, parse_mode='markdown') #  الرد على المسؤول برد Gemini بدون رأسية
            bot.logger.info(f"تم الرد بـ Gemini على رسالة: '{full_request_text}' في: {chat_title}") #  تسجيل الرد

        except Exception as e:
            bot.logger.error(f"حصل خطأ في الرد الطبيعي بـ Gemini: {str(e)}") #  تسجيل الخطأ
            try:
                await bot.client.send_message(ADMIN_ID, f"حصل مشكلة في الرد الطبيعي بـ Gemini للرسالة: '{full_request_text}' - الخطأ: {str(e)}") #  إرسال إشعار للمسؤول بالخطأ
            except:
                pass

