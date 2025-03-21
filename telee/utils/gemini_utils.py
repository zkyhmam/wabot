from typing import Optional, List, Tuple

def recommend_movies_gemini_util(self, request_text: str) -> Optional[List[Tuple[str, str]]]:
    """اقتراح أفلام مشابهة باستخدام Gemini بناءً على طلب المستخدم"""
    try:
        prompt = f"بناءً على طلب المستخدم التالي: '{request_text}'، اقترح 5 أفلام مشابهة. لو المستخدم محدد نوع معين، التزم بالنوع ده. رجع قايمة عناوين الأفلام بس."
        for attempt in range(5):
            try:
                response = self.gemini_model.generate_content(prompt)
                movie_titles = response.text.strip().split('\n')
                if not movie_titles or "مفيش" in response.text.lower() or "لا يوجد" in response.text.lower():
                    return None
                recommendations = []
                for title in movie_titles:
                    search_result = await self.search_movie_monitored(title.strip()) # <---  البحث في القنوات المراقبة بس للاقتراحات كمان
                    if search_result:
                        recommendations.append(search_result)
                if recommendations:
                    return recommendations[:5]
                return None
            except Exception as gemini_error:
                self.logger.error(f"محاولة ({attempt + 1}) فاشلة في الاتصال بـ Gemini للاقتراحات: {gemini_error}")
                await asyncio.sleep(attempt + 1)
        self.logger.error(f"فشل الاتصال بـ Gemini للاقتراحات بعد 5 محاولات.")
        await self.client.send_message(self.config["admin_id"], f"فشل الاتصال بـ Gemini للاقتراحات للطلب: '{request_text}' بعد 5 محاولات.")
        return None
    except Exception as e:
        self.logger.error(f"حصل خطأ غير متوقع في دالة recommend_movies_gemini: {str(e)}")
        return None

