/**
 * Improved WhatsApp Bot Implementation
 * ===================================
 * Advanced NodeJS WhatsApp Bot with enhanced architecture and features
 * Implements modular design, error handling, logging, and performance optimization
 */

const {
    default: makeWASocket,
    DisconnectReason,
    fetchLatestBaileysVersion,
    isJidBroadcast,
    makeInMemoryStore,
    useMultiFileAuthState,
    isJidGroup,
    generateWAMessageFromContent,
    prepareWAMessageMedia
} = require("@whiskeysockets/baileys");
const { Boom } = require("@hapi/boom");
const qrcode = require("qrcode");
const fs = require("fs");
const path = require('path');
const pino = require("pino");
const eventEmitter = require('events');
const axios = require('axios');
const os = require('os');
const moment = require('moment');
const crypto = require('crypto');
const dotenv = require('dotenv');

dotenv.config();

const { stickerArabicCommand, takeCommand } = require('./sticker.js');
const { ttsArabicCommand } = require('./tts.js');
const { downloadSong } = require('./yt.js');
const { imageSearch, gifSearch } = require("./img.js");
const { movieCommand } = require("./movie.js");
const helpController = require("./help.js");
const { sendErrorMessage, sendFormattedMessage, formatDuration } = require("./messageUtils");
const { sendSecretMessage, handleReply } = require('./secretMessages.js');
const { adminCommands, ensureDirectoriesExist, loadSettings, setBotNumber } = require('./admin.js');

const botEvents = new eventEmitter();

const CONFIG = {
    AUTH_FOLDER: "baileys_auth_info",
    LOG_FOLDER: path.join(__dirname, '..', 'logs'),
    QR_PNG_PATH: path.join(__dirname, 'qr.png'),
    QR_HTML_PATH: path.join(__dirname, 'qr.html'),
    RECONNECT_INTERVAL: 3000,
    MAX_RETRIES: 5,
    COMMAND_PREFIX_REGEX: /^[\/.]|#/,
    ADMIN_NUMBERS: (process.env.ADMIN_NUMBERS || '').split(',').map(num => num.trim())
};

let autoReply = {};
const store = makeInMemoryStore({ logger: pino().child({ level: "silent" }) });
let sock;
let qr;
let botNumber;
let connectionRetries = 0;
let startTime = Date.now();
let messageStats = {
    received: 0,
    sent: 0,
    commands: 0,
    errors: 0
};
let qrCodeLinkToSend = null;

class Logger {
    constructor() {
        this.ensureLogDirectory();
    }

    ensureLogDirectory() {
        if (!fs.existsSync(CONFIG.LOG_FOLDER)) {
            fs.mkdirSync(CONFIG.LOG_FOLDER, { recursive: true });
        }
    }

    log(level, message, data = null) {
        const timestamp = new Date().toISOString();
        const logEntry = {
            timestamp,
            level,
            message,
            ...(data && { data }),
        };

        console.log(`[${timestamp}] [${level}] ${message}`);

        const logFile = path.join(CONFIG.LOG_FOLDER, `${level}.log`);
        fs.appendFileSync(logFile, JSON.stringify(logEntry) + '\n');
    }

    info(message, data) {
        this.log('info', message, data);
    }

    error(message, error, command = null, messageData = null) {
        const errorData = {
            message: error.message,
            stack: error.stack,
            command,
            messageData: messageData ? JSON.stringify(messageData) : null
        };

        this.log('error', message, errorData);
        messageStats.errors++;
    }

    command(command, sender, query) {
        this.log('command', `Command executed: ${command}`, { sender, query });
        messageStats.commands++;
    }

    generateStats() {
        const uptime = formatDuration(Date.now() - startTime);
        const memoryUsage = process.memoryUsage();
        const stats = {
            uptime,
            messages: {
                received: messageStats.received,
                sent: messageStats.sent,
                commands: messageStats.commands,
                errors: messageStats.errors
            },
            system: {
                memory: {
                    rss: `${Math.round(memoryUsage.rss / 1024 / 1024)} MB`,
                    heapTotal: `${Math.round(memoryUsage.heapTotal / 1024 / 1024)} MB`,
                    heapUsed: `${Math.round(memoryUsage.heapUsed / 1024 / 1024)} MB`
                },
                platform: os.platform(),
                cpus: os.cpus().length,
                loadAvg: os.loadavg(),
                freeMemory: `${Math.round(os.freemem() / 1024 / 1024)} MB`,
                totalMemory: `${Math.round(os.totalmem() / 1024 / 1024)} MB`
            }
        };
        return stats;
    }
}

