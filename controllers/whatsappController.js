// whatsappController.js
const {
    default: makeWASocket,
    DisconnectReason,
    fetchLatestBaileysVersion,
    isJidBroadcast,
    makeInMemoryStore,
    useMultiFileAuthState,
    isJidGroup
} = require("@whiskeysockets/baileys");
const { Boom } = require("@hapi/boom");
const qrcode = require("qrcode-terminal");
const fs = require("fs");
const path = require('path');
const pino = require("pino");

// استيراد الدوال من الملفات الأخرى
const { stickerArabicCommand, takeCommand } = require('./sticker.js');
const { ttsArabicCommand } = require('./tts.js');
const { downloadSong, downloadVideo, searchAndDisplay } = require('./yt.js');
const { imageSearch, gifSearch } = require("./img.js");
const { movieCommand } = require("./movie.js");
const helpController = require("./help.js");
const { sendErrorMessage, sendFormattedMessage } = require("./messageUtils");
const { sendSecretMessage, handleReply } = require('./secretMessages.js');
const { adminCommands, ensureDirectoriesExist, loadSettings, setBotNumber } = require('./admin.js');
const { handleImageMessage } = require('./vision.js'); // Import the new image handler

// تعريف المتغيرات العالمية
let autoReply = {};
const store = makeInMemoryStore({ logger: pino().child({ level: "silent" }) });
let sock;
let qr;
let botNumber; // متغير لتخزين رقم البوت

// إعداد ملف تسجيل الأخطاء
const logErrorToFile = (error, command, message) => {
    const logDir = path.join(__dirname, '..', 'logs');
    if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true });
    const logFile = path.join(logDir, 'error.log');
    const logEntry = `[${new Date().toISOString()}] Command: ${command || 'Unknown'}, Error: ${error.message}, Message: ${JSON.stringify(message)}\n`;
    fs.appendFileSync(logFile, logEntry);
};

// دالة لمنع البوت من معالجة رسائله الخاصة في vision.js
const shouldProcessImage = (message) => {
    return !(message.key.remoteJid === 'status@broadcast' || message.key.fromMe);
};


// تعريف الأوامر العامة وأوامر الأدمن
const commandRoutes = {
    'sticker': stickerArabicCommand,
    'take': takeCommand,
    'tts': ttsArabicCommand,
    'song': downloadSong,
    'video': downloadVideo,
    'yts': searchAndDisplay,
    'img': imageSearch,
    'gif': gifSearch,
    'movie': movieCommand,
    'help': helpController.handler,
    'menu': helpController.handler,
    'secret': async (sock, noWa, message, query) => {
        if (!query) return await sock.sendMessage(noWa, { text: "اكتب رسالتك السرية بعد `.secret` 📩" });
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
    // أوامر الأدمن
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
        await adminCommands['stats'](sock, noWa, message);
    },
    'logs': async (sock, noWa, message) => {
        await adminCommands['logs'](sock, noWa, message);
    },
    'restart': async (sock, noWa, message) => {
        await adminCommands['restart'](sock, noWa, message);
        deleteAuthData();
        setTimeout(() => connectToWhatsApp(), 1000);
    }
};

const commandNames = Object.keys(commandRoutes);

