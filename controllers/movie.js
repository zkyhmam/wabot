const fetch = require('node-fetch');
const ytdl = require('@distube/ytdl-core');
const ytSearch = require('yt-search'); // إضافة مكتبة yt-search
const axios = require('axios');
const ffmpeg = require('fluent-ffmpeg');
const fs = require('fs');
const path = require('path');
const { sendErrorMessage, sendFormattedMessage } = require("./messageUtils");
require('dotenv').config();

const TMDB_API_KEY = "a3a01d35a3ebd5dc4fca8bc362b2c94a";
const TMDB_BEARER_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJhM2EwMWQzNWEzZWJkNWRjNGZjYThiYzM2MmIyYzk0YSIsIm5iZiI6MTc0MDc4Njg3Ni44MDcwMDAyLCJzdWIiOiI2N2MyNGNiY2M1ZGU4NDJiNGJhMjdkY2UiLCJzY29wZXMiOlsiYXBpX3JlYWQiXSwidmVyc2lvbiI6MX0.eOsWMFlT1cSkn7_ZGMMhUs3mqwqPFZ8XY2K4l_qCnlM";

const BOT_SIGNATURE = process.env.BOT_SIGNATURE || "*تحياتي Zaky 𖤍*";
const EGYPTIAN_DIALECT = process.env.EGYPTIAN_DIALECT || "Egyptian Arabic";
const FORMALITY_LEVEL = process.env.FORMALITY_LEVEL || "informal and engaging";
const EMOJI_DENSITY = process.env.EMOJI_DENSITY || "add many relevant emojis to make it fun";

const TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500";
const TMDB_API_BASE_URL = "https://api.themoviedb.org/3";

// دالة محسنة لاستخراج رابط الـ thumbnail من يوتيوب بتجربة عدة دقات
const getYoutubeThumbnail = (videoUrl) => {
    const videoId = videoUrl.split('v=')[1]?.split('&')[0];
    return {
        videoId,
        thumbnails: [
            `https://img.youtube.com/vi/${videoId}/maxresdefault.jpg`, // أعلى دقة
            `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`,     // دقة عالية
            `https://img.youtube.com/vi/${videoId}/mqdefault.jpg`,     // دقة متوسطة
            `https://img.youtube.com/vi/${videoId}/default.jpg`        // دقة قياسية
        ]
    };
};

// دالة جديدة للبحث في يوتيوب واختيار الفيديو الأكثر مشاهدة
const searchTrailerOnYoutube = async (query) => {
    try {
        const results = await ytSearch(query);
        const videos = results.videos.slice(0, 5); // أول 5 نتايج

        if (videos.length === 0) {
            throw new Error("مفيش تريلرات لقيتها على يوتيوب 😅");
        }

        // اختيار الفيديو اللي ليه أكتر مشاهدات
        const topVideo = videos.reduce((prev, current) => (prev.views > current.views) ? prev : current);
        return topVideo.url;
    } catch (error) {
        console.error(`movie.js: خطأ في البحث عن التريلر على يوتيوب: ${error.message}`);
        throw error;
    }
};

const movieCommand = async (sock, noWa, message, text) => {
    console.log("movie.js: Starting movieCommand");
    console.log(`movie.js: Received text: ${text}`);

    if (!text) {
        console.log("movie.js: No text provided");
        await sendFormattedMessage(sock, noWa, `*اكتب اسم الفيلم أو المسلسل اللي عايز تعرف عنه حاجة 🎥*`);
        return;
    }

    try {
        console.log(`movie.js: Searching for: ${text}`);
        let searchResults;
        try {
            searchResults = await searchMedia(text, 'ar-SA');
        } catch (searchError) {
            console.log(`movie.js: Error searching in Arabic: ${searchError.message}, trying English`);
            searchResults = await searchMedia(text, 'en-US');
        }

        if (!searchResults || searchResults.length === 0) {
            console.log("movie.js: No results found");
            await sendFormattedMessage(sock, noWa, `*مش لاقي الفيلم أو المسلسل ده 🔍 جرب تكتب الاسم بطريقة تانية 📝*`);
            return;
        }

        const firstResult = searchResults[0];
        console.log(`movie.js: Found media with ID: ${firstResult.id}, Type: ${firstResult.media_type}`);

        let mediaDetails;
        try {
            mediaDetails = await getMediaDetails(firstResult.id, firstResult.media_type, 'ar-SA');
        } catch (detailsError) {
            console.log(`movie.js: Error fetching details in Arabic: ${detailsError.message}, trying English`);
            mediaDetails = await getMediaDetails(firstResult.id, firstResult.media_type, 'en-US');
        }

        let mediaCredits;
        try {
            mediaCredits = await getMediaCredits(firstResult.id, firstResult.media_type);
        } catch (creditsError) {
            console.log(`movie.js: Error fetching credits: ${creditsError.message}`);
            mediaCredits = { crew: [], cast: [] };
        }

        const mediaInfo = formatMediaInfo(mediaDetails, mediaCredits, firstResult.media_type, mediaDetails.original_language === 'ar' ? 'ar-SA' : 'en-US');
        await sendMediaInfo(sock, noWa, mediaDetails, mediaInfo, message, firstResult, text);

    } catch (e) {
        console.error(`movie.js: General Error: ${e}`);
        await sendErrorMessage(sock, noWa, `*حصل مشكلة في البحث 😕 جرب تاني بعد شوية 🔄*`);
    }
};

