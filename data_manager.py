# data_manager.py
import json
import os
import copy
from typing import List, Dict, Any, Set

from config import logger, QUESTIONS_FILE, USERS_FILE, MALFORMED_QUESTIONS_FILE, DAILY_QUIZ_SUBSCRIPTIONS_FILE
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
    try:
        if os.path.exists(DAILY_QUIZ_SUBSCRIPTIONS_FILE) and os.path.getsize(DAILY_QUIZ_SUBSCRIPTIONS_FILE) > 0:
            with open(DAILY_QUIZ_SUBSCRIPTIONS_FILE, 'r', encoding='utf-8') as f:
                subscriptions_list = json.load(f)
                if isinstance(subscriptions_list, list):
                    state.daily_quiz_subscriptions = set(str(item) for item in subscriptions_list) # Убедимся, что ID - строки
                    logger.info(f"Загружено {len(state.daily_quiz_subscriptions)} подписок на ежедневную викторину из {DAILY_QUIZ_SUBSCRIPTIONS_FILE}.")
                else:
                    logger.error(f"{DAILY_QUIZ_SUBSCRIPTIONS_FILE} должен содержать JSON список. Использование пустого списка подписок.")
                    state.daily_quiz_subscriptions = set()
        else:
            logger.info(f"{DAILY_QUIZ_SUBSCRIPTIONS_FILE} не найден или пуст. Нет активных подписок на ежедневную викторину.")
            state.daily_quiz_subscriptions = set()
    except json.JSONDecodeError:
        logger.error(f"Ошибка декодирования JSON в {DAILY_QUIZ_SUBSCRIPTIONS_FILE}. Использование пустого списка подписок.")
        state.daily_quiz_subscriptions = set()
    except Exception as e:
        logger.error(f"Непредвиденная ошибка загрузки подписок на ежедневную викторину: {e}", exc_info=True)
        state.daily_quiz_subscriptions = set()

def save_daily_quiz_subscriptions():
    subscriptions_list = sorted(list(state.daily_quiz_subscriptions))
    try:
        with open(DAILY_QUIZ_SUBSCRIPTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(subscriptions_list, f, ensure_ascii=False, indent=4)
        logger.debug(f"Подписки на ежедневную викторину сохранены в {DAILY_QUIZ_SUBSCRIPTIONS_FILE}. Количество: {len(subscriptions_list)}")
    except Exception as e:
        logger.error(f"Ошибка сохранения подписок на ежедневную викторину: {e}", exc_info=True)

