from pyrogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# Reply Keyboard الثابتة
main_menu = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🧑‍💻 Me")],
        [KeyboardButton("📢 Channel"), KeyboardButton("👥 Group")],
        [KeyboardButton("👤 User"), KeyboardButton("🤖 Bot")]
    ],
    resize_keyboard=True
)

# Inline Keyboards ثابتة
channel_type_keyboard = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("🔒 Private Channel", callback_data="private_channel")],
        [InlineKeyboardButton("🌐 Public Channel", callback_data="public_channel")]
    ]
)

group_type_keyboard = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("🌐 Public Group", callback_data="public_group")],
        [InlineKeyboardButton("🔒 Private Group", callback_data="private_group"), 
         InlineKeyboardButton("🚀 Super Group", callback_data="super_group")]
    ]
)

# Inline Keyboard لاختيار اللغة (سيتم عرضها في النص)
def get_language_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"), 
             InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar")]
        ]
    )
