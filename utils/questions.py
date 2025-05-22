# utils/questions.py

import logging
import json
import os
from config import QUESTIONS_FILE

logging.basicConfig(level=logging.INFO)

def load_questions():
    try:
        with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Ошибка при загрузке вопросов: {e}")
        return {}