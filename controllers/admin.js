require('dotenv').config();
const fs = require('fs');
const path = require('path');
const { writeFile, readFile, mkdir } = require('fs/promises');

const SETTINGS_DIR = path.join(__dirname, 'config');
const SETTINGS_FILE = path.join(SETTINGS_DIR, 'autoReplySettings.json');
const LOGS_DIR = path.join(__dirname, 'logs');
const LOG_FILE = path.join(LOGS_DIR, `whatsapp-bot-${new Date().toISOString().split('T')[0]}.log`);

let autoReplySettings = {
    autoType: false,
    autoRecord: false,
    autoSeen: process.env.AUTO_SEEN === 'on',
    online24h: process.env.ONLINE_24H === 'on',
    autoTypeAlways: false,
    autoRecordAlways: false,
    autoReply: false,
    typingDelay: 2000,
    lastActive: new Date().toISOString()
};

let statistics = {
    messagesReceived: 0,
    messagesSent: 0,
    commandsExecuted: 0,
    lastRestart: new Date().toISOString(),
    activeChats: {}
};

async function ensureDirectoriesExist() {
    try {
        await mkdir(SETTINGS_DIR, { recursive: true });
        await mkdir(LOGS_DIR, { recursive: true });
        logToFile('تم إنشاء المجلدات الضرورية أو التأكد من وجودها');
    } catch (error) {
        console.error('فشل في إنشاء المجلدات:', error);
    }
}

async function saveSettings() {
    try {
        await writeFile(SETTINGS_FILE, JSON.stringify(autoReplySettings, null, 2), 'utf8');
        logToFile('تم حفظ الإعدادات بنجاح');
    } catch (error) {
        console.error('فشل في حفظ الإعدادات:', error);
        logToFile(`فشل في حفظ الإعدادات: ${error.message}`, 'error');
    }
}

async function loadSettings() {
    try {
        const fileExists = fs.existsSync(SETTINGS_FILE);
        if (fileExists) {
            const data = await readFile(SETTINGS_FILE, 'utf8');
            const savedSettings = JSON.parse(data);
            autoReplySettings = { ...autoReplySettings, ...savedSettings };
            logToFile('تم تحميل الإعدادات بنجاح');
        } else {
            logToFile('لم يتم العثور على ملف الإعدادات. سيتم استخدام الإعدادات الافتراضية');
            await saveSettings();
        }
    } catch (error) {
        console.error('فشل في تحميل الإعدادات:', error);
        logToFile(`فشل في تحميل الإعدادات: ${error.message}`, 'error');
    }
}

function logToFile(message, level = 'info') {
    const timestamp = new Date().toISOString();
    const logEntry = `[${timestamp}] [${level.toUpperCase()}] ${message}\n`;

    fs.appendFile(LOG_FILE, logEntry, (err) => {
        if (err) console.error('فشل في كتابة السجل:', err);
    });

    if (level === 'error') {
        console.error(`[${timestamp}] ${message}`);
    } else {
        console.log(`[${timestamp}] ${message}`);
    }
}

function updateChatStats(jid, incoming = true) {
    if (!statistics.activeChats[jid]) {
        statistics.activeChats[jid] = {
            incoming: 0,
            outgoing: 0,
            lastActive: new Date().toISOString()
        };
    }

    if (incoming) {
        statistics.activeChats[jid].incoming += 1;
        statistics.messagesReceived += 1;
    } else {
        statistics.activeChats[jid].outgoing += 1;
        statistics.messagesSent += 1;
    }

    statistics.activeChats[jid].lastActive = new Date().toISOString();
}

let botNumber; // متغير عالمي لتخزين رقم البوت (سيتم تعيينه من whatsappController.js)

// التحقق من أن المرسل هو البوت نفسه
const isAdminCommand = (sock, message) => {
    const sender = message.key.remoteJid;
    if (!botNumber) {
        console.log("🚫 رقم البوت لم يتم تعيينه بعد!");
        return false;
    }
    if (sender !== botNumber) {
        console.log(`🚫 رفض تنفيذ أمر الأدمن! المرسل (${sender}) ليس البوت (${botNumber}).`);
        return false;
    }
    console.log("✅ أمر أدمن مصرح به من البوت نفسه!");
    return true;
};

