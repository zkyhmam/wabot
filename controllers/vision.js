const fs = require('fs').promises;
const fsSync = require('fs');
const path = require('path');
const { google } = require('googleapis');
const { sendFormattedMessage, sendErrorMessage } = require('./messageUtils');
const { downloadContentFromMessage } = require('@whiskeysockets/baileys');

// Constants
const MAX_IMAGE_SIZE = 10 * 1024 * 1024; // 10MB
const MAX_RETRY_ATTEMPTS = 3;
const TEMP_DIR = path.join(__dirname, '..', 'temp');
const API_TIMEOUT = 30000; // 30 seconds

// Initialize Google Cloud Vision API
let vision;
try {
    vision = google.vision({
        version: 'v1',
        auth: process.env.GOOGLE_VISION_API_KEY || 'AIzaSyDGXCFF6aIa6NVXYwtnQ4aZSjtMNR8KLC0'
    });
} catch (error) {
    console.error('[Image Processor] Failed to initialize Google Vision API:', error);
}

// Cache management
const processedImages = new Set();
const processingQueue = new Map();
let cacheCleanupInterval;

/**
 * Initialize the module and set up required directories and intervals
 */
const initialize = async () => {
    try {
        try {
            await fs.mkdir(TEMP_DIR, { recursive: true });
            console.log(`[Image Processor] Temporary directory created at: ${TEMP_DIR}`);
        } catch (dirError) {
            console.error(`[Image Processor] Failed to create temporary directory: ${dirError.message}`);
            throw new Error('Failed to initialize temporary directory');
        }

        cacheCleanupInterval = setInterval(() => {
            try {
                cleanupCache();
            } catch (error) {
                console.error('[Image Processor] Error during cache cleanup:', error);
            }
        }, 3600000);

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
            try {
                const filePath = path.join(TEMP_DIR, file);
                const stats = await fs.stat(filePath);
                const fileAge = currentTime - stats.mtimeMs;
                
                if (fileAge > 7200000) {
                    await fs.unlink(filePath);
                    console.log(`[Image Processor] Deleted old temporary file: ${filePath}`);
                }
            } catch (fileError) {
                console.error(`[Image Processor] Error processing file during cleanup: ${fileError.message}`);
            }
        }
    } catch (error) {
        console.error('[Image Processor] Failed to clean up temporary files:', error);
    }
};

/**
 * Process an image using Google Cloud Vision API
 * @param {Object} sock - Socket connection object
 * @param {String} chatId - Chat ID
 * @param {String} imagePath - Path to the image file
 * @param {Object} quotedMessage - Message to quote in the response
 * @param {Number} retryCount - Current retry attempt count
 */
