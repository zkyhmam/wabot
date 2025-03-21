import re
from typing import List

def generate_hashtag_variations_util(self, movie_name: str) -> List[str]: # <--- دالة توليد الهاشتاجات
    """توليد تنويعات مختلفة من الهاشتاجات لاسم الفيلم"""
    base_name = re.sub(r'\s+', '', movie_name.lower()) #  اسم الفيلم الأساسي بدون مسافات وحروف صغيرة
    variations = []

    # هاشتاجات بسيطة
    variations.append(f"#{base_name}") #  #اسم_الفيلم
    variations.append(f"#{base_name}movie") #  #اسم_الفيلمmovie
    variations.append(f"#movie{base_name}") #  #movieاسم_الفيلم

    # هاشتاجات بكلمات إضافية
    variations.append(f"#فيلم{base_name}") #  #فيلماسم_الفيلم
    variations.append(f"#مسلسل{base_name}") #  #مسلسلاسم_الفيلم
    variations.append(f"#cartoon{base_name}") #  #cartoonاسم_الفيلم
    variations.append(f"#انمي{base_name}") # #انمياسم_الفيلم

    # لو الاسم فيه أكتر من كلمة، نستخدم كل كلمة لوحدها كـ هاشتاج
    words = base_name.split()
    if len(words) > 1:
        for word in words:
            variations.append(f"#{word}") #  #كلمة_من_الاسم

    return list(set(variations)) #  إرجاع التنويعات بدون تكرار

