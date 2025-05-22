# utils/users.py

import logging
import json
import os
from config import USERS_FILE

logging.basicConfig(level=logging.INFO)

def load_user_data():
    if not os.path.exists(USERS_FILE):
        save_user_data({})
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Ошибка при загрузке рейтинга: {e}")
        return {}

def save_user_data(data):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)