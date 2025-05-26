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
DAILY_QUIZ_CATEGORIES_TO_PICK = 3 # Количество случайных категорий для выбора (если пользователь не указал свои)
DAILY_QUIZ_MAX_CUSTOM_CATEGORIES = 3 # Максимальное количество категорий, которые пользователь может выбрать
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
# data_manager.py
import json
import os
import copy
from typing import List, Dict, Any, Set, Optional

from config import (logger, QUESTIONS_FILE, USERS_FILE, MALFORMED_QUESTIONS_FILE,
                    DAILY_QUIZ_SUBSCRIPTIONS_FILE, DAILY_QUIZ_DEFAULT_HOUR_MSK, DAILY_QUIZ_DEFAULT_MINUTE_MSK)
import state

# --- Вспомогательные функции для сериализации/десериализации ---
def convert_sets_to_lists_recursively(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: convert_sets_to_lists_recursively(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_sets_to_lists_recursively(elem) for elem in obj]
    if isinstance(obj, set):
        return sorted(list(obj)) # Сортируем для консистентности в JSON
    return obj

def convert_user_scores_lists_to_sets(scores_data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(scores_data, dict):
        return scores_data # Возвращаем как есть, если это не словарь
    for chat_id, users_in_chat in scores_data.items():
        if isinstance(users_in_chat, dict):
            for user_id, user_data_val in users_in_chat.items():
                if isinstance(user_data_val, dict):
                    # Обновляем answered_polls
                    if 'answered_polls' in user_data_val and isinstance(user_data_val['answered_polls'], list):
                        user_data_val['answered_polls'] = set(user_data_val['answered_polls'])
                    # Обновляем milestones_achieved (если есть)
                    if 'milestones_achieved' in user_data_val and isinstance(user_data_val['milestones_achieved'], list):
                        user_data_val['milestones_achieved'] = set(user_data_val['milestones_achieved'])
    return scores_data

# --- Функции загрузки и сохранения данных ---
def load_questions():
    processed_questions_count, valid_categories_count = 0, 0
    malformed_entries = [] # Для сбора некорректных записей
    try:
        with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        if not isinstance(raw_data, dict):
            logger.error(f"{QUESTIONS_FILE} должен содержать JSON объект (словарь категорий).")
            malformed_entries.append({"error_type": "root_not_dict", "data": raw_data})
            state.quiz_data = {} # Устанавливаем пустые данные
        else:
            temp_quiz_data = {}
            for category, questions_list in raw_data.items():
                if not isinstance(questions_list, list):
                    logger.warning(f"Категория '{category}' не является списком вопросов. Пропущена.")
                    malformed_entries.append({"error_type": "category_not_list", "category": category, "data": questions_list})
                    continue

                processed_category_questions = []
                for i, q_data in enumerate(questions_list):
                    is_struct_valid = (isinstance(q_data, dict) and
                                       all(k in q_data for k in ["question", "options", "correct"]) and
                                       isinstance(q_data.get("question"), str) and q_data["question"].strip() and
                                       isinstance(q_data.get("options"), list) and len(q_data["options"]) >= 2 and
                                       all(isinstance(opt, str) and opt.strip() for opt in q_data["options"]) and
                                       isinstance(q_data.get("correct"), str) and q_data["correct"].strip() and
                                       q_data["correct"] in q_data["options"])

                    has_solution = "solution" in q_data
                    is_solution_valid = not has_solution or \
                                        (isinstance(q_data.get("solution"), str) and q_data.get("solution", "").strip())

                    if not is_struct_valid or not is_solution_valid:
                        log_msg_parts = [f"Вопрос {i+1} в категории '{category}' некорректен или неполон. Пропущен."]
                        if not is_struct_valid:
                             log_msg_parts.append("Ошибка в основной структуре вопроса/ответов (question, options, correct).")
                        if not is_solution_valid:
                             log_msg_parts.append("Ошибка в поле 'solution' - должно быть непустой строкой, если присутствует.")
                        log_msg_parts.append(f"Данные: {q_data}")
                        logger.warning(" ".join(log_msg_parts))
                        malformed_entries.append({
                            "error_type": "invalid_question_format_or_solution",
                            "category": category, "question_index": i, "data": q_data,
                            "reason_struct": not is_struct_valid, "reason_solution": not is_solution_valid
                        })
                        continue

                    try:
                        correct_option_index = q_data["options"].index(q_data["correct"])
                    except ValueError: # Хотя предыдущая проверка должна это покрыть, но на всякий случай
                        logger.warning(f"Правильный ответ для вопроса {i+1} в '{category}' не найден в опциях. Пропущен. Данные: {q_data}")
                        malformed_entries.append({"error_type": "correct_not_in_options", "category": category, "question_index": i, "data": q_data})
                        continue

                    question_entry = {
                        "question": q_data["question"],
                        "options": q_data["options"],
                        "correct_option_index": correct_option_index,
                        "original_category": category
                    }
                    if has_solution and is_solution_valid: # Добавляем solution, если он есть и валиден
                        question_entry["solution"] = q_data["solution"].strip()

                    processed_category_questions.append(question_entry)
                    processed_questions_count += 1

                if processed_category_questions:
                    temp_quiz_data[category] = processed_category_questions
                    valid_categories_count += 1
            state.quiz_data = temp_quiz_data

        logger.info(f"Загружено {processed_questions_count} вопросов из {valid_categories_count} категорий.")

        if malformed_entries:
            logger.warning(f"Обнаружено {len(malformed_entries)} некорректных записей в {QUESTIONS_FILE}. Они записаны в {MALFORMED_QUESTIONS_FILE}")
            try:
                with open(MALFORMED_QUESTIONS_FILE, 'w', encoding='utf-8') as mf:
                    json.dump(malformed_entries, mf, ensure_ascii=False, indent=4)
            except Exception as e_mf:
                logger.error(f"Не удалось записать некорректные записи в {MALFORMED_QUESTIONS_FILE}: {e_mf}")

    except FileNotFoundError:
        logger.error(f"{QUESTIONS_FILE} не найден.")
        state.quiz_data = {}
    except json.JSONDecodeError:
        logger.error(f"Ошибка декодирования JSON в {QUESTIONS_FILE}.")
        state.quiz_data = {}
    except Exception as e:
        logger.error(f"Непредвиденная ошибка загрузки вопросов: {e}", exc_info=True)
        state.quiz_data = {}

def save_user_data():
    # Глубокое копирование перед модификацией для сериализации
    data_to_save = copy.deepcopy(state.user_scores)
    data_to_save_serializable = convert_sets_to_lists_recursively(data_to_save)
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save_serializable, f, ensure_ascii=False, indent=4)
        logger.debug(f"Данные пользователей сохранены в {USERS_FILE}")
    except Exception as e:
        logger.error(f"Ошибка сохранения данных пользователей: {e}", exc_info=True)

def load_user_data():
    try:
        if os.path.exists(USERS_FILE) and os.path.getsize(USERS_FILE) > 0:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
            state.user_scores = convert_user_scores_lists_to_sets(loaded_data)
            logger.info(f"Данные пользователей загружены из {USERS_FILE}.")
        else:
            logger.info(f"{USERS_FILE} не найден или пуст. Старт с пустыми данными пользователей.")
            state.user_scores = {}
    except json.JSONDecodeError:
        logger.error(f"Ошибка декодирования JSON в {USERS_FILE}. Использование пустых данных пользователей.")
        state.user_scores = {}
    except Exception as e:
        logger.error(f"Непредвиденная ошибка загрузки данных пользователей: {e}", exc_info=True)
        state.user_scores = {}

# --- Функции для подписок на ежедневную викторину ---
def load_daily_quiz_subscriptions():
    migrated_subscriptions: Dict[str, Dict[str, Any]] = {}
    file_exists_and_not_empty = os.path.exists(DAILY_QUIZ_SUBSCRIPTIONS_FILE) and os.path.getsize(DAILY_QUIZ_SUBSCRIPTIONS_FILE) > 0

    if not file_exists_and_not_empty:
        logger.info(f"{DAILY_QUIZ_SUBSCRIPTIONS_FILE} не найден или пуст. Нет активных подписок на ежедневную викторину.")
        state.daily_quiz_subscriptions = {}
        return

    try:
        with open(DAILY_QUIZ_SUBSCRIPTIONS_FILE, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)

        if isinstance(raw_data, list): # Old format: list of chat_id_str
            logger.info(f"Обнаружен старый формат {DAILY_QUIZ_SUBSCRIPTIONS_FILE} (список ID чатов). Конвертация в новый формат...")
            for chat_id_old_format in raw_data:
                chat_id_key = str(chat_id_old_format) # Ensure string
                migrated_subscriptions[chat_id_key] = {
                    "hour": DAILY_QUIZ_DEFAULT_HOUR_MSK,
                    "minute": DAILY_QUIZ_DEFAULT_MINUTE_MSK,
                    "categories": None # Default to random categories
                }
            state.daily_quiz_subscriptions = migrated_subscriptions
            logger.info(f"Конвертировано {len(migrated_subscriptions)} подписок в новый формат. Сохранение файла...")
            save_daily_quiz_subscriptions() # Save immediately after migration

        elif isinstance(raw_data, dict): # New format: dict
            for chat_id_key, details in raw_data.items():
                chat_id_str = str(chat_id_key) # Ensure string
                if not isinstance(details, dict):
                    logger.warning(f"Запись для чата {chat_id_str} в {DAILY_QUIZ_SUBSCRIPTIONS_FILE} имеет неверный формат (не словарь). Пропущено.")
                    continue
                
                categories = details.get("categories")
                if categories is not None and not (isinstance(categories, list) and all(isinstance(c, str) for c in categories)):
                    logger.warning(f"Поле 'categories' для чата {chat_id_str} имеет неверный тип (ожидается list[str] или null). Установлено в null.")
                    categories = None
                
                migrated_subscriptions[chat_id_str] = {
                    "hour": details.get("hour", DAILY_QUIZ_DEFAULT_HOUR_MSK),
                    "minute": details.get("minute", DAILY_QUIZ_DEFAULT_MINUTE_MSK),
                    "categories": categories
                }
            state.daily_quiz_subscriptions = migrated_subscriptions
            logger.info(f"Загружено {len(state.daily_quiz_subscriptions)} подписок на ежедневную викторину из {DAILY_QUIZ_SUBSCRIPTIONS_FILE} (новый формат).")
        else:
            logger.error(f"{DAILY_QUIZ_SUBSCRIPTIONS_FILE} содержит данные неизвестного формата. Использование пустого списка подписок.")
            state.daily_quiz_subscriptions = {}

    except json.JSONDecodeError:
        logger.error(f"Ошибка декодирования JSON в {DAILY_QUIZ_SUBSCRIPTIONS_FILE}. Использование пустого списка подписок.")
        state.daily_quiz_subscriptions = {}
    except Exception as e:
        logger.error(f"Непредвиденная ошибка загрузки подписок на ежедневную викторину: {e}", exc_info=True)
        state.daily_quiz_subscriptions = {}


def save_daily_quiz_subscriptions():
    # state.daily_quiz_subscriptions уже имеет формат Dict[str, Dict[str, Any]]
    # Убедимся, что все поля имеют значения по умолчанию, если они отсутствуют (хотя при загрузке это должно быть учтено)
    data_to_save = {}
    for chat_id, details in state.daily_quiz_subscriptions.items():
        data_to_save[str(chat_id)] = { # Убедимся, что chat_id это строка
            "hour": details.get("hour", DAILY_QUIZ_DEFAULT_HOUR_MSK),
            "minute": details.get("minute", DAILY_QUIZ_DEFAULT_MINUTE_MSK),
            "categories": details.get("categories") # Сохраняем None как null в JSON
        }

    try:
        with open(DAILY_QUIZ_SUBSCRIPTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=4)
        logger.debug(f"Подписки на ежедневную викторину сохранены в {DAILY_QUIZ_SUBSCRIPTIONS_FILE}. Количество: {len(data_to_save)}")
    except Exception as e:
        logger.error(f"Ошибка сохранения подписок на ежедневную викторину: {e}", exc_info=True)