const logger = new Logger();

class SecurityManager {
    constructor(adminNumbers) {
        this.adminNumbers = adminNumbers;
    }

    isAdmin(jid) {
        if (!jid) return false;
        const cleanJid = jid.split('@')[0];
        return this.adminNumbers.some(admin => admin === cleanJid);
    }

    validateCommand(commandName, jid) {
        const isAdminCommand = ['at', 'ar', 'as', 'online', 'ata', 'ara', 'autoreply',
                              'delay', 'admin', 'stats', 'logs', 'restart'].includes(commandName);

        if (isAdminCommand && !this.isAdmin(jid)) {
            return false;
        }
        return true;
    }

    generateSessionToken() {
        return crypto.randomBytes(32).toString('hex');
    }
}

const securityManager = new SecurityManager(CONFIG.ADMIN_NUMBERS);

const commandRoutes = {
    'sticker': stickerArabicCommand,
    'ملصق': stickerArabicCommand,
    'take': takeCommand,
    'تسمية': takeCommand,
    'tts': ttsArabicCommand,
    'انطق': ttsArabicCommand,
    'song': downloadSong,
    'اغنية': downloadSong,
    'img': imageSearch,
    'صورة': imageSearch,
    'gif': gifSearch,
    'متحركة': gifSearch,
    'movie': movieCommand,
    'فيلم': movieCommand,
    'help': helpController.handler,
    'مساعدة': helpController.handler,
    'menu': helpController.handler,
    'قائمة': helpController.handler,
    'secret': async (sock, noWa, message, query) => {
        if (!query) return await sock.sendMessage(noWa, { text: "اكتب رسالتك السرية بعد `.secret` 📩" });
        const [recipientJid, ...messageParts] = query.split(' ');
        const messageText = messageParts.join(' ').trim();
        if (!recipientJid || !messageText) return await sock.sendMessage(noWa, { text: "حدد رقم المستلم والرسالة السرية صح 📞" });
        await sendSecretMessage(sock, noWa, recipientJid, messageText, false);
    },
    'سري': async (sock, noWa, message, query) => {
        if (!query) return await sock.sendMessage(noWa, { text: "اكتب رسالتك السرية بعد `.سري` 📩" });
        const [recipientJid, ...messageParts] = query.split(' ');
        const messageText = messageParts.join(' ').trim();
        if (!recipientJid || !messageText) return await sock.sendMessage(noWa, { text: "حدد رقم المستلم والرسالة السرية صح 📞" });
        await sendSecretMessage(sock, noWa, recipientJid, messageText, false);
    },
    'smes': async (sock, noWa, message, query) => {
        if (!query) return await sock.sendMessage(noWa, { text: "اكتب رسالتك السرية بعد `.smes` 📩" });
        const [recipientJid, ...messageParts] = query.split(' ');
        const messageText = messageParts.join(' ').trim();
        if (!recipientJid || !messageText) return await sock.sendMessage(noWa, { text: "حدد رقم المستلم والرسالة السرية صح 📞" });
        await sendSecretMessage(sock, noWa, recipientJid, messageText, false);
    },
    'صارحني': async (sock, noWa, message, query) => {
        if (!query) return await sock.sendMessage(noWa, { text: "اكتب رسالتك السرية بعد `.صارحني` 📩" });
        const [recipientJid, ...messageParts] = query.split(' ');
        const messageText = messageParts.join(' ').trim();
        if (!recipientJid || !messageText) return await sock.sendMessage(noWa, { text: "حدد رقم المستلم والرسالة السرية صح 📞" });
        await sendSecretMessage(sock, noWa, recipientJid, messageText, false);
    },
    'about': async (sock, noWa, message) => {
        const stats = logger.generateStats();
        const aboutMsg = `*📊 معلومات البوت*\n\n` +
                         `🕒 *وقت التشغيل:* ${stats.uptime}\n` +
                         `📨 *الرسائل المستلمة:* ${stats.messages.received}\n` +
                         `📤 *الرسائل المرسلة:* ${stats.messages.sent}\n` +
                         `📟 *الأوامر المنفذة:* ${stats.messages.commands}\n` +
                         `❌ *الأخطاء:* ${stats.messages.errors}\n\n` +
                         `*💻 معلومات النظام*\n` +
                         `🧠 *الذاكرة المستخدمة:* ${stats.system.memory.heapUsed}\n` +
                         `💾 *المنصة:* ${stats.system.platform}\n` +
                         `⚙️ *عدد المعالجات:* ${stats.system.cpus}\n\n` +
                         `*المطور:* @YourName\n` +
                         `*الإصدار:* 2.0.0`;

        await sock.sendMessage(noWa, { text: aboutMsg });
    },
    'حول': async (sock, noWa, message) => {
        await commandRoutes['about'](sock, noWa, message);
    },
    'at': async (sock, noWa, message, args) => {
        if (!args[0]) return await sock.sendMessage(noWa, { text: "❌ استخدم `.at on` أو `.at off`" });
        const handler = adminCommands['at ' + args[0]];
        if (handler) await handler(sock, noWa, message);
        else await sock.sendMessage(noWa, { text: "❌ اختيار غير صالح، استخدم `on` أو `off`" });
    },
    'ar': async (sock, noWa, message, args) => {
        if (!args[0]) return await sock.sendMessage(noWa, { text: "❌ استخدم `.ar on` أو `.ar off`" });
        const handler = adminCommands['ar ' + args[0]];
        if (handler) await handler(sock, noWa, message);
        else await sock.sendMessage(noWa, { text: "❌ اختيار غير صالح، استخدم `on` أو `off`" });
    },
    'as': async (sock, noWa, message, args) => {
        if (!args[0]) return await sock.sendMessage(noWa, { text: "❌ استخدم `.as on` أو `.as off`" });
        const handler = adminCommands['as ' + args[0]];
        if (handler) await handler(sock, noWa, message);
        else await sock.sendMessage(noWa, { text: "❌ اختيار غير صالح، استخدم `on` أو `off`" });
    },
    'online': async (sock, noWa, message, args) => {
        if (!args[0]) return await sock.sendMessage(noWa, { text: "❌ استخدم `.online on` أو `.online off`" });
        const handler = adminCommands['online ' + args[0]];
        if (handler) await handler(sock, noWa, message);
        else await sock.sendMessage(noWa, { text: "❌ اختيار غير صالح، استخدم `on` أو `off`" });
    },
    'ata': async (sock, noWa, message, args) => {
        if (!args[0]) return await sock.sendMessage(noWa, { text: "❌ استخدم `.ata on` أو `.ata off`" });
        const handler = adminCommands['ata ' + args[0]];
        if (handler) await handler(sock, noWa, message);
        else await sock.sendMessage(noWa, { text: "❌ اختيار غير صالح، استخدم `on` أو `off`" });
    },
    'ara': async (sock, noWa, message, args) => {
        if (!args[0]) return await sock.sendMessage(noWa, { text: "❌ استخدم `.ara on` أو `.ara off`" });
        const handler = adminCommands['ara ' + args[0]];
        if (handler) await handler(sock, noWa, message);
        else await sock.sendMessage(noWa, { text: "❌ اختيار غير صالح، استخدم `on` أو `off`" });
    },
    'autoreply': async (sock, noWa, message, args) => {
        if (!args[0]) return await sock.sendMessage(noWa, { text: "❌ استخدم `.autoreply on` أو `.autoreply off`" });
        const handler = adminCommands['autoreply ' + args[0]];
        if (handler) await handler(sock, noWa, message);
        else await sock.sendMessage(noWa, { text: "❌ اختيار غير صالح، استخدم `on` أو `off`" });
    },
    'delay': async (sock, noWa, message, args) => {
        await adminCommands['delay'](sock, noWa, args, message);
    },
    'admin': async (sock, noWa, message) => {
        await adminCommands['admin'](sock, noWa, message);
    },
    'stats': async (sock, noWa, message) => {
        const stats = logger.generateStats();
        const formattedStats = `*📊 إحصائيات البوت*\n\n` +
                                `🕒 *وقت التشغيل:* ${stats.uptime}\n` +
                                `📨 *الرسائل المستلمة:* ${stats.messages.received}\n` +
                                `📤 *الرسائل المرسلة:* ${stats.messages.sent}\n` +
                                `📟 *الأوامر المنفذة:* ${stats.messages.commands}\n` +
                                `❌ *الأخطاء:* ${stats.messages.errors}\n\n` +
                                `*💻 معلومات النظام*\n` +
                                `🧠 *الذاكرة المستخدمة:* ${stats.system.memory.heapUsed}\n` +
                                `💾 *المنصة:* ${stats.system.platform}\n` +
                                `⚙️ *المعالجات:* ${stats.system.cpus}\n` +
                                `📈 *متوسط الحمل:* ${stats.system.loadAvg[0].toFixed(2)}\n` +
                                `📉 *الذاكرة الحرة:* ${stats.system.freeMemory}`;

        await sock.sendMessage(noWa, { text: formattedStats });
    },
    'logs': async (sock, noWa, message) => {
        try {
            const errorLogPath = path.join(CONFIG.LOG_FOLDER, 'error.log');
            if (!fs.existsSync(errorLogPath)) {
                return await sock.sendMessage(noWa, { text: "✅ لا توجد أخطاء مسجلة" });
            }

            const errorLogs = fs.readFileSync(errorLogPath, 'utf8')
                .split('\n')
                .filter(line => line.trim() !== '')
                .slice(-10);

            let formattedLogs = "*📋 آخر 10 أخطاء:*\n\n";

            errorLogs.forEach((logLine, index) => {
                try {
                    const log = JSON.parse(logLine);
                    formattedLogs += `*${index + 1}.* [${log.timestamp}]\n`;
                    formattedLogs += `*خطأ:* ${log.data.message}\n`;
                    formattedLogs += `*أمر:* ${log.data.command || 'غير معروف'}\n\n`;
                } catch (e) {
                    formattedLogs += `*${index + 1}.* ${logLine}\n\n`;
                }
            });

            await sock.sendMessage(noWa, { text: formattedLogs });
        } catch (error) {
            logger.error("خطأ في استرجاع السجلات", error);
            await sendErrorMessage(sock, noWa, "*حدث خطأ أثناء استرجاع السجلات 📋*");
        }
    },
    'restart': async (sock, noWa, message) => {
        await sock.sendMessage(noWa, { text: "*♻️ جاري إعادة تشغيل البوت...*" });
        logger.info("إعادة تشغيل البوت بواسطة المدير", { admin: noWa });
        deleteAuthData();
        setTimeout(() => connectToWhatsApp(), 1000);
    },
    'ping': async (sock, noWa, message) => {
        const start = Date.now();
        await sock.sendMessage(noWa, { text: "🏓 جاري قياس زمن الاستجابة..." });
        const pingTime = Date.now() - start;
        await sock.sendMessage(noWa, { text: `🏓 *Pong!*\nزمن الاستجابة: *${pingTime}* مللي ثانية` });
    }
};

