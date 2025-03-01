const { GoogleGenerativeAI } = require("@google/generative-ai");

const geminiApiKeys = [
    "AIzaSyC-3PFCoASRS8WpppTtbqsR599R9GdrS_I",
    "AIzaSyC-3PFCoASRS8WpppTtbqsR599R9GdrS_I",
    "AIzaSyC-3PFCoASRS8WpppTtbqsR599R9GdrS_I",
    "AIzaSyC-3PFCoASRS8WpppTtbqsR599R9GdrS_I",
    "AIzaSyC-3PFCoASRS8WpppTtbqsR599R9GdrS_I",
    "AIzaSyC-3PFCoASRS8WpppTtbqsR599R9GdrS_I",
    "AIzaSyC-3PFCoASRS8WpppTtbqsR599R9GdrS_I",
    "AIzaSyC-3PFCoASRS8WpppTtbqsR599R9GdrS_I",
    "AIzaSyC-3PFCoASRS8WpppTtbqsR599R9GdrS_I"
];
let currentApiKeyIndex = 0;

function getNextApiKey() {
    if (geminiApiKeys.length === 0) throw new Error("No Gemini API keys provided.");
    const apiKey = geminiApiKeys[currentApiKeyIndex];
    currentApiKeyIndex = (currentApiKeyIndex + 1) % geminiApiKeys.length;
    return apiKey;
}

async function callGemini(prompt, retryCount = 0) {
    const maxRetries = geminiApiKeys.length;
    const geminiApiKey = getNextApiKey();
    const genAI = new GoogleGenerativeAI(geminiApiKey);
    const model = genAI.getGenerativeModel({ model: "gemini-1.5-pro" });

    try {
        const result = await model.generateContent({
            contents: [{ role: "user", parts: [{ text: prompt }] }],
        });
        let response = result.response.text();

        const jsonMatch = response.match(/`json\s*([\s\S]*?)\s*`/) || response.match(/`python\s*([\s\S]*?)\s*`/) || response.match(/{[\s\S]*}/) || [null, response];
        response = jsonMatch[1] || jsonMatch[0] || response;

        try {
            return JSON.parse(response);
        } catch (e) {
            console.warn("Gemini response is not valid JSON, returning raw text:", response);
            return response;
        }
    } catch (error) {
        console.error("Gemini Error:", error);
        if ((error.message.includes("503 Service Unavailable") || error.message.includes("500 Internal Server Error")) && retryCount < maxRetries) {
            const delay = (retryCount + 1) * 1000;
            console.warn(`Gemini is overloaded. Retrying with delay ${delay}ms (attempt ${retryCount + 1}/${maxRetries}).`);
            await new Promise(resolve => setTimeout(resolve, delay));
            return await callGemini(prompt, retryCount + 1);
        }
        console.error("Gemini Failed after retries:", error);
        throw error;
    }
}

/**
 * دالة لتوليد استجابة من Gemini API
 * @param {string} prompt - النص المُدخل للحصول على استجابة
 * @param {number} retryCount - عدد محاولات إعادة المحاولة في حالة الفشل
 * @returns {Promise<string>} - النص الناتج من الاستجابة
 */
async function generateResponse(prompt, retryCount = 0) {
    const maxRetries = geminiApiKeys.length;
    const geminiApiKey = getNextApiKey();
    const genAI = new GoogleGenerativeAI(geminiApiKey);
    const model = genAI.getGenerativeModel({ model: "gemini-1.5-pro" });

    try {
        const result = await model.generateContent({
            contents: [{ role: "user", parts: [{ text: prompt }] }],
        });
        return result.response.text();
    } catch (error) {
        console.error("Gemini Error in generateResponse:", error);
        if ((error.message.includes("503 Service Unavailable") || error.message.includes("500 Internal Server Error")) && retryCount < maxRetries) {
            const delay = (retryCount + 1) * 1000;
            console.warn(`Gemini is overloaded. Retrying with delay ${delay}ms (attempt ${retryCount + 1}/${maxRetries}).`);
            await new Promise(resolve => setTimeout(resolve, delay));
            return await generateResponse(prompt, retryCount + 1);
        }
        console.error("Gemini Failed after retries:", error);
        throw error;
    }
}

/**
 * تصحيح اسم الفيلم أو المسلسل باستخدام Gemini API
 * @param {string} movieTitle - اسم الفيلم أو المسلسل المدخل
 * @returns {Promise<string>} - اسم الفيلم أو المسلسل المصحح
 */
