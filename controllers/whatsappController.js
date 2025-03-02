const {
    default: makeWASocket,
    DisconnectReason,
    fetchLatestBaileysVersion,
    isJidBroadcast,
    makeInMemoryStore,
    useMultiFileAuthState,
    isJidGroup,
    proto,
    generateWAMessageFromContent,
    prepareWAMessageMedia,
    areJidsSameUser,
    getContentType,
    downloadContentFromMessage
} = require("@whiskeysockets/baileys");
const { Boom } = require("@hapi/boom");
const qrcode = require("qrcode-terminal");
const fs = require("fs");
const path = require('path');
const pino = require("pino");
const logger = pino({ level: "silent" });
const moment = require('moment');
const os = require('os');

// استيراد الدوال من الملفات الأخرى
const { stickerArabicCommand, takeCommand } = require('./sticker.js');
const { ttsArabicCommand } = require('./tts.js');
const { downloadSong } = require('./yt.js');
const { imageSearch, gifSearch } = require("./img.js");
const { movieCommand } = require("./movie.js");
const helpController = require("./help.js");
const { sendErrorMessage, sendFormattedMessage } = require("./messageUtils");
const { sendSecretMessage, handleReply } = require('./secretMessages.js');
const { adminCommands, ensureDirectoriesExist, loadSettings, setBotNumber } = require('./admin.js');

// تعريف المتغيرات العالمية
let autoReply = {};
const store = makeInMemoryStore({ logger: logger.child({ level: "silent" }) });
let sock;
let qr;
let botNumber;
let status = {
    isOnline: true,
    startTime: new Date(),
    messagesProcessed: 0,
    commandsExecuted: 0
};

// إعداد ملف تسجيل الأخطاء
const logErrorToFile = (error, command, message) => {
    const logDir = path.join(__dirname, '..', 'logs');
    if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true });
    const logFile = path.join(logDir, 'error.log');
    const logEntry = `[${new Date().toISOString()}] Command: ${command || 'Unknown'}, Error: ${error.message}, Message: ${JSON.stringify(message)}\n`;
    fs.appendFileSync(logFile, logEntry);
};

// إنشاء زر بسيط
const createSimpleButton = (displayText, id = null) => {
    return {
        quickReplyButton: {
            displayText,
            id: id || `id-${displayText}`
        }
    };
};

// إنشاء أزرار مجمعة
const createButtons = (buttons, headerText, footerText = '') => {
    return {
        templateButtons: buttons,
        headerType: 4,
        text: headerText,
        footer: footerText
    };
};

// إرسال رسالة بأزرار
const sendButtonMessage = async (sock, jid, text, footer, buttons) => {
    const buttonMessage = {
        text,
        footer,
        templateButtons: buttons,
        headerType: 1
    };

    return await sock.sendMessage(jid, buttonMessage);
};

// إرسال رسالة تفاعلية مع أزرار الاستجابة السريعة
const sendInteractiveMessage = async (sock, jid, text, buttons, listTitle = '', buttonText = 'اختر أحد الخيارات') => {
    const sections = buttons.map((button, index) => ({
        title: listTitle,
        rows: [{
            title: button.displayText || button,
            rowId: `option-${index + 1}`
        }]
    }));

    const listMessage = {
        text,
        footer: '© بوت الواتساب المتقدم',
        title: listTitle,
        buttonText,
        sections
    };

    return await sock.sendMessage(jid, listMessage);
};

