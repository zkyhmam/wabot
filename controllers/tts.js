const { sendErrorMessage, sendFormattedMessage } = require('./messageUtils');
const axios = require('axios');
const fs = require('fs');
const path = require('path');

const ELEVENLABS_API_KEYS = [
    "sk_5505e3319ba72839a0fa96d17ecf6984e7bef65421ad7861",
    "sk_b72cd95601e70f70cb8b2f0ea8bf3e341be4855ac2145994",
    "sk_b4ed7661588f2551e6870754e2906db60ab0ebd269acd3f5",
    "sk_1589e85d0d905c2eee47597fa4fa15870c439331c4744631"
];
const VOICE_IDS = ["IES4nrmZdUBHByLBde0P", "LXrTqFIgiubkrMkwvOUr"]; // حط الصوتين هنا
const DAILY_REQUEST_LIMIT = 5;
const DATA_DIR = path.join(__dirname, '..', 'data');
const ASSETS_DIR = path.join(__dirname, '..', 'assets');
const USAGE_DATA_FILE = path.join(DATA_DIR, 'tts_usage.json');

[DATA_DIR, ASSETS_DIR].forEach(dir => {
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
        console.log(`📁 تم إنشاء المجلد: ${dir}`);
    }
});

let currentApiKeyIndex = 0;
let ttsRequestCounts = new Map();

function loadUsageData() {
    try {
        if (!fs.existsSync(USAGE_DATA_FILE)) {
            console.log("📊 ملف بيانات الاستخدام غير موجود، إنشاء بيانات جديدة");
            return new Map();
        }

        const data = fs.readFileSync(USAGE_DATA_FILE, 'utf8');
        if (!data || data.trim() === '') {
            return new Map();
        }

        const parsedData = JSON.parse(data);
        return new Map(parsedData);
    } catch (error) {
        console.warn(`⚠️ خطأ في تحميل بيانات الاستخدام: ${error.message}`);
        return new Map();
    }
}

function saveUsageData() {
    try {
        const data = JSON.stringify(Array.from(ttsRequestCounts.entries()));
        fs.writeFileSync(USAGE_DATA_FILE, data, 'utf8');
        console.log("💾 تم حفظ بيانات الاستخدام");
    } catch (error) {
        console.error(`❌ فشل حفظ بيانات الاستخدام: ${error.message}`);
    }
}

function resetDailyUsage() {
    console.log("🔄 إعادة تعيين عدادات الاستخدام اليومية");
    ttsRequestCounts = new Map();
    saveUsageData();
}

ttsRequestCounts = loadUsageData();

const scheduleNextReset = () => {
    const now = new Date();
    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);
    tomorrow.setHours(0, 0, 0, 0);

    const timeUntilMidnight = tomorrow - now;
    console.log(`⏰ جدولة إعادة التعيين التالية بعد ${Math.floor(timeUntilMidnight / 1000 / 60)} دقيقة`);

    setTimeout(() => {
        resetDailyUsage();
        scheduleNextReset();
    }, timeUntilMidnight);
};

scheduleNextReset();

function getNextElevenLabsApiKey() {
    const apiKey = ELEVENLABS_API_KEYS[currentApiKeyIndex];
    currentApiKeyIndex = (currentApiKeyIndex + 1) % ELEVENLABS_API_KEYS.length;
    return apiKey;
}

const checkVoiceAvailability = async (apiKey, voiceId) => {
    try {
        const response = await axios.get(`https://api.elevenlabs.io/v1/voices/${voiceId}`, {
            headers: {
                'xi-api-key': apiKey,
                'Accept': 'application/json'
            },
            timeout: 5000
        });
        return response.data;
    } catch (error) {
        console.error(`❌ فشل التحقق من توفر الصوت: ${error.message} - الصوت: ${voiceId}`);
        return null;
    }
};

function checkUsageLimit(chatId) {
    const today = new Date().toISOString().split('T')[0];
    let userUsage = ttsRequestCounts.get(chatId);

    if (!userUsage || userUsage.date !== today) {
        userUsage = { date: today, count: 0 };
        ttsRequestCounts.set(chatId, userUsage);
    }

    return {
        isLimited: userUsage.count >= DAILY_REQUEST_LIMIT,
        remaining: Math.max(0, DAILY_REQUEST_LIMIT - userUsage.count),
        total: DAILY_REQUEST_LIMIT
    };
}

function incrementUsage(chatId) {
    const today = new Date().toISOString().split('T')[0];
    let userUsage = ttsRequestCounts.get(chatId) || { date: today, count: 0 };

    if (userUsage.date !== today) {
        userUsage = { date: today, count: 0 };
    }

    userUsage.count += 1;
    ttsRequestCounts.set(chatId, userUsage);
    saveUsageData();
}

