require('dotenv').config();
const { google } = require('googleapis');
const { sendErrorMessage, sendFormattedMessage } = require("./messageUtils");
const axios = require("axios");
const NodeCache = require('node-cache');
const fs = require('fs');
const path = require('path');
const fileType = require('file-type');

// استخدام قيم API مباشرة بدلاً من متغيرات البيئة
const GOOGLE_API_KEYS = ["AIzaSyAJoaKYgRjM6uBgCUai1l8MXD4dSnxfkhQ", "AIzaSyDGXCFF6aIa6NVXYwtnQ4aZSjtMNR8KLC0"];
const CSE_ID = "d3ec272a565074ab5";
const BOT_NAME = process.env.BOT_NAME || "Zaky AI";
const SAFE_SEARCH = "off";
const IMAGE_SIZE = process.env.IMAGE_SIZE || "large";
const MAX_IMAGES = parseInt(process.env.MAX_IMAGES || "3");
const MAX_GIFS = 1; // العدد الافتراضي للصور المتحركة (1)
const MAX_GIFS_LIMIT = 3; // الحد الأقصى للصور المتحركة (3)
const MAX_IMAGES_LIMIT = 5; // الحد الأقصى للصور العادية (5)
const GIF_RETRY_ATTEMPTS = 3; // عدد محاولات إعادة البحث إذا لم تكن الصورة متحركة

console.log(`🔑 مفاتيح API المكونة: ${GOOGLE_API_KEYS.length} مفاتيح متاحة`);
console.log(`🔍 تم تكوين CSE_ID: ${CSE_ID}`);
console.log(`🔒 البحث الآمن: ${SAFE_SEARCH}`);

const searchCache = new NodeCache({ stdTTL: 3600 });

let currentApiKeyIndex = 0;

function getNextApiKey() {
    if (GOOGLE_API_KEYS.length === 0) {
        throw new Error("لم يتم توفير مفاتيح Google API");
    }
    const apiKey = GOOGLE_API_KEYS[currentApiKeyIndex];
    console.log(`🔄 استخدام مفتاح API رقم ${currentApiKeyIndex + 1}: ${apiKey.substring(0, 8)}...`);
    currentApiKeyIndex = (currentApiKeyIndex + 1) % GOOGLE_API_KEYS.length;
    return apiKey;
}

// التحقق مما إذا كانت الصورة متحركة بالفعل
async function isAnimatedGif(buffer) {
    try {
        // استخدام file-type للتحقق من نوع الملف
        const fileInfo = await fileType.fromBuffer(buffer);
        
        if (!fileInfo || fileInfo.mime !== 'image/gif') {
            return false;
        }
        
        // التحقق من وجود أكثر من إطار في صورة GIF
        // GIF المتحركة تحتوي على أكثر من إطار
        // هذه طريقة مبسطة: نبحث عن علامة "NETSCAPE2.0" التي توجد عادة في GIF المتحركة
        const hasAnimation = buffer.includes(Buffer.from([0x21, 0xFF, 0x0B, 0x4E, 0x45, 0x54, 0x53, 0x43, 0x41, 0x50, 0x45, 0x32, 0x2E, 0x30]));
        
        return hasAnimation;
    } catch (error) {
        console.error("❌ خطأ أثناء التحقق من حالة حركة الـ GIF:", error);
        return false; // في حالة الشك، نفترض أنها ليست متحركة
    }
}

