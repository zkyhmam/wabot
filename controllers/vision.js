const fs = require('fs').promises;
const fsSync = require('fs');
const path = require('path');
const { google } = require('googleapis');
const { sendFormattedMessage, sendErrorMessage } = require('./messageUtils');
const { downloadContentFromMessage } = require('@whiskeysockets/baileys');
const ffmpeg = require('fluent-ffmpeg');

// Constants
const MAX_IMAGE_SIZE = 10 * 1024 * 1024; // 10MB
const MAX_RETRY_ATTEMPTS = 3;
const TEMP_DIR = path.join(__dirname, '..', 'temp');
const API_TIMEOUT = 30000; // 30 seconds
const SERVICE_ACCOUNT_FILE = path.join(__dirname, '..', 'config', 'serviceAccount.json'); // مسار ملف JSON

// Initialize Google Cloud Vision API with Service Account
let vision;
(async () => {
    try {
        const auth = new google.auth.GoogleAuth({
            keyFile: SERVICE_ACCOUNT_FILE,
            scopes: ['https://www.googleapis.com/auth/cloud-platform'],
        });
        const client = await auth.getClient();
        vision = google.vision({
            version: 'v1',
            auth: client,
        });
        console.log('[Image Processor] Google Vision API initialized successfully with service account');
    } catch (error) {
        console.error('[Image Processor] Failed to initialize Google Vision API with service account:', error);
    }
})();

// Cache management
const processedImages = new Set();
const processingQueue = new Map();
let cacheCleanupInterval;

/**
 * Initialize the module and set up required directories and intervals
 */
const initialize = async () => {
    try {
        await fs.mkdir(TEMP_DIR, { recursive: true });
        console.log(`[Image Processor] Temporary directory created at: ${TEMP_DIR}`);

        cacheCleanupInterval = setInterval(() => {
            cleanupCache();
        }, 3600000); // كل ساعة

        return true;
    } catch (error) {
        console.error('[Image Processor] Initialization failed:', error);
        return false;
    }
};

/**
 * Clean up processed image cache and remove old temporary files
 */
const cleanupCache = async () => {
    console.log('[Image Processor] Performing cache cleanup');
    
    if (processedImages.size > 1000) {
        processedImages.clear();
        console.log('[Image Processor] Cleared processed images cache due to size');
    }
    
    try {
        const files = await fs.readdir(TEMP_DIR);
        const currentTime = Date.now();
        
        for (const file of files) {
            const filePath = path.join(TEMP_DIR, file);
            const stats = await fs.stat(filePath);
            if (currentTime - stats.mtimeMs > 7200000) { // 2 ساعة
                await fs.unlink(filePath);
                console.log(`[Image Processor] Deleted old temporary file: ${filePath}`);
            }
        }
    } catch (error) {
        console.error('[Image Processor] Failed to clean up temporary files:', error);
    }
};

/**
 * Compress image using FFmpeg
 */
const compressImage = (inputPath, outputPath) => {
    return new Promise((resolve, reject) => {
        ffmpeg(inputPath)
            .outputOptions('-vf', 'scale=1024:-1')
            .outputOptions('-q:v', '5')
            .save(outputPath)
            .on('end', resolve)
            .on('error', (err) => reject(new Error(`FFmpeg error: ${err.message}`)));
    });
};

/**
 * Process an image using Google Cloud Vision API
 */
