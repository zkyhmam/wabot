// كود secretMessages.js

const { createHash, randomBytes } = require('crypto');
const fs = require('fs');
const path = require('path');
const { LRUCache } = require('lru-cache');

// 1. هياكل البيانات المتقدمة
const conversationCache = new LRUCache({ max: 1000 });
const messageIndex = new Map();

// 2. نظام التذاكر الذكي
class ConversationTicket {
    constructor(sender, receiver) {
        this.id = `TKT-${Date.now()}-${randomBytes(3).toString('hex')}`;
        this.chainId = `CHAIN-${randomBytes(3).toString('hex')}`;
        this.sender = sender;
        this.receiver = receiver;
        this.watermark = this.generateWatermark();
        this.messages = new Map();
        this.timestamps = {
            created: Date.now(),
            updated: Date.now()
        };
        console.log(`[Ticket] Created ticket ${this.id} for sender: ${sender}, receiver: ${receiver}, watermark: ${this.watermark}`); // [لوج جديد] تسجيل إنشاء التذكرة
    }

    generateWatermark() {
        const watermark = createHash('sha256')
            .update(`${this.sender}${this.receiver}${Date.now()}`)
            .digest('hex')
            .substring(0, 8)
            .toUpperCase();
        console.log(`[Ticket] Generated watermark: ${watermark}`); // [لوج جديد] تسجيل توليد العلامة المائية
        return watermark;
    }


    addMessage(message, isReply = false, senderJid = null, receiverJid = null, type = 'unknown') { // [تعديل!] نضيف معلومات المرسل والمستقبل ونوع الرسالة
        const msgId = `MSG-${randomBytes(3).toString('hex')}`;
        this.messages.set(msgId, {
            id: msgId,
            content: message,
            timestamp: Date.now(),
            isReply,
            senderJid: senderJid, // [معلومة جديدة!] رقم مرسل الرسالة دي
            receiverJid: receiverJid, // [معلومة جديدة!] رقم مستقبل الرسالة دي
            type: type, // [معلومة جديدة!] نوع الرسالة
            context: {
                prev: this.lastMessage,
                next: null
            }
        });

        if (this.lastMessage) {
            this.messages.get(this.lastMessage).context.next = msgId;
        }
        this.lastMessage = msgId;
        this.timestamps.updated = Date.now();
        console.log(`[Ticket] Added message ${msgId} to ticket ${this.id}, isReply: ${isReply}, type: ${type}`); // [لوج جديد] تسجيل إضافة رسالة للتذكرة مع النوع
        return msgId;
    }
}

// 3. نظام التخزين الهرمي
const storage = {
    save: (ticket) => {
        const dir = path.join(__dirname, 'conv',
            ticket.receiver.slice(2, 6),
            ticket.receiver.slice(6, 10)
        );
        fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(path.join(dir, `${ticket.id}.json`), JSON.stringify(ticket));
        console.log(`[Storage] Saved ticket ${ticket.id} to storage`); // [لوج جديد] تسجيل حفظ التذكرة في التخزين
    },

    load: (ticketId) => {
        try {
            const prefix = ticketId.split('-')[2].slice(0, 4);
            const file = path.join(__dirname, 'conv',
                prefix.slice(0, 2),
                prefix.slice(2, 4),
                `${ticketId}.json`
            );
            const data = fs.readFileSync(file, 'utf8');
            const ticket = JSON.parse(data);
            console.log(`[Storage] Loaded ticket ${ticketId} from storage`); // [لوج جديد] تسجيل تحميل التذكرة من التخزين
            return ticket;
        } catch (error) {
            console.error("[Storage] Error loading ticket from storage:", error);
            return null; // Return null if ticket not found or error occurs
        }
    },
    loadByWatermark: (watermark) => {
        console.log(`[Storage] Searching for ticket with watermark: ${watermark}`); // [لوج جديد] تسجيل البحث عن التذكرة بالعلامة المائية
        for (let prefixDir of fs.readdirSync(path.join(__dirname, 'conv'))) {
            for (let suffixDir of fs.readdirSync(path.join(__dirname, 'conv', prefixDir))) {
                const dir = path.join(__dirname, 'conv', prefixDir, suffixDir);
                const files = fs.readdirSync(dir);
                for (let file of files) {
                    try {
                        const filePath = path.join(dir, file);
                        const data = fs.readFileSync(filePath, 'utf8');
                        const ticket = JSON.parse(data);
                        if (ticket.watermark === watermark) {
                            console.log(`[Storage] Found ticket ${ticket.id} by watermark ${watermark} in storage`); // [لوج جديد] تسجيل العثور على التذكرة بالعلامة المائية
                            return ticket;
                        }
                    } catch (error) {
                        console.error(`[Storage] Error reading file ${file}:`, error);
                    }
                }
            }
        }
        console.log(`[Storage] Ticket with watermark ${watermark} not found in storage`); // [لوج جديد] تسجيل عدم العثور على التذكرة بالعلامة المائية
        return null; // Ticket not found
    }
};

