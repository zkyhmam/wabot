# -*- coding: utf-8 -*-

import logging
import motor.motor_asyncio
from datetime import datetime, timedelta, timezone

from config import MONGO_URI, DAILY_LIMIT_REGULAR, DAILY_LIMIT_PREMIUM, MONTHLY_LIMIT_REGULAR, MONTHLY_LIMIT_PREMIUM, DEFAULT_LANG, BOT_USERNAME

logger = logging.getLogger(__name__)

# --- MongoDB Setup ---
try:
    mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    db = mongo_client.akwam_bot_db # Database name
    users_collection = db.users # For user data (points, lang, premium, etc.)
    archive_collection = db.archive # For archived file IDs
    settings_collection = db.settings # For bot settings like mandatory channels
    logger.info("Successfully connected to MongoDB.")
except Exception as e:
    logger.critical(f"FATAL: Could not connect to MongoDB: {e}")
    # The application should exit if DB connection fails, handled in main.py
    mongo_client = None
    db = None
    users_collection = None
    archive_collection = None
    settings_collection = None

# --- Database Functions ---

async def db_find_user(user_id: int):
    """Finds a user in the database."""
    if not users_collection: return None
    return await users_collection.find_one({"user_id": user_id})

async def db_add_user(user_id: int, lang: str = DEFAULT_LANG, referred_by: int | None = None):
    """Adds a new user to the database."""
    if not users_collection: return None
    now = datetime.now(timezone.utc)
    user_data = {
        "user_id": user_id,
        "language": lang,
        "daily_points_consumed": 0,
        "monthly_points_consumed": 0,
        "last_reset_time": now, # Time of adding user, will reset properly later
        "referral_points": 0,
        "referral_code": f"ref_{user_id}_{int(now.timestamp())}", # Simple unique code
        "referral_count": 0,
        "referred_by": referred_by,
        "premium_until": None,
        "banned": False,
        "joined_channels_check_time": None,
        "first_seen": now,
        "last_seen": now,
        "username_lower": None, # Store lowercase username for easier lookup
    }
    try:
        await users_collection.insert_one(user_data)
        logger.info(f"Added new user {user_id} to database.")
        return user_data
    except Exception as e:
        logger.error(f"Failed to add user {user_id}: {e}")
        return None

async def db_update_user(user_id: int, update_data: dict):
    """Updates user data in the database."""
    if not users_collection: return
    update_data["last_seen"] = datetime.now(timezone.utc)
    try:
        await users_collection.update_one({"user_id": user_id}, {"$set": update_data})
    except Exception as e:
         logger.error(f"Failed to update user {user_id}: {e}")

async def db_get_user_lang(user_id: int) -> str:
    """Gets the user's preferred language."""
    user = await db_find_user(user_id)
    return user.get("language", DEFAULT_LANG) if user else DEFAULT_LANG

async def db_check_and_reset_points(user_id: int):
    """Checks if daily/monthly points need resetting and does so."""
    if not users_collection: return
    user = await db_find_user(user_id)
    if not user: return

    now = datetime.now(timezone.utc)
    # Use 'first_seen' if 'last_reset_time' is missing (e.g., for very old users)
    last_reset = user.get("last_reset_time") or user.get("first_seen") or now

    needs_daily_reset = False
    needs_monthly_reset = False

    # Check daily reset (if last reset was on a previous day in UTC)
    if last_reset.date() < now.date():
        needs_daily_reset = True

    # Check monthly reset (if last reset was in a previous month)
    if last_reset.year < now.year or last_reset.month < now.month:
        needs_monthly_reset = True

    update_query = {}
    if needs_daily_reset:
        update_query["daily_points_consumed"] = 0
        logger.info(f"Resetting daily points for user {user_id}")

    if needs_monthly_reset:
         update_query["monthly_points_consumed"] = 0
         logger.info(f"Resetting monthly points for user {user_id}")

    # Always update last_reset_time if any reset happened
    if needs_daily_reset or needs_monthly_reset:
        update_query["last_reset_time"] = now
        await db_update_user(user_id, update_query)


