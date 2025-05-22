# quiz_bot/config.py
import os
import logging
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# Настройки логирования
LOGGING_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOGGING_LEVEL = logging.INFO

# Имена файлов
QUESTIONS_FILE = 'questions.json'
USERS_FILE = 'users.json'

def setup_logging():
    logging.basicConfig(format=LOGGING_FORMAT, level=LOGGING_LEVEL)

if not TOKEN:
    logging.error("❌ Токен не найден. Убедитесь, что он указан в файле .env")
    raise ValueError("Токен не найден")

