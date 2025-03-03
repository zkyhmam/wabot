const ytdl = require("@distube/ytdl-core");
const fs = require("fs");
const path = require("path");
const { sendErrorMessage, sendFormattedMessage } = require('./messageUtils');
const { google } = require('googleapis');
const ffmpeg = require('fluent-ffmpeg');
const https = require('https');
const stream = require('stream');
const { promisify } = require('util');

// Initialize Google YouTube API
const youtube = google.youtube({
    version: 'v3',
    auth: 'AIzaSyDGXCFF6aIa6NVXYwtnQ4aZSjtMNR8KLC0' // Replace with your actual API key
});

const songsFolder = path.join(__dirname, '..', 'songs');
const videosFolder = path.join(__dirname, '..', 'videos');
const thumbnailsFolder = path.join(__dirname, '..', 'thumbnails');
let songCounter = 1;
let videoCounter = 1;

// Create folders if they don't exist
[songsFolder, videosFolder, thumbnailsFolder].forEach(folder => {
    if (!fs.existsSync(folder)) {
        fs.mkdirSync(folder, { recursive: true });
    }
});

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
 * @returns {Promise} Array of video details
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

        const videoIds = response.data.items.map(item => item.id.videoId);

        const videoDetails = await youtube.videos.list({
            part: 'contentDetails,snippet,statistics',
            id: videoIds.join(',')
        });

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
            likes: parseInt(video.statistics.likeCount || 0, 10),
            comments: parseInt(video.statistics.commentCount || 0, 10),
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
 * Download thumbnail from URL
 * @param {string} url - Thumbnail URL
 * @param {string} filePath - Where to save the thumbnail
 * @returns {Promise} Success status
 */
const downloadThumbnail = async (url, filePath) => {
    return new Promise((resolve, reject) => {
        https.get(url, (response) => {
            if (response.statusCode !== 200) {
                reject(new Error(`Failed to download thumbnail: ${response.statusCode}`));
                return;
            }

            const fileStream = fs.createWriteStream(filePath);
            response.pipe(fileStream);

            fileStream.on('finish', () => {
                fileStream.close();
                resolve(true);
            });

            fileStream.on('error', (err) => {
                fs.unlink(filePath, () => {}); // Delete the file if there's an error
                reject(err);
            });
        }).on('error', (err) => {
            reject(err);
        });
    });
};

/**
 * Add thumbnail to video using ffmpeg
 * @param {string} videoPath - Path to video file
 * @param {string} thumbnailPath - Path to thumbnail image
 * @param {string} outputPath - Path to save the new video with thumbnail
 * @returns {Promise} Success status
 */