// إرسال رسالة بوسائط متعددة
const sendMediaWithButtons = async (sock, jid, media, caption, buttons) => {
    let mediaMessage;

    if (media.startsWith('http')) {
        // إذا كان المسار URL، استخدم prepareWAMessageMedia لتحميل الوسائط
        const mediaType = media.match(/\.(jpg|jpeg|png)$/i) ? 'image' :
            media.match(/\.(mp4|mov)$/i) ? 'video' :
                media.match(/\.(mp3|wav|ogg)$/i) ? 'audio' : 'document';

        const prepared = await prepareWAMessageMedia({
            [mediaType]: { url: media }
        }, { upload: sock.waUploadToServer });

        mediaMessage = generateWAMessageFromContent(jid, {
            [mediaType + 'Message']: {
                ...prepared[mediaType],
                caption,
                footer: '© بوت الواتساب المتقدم',
                templateButtons: buttons
            }
        }, {});

        return await sock.relayMessage(jid, mediaMessage.message, { messageId: mediaMessage.key.id });
    } else {
        // إذا كان ملفًا محليًا
        const stats = fs.statSync(media);
        const fileSizeInBytes = stats.size;
        const mime = media.match(/\.(jpg|jpeg|png)$/i) ? 'image/jpeg' :
            media.match(/\.(mp4|mov)$/i) ? 'video/mp4' :
                media.match(/\.(mp3|wav|ogg)$/i) ? 'audio/mpeg' : 'application/octet-stream';

        const buttonMessage = {
            caption,
            footer: '© بوت الواتساب المتقدم',
            templateButtons: buttons,
            [media.match(/\.(jpg|jpeg|png)$/i) ? 'image' :
                media.match(/\.(mp4|mov)$/i) ? 'video' :
                    media.match(/\.(mp3|wav|ogg)$/i) ? 'audio' : 'document']: {
                url: media
            }
        };

        return await sock.sendMessage(jid, buttonMessage);
    }
};