const processImage = async (sock, chatId, imagePath, quotedMessage, retryCount = 0) => {
    const imageKey = `${chatId}:${path.basename(imagePath)}`;
    if (processingQueue.has(imageKey)) {
        console.log(`[Image Processor] Image already being processed: ${imagePath}`);
        return;
    }
    
    if (processedImages.has(imagePath)) {
        console.log(`[Image Processor] Image already processed: ${imagePath}`);
        return;
    }
    
    processingQueue.set(imageKey, Date.now());
    processedImages.add(imagePath);
    
    let statusMsg;
    let imageBuffer;
    
    try {
        statusMsg = await sock.sendMessage(chatId, {
            text: "*جاري تحليل الصورة... 🤖🔍*",
        }, { quoted: quotedMessage });
        
        await fs.access(imagePath);
        imageBuffer = await fs.readFile(imagePath);
        
        if (imageBuffer.length > MAX_IMAGE_SIZE) {
            throw new Error('Image exceeds maximum size limit of 10MB');
        }
        
        // تحويل الصورة إلى base64 والتحقق من حجمها
        const imageBase64 = imageBuffer.toString('base64');
        const base64Size = Buffer.byteLength(imageBase64);
        if (base64Size > MAX_IMAGE_SIZE) {
            throw new Error(`Encoded image exceeds maximum size limit of 10MB (size: ${(base64Size / 1024 / 1024).toFixed(2)}MB)`);
        }
        
        // إعداد الطلب إلى API
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
        
        // إرسال الطلب مع تحديد مهلة زمنية
        const [result] = await Promise.race([
            vision.images.annotate({ request: request }),
            new Promise((_, reject) => setTimeout(() => reject(new Error('API request timed out')), API_TIMEOUT))
        ]);
        
        const response = result.responses[0];
        
        // استخراج البيانات مع معالجة الأخطاء
        const labels = response.labelAnnotations || [];
        const texts = response.textAnnotations || [];
        const safeSearch = response.safeSearchAnnotation || {};
        const webEntities = response.webDetection?.webEntities || [];
        const imageProperties = response.imagePropertiesAnnotation || {};
        
        // بناء نص التحليل
        let analysisText = "*🤖 تحليل الصورة:*\n\n";
        
        if (labels.length > 0) {
            analysisText += "✅ *العناصر الموجودة:* \n";
            labels.forEach(label => {
                const confidence = label.score ? (label.score * 100).toFixed(2) : "غير معروف";
                analysisText += `• ${label.description} (الثقة: ${confidence}%)\n`;
            });
            analysisText += "\n";
        }
        
        if (texts.length > 0) {
            analysisText += "📝 *النص الموجود في الصورة:*\n";
            if (texts[0].description) {
                analysisText += `"${texts[0].description}"\n\n`;
            } else {
                analysisText += "• لم يتم العثور على نص واضح\n\n";
            }
        }
        
        if (imageProperties.dominantColors?.colors) {
            analysisText += "🎨 *الألوان الرئيسية:*\n";
            const colors = imageProperties.dominantColors.colors.slice(0, 3);
            colors.forEach(color => {
                const rgb = color.color || { red: 0, green: 0, blue: 0 };
                const fraction = color.pixelFraction ? (color.pixelFraction * 100).toFixed(2) : "0.00";
                analysisText += `• R:${rgb.red}, G:${rgb.green}, B:${rgb.blue} (النسبة: ${fraction}%)\n`;
            });
            analysisText += "\n";
        }
        
        if (webEntities.length > 0) {
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
            analysisText += `• محتوى للبالغين: ${safeSearch.adult || 'غير معروف'}\n`;
            analysisText += `• محتوى ساخر: ${safeSearch.spoof || 'غير معروف'}\n`;
            analysisText += `• محتوى طبي: ${safeSearch.medical || 'غير معروف'}\n`;
            analysisText += `• محتوى عنيف: ${safeSearch.violence || 'غير معروف'}\n`;
            analysisText += `• محتوى إباحي: ${safeSearch.racy || 'غير معروف'}\n\n`;
        }
        
        analysisText += "*شكراً لاستخدامك Zaky AI لتحليل الصور! 🤖*";
        
        // إرسال نص التحليل
        if (statusMsg && statusMsg.key) {
            await sock.sendMessage(chatId, { text: analysisText }, { quoted: quotedMessage, edit: statusMsg.key });
        } else {
            await sock.sendMessage(chatId, { text: analysisText }, { quoted: quotedMessage });
        }
        console.log(`[Image Processor] Successfully analyzed and sent results for: ${imagePath}`);
        
    } catch (error) {
        console.error(`[Image Processor] Error analyzing image (attempt ${retryCount + 1}/${MAX_RETRY_ATTEMPTS}):`, error);
        
        // إعادة المحاولة في حالة أخطاء محددة
        if (retryCount < MAX_RETRY_ATTEMPTS - 1 && (error.message.includes('timeout') || error.response?.status === 500)) {
            console.log(`[Image Processor] Retrying image analysis (${retryCount + 1}/${MAX_RETRY_ATTEMPTS})...`);
            processingQueue.delete(imageKey);
            return processImage(sock, chatId, imagePath, quotedMessage, retryCount + 1);
        }
        
        // إرسال رسالة خطأ للمستخدم عند فشل جميع المحاولات
        let errorMessage = "*❌ فشل تحليل الصورة.*\n";
        if (error.message.includes('Encoded image exceeds maximum size')) {
            errorMessage += "*السبب:* الصورة كبيرة جدًا بعد التشفير. حاول إرسال صورة أصغر.\n";
        } else if (error.message.includes('API request timed out')) {
            errorMessage += "*السبب:* انتهت مهلة الطلب. حاول مرة أخرى لاحقًا.\n";
        } else if (error.response && error.response.status === 413) {
            errorMessage += "*السبب:* الطلب كبير جدًا. حاول إرسال صورة أصغر.\n";
        } else {
            errorMessage += "*السبب:* خطأ غير معروف. حاول مرة أخرى أو تأكد من صحة الصورة المرسلة.\n";
        }
        
        if (statusMsg && statusMsg.key) {
            await sock.sendMessage(chatId, { text: errorMessage }, { quoted: quotedMessage, edit: statusMsg.key });
        } else {
            await sock.sendMessage(chatId, { text: errorMessage }, { quoted: quotedMessage });
        }
        
        // تسجيل الخطأ في الكونسول بشكل مختصر
        console.error(`[Image Processor] Final error after ${MAX_RETRY_ATTEMPTS} attempts:`, {
            message: error.message,
            stack: error.stack.slice(0, 200),
            responseStatus: error.response?.status,
            responseData: error.response?.data?.slice(0, 200),
        });
    } finally {
        processingQueue.delete(imageKey);
        try {
            await fs.unlink(imagePath);
            console.log(`[Image Processor] Temp file deleted: ${imagePath}`);
        } catch (unlinkError) {
            console.error(`[Image Processor] Error deleting temp file: ${unlinkError}`);
        }
    }
};