const commandNames = Object.keys(commandRoutes);

const connectToWhatsApp = async () => {
    logger.info("بدء عملية الاتصال بواتساب");

    try {
        await ensureDirectoriesExist();
        await loadSettings();

        const { state, saveCreds } = await useMultiFileAuthState(CONFIG.AUTH_FOLDER);
        logger.info("تم تحميل/إنشاء بيانات المصادقة");

        const { version } = await fetchLatestBaileysVersion();
        logger.info(`تم الحصول على أحدث إصدار من Baileys: ${version}`);

        sock = makeWASocket({
            printQRInTerminal: false,
            auth: state,
            logger: pino({ level: "silent" }),
            version,
            shouldIgnoreJid: (jid) => isJidBroadcast(jid),
            getMessage: async (key) => {
                return {
                    conversation: 'بوت واتساب متقدم'
                };
            }
        });

        store.bind(sock.ev);

        sock.ev.on("connection.update", async (update) => {
            logger.info("تحديث الاتصال", update);
            const { connection, lastDisconnect } = update;

            if (connection === "open") {
                botNumber = sock.user.id.split(":")[0] + "@s.whatsapp.net";
                setBotNumber(botNumber);
                logger.info(`تم الاتصال بنجاح.  رقم البوت: ${botNumber}`);
                connectionRetries = 0;

                for (const admin of CONFIG.ADMIN_NUMBERS) {
                    try {
                        await sock.sendMessage(`${admin}@s.whatsapp.net`, {
                            text: `*🤖 تم تشغيل البوت بنجاح*\n\n` +
                                 `🕒 *الوقت:* ${new Date().toLocaleString('ar-SA')}\n` +
                                 `💻 *النظام:* ${os.platform()} ${os.release()}\n` +
                                 `🧠 *الذاكرة:* ${Math.round(os.freemem() / 1024 / 1024)}/${Math.round(os.totalmem() / 1024 / 1024)} MB`
                        });
                    } catch (error) {
                        logger.error("خطأ في إرسال إشعار التشغيل للمشرف", error);
                    }
                }

                updateQR("qrscanned");

                botEvents.emit('connected', botNumber);

                if (qrCodeLinkToSend) {
                    try {
                        for (const admin of CONFIG.ADMIN_NUMBERS) {
                            await sock.sendMessage(`${admin}@s.whatsapp.net`, { text: qrCodeLinkToSend });
                        }
                        qrCodeLinkToSend = null;
                    } catch (error) {
                        logger.error("خطأ أثناء إرسال الرابط المُخزّن", error);
                    }
                }
            }

            if (connection === "close") {
                const reason = new Boom(lastDisconnect?.error)?.output?.statusCode;
                logger.info(`تم إغلاق الاتصال بسبب: ${reason}`);

                switch (reason) {
                    case DisconnectReason.badSession:
                    case DisconnectReason.connectionReplaced:
                    case DisconnectReason.loggedOut:
                        logger.info("حذف بيانات الجلسة وإعادة الاتصال");
                        deleteAuthData();
                        connectToWhatsApp();
                        break;
                    case DisconnectReason.connectionClosed:
                    case DisconnectReason.connectionLost:
                    case DisconnectReason.restartRequired:
                    case DisconnectReason.timedOut:
                        logger.info("إعادة محاولة الاتصال");

                        if (connectionRetries < CONFIG.MAX_RETRIES) {
                            connectionRetries++;
                            const delay = CONFIG.RECONNECT_INTERVAL * connectionRetries;
                            logger.info(`محاولة إعادة الاتصال ${connectionRetries}/${CONFIG.MAX_RETRIES} بعد ${delay}ms`);

                            setTimeout(() => {
                                connectToWhatsApp();
                            }, delay);
                        } else {
                            logger.error("وصلت لأقصى عدد محاولات، فشل الاتصال");

                            connectionRetries = 0;
                            deleteAuthData();

                            setTimeout(() => {
                                connectToWhatsApp();
                            }, CONFIG.RECONNECT_INTERVAL * 5);
                        }
                        break;
                    default:
                        logger.error(`سبب غير معروف للانقطاع: ${reason}`);
                        setTimeout(() => {
                            connectToWhatsApp();
                        }, CONFIG.RECONNECT_INTERVAL);
                }

                botEvents.emit('disconnected', reason);
            }

            if (update.qr) {
                qr = update.qr;
                updateQR("qr");
            }
        });

        sock.ev.on("creds.update", saveCreds);

        sock.ev.on("messages.upsert", async ({ messages, type }) => {
            if (type !== "notify") return;

            const message = messages[0];
            if (!message) return;

            const noWa = message.key.remoteJid;
            const pesan = message.message?.conversation ||
                         message.message?.extendedTextMessage?.text ||
                         message.message?.imageMessage?.caption ||
                         message.message?.videoMessage?.caption || '';

            messageStats.received++;

            logger.info(`رسالة جديدة من ${noWa}`, { message: pesan });

            if (CONFIG.COMMAND_PREFIX_REGEX.test(pesan.trim().charAt(0))) {
                let args = pesan.slice(1).trim().split(/\s+/);
                const command = args.shift().toLowerCase();
                const query = args.join(" ");

                logger.command(command, noWa, query);

                if (!securityManager.validateCommand(command, noWa)) {
                    await sock.sendMessage(noWa, {
                        text: "*⛔ غير مصرح لك باستخدام هذا الأمر*"
                    });
                    return;
                }

                const handler = commandRoutes[command];
                await handleCommand(sock, noWa, message, command, query, args, handler);
            }
            else if (message.message?.extendedTextMessage?.contextInfo?.quotedMessage) {
                await handleReply(sock, message);
            }
            else if (noWa === botNumber && pesan.toLowerCase() === "test") {
                await sock.sendMessage(botNumber, { text: "أنا برد على نفسي! 🤖" });
                messageStats.sent++;
            }
        });

        if (qr) {
            updateQR("qr");
        }

        return sock;
    } catch (error) {
        logger.error("خطأ في دالة الاتصال بواتساب", error);

        if (connectionRetries < CONFIG.MAX_RETRIES) {
            connectionRetries++;
            logger.info(`إعادة محاولة الاتصال ${connectionRetries}/${CONFIG.MAX_RETRIES}`);

            setTimeout(() => {
                connectToWhatsApp();
            }, CONFIG.RECONNECT_INTERVAL);
        } else {
            logger.error("فشل الاتصال بعد عدة محاولات");
        }
    }
};

