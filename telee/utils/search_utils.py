import re
from typing import List, Optional, Tuple
from telethon.tl.types import Channel, Message, MessageMediaUnsupported


SEARCH_COOLDOWN = 1 #  Make sure this is consistent across files if needed

def generate_name_variations(name: str) -> List[str]:
    """إنشاء تنويعات مختلفة من اسم الفيلم"""
    variations = [name]

    # إزالة أل التعريف
    if name.startswith('ال'):
        variations.append(name[2:])

    # العمل فقط مع الكلمة الأولى (اسم الفيلم غالبًا)
    words = name.split()
    if words:
        variations.append(words[0])

    # إذا كان الاسم باللغة العربية والإنجليزية معًا، افصل بينهما
    arabic_part = ''.join([c for c in name if ord(c) > 128])
    english_part = ''.join([c for c in name if ord(c) < 128 and c.isalnum()])

    if arabic_part and english_part:
        variations.append(arabic_part.strip())
        variations.append(english_part.strip())

    return variations

def get_search_keywords(query: str) -> List[str]:
    """استخراج كلمات البحث الرئيسية من الاستعلام"""
    # تنظيف النص
    query = re.sub(r'[^\w\s]', ' ', query.lower())
    query = re.sub(r'\s+', ' ', query).strip()

    keywords = []
    words = query.split()

    # إضافة الكلمات الأصلية
    keywords.extend([w for w in words if len(w) > 0]) # <--- تم تعديل الشرط هنا ليشمل الكلمات القصيرة

    # إضافة الكلمة الأولى والثانية مجتمعتين إذا وجدت
    if len(words) >= 2:
        keywords.append(f"{words[0]} {words[1]}")

    # إزالة التكرارات
    return list(set(keywords))

