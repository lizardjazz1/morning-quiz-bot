# config.py
import logging
import os
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()

# --- Основные Константы ---
TOKEN = os.getenv("BOT_TOKEN")
LOG_LVL_STR = os.getenv("LOG_LEVEL", "INFO").upper() # DEBUG, INFO, WARNING, ERROR, CRITICAL

QS_F = 'questions.json'
BAD_QS_F = 'malformed_questions.json' # Renamed from MALFORMED_QUESTIONS_FILE
USRS_F = 'users.json'

POLL_OPEN_S = 25  # Секунд на ответ для обычных /quiz и /quiz10 (Renamed from DEFAULT_POLL_OPEN_PERIOD)
QS_PER_SESSION = 10 # Для /quiz10 (Renamed from NUMBER_OF_QUESTIONS_IN_SESSION)
JOB_GRACE_S = 2 # Секунды запаса для задач JobQueue (Renamed from JOB_GRACE_PERIOD)

# Константы для Callback Data (для кнопок выбора категории /quiz10)
CB_Q10_CAT_PFX = "q10s_" # НОВЫЙ короткий префикс (Renamed from CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT)
CB_Q10_RND_CAT = "q10_cat_r" # Renamed from CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY

# Константы для /quiz10notify
Q10_NOTIFY_DELAY_M = 2 # Минут до начала квиза (Renamed from QUIZ10_NOTIFY_DELAY_MINUTES)

# --- Константы для Ежедневной Викторины ---
DQS_F = 'daily_quiz_subscriptions.json' # Renamed from DAILY_QUIZ_SUBSCRIPTIONS_FILE
DQ_DEF_H = 7 # Renamed from DAILY_QUIZ_DEFAULT_HOUR_MSK
DQ_DEF_M = 0 # Renamed from DAILY_QUIZ_DEFAULT_MINUTE_MSK
DQ_QS_COUNT = 10 # Renamed from DAILY_QUIZ_QUESTIONS_COUNT
DQ_CATS_PICK = 3 # Renamed from DAILY_QUIZ_CATEGORIES_TO_PICK
DQ_MAX_CUST_CATS = 3 # Renamed from DAILY_QUIZ_MAX_CUSTOM_CATEGORIES
DQ_POLL_OPEN_S = 600 # Renamed from DAILY_QUIZ_POLL_OPEN_PERIOD_SECONDS
DQ_Q_INTERVAL_S = 60 # Renamed from DAILY_QUIZ_QUESTION_INTERVAL_SECONDS

# --- Настройка логгера ---
log_level = getattr(logging, LOG_LVL_STR, logging.INFO)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=log_level
)
logger = logging.getLogger(__name__)

if not TOKEN:
    logger.critical("Токен BOT_TOKEN не найден в .env файле! Пожалуйста, создайте .env файл и добавьте в него BOT_TOKEN.")

# Выводим фактический уровень логгирования
logger.info(f"Уровень логирования установлен на: {logging.getLevelName(logger.getEffectiveLevel())}")