const adminCommands = {
    'at on': async (sock, noWa, message) => {
        if (!isAdminCommand(sock, message)) {
            await sock.sendMessage(noWa, { text: "🚫 الأمر ده للبوت نفسه بس!" });
            return;
        }
        autoReplySettings.autoType = true;
        await sock.sendMessage(noWa, { text: '✅ الكتابة التلقائية شغالة دلوقتي 📝' });
        await saveSettings();
        logToFile(`تم تفعيل الكتابة التلقائية بواسطة ${noWa}`);
    },
    'at off': async (sock, noWa, message) => {
        if (!isAdminCommand(sock, message)) {
            await sock.sendMessage(noWa, { text: "🚫 الأمر ده للبوت نفسه بس!" });
            return;
        }
        autoReplySettings.autoType = false;
        await sock.sendMessage(noWa, { text: '❌ الكتابة التلقائية اتعطلت 📝' });
        await saveSettings();
        logToFile(`تم تعطيل الكتابة التلقائية بواسطة ${noWa}`);
    },
    'ar on': async (sock, noWa, message) => {
        if (!isAdminCommand(sock, message)) {
            await sock.sendMessage(noWa, { text: "🚫 الأمر ده للبوت نفسه بس!" });
            return;
        }
        autoReplySettings.autoRecord = true;
        await sock.sendMessage(noWa, { text: '✅ التسجيل الصوتي شغال دلوقتي 🎙️' });
        await saveSettings();
        logToFile(`تم تفعيل التسجيل التلقائي بواسطة ${noWa}`);
    },
    'ar off': async (sock, noWa, message) => {
        if (!isAdminCommand(sock, message)) {
            await sock.sendMessage(noWa, { text: "🚫 الأمر ده للبوت نفسه بس!" });
            return;
        }
        autoReplySettings.autoRecord = false;
        await sock.sendMessage(noWa, { text: '❌ التسجيل الصوتي اتعطل 🎙️' });
        await saveSettings();
        logToFile(`تم تعطيل التسجيل التلقائي بواسطة ${noWa}`);
    },
    'as on': async (sock, noWa, message) => {
        if (!isAdminCommand(sock, message)) {
            await sock.sendMessage(noWa, { text: "🚫 الأمر ده للبوت نفسه بس!" });
            return;
        }
        autoReplySettings.autoSeen = true;
        await sock.sendMessage(noWa, { text: '✅ القراءة التلقائية شغالة دلوقتي 👀' });
        await saveSettings();
        logToFile(`تم تفعيل القراءة التلقائية بواسطة ${noWa}`);
    },
    'as off': async (sock, noWa, message) => {
        if (!isAdminCommand(sock, message)) {
            await sock.sendMessage(noWa, { text: "🚫 الأمر ده للبوت نفسه بس!" });
            return;
        }
        autoReplySettings.autoSeen = false;
        await sock.sendMessage(noWa, { text: '❌ القراءة التلقائية اتعطلت 👀' });
        await saveSettings();
        logToFile(`تم تعطيل القراءة التلقائية بواسطة ${noWa}`);
    },
    'online on': async (sock, noWa, message) => {
        if (!isAdminCommand(sock, message)) {
            await sock.sendMessage(noWa, { text: "🚫 الأمر ده للبوت نفسه بس!" });
            return;
        }
        autoReplySettings.online24h = true;
        await sock.sendMessage(noWa, { text: '✅ الظهور متصل 24 ساعة شغال دلوقتي 🌐' });
        await saveSettings();
        logToFile(`تم تفعيل الاتصال الدائم بواسطة ${noWa}`);
    },
    'online off': async (sock, noWa, message) => {
        if (!isAdminCommand(sock, message)) {
            await sock.sendMessage(noWa, { text: "🚫 الأمر ده للبوت نفسه بس!" });
            return;
        }
        autoReplySettings.online24h = false;
        await sock.sendMessage(noWa, { text: '❌ الظهور متصل 24 ساعة اتعطل 🌐' });
        await saveSettings();
        logToFile(`تم تعطيل الاتصال الدائم بواسطة ${noWa}`);
    },
    'ata on': async (sock, noWa, message) => {
        if (!isAdminCommand(sock, message)) {
            await sock.sendMessage(noWa, { text: "🚫 الأمر ده للبوت نفسه بس!" });
            return;
        }
        autoReplySettings.autoTypeAlways = true;
        await sock.sendMessage(noWa, { text: '✅ الكتابة التلقائية الدائمة شغالة دلوقتي 📝🕒' });
        await saveSettings();
        logToFile(`تم تفعيل الكتابة التلقائية الدائمة بواسطة ${noWa}`);
    },
    'ata off': async (sock, noWa, message) => {
        if (!isAdminCommand(sock, message)) {
            await sock.sendMessage(noWa, { text: "🚫 الأمر ده للبوت نفسه بس!" });
            return;
        }
        autoReplySettings.autoTypeAlways = false;
        await sock.sendMessage(noWa, { text: '❌ الكتابة التلقائية الدائمة اتعطلت 📝🕒' });
        await saveSettings();
        logToFile(`تم تعطيل الكتابة التلقائية الدائمة بواسطة ${noWa}`);
    },
    'ara on': async (sock, noWa, message) => {
        if (!isAdminCommand(sock, message)) {
            await sock.sendMessage(noWa, { text: "🚫 الأمر ده للبوت نفسه بس!" });
            return;
        }
        autoReplySettings.autoRecordAlways = true;
        await sock.sendMessage(noWa, { text: '✅ التسجيل الصوتي الدائم شغال دلوقتي 🎙️🕒' });
        await saveSettings();
        logToFile(`تم تفعيل التسجيل التلقائي الدائم بواسطة ${noWa}`);
    },
    'ara off': async (sock, noWa, message) => {
        if (!isAdminCommand(sock, message)) {
            await sock.sendMessage(noWa, { text: "🚫 الأمر ده للبوت نفسه بس!" });
            return;
        }
        autoReplySettings.autoRecordAlways = false;
        await sock.sendMessage(noWa, { text: '❌ التسجيل الصوتي الدائم اتعطل 🎙️🕒' });
        await saveSettings();
        logToFile(`تم تعطيل التسجيل التلقائي الدائم بواسطة ${noWa}`);
    },
    'autoreply on': async (sock, noWa, message) => {
        if (!isAdminCommand(sock, message)) {
            await sock.sendMessage(noWa, { text: "🚫 الأمر ده للبوت نفسه بس!" });
            return;
        }
        autoReplySettings.autoReply = true;
        await sock.sendMessage(noWa, { text: '✅ الرد التلقائي شغال دلوقتي 🤖' });
        await saveSettings();
        logToFile(`تم تفعيل الرد التلقائي بواسطة ${noWa}`);
    },
    'autoreply off': async (sock, noWa, message) => {
        if (!isAdminCommand(sock, message)) {
            await sock.sendMessage(noWa, { text: "🚫 الأمر ده للبوت نفسه بس!" });
            return;
        }
        autoReplySettings.autoReply = false;
        await sock.sendMessage(noWa, { text: '❌ الرد التلقائي اتعطل 🤖' });
        await saveSettings();
        logToFile(`تم تعطيل الرد التلقائي بواسطة ${noWa}`);
    },
    'delay': async (sock, noWa, args, message) => {
        if (!isAdminCommand(sock, message)) {
            await sock.sendMessage(noWa, { text: "🚫 الأمر ده للبوت نفسه بس!" });
            return;
        }
        const delay = parseInt(args[0]);
        if (!isNaN(delay) && delay > 0) {
            autoReplySettings.typingDelay = delay;
            await sock.sendMessage(noWa, { text: `✅ تم ضبط تأخير الكتابة على ${delay} مللي ثانية ⏱️` });
            await saveSettings();
            logToFile(`تم تغيير تأخير الكتابة إلى ${delay}ms بواسطة ${noWa}`);
        } else {
            await sock.sendMessage(noWa, { text: '❌ اكتب قيمة صحيحة للتأخير (مثال: .delay 3000) 📝' });
        }
    },
    'admin': async (sock, noWa, message) => {
        if (!isAdminCommand(sock, message)) {
            await sock.sendMessage(noWa, { text: "🚫 الأمر ده للبوت نفسه بس!" });
            return;
        }
        let adminHelpMessage = "*~🛠️ أوامر الأدمن 🛠️~*\n\n";
        adminHelpMessage += "`.at on/off` - تشغيل/تعطيل الكتابة التلقائية 📝\n";
        adminHelpMessage += "`.ar on/off` - تشغيل/تعطيل التسجيل الصوتي 🎙️\n";
        adminHelpMessage += "`.as on/off` - تشغيل/تعطيل رؤية الرسائل 👀\n";
        adminHelpMessage += "`.online on/off` - تشغيل/تعطيل الظهور متصل 24 ساعة 🌐\n";
        adminHelpMessage += "`.ata on/off` - تشغيل/تعطيل الكتابة التلقائية دائمًا 📝🕒\n";
        adminHelpMessage += "`.ara on/off` - تشغيل/تعطيل التسجيل الصوتي دائمًا 🎙️🕒\n";
        adminHelpMessage += "`.autoreply on/off` - تشغيل/تعطيل الرد التلقائي 🤖\n";
        adminHelpMessage += "`.delay [مللي ثانية]` - ضبط تأخير الكتابة ⏱️\n";
        adminHelpMessage += "`.stats` - إظهار إحصائيات البوت 📊\n";
        adminHelpMessage += "`.logs` - إظهار آخر 10 سجلات 📜\n";
        adminHelpMessage += "`.restart` - إعادة تشغيل البوت 🔄\n";
        adminHelpMessage += "`.admin` - إظهار قائمة الأوامر دي 📜\n";
        await sock.sendMessage(noWa, { text: adminHelpMessage });
        statistics.commandsExecuted++;
    },
    'stats': async (sock, noWa, message) => {
        if (!isAdminCommand(sock, message)) {
            await sock.sendMessage(noWa, { text: "🚫 الأمر ده للبوت نفسه بس!" });
            return;
        }
        const uptime = new Date() - new Date(statistics.lastRestart);
        const days = Math.floor(uptime / (1000 * 60 * 60 * 24));
        const hours = Math.floor((uptime % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        const minutes = Math.floor((uptime % (1000 * 60 * 60)) / (1000 * 60));

        let statsMessage = "📊 *إحصائيات البوت* 📊\n\n";
        statsMessage += "🚀 *حالة الأوامر دلوقتي:*\n";
        statsMessage += `  ✍️ الكتابة التلقائية: ${autoReplySettings.autoType ? '✅ شغالة' : '❌ متعطلة'}\n`;
        statsMessage += `  🎙️ التسجيل الصوتي: ${autoReplySettings.autoRecord ? '✅ شغال' : '❌ متعطل'}\n`;
        statsMessage += `  👀 القراءة التلقائية: ${autoReplySettings.autoSeen ? '✅ شغالة' : '❌ متعطلة'}\n`;
        statsMessage += `  🟢 الظهور متصل 24 ساعة: ${autoReplySettings.online24h ? '✅ شغال' : '❌ متعطل'}\n`;
        statsMessage += `  ✍️ الكتابة التلقائية (دائمًا): ${autoReplySettings.autoTypeAlways ? '✅ شغالة' : '❌ متعطلة'}\n`;
        statsMessage += `  🎙️ التسجيل الصوتي (دائمًا): ${autoReplySettings.autoRecordAlways ? '✅ شغال' : '❌ متعطل'}\n`;
        statsMessage += `  🤖 الرد التلقائي: ${autoReplySettings.autoReply ? '✅ شغال' : '❌ متعطل'}\n\n`;

        statsMessage += "📈 *إحصائيات النشاط:*\n";
        statsMessage += `  📥 الرسايل اللي جت: ${statistics.messagesReceived}\n`;
        statsMessage += `  📤 الرسايل اللي اتبعتت: ${statistics.messagesSent}\n`;
        statsMessage += `  🔄 الأوامر اللي اتعملت: ${statistics.commandsExecuted}\n`;
        statsMessage += `  ⏱️ مدة التشغيل: ${days} يوم ${hours} ساعة ${minutes} دقيقة\n`;
        statsMessage += `  👥 المحادثات النشطة: ${Object.keys(statistics.activeChats).length}\n\n`;

        statsMessage += "💡 *آخر تحديث:* " + new Date().toLocaleString('ar-SA');

        await sock.sendMessage(noWa, { text: statsMessage });
        statistics.commandsExecuted++;
        logToFile(`تم عرض الإحصائيات بواسطة ${noWa}`);
    },
    'logs': async (sock, noWa, message) => {
        if (!isAdminCommand(sock, message)) {
            await sock.sendMessage(noWa, { text: "🚫 الأمر ده للبوت نفسه بس!" });
            return;
        }
        try {
            const fileExists = fs.existsSync(LOG_FILE);
            if (fileExists) {
                const data = await readFile(LOG_FILE, 'utf8');
                const logs = data.split('\n').filter(line => line.trim() !== '');
                const recentLogs = logs.slice(-10).join('\n');
                await sock.sendMessage(noWa, { text: `📜 *آخر 10 سجلات:*\n\n${recentLogs}` });
            } else {
                await sock.sendMessage(noWa, { text: '❌ مفيش سجلات متاحة لسة 😕' });
            }
        } catch (error) {
            console.error('فشل في قراءة ملف السجلات:', error);
            await sock.sendMessage(noWa, { text: '❌ حصل مشكلة وأنا بقرأ السجلات 😔' });
        }
        statistics.commandsExecuted++;
    },
    'restart': async (sock, noWa, message) => {
        if (!isAdminCommand(sock, message)) {
            await sock.sendMessage(noWa, { text: "🚫 الأمر ده للبوت نفسه بس!" });
            return;
        }
        await sock.sendMessage(noWa, { text: '🔄 جاري إعادة تشغيل البوت... ⏳' });
        statistics.lastRestart = new Date().toISOString();
        logToFile(`تم طلب إعادة تشغيل البوت بواسطة ${noWa}`);
        statistics.commandsExecuted++;
    }
};

// تعيين رقم البوت من whatsappController.js
const setBotNumber = (number) => {
    botNumber = number;
};

module.exports = { adminCommands, ensureDirectoriesExist, loadSettings, setBotNumber };
