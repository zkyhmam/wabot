const ytdl = require("@distube/ytdl-core");
const fs = require("fs");
const path = require("path");
const { sendErrorMessage, sendFormattedMessage } = require('./messageUtils');
const { google } = require('googleapis');

// Initialize Google YouTube API
const youtube = google.youtube({
    version: 'v3',
    auth: 'AIzaSyDGXCFF6aIa6NVXYwtnQ4aZSjtMNR8KLC0'
});

const songsFolder = path.join(__dirname, '..', 'songs');
const videosFolder = path.join(__dirname, '..', 'videos');
let songCounter = 1;
let videoCounter = 1;

// Create folders if they don't exist
if (!fs.existsSync(songsFolder)) {
    fs.mkdirSync(songsFolder, { recursive: true });
}

if (!fs.existsSync(videosFolder)) {
    fs.mkdirSync(videosFolder, { recursive: true });
}

/**
 * Format duration from ISO 8601 to readable format
 * @param {string} isoDuration - YouTube API duration format (PT1H32M15S)
 * @returns {string} Formatted duration (1:32:15)
 */
const formatDuration = (isoDuration) => {
    if (!isoDuration) return "مش معروف";
    
    const match = isoDuration.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);
    
    if (!match) return "مش معروف";
    
    const hours = parseInt(match[1] || 0);
    const minutes = parseInt(match[2] || 0);
    const seconds = parseInt(match[3] || 0);
    
    if (hours > 0) {
        return `${hours}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    } else {
        return `${minutes}:${seconds.toString().padStart(2, '0')}`;
    }
};

/**
 * Search for videos using YouTube API
 * @param {string} query - Search query
 * @param {number} maxResults - Maximum number of results to return
 * @returns {Promise<Array>} Array of video details
 */
const searchYouTube = async (query, maxResults = 5) => {
    try {
        const response = await youtube.search.list({
            part: 'snippet',
            q: query,
            maxResults: maxResults,
            type: 'video'
        });

        if (!response.data.items || !response.data.items.length) {
            return [];
        }

        // Get video IDs
        const videoIds = response.data.items.map(item => item.id.videoId);

        // Get detailed info including duration
        const videoDetails = await youtube.videos.list({
            part: 'contentDetails,snippet,statistics',
            id: videoIds.join(',')
        });

        // Format the results
        return videoDetails.data.items.map(video => ({
            id: video.id,
            url: `https://www.youtube.com/watch?v=${video.id}`,
            title: video.snippet.title,
            description: video.snippet.description,
            thumbnail: video.snippet.thumbnails.high.url,
            author: {
                name: video.snippet.channelTitle,
                id: video.snippet.channelId,
                url: `https://www.youtube.com/channel/${video.snippet.channelId}`
            },
            duration: {
                seconds: convertIsoDurationToSeconds(video.contentDetails.duration),
                timestamp: formatDuration(video.contentDetails.duration)
            },
            views: parseInt(video.statistics.viewCount, 10),
            uploadDate: video.snippet.publishedAt
        }));
    } catch (error) {
        console.error("[YouTube API] Search error:", error);
        return [];
    }
};

/**
 * Convert ISO 8601 duration to seconds
 * @param {string} isoDuration - Duration in ISO format
 * @returns {number} Duration in seconds
 */
const convertIsoDurationToSeconds = (isoDuration) => {
    const match = isoDuration.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);
    
    if (!match) return 0;
    
    const hours = parseInt(match[1] || 0);
    const minutes = parseInt(match[2] || 0);
    const seconds = parseInt(match[3] || 0);
    
    return hours * 3600 + minutes * 60 + seconds;
};

/**
 * Download song from YouTube
 * @param {object} sock - WebSocket connection
 * @param {string} chatId - Chat ID
 * @param {object} message - Original message object
 * @param {string} query - Search query
 */