function parseSearchOptions(text, isGifCommand = false) {
    const options = {
        query: text,
        safeSearch: SAFE_SEARCH,
        imageSize: IMAGE_SIZE,
        imageType: isGifCommand ? "animated" : "any",
        maxResults: isGifCommand ? MAX_GIFS : MAX_IMAGES
    };

    // البحث عن أنماط مثل -3، -4، إلخ
    const countRegex = /-(\d+)/;
    const countMatch = text.match(countRegex);
    
    if (countMatch && countMatch[1]) {
        const count = parseInt(countMatch[1]);
        const maxAllowed = isGifCommand ? MAX_GIFS_LIMIT : MAX_IMAGES_LIMIT;
        
        if (count > 0 && count <= maxAllowed) {
            options.maxResults = count;
            options.query = options.query.replace(countMatch[0], '').trim();
            console.log(`🔢 تم تحديد عدد ${isGifCommand ? 'الصور المتحركة' : 'الصور'} إلى: ${count}`);
        }
    }

    // لأمر الصور العادية، ابحث عن تنسيقات أخرى مثل -jpg، -png، إلخ
    if (!isGifCommand) {
        const typeRegex = /-(\w+)/g;
        let match;
        
        while ((match = typeRegex.exec(text)) !== null) {
            if (/^\d+$/.test(match[1])) {
                continue; // تخطي إذا كان رقمًا بالفعل (للعدد)
            }
            
            const optionValue = match[1].toLowerCase();
            options.query = options.query.replace(match[0], '').trim();
            
            // خيارات نوع الصورة
            if (['png', 'jpg', 'bmp'].includes(optionValue)) {
                options.imageType = optionValue;
                console.log(`🖼️ تم تعيين نوع الصورة إلى: ${optionValue}`);
            }
            // خيارات الحجم
            else if (['small', 'medium', 'large', 'xlarge'].includes(optionValue)) {
                options.imageSize = optionValue;
                console.log(`📏 تم تعيين حجم الصورة إلى: ${optionValue}`);
            }
            // خيارات الفلتر
            else if (optionValue === 'safe') {
                options.safeSearch = 'active';
                console.log(`🔒 تم تفعيل البحث الآمن`);
            }
            else if (optionValue === 'off') {
                options.safeSearch = 'off';
                console.log(`🔓 تم تعطيل البحث الآمن`);
            }
        }
    }

    return options;
}


