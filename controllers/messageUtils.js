const fs = require('fs');
const path = require('path');
const { promisify } = require('util');
require('dotenv').config();

const externalAdTitle = process.env.EXTERNAL_AD_TITLE || 'مطور 🤖 Zaky AI 🤖';
const externalAdBody = process.env.EXTERNAL_AD_BODY || 'للمساعدة أو الاستفسارات';
const externalAdMediaType = parseInt(process.env.EXTERNAL_AD_MEDIA_TYPE) || 2;
const externalAdThumbnailPath = process.env.EXTERNAL_AD_THUMBNAIL_PATH || path.join(__dirname, '..', 'assets', 'zakyai.jpg');
const mediaUrl = process.env.EXTERNAL_AD_MEDIA_URL || 'https://wa.me/201280779419';
const sourceUrl = process.env.EXTERNAL_AD_SOURCE_URL || 'https://wa.me/201280779419';
const botSignature = process.env.BOT_SIGNATURE || "تحياتي Zaky 𖤍";

let externalAdThumbnail;
try {
    externalAdThumbnail = fs.readFileSync(externalAdThumbnailPath);
} catch (error) {
    console.warn(`⚠️ لم يتم العثور على الصورة المصغرة في المسار: ${externalAdThumbnailPath}. استخدام صورة افتراضية بديلة.`);
    externalAdThumbnail = null;
}

const createAdContext = (customTitle = externalAdTitle) => ({
    forwardingScore: 999,
    isForwarded: true,
    externalAdReply: {
        title: customTitle,
        body: externalAdBody,
        mediaType: externalAdMediaType,
        thumbnail: externalAdThumbnail,
        mediaUrl: mediaUrl,
        sourceUrl: sourceUrl
    }
});

const sendErrorMessage = async (sock, chatId, text, customTitle = externalAdTitle, quoted = null) => {
    const message = {
        text,
        contextInfo: createAdContext(customTitle)
    };

    await sock.sendMessage(chatId, message, quoted ? { quoted } : {}).catch(err => {
        console.error(`❌ فشل إرسال رسالة الخطأ: ${err.message}`);
    });
};

const sendStickerCreationSuccessMessage = async (sock, chatId, customText = '✅ تم عمل الملصق بنجاح 🎉', quoted = null) => {
    const message = {
        text: customText,
        contextInfo: createAdContext()
    };

    await sock.sendMessage(chatId, message, quoted ? { quoted } : {}).catch(err => {
        console.error(`❌ فشل إرسال رسالة نجاح الملصق: ${err.message}`);
    });
};

const sendText = async (sock, chatId, text, quoted = null, withAd = false) => {
    const message = withAd
        ? { text, contextInfo: createAdContext() }
        : { text };

    await sock.sendMessage(chatId, message, quoted ? { quoted } : {}).catch(err => {
        console.error(`❌ فشل إرسال النص: ${err.message}`);
    });
};

const sendFormattedMessage = async (sock, chatId, messageText, emoji = '🚀', quoted = null, withAd = false) => {
    const formattedMessage = `*${messageText}* ${emoji}`;

    const message = withAd
        ? { text: formattedMessage, contextInfo: createAdContext() }
        : { text: formattedMessage };

    return sock.sendMessage(chatId, message, quoted ? { quoted } : {}).catch(err => {
        console.error(`❌ فشل إرسال الرسالة المنسقة: ${err.message}`);
        return null;
    });
};

const sendImage = async (sock, chatId, image, caption = '', quoted = null) => {
    try {
        let imageData;

        if (typeof image === 'string' && (image.startsWith('http://') || image.startsWith('https://'))) {
            imageData = { url: image };
        } else {
            imageData = image;
        }

        const message = {
            image: imageData,
            caption: caption ? `${caption}\n\n${botSignature}` : botSignature
        };

        return await sock.sendMessage(chatId, message, quoted ? { quoted } : {});
    } catch (error) {
        console.error(`❌ فشل إرسال الصورة: ${error.message}`);
        await sendErrorMessage(sock, chatId, "⚠️ حصل مشكلة وأنا ببعت الصورة 😕 جرب تاني 🔄", null, quoted);
        return null;
    }
};

