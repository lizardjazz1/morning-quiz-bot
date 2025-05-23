# config.py
import logging
import os
from dotenv import load_dotenv

# --- Константы ---
QUESTIONS_FILE = 'questions.json'
MALFORMED_QUESTIONS_FILE = 'malformed_questions.json' # Новый файл
USERS_FILE = 'users.json'
DEFAULT_POLL_OPEN_PERIOD = 25  # Секунд на ответ
FINAL_ANSWER_WINDOW_SECONDS = 45 # Время на последний вопрос в /quiz10
NUMBER_OF_QUESTIONS_IN_SESSION = 10
JOB_GRACE_PERIOD = 1 # Секунды запаса для задач JobQueue после закрытия опроса

# Константы для Callback Data (для кнопок выбора категории)
CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY = "quiz10_cat_"
CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY = "quiz10_cat_random"

# Константы для /quiz10notify
QUIZ10_NOTIFY_DELAY_MINUTES = 2 # Минут до начала квиза после уведомления
CALLBACK_DATA_QUIZ10_NOTIFY_START_NOW = "quiz10_notify_start_now_" # префикс + chat_id + category_encoded


# Загрузка переменных окружения из .env файла
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# --- Настройка логгера ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

if not TOKEN:
    logger.critical("Токен BOT_TOKEN не найден в .env файле! Пожалуйста, создайте .env файл и добавьте в него BOT_TOKEN.")