async def search_movie_in_channel(self, channel_entity: Channel, movie_name: str) -> Optional[Tuple[str, str, Message]]:
    """البحث عن الفيلم في القناة بعدة طرق"""
    try:
        main_keywords =  self.get_search_keywords(movie_name) # <---  استخدام دالة استخراج الكلمات الرئيسية هنا

        self.logger.info(f"البحث عن '{movie_name}' في قناة '{channel_entity.title}' (ID: {channel_entity.id})") # <--- تسجيل إضافي قبل البحث الفعلي

        # تهيئة المتغيرات اللي ممكن ترجع من البحث
        post_link = None
        title = None
        message_obj = None

        # طريقة 1: البحث عن طريق الكلمات المفتاحية "فيلم" أو "مسلسل" أولاً
        async for message in self.client.iter_messages(channel_entity, limit=200):
            if not message.text:
                continue
            if message.media and not isinstance(message.media, type(None)):
                if message.media and isinstance(message.media, MessageMediaUnsupported):
                    continue

            msg_text = message.text.lower()
            lines = msg_text.splitlines() # تقسيم الرسالة لسطور

            # تسجيل محتوى الرسالة اللي بيتم البحث فيها
            self.logger.debug(f"فحص الرسالة (ID: {message.id}) في قناة '{channel_entity.title}': النص = '{msg_text[:100]}...'") # تسجيل أول 100 حرف من الرسالة

            # البحث في كل سطر عن الكلمات المفتاحية
            for line in lines[:self.config["search_lines_limit"]]: # البحث في أول كام سطر بس
                if "فيلم" in line.lower() or "مسلسل" in line.lower(): #  بندور على الكلمات المفتاحية في السطر ده
                    search_term = line.lower().replace("فيلم", "").replace("مسلسل", "").strip() #  ناخد باقي السطر كـ اسم الفيلم/المسلسل

                    if movie_name.lower() in search_term: #  نتأكد الاسم المطلوب موجود في اللي استخرجناه
                        if channel_entity.username:
                            post_link = f"https://t.me/{channel_entity.username}/{message.id}"
                        else:
                            post_link = f"https://t.me/c/{str(channel_entity.id)[4:]}/{message.id}"

                        title = message.text.split('\n')[0]
                        message_obj = message #  حفظ كائن الرسالة هنا
                        self.logger.info(f"تم العثور على الفيلم '{movie_name}' في قناة '{channel_entity.title}' بالكلمات المفتاحية، الرسالة ID: {message.id}") # تسجيل تفصيلي للنتيجة
                        return post_link, title, message_obj #  لو لاقينا الكلمة المفتاحية والاسم ، يبقى تمام، نرجع النتيجة

        # طريقة 2: لو مالقيناش بالطريقة الأولى، نرجع للطرق القديمة (بحث بالنص الكامل والكلمات الرئيسية)
        async for message in self.client.iter_messages(channel_entity, limit=200):
             if not message.text:
                continue
             if message.media and not isinstance(message.media, type(None)):
                if message.media and isinstance(message.media, MessageMediaUnsupported):
                    continue

             if self.config["search_full_message"]:
                 msg_text = message.text.lower()
             else:
                 # ---  هنا التعديل: هناخد أول عدد سطور محدد من الإعدادات ---
                 message_lines = message.text.split('\n')
                 first_n_lines = '\n'.join(message_lines[:self.config["search_lines_limit"]]).lower()
                 msg_text = first_n_lines

             # تسجيل محتوى الرسالة اللي بيتم البحث فيها (للطرق التانية)
             self.logger.debug(f"فحص الرسالة (ID: {message.id}) في قناة '{channel_entity.title}' للطرق الأخرى: النص = '{msg_text[:100]}...'") # تسجيل أول 100 حرف للبحث بالطرق الأخرى

             # طريقة 2.1: البحث عن النص الكامل
             if movie_name.lower() in msg_text: #  ونبحث عن الاسم مباشرة
                 if channel_entity.username:
                     post_link = f"https://t.me/{channel_entity.username}/{message.id}"
                 else:
                     post_link = f"https://t.me/c/{str(channel_entity.id)[4:]}/{message.id}"

                 title = message.text.split('\n')[0]
                 message_obj = message #  حفظ كائن الرسالة هنا
                 self.logger.info(f"تم العثور على الفيلم '{movie_name}' في قناة '{channel_entity.title}' بالنص الكامل، الرسالة ID: {message.id}") # تسجيل تفصيلي للنتيجة
                 return post_link, title, message_obj

             # طريقة 2.2: البحث عن جميع الكلمات الرئيسية معًا
             if main_keywords:
                 all_keywords_found = True
                 for keyword in main_keywords: #  لوب على الكلمات الرئيسية
                     if keyword.lower() not in msg_text: #  وندور على كل كلمة رئيسية في الرسالة
                         all_keywords_found = False
                         break
                 if all_keywords_found: #  لو كل الكلمات الرئيسية موجودة
                     if channel_entity.username:
                         post_link = f"https://t.me/{channel_entity.username}/{message.id}"
                     else:
                         post_link = f"https://t.me/c/{str(channel_entity.id)[4:]}/{message.id}"

                     title = message.text.split('\n')[0]
                     message_obj = message #  حفظ كائن الرسالة هنا
                     self.logger.info(f"تم العثور على الفيلم '{movie_name}' بالكلمات الرئيسية ({main_keywords}) في قناة '{channel_entity.title}'، الرسالة ID: {message.id}") # تسجيل تفصيلي للنتيجة
                     return post_link, title, message_obj

         # طريقة 2.3: البحث بمجموعة من الكلمات متتالية (مش هنعدلها عشان التنويعات ممكن تعقد الموضوع)

         # طريقة 2.4: البحث بمطابقة نسبة من الكلمات المهمة (مش هنعدلها بردو لنفس السبب)

        self.logger.info(f"لم يتم العثور على الفيلم '{movie_name}' في قناة '{channel_entity.title}'.") # تسجيل في حالة عدم العثور على الفيلم
        return None
    except Exception as e:
        self.logger.error(f"خطأ في البحث عن الفيلم '{movie_name}' في القناة '{channel_entity.title}': {str(e)}")
        return None