async function handleCommand(sock, noWa, message, command, query, args, handler) {
    if (!handler) {
        logger.info(`أمر غير معروف: ${command}`);
        return await sendErrorMessage(sock, noWa, "*أمر مش معروف 🚫... جرب تكتب `.مساعدة` علشان تشوف قائمة الأوامر 📜*");
    }

    try {
        console.log(`🔄  messages.upsert: استدعاء الأمر ${command}`);
        await sock.sendMessage(noWa, { react: { text: "⏳", key: message.key } });

        const sender = {
            id: message.key.remoteJid,
            name: message.pushName || "مستخدم",
            pushName: message.pushName || "مستخدم"
        };

        if (['at', 'ar', 'as', 'online', 'ata', 'ara', 'autoreply'].includes(command)) {
            if (args.length < 1 || !['on', 'off'].includes(args[0])) {
                return await sock.sendMessage(noWa, { text: `❌ الأمر \`${command}\` يحتاج إلى \`on\` أو \`off\`` });
            }
            await handler(sock, noWa, message, args);
        } else if (command === 'delay') {
            await handler(sock, noWa, message, args);
        } else {
            await handler(sock, noWa, message, query);
        }

        await sock.sendMessage(noWa, { react: { text: "✅", key: message.key } });
    } catch (error) {
        logger.error(`خطأ في تنفيذ الأمر ${command}`, error, command, message);
        let errorMessage = "*حصل مشكلة مؤقتة 😕 جرب تاني بعد شوية 🔄*";
        if (error.message.includes("timeout")) errorMessage = "*الخدمة أخدت وقت طويل ⏳ جرب تاني*";
        else if (error.message.includes("quota")) errorMessage = "*الكوتة خلّصت النهاردة 😓 جرب بكرة*";
        await sendErrorMessage(sock, noWa, errorMessage);
        await sock.sendMessage(noWa, { react: { text: "❌", key: message.key } });
    }
}

