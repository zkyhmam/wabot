import logging
from telegram.ext import ContextTypes
import re

logger = logging.getLogger(__name__)

async def is_subscribed(context: ContextTypes.DEFAULT_TYPE, user_id: int, channel_id: int):
    try:
        member = await context.bot.get_chat_member(channel_id, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

async def resolve_channel_id(context: ContextTypes.DEFAULT_TYPE, input_str: str):
    try:
        if input_str.startswith("https://t.me/") or input_str.startswith("@"):
            username = input_str.split("/")[-1] if "t.me" in input_str else input_str[1:]
            chat = await context.bot.get_chat(f"@{username}")
            return chat.id
        elif input_str.startswith("-100") and input_str.isdigit():
            return int(input_str)
        return None
    except Exception as e:
        logger.error(f"[red]❌ Error resolving channel ID: {e}[/red]")
        return None

async def resolve_user_id(context: ContextTypes.DEFAULT_TYPE, input_str: str):
    try:
        if input_str.startswith("@"):
            user = await context.bot.get_chat(input_str)
            return user.id
        elif input_str.isdigit():
            return int(input_str)
        return None
    except Exception as e:
        logger.error(f"[red]❌ Error resolving user ID: {e}[/red]")
        return None
