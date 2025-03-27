import phonenumbers
from phonenumbers import geocoder

def get_country(phone_number):
    try:
        parsed_number = phonenumbers.parse(phone_number)
        return geocoder.description_for_number(parsed_number, "en")
    except:
        return "Unknown"

async def get_user_info(client, user):
    user_info = await client.get_users(user.id)
    phone = user_info.phone_number if user_info.phone_number else "None"
    country = get_country("+" + phone) if phone != "None" else "Unknown"
    last_seen = "Recently" if user_info.status else "Unknown"
    info_text = (
        f"🆔 User ID: {user_info.id}\n"
        f"👤 Username: @{user_info.username if user_info.username else 'None'}\n"
        f"📛 Name: {user_info.first_name or ''} {user_info.last_name or ''}\n"
        f"📞 Phone Number: {phone}\n"
        f"🌎 Country: {country}\n"
        f"🕒 Last Seen: {last_seen}\n"
        f"💼 Premium: {'✅ Yes' if user_info.is_premium else '❌ No'}\n"
        f"⚠️ Scam: {'✅ Yes' if user_info.is_scam else '❌ No'}\n"
        f"⚠️ Fake: {'✅ Yes' if user_info.is_fake else '❌ No'}\n"
        f"📸 Profile Photo: {'Available' if user_info.photo else 'None'}"
    )
    return info_text

async def get_channel_info(client, chat):
    channel = await client.get_chat(chat.id)
    info_text = (
        f"🆔 Channel ID: {channel.id}\n"
        f"📛 Name: {channel.title}\n"
        f"👥 Members: {channel.members_count or 'Unknown'}\n"
        f"📸 Photo: {'Available' if channel.photo else 'None'}\n"
        f"🔗 Link: {f't.me/{channel.username}' if channel.username else 'None'}"
    )
    return info_text

async def get_group_info(client, chat):
    group = await client.get_chat(chat.id)
    info_text = (
        f"🆔 Group ID: {group.id}\n"
        f"📛 Name: {group.title}\n"
        f"👥 Members: {group.members_count or 'Unknown'}\n"
        f"📸 Photo: {'Available' if group.photo else 'None'}\n"
        f"🔗 Link: {f't.me/{group.username}' if group.username else 'None'}"
    )
    return info_text

async def get_bot_info(client, user):
    bot_info = await client.get_users(user.id)
    info_text = (
        f"🆔 Bot ID: {bot_info.id}\n"
        f"🤖 Name: {bot_info.first_name}\n"
        f"👤 Username: @{bot_info.username}\n"
        f"💼 Official: {'✅ Yes' if bot_info.is_verified else '❌ No'}"
    )
    return info_text
