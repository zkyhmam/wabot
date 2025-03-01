const { sendFormattedMessage } = require("./messageUtils");
require('dotenv').config();

console.log("[HELP] Initializing help module...");

const helpCommand = async (sock, chatId, message) => {
    console.log(`[HELP] Executing helpCommand for chat: ${chatId}`);

    const helpMessage = "*~📜 قائمة الأوامر المتاحة 📜~*\n\n" +
        "• `.tts <نص>` - حول النص لكلام 🎤\n" +
        "  *مثال:* `.tts السلام عليكم يا جماعة، إزيكم؟`\n\n" +
        "• `.movie <اسم الفيلم>` - جيب معلومات عن فيلم أو مسلسل 🎥\n" +
        "  *مثال:* `.movie Inception`\n\n" +
        "• `.img <كلمة البحث>` - ابحث عن صور 🖼️\n" +
        "  *مثال:* `.img قطط كيوت`\n" +
        "  *خيارات إضافية:* `--gif` لصور متحركة، `--count 5` لعدد الصور\n\n" +
        "• `.song <اسم الأغنية>` - نزل أغنية من YouTube 🎵\n" +
        "  *مثال:* `.song أغنية حسن شاكوش`\n\n" +
        "• `.sticker` - حول صورة أو فيديو لملصق 🌟\n" +
        "  *مثال:* ابعت صورة واكتب `.sticker`\n\n" +
        "• `.take <اسم مخصص>` - حول صورة لملصق باسمك أو اسم مخصص 📌\n" +
        "  *مثال:* `.take محمد`\n\n" +
        "• `.secret <رقم> <رسالة>` - ابعت رسالة سرية 📩\n" +
        "  *مثال:* `.secret 20123456789 مرحبًا`\n\n" +
        "• `.help` أو `.menu` - اعرض القائمة دي 📜\n\n" +
        "*ملاحظة:* كل الأوامر لازم تبدأ بـ `.` وتكون واضحة علشان أقدر أساعدك! 😊";

    try {
        console.log(`[HELP] Attempting to send help message to ${chatId}`);
        await sendFormattedMessage(sock, chatId, helpMessage, '🚀', message);
        console.log("[HELP] Help message sent successfully");
    } catch (error) {
        console.error("[HELP] Error sending help message:", error);
        await sendErrorMessage(sock, chatId, "❌ حصل مشكلة وأنا ببعت قائمة الأوامر 😕 جرب تاني بعد شوية 🔄");
    }
};

const handler = async (sock, noWa, message) => {
    console.log(`[HELP] Handler triggered for chat: ${noWa}`);
    await helpCommand(sock, noWa, message);
};

console.log("[HELP] Setting handler metadata...");
handler.help = ['help', 'menu'];
handler.tags = ['general'];
handler.command = /^(help|menu)$/i;

console.log("[HELP] Module initialization complete");
module.exports = { handler };
