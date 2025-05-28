#data_manager.py
import json
import os
import copy
import logging
from pathlib import Path
from typing import Dict, Any, List, Set, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app_config import AppConfig
    from state import BotState

logger = logging.getLogger(__name__)

class DataManager:
    def __init__(self, app_config: 'AppConfig', state: 'BotState'):
        self.app_config = app_config
        self.paths_config = app_config.paths
        self.state = state

    def _convert_sets_to_lists_recursively(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: self._convert_sets_to_lists_recursively(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._convert_sets_to_lists_recursively(elem) for elem in obj]
        if isinstance(obj, set):
            return sorted(list(obj))
        return obj

    def _convert_user_scores_lists_to_sets(self, scores_data: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(scores_data, dict): return scores_data
        for chat_id_str, users_in_chat in scores_data.items():
            if isinstance(users_in_chat, dict):
                for user_id_str, user_data_val in users_in_chat.items():
                    if isinstance(user_data_val, dict):
                        if 'answered_polls' in user_data_val and isinstance(user_data_val['answered_polls'], list):
                            user_data_val['answered_polls'] = set(user_data_val['answered_polls'])
                        if 'milestones_achieved' in user_data_val and isinstance(user_data_val['milestones_achieved'], list):
                            user_data_val['milestones_achieved'] = set(user_data_val['milestones_achieved'])
        return scores_data

    def load_questions(self) -> None:
        processed_questions_count = 0
        valid_categories_count = 0
        malformed_entries: List[Dict[str, Any]] = []
        temp_quiz_data: Dict[str, List[Dict[str, Any]]] = {}

        try:
            with open(self.paths_config.questions_file, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)

            if not isinstance(raw_data, dict):
                logger.error(f"{self.paths_config.questions_file} должен содержать JSON объект (словарь категорий).")
                malformed_entries.append({"error_type": "root_not_dict", "data": raw_data})
            else:
                for category, questions_list in raw_data.items():
                    if not isinstance(questions_list, list):
                        logger.warning(f"Категория '{category}' не является списком вопросов. Пропущена.")
                        malformed_entries.append({"error_type": "category_not_list", "category": category, "data": questions_list})
                        continue

                    processed_category_questions: List[Dict[str, Any]] = []
                    for i, q_data in enumerate(questions_list):
                        question_text_original = q_data.get("question")
                        options_original = q_data.get("options")
                        correct_text_original = q_data.get("correct")
                        solution_text_original = q_data.get("solution")

                        is_struct_valid = (
                            isinstance(q_data, dict) and
                            isinstance(question_text_original, str) and question_text_original.strip() and
                            isinstance(options_original, list) and len(options_original) >= 2 and
                            all(isinstance(opt, str) for opt in options_original) and
                            isinstance(correct_text_original, str) and correct_text_original.strip()
                        )
                        if not is_struct_valid:
                            logger.warning(f"Вопрос {i+1} в категории '{category}' имеет невалидную структуру. Пропущен. Данные: {q_data}")
                            malformed_entries.append({"error_type": "invalid_question_structure", "category": category, "question_index": i, "data": q_data})
                            continue

                        question_text_stripped = question_text_original.strip()
                        options_stripped = [opt.strip() for opt in options_original]
                        options_valid_final = [opt for opt in options_stripped if opt] # Убираем пустые строки после strip

                        if len(options_valid_final) < 2:
                            logger.warning(f"Вопрос {i+1} в категории '{category}' имеет менее двух валидных опций после очистки. Пропущен. Данные: {q_data}")
                            malformed_entries.append({"error_type": "insufficient_valid_options", "category": category, "question_index": i, "data": q_data})
                            continue
                        
                        correct_text_stripped = correct_text_original.strip()
                        if correct_text_stripped not in options_valid_final:
                            logger.warning(f"Правильный ответ '{correct_text_stripped}' для вопроса {i+1} в '{category}' не найден среди валидных опций {options_valid_final}. Пропущен. Данные: {q_data}")
                            malformed_entries.append({"error_type": "correct_not_in_valid_options", "category": category, "question_index": i, "data": q_data})
                            continue
                        
                        try:
                            correct_option_index_final = options_valid_final.index(correct_text_stripped)
                        except ValueError: # Теоретически не должно произойти из-за проверки выше
                            logger.error(f"КРИТИЧЕСКАЯ ОШИБКА ЛОГИКИ: правильный ответ '{correct_text_stripped}' не найден в {options_valid_final}. Пропущен.")
                            malformed_entries.append({"error_type": "internal_logic_error_correct_option", "category": category, "question_index": i, "data": q_data})
                            continue

                        has_solution = "solution" in q_data
                        solution_text_stripped = None
                        if has_solution:
                            if isinstance(solution_text_original, str) and solution_text_original.strip():
                                solution_text_stripped = solution_text_original.strip()
                            else:
                                logger.warning(f"Решение для вопроса {i+1} в категории '{category}' некорректно (не строка или пустое). Решение пропущено. Данные: {q_data}")
                                malformed_entries.append({"error_type": "invalid_solution_format", "category": category, "question_index": i, "data": q_data})
                        
                        question_entry = {
                            "id": f"{category.lower().replace(' ', '_')}_{i+1}",
                            "question": question_text_stripped,
                            "options": options_valid_final,
                            "correct_option_text": correct_text_stripped,
                            "correct_option_index": correct_option_index_final,
                            "original_category": category
                        }
                        if solution_text_stripped:
                            question_entry["solution"] = solution_text_stripped

                        processed_category_questions.append(question_entry)
                        processed_questions_count += 1

                    if processed_category_questions:
                        temp_quiz_data[category] = processed_category_questions
                        valid_categories_count += 1
            
            self.state.quiz_data = temp_quiz_data
            logger.info(f"Загружено {processed_questions_count} вопросов из {valid_categories_count} категорий.")

            if malformed_entries:
                logger.warning(f"Обнаружено {len(malformed_entries)} некорректных записей в {self.paths_config.questions_file}. Они записаны в {self.paths_config.malformed_questions_file}")
                try:
                    with open(self.paths_config.malformed_questions_file, 'w', encoding='utf-8') as mf:
                        json.dump(malformed_entries, mf, ensure_ascii=False, indent=4)
                except Exception as e_mf:
                    logger.error(f"Не удалось записать некорректные записи: {e_mf}")
        except FileNotFoundError:
            logger.error(f"{self.paths_config.questions_file} не найден.")
            self.state.quiz_data = {}
        except json.JSONDecodeError:
            logger.error(f"Ошибка декодирования JSON в {self.paths_config.questions_file}.")
            self.state.quiz_data = {}
        except Exception as e:
            logger.error(f"Непредвиденная ошибка загрузки вопросов: {e}", exc_info=True)
            self.state.quiz_data = {}
        if not self.state.quiz_data:
             logger.warning("Словарь state.quiz_data пуст после попытки загрузки.")

    def load_user_data(self) -> None:
        try:
            if self.paths_config.users_file.exists() and self.paths_config.users_file.stat().st_size > 0:
                with open(self.paths_config.users_file, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                self.state.user_scores = self._convert_user_scores_lists_to_sets(loaded_data)
                logger.info(f"Данные пользователей загружены из {self.paths_config.users_file}.")
            else:
                logger.info(f"{self.paths_config.users_file} не найден или пуст.")
                self.state.user_scores = {}
        except json.JSONDecodeError:
            logger.error(f"Ошибка декодирования JSON в {self.paths_config.users_file}.")
            self.state.user_scores = {}
        except Exception as e:
            logger.error(f"Непредвиденная ошибка загрузки данных пользователей: {e}", exc_info=True)
            self.state.user_scores = {}

    def load_chat_settings(self) -> None:
        loaded_settings: Dict[int, Dict[str, Any]] = {}
        migrated_something = False
        default_settings_template = copy.deepcopy(self.app_config.default_chat_settings)

        if self.paths_config.chat_settings_file.exists() and self.paths_config.chat_settings_file.stat().st_size > 0:
            try:
                with open(self.paths_config.chat_settings_file, 'r', encoding='utf-8') as f:
                    raw_settings = json.load(f)
                for chat_id_str, settings_val in raw_settings.items():
                    try:
                        chat_id_int = int(chat_id_str)
                        if isinstance(settings_val, dict):
                            loaded_settings[chat_id_int] = settings_val
                        else:
                            logger.warning(f"Настройки для chat_id '{chat_id_str}' не являются словарем. Пропущены.")
                    except ValueError:
                        logger.warning(f"Некорректный chat_id '{chat_id_str}' в {self.paths_config.chat_settings_file}. Пропущен.")
                logger.info(f"Настройки чатов загружены из {self.paths_config.chat_settings_file}.")
            except Exception as e: logger.error(f"Ошибка загрузки настроек чатов: {e}", exc_info=True)

        self.state.chat_settings = loaded_settings

        if self.paths_config.old_daily_quiz_subscriptions_file.exists() and \
           self.paths_config.old_daily_quiz_subscriptions_file.stat().st_size > 0:
            logger.info(f"Обнаружен файл старых подписок {self.paths_config.old_daily_quiz_subscriptions_file}. Попытка миграции...")
            try:
                with open(self.paths_config.old_daily_quiz_subscriptions_file, 'r', encoding='utf-8') as f:
                    old_subs_data = json.load(f)
                
                def_daily_s_template_from_appconfig = self.app_config.daily_quiz_defaults

                if isinstance(old_subs_data, dict):
                    for chat_id_str, sub_details in old_subs_data.items():
                        try: chat_id_int = int(chat_id_str)
                        except ValueError: continue
                        if not isinstance(sub_details, dict): continue

                        self.state.chat_settings.setdefault(chat_id_int, copy.deepcopy(default_settings_template))
                        current_chat_s = self.state.chat_settings[chat_id_int]
                        current_chat_s.setdefault("daily_quiz", copy.deepcopy(def_daily_s_template_from_appconfig)) # Используем полный дефолт из appconfig

                        current_chat_s["daily_quiz"]["enabled"] = True
                        current_chat_s["daily_quiz"]["hour_msk"] = sub_details.get("hour", def_daily_s_template_from_appconfig["hour_msk"])
                        current_chat_s["daily_quiz"]["minute_msk"] = sub_details.get("minute", def_daily_s_template_from_appconfig["minute_msk"])
                        
                        old_cats = sub_details.get("categories")
                        if old_cats and isinstance(old_cats, list) and all(isinstance(c, str) for c in old_cats):
                            current_chat_s["daily_quiz"]["categories_mode"] = "specific"
                            current_chat_s["daily_quiz"]["specific_categories"] = old_cats
                        else:
                            current_chat_s["daily_quiz"]["categories_mode"] = "random"
                            current_chat_s["daily_quiz"]["specific_categories"] = [] # Явно

                        # Убедимся, что остальные поля daily_quiz присутствуют, беря их из daily_quiz_defaults
                        for key, default_val in def_daily_s_template_from_appconfig.items():
                            current_chat_s["daily_quiz"].setdefault(key, default_val)
                        # num_questions из app_config.daily_quiz_questions_count_default, если в sub_details нет
                        current_chat_s["daily_quiz"]["num_questions"] = sub_details.get("num_questions", self.app_config.daily_quiz_questions_count_default)


                        migrated_something = True
                if migrated_something:
                    logger.info(f"Миграция из {self.paths_config.old_daily_quiz_subscriptions_file} завершена.")
                    try:
                        os.rename(self.paths_config.old_daily_quiz_subscriptions_file, str(self.paths_config.old_daily_quiz_subscriptions_file) + ".migrated")
                        logger.info(f"Старый файл подписок переименован.")
                    except OSError as e: logger.error(f"Не удалось переименовать старый файл подписок: {e}")
            except Exception as e: logger.error(f"Ошибка миграции старых подписок: {e}", exc_info=True)

        if migrated_something: self.save_chat_settings()

    def get_chat_settings(self, chat_id: int) -> Dict[str, Any]:
        defaults = copy.deepcopy(self.app_config.default_chat_settings)
        if chat_id in self.state.chat_settings:
            chat_specific = self.state.chat_settings[chat_id]
            self._deep_merge_dicts(defaults, chat_specific)
        return defaults

    def _deep_merge_dicts(self, base_dict: Dict[Any, Any], updates_dict: Dict[Any, Any]) -> None:
        for key, value in updates_dict.items():
            if isinstance(value, dict) and key in base_dict and isinstance(base_dict[key], dict):
                self._deep_merge_dicts(base_dict[key], value)
            else:
                base_dict[key] = value

    def save_user_data(self) -> None:
        data_to_save = self._convert_sets_to_lists_recursively(self.state.user_scores)
        try:
            with open(self.paths_config.users_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
            logger.debug(f"Данные пользователей сохранены в {self.paths_config.users_file}")
        except Exception as e: logger.error(f"Ошибка сохранения данных пользователей: {e}", exc_info=True)

    def save_chat_settings(self) -> None:
        data_to_save = {str(chat_id): settings for chat_id, settings in self.state.chat_settings.items()}
        try:
            with open(self.paths_config.chat_settings_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
            logger.debug(f"Настройки чатов сохранены ({len(data_to_save)} чатов).")
        except Exception as e: logger.error(f"Ошибка сохранения настроек чатов: {e}", exc_info=True)

    def save_all_data(self) -> None:
        logger.info("Сохранение всех данных...")
        self.save_user_data()
        self.save_chat_settings()
        logger.info("Сохранение всех данных завершено.")

    def load_all_data(self) -> None:
        logger.info("Загрузка всех данных...")
        self.load_questions()
        self.load_user_data()
        self.load_chat_settings()
        logger.info("Загрузка всех данных завершена.")

    def update_chat_setting(self, chat_id: int, key_path: List[str], value: Any) -> None:
        if chat_id not in self.state.chat_settings:
            self.state.chat_settings[chat_id] = copy.deepcopy(self.app_config.default_chat_settings)

        current_level = self.state.chat_settings[chat_id]
        for i, key_part in enumerate(key_path):
            if i == len(key_path) - 1:
                current_level[key_part] = value
            else:
                current_level = current_level.setdefault(key_part, {})
        self.save_chat_settings()
        logger.info(f"Настройка '{'.'.join(key_path)}' для чата {chat_id} обновлена.")

    def reset_chat_settings(self, chat_id: int) -> None:
        if chat_id in self.state.chat_settings:
            del self.state.chat_settings[chat_id]
            logger.info(f"Настройки для чата {chat_id} сброшены.")
            self.save_chat_settings()
        else:
            logger.info(f"Для чата {chat_id} не было специфичных настроек для сброса.")

    def get_all_questions(self) -> Dict[str, List[Dict[str, Any]]]:
        return self.state.quiz_data