const connectToWhatsApp = async () => {
    console.log("➡️  connectToWhatsApp: بدء الدالة");

    await ensureDirectoriesExist(); // إنشاء المجلدات الضرورية من admin.js
    await loadSettings(); // تحميل إعدادات الأدمن

    const { state, saveCreds } = await useMultiFileAuthState("baileys_auth_info");
    console.log("➡️  connectToWhatsApp: تم تحميل/إنشاء بيانات المصادقة");

    const { version } = await fetchLatestBaileysVersion();
    console.log("➡️  connectToWhatsApp: تم الحصول على أحدث إصدار من Baileys:", version);

    sock = makeWASocket({
        printQRInTerminal: true,
        auth: state,
        logger: pino({ level: "silent" }),
        version,
        shouldIgnoreJid: (jid) => isJidBroadcast(jid),
    });

    store.bind(sock.ev);

    sock.ev.on("connection.update", async (update) => {
        console.log("🔄  connection.update:", update);
        const { connection, lastDisconnect } = update;

        if (connection === "open") {
            botNumber = sock.user.id.split(":")[0] + "@s.whatsapp.net"; // استخراج رقم البوت
            setBotNumber(botNumber); // تمرير رقم البوت إلى admin.js
            console.log("🔹 رقم البوت:", botNumber);
        }

        if (connection === "close") {
            const reason = new Boom(lastDisconnect?.error)?.output?.statusCode;
            console.log("❌  connection.update: تم إغلاق الاتصال بسبب:", reason);
            switch (reason) {
                case DisconnectReason.badSession:
                case DisconnectReason.connectionReplaced:
                case DisconnectReason.loggedOut:
                    deleteAuthData();
                    connectToWhatsApp();
                    break;
                case DisconnectReason.connectionClosed:
                case DisconnectReason.connectionLost:
                case DisconnectReason.restartRequired:
                case DisconnectReason.timedOut:
                    connectToWhatsApp();
                    break;
            }
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
      const noWa = message.key.remoteJid;
      let pesan = message.message?.conversation || message.message?.extendedTextMessage?.text || '';

      // تعديل رسائل البوت نفسه
      if (message.key.fromMe) {
        if(message.message?.extendedTextMessage?.contextInfo?.quotedMessage?.conversation){
          message.message.extendedTextMessage.contextInfo.quotedMessage.conversation = message.message.extendedTextMessage.contextInfo.quotedMessage.conversation.replace(/Zaky AI 🤖/g, 'Zaky Bot 🤖');
        }
          // تعديل الرسائل النصية
          if (message.message?.conversation) {
              message.message.conversation = message.message.conversation.replace(/Zaky AI 🤖/g, 'Zaky Bot 🤖');
          }
          if (message.message?.extendedTextMessage?.text) {
              message.message.extendedTextMessage.text = message.message.extendedTextMessage.text.replace(/Zaky AI 🤖/g, 'Zaky Bot 🤖');
          }
          // تعديل رسائل الأزرار
          if (message.message?.buttonsMessage?.caption) {
              message.message.buttonsMessage.caption = message.message.buttonsMessage.caption.replace(/Zaky AI 🤖/g, 'Zaky Bot 🤖');
          }
          if (message.message?.buttonsMessage?.footer) {
              message.message.buttonsMessage.footer = message.message.buttonsMessage.footer.replace(/Zaky AI 🤖/g, 'Zaky Bot 🤖');
          }
           // تعديل الرسائل التي تحتوي على صور
          if (message.message?.imageMessage?.caption) {
              message.message.imageMessage.caption = message.message.imageMessage.caption.replace(/Zaky AI 🤖/g, "Zaky Bot 🤖");
          }

          // تعديل الرسائل التي تحتوي على مقاطع فيديو
          if (message.message?.videoMessage?.caption) {
              message.message.videoMessage.caption = message.message.videoMessage.caption.replace(/Zaky AI 🤖/g, "Zaky Bot 🤖");
          }
        }

      console.log(`📩  messages.upsert: رسالة جديدة من ${noWa}، الرسالة: ${pesan}`);

      // معالجة الصور (إذا كانت الرسالة ليست من البوت)
      if (shouldProcessImage(message)) {
          await handleImageMessage(sock, message);
      }

      const prefixRegex = /^[\/.]|#/;
      if (prefixRegex.test(pesan.trim().charAt(0))) {
          let args = pesan.slice(1).trim().split(/\s+/);
          const command = args.shift().toLowerCase();
          const query = args.join(" ");
          console.log(`🔄  messages.upsert: تنفيذ الأمر: ${command}, الاستعلام: ${query}`);

          const handler = commandRoutes[command];
          await handleCommand(sock, noWa, message, command, query, args, handler);
      } else if (message.message?.extendedTextMessage?.contextInfo?.quotedMessage) {
          await handleReply(sock, message);
      } else if (noWa === botNumber && pesan.toLowerCase() === "test") {
          await sock.sendMessage(botNumber, { text: "أنا برد على نفسي! 🤖" });
      }
  });
};

async function handleCommand(sock, noWa, message, command, query, args, handler) {
    if (!handler) {
        console.log("❌  messages.upsert: أمر غير معروف");
        return await sendErrorMessage(sock, noWa, "*أمر مش معروف 🚫... جرب تكتب `.help` علشان تشوف قائمة الأوامر 📜*");
    }

    try {
        console.log(`🔄  messages.upsert: استدعاء الأمر ${command}`);
        await sock.sendMessage(noWa, { react: { text: "⏳", key: message.key } });

        const sender = {
            id: message.key.remoteJid,
            name: message.pushName || "مستخدم",
            pushName: message.pushName || "مستخدم"
        };

        // معالجة الأوامر التي تحتاج إلى on/off أو args خاصة
        if (['at', 'ar', 'as', 'online', 'ata', 'ara', 'autoreply'].includes(command)) {
            if (args.length < 1 || !['on', 'off'].includes(args[0])) {
                return await sock.sendMessage(noWa, { text: `❌ الأمر \`${command}\` يحتاج إلى \`on\` أو \`off\`` });
            }
            await handler(sock, noWa, message, args);
        } else if (command === 'delay') {
            await handler(sock, noWa, message, args);
        }else {
            await handler(sock, noWa, message, query);
        }

        await sock.sendMessage(noWa, { react: { text: "✅", key: message.key } });
    } catch (error) {
        console.error(`❌  خطأ في تنفيذ الأمر ${command}:`, error);
        logErrorToFile(error, command, message);
        let errorMessage = "*حصل مشكلة مؤقتة 😕 جرب تاني بعد شوية 🔄*";
        if (error.message.includes("timeout")) errorMessage = "*الخدمة أخدت وقت طويل ⏳ جرب تاني*";
        else if (error.message.includes("quota")) errorMessage = "*الكوتة خلّصت النهاردة 😓 جرب بكرة*";
        await sendErrorMessage(sock, noWa, errorMessage);
        await sock.sendMessage(noWa, { react: { text: "❌", key: message.key } });
    }
}

const deleteAuthData = () => {
    try {
        fs.rmSync("baileys_auth_info", { recursive: true, force: true });
        console.log("🗑️  تم حذف بيانات الجلسة القديمة.");
    } catch (error) {
        console.error("❌  deleteAuthData: خطأ أثناء حذف بيانات الجلسة:", error);
    }
};

const updateQR = (data) => {
    switch (data) {
        case "qr":
            qrcode.generate(qr, { small: true });
            break;
        case "qrscanned":
            break;
    }
};

module.exports = { connectToWhatsApp, updateQR, commandNames };