async function correctMovieTitle(movieTitle) {
    try {
        // إذا كان النص فارغًا، قم بإرجاعه كما هو
        if (!movieTitle || movieTitle.trim() === '') {
            return movieTitle;
        }

        // استخدام generateResponse الموجودة مسبقًا لإصلاح اسم الفيلم
        const prompt = `
Correct or standardize this movie or TV show title. If it's in Arabic, keep it as it is. 
Just return the corrected title without any explanation or additional text.

Title: ${movieTitle}`;

        const correctedTitle = await generateResponse(prompt);
        
        // في حالة أي شيء غير متوقع، أعد الاسم الأصلي
        if (!correctedTitle || correctedTitle.includes("SAFETY")) {
            return movieTitle;
        }
        
        // إزالة أي علامات اقتباس وأقواس وترميز HTML في الاستجابة
        return correctedTitle
            .trim()
            .replace(/^["'"\s]+|["'"\s]+$/g, '')
            .replace(/<[^>]*>/g, '');
    } catch (error) {
        console.log(`gemini.js: خطأ في تصحيح اسم الفيلم: ${error.message}`);
        // في حالة حدوث أي خطأ، أعد الاسم الأصلي
        return movieTitle;
    }
}

async function detectIntent(text, message, isCommandCorrection = false, historyDepth = 3, retryCount = 0) {
    let intent = "unknown";
    let keywords = null;
    let correctedCommand = null;
    let errorMessage = null;
    let confidence = 0.5;
    let songTitle = null;

    let context = "";
    if (message.quoted) {
        context += `Quoted message: ${message.quoted.text}\n`;
        if (message.quoted.imageMessage) context += 'The quoted message is an image.\n';
        if (message.quoted.videoMessage) context += 'The quoted message is a video.\n';
        if (message.quoted.audioMessage) context += 'The quoted message is an audio.\n';
        if (message.quoted.stickerMessage) context += 'The quoted message is a sticker.\n';
        if (message.quoted.documentMessage) context += 'The quoted message is a document.\n';
        if (message.quoted.locationMessage) context += 'The quoted message is a location.\n';
        if (message.quoted.contactMessage) context += 'The quoted message is a contact.\n';
    }
    if (message.message?.imageMessage) context += 'The current message contains an image.\n';
    if (message.message?.videoMessage) context += 'The current message is a video.\n';
    if (message.message?.audioMessage) context += 'The current message is an audio.\n';
    if (message.message?.stickerMessage) context += 'The current message is a sticker.\n';
    if (message.message?.documentMessage) context += 'The current message is a document.\n';
    if (message.message?.locationMessage) context += 'The current message is a location.\n';
    if (message.message?.contactMessage) context += 'The current message is a contact.\n';

    let historyMessages = [];
    if (historyDepth > 0 && message.history && message.history.messages) {
        const recentMessages = message.history.messages.slice(-historyDepth).filter(msg => msg.key.remoteJid === message.key.remoteJid && msg.key.fromMe === false);
        for (const histMessage of recentMessages) {
            if (histMessage.message?.imageMessage || histMessage.message?.videoMessage || histMessage.message?.documentMessage) {
                historyMessages.push(histMessage.message);
            }
        }
    }

    let prompt = `
    [Task Definition]
    Your primary goal is to analyze user messages to detect the user's intent and, if necessary, correct command format errors in their commands.

    [Intent Categories]
    You MUST identify the primary intent from these categories:
    - anime_quote: User is requesting an anime quote.
    - text_to_speech: User wants to convert text to speech.
    - sticker_request: User is requesting a sticker.
    - song_request: User is requesting to download a song.
    - movie_info_request: User is asking for information about a movie.
    - image_search_request: User wants to search for an image.
    - help_request: User is asking for help or command list.
    - secret_message_request: User wants to send a secret message.
    If the message intent does not match any of these, classify the intent as "unknown".

    [Response Format]
    You MUST respond in JSON format.
    For command correction tasks (when asked to correct a command), directly return the corrected command as a text string under the key "correctedCommand". This corrected command MUST be directly executable by the system. If correction is impossible or the input is not a command, use "errorMessage" to provide a user-friendly error message or explanation.
    For intent detection, return a JSON object including: "primaryIntent", "confidence", and intent-specific details.

    [Command Correction Scenario]
    - If asked to correct a command (isCommandCorrection=true), focus on correcting errors in command format or keywords.
    - Correct the command to be directly executable.
    - Return the ENTIRE corrected command string (including the command prefix and all parameters) under "correctedCommand".
    - If unable to correct, use "errorMessage" to explain the issue.

    [Example - Command Correction]
    User message (incorrect command): "secreet 2012xxxxxxxxx hi"
    Response JSON:
    { "correctedCommand": ".secret 2012xxxxxxxxx hi" }

    [Intent Detection Scenario]
    - If NOT asked to correct a command (isCommandCorrection=false), perform intent detection.
    - For 'image_search_request', extract keywords for image search.
    - For 'song_request', extract the title of the song the user wants to download and include it in the 'songTitle' field.
    - Return intent details in JSON format as shown in the example format.

    [Example - Intent Detection]
    User message: "عايز صورة لمحمد صلاح"
    Response JSON:
    {
      "primaryIntent": "image_search_request",
      "confidence": 0.95,
      "isAnimeQuote": false,
      "isTextToSpeech": false,
      "isStickerRequest": false,
      "isSongRequest": false,
      "isMovieInfoRequest": false,
      "isImageSearchRequest": true,
      "imageSearchKeywords": "محمد صلاح",
      "isHelpRequest": false,
      "isSecretMessageRequest": false,
      "lastMediaMessage": null
    }

    [Example - Song Request Intent Detection]
    User message: "عايز اغنية حسن شاكوش"
    Response JSON:
    {
      "primaryIntent": "song_request",
      "confidence": 0.95,
      "isAnimeQuote": false,
      "isTextToSpeech": false,
      "isStickerRequest": false,
      "isSongRequest": true,
      "isMovieInfoRequest": false,
      "isImageSearchRequest": false,
      "songTitle": "حسن شاكوش",
      "isHelpRequest": false,
      "isSecretMessageRequest": false,
      "lastMediaMessage": null
    }

    [Examples of secret_message_request Intent]
    - "رسالة سرية"
    - "secret"
    - "صارحني"
    - "ابعت رسالة سرية"

    [User Message Analysis]
    Analyze this user message: "${text}"
    `;

    try {
        const response = await callGemini(prompt);
        const intentJSON = response;
        console.log("🔮 Gemini JSON Response:", intentJSON);

        intent = intentJSON.primaryIntent || "unknown";
        confidence = intentJSON.confidence !== undefined ? intentJSON.confidence : 0.5;
        keywords = intentJSON.imageSearchKeywords || null;
        correctedCommand = intentJSON.correctedCommand || null;
        errorMessage = intentJSON.errorMessage || null;
        songTitle = intentJSON.songTitle || null;

        if (historyDepth > 0 && intentJSON.isStickerRequest && !message.message?.imageMessage && !message.message?.videoMessage && !message.message?.documentMessage && historyMessages.length > 0) {
            intentJSON.lastMediaMessage = historyMessages[historyMessages.length - 1].message;
        } else {
            intentJSON.lastMediaMessage = null;
        }
        return {
            primaryIntent: intent,
            confidence: confidence,
            isAnimeQuote: !!intentJSON.isAnimeQuote,
            isTextToSpeech: !!intentJSON.isTextToSpeech,
            isStickerRequest: !!intentJSON.isStickerRequest,
            isSongRequest: !!intentJSON.isSongRequest,
            isMovieInfoRequest: !!intentJSON.isMovieInfoRequest,
            isImageSearchRequest: !!intentJSON.isImageSearchRequest,
            imageSearchKeywords: keywords,
            isHelpRequest: !!intentJSON.isHelpRequest,
            isSecretMessageRequest: !!intentJSON.isSecretMessageRequest,
            lastMediaMessage: intentJSON.lastMediaMessage,
            correctedCommand: correctedCommand,
            errorMessage: errorMessage,
            songTitle: songTitle
        };
    } catch (error) {
        console.error("Gemini Intent Detection Failed:", error);
        return {
            primaryIntent: "unknown",
            confidence: 0.1,
            isAnimeQuote: false,
            isTextToSpeech: false,
            isStickerRequest: false,
            isSongRequest: false,
            isMovieInfoRequest: false,
            isImageSearchRequest: false,
            imageSearchKeywords: null,
            isHelpRequest: false,
            isSecretMessageRequest: false,
            lastMediaMessage: null,
            correctedCommand: null,
            errorMessage: "*حصل مشكلة وأنا بفهم طلبك 😕 جرب تاني بعد شوية 🙏*",
            songTitle: null
        };
    }
}

module.exports = { detectIntent, callGemini, generateResponse, correctMovieTitle };
