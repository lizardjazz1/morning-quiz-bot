# config.py
import logging
import os
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()

# --- Основные Константы ---
TOKEN = os.getenv("BOT_TOKEN")
LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper() # DEBUG, INFO, WARNING, ERROR, CRITICAL

QUESTIONS_FILE = 'questions.json'
MALFORMED_QUESTIONS_FILE = 'malformed_questions.json'
USERS_FILE = 'users.json'

DEFAULT_POLL_OPEN_PERIOD = 25  # Секунд на ответ для обычных /quiz и /quiz10
NUMBER_OF_QUESTIONS_IN_SESSION = 10 # Для /quiz10
JOB_GRACE_PERIOD = 2 # Секунды запаса для задач JobQueue после закрытия опроса (увеличено для надежности)

# Константы для Callback Data (для кнопок выбора категории /quiz10)
CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT = "q10s_" # НОВЫЙ короткий префикс для category selection callback data
CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY = "quiz10_cat_random"

# Константы для /quiz10notify
QUIZ10_NOTIFY_DELAY_MINUTES = 2 # Минут до начала квиза после уведомления

# --- Константы для Ежедневной Викторины ---
DAILY_QUIZ_SUBSCRIPTIONS_FILE = 'daily_quiz_subscriptions.json'
DAILY_QUIZ_DEFAULT_HOUR_MSK = 7
DAILY_QUIZ_DEFAULT_MINUTE_MSK = 0
DAILY_QUIZ_QUESTIONS_COUNT = 10
DAILY_QUIZ_CATEGORIES_TO_PICK = 3 # Количество случайных категорий для выбора
DAILY_QUIZ_POLL_OPEN_PERIOD_SECONDS = 600 # Максимальное время для Telegram Poll (10 минут)
DAILY_QUIZ_QUESTION_INTERVAL_SECONDS = 60 # 1 минута между вопросами

# --- Настройка логгера ---
log_level = getattr(logging, LOG_LEVEL_STR, logging.INFO)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=log_level
)
logger = logging.getLogger(__name__)

if not TOKEN:
    logger.critical("Токен BOT_TOKEN не найден в .env файле! Пожалуйста, создайте .env файл и добавьте в него BOT_TOKEN.")

# Выводим фактический уровень логгирования
logger.info(f"Уровень логирования установлен на: {logging.getLevelName(logger.getEffectiveLevel())}")