const processImage = async (sock, chatId, imagePath, quotedMessage, retryCount = 0) => {
    const imageKey = `${chatId}:${path.basename(imagePath)}`;
    if (processingQueue.has(imageKey)) return;

    processingQueue.set(imageKey, Date.now());
    processedImages.add(imagePath);

    let statusMsg;
    let compressedImagePath = path.join(TEMP_DIR, `compressed_${path.basename(imagePath)}`);
    
    try {
        statusMsg = await sock.sendMessage(chatId, { text: "*جاري تحليل الصورة... 🤖🔍*" }, { quoted: quotedMessage });

        // ضغط الصورة
        await compressImage(imagePath, compressedImagePath);
        const imageBuffer = await fs.readFile(compressedImagePath);

        const imageBase64 = imageBuffer.toString('base64');
        if (Buffer.byteLength(imageBase64) > MAX_IMAGE_SIZE) {
            throw new Error(`الصورة كبيرة جدًا (${(Buffer.byteLength(imageBase64) / 1024 / 1024).toFixed(2)} ميغابايت)`);
        }

        // إعداد طلب الـ API
        const request = {
            image: { content: imageBase64 },
            features: [
                { type: 'LABEL_DETECTION', maxResults: 5 },
                { type: 'TEXT_DETECTION' },
                { type: 'IMAGE_PROPERTIES' },
                { type: 'SAFE_SEARCH_DETECTION' },
                { type: 'WEB_DETECTION', maxResults: 3 }
            ],
        };

        // إرسال الطلب
        const [result] = await Promise.race([
            vision.images.annotate({ requestBody: { requests: [request] } }),
            new Promise((_, reject) => setTimeout(() => reject(new Error('انتهت مهلة الطلب')), API_TIMEOUT))
        ]);

        const response = result.responses[0];
        let analysisText = "*🤖 تحليل الصورة:*\n\n";

        if (response.labelAnnotations?.length) {
            analysisText += "✅ *العناصر الموجودة:*\n" + response.labelAnnotations.map(l => `• ${l.description} (${(l.score * 100).toFixed(2)}%)`).join('\n') + "\n\n";
        }
        if (response.textAnnotations?.length) {
            analysisText += "📝 *النص الموجود:*\n" + `"${response.textAnnotations[0].description}"\n\n`;
        }
        if (response.imagePropertiesAnnotation?.dominantColors?.colors) {
            analysisText += "🎨 *الألوان الرئيسية:*\n" + response.imagePropertiesAnnotation.dominantColors.colors.slice(0, 3)
                .map(c => `• R:${c.color.red}, G:${c.color.green}, B:${c.color.blue} (${(c.pixelFraction * 100).toFixed(2)}%)`).join('\n') + "\n\n";
        }
        if (response.webDetection?.webEntities?.length) {
            analysisText += "🌐 *نتائج الويب:*\n" + response.webDetection.webEntities.map(e => `• ${e.description}`).join('\n') + "\n\n";
        }
        if (response.safeSearchAnnotation) {
            analysisText += "⚠️ *فحص المحتوى:*\n" + 
                `• محتوى للبالغين: ${response.safeSearchAnnotation.adult}\n` +
                `• محتوى ساخر: ${response.safeSearchAnnotation.spoof}\n` +
                `• محتوى طبي: ${response.safeSearchAnnotation.medical}\n` +
                `• محتوى عنيف: ${response.safeSearchAnnotation.violence}\n` +
                `• محتوى إباحي: ${response.safeSearchAnnotation.racy}\n\n`;
        }

        analysisText += "*شكراً لاستخدامك Zaky AI! 🤖*";
        await sock.sendMessage(chatId, { text: analysisText }, { quoted: quotedMessage, edit: statusMsg.key });

    } catch (error) {
        if (retryCount < MAX_RETRY_ATTEMPTS - 1 && error.message.includes('timeout')) {
            processingQueue.delete(imageKey);
            return processImage(sock, chatId, imagePath, quotedMessage, retryCount + 1);
        }
        const errorMessage = `*❌ فشل تحليل الصورة:*\n*السبب:* ${error.message.includes('timeout') ? 'انتهت مهلة الطلب' : error.message}`;
        await sock.sendMessage(chatId, { text: errorMessage }, { quoted: quotedMessage, edit: statusMsg?.key });
        console.error('[Image Processor] Error:', error);
    } finally {
        processingQueue.delete(imageKey);
        await Promise.all([fs.unlink(imagePath).catch(() => {}), fs.unlink(compressedImagePath).catch(() => {})]);
    }
};

/**
 * Handle incoming image messages
 */
const handleImageMessage = async (sock, message) => {
    if (!message?.key || message.key.remoteJid === 'status@broadcast' || message.key.fromMe) return;

    const chatId = message.key.remoteJid;
    const quotedMessage = message;
    const imageMessage = message.message?.imageMessage || message.message?.extendedTextMessage?.contextInfo?.quotedMessage?.imageMessage;

    if (!imageMessage) return;

    const stream = await downloadContentFromMessage(imageMessage, 'image');
    let buffer = Buffer.from([]);
    for await (const chunk of stream) buffer = Buffer.concat([buffer, chunk]);

    const tempImagePath = path.join(TEMP_DIR, `image_${Date.now()}_${Math.random() * 1000}.jpg`);
    await fs.writeFile(tempImagePath, buffer);
    await processImage(sock, chatId, tempImagePath, quotedMessage);
};

/**
 * Shutdown and cleanup resources
 */
const shutdown = async () => {
    clearInterval(cacheCleanupInterval);
    processedImages.clear();
    processingQueue.clear();
    console.log('[Image Processor] Shutdown complete');
};

module.exports = { handleImageMessage, initialize, shutdown, processImage };