const ttsArabicCommand = async (sock, chatId, message, text) => {
    console.log(`🎙️ بدء تحويل النص إلى كلام للمستخدم: ${chatId}`);

    let finalText = text;
    if (!finalText && message.quoted && message.quoted.text) {
        finalText = message.quoted.text;
        console.log("📝 استخدام نص من رسالة مقتبسة");
    }
    let voiceIndex = -1; // قيمة افتراضية معناها إن المستخدم مختارش صوت معين

    // نشوف المستخدم كاتب رقم ولا لأ
    if (finalText) {
        const parts = finalText.split(" ");
        if (parts.length > 1 && parts[parts.length - 1].startsWith("-")) {
          const voiceNumber = parseInt(parts[parts.length - 1].substring(1));
          // نتأكد إن الرقم صالح
          if (!isNaN(voiceNumber) && voiceNumber > 0 && voiceNumber <= VOICE_IDS.length) {
            voiceIndex = voiceNumber - 1; // اطرح 1 عشان المصفوفات بتبدأ من الصفر
            finalText = parts.slice(0, -1).join(" "); // شيل رقم الصوت من النص
            console.log(`🗣️ المستخدم اختار الصوت رقم: ${voiceIndex + 1}`);
          }
        }
    }

    if (!finalText || finalText.trim() === "") {
        const helpMessage = "*ازاي تستخدم الأمر ده؟ 🤔*\n\n" +
        "• اكتب `.tts` وجنبه النص اللي عايز تحوله لكلام 🎤\n" +
        "• أو رد على رسالة نصية واكتب `.tts` 📩\n" +
        "• لاختيار صوت معين، ضيف رقم الصوت بعد شرطة في آخر الأمر، زي `.tts hello -2` 🌟\n\n" +
        "*مثال:* `.tts السلام عليكم يا جماعة، إزيكم؟` 🌟";
        await sendErrorMessage(sock, chatId, helpMessage);
        return;
    }

    const usageStatus = checkUsageLimit(chatId);
    if (usageStatus.isLimited) {
        await sendErrorMessage(sock, chatId, `*عديت الحد اليومي! 🚫*\n\nاستخدمت كل المحاولات (${DAILY_REQUEST_LIMIT} مرة) لتحويل النص لصوت النهاردة 📊\n\nجرب تاني بكرة أو كلم الدعم لو عايز زيادة! 📞`);
        return;
    }

    const statusMsg = await sock.sendMessage(chatId, {
        text: "*جاري تحويل النص لكلام... ⏳*"
    });

    try {
        console.log("🔊 استخدام النص الأصلي كما هو.");

        await sock.sendMessage(chatId, {
            text: "*جاري إنشاء الملف الصوتي... 🔊*",
            edit: statusMsg.key
        });

        let succeeded = false;
        for (let i = 0; i < ELEVENLABS_API_KEYS.length && !succeeded; i++) {
            const apiKey = ELEVENLABS_API_KEYS[i];

            // لو المستخدم مختار صوت، هنستخدمه. لو مش مختار، هنلف عليهم كلهم
            const voicesToTry = voiceIndex >= 0 ? [VOICE_IDS[voiceIndex]] : VOICE_IDS;

            for (let j = 0; j < voicesToTry.length && !succeeded; j++) {
                const voiceId = voicesToTry[j];

                const voiceDetails = await checkVoiceAvailability(apiKey, voiceId);
                if (!voiceDetails) {
                    console.log(`⚠️ الصوت ${voiceId} غير متاح باستخدام المفتاح رقم ${i+1}`);
                    continue;
                }

                const fileName = `tts-${Date.now()}-${Math.floor(Math.random() * 10000)}.mp3`;
                const filePath = path.join(ASSETS_DIR, fileName);

                try {
                    const requestData = {
                        text: finalText,
                        model_id: "eleven_multilingual_v2",
                        voice_settings: {
                            stability: 0.6,
                            similarity_boost: 0.75,
                            style: 0.15
                        }
                    };

                    console.log(`🔑 استخدام مفتاح API رقم ${i+1} والصوت ${voiceId}`);
                    const elevenlabsResponse = await axios({
                        method: 'POST',
                        url: `https://api.elevenlabs.io/v1/text-to-speech/${voiceId}`,
                        headers: {
                            'xi-api-key': apiKey,
                            'Content-Type': 'application/json',
                            'Accept': 'audio/mpeg'
                        },
                        data: requestData,
                        responseType: 'stream',
                        timeout: 30000
                    });

                    const writeStream = fs.createWriteStream(filePath);
                    elevenlabsResponse.data.pipe(writeStream);

                    await new Promise((resolve, reject) => {
                        writeStream.on("finish", resolve);
                        writeStream.on("error", reject);
                    });

                    console.log("✅ تم إنشاء الملف الصوتي بنجاح");
                    const audioBuffer = fs.readFileSync(filePath);

                    await sock.sendMessage(chatId, {
                        text: "*جاري إرسال الصوت... 🚀*",
                        edit: statusMsg.key
                    });

                    await sock.sendMessage(chatId, {
                        audio: audioBuffer,
                        mimetype: 'audio/mpeg',
                        ptt: true
                    }, { quoted: message });

                    fs.unlinkSync(filePath);
                    console.log("🗑️ تم حذف الملف المؤقت");

                    await sock.sendMessage(chatId, {
                        text: `*تم تحويل النص لصوت بنجاح 🎉*\n\n*محاولاتك النهاردة:* ${usageStatus.remaining - 1} من ${usageStatus.total} متبقية 📉`,
                        edit: statusMsg.key
                    });

                    incrementUsage(chatId);
                    succeeded = true;

                } catch (error) {
                    console.error(`❌ فشل استخدام المفتاح رقم ${i+1} والصوت ${voiceId}: ${error.message}`);
                    if (fs.existsSync(filePath)) {
                        fs.unlinkSync(filePath);
                    }
                }
            }
        }

        if (!succeeded) {
            await sock.sendMessage(chatId, {
                text: "*معلش، كل المحاولات فشلت في إنشاء الصوت 😔*\n\nجرب تاني بعد شوية أو استخدم نص أقصر 📝",
                edit: statusMsg.key
            });
        }

    } catch (error) {
        console.error(`❌ خطأ غير متوقع: ${error.message}`);
        await sock.sendMessage(chatId, {
            text: "*حصل مشكلة غريبة 😵*\n\nجرب تاني بعد شوية 🙏",
            edit: statusMsg.key
        });
    }
};

module.exports = { ttsArabicCommand };
