require("dotenv").config();
const { downloadMediaMessage } = require("@whiskeysockets/baileys");
const { exec } = require("child_process");
const fs = require("fs");
const path = require("path");
const webp = require("node-webpmux");
const crypto = require("crypto");
const { sendErrorMessage } = require("./messageUtils");

const stickerArabicCommand = async (sock, chatId, message, sender = null) => {
    try {
        let mediaMessage;
        let currentMessage = message;

        if (currentMessage.message?.extendedTextMessage?.contextInfo?.quotedMessage) {
            const quotedMessage = currentMessage.message.extendedTextMessage.contextInfo.quotedMessage;
            mediaMessage = quotedMessage.imageMessage || quotedMessage.videoMessage || quotedMessage.documentMessage;
            currentMessage = { message: quotedMessage };
        } else {
            mediaMessage = currentMessage.message?.imageMessage || currentMessage.message?.videoMessage || currentMessage.message?.documentMessage;
        }

        if (!mediaMessage) {
            await sendErrorMessage(sock, chatId, "📌 ابعت صورة 🖼️ أو فيديو 📽️ أو GIF متحرك 🎞️ مع \`.sticker` علشان أحوله لملصق 🌟");
            return;
        }

        const mediaBuffer = await downloadMediaMessage(currentMessage, "buffer", {}, {
            logger: undefined,
            reuploadRequest: sock.updateMediaMessage
        });

        if (!mediaBuffer) {
            await sendErrorMessage(sock, chatId, "❌ مش عارف أحمل الوسائط 😕 جرب تاني بعد شوية 🔄");
            return;
        }

        const packInfo = {
            packName: process.env.STICKER_PACK_NAME || "ملصقات Zaky AI",
            packPublisher: process.env.STICKER_PUBLISHER || "Zaky AI"
        };

        await createAndSendSticker(sock, chatId, mediaBuffer, mediaMessage, packInfo);

    } catch (error) {
        console.error("❌ حدث خطأ أثناء إنشاء الملصق:", error);
        await sendErrorMessage(sock, chatId, "❌ معلش، حصل مشكلة وأنا بعمل الملصق 😔 جرب تاني بعد شوية 🙏");
    }
};