// وظيفة للبحث عن الصور أو صور GIF
const searchMedia = async (sock, chatId, message, text, isGifCommand = false) => {
    if (!text) {
        if (isGifCommand) {
            await sendFormattedMessage(sock, chatId, "🎞️ *ابحث عن صور متحركة GIF بسهولة!*\n\nاكتب الكلمة اللي عايز تبحث عنها بعد \`.gif` 🌟\n\n*مثال:* \`.gif قطط كيوت` 😺\n\n*خيارات:*\n- `-2` لعدد الصور المتحركة (من 1 لـ 3) 🔢");
        } else {
            await sendFormattedMessage(sock, chatId, "🖼️ *ابحث عن صور بسهولة!*\n\nاكتب الكلمة اللي عايز تبحث عنها بعد \`.img` 🌟\n\n*مثال:* \`.img قطط كيوت` 😺\n\n*خيارات:*\n- `-png` أو `-jpg` لنوع الصورة 📸\n- `-3` لعدد الصور (من 1 لـ 5) 🔢\n- `-large` أو `-medium` لحجم الصورة 📏\n- `-safe` لتفعيل الفلتر الأمني 🔒");
        }
        return;
    }

    try {
        console.log(`🔍 ${isGifCommand ? 'gifSearch' : 'imageSearch'}: بدء البحث عن: "${text}"`);

        const searchOptions = parseSearchOptions(text, isGifCommand);
        console.log(`🔍 ${isGifCommand ? 'gifSearch' : 'imageSearch'}: خيارات البحث:`, searchOptions);

        const cacheKey = JSON.stringify({...searchOptions, isGif: isGifCommand});

        let mediaUrls = searchCache.get(cacheKey);

        if (!mediaUrls) {
            await sendFormattedMessage(sock, chatId, `🔍 جاري البحث عن "${searchOptions.query}"...`);

            const apiKey = getNextApiKey();
            const customSearch = google.customsearch('v1');

            console.log(`🔍 جاري البحث بالمعلمات:
               - الاستعلام: ${searchOptions.query}
               - CSE_ID: ${CSE_ID}
               - البحث الآمن: ${searchOptions.safeSearch}
               - حجم الصورة: ${searchOptions.imageSize}
               - الحد الأقصى للنتائج: ${searchOptions.maxResults}
               - نوع الصورة: ${searchOptions.imageType}
               - بحث عن GIF: ${isGifCommand}`);

            try {
                // تحسين للبحث عن GIF متحركة
                if (isGifCommand) {
                    // نضيف كلمات مفتاحية إضافية تزيد من احتمالية الحصول على GIF متحركة فعلاً
                    searchOptions.query = `${searchOptions.query} animated gif motion`;
                }
                
                // إعداد معلمات البحث
                let searchParams = {
                    auth: apiKey,
                    cx: CSE_ID,
                    q: searchOptions.query,
                    searchType: 'image',
                    num: searchOptions.maxResults * (isGifCommand ? 3 : 1), // نزيد العدد لضمان العثور على GIF متحركة
                    safe: searchOptions.safeSearch
                };
                
                // للصور المتحركة
                if (isGifCommand) {
                    searchParams.fileType = 'gif';
                    searchParams.imgType = 'animated';
                    searchParams.rights = 'cc_publicdomain cc_attribute cc_sharealike'; // نبحث عن محتوى متاح بحرية
                } 
                // لأنواع الصور الأخرى
                else if (searchOptions.imageType !== 'any') {
                    searchParams.fileType = searchOptions.imageType;
                }
                
                // إضافة الحجم إذا تم تحديده
                if (searchOptions.imageSize) {
                    searchParams.imgSize = searchOptions.imageSize;
                }
                
                console.log("📝 معلمات البحث النهائية:", JSON.stringify(searchParams, null, 2));
                
                const response = await customSearch.cse.list(searchParams);

                console.log(`✅ API استجابت بالحالة: ${response.status}`);
                console.log(`📊 البيانات المستلمة: ${response.data ? 'نعم' : 'لا'}`);
                console.log(`🔢 إجمالي النتائج: ${response.data?.searchInformation?.totalResults || 'غير معروف'}`);
                console.log(`📋 العناصر في الاستجابة: ${response.data?.items?.length || 0}`);

                const items = response.data.items;

                if (!items || items.length === 0) {
                    console.log(`❌ ${isGifCommand ? 'gifSearch' : 'imageSearch'}: لم يتم العثور على نتائج للبحث.`);
                    await sendErrorMessage(sock, chatId, `❌ مش لاقي ${isGifCommand ? 'صور متحركة' : 'صور'} تناسب بحثك 😕 جرب كلمات تانية 🔄`);
                    return;
                }

                mediaUrls = items.map(item => ({
                    url: item.link,
                    title: item.title,
                    source: item.displayLink
                }));
                
                console.log(`✅ تم العثور على ${mediaUrls.length} ${isGifCommand ? 'صور متحركة' : 'صور'}`);
                // لا نقوم بتخزين نتائج GIF في ذاكرة التخزين المؤقت حتى نتحقق أولاً من أنها متحركة بالفعل
                if (!isGifCommand) {
                    searchCache.set(cacheKey, mediaUrls);
                }
            } catch (searchError) {
                console.error(`❌ خطأ في البحث عن ${isGifCommand ? 'صور متحركة' : 'صور'}:`, searchError);
                console.error("تفاصيل الخطأ:", searchError.response?.data || searchError.message);
                throw searchError;
            }
        } else {
            console.log(`🔍 ${isGifCommand ? 'gifSearch' : 'imageSearch'}: تم استخدام النتائج المخزنة مؤقتًا`);
        }

        let successCount = 0;
        let failCount = 0;
        let validatedGifs = [];

        if (isGifCommand) {
            await sendFormattedMessage(sock, chatId, `⏳ جاري التحقق من ${mediaUrls.length} صورة متحركة...`);
            
            // التحقق من أن الـ GIF متحرك بالفعل قبل إرساله
            for (const media of mediaUrls) {
                if (validatedGifs.length >= searchOptions.maxResults) {
                    break; // وصلنا للعدد المطلوب من الـ GIF المتحركة
                }
                
                try {
                    console.log(`🔍 جاري التحقق من GIF: ${media.url}`);
                    
                    const mediaResponse = await axios.get(media.url, {
                        responseType: 'arraybuffer',
                        headers: {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                        },
                        timeout: 15000
                    });
                    
                    const buffer = Buffer.from(mediaResponse.data, 'binary');
                    
                    // التحقق من أن الملف GIF وأنه متحرك
                    if (mediaResponse.headers['content-type'].includes('image/gif') && await isAnimatedGif(buffer)) {
                        console.log(`✅ تم التحقق من أن الـ GIF متحرك: ${media.url}`);
                        validatedGifs.push({...media, buffer});
                    } else {
                        console.log(`❌ الملف ليس GIF متحرك: ${media.url}`);
                    }
                } catch (error) {
                    console.error(`❌ خطأ أثناء تحميل أو التحقق من GIF: ${media.url}`, error.message);
                }
            }
            
            // إذا لم نجد أي GIF متحرك، نخبر المستخدم
            if (validatedGifs.length === 0) {
                await sendErrorMessage(sock, chatId, `❌ لم أتمكن من العثور على صور متحركة حقيقية لبحثك 😕 جرب كلمات تانية 🔄`);
                return;
            }
            
            // استخدام الـ GIF المتحركة المتحقق منها فقط
            mediaUrls = validatedGifs;
        }

        for (const media of mediaUrls) {
            console.log(`🔍 ${isGifCommand ? 'gifSearch' : 'imageSearch'}: جاري إرسال ${isGifCommand ? 'الصورة المتحركة' : 'الصورة'}: ${media.url}`);

            try {
                // استخدام البفر المخزن مسبقاً للـ GIF المتحركة بدلاً من إعادة تنزيله
                let buffer;
                if (isGifCommand && media.buffer) {
                    buffer = media.buffer;
                } else {
                    const mediaResponse = await axios.get(media.url, {
                        responseType: 'arraybuffer',
                        headers: {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                        },
                        timeout: 15000 // وقت انتظار أطول للصور المتحركة
                    });

                    console.log(`✅ تم تنزيل ${isGifCommand ? 'GIF' : 'الصورة'}: ${mediaResponse.status} (${mediaResponse.headers['content-type']})`);
                    console.log(`📊 الحجم: ${mediaResponse.data.length} بايت`);

                    buffer = Buffer.from(mediaResponse.data, 'binary');
                }

                // طريقة خاصة لإرسال صور GIF متحركة
                if (isGifCommand) {
                    // إنشاء مجلد مؤقت إذا لم يكن موجودًا
                    const tmpDir = path.join(process.cwd(), 'tmp');
                    if (!fs.existsSync(tmpDir)) {
                        fs.mkdirSync(tmpDir, { recursive: true });
                    }
                    
                    // حفظ GIF مؤقتًا
                    const tmpFile = path.join(tmpDir, `gif_${Date.now()}_${Math.random().toString(36).substring(2, 8)}.gif`);
                    fs.writeFileSync(tmpFile, buffer);
                    
                    try {
                        // تحويل GIF إلى MP4 للتوافق الأفضل مع WhatsApp
                        const ffmpeg = require('fluent-ffmpeg');
                        const outputFile = tmpFile.replace('.gif', '.mp4');
                        
                        // إنشاء وعد للانتظار حتى يكتمل التحويل
                        await new Promise((resolve, reject) => {
                            ffmpeg(tmpFile)
                                .outputOptions([
                                    '-movflags faststart',
                                    '-pix_fmt yuv420p',
                                    '-vf "scale=trunc(iw/2)*2:trunc(ih/2)*2"',
                                    '-preset ultrafast',
                                    '-f mp4'
                                ])
                                .save(outputFile)
                                .on('end', resolve)
                                .on('error', reject);
                        });
                        
                        console.log(`✅ تم تحويل GIF إلى MP4 بنجاح: ${outputFile}`);
                        
                        // إرسال MP4 كفيديو مع خاصية gifPlayback
                        await sock.sendMessage(chatId, {
                            video: fs.readFileSync(outputFile),
                            gifPlayback: true,
                            caption: `🎬 *${media.title}*`,
                            mimetype: 'video/mp4'
                        }, { quoted: message });
                        
                        console.log(`✅ تم إرسال GIF كفيديو متحرك بنجاح`);
                        
                        // حذف الملفات المؤقتة
                        if (fs.existsSync(tmpFile)) fs.unlinkSync(tmpFile);
                        if (fs.existsSync(outputFile)) fs.unlinkSync(outputFile);
                        
                    } catch (conversionError) {
                        console.error("❌ فشل تحويل GIF إلى MP4:", conversionError.message);
                        
                        // محاولة بديلة: إرسال GIF كفيديو مباشرة
                        try {
                            await sock.sendMessage(chatId, {
                                video: fs.readFileSync(tmpFile),
                                gifPlayback: true,
                                caption: `🎬 *${media.title}*`,
                                mimetype: 'video/gif'
                            }, { quoted: message });
                            
                            console.log(`✅ تم إرسال GIF كفيديو بدون تحويل بنجاح`);
                            
                        } catch (directGifError) {
                            console.error("❌ فشل إرسال GIF كفيديو مباشر:", directGifError.message);
                            
                            // كملاذ أخير، نرسله كصورة ثابتة
                            await sock.sendMessage(chatId, {
                                image: buffer,
                                caption: `🎬 *${media.title}*\n\n(تم إرسالها كصورة ثابتة لأسباب تقنية)`
                            }, { quoted: message });
                            
                            console.log(`⚠️ تم إرسال GIF كصورة ثابتة كحل أخير`);
                        }
                        
                        // حذف الملفات المؤقتة
                        if (fs.existsSync(tmpFile)) fs.unlinkSync(tmpFile);
                    }
                } else {
                    // إرسال الصور العادية كالمعتاد
                    await sock.sendMessage(chatId, {
                        image: buffer,
                        caption: `🖼️ *${media.title}*`
                    }, { quoted: message });
                }

                successCount++;
                console.log(`✅ ${isGifCommand ? 'gifSearch' : 'imageSearch'}: تم إرسال ${isGifCommand ? 'الصورة المتحركة' : 'الصورة'} ${successCount} بنجاح`);

                await new Promise(resolve => setTimeout(resolve, 1000)); // مزيد من الوقت بين الإرسالات

            } catch (sendError) {
                console.error(`❌ ${isGifCommand ? 'gifSearch' : 'imageSearch'}: فشل إرسال ${isGifCommand ? 'الصورة المتحركة' : 'الصورة'}:`, sendError.message);
                console.error(`❌ الخطأ الكامل:`, sendError);
                failCount++;
            }
        }

        if (successCount === 0) {
            await sendErrorMessage(sock, chatId, `❌ مقدرتش أبعت أي ${isGifCommand ? 'صور متحركة' : 'صور'} 😔 ممكن الروابط مش شغالة أو الحجم كبير أوي 📏`);
        } else if (failCount > 0) {
            await sendFormattedMessage(sock, chatId, `✅ بعتلك ${successCount} ${isGifCommand ? 'صورة متحركة' : 'صورة'} بنجاح 🎉`);
        }

    } catch (error) {
        console.error(`❌ ${isGifCommand ? 'gifSearch' : 'imageSearch'}: خطأ في البحث أو الإرسال:`, error.message);
        console.error("❌ الخطأ الكامل:", error);

        if (error.message.includes('quota')) {
            await sendErrorMessage(sock, chatId, "❌ معلش، الكوتة اليومية خلصت 😓 جرب تاني بكرة 🙏");
        } else if (error.message.includes('Invalid Value')) {
            await sendErrorMessage(sock, chatId, "❌ فيه مشكلة في طلبك 😕 جرب كلمات تانية 📝");
        } else if (error.message.includes('ETIMEDOUT') || error.message.includes('timeout')) {
            await sendErrorMessage(sock, chatId, "❌ البحث أخد وقت طويل أوي ⏳ ممكن النت بطيء، جرب تاني 🔄");
        } else {
            await sendErrorMessage(sock, chatId, "❌ حصل مشكلة في البحث عن الصور 😔 جرب تاني بعد شوية 🔄");
        }
    }
};

// وظائف البحث عن الصور
const imageSearch = async (sock, chatId, message, text) => {
    return await searchMedia(sock, chatId, message, text, false);
};

// وظيفة خاصة للبحث عن صور GIF
const gifSearch = async (sock, chatId, message, text) => {
    return await searchMedia(sock, chatId, message, text, true);
};

imageSearch.help = ['img <كلمة البحث>', 'image <كلمة البحث>', 'صورة <كلمة البحث>'];
imageSearch.tags = ['tools', 'search', 'media'];
imageSearch.command = /^(img|image|photo|pic|صور|صورة)$/i;

gifSearch.help = ['gif <كلمة البحث>', 'متحركة <كلمة البحث>'];
gifSearch.tags = ['tools', 'search', 'media'];
gifSearch.command = /^(gif|متحركة)$/i;

module.exports = { imageSearch, gifSearch };