async def search_movie_monitored(self, movie_name: str) -> Optional[Tuple[str, str]]: # <--- تم تغيير الاسم هنا
    """البحث عن فيلم في القنوات المراقبة فقط بالطريقة المطورة""" # <---  تعديل الوصف

    search_in_channels = self.config["monitored_channels"] # البحث في القنوات المراقبة بس

    # ---  الخطوة الأولى: البحث في القنوات المراقبة ---
    self.logger.info(f"البحث عن '{movie_name}' في القنوات المراقبة...")
    try:
        for channel_info in search_in_channels:
            try:
                channel_entity = await self.client.get_entity(channel_info['id'])

                # طريقة 1: البحث العادي بالكلمات
                result = await self.search_movie_in_channel(channel_entity, movie_name)
                if result:
                    post_link, title, _ = result # <--- unpacking 3 values but only using 2
                    return post_link, title

                # طريقة 2: البحث بالهاشتاغ
                result = await self.search_by_hashtags(channel_entity, movie_name) # <---  استدعاء دالة البحث بالهاشتاجات
                if result:
                    post_link, title, message = result
                    return post_link, title

                # انتظار قليل بين عمليات البحث في القنوات
                await asyncio.sleep(SEARCH_COOLDOWN)
            except Exception as e:
                self.logger.error(f"خطأ في البحث في القناة '{channel_info['title']}': {str(e)}")

        return None # لو البحث خلص في القنوات المراقبة وملاقتش نتيجة مؤكدة، يبقى نرجع None

    except Exception as e:
        self.logger.error(f"حصل خطأ غير متوقع في دالة search_movie_monitored: {str(e)}")
        return None

async def search_by_hashtags(self, channel_entity: Channel, movie_name: str) -> Optional[Tuple[str, str, Message]]: # <--- دالة البحث بالهاشتاجات الجديدة
    """البحث عن فيلم في القناة باستخدام الهاشتاجات"""
    try:
        hashtags = self.generate_hashtag_variations(movie_name) # توليد تنويعات الهاشتاجات

        self.logger.info(f"البحث عن '{movie_name}' في قناة '{channel_entity.title}' (ID: {channel_entity.id}) باستخدام الهاشتاجات: {hashtags}") # تسجيل إضافي قبل البحث بالهاشتاج

        post_link = None
        title = None
        message_obj = None


        for hashtag in hashtags: #  لوب على الهاشتاجات المولدة
            async for message in self.client.iter_messages(channel_entity, limit=50, search=hashtag): #  limit البحث بالهاشتاج بيكون أبطأ، فخلينا 50 رسالة بس كفاية
                if not message.text:
                    continue
                if message.media and not isinstance(message.media, type(None)):
                    if message.media and isinstance(message.media, MessageMediaUnsupported):
                        continue

                msg_text = message.text.lower() #  نص الرسالة
                lines = msg_text.splitlines() # تقسيم الرسالة لسطور

                # تسجيل محتوى الرسالة اللي بيتم البحث فيها (بالهاشتاج)
                self.logger.debug(f"فحص الرسالة (ID: {message.id}) في قناة '{channel_entity.title}' بالهاشتاج '{hashtag}': النص = '{msg_text[:100]}...'") # تسجيل أول 100 حرف من الرسالة للبحث بالهاشتاج

                # البحث في أول كام سطر بس عن اسم الفيلم
                for line in lines[:self.config["search_lines_limit"]]:
                    if movie_name.lower() in line.lower(): #  لو لقينا اسم الفيلم في السطر ده
                        if channel_entity.username:
                            post_link = f"https://t.me/{channel_entity.username}/{message.id}"
                        else:
                            post_link = f"https://t.me/c/{str(channel_entity.id)[4:]}/{message.id}"
                        title = message.text.split('\n')[0]
                        message_obj = message #  حفظ كائن الرسالة هنا
                        self.logger.info(f"تم العثور على الفيلم '{movie_name}' في قناة '{channel_entity.title}' بالهاشتاج '{hashtag}'، الرسالة ID: {message.id}") # تسجيل تفصيلي بالنتيجة
                        return post_link, title, message_obj #  نرجع النتيجة على طول

        self.logger.info(f"لم يتم العثور على الفيلم '{movie_name}' في قناة '{channel_entity.title}' باستخدام الهاشتاجات: {hashtags}.") # تسجيل حالة عدم العثور بالهاشتاجات
        return None

    except Exception as e:  # <-- تمت إضافة البلوك المطلوب هنا
        self.logger.error(f"خطأ في البحث بالهاشتاجات: {str(e)}")
        return None