async def db_get_user_points_info(user_id: int) -> dict | None:
    """Gets current points status, checking for reset first."""
    if not users_collection: return None
    await db_check_and_reset_points(user_id) # Ensure points are up-to-date
    user = await db_find_user(user_id)
    if not user: return None # Should not happen if user exists

    premium_until = user.get("premium_until")
    is_premium = premium_until and premium_until > datetime.now(timezone.utc)
    daily_limit = DAILY_LIMIT_PREMIUM if is_premium else DAILY_LIMIT_REGULAR
    monthly_limit = MONTHLY_LIMIT_PREMIUM if is_premium else MONTHLY_LIMIT_REGULAR

    return {
        "daily_consumed": user.get("daily_points_consumed", 0),
        "monthly_consumed": user.get("monthly_points_consumed", 0),
        "referral_points": user.get("referral_points", 0),
        "daily_limit": daily_limit,
        "monthly_limit": monthly_limit,
        "is_premium": is_premium,
        "premium_until": premium_until,
        "last_reset_time": user.get("last_reset_time"),
        "referral_count": user.get("referral_count", 0)
    }

async def db_deduct_points(user_id: int, cost: int) -> bool:
    """Tries to deduct points (daily first, then referral). Returns True if successful."""
    if not users_collection: return False
    points_info = await db_get_user_points_info(user_id) # Get current status after potential reset
    if not points_info: return False

    remaining_daily = points_info["daily_limit"] - points_info["daily_consumed"]
    remaining_monthly = points_info["monthly_limit"] - points_info["monthly_consumed"]
    referral_points = points_info["referral_points"]

    if points_info["monthly_consumed"] + cost > points_info["monthly_limit"]:
         logger.warning(f"User {user_id} reached monthly limit ({points_info['monthly_consumed']}/{points_info['monthly_limit']}). Cost: {cost}")
         return False # Monthly limit exceeded

    update_query = {"$inc": {}}
    deducted = False

    if remaining_daily >= cost:
        update_query["$inc"]["daily_points_consumed"] = cost
        update_query["$inc"]["monthly_points_consumed"] = cost
        deducted = True
        logger.info(f"Deducting {cost} daily points from user {user_id}.")
    elif referral_points >= cost:
        update_query["$inc"]["referral_points"] = -cost
        update_query["$inc"]["monthly_points_consumed"] = cost # Still counts towards monthly limit
        deducted = True
        logger.info(f"Deducting {cost} referral points from user {user_id}.")
    else:
        logger.warning(f"User {user_id} has insufficient points. Daily: {remaining_daily}, Referral: {referral_points}. Cost: {cost}")
        return False # Not enough points

    if deducted:
        try:
            await users_collection.update_one({"user_id": user_id}, update_query)
            return True
        except Exception as e:
            logger.error(f"Failed to deduct points for user {user_id}: {e}")
            # Consider rolling back or logging inconsistency if deduction fails
            return False

    return False

async def db_add_referral_points(referrer_id: int, points: int):
    """Adds referral points and increments referral count."""
    if not users_collection: return
    try:
        await users_collection.update_one(
            {"user_id": referrer_id},
            {"$inc": {"referral_points": points, "referral_count": 1}}
        )
        logger.info(f"Awarded {points} referral points to user {referrer_id}.")
    except Exception as e:
         logger.error(f"Failed to add referral points for user {referrer_id}: {e}")


async def db_get_referral_link(user_id: int, bot_username: str | None = None) -> str:
    """Generates or retrieves the user's referral link."""
    user = await db_find_user(user_id)
    if user and "referral_code" in user:
        username = bot_username or BOT_USERNAME # Use config fallback if not provided
        if username:
             return f"https://t.me/{username}?start={user['referral_code']}"
        else:
             logger.warning("BOT_USERNAME not configured, cannot generate full referral link.")
             return f"Start the bot with code: {user['referral_code']}" # Fallback link text
    return "N/A" # Should not happen for existing users


# --- Archive DB Functions ---
async def db_find_archived_file(akwam_id: str, quality: str):
    """Finds an archived file by Akwam ID and quality."""
    if not archive_collection: return None
    return await archive_collection.find_one({"akwam_id": akwam_id, "quality": quality})

async def db_add_archived_file(akwam_id: str, quality: str, title: str, file_id: str, file_unique_id: str, message_id: int):
    """Adds or updates an archived file record."""
    if not archive_collection: return
    try:
        await archive_collection.update_one(
            {"akwam_id": akwam_id, "quality": quality},
            {"$set": {
                "title": title,
                "file_id": file_id,
                "file_unique_id": file_unique_id,
                "message_id": message_id,
                "archived_at": datetime.now(timezone.utc)
            }},
            upsert=True
        )
        logger.info(f"Archived/Updated file: ID={akwam_id}, Quality={quality}, FileID={file_id}")
    except Exception as e:
         logger.error(f"Failed to add/update archive file {akwam_id} ({quality}): {e}")