const sendMedia = async (sock, chatId, media, type, caption = '', filename = '', quoted = null) => {
    try {
        let mediaData;

        if (typeof media === 'string' && (media.startsWith('http://') || media.startsWith('https://'))) {
            mediaData = { url: media };
        } else {
            mediaData = media;
        }

        const message = {};

        switch (type.toLowerCase()) {
            case 'audio':
                message.audio = mediaData;
                message.mimetype = 'audio/mp4';
                message.ptt = false;
                break;

            case 'voice':
                message.audio = mediaData;
                message.mimetype = 'audio/ogg; codecs=opus';
                message.ptt = true;
                break;

            case 'video':
                message.video = mediaData;
                message.caption = caption ? `${caption}\n\n${botSignature}` : botSignature;
                message.gifPlayback = false;
                break;

            case 'gif':
                message.video = mediaData;
                message.caption = caption ? `${caption}\n\n${botSignature}` : botSignature;
                message.gifPlayback = true;
                break;

            case 'document':
                message.document = mediaData;
                message.mimetype = 'application/pdf';
                message.fileName = filename || 'document.pdf';
                message.caption = caption ? `${caption}\n\n${botSignature}` : botSignature;
                break;

            default:
                throw new Error(`نوع وسائط مش مدعوم: ${type}`);
        }

        return await sock.sendMessage(chatId, message, quoted ? { quoted } : {});
    } catch (error) {
        console.error(`❌ فشل إرسال الوسائط (${type}): ${error.message}`);
        await sendErrorMessage(sock, chatId, `⚠️ حصل مشكلة وأنا ببعت ${type} 😕 جرب تاني 🔄`, null, quoted);
        return null;
    }
};

const sendPoll = async (sock, chatId, title, options, quoted = null) => {
    try {
        const message = {
            poll: {
                name: title,
                values: options,
                selectableCount: 1
            }
        };

        return await sock.sendMessage(chatId, message, quoted ? { quoted } : {});
    } catch (error) {
        console.error(`❌ فشل إرسال الاستطلاع: ${error.message}`);
        await sendErrorMessage(sock, chatId, "⚠️ حصل مشكلة وأنا بعمل الاستطلاع 😕 جرب تاني 🔄", null, quoted);
        return null;
    }
};

const sendLocation = async (sock, chatId, latitude, longitude, name = '', address = '', quoted = null) => {
    try {
        const message = {
            location: {
                degreesLatitude: latitude,
                degreesLongitude: longitude,
                name: name,
                address: address
            }
        };

        return await sock.sendMessage(chatId, message, quoted ? { quoted } : {});
    } catch (error) {
        console.error(`❌ فشل إرسال الموقع: ${error.message}`);
        await sendErrorMessage(sock, chatId, "⚠️ حصل مشكلة وأنا ببعت الموقع 😕 جرب تاني 🔄", null, quoted);
        return null;
    }
};

const sendContact = async (sock, chatId, vcard, displayName, quoted = null) => {
    try {
        const message = {
            contacts: {
                displayName: displayName,
                contacts: [{ vcard }]
            }
        };

        return await sock.sendMessage(chatId, message, quoted ? { quoted } : {});
    } catch (error) {
        console.error(`❌ فشل إرسال جهة الاتصال: ${error.message}`);
        await sendErrorMessage(sock, chatId, "⚠️ حصل مشكلة وأنا ببعت جهة الاتصال 😕 جرب تاني 🔄", null, quoted);
        return null;
    }
};

const sendButtons = async (sock, chatId, text, footer = '', buttons = [], quoted = null) => {
    try {
        const message = {
            text: text,
            footer: footer || botSignature,
            buttons: buttons,
            headerType: 1
        };

        return await sock.sendMessage(chatId, message, quoted ? { quoted } : {});
    } catch (error) {
        console.error(`❌ فشل إرسال الأزرار: ${error.message}`);
        return await sendText(sock, chatId, `${text}\n\n${footer || botSignature}`, quoted);
    }
};

const sendQuickReplies = async (sock, chatId, text, quickReplies = [], quoted = null) => {
    try {
        const buttons = quickReplies.map((reply, index) => ({
            buttonId: `qr_${index}`,
            buttonText: { displayText: reply },
            type: 1
        }));

        return await sendButtons(sock, chatId, text, '', buttons, quoted);
    } catch (error) {
        console.error(`❌ فشل إرسال الردود السريعة: ${error.message}`);
        return await sendText(sock, chatId, text, quoted);
    }
};

const sendWithAd = async (sock, chatId, text, adInfo = {}, quoted = null) => {
    try {
        const customAd = {
            title: adInfo.title || externalAdTitle,
            body: adInfo.body || externalAdBody,
            mediaType: adInfo.mediaType || externalAdMediaType,
            thumbnail: adInfo.thumbnail || externalAdThumbnail,
            mediaUrl: adInfo.mediaUrl || mediaUrl,
            sourceUrl: adInfo.sourceUrl || sourceUrl
        };

        const message = {
            text,
            contextInfo: {
                forwardingScore: 999,
                isForwarded: true,
                externalAdReply: customAd
            }
        };

        return await sock.sendMessage(chatId, message, quoted ? { quoted } : {});
    } catch (error) {
        console.error(`❌ فشل إرسال الرسالة مع الإعلان: ${error.message}`);
        return await sendText(sock, chatId, text, quoted);
    }
};

module.exports = {
    sendErrorMessage,
    sendStickerCreationSuccessMessage,
    sendText,
    sendFormattedMessage,
    sendImage,
    sendMedia,
    sendPoll,
    sendLocation,
    sendContact,
    sendButtons,
    sendQuickReplies,
    sendWithAd,
    BOT_SIGNATURE: botSignature,
    createAdContext
};