// تعريف الأوامر العامة وأوامر الأدمن
const commandRoutes = {
    'sticker': stickerArabicCommand,
    'take': takeCommand,
    'tts': ttsArabicCommand,
    'song': downloadSong,
    'img': imageSearch,
    'gif': gifSearch,
    'movie': movieCommand,
    'help': async (sock, noWa, message, query) => {
        status.commandsExecuted++;
        const sections = [
            {
                title: 'الأوامر العامة',
                rows: [
                    { title: 'الملصقات - Stickers', rowId: 'help_sticker', description: 'إنشاء وتعديل الملصقات' },
                    { title: 'الوسائط - Media', rowId: 'help_media', description: 'البحث عن الصور والـGIF والأغاني' },
                    { title: 'النصوص - Text', rowId: 'help_text', description: 'تحويل النص إلى صوت وأكثر' },
                    { title: 'الرسائل السرية - Secret', rowId: 'help_secret', description: 'إرسال رسائل سرية' }
                ]
            },
            {
                title: 'أوامر المسؤول',
                rows: [
                    { title: 'إعدادات البوت - Settings', rowId: 'help_admin', description: 'إدارة إعدادات البوت' }
                ]
            }
        ];

        const listMessage = {
            text: '📚 *قائمة أوامر البوت* 📚\n\nاختر فئة لعرض الأوامر المتاحة.',
            footer: '© بوت الواتساب المتقدم',
            title: 'مساعدة البوت',
            buttonText: 'عرض الأوامر',
            sections
        };

        await sock.sendMessage(noWa, listMessage);
    },
    'menu': async (sock, noWa, message, query) => {
        status.commandsExecuted++;
        const buttons = [
            createSimpleButton('📝 قائمة الأوامر', 'help'),
            createSimpleButton('🔧 إعدادات', 'settings'),
            createSimpleButton('ℹ️ حول البوت', 'about')
        ];

        await sendButtonMessage(
            sock,
            noWa,
            '*قائمة البوت الرئيسية* 🤖\n\nاختر أحد الخيارات التالية:',
            '© بوت الواتساب المتقدم',
            buttons
        );
    },
    'secret': async (sock, noWa, message, query) => {
        status.commandsExecuted++;
        if (!query) {
            const buttons = [
                createSimpleButton('📤 إرسال رسالة سرية', 'send_secret'),
                createSimpleButton('ℹ️ كيفية الاستخدام', 'secret_help')
            ];

            return await sendButtonMessage(
                sock,
                noWa,
                '*الرسائل السرية* 🔒\n\nيمكنك إرسال رسائل سرية لأي شخص باستخدام هذه الميزة.',
                'الصيغة: `.secret الرقم الرسالة`',
                buttons
            );
        }

        const [recipientJid, ...messageParts] = query.split(' ');
        const messageText = messageParts.join(' ').trim();
        if (!recipientJid || !messageText) return await sock.sendMessage(noWa, { text: "حدد رقم المستلم والرسالة السرية صح 📞" });
        await sendSecretMessage(sock, noWa, recipientJid, messageText, false);
    },
    'smes': async (sock, noWa, message, query) => {
        status.commandsExecuted++;
        if (!query) return await sock.sendMessage(noWa, { text: "اكتب رسالتك السرية بعد `.smes` 📩" });
        const [recipientJid, ...messageParts] = query.split(' ');
        const messageText = messageParts.join(' ').trim();
        if (!recipientJid || !messageText) return await sock.sendMessage(noWa, { text: "حدد رقم المستلم والرسالة السرية صح 📞" });
        await sendSecretMessage(sock, noWa, recipientJid, messageText, false);
    },
    'صارحني': async (sock, noWa, message, query) => {
        status.commandsExecuted++;
        if (!query) return await sock.sendMessage(noWa, { text: "اكتب رسالتك السرية بعد `.صارحني` 📩" });
        const [recipientJid, ...messageParts] = query.split(' ');
        const messageText = messageParts.join(' ').trim();
        if (!recipientJid || !messageText) return await sock.sendMessage(noWa, { text: "حدد رقم المستلم والرسالة السرية صح 📞" });
        await sendSecretMessage(sock, noWa, recipientJid, messageText, false);
    },
    // أوامر الأدمن
    'at': async (sock, noWa, message, args) => {
        status.commandsExecuted++;
        if (!args[0]) {
            const buttons = [
                createSimpleButton('✅ تفعيل', 'at_on'),
                createSimpleButton('❌ تعطيل', 'at_off'),
                createSimpleButton('ℹ️ الحالة', 'at_status')
            ];

            return await sendButtonMessage(
                sock,
                noWa,
                '*إعدادات التنبيه التلقائي* 🔔\n\nاختر أحد الخيارات:',
                'استخدم `.at on` أو `.at off`',
                buttons
            );
        }

        const handler = adminCommands['at ' + args[0]];
        if (handler) await handler(sock, noWa, message);
        else await sock.sendMessage(noWa, { text: "❌ اختيار غير صالح، استخدم `on` أو `off`" });
    },
    'ar': async (sock, noWa, message, args) => {
        status.commandsExecuted++;
        if (!args[0]) {
            const buttons = [
                createSimpleButton('✅ تفعيل', 'ar_on'),
                createSimpleButton('❌ تعطيل', 'ar_off'),
                createSimpleButton('ℹ️ الحالة', 'ar_status')
            ];

            return await sendButtonMessage(
                sock,
                noWa,
                '*إعدادات الرد التلقائي* 🤖\n\nاختر أحد الخيارات:',
                'استخدم `.ar on` أو `.ar off`',
                buttons
            );
        }

        const handler = adminCommands['ar ' + args[0]];
        if (handler) await handler(sock, noWa, message);
        else await sock.sendMessage(noWa, { text: "❌ اختيار غير صالح، استخدم `on` أو `off`" });
    },
    'as': async (sock, noWa, message, args) => {
        status.commandsExecuted++;
        if (!args[0]) {
            const buttons = [
                createSimpleButton('✅ تفعيل', 'as_on'),
                createSimpleButton('❌ تعطيل', 'as_off'),
                createSimpleButton('ℹ️ الحالة', 'as_status')
            ];

            return await sendButtonMessage(
                sock,
                noWa,
                '*إعدادات السلام التلقائي* 👋\n\nاختر أحد الخيارات:',
                'استخدم `.as on` أو `.as off`',
                buttons
            );
        }

        const handler = adminCommands['as ' + args[0]];
        if (handler) await handler(sock, noWa, message);
        else await sock.sendMessage(noWa, { text: "❌ اختيار غير صالح، استخدم `on` أو `off`" });
    },
    'online': async (sock, noWa, message, args) => {
        status.commandsExecuted++;
        if (!args[0]) {
            const buttons = [
                createSimpleButton('✅ متصل', 'online_on'),
                createSimpleButton('❌ غير متصل', 'online_off'),
                createSimpleButton('ℹ️ الحالة', 'online_status')
            ];

            return await sendButtonMessage(
                sock,
                noWa,
                '*إعدادات حالة الاتصال* 🟢\n\nاختر أحد الخيارات:',
                'استخدم `.online on` أو `.online off`',
                buttons
            );
        }

        const handler = adminCommands['online ' + args[0]];
        if (handler) await handler(sock, noWa, message);
        else await sock.sendMessage(noWa, { text: "❌ اختيار غير صالح، استخدم `on` أو `off`" });
    },
    'ata': async (sock, noWa, message, args) => {
        status.commandsExecuted++;
        if (!args[0]) {
            const buttons = [
                createSimpleButton('✅ تفعيل', 'ata_on'),
                createSimpleButton('❌ تعطيل', 'ata_off'),
                createSimpleButton('ℹ️ الحالة', 'ata_status')
            ];

            return await sendButtonMessage(
                sock,
                noWa,
                '*إعدادات الاستجابة التلقائية للمجموعات* 👥\n\nاختر أحد الخيارات:',
                'استخدم `.ata on` أو `.ata off`',
                buttons
            );
        }

        const handler = adminCommands['ata ' + args[0]];
        if (handler) await handler(sock, noWa, message);
        else await sock.sendMessage(noWa, { text: "❌ اختيار غير صالح، استخدم `on` أو `off`" });
    },
    'ara': async (sock, noWa, message, args) => {
        status.commandsExecuted++;
        if (!args[0]) {
            const buttons = [
                createSimpleButton('✅ تفعيل', 'ara_on'),
                createSimpleButton('❌ تعطيل', 'ara_off'),
                createSimpleButton('ℹ️ الحالة', 'ara_status')
            ];

            return await sendButtonMessage(
                sock,
                noWa,
                '*إعدادات الرد التلقائي للمجموعات* 👥\n\nاختر أحد الخيارات:',
                'استخدم `.ara on` أو `.ara off`',
                buttons
            );
        }

        const handler = adminCommands['ara ' + args[0]];
        if (handler) await handler(sock, noWa, message);
        else await sock.sendMessage(noWa, { text: "❌ اختيار غير صالح، استخدم `on` أو `off`" });
    },
    'autoreply': async (sock, noWa, message, args) => {
        status.commandsExecuted++;
        if (!args[0]) {
            const buttons = [
                createSimpleButton('✅ تفعيل', 'autoreply_on'),
                createSimpleButton('❌ تعطيل', 'autoreply_off'),
                createSimpleButton('ℹ️ إدارة الردود', 'autoreply_manage')
            ];

            return await sendButtonMessage(
                sock,
                noWa,
                '*إعدادات الردود التلقائية المخصصة* 📝\n\nاختر أحد الخيارات:',
                'استخدم `.autoreply on` أو `.autoreply off`',
                buttons
            );
        }

        const handler = adminCommands['autoreply ' + args[0]];
        if (handler) await handler(sock, noWa, message);
        else await sock.sendMessage(noWa, { text: "❌ اختيار غير صالح، استخدم `on` أو `off`" });
    },
    'delay': async (sock, noWa, message, args) => {
        status.commandsExecuted++;
        if (!args || args.length === 0) {
            const sections = [
                {
                    title: 'إعدادات التأخير',
                    rows: [
                        { title: '1 ثانية', rowId: 'delay_1', description: 'تأخير 1 ثانية' },
                        { title: '2 ثانية', rowId: 'delay_2', description: 'تأخير 2 ثانية' },
                        { title: '3 ثوان', rowId: 'delay_3', description: 'تأخير 3 ثوان' },
                        { title: '5 ثوان', rowId: 'delay_5', description: 'تأخير 5 ثوان' }
                    ]
                }
            ];

            const listMessage = {
                text: '*إعدادات تأخير الرد* ⏱️\n\nحدد وقت التأخير المطلوب:',
                footer: '© بوت الواتساب المتقدم',
                title: 'تأخير الرد',
                buttonText: 'اختر التأخير',
                sections
            };

            return await sock.sendMessage(noWa, listMessage);
        }

        await adminCommands['delay'](sock, noWa, args, message);
    },
    'admin': async (sock, noWa, message) => {
        status.commandsExecuted++;
        const buttons = [
            createSimpleButton('📊 الإحصائيات', 'stats'),
            createSimpleButton('📝 السجلات', 'logs'),
            createSimpleButton('🔄 إعادة تشغيل', 'restart')
        ];

        await sendButtonMessage(
            sock,
            noWa,
            '*لوحة المسؤول* 🛠️\n\nاختر أحد الخيارات التالية:',
            '© بوت الواتساب المتقدم',
            buttons
        );

        await adminCommands['admin'](sock, noWa, message);
    },
    'stats': async (sock, noWa, message) => {
        status.commandsExecuted++;
        // جمع معلومات النظام
        const uptime = moment.duration(process.uptime(), 'seconds').humanize();
        const memUsage = process.memoryUsage();
        const systemInfo = {
            platform: os.platform(),
            arch: os.arch(),
            cpus: os.cpus().length,
            totalMemory: Math.round(os.totalmem() / (1024 * 1024)) + ' MB',
            freeMemory: Math.round(os.freemem() / (1024 * 1024)) + ' MB',
            uptime: Math.round(os.uptime() / 3600) + ' ساعة'
        };

        // إنشاء رسالة الإحصائيات
        const statsMessage = `*📊 إحصائيات البوت*\n\n` +
            `*⏱️ وقت التشغيل:* ${uptime}\n` +
            `*📨 الرسائل المعالجة:* ${status.messagesProcessed}\n` +
            `*🔧 الأوامر المنفذة:* ${status.commandsExecuted}\n\n` +
            `*💻 معلومات النظام:*\n` +
            `- النظام: ${systemInfo.platform} (${systemInfo.arch})\n` +
            `- المعالجات: ${systemInfo.cpus}\n` +
            `- الذاكرة: ${systemInfo.freeMemory} حرة من ${systemInfo.totalMemory}\n` +
            `- تشغيل النظام: ${systemInfo.uptime}\n\n` +
            `*🧠 استخدام الذاكرة:*\n` +
            `- RSS: ${Math.round(memUsage.rss / (1024 * 1024))} MB\n` +
            `- Heap: ${Math.round(memUsage.heapUsed / (1024 * 1024))} MB / ${Math.round(memUsage.heapTotal / (1024 * 1024))} MB`;

        const buttons = [
            createSimpleButton('🔄 تحديث', 'refresh_stats')
        ];

        await sendButtonMessage(sock, noWa, statsMessage, 'آخر تحديث: ' + new Date().toLocaleString(), buttons);
        await adminCommands['stats'](sock, noWa, message);
    },
    'logs': async (sock, noWa, message) => {
        status.commandsExecuted++;
        // قراءة آخر 10 أخطاء من ملف السجل
        const logDir = path.join(__dirname, '..', 'logs');
        const logFile = path.join(logDir, 'error.log');

        let logContent = "";
        if (fs.existsSync(logFile)) {
            const data = fs.readFileSync(logFile, 'utf8');
            const lines = data.split('\n').filter(line => line.trim() !== '');
            logContent = lines.slice(-10).join('\n');
        } else {
            logContent = "لا توجد سجلات أخطاء حتى الآن.";
        }

        const buttons = [
            createSimpleButton('🗑️ مسح السجلات', 'clear_logs'),
            createSimpleButton('📥 تحميل كامل السجلات', 'download_logs')
        ];

        await sendButtonMessage(
            sock,
            noWa,
            `*📝 آخر الأخطاء المسجلة*\n\n${logContent.length > 1000 ? logContent.substring(0, 1000) + '...' : logContent}`,
            'استخدم الأزرار أدناه للتحكم في السجلات',
            buttons
        );

        await adminCommands['logs'](sock, noWa, message);
    },
    'restart': async (sock, noWa, message) => {
        status.commandsExecuted++;

        await sock.sendMessage(noWa, {
            text: "*🔄 جاري إعادة تشغيل البوت...*\n\nسيتم إعادة الاتصال خلال ثوان.",
            footer: '© بوت الواتساب المتقدم'
        });

        await adminCommands['restart'](sock, noWa, message);
        deleteAuthData();
        setTimeout(() => connectToWhatsApp(), 1000);
    },
    'about': async (sock, noWa, message) => {
        status.commandsExecuted++;

        const buttons = [
            createSimpleButton('📚 الأوامر', 'help'),
            createSimpleButton('📊 الإحصائيات', 'stats')
        ];

        const aboutMessage = `*حول البوت* ℹ️\n\n` +
            `بوت واتساب متقدم يوفر العديد من الميزات والأدوات المفيدة لمستخدمي واتساب.\n\n` +
            `*الميزات:*\n` +
            `• إنشاء ملصقات من الصور والفيديوهات 🖼️\n` +
            `• تحويل النص إلى صوت 🔊\n` +
            `• البحث عن الصور وتنزيل الأغاني 🎵\n` +
            `• إرسال رسائل سرية 🔒\n` +
            `• البحث عن معلومات الأفلام 🎬\n` +
            `• العديد من الأدوات الأخرى 🛠️\n\n` +
            `*الإصدار:* 2.0.0\n` +
            `*تاريخ آخر تحديث:* ${new Date().toLocaleDateString()}\n` +
            `*وقت التشغيل:* ${moment.duration(process.uptime(), 'seconds').humanize()}`;

        await sendButtonMessage(sock, noWa, aboutMessage, '© بوت الواتساب المتقدم', buttons);
    }
};