// 4. إدارة المحادثات
class ConversationManager {
    constructor() {
        this.tickets = new Map();
        this.loadActiveTickets();
        console.log(`[ConversationManager] Initialized Conversation Manager`); // [لوج جديد] تسجيل تهيئة مدير المحادثات
    }

    async loadActiveTickets() {
        // Improved loadActiveTickets to actually load tickets into memory on startup
        const convDir = path.join(__dirname, 'conv');
        if (fs.existsSync(convDir)) { // Check if the directory exists
            for (let prefixDir of fs.readdirSync(convDir)) {
                const prefixDirPath = path.join(convDir, prefixDir);
                if (fs.statSync(prefixDirPath).isDirectory()) { // Ensure it's a directory
                    for (let suffixDir of fs.readdirSync(prefixDirPath)) {
                        const suffixDirPath = path.join(prefixDirPath, suffixDir);
                        if (fs.statSync(suffixDirPath).isDirectory()) { // Ensure it's a directory
                            const files = fs.readdirSync(suffixDirPath);
                            for (let file of files) {
                                if (file.endsWith('.json')) {
                                    const filePath = path.join(suffixDirPath, file);
                                    try {
                                        const data = fs.readFileSync(filePath, 'utf8');
                                        const ticket = JSON.parse(data);
                                        if (ticket && ticket.id) {
                                            this.tickets.set(ticket.id, ticket); // Load into active tickets
                                            messageIndex.set(ticket.watermark, ticket.id); // Index by watermark
                                            conversationCache.set(ticket.id, ticket); // Load into cache
                                            console.log(`[ConversationManager] Loaded active ticket ${ticket.id} from storage on startup`); // [لوج جديد] تسجيل تحميل تذكرة نشطة عند بدء التشغيل
                                        } else {
                                            console.warn(`[ConversationManager] Invalid ticket data in ${file}`);
                                        }
                                    } catch (error) {
                                        console.error(`[ConversationManager] Error loading ticket from ${file}:`, error);
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        console.log(`[ConversationManager] Loaded ${this.tickets.size} active tickets on startup.`);

    }

    createTicket(sender, receiver) {
        const ticket = new ConversationTicket(sender, receiver);
        this.tickets.set(ticket.id, ticket);
        storage.save(ticket);
        console.log(`[ConversationManager] Created and cached ticket ${ticket.id} for sender: ${sender}, receiver: ${receiver}`); // [لوج جديد] تسجيل إنشاء وتخزين التذكرة في الذاكرة المؤقتة
        return ticket;
    }

    findTicketByWatermark(watermark) {
        console.log(`[ConversationManager] Searching for ticket by watermark: ${watermark}`); // [لوج جديد] تسجيل البحث عن التذكرة بالعلامة المائية
        if (messageIndex.has(watermark)) {
            const ticketId = messageIndex.get(watermark);
            if (conversationCache.has(ticketId)) {
                console.log(`[ConversationManager] Found ticket ${ticketId} in cache by watermark: ${watermark}`); // [لوج جديد] تسجيل العثور على التذكرة في الذاكرة المؤقتة بالعلامة المائية
                return conversationCache.get(ticketId); // Fastest path: check cache first
            } else {
                // If in index but not in cache, try to load from storage and then cache
                let ticket = storage.load(ticketId);
                if (ticket) {
                    conversationCache.set(ticketId, ticket); // Cache loaded ticket
                    console.log(`[ConversationManager] Loaded ticket ${ticketId} from storage and cached by watermark: ${watermark}`); // [لوج جديد] تسجيل تحميل وتخزين التذكرة من التخزين المؤقتة بالعلامة المائية
                    return ticket;
                }
            }
        } else {
            const ticket = storage.loadByWatermark(watermark); // Check storage if not in index/cache
            if (ticket) {
                this.tickets.set(ticket.id, ticket); // Add to active tickets
                messageIndex.set(ticket.watermark, ticket.id); // Add to index
                conversationCache.set(ticket.id, ticket); // Cache it
                console.log(`[ConversationManager] Loaded ticket ${ticket.id} from storage, cached, and indexed by watermark: ${watermark}`); // [لوج جديد] تسجيل تحميل وتخزين وفهرسة التذكرة من التخزين المؤقتة بالعلامة المائية
                return ticket;
            }
        }

        console.log(`[ConversationManager] Ticket not found by watermark: ${watermark}`); // [لوج جديد] تسجيل عدم العثور على التذكرة بالعلامة المائية
        return null; // Not found in cache, index, or storage
    }


}
const conversationManager = new ConversationManager(); // Create a single instance


// 5. معالجة الرسائل
async function sendSecretMessage(sock, senderJid, recipientJid, messageText, isAnonymous) {
    try {
        if (!recipientJid.endsWith('@s.whatsapp.net')) {
            recipientJid += '@s.whatsapp.net';
        }

        const ticket = conversationManager.createTicket(senderJid, recipientJid);
        const msgContent = `*رسالة سرية من (${ticket.watermark}) 💌*\n\n> ${messageText}\n\n*_رد على الرسالة مباشرة وردك هيوصل للراسل_*`;

        console.log("[sendSecretMessage] Message content to be sent:", msgContent); // [لوج جديد] تسجيل محتوى الرسالة السرية قبل الإرسال

        const messageContent = {
            text: msgContent,
            contextInfo: {
                mentionedJid: [recipientJid],
                forwardingScore: 999,
                isForwarded: true,
                ...(isAnonymous && { originalSender: senderJid }),
                messageChainId: ticket.chainId, // Include chainId if still needed for other logic
                originalSender: senderJid // Keep originalSender if used elsewhere
            }
        };


        await sock.sendMessage(recipientJid, messageContent);
        ticket.addMessage(messageText, false, senderJid, recipientJid, 'originalSecretMessage'); // [تعديل!] نضيف معلومات المرسل والمستقبل ونوع الرسالة
        conversationCache.set(ticket.id, ticket); // Ensure ticket is in cache
        messageIndex.set(ticket.watermark, ticket.id); // Ensure watermark is indexed

        await sock.sendMessage(senderJid, { text: `*رسالتك وصلت لـ "${ticket.watermark}" ، في انتظار رد من المستلم 🚀...*` });
        console.log("[sendSecretMessage] Secret message sent successfully to:", recipientJid); // [لوج جديد] تسجيل نجاح إرسال الرسالة السرية

    } catch (error) {
        console.error("[sendSecretMessage] Error in sendSecretMessage:", error);
        await sock.sendMessage(senderJid, { text: "معلش، حصلت مشكلة عامة 😫💞" });
    }
}

// 6. معالجة الردود
async function handleReply(sock, message) {
    try {
        console.log("[handleReply] Incoming reply message:", message); // [لوج جديد] تسجيل الرسالة الواردة للرد بالكامل

        const quotedMessage = message.message?.extendedTextMessage?.contextInfo?.quotedMessage;
        if (!quotedMessage) {
            console.log("[handleReply] Error: Quoted message is missing in reply"); // [لوج جديد] تسجيل خطأ: الرسالة المقتبس منها مفقودة
            await sock.sendMessage(message.key.remoteJid, { text: "يعم انت بتعمل ايه يخربيتك 🤦، رد على الرسالة نفسها 🙂" }, { quoted: message });
            return;
        }
        console.log("[handleReply] Quoted message found:", quotedMessage); // [لوج جديد] تسجيل العثور على الرسالة المقتبس منها

        let quotedMessageText; // تعريف متغير لنص الرسالة المقتبس منها

        // [تعديل جديد ومهم!] فحص نوع الرسالة المقتبس منها واستخراج النص من المكان الصح
        if (quotedMessage.extendedTextMessage?.text) {
            // الحالة الأولى: الرد على الرسالة السرية الأصلية (فيها extendedTextMessage)
            quotedMessageText = quotedMessage.extendedTextMessage.text;
            console.log("[handleReply] Quoted Message Type: extendedTextMessage"); // [لوج جديد] تسجيل نوع الرسالة المقتبس منها: extendedTextMessage
        } else if (quotedMessage.conversation) {
            // الحالة الثانية: الرد على رد سابق من البوت (فيها conversation)
            quotedMessageText = quotedMessage.conversation;
            console.log("[handleReply] Quoted Message Type: conversation"); // [لوج جديد] تسجيل نوع الرسالة المقتبس منها: conversation
        } else {
            // الحالة الثالثة: نوع غير متوقع من الرسائل المقتبس منها
            console.log("[handleReply] Error: Unexpected quoted message type"); // [لوج جديد] تسجيل خطأ: نوع غير متوقع للرسالة المقتبس منها
            console.log("[handleReply] Quoted Message Object:", quotedMessage); // [لوج جديد] تسجيل الكائن الكامل للرسالة المقتبس منها للتحليل
            return await sock.sendMessage(message.key.remoteJid, {
                text: '*مينفعش ترد غير مرة واحدة على الرسالة، انتظر رسالة جديدة منه 🚀...*'
            });
        }
        console.log("[handleReply] Quoted Message Text:", quotedMessageText); // [Log] Log the quoted message text

        const watermark = extractWatermark(quotedMessageText); // استخراج العلامة المائية من نص الرسالة المقتبس منها
        console.log("[handleReply] Extracted watermark:", watermark); // [لوج موجود] تسجيل العلامة المائية المستخرجة

        if (!watermark) {
            console.log("[handleReply] Error: Watermark not found in reply text"); // [لوج جديد] تسجيل خطأ: لم يتم العثور على العلامة المائية في نص الرد
            return await sock.sendMessage(message.key.remoteJid, {
                text: '*الرسالة مش صارحني، او انت رديت اكتر من مرة على الرسالة 👀...*'
            });
        }

        const ticket = conversationManager.findTicketByWatermark(watermark);
        if (!ticket) {
            console.log("[handleReply] Error: Ticket not found for watermark:", watermark); // [لوج جديد] تسجيل خطأ: لم يتم العثور على التذكرة بالعلامة المائية
            return await sock.sendMessage(message.key.remoteJid, {
                text: '*انتهت صلاحية الرسالة، بيتم حذف اليوزر بعد ساعة ⏳...*'
            });
        }
        console.log("[handleReply] Found ticket for watermark:", ticket.id, "watermark:", ticket.watermark); // [لوج جديد] تسجيل العثور على التذكرة بالعلامة المائية


        const replyText = cleanMessageText(message.message?.extendedTextMessage?.text); // النص بتاع الرد نفسه زي ما هو
        let replyMessageType = 'recipientReply'; // [نوع الرد الافتراضي] هنفترض إنه رد من المستلم في الأول
        let replyReceiverJid; // [متغير جديد!] هنحدد مين هو مستقبل الرد
        // [منطق جديد لتحديد مُستقبل الرد بناءً على نوع الرسالة المقتبس منها]
        if (quotedMessage.extendedTextMessage?.text.includes('رسالة سرية')) { // فحص نوع الرسالة المقتبس منها
            replyReceiverJid = ticket.sender; // [الحالة الأولى] الرد على الرسالة السرية الأصلية: يروح للمرسل الأصلي
            replyMessageType = 'recipientReply'; // نوع الرد: رد من المستلم
        } else if (quotedMessage.conversation?.includes('رد جديد')) { // فحص نوع الرسالة المقتبس منها (الردود)
            // هنا محتاجين نحدد مين هو مستقبل الرد في الردود المتتابعة...
            // في الحالة دي، مستقبل الرد هو الـ `senderJid` بتاع الرسالة المقتبس منها!
            const quotedMessageTicket = conversationManager.findTicketByWatermark(extractWatermark(quotedMessage.conversation)); // [مهم!] نجيب تذكرة الرسالة المقتبس منها عشان نوصل لـ `senderJid` بتاعها!
            replyReceiverJid = quotedMessageTicket.messages.get(quotedMessageTicket.lastMessage).senderJid; // [مهم!] ناخد الـ `senderJid` من آخر رسالة في تذكرة الرسالة المقتبس منها!
            replyMessageType = 'senderReplyToRecipientReply'; // نوع الرد: رد من المرسل على رد المستلم
        } else {
            console.log("[handleReply] Error: Unexpected quoted message type for reply routing");
            return await sock.sendMessage(message.key.remoteJid, {
                text: '*مش قادر احدد مين المفروض يستلم الرد ده. فيه مشكلة في فهم سياق الرد 😫💞*'
            });
        }


        ticket.addMessage(replyText, true, message.key.remoteJid, replyReceiverJid, replyMessageType); // [تعديل!] نسجل الرد في التذكرة مع معلومات المرسل والمستقبل والنوع

        await sock.sendMessage(replyReceiverJid, { // [تعديل!] نبعت الرد للمستقبل اللي حددناه!
            text: `*رد جديد من (${ticket.watermark}) 📩*\n\n> ${replyText}\n\n*_تأكد من تطابق يوزر الراسل_*`
        });

        storage.save(ticket); // Save updated ticket
        conversationCache.set(ticket.id, ticket); // Update cache

        await sock.sendMessage(message.key.remoteJid, { text: "*ردك وصل، في انتظار رد من الطرف الآخر 🚀...*" }, { quoted: message });
        console.log("[handleReply] Reply processed and sent to receiver:", replyReceiverJid); // [لوج جديد] تسجيل معالجة الرد وإرساله للمستقبل الصحيح


    } catch (error) {
        console.error("[handleReply] Error in handleReply:", error);
        await sock.sendMessage(message.key.remoteJid, { text: "معلش، حصلت مشكلة عامة في الرد 😫💔" }, { quoted: message });
    }
}


// 7. وظائف مساعدة
function extractWatermark(text) {
    console.log("[extractWatermark] Input text:", text); // [لوج جديد] تسجيل النص المدخل لدالة استخراج العلامة المائية
    if (!text) {
        console.log("[extractWatermark] Text is null or undefined, returning null"); // [لوج جديد] تسجيل النص المدخل فارغ
        return null; // Prevent error if text is undefined/null
    }
    // استخدام trim() لإزالة المسافات البيضاء الزائدة قبل وبعد النص
    const trimmedText = text.trim();
    // تعديل الـ Regular Expression علشان يكون أكثر مرونة مع المسافات داخل الأقواس
    const match = trimmedText.match(/\(\s*([A-F0-9]{8})\s*\)/);
    console.log("[extractWatermark] Regex match result:", match); // [لوج جديد] تسجيل نتيجة مطابقة الـ Regular Expression
    const extractedWatermark = match ? match[1] : null;
    console.log("[extractWatermark] Extracted watermark value:", extractedWatermark); // [لوج جديد] تسجيل القيمة المستخرجة للعلامة المائية
    return extractedWatermark;
}

function cleanMessageText(text) {
    if (!text) return ""; // Handle undefined text to prevent errors
    return text.replace(/\(([A-F0-9]{8})\)/, '').trim();
}

// 8. نظام الاسترجاع الآلي (ممكن نحتاجه بعدين)
async function recoverConversation(watermark) {
    return conversationManager.findTicketByWatermark(watermark);
}

// 9. النظافة التلقائية
setInterval(() => {
    conversationCache.forEach((ticket, id) => {
        if (Date.now() - ticket.timestamps.updated > 86400000) {
            conversationCache.delete(id);
            messageIndex.delete(ticket.watermark);
            console.log(`[CleanUp] Ticket ${id} with watermark ${ticket.watermark} expired and removed from cache.`); // [لوج جديد] تسجيل انتهاء صلاحية التذكرة وإزالتها من الذاكرة المؤقتة
        }
    });
}, 3600000); // كل ساعة


module.exports = {
    sendSecretMessage,
    handleReply,
    recoverConversation
};