const downloadSong = async (sock, chatId, message, query) => {
    if (!query || query.trim() === '') {
        await sendErrorMessage(sock, chatId, "*اكتب اسم الأغنية بعد \`.song` علشان أجيبها 🎵*");
        return;
    }

    let statusMsg = await sock.sendMessage(chatId, {
        text: "*جاري البحث... 🔎*\n`" + query + "`"
    });

    try {
        const searchResults = await searchYouTube(query);

        if (!searchResults || !searchResults.length) {
            await sock.sendMessage(chatId, {
                text: "*مش لاقي نتايج 😕*\n*جرب كلمات بحث تانية 📝*",
                edit: statusMsg.key
            });
            return;
        }

        const song = searchResults[0];
        const songDuration = song.duration.timestamp || "مش معروف";
        const songTitle = song.title.replace(/[^\w\s]/gi, "");
        const artistName = song.author?.name || "فنان مش معروف";
        const viewCount = song.views ? new Intl.NumberFormat('ar-EG').format(song.views) : "غير معروف";

        const fileName = `song_${songCounter}_${Date.now()}.mp3`;
        const filePath = path.join(songsFolder, fileName);
        songCounter++;

        console.log(`[Song Downloader] Found: "${songTitle}" by ${artistName}, Duration: ${songDuration}`);
        console.log(`[Song Downloader] Saving to: ${filePath}`);

        await sock.sendMessage(chatId, {
            text: `*لقيت الأغنية ✅*\n\n*🎵 ${songTitle}*\n*👤 ${artistName}*\n*⏱️ ${songDuration}*\n*👁️ ${viewCount} مشاهدة*\n\n*جاري التحميل... ⏳*`,
            edit: statusMsg.key
        });

        const stream = ytdl(song.url, {
            quality: "highestaudio",
            filter: "audioonly"
        });

        const writeStream = fs.createWriteStream(filePath);
        stream.pipe(writeStream);

        // Progress tracking
        let downloadedBytes = 0;
        let totalBytes = 0;
        let lastProgressUpdate = Date.now();

        stream.on('info', (info, format) => {
            totalBytes = parseInt(format.contentLength, 10) || 0;
        });

        stream.on('data', (chunk) => {
            downloadedBytes += chunk.length;
            
            // Update progress every 2 seconds to avoid too many messages
            const now = Date.now();
            if (now - lastProgressUpdate > 2000 && totalBytes > 0) {
                lastProgressUpdate = now;
                const progress = Math.floor((downloadedBytes / totalBytes) * 100);
                sock.sendMessage(chatId, {
                    text: `*لقيت الأغنية ✅*\n\n*🎵 ${songTitle}*\n*👤 ${artistName}*\n*⏱️ ${songDuration}*\n\n*جاري التحميل... ${progress}% ⏳*`,
                    edit: statusMsg.key
                }).catch(err => console.error('[Song Downloader] Error updating progress:', err));
            }
        });

        writeStream.on("finish", async () => {
            await sock.sendMessage(chatId, {
                text: `*تم التحميل بنجاح 🎉*\n\n*🎵 ${songTitle}*\n*👤 ${artistName}*\n*⏱️ ${songDuration}*\n\n*جاري الإرسال... 🚀*`,
                edit: statusMsg.key
            });

            try {
                const audioBuffer = fs.readFileSync(filePath);
                const fileStats = fs.statSync(filePath);
                const fileSizeMB = (fileStats.size / (1024 * 1024)).toFixed(2);

                await sock.sendMessage(
                    chatId,
                    {
                        audio: audioBuffer,
                        mimetype: "audio/mp4",
                        fileName: `${songTitle}.mp3`,
                        caption: `🎵 ${songTitle}\n👤 ${artistName}\n⏱️ ${songDuration}\n📊 ${fileSizeMB}MB\n📅 ${new Date().toLocaleDateString('ar-EG')}`,
                        waveform: [0, 127, 64, 32, 96, 127, 64, 96, 32, 64, 127, 96, 64, 32, 0]
                    },
                    { quoted: message }
                );

                fs.unlink(filePath, (err) => {
                    if (err) console.error(`[Song Downloader] Error deleting file: ${err}`);
                    else console.log(`[Song Downloader] Temp file deleted: ${filePath}`);
                });

                await sock.sendMessage(chatId, {
                    text: `*تم إرسال الأغنية بنجاح ✨*\n\n*🎵 ${songTitle}*\n*👤 ${artistName}*\n*👁️ ${viewCount} مشاهدة*\n\n*شكرًا إنك استخدمت Zaky AI 🤖*\n\n*لتحميل المزيد من الأغاني استخدم .song متبوعًا باسم الأغنية*`,
                    edit: statusMsg.key
                });

            } catch (sendError) {
                console.error("[Song Downloader] Error sending audio:", sendError);
                await sock.sendMessage(chatId, {
                    text: "*⚠️ حصل مشكلة وأنا ببعت الملف 😕*\n*جرب تاني بعد شوية 🔄*",
                    edit: statusMsg.key
                });

                if (fs.existsSync(filePath)) {
                    fs.unlinkSync(filePath);
                }
            }
        });

        stream.on("error", async (err) => {
            console.error("[Song Downloader] Download error:", err);
            await sock.sendMessage(chatId, {
                text: "*⚠️ حصل مشكلة وأنا بنزل الأغنية 😔*\n*ممكن المحتوى محمي أو مش متاح للتنزيل 🚫*\n\n*جرب أغنية تانية أو نفس الأغنية من مصدر تاني 🔍*",
                edit: statusMsg.key
            });

            if (fs.existsSync(filePath)) {
                fs.unlinkSync(filePath);
            }
        });

    } catch (error) {
        console.error("[Song Downloader] Critical error:", error);
        await sock.sendMessage(chatId, {
            text: "*❌ حصل مشكلة غريبة 😵*\n*جرب تاني بعد شوية 🙏*",
            edit: statusMsg.key
        });
    }
};

