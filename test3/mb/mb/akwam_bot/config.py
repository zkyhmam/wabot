# -*- coding: utf-8 -*-

import os
from dotenv import load_dotenv

# Load environment variables from .env file (optional but recommended)
load_dotenv()

# --- Configuration ---
# WARNING: Storing secrets directly in code is generally not recommended for production.
# Consider using environment variables or a config file in a real-world scenario.
API_ID = int(os.getenv("API_ID", "25713843"))  # Replace/set in .env
API_HASH = os.getenv("API_HASH", "311352d08811e7f5136dfb27f71014c1")  # Replace/set in .env
BOT_TOKEN = os.getenv("BOT_TOKEN", "7558529929:AAFmMHm2HuqHsdqdQvl_ZLCoXn5XOPiRzfw") # Replace/set in .env
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://zkyhmam:Zz462008##@cluster0.7bpsz.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0") # Replace/set in .env
ADMIN_ID = int(os.getenv("ADMIN_ID", "6988696258"))  # Replace/set in .env
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "Zaky1million") # Admin username for contact
ARCHIVE_CHANNEL_ID = int(os.getenv("ARCHIVE_CHANNEL_ID", "-1002098707576")) # Replace/set in .env
BOT_USERNAME = os.getenv("BOT_USERNAME", "ZakyaaBot") # Will be fetched automatically, but can be set

# --- Constants ---
BASE_URL = "https://ak.sv" # Main site URL
AKWAM_SEARCH_URL = BASE_URL + "/search?q={query}&page={page}"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
REQUEST_DELAY = 1.0 # Seconds delay between requests to the site
PROGRESS_UPDATE_INTERVAL = 3 # Seconds interval for updating progress messages
MAX_RESULTS_PER_PAGE = 6 # Number of search results per page (used in formatting, actual scraping might differ)

# Point Costs
POINTS_MOVIE = 20
POINTS_EPISODE = 10

# Plan Limits
DAILY_LIMIT_REGULAR = 60
MONTHLY_LIMIT_REGULAR = 1500
DAILY_LIMIT_PREMIUM = 500
MONTHLY_LIMIT_PREMIUM = 10000

# Referral System
POINTS_REFERRAL = 20
REFERRAL_TARGET_FOR_PREMIUM = 50
PREMIUM_REFERRAL_DURATION_DAYS = 30

# Download Concurrency
MAX_CONCURRENT_PREMIUM_DOWNLOADS = 3
MAX_CONCURRENT_REGULAR_DOWNLOADS = 1 # Explicitly define

# Logging
LOG_LEVEL = "INFO"