/**
 * Handle incoming image messages
 * @param {Object} sock - Socket connection object
 * @param {Object} message - Message object
 */
const handleImageMessage = async (sock, message) => {
    if (!message || !message.key) {
        console.error('[Image Processor] Invalid message object');
        return;
    }
    
    try {
        if (message.key.remoteJid === 'status@broadcast' || message.key.fromMe) {
            return;
        }
        
        const chatId = message.key.remoteJid;
        if (!chatId) {
            console.error('[Image Processor] Invalid chat ID');
            return;
        }
        
        const quotedMessage = message;
        
        let imageMessage;
        try {
            if (message.message?.imageMessage) {
                imageMessage = message.message.imageMessage;
            } else if (message.message?.extendedTextMessage?.contextInfo?.quotedMessage?.imageMessage) {
                imageMessage = message.message.extendedTextMessage.contextInfo.quotedMessage.imageMessage;
            } else {
                return;
            }
        } catch (error) {
            console.error('[Image Processor] Error extracting image message:', error);
            return;
        }
        
        if (!imageMessage) {
            console.error('[Image Processor] No image message found');
            return;
        }
        
        let buffer;
        try {
            const stream = await downloadContentFromMessage(imageMessage, 'image');
            if (!stream) {
                throw new Error('Failed to get download stream');
            }
            
            buffer = Buffer.from([]);
            for await (const chunk of stream) {
                buffer = Buffer.concat([buffer, chunk]);
            }
        } catch (downloadError) {
            console.error('[Image Processor] Error downloading image:', downloadError);
            await sendErrorMessage(sock, chatId, 'فشل تحميل الصورة. حاول مرة أخرى.', quotedMessage);
            return;
        }
        
        if (!buffer || buffer.length === 0) {
            console.error('[Image Processor] Empty buffer after download');
            await sendErrorMessage(sock, chatId, 'الصورة فارغة أو تالفة. حاول مرة أخرى.', quotedMessage);
            return;
        }
        
        const imageId = Date.now() + Math.floor(Math.random() * 1000);
        const tempImagePath = path.join(TEMP_DIR, `image_${imageId}.jpg`);
        
        try {
            if (!fsSync.existsSync(TEMP_DIR)) {
                await fs.mkdir(TEMP_DIR, { recursive: true });
            }
            
            await fs.writeFile(tempImagePath, buffer);
        } catch (writeError) {
            console.error('[Image Processor] Error writing temp file:', writeError);
            await sendErrorMessage(sock, chatId, 'فشل حفظ الصورة للمعالجة. حاول مرة أخرى.', quotedMessage);
            return;
        }
        
        await processImage(sock, chatId, tempImagePath, quotedMessage);
        
    } catch (error) {
        console.error('[Image Processor] Unexpected error in handleImageMessage:', error);
        try {
            if (message && message.key && message.key.remoteJid) {
                await sendErrorMessage(
                    sock, 
                    message.key.remoteJid, 
                    'حدث خطأ غير متوقع أثناء معالجة الصورة. حاول مرة أخرى لاحقاً.', 
                    message
                );
            }
        } catch (sendError) {
            console.error('[Image Processor] Failed to send error message:', sendError);
        }
    }
};

/**
 * Shutdown and cleanup resources
 */
const shutdown = async () => {
    try {
        if (cacheCleanupInterval) {
            clearInterval(cacheCleanupInterval);
        }
        
        processedImages.clear();
        processingQueue.clear();
        
        try {
            const files = await fs.readdir(TEMP_DIR);
            for (const file of files) {
                try {
                    await fs.unlink(path.join(TEMP_DIR, file));
                } catch (unlinkError) {
                    console.error(`[Image Processor] Error deleting file during shutdown: ${unlinkError.message}`);
                }
            }
        } catch (readError) {
            console.error(`[Image Processor] Error reading temp directory during shutdown: ${readError.message}`);
        }
        
        console.log('[Image Processor] Shutdown complete');
        return true;
    } catch (error) {
        console.error('[Image Processor] Error during shutdown:', error);
        return false;
    }
};

module.exports = {
    handleImageMessage,
    initialize,
    shutdown,
    processImage,
};