const searchMedia = async (query, language) => {
    const url = `${TMDB_API_BASE_URL}/search/multi?api_key=${TMDB_API_KEY}&query=${encodeURIComponent(query)}&include_adult=false&language=${language}`;

    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`TMDB search API request failed with status ${response.status}`);
    }

    const data = await response.json();

    return data.results
        .filter(item => item.media_type === 'movie' || item.media_type === 'tv')
        .slice(0, 5);
};

const getMediaDetails = async (id, mediaType, language) => {
    const url = `${TMDB_API_BASE_URL}/${mediaType}/${id}?api_key=${TMDB_API_KEY}&append_to_response=watch/providers,external_ids,content_ratings,release_dates&language=${language}`;

    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`TMDB details API request failed with status ${response.status}`);
    }

    return await response.json();
};

const getMediaCredits = async (id, mediaType) => {
    const url = `${TMDB_API_BASE_URL}/${mediaType}/${id}/credits?api_key=${TMDB_API_KEY}`;

    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`TMDB credits API request failed with status ${response.status}`);
    }

    return await response.json();
};

const formatMediaInfo = (details, credits, mediaType, language) => {
    let contentRating = "*غير مصنف*";

    if (mediaType === 'movie' && details.release_dates && details.release_dates.results) {
        const usRating = details.release_dates.results.find(country => country.iso_3166_1 === 'US');
        if (usRating && usRating.release_dates && usRating.release_dates.length > 0) {
            contentRating = usRating.release_dates[0].certification || "*غير مصنف*";
        }
    } else if (mediaType === 'tv' && details.content_ratings && details.content_ratings.results) {
        const usRating = details.content_ratings.results.find(country => country.iso_3166_1 === 'US');
        if (usRating) {
            contentRating = usRating.rating || "*غير مصنف*";
        }
    }

    const directors = credits.crew
        ? credits.crew
            .filter(person => person.job === 'Director')
            .map(director => director.name)
            .slice(0, 2)
            .join(', ')
        : '*غير معروف*';

    const actors = credits.cast
        ? credits.cast
            .slice(0, 5)
            .map(actor => actor.name)
            .join(', ')
        : '*غير معروف*';

    const genres = details.genres
        ? details.genres
            .map(genre => genre.name)
            .join(', ')
        : '*غير محدد*';

    const releaseDate = mediaType === 'movie'
        ? details.release_date
        : details.first_air_date;

    let info = '';

    if (mediaType === 'movie') {
        info = `*🎬 معلومات الفيلم*\n\n` +
            `*العنوان:* ${details.title || '*غير معروف*'}\n` +
            `*العنوان الأصلي:* ${details.original_title || '*غير معروف*'}\n` +
            `*سنة الإصدار:* ${releaseDate ? releaseDate.substring(0, 4) : '*غير معروف*'}\n` +
            `*التصنيف العمري:* ${contentRating}\n` +
            `*تقييم المستخدمين:* ⭐ ${details.vote_average ? details.vote_average.toFixed(1) : '*غير متاح*'}/10 (${details.vote_count || 0} صوت)\n` +
            `*مدة الفيلم:* ${details.runtime ? `${details.runtime} دقيقة` : '*غير معروف*'}\n` +
            `*الأنواع:* ${genres}\n` +
            `*المخرج:* ${directors}\n` +
            `*الممثلين:* ${actors}\n` +
            `*الحالة:* ${details.status || '*غير معروف*'}\n` +
            `*الميزانية:* ${details.budget ? `$${(details.budget/1000000).toFixed(1)}M` : '*غير معروف*'}\n` +
            `*الإيرادات:* ${details.revenue ? `$${(details.revenue/1000000).toFixed(1)}M` : '*غير معروف*'}\n` +
            `*اللغة:* ${details.original_language ? details.original_language.toUpperCase() : '*غير معروف*'}\n\n` +
            `*نبذة عن الفيلم:*\n${details.overview || '*مفيش نبذة متاحة.*'}\n\n` +
            `*معرف IMDB:* ${details.external_ids?.imdb_id || '*غير متاح*'}\n`;
    } else {
        info = `*📺 معلومات المسلسل*\n\n` +
            `*العنوان:* ${details.name || '*غير معروف*'}\n` +
            `*العنوان الأصلي:* ${details.original_name || '*غير معروف*'}\n` +
            `*تاريخ أول عرض:* ${releaseDate || '*غير معروف*'}\n` +
            `*التصنيف العمري:* ${contentRating}\n` +
            `*تقييم المستخدمين:* ⭐ ${details.vote_average ? details.vote_average.toFixed(1) : '*غير متاح*'}/10 (${details.vote_count || 0} صوت)\n` +
            `*عدد المواسم:* ${details.number_of_seasons || '*غير معروف*'}\n` +
            `*عدد الحلقات:* ${details.number_of_episodes || '*غير معروف*'}\n` +
            `*الأنواع:* ${genres}\n` +
            `*المبدع:* ${details.created_by ? details.created_by.map(creator => creator.name).join(', ') : '*غير معروف*'}\n` +
            `*الممثلين:* ${actors}\n` +
            `*الحالة:* ${details.status || '*غير معروف*'}\n` +
            `*اللغة:* ${details.original_language ? details.original_language.toUpperCase() : '*غير معروف*'}\n\n` +
            `*نبذة عن المسلسل:*\n${details.overview || '*مفيش نبذة متاحة.*'}\n\n` +
            `*معرف IMDB:* ${details.external_ids?.imdb_id || '*غير متاح*'}\n`;
    }

    return info;
};