/**
 * Download video from YouTube
 * @param {object} sock - WebSocket connection
 * @param {string} chatId - Chat ID
 * @param {object} message - Original message object
 * @param {string} query - Search query
 */
const downloadVideo = async (sock, chatId, message, query) => {
    if (!query || query.trim() === '') {
        await sendErrorMessage(sock, chatId, "*اكتب اسم الفيديو بعد \`.video` علشان أجيبه 🎬*");
        return;
    }

    let statusMsg = await sock.sendMessage(chatId, {
        text: "*جاري البحث... 🔎*\n`" + query + "`"
    });

    try {
        const searchResults = await searchYouTube(query);

        if (!searchResults || !searchResults.length) {
            await sock.sendMessage(chatId, {
                text: "*مش لاقي نتايج 😕*\n*جرب كلمات بحث تانية 📝*",
                edit: statusMsg.key
            });
            return;
        }

        const video = searchResults[0];
        const videoDuration = video.duration.timestamp || "مش معروف";
        const videoTitle = video.title.replace(/[^\w\s]/gi, "");
        const channelName = video.author?.name || "قناة غير معروفة";
        const viewCount = video.views ? new Intl.NumberFormat('ar-EG').format(video.views) : "غير معروف";

        // Check if video is too long (10 minutes max)
        if (video.duration.seconds > 600) { 
            await sock.sendMessage(chatId, {
                text: `*⚠️ الفيديو ده طويل جدًا (${videoDuration}) ⏱️*\n*ممكن تجرب فيديو أقصر من 10 دقايق 🙏*`,
                edit: statusMsg.key
            });
            return;
        }

        const fileName = `video_${videoCounter}_${Date.now()}.mp4`;
        const filePath = path.join(videosFolder, fileName);
        videoCounter++;

        console.log(`[Video Downloader] Found: "${videoTitle}" by ${channelName}, Duration: ${videoDuration}`);
        console.log(`[Video Downloader] Saving to: ${filePath}`);

        await sock.sendMessage(chatId, {
            text: `*لقيت الفيديو ✅*\n\n*🎬 ${videoTitle}*\n*📺 ${channelName}*\n*⏱️ ${videoDuration}*\n*👁️ ${viewCount} مشاهدة*\n\n*جاري التحميل... ⏳*`,
            edit: statusMsg.key
        });

        const stream = ytdl(video.url, {
            quality: "highest",
            filter: "videoandaudio"
        });

        const writeStream = fs.createWriteStream(filePath);
        stream.pipe(writeStream);
        
        // Progress tracking
        let downloadedBytes = 0;
        let totalBytes = 0;
        let lastProgressUpdate = Date.now();

        stream.on('info', (info, format) => {
            totalBytes = parseInt(format.contentLength, 10) || 0;
        });

        stream.on('data', (chunk) => {
            downloadedBytes += chunk.length;
            
            // Update progress every 3 seconds to avoid too many messages
            const now = Date.now();
            if (now - lastProgressUpdate > 3000 && totalBytes > 0) {
                lastProgressUpdate = now;
                const progress = Math.floor((downloadedBytes / totalBytes) * 100);
                sock.sendMessage(chatId, {
                    text: `*لقيت الفيديو ✅*\n\n*🎬 ${videoTitle}*\n*📺 ${channelName}*\n*⏱️ ${videoDuration}*\n\n*جاري التحميل... ${progress}% ⏳*`,
                    edit: statusMsg.key
                }).catch(err => console.error('[Video Downloader] Error updating progress:', err));
            }
        });

        writeStream.on("finish", async () => {
            await sock.sendMessage(chatId, {
                text: `*تم التحميل بنجاح 🎉*\n\n*🎬 ${videoTitle}*\n*📺 ${channelName}*\n*⏱️ ${videoDuration}*\n\n*جاري الإرسال... 🚀*`,
                edit: statusMsg.key
            });

            try {
                const videoBuffer = fs.readFileSync(filePath);
                const fileStats = fs.statSync(filePath);
                const fileSizeMB = (fileStats.size / (1024 * 1024)).toFixed(2);

                await sock.sendMessage(
                    chatId,
                    {
                        video: videoBuffer,
                        caption: `🎬 ${videoTitle}\n📺 ${channelName}\n⏱️ ${videoDuration}\n📊 ${fileSizeMB}MB`,
                        mimetype: "video/mp4",
                        fileName: `${videoTitle}.mp4`
                    },
                    { quoted: message }
                );

                fs.unlink(filePath, (err) => {
                    if (err) console.error(`[Video Downloader] Error deleting file: ${err}`);
                    else console.log(`[Video Downloader] Temp file deleted: ${filePath}`);
                });

                await sock.sendMessage(chatId, {
                    text: `*تم إرسال الفيديو بنجاح ✨*\n\n*🎬 ${videoTitle}*\n*📺 ${channelName}*\n*👁️ ${viewCount} مشاهدة*\n\n*شكرًا إنك استخدمت Zaky AI 🤖*\n\n*لتحميل المزيد من الفيديوهات استخدم .video متبوعًا باسم الفيديو*`,
                    edit: statusMsg.key
                });

            } catch (sendError) {
                console.error("[Video Downloader] Error sending video:", sendError);
                await sock.sendMessage(chatId, {
                    text: "*⚠️ حصل مشكلة وأنا ببعت الفيديو 😕*\n*ممكن حجم الفيديو كبير أو حصلت مشكلة في الشبكة 🔄*\n*جرب فيديو أقصر أو تاني بعد شوية*",
                    edit: statusMsg.key
                });

                if (fs.existsSync(filePath)) {
                    fs.unlinkSync(filePath);
                }
            }
        });

        stream.on("error", async (err) => {
            console.error("[Video Downloader] Download error:", err);
            await sock.sendMessage(chatId, {
                text: "*⚠️ حصل مشكلة وأنا بنزل الفيديو 😔*\n*ممكن المحتوى محمي أو مش متاح للتنزيل 🚫*\n\n*جرب فيديو تاني أو نفس الفيديو من مصدر تاني 🔍*",
                edit: statusMsg.key
            });

            if (fs.existsSync(filePath)) {
                fs.unlinkSync(filePath);
            }
        });

    } catch (error) {
        console.error("[Video Downloader] Critical error:", error);
        await sock.sendMessage(chatId, {
            text: "*❌ حصل مشكلة غريبة 😵*\n*جرب تاني بعد شوية 🙏*",
            edit: statusMsg.key
        });
    }
};

