const yts = require("youtube-yts");
const ytdl = require("@distube/ytdl-core");
const fs = require("fs");
const path = require("path");
const { sendErrorMessage, sendFormattedMessage } = require('./messageUtils');

const songsFolder = path.join(__dirname, '..', 'songs');
let songCounter = 1;

if (!fs.existsSync(songsFolder)) {
    fs.mkdirSync(songsFolder, { recursive: true });
}

const downloadSong = async (sock, chatId, message, query) => {
    if (!query || query.trim() === '') {
        await sendErrorMessage(sock, chatId, "*اكتب اسم الأغنية بعد \`.song` علشان أجيبها 🎵*");
        return;
    }

    let statusMsg = await sock.sendMessage(chatId, {
        text: "*جاري البحث... 🔎*\n`" + query + "`"
    });

    try {
        const searchResults = await yts(query);

        if (!searchResults.videos || !searchResults.videos.length) {
            await sock.sendMessage(chatId, {
                text: "*مش لاقي نتايج 😕*\n*جرب كلمات بحث تانية 📝*",
                edit: statusMsg.key
            });
            return;
        }

        const song = searchResults.videos[0];
        const songDuration = song.duration ? song.duration.timestamp : "مش معروف";
        const songTitle = song.title.replace(/[^\w\s]/gi, "");
        const artistName = song.author?.name || "فنان مش معروف";

        const fileName = `song_${songCounter}_${Date.now()}.mp3`;
        const filePath = path.join(songsFolder, fileName);
        songCounter++;

        console.log(`[Song Downloader] Found: "${songTitle}" by ${artistName}, Duration: ${songDuration}`);
        console.log(`[Song Downloader] Saving to: ${filePath}`);

        await sock.sendMessage(chatId, {
            text: `*لقيت الأغنية ✅*\n\n*🎵 ${songTitle}*\n*👤 ${artistName}*\n*⏱️ ${songDuration}*\n\n*جاري التحميل... ⏳*`,
            edit: statusMsg.key
        });

        const stream = ytdl(song.url, {
            quality: "highestaudio",
            filter: "audioonly"
        });

        const writeStream = fs.createWriteStream(filePath);
        stream.pipe(writeStream);

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
                        caption: `🎵 ${songTitle}\n👤 ${artistName}\n⏱️ ${songDuration}\n📊 ${fileSizeMB}MB`,
                        waveform: [0, 127, 64, 32, 96, 127, 64, 96, 32, 64, 127, 96, 64, 32, 0]
                    },
                    { quoted: message }
                );

                fs.unlink(filePath, (err) => {
                    if (err) console.error(`[Song Downloader] Error deleting file: ${err}`);
                    else console.log(`[Song Downloader] Temp file deleted: ${filePath}`);
                });

                await sock.sendMessage(chatId, {
                    text: `*تم إرسال الأغنية بنجاح ✨*\n\n*🎵 ${songTitle}*\n*👤 ${artistName}*\n\n*شكرًا إنك استخدمت Zaky AI 🤖*`,
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
                text: "*⚠️ حصل مشكلة وأنا بنزل الأغنية 😔*\n*ممكن المحتوى محمي أو مش متاح للتنزيل 🚫*",
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

module.exports = { downloadSong };