const deleteAuthData = () => {
    try {
        fs.rmSync(CONFIG.AUTH_FOLDER, { recursive: true, force: true });
        logger.info("تم حذف بيانات الجلسة القديمة.");
    } catch (error) {
        logger.error("خطأ أثناء حذف بيانات الجلسة", error);
    }
};

const updateQR = async (data) => {
    switch (data) {
        case "qr":
            try {
                await qrcode.toFile(CONFIG.QR_PNG_PATH, qr, { errorCorrectionLevel: 'H' });

                const htmlContent = `
<!DOCTYPE html>
<html>
<head>
    <title>QR Code</title>
    <style>
        body {
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            background-color: #f0f0f0;
        }
        img {
            border: 5px solid #4CAF50;
            border-radius: 10px;
        }
    </style>
</head>
<body>
    <img src="qr.png" alt="QR Code">
</body>
</html>
`;
                fs.writeFileSync(CONFIG.QR_HTML_PATH, htmlContent);
                logger.info("تم إنشاء رمز الاستجابة السريعة وملف HTML.");

                qrCodeLinkToSend = `افتح الرابط لعرض رمز الاستجابة السريعة: file://${CONFIG.QR_HTML_PATH}`;

            } catch (error) {
                logger.error("خطأ أثناء إنشاء رمز الاستجابة السريعة أو ملف HTML", error);
            }
            break;
        case "qrscanned":
            try {
                fs.unlinkSync(CONFIG.QR_PNG_PATH);
                fs.unlinkSync(CONFIG.QR_HTML_PATH);
                logger.info("تم حذف ملفات QR.");
            } catch (err) {
                logger.error("خطأ أثناء حذف ملفات QR", err);
            }
            break;
    }
};

module.exports = { connectToWhatsApp, updateQR, commandNames, botEvents };