const sendMediaInfo = async (sock, noWa, mediaDetails, mediaInfo, message, firstResult, text) => {
    const posterUrl = mediaDetails.poster_path
        ? `${TMDB_IMAGE_BASE_URL}${mediaDetails.poster_path}`
        : 'https://via.placeholder.com/500x750?text=No+Poster+Available';

    try {
        console.log("movie.js: Sending image message with caption");
        await sock.sendMessage(noWa, {
            image: { url: posterUrl },
            caption: mediaInfo + `\n\n${BOT_SIGNATURE}`
        }, { quoted: message });
        console.log("movie.js: Image message sent successfully");
    } catch (sendError) {
        console.error(`movie.js: Error sending image message: ${sendError.message}`);
        await sock.sendMessage(noWa, {
            text: mediaInfo + `\n\n${BOT_SIGNATURE}`
        }, { quoted: message });
    }

    try {
        console.log("movie.js: Searching for trailers on YouTube...");
        const query = `${text} official trailer`; // استعلام البحث باسم الفيلم + "official trailer"
        const trailerUrl = await searchTrailerOnYoutube(query);
        console.log(`movie.js: Trailer URL from YouTube: ${trailerUrl}`);

        // إرسال رسالة أثناء التحميل
        console.log("movie.js: Sending 'loading' message");
        await sock.sendMessage(noWa, {
            text: `*يتم تحميل التريلر 🚀..*`
        });
        console.log("movie.js: 'Loading' message sent");

        // جلب رابط الـ thumbnail من يوتيوب
        const thumbnailInfo = getYoutubeThumbnail(trailerUrl);
        console.log(`movie.js: Video ID: ${thumbnailInfo.videoId}`);

        // تحميل الـ thumbnail - تجربة عدة دقات
        console.log("movie.js: Fetching thumbnail - trying various resolutions");
        let thumbnailBuffer = null;
        let thumbnailFetched = false;

        for (const thumbnailUrl of thumbnailInfo.thumbnails) {
            try {
                console.log(`movie.js: Trying thumbnail URL: ${thumbnailUrl}`);
                const thumbnailResponse = await axios.get(thumbnailUrl, { responseType: 'arraybuffer' });
                thumbnailBuffer = Buffer.from(thumbnailResponse.data, 'binary');
                console.log(`movie.js: Thumbnail fetched successfully, size: ${thumbnailBuffer.length} bytes`);
                thumbnailFetched = true;
                break;
            } catch (thumbError) {
                console.log(`movie.js: Failed to fetch thumbnail from ${thumbnailUrl}: ${thumbError.message}`);
            }
        }

        if (!thumbnailFetched) {
            console.log("movie.js: Could not fetch any thumbnail");
            throw new Error("مش عارف أجيب الـ thumbnail بأي دقة 😞");
        }

        // تحميل الفيديو بجودة 360p
        console.log("movie.js: Starting video download");
        const videoStream = ytdl(trailerUrl, {
            quality: '18', // 360p
            filter: 'audioandvideo'
        });

        // مسار مؤقت للفيديو
        const tempVideoPath = path.join(__dirname, `temp_${thumbnailInfo.videoId}.mp4`);
        const finalVideoPath = path.join(__dirname, `final_${thumbnailInfo.videoId}.mp4`);

        // حفظ الفيديو مؤقتًا من الـ stream
        console.log("movie.js: Saving video to temp file");
        await new Promise((resolve, reject) => {
            const fileStream = fs.createWriteStream(tempVideoPath);
            videoStream.pipe(fileStream);
            fileStream.on('finish', resolve);
            fileStream.on('error', reject);
        });
        console.log("movie.js: Video saved to temp file");

        // حفظ الـ thumbnail كملف مؤقت
        const tempThumbnailPath = path.join(__dirname, `thumb_${thumbnailInfo.videoId}.jpg`);
        console.log("movie.js: Saving thumbnail to temp file");
        fs.writeFileSync(tempThumbnailPath, thumbnailBuffer);
        console.log(`movie.js: Thumbnail saved to ${tempThumbnailPath}`);

        // إضافة الـ thumbnail كغلاف فقط باستخدام ffmpeg
        console.log("movie.js: Adding thumbnail as cover using ffmpeg");
        try {
            await new Promise((resolve, reject) => {
                ffmpeg()
                    .input(tempVideoPath)
                    .input(tempThumbnailPath)
                    .outputOptions([
                        '-c:v copy',  // نسخ الفيديو بدون إعادة ترميز
                        '-c:a copy',  // نسخ الصوت بدون إعادة ترميز
                        '-map 0:v',   // استخدام الفيديو الأصلي
                        '-map 0:a?',  // استخدام الصوت لو موجود
                        '-map 1:v',   // إضافة الـ thumbnail
                        '-disposition:v:1 attached_pic'  // تعيين الـ thumbnail كغلاف
                    ])
                    .save(finalVideoPath)
                    .on('end', () => {
                        console.log("movie.js: FFmpeg added thumbnail as cover");
                        resolve();
                    })
                    .on('error', (err) => {
                        console.error(`movie.js: FFmpeg error: ${err.message}`);
                        reject(err);
                    });
            });
        } catch (ffmpegError) {
            console.error(`movie.js: Failed to add thumbnail: ${ffmpegError.message}`);
            fs.copyFileSync(tempVideoPath, finalVideoPath);
            console.log("movie.js: Copied original video as fallback");
        }

        // إرسال الفيديو النهائي مع الغلاف
        console.log("movie.js: Sending final video with thumbnail");
        await sock.sendMessage(noWa, {
            video: { url: finalVideoPath },
            caption: `*تريلر ${mediaDetails.title || mediaDetails.name} جاهز! 🎬*\n*استمتع بالمشاهدة يا وحش 🔥*`
        });
        console.log("movie.js: Final video sent successfully");

        // حذف الملفات المؤقتة
        console.log("movie.js: Cleaning up temp files");
        try {
            fs.unlinkSync(tempVideoPath);
            fs.unlinkSync(tempThumbnailPath);
            fs.unlinkSync(finalVideoPath);
            console.log("movie.js: Temp files deleted");
        } catch (cleanupError) {
            console.error(`movie.js: Error cleaning up temp files: ${cleanupError.message}`);
        }

    } catch (videoError) {
        console.error(`movie.js: Error fetching or sending video: ${videoError.message}`);
        await sock.sendMessage(noWa, {
            text: `*📽️ مفيش تريلر متاح للعمل ده حاليًا، يمكن يكون مش موجود أو فيه مشكلة تقنية 😕*`
        });
    }
};

movieCommand.help = ['movie <movie name>', 'tv <tv show name>'];
movieCommand.tags = ['tools', 'entertainment', 'media'];
movieCommand.command = /^(imdb|movie|فيلم|مسلسل|tv|show)$/i;

module.exports = { movieCommand };