const takeCommand = async (sock, chatId, message, sender) => {
    try {
        let mediaMessage;
        let currentMessage = message;
        let customName = null;
        let customNumber = null;
        let usedDefaultSenderInfo = false;

        // تحقق من وجود معلومات المرسل وإنشائها إذا كانت مفقودة
        if (!sender || typeof sender !== 'object') {
            sender = {
                id: message.key.remoteJid,
                name: message.pushName || "مستخدم",
                pushName: message.pushName || "مستخدم"
            };
        }

        // استخراج الاسم والرقم من النص
        let msgText = '';

        if (message.message?.conversation) {
            msgText = message.message.conversation;
        } else if (message.message?.extendedTextMessage?.text) {
            msgText = message.message.extendedTextMessage.text;
        } else if (message.message?.imageMessage?.caption) {
            msgText = message.message.imageMessage.caption;
        } else if (message.message?.videoMessage?.caption) {
            msgText = message.message.videoMessage.caption;
        }

        console.log(`استلمت رسالة: "${msgText}"`); // سجل للتصحيح

        // التحقق من وجود معلومات إضافية بعد .take
        const takeRegex = /^\.take\s+(.+)$/i;
        if (takeRegex.test(msgText)) {
            const params = msgText.replace(takeRegex, '$1').trim();
            console.log(`معلومات بعد .take: "${params}"`); // سجل للتصحيح

            // البحث عن رقم هاتف في النص (افتراض أنه على الأقل 10 أرقام)
            const phoneMatch = params.match(/(\d{10,})/);

            if (phoneMatch) {
                customNumber = phoneMatch[1];
                // استخراج الاسم بعد إزالة الرقم
                customName = params.replace(phoneMatch[0], '').trim();
            } else {
                customName = params;
            }
        } else if (msgText.trim() === '.take') {
            // إذا كان الأمر .take فقط بدون معلومات إضافية
            usedDefaultSenderInfo = true;
        }

        // التعامل مع الصورة التي تحتوي على كابشن
        if (message.message?.imageMessage && message.message?.imageMessage?.caption?.startsWith('.take')) {
            mediaMessage = message.message.imageMessage;

            // استخراج المعلومات من الكابشن
            const caption = message.message.imageMessage.caption;
            const captionParams = caption.replace(/^\.take\s+/, '').trim();

            if (captionParams) {
                // البحث عن رقم هاتف في النص
                const phoneMatch = captionParams.match(/(\d{10,})/);

                if (phoneMatch) {
                    customNumber = phoneMatch[1];
                    // استخراج الاسم بعد إزالة الرقم
                    customName = captionParams.replace(phoneMatch[0], '').trim();
                } else {
                    customName = captionParams;
                }
            }
        }
        // التعامل مع الفيديو الذي يحتوي على كابشن
        else if (message.message?.videoMessage && message.message?.videoMessage?.caption?.startsWith('.take')) {
            mediaMessage = message.message.videoMessage;

            // استخراج المعلومات من الكابشن
            const caption = message.message.videoMessage.caption;
            const captionParams = caption.replace(/^\.take\s+/, '').trim();

            if (captionParams) {
                // البحث عن رقم هاتف في النص
                const phoneMatch = captionParams.match(/(\d{10,})/);

                if (phoneMatch) {
                    customNumber = phoneMatch[1];
                    // استخراج الاسم بعد إزالة الرقم
                    customName = captionParams.replace(phoneMatch[0], '').trim();
                } else {
                    customName = captionParams;
                }
            }
        }
        // التحقق مما إذا كانت الرسالة رداً على رسالة أخرى
        else if (currentMessage.message?.extendedTextMessage?.contextInfo?.quotedMessage) {
            const quotedMessage = currentMessage.message.extendedTextMessage.contextInfo.quotedMessage;
            mediaMessage = quotedMessage.imageMessage ||
                         quotedMessage.videoMessage ||
                         quotedMessage.documentMessage ||
                         quotedMessage.stickerMessage; // إضافة دعم للملصقات
            currentMessage = { message: quotedMessage };
        } else {
            mediaMessage = currentMessage.message?.imageMessage ||
                         currentMessage.message?.videoMessage ||
                         currentMessage.message?.documentMessage ||
                         currentMessage.message?.stickerMessage; // إضافة دعم للملصقات
        }

        if (!mediaMessage) {
            await sendErrorMessage(sock, chatId, "📌 ابعت صورة 🖼️ أو فيديو 📽️ أو GIF متحرك 🎞️ أو ملصق 🏷️ مع \`.take` علشان أعمل ملصق مخصص 🌟");
            return;
        }

        const mediaBuffer = await downloadMediaMessage(currentMessage, "buffer", {}, {
            logger: undefined,
            reuploadRequest: sock.updateMediaMessage
        });

        if (!mediaBuffer) {
            await sendErrorMessage(sock, chatId, "❌ مش عارف أحمل الوسائط 😕 جرب تاني بعد شوية 🔄");
            return;
        }

        let packInfo;

        if (usedDefaultSenderInfo) {
            // إذا استخدم الأمر .take فقط - استخدم معلومات المرسل
            const senderName = sender.name || sender.pushName || "مستخدم";
            const senderNumber = (sender.id || "").split('@')[0] || "مجهول";
            packInfo = {
                packName: senderName,
                packPublisher: senderNumber
            };
        } else {
            // إذا حدد المستخدم اسم مخصص
            if (customNumber) {
                // إذا حدد المستخدم اسم ورقم
                packInfo = {
                    packName: customName,
                    packPublisher: customNumber
                };
            } else {
                // إذا حدد المستخدم اسم فقط - استخدم اسمه فقط ولا تضع قيمة افتراضية
                packInfo = {
                    packName: customName,
                    packPublisher: ""  // لا تستخدم أي قيمة افتراضية
                };
            }
        }

        await createAndSendSticker(sock, chatId, mediaBuffer, mediaMessage, packInfo);

        // رسالة التأكيد بناءً على البيانات المتوفرة
        if (usedDefaultSenderInfo) {
            // إذا كان الأمر .take فقط
            await sock.sendMessage(chatId, {
                text: `✅ تم عمل الملصق باسمك ورقمك 🎉`
            });
        } else if (customName && customNumber) {
            // إذا تم تحديد اسم ورقم مخصصين
            await sock.sendMessage(chatId, {
                text: `✅ تم عمل الملصق باسم "${customName}" ورقم "${customNumber}" 🎉`
            });
        } else if (customName) {
            // إذا تم تحديد اسم مخصص فقط
            await sock.sendMessage(chatId, {
                text: `✅ تم عمل الملصق باسم "${customName}" 🎉`
            });
        }

    } catch (error) {
        console.error("❌ حدث خطأ أثناء إنشاء الملصق:", error);
        await sendErrorMessage(sock, chatId, "❌ معلش، حصل مشكلة وأنا بعمل الملصق 😔 جرب تاني بعد شوية 🙏");
    }
};

