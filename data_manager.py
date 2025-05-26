# data_manager.py
import json
import os
import copy
from typing import List, Dict, Any, Set, Optional

from config import (logger, QS_F, USRS_F, BAD_QS_F, # Renamed constants
                    DQS_F, DQ_DEF_H, DQ_DEF_M)
import state

# --- Вспомогательные функции для сериализации/десериализации ---
def sets_to_lists_rec(obj: Any) -> Any: # Renamed from convert_sets_to_lists_recursively
    if isinstance(obj, dict):
        return {k: sets_to_lists_rec(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sets_to_lists_rec(elem) for elem in obj]
    if isinstance(obj, set):
        return sorted(list(obj))
    return obj

def usr_scores_lists_to_sets(scores_data: Dict[str, Any]) -> Dict[str, Any]: # Renamed from convert_user_scores_lists_to_sets
    if not isinstance(scores_data, dict):
        return scores_data
    for cid, users_in_chat in scores_data.items():
        if isinstance(users_in_chat, dict):
            for uid, usr_data_val in users_in_chat.items():
                if isinstance(usr_data_val, dict):
                    if 'answered_polls' in usr_data_val and isinstance(usr_data_val['answered_polls'], list):
                        usr_data_val['answered_polls'] = set(usr_data_val['answered_polls'])
                    if 'milestones_achieved' in usr_data_val and isinstance(usr_data_val['milestones_achieved'], list):
                        usr_data_val['milestones_achieved'] = set(usr_data_val['milestones_achieved'])
    return scores_data

# --- Функции загрузки и сохранения данных ---
def load_qs(): # Renamed from load_questions
    proc_qs_count, valid_cats_count = 0, 0
    bad_entries = []
    try:
        with open(QS_F, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        if not isinstance(raw_data, dict):
            logger.error(f"{QS_F} должен содержать JSON объект (словарь категорий).")
            bad_entries.append({"error_type": "root_not_dict", "data": raw_data})
            state.qs_data = {}
        else:
            temp_qs_data = {}
            for cat, qs_list in raw_data.items():
                if not isinstance(qs_list, list):
                    logger.warning(f"Категория '{cat}' не является списком вопросов. Пропущена.")
                    bad_entries.append({"error_type": "category_not_list", "category": cat, "data": qs_list})
                    continue

                proc_cat_qs = []
                for i, q_item in enumerate(qs_list): # Renamed q_data to q_item
                    is_struct_ok = (isinstance(q_item, dict) and
                                   all(k in q_item for k in ["question", "options", "correct"]) and
                                   isinstance(q_item.get("question"), str) and q_item["question"].strip() and
                                   isinstance(q_item.get("options"), list) and len(q_item["options"]) >= 2 and
                                   all(isinstance(opt, str) and opt.strip() for opt in q_item["options"]) and
                                   isinstance(q_item.get("correct"), str) and q_item["correct"].strip() and
                                   q_item["correct"] in q_item["options"])

                    has_sol = "solution" in q_item
                    is_sol_ok = not has_sol or \
                                     (isinstance(q_item.get("solution"), str) and q_item.get("solution", "").strip())

                    if not is_struct_ok or not is_sol_ok:
                        log_parts = [f"Вопрос {i+1} в категории '{cat}' некорректен. Пропущен."]
                        if not is_struct_ok: log_parts.append("Ошибка в структуре (question, options, correct).")
                        if not is_sol_ok: log_parts.append("Ошибка в 'solution'.")
                        log_parts.append(f"Данные: {q_item}")
                        logger.warning(" ".join(log_parts))
                        bad_entries.append({
                            "error_type": "invalid_q_format", "category": cat, "q_idx": i, "data": q_item, # Renamed fields
                            "reason_struct": not is_struct_ok, "reason_solution": not is_sol_ok
                        })
                        continue
                    try:
                        correct_opt_idx = q_item["options"].index(q_item["correct"])
                    except ValueError:
                        logger.warning(f"Правильный ответ для вопроса {i+1} в '{cat}' не найден в опциях. Пропущен. Данные: {q_item}")
                        bad_entries.append({"error_type": "correct_not_in_opts", "category": cat, "q_idx": i, "data": q_item})
                        continue

                    q_entry = {
                        "question": q_item["question"],
                        "options": q_item["options"],
                        "correct_option_index": correct_opt_idx,
                        "original_category": cat
                    }
                    if has_sol and is_sol_ok:
                        q_entry["solution"] = q_item["solution"].strip()

                    proc_cat_qs.append(q_entry)
                    proc_qs_count += 1

                if proc_cat_qs:
                    temp_qs_data[cat] = proc_cat_qs
                    valid_cats_count += 1
            state.qs_data = temp_qs_data

        logger.info(f"Загружено {proc_qs_count} вопросов из {valid_cats_count} категорий.")

        if bad_entries:
            logger.warning(f"Обнаружено {len(bad_entries)} некорректных записей в {QS_F}. Они записаны в {BAD_QS_F}")
            try:
                with open(BAD_QS_F, 'w', encoding='utf-8') as mf:
                    json.dump(bad_entries, mf, ensure_ascii=False, indent=4)
            except Exception as e_mf:
                logger.error(f"Не удалось записать некорректные записи в {BAD_QS_F}: {e_mf}")

    except FileNotFoundError:
        logger.error(f"{QS_F} не найден.")
        state.qs_data = {}
    except json.JSONDecodeError:
        logger.error(f"Ошибка декодирования JSON в {QS_F}.")
        state.qs_data = {}
    except Exception as e:
        logger.error(f"Непредвиденная ошибка загрузки вопросов: {e}", exc_info=True)
        state.qs_data = {}

def save_usr_data(): # Renamed from save_user_data
    data_to_save = copy.deepcopy(state.usr_scores)
    serializable_data = sets_to_lists_rec(data_to_save) # Renamed var
    try:
        with open(USRS_F, 'w', encoding='utf-8') as f:
            json.dump(serializable_data, f, ensure_ascii=False, indent=4)
        logger.debug(f"Данные пользователей сохранены в {USRS_F}")
    except Exception as e:
        logger.error(f"Ошибка сохранения данных пользователей: {e}", exc_info=True)

def load_usr_data(): # Renamed from load_user_data
    try:
        if os.path.exists(USRS_F) and os.path.getsize(USRS_F) > 0:
            with open(USRS_F, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
            state.usr_scores = usr_scores_lists_to_sets(loaded_data)
            logger.info(f"Данные пользователей загружены из {USRS_F}.")
        else:
            logger.info(f"{USRS_F} не найден или пуст. Старт с пустыми данными пользователей.")
            state.usr_scores = {}
    except json.JSONDecodeError:
        logger.error(f"Ошибка декодирования JSON в {USRS_F}. Использование пустых данных.")
        state.usr_scores = {}
    except Exception as e:
        logger.error(f"Непредвиденная ошибка загрузки данных пользователей: {e}", exc_info=True)
        state.usr_scores = {}

# --- Функции для подписок на ежедневную викторину ---
def load_daily_q_subs(): # Renamed from load_daily_quiz_subscriptions
    migrated_subs: Dict[str, Dict[str, Any]] = {}
    file_ok = os.path.exists(DQS_F) and os.path.getsize(DQS_F) > 0

    if not file_ok:
        logger.info(f"{DQS_F} не найден или пуст. Нет активных подписок.")
        state.daily_q_subs = {}
        return

    try:
        with open(DQS_F, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)

        if isinstance(raw_data, list):
            logger.info(f"Обнаружен старый формат {DQS_F}. Конвертация...")
            for cid_old in raw_data:
                cid_key = str(cid_old)
                migrated_subs[cid_key] = {
                    "hour": DQ_DEF_H, "minute": DQ_DEF_M, "categories": None
                }
            state.daily_q_subs = migrated_subs
            logger.info(f"Конвертировано {len(migrated_subs)} подписок. Сохранение...")
            save_daily_q_subs()
        elif isinstance(raw_data, dict):
            for cid_key, details in raw_data.items():
                cid_str = str(cid_key)
                if not isinstance(details, dict):
                    logger.warning(f"Запись для чата {cid_str} в {DQS_F} неверна. Пропущено.")
                    continue
                cats = details.get("categories")
                if cats is not None and not (isinstance(cats, list) and all(isinstance(c, str) for c in cats)):
                    logger.warning(f"Поле 'categories' для чата {cid_str} неверно. Установлено в null.")
                    cats = None
                migrated_subs[cid_str] = {
                    "hour": details.get("hour", DQ_DEF_H),
                    "minute": details.get("minute", DQ_DEF_M),
                    "categories": cats
                }
            state.daily_q_subs = migrated_subs
            logger.info(f"Загружено {len(state.daily_q_subs)} подписок из {DQS_F}.")
        else:
            logger.error(f"{DQS_F} содержит данные неизвестного формата.")
            state.daily_q_subs = {}

    except json.JSONDecodeError:
        logger.error(f"Ошибка декодирования JSON в {DQS_F}.")
        state.daily_q_subs = {}
    except Exception as e:
        logger.error(f"Непредвиденная ошибка загрузки подписок: {e}", exc_info=True)
        state.daily_q_subs = {}

def save_daily_q_subs(): # Renamed from save_daily_quiz_subscriptions
    data_to_save = {}
    for cid, details in state.daily_q_subs.items():
        data_to_save[str(cid)] = {
            "hour": details.get("hour", DQ_DEF_H),
            "minute": details.get("minute", DQ_DEF_M),
            "categories": details.get("categories")
        }
    try:
        with open(DQS_F, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=4)
        logger.debug(f"Подписки на ежедневную викторину сохранены в {DQS_F}. Кол-во: {len(data_to_save)}")
    except Exception as e:
        logger.error(f"Ошибка сохранения подписок: {e}", exc_info=True)