async def search_movie_expanded(self, movie_name: str) -> Optional[Tuple[str, str]]: # <--- دالة البحث الموسع الجديدة
    """البحث عن فيلم في كل الدردشات (موسع) بالطريقة المطورة""" # <---  تعديل الوصف

    search_in_channels = self.config["monitored_channels"] # القنوات المراقبة (عشان نستثنيها بعدين)

    # ---  الخطوة الأولى: البحث الموسع في كل الدردشات ---
    self.logger.info(f"البحث الموسع عن '{movie_name}' في كل الدردشات...")
    dialogs = await self.client.get_dialogs()
    for dialog in dialogs:
        if dialog.name == 'me':
            continue
        is_monitored_channel = False # هنتحقق إذا كانت القناة من القنوات المراقبة ولا لأ
        if isinstance(dialog.entity, Channel):
            for channel_info in search_in_channels:
                if channel_info['id'] == dialog.entity.id:
                    is_monitored_channel = True
                    break

        if is_monitored_channel: # لو القناة من القنوات المراقبة، هنتخطاها عشان بحثنا فيها خلاص
            continue

        channel_entity = dialog.entity
        try:
            if isinstance(channel_entity, (Channel, Chat, User)):
                # طريقة 1: البحث العادي بالكلمات
                result = await self.search_movie_in_channel(channel_entity, movie_name)
                if result:
                    post_link, title, _ = result # <--- unpacking 3 values but only using 2
                    return post_link, title

                # طريقة 2: البحث بالهاشتاجات
                result = await self.search_by_hashtags(channel_entity, movie_name) # <--- إضافة البحث بالهاشتاجات في البحث الموسع
                if result:
                    post_link, title, message = result
                    return post_link, title


            # انتظار قليل بين عمليات البحث في القنوات
            await asyncio.sleep(SEARCH_COOLDOWN)
        except Exception as e:
            self.logger.error(f"خطأ في البحث الموسع في الدردشة '{dialog.name}': {str(e)}")

    # ---  محاولة البحث مرة أخرى بتنويعات الاسم لو مفيش نتيجة مؤكدة ---
    if ' ' in movie_name:
        variations = self.generate_name_variations(movie_name)
        for variation in variations[1:]:
            self.logger.info(f"إعادة البحث الموسع عن تنويعة الاسم: '{variation}'") # <--- تعديل نوع البحث في التسجيل
            search_result = await self.search_movie_expanded(variation) # <---  استدعاء دالة البحث الموسع هنا
            if search_result:
                return search_result

        return None # لو البحث الموسع خلص في كل حتة وملاقتش نتيجة مؤكدة، يبقى نرجع None
    return None # لو مفيش تنويعات للأسماء، وبردو مفيش نتيجة، يبقى نرجع None