/**
 * Search YouTube and return results
 * @param {object} sock - WebSocket connection
 * @param {string} chatId - Chat ID
 * @param {object} message - Original message object
 * @param {string} query - Search query
 * @param {number} maxResults - Maximum number of results to return
 */
const searchAndDisplay = async (sock, chatId, message, query, maxResults = 5) => {
    if (!query || query.trim() === '') {
        await sendErrorMessage(sock, chatId, "*اكتب كلمات البحث بعد \`.yts` علشان أبحث 🔍*");
        return;
    }

    let statusMsg = await sock.sendMessage(chatId, {
        text: "*جاري البحث في يوتيوب... 🔎*\n`" + query + "`"
    });

    try {
        const searchResults = await searchYouTube(query, maxResults);

        if (!searchResults || !searchResults.length) {
            await sock.sendMessage(chatId, {
                text: "*مش لاقي نتايج 😕*\n*جرب كلمات بحث تانية 📝*",
                edit: statusMsg.key
            });
            return;
        }

        let resultText = `*📋 نتائج البحث عن "${query}"*\n\n`;

        searchResults.forEach((video, index) => {
            resultText += `*${index + 1}. ${video.title}*\n`;
            resultText += `👤 ${video.author.name}\n`;
            resultText += `⏱️ ${video.duration.timestamp}\n`;
            resultText += `👁️ ${new Intl.NumberFormat('ar-EG').format(video.views)} مشاهدة\n`;
            resultText += `🔗 ${video.url}\n\n`;
        });

        resultText += `*لتحميل فيديو: \`.video ${query}\`*\n`;
        resultText += `*لتحميل أغنية: \`.song ${query}\`*`;

        await sock.sendMessage(chatId, {
            text: resultText,
            edit: statusMsg.key
        });

    } catch (error) {
        console.error("[YouTube Search] Critical error:", error);
        await sock.sendMessage(chatId, {
            text: "*❌ حصل مشكلة في البحث 😵*\n*جرب تاني بعد شوية 🙏*",
            edit: statusMsg.key
        });
    }
};

module.exports = {
    downloadSong,
    downloadVideo,
    searchAndDisplay
};