const commandNames = Object.keys(commandRoutes);

// معالجة الأزرار عند الضغط عليها
const handleButtonResponse = async (sock, msg) => {
    const { selectedButtonId, selectedRowId } = msg.message.buttonsResponseMessage || msg.message.listResponseMessage || {};
    const responseId = selectedButtonId || selectedRowId || '';
    const sender = msg.key.remoteJid;

    console.log(`🔄 استجابة زر من ${sender}: ${responseId}`);

    if (responseId.startsWith('help_')) {
        const category = responseId.split('_')[1];
        let helpText = '';

        switch (category) {
            case 'sticker':
                helpText = `*📚 أوامر الملصقات*\n\n` +
                    `• \`.sticker\` - تحويل الصورة أو الفيديو إلى ملصق\n` +
                    `• \`.take اسم المؤلف\` - تغيير اسم المؤلف للملصق`;
                break;
            case 'media':
                helpText = `*📚 أوامر الوسائط*\n\n` +
                    `• \`.img استعلام\` - البحث عن صورة\n` +
                    `• \`.gif استعلام\` - البحث عن GIF\n` +
                    `• \`.song اسم الأغنية\` - تنزيل أغنية\n` +
                    `• \`.movie اسم الفيلم\` - البحث عن معلومات فيلم`;
                break;
            case 'text':
                helpText = `*📚 أوامر النص*\n\n` +
                    `• \`.tts نص\` - تحويل النص إلى صوت`;
                break;
            case 'secret':
                helpText = `*📚 أوامر الرسائل السرية*\n\n` +
                    `• \`.secret الرقم الرسالة\` - إرسال رسالة سرية\n` +
                    `• \`.smes الرقم الرسالة\` - اختصار لأمر secret\n` +
                    `• \`.صارحني الرقم الرسالة\` - نفس الأمر بالعربي`;
                break;
            case 'admin':
                helpText = `*📚 أوامر المسؤول*\n\n` +
                    `• \`.admin\` - عرض لوحة المسؤول\n` +
                    `• \`.stats\` - عرض إحصائيات البوت\n` +
                    `• \`.logs\` - عرض سجلات الأخطاء\n` +
                    `• \`.restart\` - إعادة تشغيل البوت\n` +
                    `• \`.at on/off\` - تفعيل/تعطيل التنبيه التلقائي\n` +
                    `• \`.ar on/off\` - تفعيل/تعطيل الرد التلقائي\n` +
                    `• \`.online on/off\` - تحديد حالة الاتصال\n` +
                    `• \`.delay رقم\` - تحديد تأخير الرد`;
                break;
            default:
                helpText = "فئة غير معروفة";
        }

        await sock.sendMessage(sender, { text: helpText });
    } else if (responseId.includes('_on') || responseId.includes('_off')) {
        // معالجة تفعيل/تعطيل الميزات
        const [command, state] = responseId.split('_');
        try {
            const handler = adminCommands[`${command} ${state}`];
            if (handler) {
                await handler(sock, sender, {});
            } else {
                await sock.sendMessage(sender, { text: "❌ أمر غير صالح" });
            }
        } catch (error) {
            console.error("خطأ في معالجة استجابة الزر:", error);
            await sock.sendMessage(sender, { text: "❌ حدث خطأ أثناء تنفيذ الأمر" });
        }
    } else if (responseId === 'refresh_stats') {
        // تحديث الإحصائيات
        await commandRoutes['stats'](sock, sender, {});
    } else if (responseId === 'clear_logs') {
        // مسح السجلات
        const logDir = path.join(__dirname, '..', 'logs');
        const logFile = path.join(logDir, 'error.log');
        if (fs.existsSync(logFile)) {
            fs.writeFileSync(logFile, '');
            await sock.sendMessage(sender, { text: "✅ تم مسح السجلات بنجاح" });
        } else {
            await sock.sendMessage(sender, { text: "❌ لا يوجد ملف سجلات" });
        }
    } else if (responseId === 'download_logs') {
        // تحميل كامل السجلات
        const logDir = path.join(__dirname, '..', 'logs');
        const logFile = path.join(logDir, 'error.log');
        if (fs.existsSync(logFile)) {
            await sock.sendMessage(sender, {
                document: { url: logFile },
                fileName: 'error_logs.txt',
                mimetype: 'text/plain'
            });
        } else {
            await sock.sendMessage(sender, { text: "❌ لا يوجد ملف سجلات" });
        }
    }
};



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
            status.isOnline = true;
            status.startTime = new Date();
        }

        if (connection === "close") {
            const reason = new Boom(lastDisconnect?.error)?.output?.statusCode;
            console.log("❌  connection.update: تم إغلاق الاتصال بسبب:", reason);
            status.isOnline = false;
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

        status.messagesProcessed++;

        console.log(`📩  messages.upsert: رسالة جديدة من ${noWa}، الرسالة: ${pesan}`);

        // معالجة استجابات الأزرار والقوائم
        if (message.message?.buttonsResponseMessage || message.message?.listResponseMessage) {
            return await handleButtonResponse(sock, message);
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
        } else {
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

module.exports = { connectToWhatsApp, updateQR, commandNames };
