# quiz_bot/data_manager.py
import json
import logging
import os
from config import QUESTIONS_FILE, USERS_FILE

def load_questions():
    try:
        with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Ошибка при загрузке вопросов: {e}")
        return {}

def load_user_data():
    if not os.path.exists(USERS_FILE):
        save_user_data({})  # Создаем файл, если его нет
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Ошибка при загрузке данных пользователей: {e}")
        return {}

def save_user_data(data):
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Ошибка при сохранении данных пользователей: {e}")