const addThumbnailToVideo = async (videoPath, thumbnailPath, outputPath) => {
    return new Promise((resolve, reject) => {
        ffmpeg(videoPath)
            .input(thumbnailPath)
            .outputOptions([
                '-map 0',
                '-map 1',
                '-c copy',
                '-disposition:v:1 attached_pic',
                '-metadata:s:v:1 title="Album cover"',
                '-metadata:s:v:1 comment="Cover (front)"'
            ])
            .output(outputPath)
            .on('end', () => {
                resolve(true);
            })
            .on('error', (err) => {
                console.error('[ffmpeg] Error adding thumbnail:', err);
                reject(err);
            })
            .run();
    });
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
        const songTitle = song.title.replace(/[^\w\s]/gi, ""); // Remove special characters
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

        let downloadedBytes = 0;
        let totalBytes = 0;
        let lastProgressUpdate = Date.now();

        stream.on('info', (info, format) => {
            totalBytes = parseInt(format.contentLength, 10) || 0;
        });

        stream.on('data', (chunk) => {
            downloadedBytes += chunk.length;

            const now = Date.now();
            if (now - lastProgressUpdate > 2000 && totalBytes > 0) { // Update every 2 seconds
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
                        waveform: [0,127,64,32,96,127,64,96,32,64,127,96,64,32,0] // Example waveform
                    },
                    { quoted: message }
                );

                // Delete the temporary file
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
                 // Delete temp file even on send error
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
             // Delete temp file on download error
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
 * Download video from YouTube with thumbnail as cover
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

    let statusMsg = await sock.sendMessage(chatId, { text: "*جاري البحث... 🔎*\n`" + query + "`" });

    try {
        const searchResults = await searchYouTube(query);

        if (!searchResults || !searchResults.length) {
            await sock.sendMessage(chatId, { text: "*مش لاقي نتايج 😕*\n*جرب كلمات بحث تانية 📝*", edit: statusMsg.key });
            return;
        }

        const video = searchResults[0];
        const videoDuration = video.duration.timestamp || "مش معروف";
        const videoTitle = video.title.replace(/[^\w\s]/gi, ""); // Remove special characters
        const channelName = video.author?.name || "قناة غير معروفة";
        const viewCount = video.views ? new Intl.NumberFormat('ar-EG').format(video.views) : "غير معروف";

        // Limit video duration to 10 minutes (600 seconds)
        if (video.duration.seconds > 600) {
          await sock.sendMessage(chatId, {
            text: `*⚠️ الفيديو ده طويل جدًا (${videoDuration}) ⏱️*\n*ممكن تجرب فيديو أقصر من 10 دقايق 🙏*`,
            edit: statusMsg.key
          });
          return;
        }

        const videoId = Date.now(); // Use this for unique filenames
        const fileName = `video_${videoCounter}_${videoId}.mp4`;
        const filePath = path.join(videosFolder, fileName);
        const thumbnailPath = path.join(thumbnailsFolder, `thumb_${videoId}.jpg`);
        const finalVideoPath = path.join(videosFolder, `final_${videoId}.mp4`); // Separate path for final video
        videoCounter++;

        console.log(`[Video Downloader] Found: "${videoTitle}" by ${channelName}, Duration: ${videoDuration}`);
        console.log(`[Video Downloader] Saving to: ${filePath}`);


        await sock.sendMessage(chatId, { text: `*لقيت الفيديو ✅*\n\n*🎬 ${videoTitle}*\n*📺 ${channelName}*\n*⏱️ ${videoDuration}*\n*👁️ ${viewCount} مشاهدة*\n\n*جاري التحميل... ⏳*`, edit: statusMsg.key });

         // Download thumbnail first (before starting the main download)
        try{
          await downloadThumbnail(video.thumbnail, thumbnailPath);
          console.log(`[Video Downloader] Thumbnail downloaded: ${thumbnailPath}`);
        } catch (thumbnailError) {
          console.error("[Video Downloader] Thumbnail download error:", thumbnailError);
          //  Don't return; continue without thumbnail
        }

        const stream = ytdl(video.url, {
            quality: "highest",
            filter: "videoandaudio"
        });
        const writeStream = fs.createWriteStream(filePath);
        stream.pipe(writeStream);

        let downloadedBytes = 0;
        let totalBytes = 0;
        let lastProgressUpdate = Date.now();

        stream.on('info', (info, format) => {
          totalBytes = parseInt(format.contentLength, 10) || 0; // Fallback to 0 if contentLength is undefined
        });

        stream.on('data', (chunk) => {
            downloadedBytes += chunk.length;
             const now = Date.now();
            if (now - lastProgressUpdate > 3000 && totalBytes > 0) { // Update every 3 seconds and only if totalBytes is valid.
              lastProgressUpdate = now;
              const progress = Math.floor((downloadedBytes / totalBytes) * 100);
                sock.sendMessage(chatId, { text: `*لقيت الفيديو ✅*\n\n*🎬 ${videoTitle}*\n*📺 ${channelName}*\n*⏱️ ${videoDuration}*\n\n*جاري التحميل... ${progress}% ⏳*`, edit: statusMsg.key })
                .catch(err => console.error('[Video Downloader] Error updating progress:', err));
            }
        });

        writeStream.on("finish", async () => {
          await sock.sendMessage(chatId, {
            text: `*تم التحميل بنجاح 🎉*\n\n*🎬 ${videoTitle}*\n*📺 ${channelName}*\n*⏱️ ${videoDuration}*\n\n*جاري إضافة الصورة المصغرة... 🖼️*`,
            edit: statusMsg.key
          });

          try {
            let videoToSend = filePath; // Default to original video

            // Add thumbnail if it exists
            if (fs.existsSync(thumbnailPath)) {
              try {
                await addThumbnailToVideo(filePath, thumbnailPath, finalVideoPath);
                console.log(`[Video Downloader] Thumbnail added to video: ${finalVideoPath}`);
                videoToSend = finalVideoPath; // Use the video with the thumbnail
              } catch (ffmpegError) {
                console.error("[Video Downloader] ffmpeg error:", ffmpegError);
                //  Continue sending the original video if adding thumbnail fails
              }
            }

            await sock.sendMessage(chatId, {
              text: `*تم معالجة الفيديو بنجاح 🎉*\n\n*🎬 ${videoTitle}*\n*📺 ${channelName}*\n*⏱️ ${videoDuration}*\n\n*جاري الإرسال... 🚀*`,
              edit: statusMsg.key
            });

            const videoBuffer = fs.readFileSync(videoToSend);
            const fileStats = fs.statSync(videoToSend);
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

            // Delete temporary files (original video, thumbnail, and final video)
            [filePath, thumbnailPath, finalVideoPath].forEach(file => {
              if (fs.existsSync(file)) {
                fs.unlink(file, (err) => {
                  if (err) console.error(`[Video Downloader] Error deleting file: ${err}`);
                  else console.log(`[Video Downloader] Temp file deleted: ${file}`);
                });
              }
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
             // Delete temp files even on send error.
            [filePath, thumbnailPath, finalVideoPath].forEach(file => {
                if (fs.existsSync(file)) {
                    fs.unlinkSync(file);
                }
            });
          }
      });

        stream.on("error", async (err) => {
            console.error("[Video Downloader] Download error:", err);
            await sock.sendMessage(chatId, {
                text: "*⚠️ حصل مشكلة وأنا بنزل الفيديو 😔*\n*ممكن المحتوى محمي أو مش متاح للتنزيل 🚫*\n\n*جرب فيديو تاني أو نفس الفيديو من مصدر تاني 🔍*",
                edit: statusMsg.key
            });
            // Delete temp files (video and thumbnail) if download fails
            [filePath, thumbnailPath].forEach(file => {
              if (fs.existsSync(file)) {
                fs.unlinkSync(file);
              }
            });
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
 * Search YouTube and return results as separate messages with thumbnails and interactive buttons
 * @param {object} sock - WebSocket connection
 * @param {string} chatId - Chat ID
 * @param {object} message - Original message object
 * @param {string} query - Search query
 * @param {number} maxResults - Maximum number of results to return
 */
const searchAndDisplay = async (sock, chatId, message, query, maxResults = 3) => {
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

    await sock.sendMessage(chatId, {
      text: `*📋 نتائج البحث عن "${query}" (${searchResults.length} نتائج)*`,
      edit: statusMsg.key
    });

    console.log("[YouTube Search] Starting to process search results with buttons...");

    for (const video of searchResults) {
      console.log(`[YouTube Search] Processing video: ${video.title} (ID: ${video.id})`);

      const viewsFormatted = new Intl.NumberFormat('ar-EG').format(video.views);
      const likesFormatted = new Intl.NumberFormat('ar-EG').format(video.likes);
      const commentsFormatted = new Intl.NumberFormat('ar-EG').format(video.comments);

      const caption = `*🎬 ${video.title}*\n\n` +
                      `*📺 القناة:* ${video.author.name}\n` +
                      `*⏱️ المدة:* ${video.duration.timestamp}\n` +
                      `*👁️ المشاهدات:* ${viewsFormatted}\n` +
                      `*👍 الإعجابات:* ${likesFormatted}\n` +
                      `*💬 التعليقات:* ${commentsFormatted}\n\n` +
                      `*🔗 الرابط:* ${video.url}\n\n` +
                      `*📥 لتحميل هذا الفيديو:* \`.video ${video.title}\`\n` +
                      `*🎵 لتحميل صوت فقط:* \`.song ${video.title}\``;

      try {
          console.log(`[YouTube Search] Downloading thumbnail for video: ${video.id}`);
          const thumbnailId = Date.now() + Math.floor(Math.random() * 1000); // Unique ID
          const tempThumbPath = path.join(thumbnailsFolder, `temp_thumb_${thumbnailId}.jpg`); // Temp path
          await downloadThumbnail(video.thumbnail, tempThumbPath);
          console.log(`[YouTube Search] Thumbnail downloaded successfully: ${tempThumbPath}`);

          console.log(`[YouTube Search] Preparing buttons for video: ${video.id}`);
        const buttons = [
          {
            buttonId: `download_video_${video.id}`,
            buttonText: { displayText: 'تنزيل الفيديو - Zaky AI 📹' },
            type: 1
          },
          {
            buttonId: `download_song_${video.id}`,
            buttonText: { displayText: 'تنزيل الصوت - Zaky AI 🎵' },
            type: 1
          }
        ];
        console.log(`[YouTube Search] Buttons prepared: ${JSON.stringify(buttons)}`);

        console.log(`[YouTube Search] Sending message with buttons for video: ${video.id}`);
        await sock.sendMessage(
          chatId,
          {
            image: fs.readFileSync(tempThumbPath), // Use temp image
            caption: caption,
            footer: 'Zaky AI 🤖', // Consistent footer
            buttons: buttons,
            headerType: 4
          },
          { quoted: message }
        );
        console.log(`[YouTube Search] Message with buttons sent successfully for video: ${video.id}`);

        // Clean up temp thumbnail
        fs.unlink(tempThumbPath, (err) => {
          if (err) console.error(`[YouTube Search] Error deleting temp thumbnail: ${err}`);
          else console.log(`[YouTube Search] Temp thumbnail deleted: ${tempThumbPath}`);
        });
        await new Promise(resolve => setTimeout(resolve, 500)); // Short delay


      } catch (imgError) {
        console.error(`[YouTube Search] Error with thumbnail or buttons for video ${video.id}:`, imgError);
        console.log(`[YouTube Search] Falling back to text-only message for video: ${video.id}`);
        await sock.sendMessage(chatId, { text: caption }, { quoted: message }); // Send text-only message
        console.log(`[YouTube Search] Text-only message sent for video: ${video.id}`);
      }
    }

    console.log("[YouTube Search] Sending summary message...");
    await sock.sendMessage(chatId, {
      text: `*لتحميل فيديو: \`.video ${query}\`*\n*لتحميل أغنية: \`.song ${query}\`*\n\n*لمزيد من نتائج البحث اكتب:* \`.yts ${query} more\``
    });
    console.log("[YouTube Search] Summary message sent successfully.");


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
