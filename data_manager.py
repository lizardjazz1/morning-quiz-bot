#data_manager.py
import json
import os
import copy
from typing import List, Dict, Any, Set

# Импорты из других модулей проекта
from config import logger, QUESTIONS_FILE, USERS_FILE
import state # Для доступа и изменения глобальных переменных состояния

# --- Вспомогательные функции для сериализации/десериализации ---
# Эти функции используются только внутри data_manager.py для корректного сохранения set в JSON.

def convert_sets_to_lists_recursively(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: convert_sets_to_lists_recursively(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_sets_to_lists_recursively(elem) for elem in obj]
    if isinstance(obj, set):
        return list(obj)
    return obj

def convert_user_scores_lists_to_sets(scores_data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(scores_data, dict):
        return scores_data
    for chat_id, users_in_chat in scores_data.items():
        if isinstance(users_in_chat, dict):
            for user_id, user_data_val in users_in_chat.items():
                if isinstance(user_data_val, dict) and \
                   'answered_polls' in user_data_val and \
                   isinstance(user_data_val['answered_polls'], list):
                    user_data_val['answered_polls'] = set(user_data_val['answered_polls'])
    return scores_data

# --- Функции загрузки и сохранения данных ---

# load_questions: Загружает вопросы из QUESTIONS_FILE в state.quiz_data.
# Вызывается из bot.py при старте.
def load_questions():
    processed_questions_count, valid_categories_count = 0, 0
    try:
        with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        if not isinstance(raw_data, dict):
            logger.error(f"{QUESTIONS_FILE} должен содержать JSON объект.")
            return
        temp_quiz_data = {}
        for category, questions_list in raw_data.items():
            if not isinstance(questions_list, list):
                logger.warning(f"Категория '{category}' не список. Пропущена.")
                continue
            processed_category_questions = []
            for i, q_data in enumerate(questions_list):
                if not (isinstance(q_data, dict) and
                        all(k in q_data for k in ["question", "options", "correct"]) and
                        isinstance(q_data["options"], list) and len(q_data["options"]) >= 2 and
                        q_data["correct"] in q_data["options"]):
                    logger.warning(f"Вопрос {i+1} в '{category}' некорректен. Пропущен. Данные: {q_data}")
                    continue
                correct_option_index = q_data["options"].index(q_data["correct"])
                processed_category_questions.append({
                    "question": q_data["question"],
                    "options": q_data["options"],
                    "correct_option_index": correct_option_index,
                    "original_category": category
                })
                processed_questions_count += 1
            if processed_category_questions:
                temp_quiz_data[category] = processed_category_questions
                valid_categories_count += 1
        state.quiz_data = temp_quiz_data # Обновляем глобальное состояние
        logger.info(f"Загружено {processed_questions_count} вопросов из {valid_categories_count} категорий.")
    except FileNotFoundError:
        logger.error(f"{QUESTIONS_FILE} не найден.")
    except json.JSONDecodeError:
        logger.error(f"Ошибка декодирования JSON в {QUESTIONS_FILE}.")
    except Exception as e:
        logger.error(f"Ошибка загрузки вопросов: {e}", exc_info=True)

# save_user_data: Сохраняет state.user_scores в USERS_FILE.
# Вызывается из command_handlers.py (/start) и poll_answer_handler.py.
def save_user_data():
    data_to_save = copy.deepcopy(state.user_scores)
    data_to_save_serializable = convert_sets_to_lists_recursively(data_to_save)
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save_serializable, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}", exc_info=True)

# load_user_data: Загружает данные пользователей из USERS_FILE в state.user_scores.
# Вызывается из bot.py при старте.
def load_user_data():
    try:
        if os.path.exists(USERS_FILE) and os.path.getsize(USERS_FILE) > 0:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
            state.user_scores = convert_user_scores_lists_to_sets(loaded_data)
            logger.info("Данные пользователей загружены.")
        else:
            logger.info(f"{USERS_FILE} не найден или пуст. Старт с пустыми данными.")
            state.user_scores = {}
    except json.JSONDecodeError:
        logger.error(f"Ошибка декодирования {USERS_FILE}. Использование пустых данных.")
        state.user_scores = {}
    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}", exc_info=True)
        state.user_scores = {}
