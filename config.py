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
JOB_GRACE_PERIOD = 2 # Секунды запаса для задач JobQueue после закрытия опроса

# Константы для Callback Data (для кнопок выбора категории /quiz10)
CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT = "q10s_"
CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY = "quiz10_cat_random"

# Константы для /quiz10notify
QUIZ10_NOTIFY_DELAY_MINUTES = 2 # Минут до начала квиза после уведомления

# --- Константы для Ежедневной Викторины ---
DAILY_QUIZ_SUBSCRIPTIONS_FILE = 'daily_quiz_subscriptions.json'
DAILY_QUIZ_DEFAULT_HOUR_MSK = 7
DAILY_QUIZ_DEFAULT_MINUTE_MSK = 0
DAILY_QUIZ_QUESTIONS_COUNT = 10 # Количество вопросов в ежедневной викторине
DAILY_QUIZ_CATEGORIES_TO_PICK = 3 # Сколько случайных категорий выбирать по умолчанию
DAILY_QUIZ_POLL_OPEN_PERIOD_SECONDS = 60 * 5 # Время на ответ на вопрос в ежедневной викторине (5 минут)
DAILY_QUIZ_QUESTION_INTERVAL_SECONDS = 60 * 5 + 10 # Интервал между вопросами (время опроса + 10 секунд)
DAILY_QUIZ_MAX_CUSTOM_CATEGORIES = 5 # Максимальное кол-во кастомных категорий для ежедневной викторины

# Константы для Callback Data (для кнопок выбора категории ежедневной викторины)
CALLBACK_DATA_PREFIX_DAILY_QUIZ_CATEGORY_SHORT = "dq_s_" # Daily Quiz Short
CALLBACK_DATA_DAILY_QUIZ_RANDOM_CATEGORY = "dq_cat_random"

# Инициализация логгера
log_level_map = {
    "DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING,
    "ERROR": logging.ERROR, "CRITICAL": logging.CRITICAL,
}
effective_log_level = log_level_map.get(LOG_LEVEL_STR, logging.INFO)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=effective_log_level
)
logger = logging.getLogger(__name__)

# Проверка наличия токена
if TOKEN is None:
    logger.critical("Токен бота не найден. Убедитесь, что BOT_TOKEN задан в .env или переменных окружения.")
    exit()

