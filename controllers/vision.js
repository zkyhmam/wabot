const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');
const { sendFormattedMessage, sendErrorMessage } = require('./messageUtils'); // Assuming you have this

// Initialize Google Cloud Vision API
const vision = google.vision({
    version: 'v1',
    auth: 'AIzaSyDGXCFF6aIa6NVXYwtnQ4aZSjtMNR8KLC0' // REPLACE WITH YOUR API KEY
});

const processedImages = new Set(); // Keep track of processed image paths


/**
 * Processes an image using Google Cloud Vision API and sends the analysis.
 * @param {object} sock - WebSocket connection.
 * @param {string} chatId - The chat ID.
 * @param {string} imagePath - Path to the image file.
 * @param {object} quotedMessage - The original message object (the image message).  Important for replying.
 */
const processImage = async (sock, chatId, imagePath, quotedMessage) => {

    // Prevent duplicate processing.  Crucial for "on message" events.
    if (processedImages.has(imagePath)) {
        console.log(`[Image Processor] Image already processed: ${imagePath}`);
        return;
    }
    processedImages.add(imagePath);


    let statusMsg = await sock.sendMessage(chatId, {
        text: "*جاري تحليل الصورة... 🤖🔍*",
    }, { quoted: quotedMessage }); // Reply to the image message


    try {
        const imageBuffer = fs.readFileSync(imagePath);
        const imageBase64 = imageBuffer.toString('base64');

        const request = {
            image: {
                content: imageBase64,
            },
            features: [
                { type: 'LABEL_DETECTION', maxResults: 5 },     // Find labels/objects
                { type: 'TEXT_DETECTION' },                 // Detect text (OCR)
                { type: 'IMAGE_PROPERTIES' },               // Dominant colors, etc.
                { type: 'SAFE_SEARCH_DETECTION' },          // Check for inappropriate content
                { type: 'WEB_DETECTION', maxResults: 3 }       // Find similar images online
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
            analysisText += `"${texts[0].description}"\n\n`; // texts[0] usually contains the full detected text
        }
		
		if (imageProperties && imageProperties.dominantColors && imageProperties.dominantColors.colors) {
			const colors = imageProperties.dominantColors.colors;
			analysisText += "🎨 *الألوان الرئيسية:*\n";
			colors.slice(0, 3).forEach(color => { // Limit to top 3 colors for brevity
				const rgb = color.color;
				analysisText += `• R:${rgb.red}, G:${rgb.green}, B:${rgb.blue} (النسبة: ${(color.pixelFraction * 100).toFixed(2)}%)\n`;
			});
			analysisText += "\n";
		}

        if (webEntities && webEntities.length > 0) {
            analysisText += "🌐 *نتائج الويب ذات الصلة:* \n";
            webEntities.forEach(entity => {
                if (entity.description) { // Check for description to avoid empty entries.
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
         // Clean up:  Delete the temporary image file.  *VERY IMPORTANT*
        fs.unlink(imagePath, (err) => {
            if (err) console.error(`[Image Processor] Error deleting file: ${err}`);
            else console.log(`[Image Processor] Temp file deleted: ${imagePath}`);
        });
    }
};



/**
 * Handles incoming image messages.  This is the main entry point.
 * @param {object} sock - The WebSocket connection.
 * @param {object} message - The incoming message object.
 */
const handleImageMessage = async (sock, message) => {
    // Check if the message is an image and not from the bot itself
    if (message.key.remoteJid === 'status@broadcast' || message.key.fromMe) { // Crucial check!
        return;
    }

    const chatId = message.key.remoteJid;
    const quotedMessage = message; // Use the entire message as the quoted message

	if (message.message?.imageMessage || message.message?.extendedTextMessage?.contextInfo?.quotedMessage?.imageMessage) {
	    // Check for direct image message OR quoted image message
	    const imageMessage = message.message.imageMessage || message.message.extendedTextMessage.contextInfo.quotedMessage.imageMessage;

	    // Download the image
	    const stream = await downloadContentFromMessage(imageMessage, 'image'); // Use Baileys function
	    const buffer = Buffer.from([]);
	    for await (const chunk of stream) {
	        buffer = Buffer.concat([buffer, chunk]);
	    }

	    const imageId = Date.now() + Math.floor(Math.random() * 1000); // Unique ID
	    const tempImagePath = path.join(__dirname, '..', 'temp', `image_${imageId}.jpg`); // Save to a 'temp' folder

	    // Ensure the 'temp' directory exists
	    const tempDir = path.join(__dirname, '..', 'temp');
	    if (!fs.existsSync(tempDir)) {
	        fs.mkdirSync(tempDir, { recursive: true });
	    }

	    fs.writeFileSync(tempImagePath, buffer); // Save the image

	    // Process the downloaded image
	    await processImage(sock, chatId, tempImagePath, quotedMessage);
	}
};


module.exports = {
    handleImageMessage,
    // processImage  // No need to export processImage, it's called internally
};