const createAndSendSticker = async (sock, chatId, mediaBuffer, mediaMessage, packInfo) => {
    const tmpDir = path.join(process.cwd(), "tmp");
    if (!fs.existsSync(tmpDir)) fs.mkdirSync(tmpDir, { recursive: true });

    const tempInput = path.join(tmpDir, `temp_${Date.now()}`);
    const tempOutput = path.join(tmpDir, `sticker_${Date.now()}.webp`);

    fs.writeFileSync(tempInput, mediaBuffer);

    try {
        // تحديد ما إذا كان الملف متحرك (GIF أو فيديو أو ستيكر متحرك)
        const isAnimated = mediaMessage.mimetype?.includes("gif") || 
                          mediaMessage.seconds > 0 || 
                          (mediaMessage.mimetype?.includes("webp") && 
                          (mediaMessage.isAnimated || 
                           (Buffer.isBuffer(mediaBuffer) && 
                            (mediaBuffer.includes(Buffer.from("ANIM")) || 
                             mediaBuffer.includes(Buffer.from("ANMF"))))));

        // التعامل مع الملصقات المتحركة
        if (isAnimated) {
            if (mediaMessage.mimetype?.includes("webp")) {
                // للملصقات المتحركة WebP، نستخدم أداة WebPMux مباشرة
                try {
                    // نسخ الملف الأصلي إلى ملف الإخراج مؤقتًا
                    fs.copyFileSync(tempInput, tempOutput);
                    
                    // إضافة metadata فقط للملصق المتحرك
                    const img = new webp.Image();
                    await img.load(fs.readFileSync(tempOutput));
                    
                    // إضافة معلومات EXIF
                    const json = {
                        "sticker-pack-id": crypto.randomBytes(32).toString("hex"),
                        "sticker-pack-name": packInfo.packName,
                        "sticker-pack-publisher": packInfo.packPublisher,
                        "emojis": (process.env.STICKER_EMOJIS || "🇪🇬,😎,😂").split(",")
                    };
                    
                    const exifAttr = Buffer.from([0x49, 0x49, 0x2A, 0x00, 0x08, 0x00, 0x00, 0x00, 0x01, 0x00, 0x41, 0x57, 0x07, 0x00, 0x00, 0x00, 0x00, 0x00, 0x16, 0x00, 0x00, 0x00]);
                    const jsonBuffer = Buffer.from(JSON.stringify(json), "utf8");
                    const exif = Buffer.concat([exifAttr, jsonBuffer]);
                    exif.writeUIntLE(jsonBuffer.length, 14, 4);
                    
                    img.exif = exif;
                    const finalBuffer = await img.save(null);
                    
                    // إرسال الملصق
                    await sock.sendMessage(chatId, {
                        sticker: finalBuffer,
                        contextInfo: {
                            forwardingScore: 999,
                            isForwarded: true,
                            externalAdReply: {
                                title: process.env.EXTERNAL_AD_TITLE || "🤖 Zaky AI 🤖",
                                body: process.env.EXTERNAL_AD_BODY || "للمساعدة أو الاستفسارات",
                                mediaType: Number(process.env.EXTERNAL_AD_MEDIA_TYPE) || 2,
                                thumbnail: fs.readFileSync(path.join(process.cwd(), process.env.EXTERNAL_AD_THUMBNAIL_PATH || "./assets/zakyai.jpg")),
                                mediaUrl: process.env.EXTERNAL_AD_MEDIA_URL || "https://wa.me/201280779419",
                                sourceUrl: process.env.EXTERNAL_AD_SOURCE_URL || "https://wa.me/201280779419"
                            }
                        }
                    });
                    
                    // تنظيف الملفات
                    if (fs.existsSync(tempInput)) fs.unlinkSync(tempInput);
                    if (fs.existsSync(tempOutput)) fs.unlinkSync(tempOutput);
                    
                    return; // الخروج بعد النجاح
                } catch (error) {
                    console.error("فشل في معالجة ملصق WebP متحرك، جار المحاولة بطريقة بديلة:", error);
                    // سنتابع مع الطريقة البديلة إذا فشلت هذه الطريقة
                }
            }
            
            // استخدام FFmpeg للتحويل من فيديو أو GIF إلى WebP متحرك
            const tempGif = path.join(tmpDir, `temp_gif_${Date.now()}.gif`);
            let ffmpegCommand;
            
            // إذا كان المدخل فيديو، نحوله مباشرة إلى WebP
            if (mediaMessage.mimetype?.includes("video") || mediaMessage.seconds > 0) {
                ffmpegCommand = `ffmpeg -i "${tempInput}" -vf "fps=${process.env.STICKER_FPS || 15},scale=${process.env.STICKER_SCALE || 512}:${process.env.STICKER_SCALE || 512}:force_original_aspect_ratio=decrease,pad=${process.env.STICKER_SCALE || 512}:${process.env.STICKER_SCALE || 512}:(ow-iw)/2:(oh-ih)/2:color=#00000000" -c:v libwebp -lossless 0 -compression_level ${process.env.STICKER_COMPRESSION_LEVEL || 6} -q:v ${process.env.STICKER_QUALITY || 50} -loop 0 -preset picture -an -vsync 0 "${tempOutput}"`;
            } 
            // إذا كان GIF أو WebP متحرك، نحاول تحويله إلى GIF ثم إلى WebP
            else {
                // أولاً: نحاول استخراج الإطارات (frames) مباشرة
                ffmpegCommand = `ffmpeg -i "${tempInput}" -vf "fps=${process.env.STICKER_FPS || 15},scale=${process.env.STICKER_SCALE || 512}:${process.env.STICKER_SCALE || 512}:force_original_aspect_ratio=decrease,pad=${process.env.STICKER_SCALE || 512}:${process.env.STICKER_SCALE || 512}:(ow-iw)/2:(oh-ih)/2:color=#00000000" -c:v libwebp -lossless 0 -compression_level ${process.env.STICKER_COMPRESSION_LEVEL || 6} -q:v ${process.env.STICKER_QUALITY || 50} -loop 0 -preset picture -an -vsync 0 "${tempOutput}"`;
            }
            
            try {
                await new Promise((resolve, reject) => {
                    exec(ffmpegCommand, { maxBuffer: 10 * 1024 * 1024 }, (error, stdout, stderr) => {
                        if (error) {
                            console.error("خطأ في تنفيذ FFmpeg:", error);
                            console.log("stderr:", stderr);
                            return reject(error);
                        }
                        resolve();
                    });
                });
                
                // في حالة الفشل أو عدم وجود الملف المُخرج
                if (!fs.existsSync(tempOutput)) {
                    throw new Error("لم يتم إنشاء ملف الإخراج");
                }
            } catch (error) {
                console.error("فشل في تنفيذ الأمر الأول، جار تجربة طريقة بديلة...", error);
                
                // الطريقة البديلة: تحويل المدخل إلى GIF ثم إلى WebP
                try {
                    await new Promise((resolve, reject) => {
                        exec(`ffmpeg -i "${tempInput}" -vf "fps=${process.env.STICKER_FPS || 15},scale=${process.env.STICKER_SCALE || 512}:${process.env.STICKER_SCALE || 512}:force_original_aspect_ratio=decrease" "${tempGif}"`, { maxBuffer: 10 * 1024 * 1024 }, (error) => {
                            if (error) {
                                console.error("خطأ في تحويل الملف إلى GIF:", error);
                                return reject(error);
                            }
                            resolve();
                        });
                    });
                    
                    await new Promise((resolve, reject) => {
                        exec(`ffmpeg -i "${tempGif}" -vf "pad=${process.env.STICKER_SCALE || 512}:${process.env.STICKER_SCALE || 512}:(ow-iw)/2:(oh-ih)/2:color=#00000000" -c:v libwebp -lossless 0 -compression_level ${process.env.STICKER_COMPRESSION_LEVEL || 6} -q:v ${process.env.STICKER_QUALITY || 50} -loop 0 -preset picture -an -vsync 0 "${tempOutput}"`, { maxBuffer: 10 * 1024 * 1024 }, (error) => {
                            if (error) {
                                console.error("خطأ في تحويل GIF إلى WebP:", error);
                                return reject(error);
                            }
                            resolve();
                        });
                    });
                    
                    // حذف ملف GIF المؤقت
                    if (fs.existsSync(tempGif)) {
                        fs.unlinkSync(tempGif);
                    }
                } catch (error) {
                    console.error("فشلت جميع الطرق البديلة:", error);
                    throw error; // رمي الخطأ للتعامل معه في الـ catch الخارجي
                }
            }
        } else {
            // معالجة الصور الثابتة
            const ffmpegCommand = `ffmpeg -i "${tempInput}" -vf "scale=${process.env.STICKER_SCALE || 512}:${process.env.STICKER_SCALE || 512}:force_original_aspect_ratio=decrease,format=rgba,pad=${process.env.STICKER_SCALE || 512}:${process.env.STICKER_SCALE || 512}:(ow-iw)/2:(oh-ih)/2:color=#00000000" -c:v libwebp -preset default -loop 0 -q:v ${process.env.STICKER_QUALITY || 50} -compression_level ${process.env.STICKER_COMPRESSION_LEVEL || 6} "${tempOutput}"`;
            
            await new Promise((resolve, reject) => {
                exec(ffmpegCommand, { maxBuffer: 10 * 1024 * 1024 }, (error) => {
                    if (error) {
                        console.error("خطأ في تحويل الصورة إلى WebP:", error);
                        return reject(error);
                    }
                    resolve();
                });
            });
        }

        // إذا لم يتم إنشاء الملف بنجاح، نرسل رسالة خطأ ونخرج
        if (!fs.existsSync(tempOutput)) {
            await sendErrorMessage(sock, chatId, "❌ حدث خطأ أثناء معالجة الملصق. يرجى المحاولة مرة أخرى.");
            if (fs.existsSync(tempInput)) fs.unlinkSync(tempInput);
            return;
        }

        // إضافة معلومات الملصق (EXIF)
        try {
            const webpBuffer = fs.readFileSync(tempOutput);
            const img = new webp.Image();
            await img.load(webpBuffer);

            const json = {
                "sticker-pack-id": crypto.randomBytes(32).toString("hex"),
                "sticker-pack-name": packInfo.packName,
                "sticker-pack-publisher": packInfo.packPublisher,
                "emojis": (process.env.STICKER_EMOJIS || "🇪🇬,😎,😂").split(",")
            };

            const exifAttr = Buffer.from([0x49, 0x49, 0x2A, 0x00, 0x08, 0x00, 0x00, 0x00, 0x01, 0x00, 0x41, 0x57, 0x07, 0x00, 0x00, 0x00, 0x00, 0x00, 0x16, 0x00, 0x00, 0x00]);
            const jsonBuffer = Buffer.from(JSON.stringify(json), "utf8");
            const exif = Buffer.concat([exifAttr, jsonBuffer]);
            exif.writeUIntLE(jsonBuffer.length, 14, 4);

            img.exif = exif;
            const finalBuffer = await img.save(null);

            // إرسال الملصق
            await sock.sendMessage(chatId, {
                sticker: finalBuffer,
                contextInfo: {
                    forwardingScore: 999,
                    isForwarded: true,
                    externalAdReply: {
                        title: process.env.EXTERNAL_AD_TITLE || "🤖 Zaky AI 🤖",
                        body: process.env.EXTERNAL_AD_BODY || "للمساعدة أو الاستفسارات",
                        mediaType: Number(process.env.EXTERNAL_AD_MEDIA_TYPE) || 2,
                        thumbnail: fs.readFileSync(path.join(process.cwd(), process.env.EXTERNAL_AD_THUMBNAIL_PATH || "./assets/zakyai.jpg")),
                        mediaUrl: process.env.EXTERNAL_AD_MEDIA_URL || "https://wa.me/201280779419",
                        sourceUrl: process.env.EXTERNAL_AD_SOURCE_URL || "https://wa.me/201280779419"
                    }
                }
            });
        } catch (error) {
            console.error("❌ خطأ في إضافة معلومات EXIF:", error);
            // إذا فشل إضافة معلومات EXIF، نرسل الملصق بدون معلومات
            await sock.sendMessage(chatId, {
                sticker: fs.readFileSync(tempOutput)
            });
        }
    } catch (error) {
        console.error("❌ خطأ في إنشاء الملصق:", error);
        await sendErrorMessage(sock, chatId, "❌ معلش، حصل مشكلة وأنا بعمل الملصق 😔 جرب تاني بعد شوية 🙏");
    } finally {
        // تنظيف الملفات المؤقتة
        if (fs.existsSync(tempInput)) fs.unlinkSync(tempInput);
        if (fs.existsSync(tempOutput)) fs.unlinkSync(tempOutput);
    }
};

const handleStickerCommands = async (sock, chatId, message, sender) => {
    try {
        let command = "";

        if (message.message?.conversation) {
            command = message.message.conversation.split(" ")[0].toLowerCase();
        } else if (message.message?.extendedTextMessage?.text) {
            command = message.message.extendedTextMessage.text.split(" ")[0].toLowerCase();
        } else if (message.message?.imageMessage?.caption) {
            command = message.message.imageMessage.caption.split(" ")[0].toLowerCase();
        } else if (message.message?.videoMessage?.caption) {
            command = message.message.videoMessage.caption.split(" ")[0].toLowerCase();
        }

        switch (command) {
            case ".sticker":
            case ".ملصق":
                await stickerArabicCommand(sock, chatId, message, sender);
                break;
            case ".take":
            case ".أخذ":
                await takeCommand(sock, chatId, message, sender);
                break;
            default:
                break;
        }
    } catch (error) {
        console.error("❌ خطأ في معالجة أوامر الملصقات:", error);
        await sendErrorMessage(sock, chatId, "❌ حصل مشكلة وأنا بشتغل على الأمر 😕 جرب تاني بعد شوية 🔄");
    }
};

module.exports = {
    stickerArabicCommand,
    takeCommand,
    handleStickerCommands
};
