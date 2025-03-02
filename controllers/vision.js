const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');
const { sendFormattedMessage, sendErrorMessage } = require('./messageUtils');
const { downloadContentFromMessage } = require('@whiskeysockets/baileys');

// Initialize Google Cloud Vision API
const vision = google.vision({
    version: 'v1',
    auth: 'AIzaSyDGXCFF6aIa6NVXYwtnQ4aZSjtMNR8KLC0' // REPLACE WITH YOUR API KEY
});

const processedImages = new Set(); // Keep track of processed image paths

const processImage = async (sock, chatId, imagePath, quotedMessage) => {
    if (processedImages.has(imagePath)) {
        console.log(`[Image Processor] Image already processed: ${imagePath}`);
        return;
    }
    processedImages.add(imagePath);

    let statusMsg = await sock.sendMessage(chatId, {
        text: "*جاري تحليل الصورة... 🤖🔍*",
    }, { quoted: quotedMessage });

    try {
        const imageBuffer = fs.readFileSync(imagePath);
        const imageBase64 = imageBuffer.toString('base64');

        const request = {
            image: {
                content: imageBase64,
            },
            features: [
                { type: 'LABEL_DETECTION', maxResults: 5 },
                { type: 'TEXT_DETECTION' },
                { type: 'IMAGE_PROPERTIES' },
                { type: 'SAFE_SEARCH_DETECTION' },
                { type: 'WEB_DETECTION', maxResults: 3 }
            ],
        };

        const [result] = await vision.images.annotate({ requestBody: request });
        const labels = result.labelAnnotations;
        const texts = result.textAnnotations;
        const safeSearch = result.safeSearchAnnotation;
        const webEntities = result.webDetection && result.webDetection.webEntities;
        const imageProperties = result.imagePropertiesAnnotation;

        let analysisText = "*🤖 تحليل الصورة:*\n\n";

        if (labels && labels.length > 0) {
            analysisText += "✅ *العناصر الموجودة:* \n";
            labels.forEach(label => analysisText += `• ${label.description} (الثقة: ${(label.score * 100).toFixed(2)}%)\n`);
            analysisText += "\n";
        }

        if (texts && texts.length > 0) {
            analysisText += "📝 *النص الموجود في الصورة:*\n";
            analysisText += `"${texts[0].description}"\n\n`;
        }

        if (imageProperties && imageProperties.dominantColors && imageProperties.dominantColors.colors) {
            const colors = imageProperties.dominantColors.colors;
            analysisText += "🎨 *الألوان الرئيسية:*\n";
            colors.slice(0, 3).forEach(color => {
                const rgb = color.color;
                analysisText += `• R:${rgb.red}, G:${rgb.green}, B:${rgb.blue} (النسبة: ${(color.pixelFraction * 100).toFixed(2)}%)\n`;
            });
            analysisText += "\n";
        }

        if (webEntities && webEntities.length > 0) {
            analysisText += "🌐 *نتائج الويب ذات الصلة:* \n";
            webEntities.forEach(entity => {
                if (entity.description) {
                    analysisText += `• ${entity.description}\n`;
                }
            });
            analysisText += "\n";
        }

        if (safeSearch) {
            analysisText += "⚠️ *فحص المحتوى:* \n";
            analysisText += `• محتوى للبالغين: ${safeSearch.adult}\n`;
            analysisText += `• محتوى ساخر: ${safeSearch.spoof}\n`;
            analysisText += `• محتوى طبي: ${safeSearch.medical}\n`;
            analysisText += `• محتوى عنيف: ${safeSearch.violence}\n`;
            analysisText += `• محتوى إباحي: ${safeSearch.racy}\n\n`;
        }

        analysisText += "*شكراً لاستخدامك Zaky AI لتحليل الصور! 🤖*";

        await sock.sendMessage(chatId, { text: analysisText }, { quoted: quotedMessage, edit: statusMsg.key });

    } catch (error) {
        console.error('[Image Processor] Error analyzing image:', error);
        await sock.sendMessage(chatId, {
            text: "*❌ فشل تحليل الصورة.  فيه مشكلة في الاتصال بـ Google Cloud Vision أو في الصورة نفسها. حاول مرة تانية.*",
            edit: statusMsg.key
        }, { quoted: quotedMessage });

    } finally {
        fs.unlink(imagePath, (err) => {
            if (err) console.error(`[Image Processor] Error deleting file: ${err}`);
            else console.log(`[Image Processor] Temp file deleted: ${imagePath}`);
        });
    }
};

const handleImageMessage = async (sock, message) => {
    if (message.key.remoteJid === 'status@broadcast' || message.key.fromMe) {
        return;
    }

    const chatId = message.key.remoteJid;
    const quotedMessage = message;

    if (message.message?.imageMessage || message.message?.extendedTextMessage?.contextInfo?.quotedMessage?.imageMessage) {
        const imageMessage = message.message.imageMessage || message.message.extendedTextMessage.contextInfo.quotedMessage.imageMessage;

        const stream = await downloadContentFromMessage(imageMessage, 'image');
        let buffer = Buffer.from([]);  // <--  استخدم 'let'
        for await (const chunk of stream) {
            buffer = Buffer.concat([buffer, chunk]);
        }

        const imageId = Date.now() + Math.floor(Math.random() * 1000);
        const tempImagePath = path.join(__dirname, '..', 'temp', `image_${imageId}.jpg`);

        const tempDir = path.join(__dirname, '..', 'temp');
        if (!fs.existsSync(tempDir)) {
            fs.mkdirSync(tempDir, { recursive: true });
        }

        fs.writeFileSync(tempImagePath, buffer);
        await processImage(sock, chatId, tempImagePath, quotedMessage);
    }
};

module.exports = {
    handleImageMessage,
};
