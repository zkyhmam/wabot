from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from keyboards import main_menu, channel_type_keyboard, group_type_keyboard, get_language_keyboard
from localization import texts, user_languages
import utils

@Client.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    lang = user_languages.get(user_id, "en")  # الافتراضي: الإنجليزية
    await message.reply_text(texts[lang]["welcome"], reply_markup=main_menu)
    await message.reply_text(texts[lang]["choose_language"], reply_markup=get_language_keyboard())

@Client.on_message(filters.regex("🧑‍💻 Me"))
async def me_button(client: Client, message: Message):
    user_id = message.from_user.id
    lang = user_languages.get(user_id, "en")
    user_info = await utils.get_user_info(client, message.from_user)
    await message.reply_text(f"{texts[lang]['me_info']}\n\n{user_info}")

@Client.on_message(filters.regex("📢 Channel"))
async def channel_button(client: Client, message: Message):
    user_id = message.from_user.id
    lang = user_languages.get(user_id, "en")
    await message.reply_text(texts[lang]["channel_type"], reply_markup=channel_type_keyboard)

@Client.on_message(filters.regex("👥 Group"))
async def group_button(client: Client, message: Message):
    user_id = message.from_user.id
    lang = user_languages.get(user_id, "en")
    await message.reply_text(texts[lang]["group_type"], reply_markup=group_type_keyboard)

@Client.on_message(filters.regex("👤 User"))
async def user_button(client: Client, message: Message):
    user_id = message.from_user.id
    lang = user_languages.get(user_id, "en")
    await message.reply_text(texts[lang]["share_user"])

@Client.on_message(filters.regex("🤖 Bot"))
async def bot_button(client: Client, message: Message):
    user_id = message.from_user.id
    lang = user_languages.get(user_id, "en")
    await message.reply_text(texts[lang]["share_bot"])

@Client.on_callback_query(filters.regex("lang_(.*)"))
async def change_language(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    lang = callback_query.data.split("_")[1]
    user_languages[user_id] = lang
    lang_name = "English" if lang == "en" else "العربية"
    await callback_query.message.edit_text(texts[lang]["lang_changed"].format(lang=lang_name))

@Client.on_callback_query(filters.regex("private_channel|public_channel"))
async def channel_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    lang = user_languages.get(user_id, "en")
    await callback_query.message.edit_text(texts[lang]["share_channel"])

@Client.on_callback_query(filters.regex("public_group|private_group|super_group"))
async def group_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    lang = user_languages.get(user_id, "en")
    await callback_query.message.edit_text(texts[lang]["share_group"])

@Client.on_message(filters.forwarded)
async def handle_forwarded(client: Client, message: Message):
    user_id = message.from_user.id
    lang = user_languages.get(user_id, "en")
    if message.forward_from:  # مستخدم
        info = await utils.get_user_info(client, message.forward_from)
        await message.reply_text(info)
    elif message.forward_from_chat:  # قناة أو مجموعة
        chat = message.forward_from_chat
        if chat.type == "channel":
            info = await utils.get_channel_info(client, chat)
            await message.reply_text(info)
        elif chat.type in ["group", "supergroup"]:
            info = await utils.get_group_info(client, chat)
            await message.reply_text(info)
    elif message.forward_from and message.forward_from.is_bot:  # بوت
        info = await utils.get_bot_info(client, message.forward_from)
        await message.reply_text(info)
