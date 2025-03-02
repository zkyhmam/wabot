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
        auth: process.env.GOOGLE_VISION_API_KEY || 'AIzaSyDGXCFF6aIa6NVXYwtnQ4aZSjtMNR8KLC0' // Always better to use environment variables
    });
} catch (error) {
    console.error('[Image Processor] Failed to initialize Google Vision API:', error);
    // Continue execution, we'll handle this during actual API calls
}

// Cache management
const processedImages = new Set(); // Keep track of processed image paths
const processingQueue = new Map(); // Track images currently being processed
let cacheCleanupInterval;

/**
 * Initialize the module and set up required directories and intervals
 */
const initialize = async () => {
    try {
        // Ensure temp directory exists
        try {
            await fs.mkdir(TEMP_DIR, { recursive: true });
            console.log(`[Image Processor] Temporary directory created at: ${TEMP_DIR}`);
        } catch (dirError) {
            console.error(`[Image Processor] Failed to create temporary directory: ${dirError.message}`);
            throw new Error('Failed to initialize temporary directory');
        }

        // Set up cache cleanup interval
        cacheCleanupInterval = setInterval(() => {
            try {
                cleanupCache();
            } catch (error) {
                console.error('[Image Processor] Error during cache cleanup:', error);
            }
        }, 3600000); // Clean up cache every hour

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
    
    // Clear processed images older than 1 hour
    if (processedImages.size > 1000) {
        processedImages.clear();
        console.log('[Image Processor] Cleared processed images cache due to size');
    }
    
    // Delete old temporary files
    try {
        const files = await fs.readdir(TEMP_DIR);
        const currentTime = Date.now();
        
        for (const file of files) {
            try {
                const filePath = path.join(TEMP_DIR, file);
                const stats = await fs.stat(filePath);
                const fileAge = currentTime - stats.mtimeMs;
                
                // Delete files older than 2 hours
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
    // Check if already being processed to prevent duplicate processing
    const imageKey = `${chatId}:${path.basename(imagePath)}`;
    if (processingQueue.has(imageKey)) {
        console.log(`[Image Processor] Image already being processed: ${imagePath}`);
        return;
    }
    
    // Check if already processed to prevent duplicate analysis
    if (processedImages.has(imagePath)) {
        console.log(`[Image Processor] Image already processed: ${imagePath}`);
        return;
    }
    
    // Mark as being processed
    processingQueue.set(imageKey, Date.now());
    processedImages.add(imagePath);
    
    let statusMsg;
    let imageBuffer;
    
    try {
        // Send initial status message
        try {
            statusMsg = await sock.sendMessage(chatId, {
                text: "*جاري تحليل الصورة... 🤖🔍*",
            }, { quoted: quotedMessage });
        } catch (msgError) {
            console.error('[Image Processor] Failed to send status message:', msgError);
            // Continue processing even if status message fails
        }
        
        // Validate image file exists
        try {
            await fs.access(imagePath);
        } catch (accessError) {
            throw new Error(`Image file not accessible: ${accessError.message}`);
        }
        
        // Read image file
        try {
            imageBuffer = await fs.readFile(imagePath);
        } catch (readError) {
            throw new Error(`Failed to read image file: ${readError.message}`);
        }
        
        // Validate image size
        if (imageBuffer.length > MAX_IMAGE_SIZE) {
            throw new Error('Image exceeds maximum size limit of 10MB');
        }
        
        // Validate image format (basic check)
        const magicNumbers = {
            jpeg: [0xFF, 0xD8, 0xFF],
            png: [0x89, 0x50, 0x4E, 0x47],
            gif: [0x47, 0x49, 0x46, 0x38]
        };
        
        let validFormat = false;
        for (const [format, numbers] of Object.entries(magicNumbers)) {
            if (numbers.every((val, i) => imageBuffer[i] === val)) {
                validFormat = true;
                break;
            }
        }
        
        if (!validFormat) {
            throw new Error('Unsupported image format. Please use JPEG, PNG, or GIF.');
        }
        
        // Convert image to base64
        const imageBase64 = imageBuffer.toString('base64');
        
        // Prepare API request with error handling
        if (!vision) {
            throw new Error('Google Vision API not initialized properly');
        }
        
        // Configure request
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
        
        // Set up timeout promise
        const timeoutPromise = new Promise((_, reject) => {
            setTimeout(() => reject(new Error('API request timed out')), API_TIMEOUT);
        });
        
        // Make API request with timeout
        const [result] = await Promise.race([
            vision.images.annotate({ request: request }),
            timeoutPromise
        ]);
        
        // Safety check for API response
        if (!result || !result.responses || !result.responses[0]) {
            throw new Error('Invalid API response structure');
        }
        
        const response = result.responses[0];
        
        // Extract data with error handling for each feature
        let labels, texts, safeSearch, webEntities, imageProperties;
        
        try {
            labels = response.labelAnnotations || [];
        } catch (error) {
            console.warn('[Image Processor] Error extracting labels:', error);
            labels = [];
        }
        
        try {
            texts = response.textAnnotations || [];
        } catch (error) {
            console.warn('[Image Processor] Error extracting texts:', error);
            texts = [];
        }
        
        try {
            safeSearch = response.safeSearchAnnotation || {};
        } catch (error) {
            console.warn('[Image Processor] Error extracting safe search data:', error);
            safeSearch = {};
        }
        
        try {
            webEntities = response.webDetection?.webEntities || [];
        } catch (error) {
            console.warn('[Image Processor] Error extracting web entities:', error);
            webEntities = [];
        }
        
        try {
            imageProperties = response.imagePropertiesAnnotation || {};
        } catch (error) {
            console.warn('[Image Processor] Error extracting image properties:', error);
            imageProperties = {};
        }
        
        // Build analysis text
        let analysisText = "*🤖 تحليل الصورة:*\n\n";
        
        if (labels && labels.length > 0) {
            analysisText += "✅ *العناصر الموجودة:* \n";
            try {
                labels.forEach(label => {
                    if (label && label.description) {
                        const confidence = label.score ? (label.score * 100).toFixed(2) : "غير معروف";
                        analysisText += `• ${label.description} (الثقة: ${confidence}%)\n`;
                    }
                });
            } catch (error) {
                console.warn('[Image Processor] Error formatting labels:', error);
                analysisText += "• حدث خطأ في معالجة البيانات\n";
            }
            analysisText += "\n";
        }
        
        if (texts && texts.length > 0) {
            analysisText += "📝 *النص الموجود في الصورة:*\n";
            try {
                if (texts[0] && texts[0].description) {
                    analysisText += `"${texts[0].description}"\n\n`;
                } else {
                    analysisText += "• لم يتم العثور على نص واضح\n\n";
                }
            } catch (error) {
                console.warn('[Image Processor] Error formatting text:', error);
                analysisText += "• حدث خطأ في معالجة النص\n\n";
            }
        }
        
        if (imageProperties?.dominantColors?.colors) {
            analysisText += "🎨 *الألوان الرئيسية:*\n";
            try {
                const colors = imageProperties.dominantColors.colors;
                colors.slice(0, 3).forEach(color => {
                    const rgb = color.color || { red: 0, green: 0, blue: 0 };
                    const fraction = color.pixelFraction ? (color.pixelFraction * 100).toFixed(2) : "0.00";
                    analysisText += `• R:${rgb.red || 0}, G:${rgb.green || 0}, B:${rgb.blue || 0} (النسبة: ${fraction}%)\n`;
                });
            } catch (error) {
                console.warn('[Image Processor] Error formatting colors:', error);
                analysisText += "• حدث خطأ في معالجة بيانات الألوان\n";
            }
            analysisText += "\n";
        }
        
        if (webEntities && webEntities.length > 0) {
            analysisText += "🌐 *نتائج الويب ذات الصلة:* \n";
            try {
                webEntities.forEach(entity => {
                    if (entity && entity.description) {
                        analysisText += `• ${entity.description}\n`;
                    }
                });
            } catch (error) {
                console.warn('[Image Processor] Error formatting web entities:', error);
                analysisText += "• حدث خطأ في معالجة بيانات الويب\n";
            }
            analysisText += "\n";
        }
        
        if (safeSearch) {
            analysisText += "⚠️ *فحص المحتوى:* \n";
            try {
                analysisText += `• محتوى للبالغين: ${safeSearch.adult || 'غير معروف'}\n`;
                analysisText += `• محتوى ساخر: ${safeSearch.spoof || 'غير معروف'}\n`;
                analysisText += `• محتوى طبي: ${safeSearch.medical || 'غير معروف'}\n`;
                analysisText += `• محتوى عنيف: ${safeSearch.violence || 'غير معروف'}\n`;
                analysisText += `• محتوى إباحي: ${safeSearch.racy || 'غير معروف'}\n\n`;
            } catch (error) {
                console.warn('[Image Processor] Error formatting safe search data:', error);
                analysisText += "• حدث خطأ في معالجة بيانات الأمان\n\n";
            }
        }
        
        analysisText += "*شكراً لاستخدامك Zaky AI لتحليل الصور! 🤖*";
        
        // Send analysis message
        try {
            if (statusMsg && statusMsg.key) {
                await sock.sendMessage(chatId, { text: analysisText }, { quoted: quotedMessage, edit: statusMsg.key });
            } else {
                await sock.sendMessage(chatId, { text: analysisText }, { quoted: quotedMessage });
            }
            console.log(`[Image Processor] Successfully analyzed and sent results for: ${imagePath}`);
        } catch (sendError) {
            console.error('[Image Processor] Failed to send analysis message:', sendError);
            throw new Error(`Failed to send analysis message: ${sendError.message}`);
        }
        
    } catch (error) {
        console.error(`[Image Processor] Error analyzing image (attempt ${retryCount + 1}/${MAX_RETRY_ATTEMPTS}):`, error);
        
        // Retry logic
        if (retryCount < MAX_RETRY_ATTEMPTS - 1) {
            console.log(`[Image Processor] Retrying image analysis (${retryCount + 1}/${MAX_RETRY_ATTEMPTS})...`);
            processingQueue.delete(imageKey);
            return processImage(sock, chatId, imagePath, quotedMessage, retryCount + 1);
        }
        
        // Send error message on final failure
        try {
            const errorMessage = "*❌ فشل تحليل الصورة.*\n" +
                                 `*السبب:* ${error.message || 'خطأ غير معروف'}\n` +
                                 "*حاول مرة أخرى أو تأكد من صحة الصورة المرسلة.*";
            
            if (statusMsg && statusMsg.key) {
                await sock.sendMessage(chatId, { text: errorMessage }, { quoted: quotedMessage, edit: statusMsg.key });
            } else {
                await sock.sendMessage(chatId, { text: errorMessage }, { quoted: quotedMessage });
            }
        } catch (sendError) {
            console.error('[Image Processor] Failed to send error message:', sendError);
        }
    } finally {
        // Clean up resources
        processingQueue.delete(imageKey);
        
        // Delete temporary file
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
        // Skip status updates and own messages
        if (message.key.remoteJid === 'status@broadcast' || message.key.fromMe) {
            return;
        }
        
        const chatId = message.key.remoteJid;
        if (!chatId) {
            console.error('[Image Processor] Invalid chat ID');
            return;
        }
        
        const quotedMessage = message;
        
        // Extract image message with error handling
        let imageMessage;
        try {
            if (message.message?.imageMessage) {
                imageMessage = message.message.imageMessage;
            } else if (message.message?.extendedTextMessage?.contextInfo?.quotedMessage?.imageMessage) {
                imageMessage = message.message.extendedTextMessage.contextInfo.quotedMessage.imageMessage;
            } else {
                // Not an image message
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
        
        // Download image content
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
        
        // Generate unique temporary file path
        const imageId = Date.now() + Math.floor(Math.random() * 1000);
        const tempImagePath = path.join(TEMP_DIR, `image_${imageId}.jpg`);
        
        // Write to file
        try {
            // Ensure temp directory exists
            if (!fsSync.existsSync(TEMP_DIR)) {
                await fs.mkdir(TEMP_DIR, { recursive: true });
            }
            
            await fs.writeFile(tempImagePath, buffer);
        } catch (writeError) {
            console.error('[Image Processor] Error writing temp file:', writeError);
            await sendErrorMessage(sock, chatId, 'فشل حفظ الصورة للمعالجة. حاول مرة أخرى.', quotedMessage);
            return;
        }
        
        // Process the image
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
        
        // Clean up any resources
        processedImages.clear();
        processingQueue.clear();
        
        // Delete all temporary files
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
    processImage, // Exported for testing purposes
};
