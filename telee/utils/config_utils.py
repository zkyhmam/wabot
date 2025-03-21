import os
import json
from typing import Dict

CONFIG_FILE = "config.json" #  Make sure this is consistent across files if needed
ADMIN_ID = 6988696258 #  Make sure this is consistent across files if needed
ADMIN_USERNAME = "Zaky1million" #  Make sure this is consistent across files if needed

def load_config(config_file: str) -> Dict:
    """تحميل إعدادات البوت"""
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # ---  إضافة الإعدادات الجديدة لو مش موجودة في الملف القديم ---
        if "search_lines_limit" not in config:
            config["search_lines_limit"] = 2
        if "search_full_message" not in config:
            config["search_full_message"] = False
        if "monitored_shares" not in config: # <--- إضافة قائمة المراقبة لو مش موجودة
            config["monitored_shares"] = []
        if "archive_channel_id" not in config:  # <--- إضافة معرف قناة الأرشيف
            config["archive_channel_id"] = None
        if "request_group_link" not in config:  # <--- إضافة رابط جروب الطلبات
            config["request_group_link"] = None

        return config
    return {
        "admin_id": ADMIN_ID,
        "admin_username": ADMIN_USERNAME,
        "allowed_groups": [],
        "monitored_channels": [],
        "search_lines_limit": 2,
        "search_full_message": False,
        "monitored_shares": [], # <--- قائمة مراقبة الشير افتراضيا فارغة
        "archive_channel_id": None, # <--- معرف قناة الأرشيف افتراضيًا فارغ
        "request_group_link": None # <--- رابط جروب الطلبات افتراضيا فارغ
    }

def save_config(config: Dict, config_file: str):
    """حفظ إعدادات البوت"""
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

