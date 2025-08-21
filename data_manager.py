#data_manager.py
import json
import os
import copy
import logging
from pathlib import Path
from typing import Dict, Any, List, Set, Optional, TYPE_CHECKING
import re # Добавляем импорт для регулярных выражений

if TYPE_CHECKING:
    from app_config import AppConfig
    from state import BotState

logger = logging.getLogger(__name__)

class DataManager:
    def __init__(self, app_config: 'AppConfig', state: 'BotState'):
        logger.debug("DataManager.__init__ НАЧАТ.")
        self.app_config = app_config
        self.paths_config = app_config.paths
        self.state = state
        # Паттерн для символов, которые могут вызвать проблемы в Telegram без парсинга
        # Включает символы MarkdownV2 и некоторые другие, которые могут быть интерпретированы как начало сущности.
        # Скобки и точка были замечены в ошибках.
        self._problematic_chars_pattern = re.compile(r'[_\*\\[\\]\\(\\)\~\\`\\>\\#\\+\\-\=\\|\\{\\}\\.\\!]')
        logger.debug("DataManager.__init__ ЗАВЕРШЕН.")

    def _sanitize_text_for_telegram(self, text: str) -> str:
        """
        Sanitizes text to prevent Telegram API errors in plain text fields.
        Focuses on replacing characters known to cause issues like parenthesis.
        """
        if not isinstance(text, str):
            return ""

        # Replace problematic characters for plain text fields.
        # Based on observed errors, primarily parenthesis are an issue.
        sanitized_text = text.replace('(', '(').replace(')', ')')

        return sanitized_text

    def _convert_sets_to_lists_recursively(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: self._convert_sets_to_lists_recursively(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._convert_sets_to_lists_recursively(elem) for elem in obj]
        if isinstance(obj, set):
            # ИСПРАВЛЕНО: Приводим все элементы к строке перед сортировкой,
            # чтобы избежать TypeError при смешанных типах данных в множестве.
            return sorted([str(item) for item in obj])
        return obj

    def _convert_user_scores_lists_to_sets(self, scores_data: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(scores_data, dict): return scores_data
        for chat_id_str, users_in_chat in scores_data.items():
            if isinstance(users_in_chat, dict):
                for user_id_str, user_data_val in users_in_chat.items():
                    if isinstance(user_data_val, dict):
                        # Поля, которые должны быть типа set
                        answered_polls_list = user_data_val.get('answered_polls', [])
                        # Элементы в answered_polls_list могут быть смешанных типов,
                        # set() корректно их обработает. Проблема возникает при сортировке.
                        user_data_val['answered_polls'] = set(answered_polls_list) if isinstance(answered_polls_list, list) else set()

                        milestones_list = user_data_val.get('milestones_achieved', [])
                        user_data_val['milestones_achieved'] = set(milestones_list) if isinstance(milestones_list, list) else set()

                        # Основные поля, которые должны существовать (для обратной совместимости)
                        if 'name' not in user_data_val:
                            user_data_val['name'] = f"Player {user_id_str}"
                            logger.debug(f"Добавлено поле 'name' для user {user_id_str} в chat {chat_id_str} при загрузке старых данных.")
                        if 'score' not in user_data_val:
                            user_data_val['score'] = 0
                            logger.debug(f"Добавлено поле 'score' для user {user_id_str} в chat {chat_id_str} при загрузке старых данных.")

                        # Временные метки (для обратной совместимости)
                        if 'first_answer_time' not in user_data_val:
                            user_data_val['first_answer_time'] = None
                            logger.debug(f"Добавлено поле 'first_answer_time' для user {user_id_str} в chat {chat_id_str} при загрузке старых данных.")
                        if 'last_answer_time' not in user_data_val:
                            user_data_val['last_answer_time'] = None
                            logger.debug(f"Добавлено поле 'last_answer_time' для user {user_id_str} в chat {chat_id_str} при загрузке старых данных.")
        return scores_data

    def load_questions(self) -> None:
        logger.debug(f"Попытка загрузить вопросы из {self.paths_config.questions_file}")
        processed_questions_count = 0
        valid_categories_count = 0
        malformed_entries: List[Dict[str, Any]] = []
        temp_quiz_data: Dict[str, List[Dict[str, Any]]] = {}
        try:
            with open(self.paths_config.questions_file, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            logger.debug(f"Вопросы успешно загружены из {self.paths_config.questions_file}")
            if not isinstance(raw_data, dict):
                logger.error(f"{self.paths_config.questions_file} должен содержать JSON объект (словарь категорий).")
                malformed_entries.append({"error_type": "root_not_dict", "data": raw_data})
            else:
                for category, questions_list in raw_data.items():
                    if not isinstance(questions_list, list):
                        malformed_entries.append({"error_type": "category_not_list", "category": category, "data": questions_list})
                        continue
                    processed_category_questions: List[Dict[str, Any]] = []
                    for i, q_data in enumerate(questions_list):
                        question_text_original = q_data.get("question")
                        options_original = q_data.get("options")
                        correct_text_original = q_data.get("correct")
                        solution_text_original = q_data.get("solution")
                        is_struct_valid = (isinstance(q_data, dict) and isinstance(question_text_original, str) and question_text_original.strip() and isinstance(options_original, list) and len(options_original) >= 2 and all(isinstance(opt, str) for opt in options_original) and isinstance(correct_text_original, str) and correct_text_original.strip())
                        if not is_struct_valid:
                            malformed_entries.append({"error_type": "invalid_question_structure", "category": category, "question_index": i, "data": q_data})
                            continue

                        # Очистка текста вопроса, вариантов ответов и пояснения
                        question_text_stripped_and_sanitized = self._sanitize_text_for_telegram(question_text_original)
                        options_stripped_and_sanitized = [self._sanitize_text_for_telegram(opt) for opt in options_original]
                        correct_text_stripped_and_sanitized = self._sanitize_text_for_telegram(correct_text_original)
                        solution_text_stripped_and_sanitized = None
                        has_solution = "solution" in q_data
                        if has_solution:
                            if isinstance(solution_text_original, str) and solution_text_original.strip():
                                solution_text_stripped_and_sanitized = self._sanitize_text_for_telegram(solution_text_original)
                            else:
                                malformed_entries.append({"error_type": "invalid_solution_format", "category": category, "question_index": i, "data": q_data})

                        # Проверки валидности используем очищенные тексты
                        if not question_text_stripped_and_sanitized:
                             malformed_entries.append({"error_type": "empty_question_after_sanitization", "category": category, "question_index": i, "data": q_data})
                             continue

                        options_valid_final = [opt for opt in options_stripped_and_sanitized if opt]
                        if len(options_valid_final) < 2:
                            malformed_entries.append({"error_type": "insufficient_valid_options_after_sanitization", "category": category, "question_index": i, "data": q_data})
                            continue

                        # Проверка, что правильный ответ всё ещё существует среди очищенных и валидных опций
                        if correct_text_stripped_and_sanitized not in options_valid_final:
                             logger.warning(f"Правильный ответ \'{correct_text_original}\' стал \'{correct_text_stripped_and_sanitized}\' после очистки и не найден среди очищенных опций {options_valid_final} для вопроса в категории {category} (индекс {i}). Вопрос будет пропущен.")
                             malformed_entries.append({"error_type": "correct_not_in_valid_options_after_sanitization", "category": category, "question_index": i, "data": q_data, "sanitized_correct": correct_text_stripped_and_sanitized, "sanitized_options": options_valid_final})
                             continue

                        try:
                            # Индекс правильного ответа ищем среди ОЧИЩЕННЫХ И ВАЛИДНЫХ опций
                            correct_option_index_final = options_valid_final.index(correct_text_stripped_and_sanitized)
                        except ValueError:
                            # Это должно происходить редко, если предыдущая проверка прошла успешно
                            malformed_entries.append({"error_type": "internal_logic_error_correct_option_sanitized", "category": category, "question_index": i, "data": q_data, "sanitized_correct": correct_text_stripped_and_sanitized, "sanitized_options": options_valid_final})
                            continue

                        # Формируем запись вопроса, используя очищенные тексты
                        question_entry = {"id": f"{category.lower().replace(' ', '_')}_{i+1}", "question": question_text_stripped_and_sanitized, "options": options_valid_final, "correct_option_text": correct_text_stripped_and_sanitized, "correct_option_index": correct_option_index_final, "original_category": category}
                        if solution_text_stripped_and_sanitized: question_entry["solution"] = solution_text_stripped_and_sanitized

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
                except Exception as e_mf: logger.error(f"Не удалось записать некорректные записи: {e_mf}")
        except FileNotFoundError:
            self.state.quiz_data = {}
            logger.warning(f"{self.paths_config.questions_file} не найден. state.quiz_data установлен в пустой словарь.")
        except json.JSONDecodeError:
            self.state.quiz_data = {}
            logger.error(f"Ошибка декодирования JSON в {self.paths_config.questions_file}. state.quiz_data установлен в пустой словарь.")
        except Exception as e: self.state.quiz_data = {}
        if not self.state.quiz_data: logger.warning("Словарь state.quiz_data пуст после попытки загрузки.")

    def load_user_data(self) -> None:
        logger.debug(f"Попытка загрузить данные пользователей из {self.paths_config.users_file}")
        try:
            if self.paths_config.users_file.exists() and self.paths_config.users_file.stat().st_size > 0:
                with open(self.paths_config.users_file, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                logger.debug(f"Данные пользователей успешно загружены из {self.paths_config.users_file}")
                self.state.user_scores = self._convert_user_scores_lists_to_sets(loaded_data)
                logger.info(f"Данные пользователей загружены из {self.paths_config.users_file}.")
            else:
                logger.info(f"{self.paths_config.users_file} не найден или пуст. state.user_scores установлен в пустой словарь.")
                self.state.user_scores = {}
        except json.JSONDecodeError:
            self.state.user_scores = {}
            logger.error(f"Ошибка декодирования JSON в {self.paths_config.users_file}. state.user_scores установлен в пустой словарь.")
        except Exception as e:
            self.state.user_scores = {}
            logger.error(f"Непредвиденная ошибка загрузки данных пользователей {self.paths_config.users_file}: {e}", exc_info=True)


    def load_chat_settings(self) -> None:
        logger.debug(f"Попытка загрузить настройки чатов из {self.paths_config.chat_settings_file}")
        loaded_settings: Dict[int, Dict[str, Any]] = {}
        migrated_something_from_old_subs = False
        default_settings_template = copy.deepcopy(self.app_config.default_chat_settings)

        if self.paths_config.chat_settings_file.exists() and self.paths_config.chat_settings_file.stat().st_size > 0:
            try:
                with open(self.paths_config.chat_settings_file, 'r', encoding='utf-8') as f:
                    raw_settings = json.load(f)
                logger.debug(f"Настройки чатов успешно загружены из {self.paths_config.chat_settings_file}")
                for chat_id_str, settings_val in raw_settings.items():
                    try:
                        chat_id_int = int(chat_id_str)
                        if isinstance(settings_val, dict):
                            # Миграция старого формата времени (hour_msk, minute_msk) в times_msk
                            if "daily_quiz" in settings_val and \
                               "hour_msk" in settings_val["daily_quiz"] and \
                               "minute_msk" in settings_val["daily_quiz"] and \
                               "times_msk" not in settings_val["daily_quiz"]:

                                h = settings_val["daily_quiz"].pop("hour_msk")
                                m = settings_val["daily_quiz"].pop("minute_msk")
                                settings_val["daily_quiz"]["times_msk"] = [{"hour": h, "minute": m}]
                                logger.info(f"Мигрировано время для daily_quiz в чате {chat_id_int} в новый формат times_msk.")
                                migrated_something_from_old_subs = True

                            loaded_settings[chat_id_int] = settings_val
                        else:
                            logger.warning(f"Настройки для chat_id '{chat_id_str}' не являются словарем. Пропущены.")
                    except ValueError:
                        logger.warning(f"Некорректный chat_id '{chat_id_str}' в {self.paths_config.chat_settings_file}. Пропущен.")
                logger.info(f"Настройки чатов загружены из {self.paths_config.chat_settings_file}.")
            except Exception as e: logger.error(f"Ошибка загрузки настроек чатов: {e}", exc_info=True)

        self.state.chat_settings = loaded_settings

        logger.debug(f"Проверка наличия файла старых подписок для миграции: {self.paths_config.old_daily_quiz_subscriptions_file}")
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
                        current_chat_s.setdefault("daily_quiz", copy.deepcopy(def_daily_s_template_from_appconfig))
                        current_chat_s["daily_quiz"]["enabled"] = True

                        old_h = sub_details.get("hour")
                        old_m = sub_details.get("minute")
                        if isinstance(old_h, int) and isinstance(old_m, int):
                            if "times_msk" not in current_chat_s["daily_quiz"] or not current_chat_s["daily_quiz"]["times_msk"]:
                                current_chat_s["daily_quiz"]["times_msk"] = [{"hour": old_h, "minute": old_m}]

                        old_cats = sub_details.get("categories")
                        if old_cats and isinstance(old_cats, list) and all(isinstance(c, str) for c in old_cats):
                            current_chat_s["daily_quiz"]["categories_mode"] = "specific"
                            current_chat_s["daily_quiz"]["specific_categories"] = old_cats
                        else:
                            current_chat_s["daily_quiz"]["categories_mode"] = "random"
                            current_chat_s["daily_quiz"]["specific_categories"] = []

                        for key, default_val in def_daily_s_template_from_appconfig.items():
                            if key != "times_msk":
                                current_chat_s["daily_quiz"].setdefault(key, default_val)
                        current_chat_s["daily_quiz"]["num_questions"] = sub_details.get("num_questions", def_daily_s_template_from_appconfig.get("num_questions", 10))
                        migrated_something_from_old_subs = True
                if migrated_something_from_old_subs:
                    logger.info(f"Миграция из {self.paths_config.old_daily_quiz_subscriptions_file} завершена.")
                    try:
                        os.rename(self.paths_config.old_daily_quiz_subscriptions_file, str(self.paths_config.old_daily_quiz_subscriptions_file) + ".migrated")
                        logger.info(f"Старый файл подписок переименован.")
                    except OSError as e: logger.error(f"Не удалось переименовать старый файл подписок: {e}")
            except Exception as e: logger.error(f"Ошибка миграции старых подписок: {e}", exc_info=True)

        if migrated_something_from_old_subs: self.save_chat_settings()

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

    def save_messages_to_delete(self) -> None:
        """Сохраняет сообщения для удаления в файл"""
        data_to_save = {str(chat_id): list(message_ids) for chat_id, message_ids in self.state.generic_messages_to_delete.items()}
        try:
            with open(self.paths_config.messages_to_delete_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
            logger.debug(f"Сообщения для удаления сохранены ({len(data_to_save)} чатов).")
        except Exception as e: logger.error(f"Ошибка сохранения сообщений для удаления: {e}", exc_info=True)

    def load_messages_to_delete(self) -> None:
        """Загружает сообщения для удаления из файла"""
        try:
            if not self.paths_config.messages_to_delete_file.exists():
                logger.debug(f"Файл сообщений для удаления не найден: {self.paths_config.messages_to_delete_file}")
                return
            
            with open(self.paths_config.messages_to_delete_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Преобразуем строковые ключи обратно в int и списки в множества
            for chat_id_str, message_ids_list in data.items():
                try:
                    chat_id = int(chat_id_str)
                    self.state.generic_messages_to_delete[chat_id] = set(message_ids_list)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Ошибка преобразования данных для чата {chat_id_str}: {e}")
            
            total_messages = sum(len(message_ids) for message_ids in self.state.generic_messages_to_delete.values())
            logger.info(f"Загружено {total_messages} сообщений для удаления из {len(self.state.generic_messages_to_delete)} чатов.")
            
        except Exception as e: 
            logger.error(f"Ошибка загрузки сообщений для удаления: {e}", exc_info=True)

    def save_all_data(self) -> None:
        logger.info("Сохранение всех данных...")
        self.save_user_data()
        self.save_chat_settings()
        self.save_messages_to_delete()
        logger.info("Сохранение всех данных завершено.")

    def load_all_data(self) -> None:
        logger.debug("Начало загрузки всех данных...")
        self.load_questions()
        self.load_user_data()
        self.load_chat_settings()
        self.load_messages_to_delete()
        logger.debug("Загрузка всех данных завершена.")

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
        logger.info(f"Настройка '{'.'.join(key_path)}' для чата {chat_id} обновлена на: {value}")

    def reset_chat_settings(self, chat_id: int) -> None:
        if chat_id in self.state.chat_settings:
            del self.state.chat_settings[chat_id]
            logger.info(f"Настройки для чата {chat_id} сброшены.")
            self.save_chat_settings()
        else:
            logger.info(f"Для чата {chat_id} не было специфичных настроек для сброса.")

    def get_all_questions(self) -> Dict[str, List[Dict[str, Any]]]:
        return self.state.quiz_data

    def get_global_setting(self, key: str, default_value: Any = None) -> Any:
        """Получает глобальную настройку из state"""
        if not hasattr(self.state, 'global_settings'):
            self.state.global_settings = {}
        return self.state.global_settings.get(key, default_value)

    def update_global_setting(self, key: str, value: Any) -> None:
        """Обновляет глобальную настройку в state"""
        if not hasattr(self.state, 'global_settings'):
            self.state.global_settings = {}
        self.state.global_settings[key] = value
        logger.debug(f"Глобальная настройка '{key}' обновлена")