async def db_remove_archived_file(akwam_id: str, quality: str):
    """Removes an archived file record."""
    if not archive_collection: return
    try:
        result = await archive_collection.delete_one({"akwam_id": akwam_id, "quality": quality})
        if result.deleted_count > 0:
            logger.info(f"Removed outdated archive record for ID={akwam_id}, Quality={quality}")
    except Exception as e:
         logger.error(f"Failed to remove archive file {akwam_id} ({quality}): {e}")

# --- Settings DB Functions ---
async def db_get_channels():
    """Gets the list of mandatory join channels."""
    if not settings_collection: return []
    try:
        settings = await settings_collection.find_one({"_id": "mandatory_channels"})
        return settings.get("channels", []) if settings else []
    except Exception as e:
         logger.error(f"Failed to get mandatory channels: {e}")
         return []

async def db_add_channel(app_client, channel_input: str) -> bool:
    """Adds a channel to the mandatory list. Requires app client."""
    if not settings_collection: return False
    try:
        # Resolve username to ID if needed, handle potential errors
        channel_id = None
        if channel_input.isdigit() or (channel_input.startswith("-") and channel_input[1:].isdigit()):
             channel_id = int(channel_input)
        else:
             # Use app_client passed from the main application context
             chat = await app_client.get_chat(channel_input.replace("@", ""))
             channel_id = chat.id

        if channel_id:
            # Check if bot can access the channel
            try:
                 await app_client.get_chat(channel_id) # Throws error if bot can't access
                 await settings_collection.update_one(
                     {"_id": "mandatory_channels"},
                     {"$addToSet": {"channels": channel_id}},
                     upsert=True
                 )
                 logger.info(f"Added mandatory channel: {channel_id} ({channel_input})")
                 return True
            except Exception as e:
                 logger.error(f"Bot cannot access channel {channel_input} ({channel_id}): {e}")
                 return False
        else:
            logger.error(f"Could not resolve channel input: {channel_input}")
            return False
    except Exception as e:
        logger.error(f"Error adding channel {channel_input}: {e}")
        return False


async def db_remove_channel(channel_id: int | str):
    """Removes a channel from the mandatory list."""
    if not settings_collection: return False
    try:
        # Ensure channel_id is int if it's a numerical string
        clean_id = channel_id
        if isinstance(channel_id, str) and (channel_id.isdigit() or (channel_id.startswith("-") and channel_id[1:].isdigit())):
             clean_id = int(channel_id)

        await settings_collection.update_one(
            {"_id": "mandatory_channels"},
            {"$pull": {"channels": clean_id}}
        )
        logger.info(f"Removed mandatory channel: {clean_id}")
        return True
    except Exception as e:
        logger.error(f"Error removing channel {channel_id}: {e}")
        return False

async def db_get_banned_users(skip: int, limit: int):
    """Retrieves a paginated list of banned users."""
    if not users_collection: return [], 0
    try:
        cursor = users_collection.find({"banned": True}).skip(skip).limit(limit)
        users = await cursor.to_list(length=limit)
        total = await users_collection.count_documents({"banned": True})
        return users, total
    except Exception as e:
        logger.error(f"Failed to get banned users: {e}")
        return [], 0

async def db_update_user_ban_status(user_id: int, banned: bool) -> bool:
    """Sets the banned status for a user."""
    if not users_collection: return False
    try:
        result = await users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"banned": banned}}
        )
        # Check if the user exists and was modified, or if the status is already set correctly
        if result.modified_count > 0:
            return True
        elif result.matched_count > 0:
             # User exists, check if status is already what we want
             existing_user = await db_find_user(user_id)
             return existing_user is not None and existing_user.get("banned") == banned
        else:
             # User not found
             return False
    except Exception as e:
        logger.error(f"Failed to update ban status for user {user_id}: {e}")
        return False

async def db_add_referral_points_admin(user_id: int, points: int) -> bool:
    """Adds referral points (typically by admin)."""
    if not users_collection: return False
    try:
        result = await users_collection.update_one(
            {"user_id": user_id},
            {"$inc": {"referral_points": points}}
        )
        return result.matched_count > 0
    except Exception as e:
        logger.error(f"Failed to add referral points for user {user_id}: {e}")
        return False
