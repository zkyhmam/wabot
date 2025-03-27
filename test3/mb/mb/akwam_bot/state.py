# -*- coding: utf-8 -*-

import asyncio
from config import MAX_CONCURRENT_PREMIUM_DOWNLOADS, MAX_CONCURRENT_REGULAR_DOWNLOADS

# Stores temporary user data like last search results {user_id: {"last_search_results": [...]}}
user_states = {}

# Queue for non-premium downloads
download_queue = asyncio.Queue(MAX_CONCURRENT_REGULAR_DOWNLOADS)

# Limit concurrent premium downloads
premium_semaphore = asyncio.Semaphore(MAX_CONCURRENT_PREMIUM_DOWNLOADS)

# Stores active download tasks {user_id: asyncio.Task | "pending" | None}
download_tasks = {}

# Asyncio locks per user to prevent multiple simultaneous downloads {user_id: asyncio.Lock}
user_download_locks = {}

# {message_identifier: timestamp} # message_identifier = f"{chat_id}_{message_id}"
last_progress_update = {}