async def search_movie(self, movie_name: str, is_group_request: bool = False) -> Optional[Tuple[str, str]]: # <---  تعديل دالة البحث الرئيسية عشان تدعم البحث في الجروبات بس
    """البحث عن فيلم في القنوات المراقبة ثم البحث الموسع في كل الدردشات (مع مراعاة مصدر الطلب)"""

    # ---  تعديل معالجة كلمات البحث "فيلم" و "مسلسل" ---
    original_movie_name = movie_name #  احتفظ بالاسم الأصلي للتسجيل

    if movie_name.lower().startswith("فيلم "):
        movie_name = movie_name[5:].strip() #  احذف "فيلم " والمسافة الزيادة
    elif movie_name.lower().startswith("مسلسل "):
        movie_name = movie_name[6:].strip() #  احذف "مسلسل " والمسافة الزيادة

    if movie_name.lower().endswith(" فيلم"):
        movie_name = movie_name[:-5].strip() # احذف " فيلم" من النهاية
    elif movie_name.lower().endswith(" مسلسل"):
        movie_name = movie_name[:-6].strip() # احذف " مسلسل" من النهاية


    if is_group_request: # <---  Check: لو الطلب جاي من جروب
        self.logger.info(f"بحث عن '{original_movie_name}' (معدل: '{movie_name}') في القنوات المراقبة فقط (طلب جروب)...") # <---  تسجيل نوع البحث والاسم المعدل
        result_monitored = await self.search_movie_monitored(movie_name) #  بحث في القنوات المراقبة بس
        if result_monitored:
            return result_monitored #  لو لاقى في القنوات المراقبة، يرجع النتيجة على طول
        return None #  لو مالقاش في القنوات المراقبة في حالة طلب الجروب، يرجع None بدون بحث موسع
    else: #  لو الطلب مش من جروب (يعني من DM أو من الأدمن)
        self.logger.info(f"بحث عن '{original_movie_name}' (معدل: '{movie_name}') في القنوات المراقبة ثم بحث موسع...") # <--- تسجيل نوع البحث والاسم المعدل
        result_monitored = await self.search_movie_monitored(movie_name) #  بحث في القنوات المراقبة الأول
        if result_monitored:
            return result_monitored #  لو لاقى في القنوات المراقبة، يرجع النتيجة على طول

        result_expanded = await self.search_movie_expanded(movie_name) #  لو مالقاش في القنوات المراقبة، يبحث موسع
        if result_expanded:
            return result_expanded #  لو لاقى في البحث الموسع، يرجع النتيجة

        return None #  لو مالقاش في الاتنين، يرجع None


async def search_movie_everywhere_video(self, movie_name: str) -> Optional[Tuple[str, str, Message]]:
    """البحث عن فيلم فيديو في كل الدردشات وإرجاع الرابط وكائن الرسالة"""
    excluded_chats_ids = set()  # لتتبع الشاتات المستبعدة بسبب عدم دعم التحويل
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        dialogs = await self.client.get_dialogs()
        for dialog in dialogs:
            if dialog.name == 'me':
                continue
            channel_entity = dialog.entity
            if not isinstance(channel_entity, (Channel, Chat, User)):
                continue
            if channel_entity.id in excluded_chats_ids: # تخطي الشاتات المستبعدة في المحاولات اللاحقة
                continue

            try:
                async for message in self.client.iter_messages(channel_entity, limit=200):
                    if not message.media or not message.media.video: # البحث عن رسائل الفيديو فقط
                        continue
                    if not message.text:
                        continue
                    if message.media and isinstance(message.media, MessageMediaUnsupported):
                        continue

                    msg_text = message.text.lower()
                    lines = msg_text.splitlines()

                    for line in lines[:self.config["search_lines_limit"]]:
                        if movie_name.lower() in line.lower():
                            if await self.is_forwardable_chat(channel_entity): # التحقق من قابلية التحويل
                                return await self.process_video_result(channel_entity, message, movie_name)
                            else:
                                excluded_chats_ids.add(channel_entity.id) # استبعاد الشات لو التحويل مش مدعوم
                                self.logger.warning(f"تم استبعاد الشات '{channel_entity.title}' (ID: {channel_entity.id}) بسبب عدم دعم التحويل.")
                                break # الخروج من اللوب الداخلي والذهاب للشات التالي
                await asyncio.sleep(SEARCH_COOLDOWN) # انتظار بين الشاتات
            except Exception as e:
                self.logger.error(f"خطأ في البحث في الدردشة '{dialog.name}' (للبحث عن فيديو): {str(e)}")
        retry_count += 1
        if retry_count < max_retries and excluded_chats_ids: # إعادة المحاولة إذا كان فيه شاتات مستبعدة ولسه فيه محاولات
            self.logger.info(f"إعادة محاولة البحث عن فيديو '{movie_name}' (المحاولة رقم {retry_count}) مع استبعاد الشاتات الغير قابلة للتحويل.")
        else:
            break # الخروج من اللوب لو خلصت المحاولات أو مفيش شاتات مستبعدة

    return None

