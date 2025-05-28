# bot/data_manager.py
import json
import os
import copy # Для deepcopy при слиянии настроек
import logging
from pathlib import Path
from typing import Dict, Any, List, Set, Optional, Tuple

# Прямые импорты AppConfig и BotState НЕ НУЖНЫ, если DataManager получает их экземпляры
# from .app_config import AppConfig # НЕПРАВИЛЬНО, если передаем через конструктор
# from .state import BotState # НЕПРАВИЛЬНО, если передаем через конструктор

logger = logging.getLogger(__name__)

class DataManager:
    def __init__(self, paths_config, state: 'BotState', app_config: 'AppConfig'): # Используем кавычки для type hint BotState/AppConfig из-за циклической зависимости при импорте типов
        self.paths_config = paths_config # Экземпляр PathConfig из AppConfig
        self.state = state             # Экземпляр BotState
        self.app_config = app_config   # Экземпляр AppConfig (для default_chat_settings)

    # --- Вспомогательные функции для сериализации/десериализации ---
    def _convert_sets_to_lists_recursively(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: self._convert_sets_to_lists_recursively(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._convert_sets_to_lists_recursively(elem) for elem in obj]
        if isinstance(obj, set):
            return sorted(list(obj)) # Сортируем для консистентности при сохранении
        return obj

    def _convert_user_scores_lists_to_sets(self, scores_data: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(scores_data, dict): return scores_data
        # Ключи chat_id (строки) и user_id (строки) остаются как есть из JSON
        for chat_id_str, users_in_chat in scores_data.items():
            if isinstance(users_in_chat, dict):
                for user_id_str, user_data_val in users_in_chat.items():
                    if isinstance(user_data_val, dict):
                        if 'answered_polls' in user_data_val and isinstance(user_data_val['answered_polls'], list):
                            user_data_val['answered_polls'] = set(user_data_val['answered_polls'])
                        if 'milestones_achieved' in user_data_val and isinstance(user_data_val['milestones_achieved'], list):
                            user_data_val['milestones_achieved'] = set(user_data_val['milestones_achieved'])
        return scores_data

    # --- Загрузка данных ---
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
                        is_struct_valid = (
                            isinstance(q_data, dict) and
                            all(k in q_data for k in ["question", "options", "correct"]) and
                            isinstance(q_data.get("question"), str) and q_data["question"].strip() and
                            isinstance(q_data.get("options"), list) and len(q_data["options"]) >= 2 and
                            all(isinstance(opt, str) and opt.strip() for opt in q_data["options"]) and
                            isinstance(q_data.get("correct"), str) and q_data["correct"].strip() and
                            q_data["correct"] in q_data["options"]
                        )
                        has_solution = "solution" in q_data
                        is_solution_valid = not has_solution or \
                                            (isinstance(q_data.get("solution"), str) and q_data.get("solution", "").strip())

                        if not is_struct_valid or not is_solution_valid:
                            logger.warning(f"Вопрос {i+1} в категории '{category}' некорректен. Пропущен. Данные: {q_data}")
                            malformed_entries.append({
                                "error_type": "invalid_question_format_or_solution", "category": category,
                                "question_index": i, "data": q_data
                            })
                            continue
                        
                        try:
                            correct_option_index = q_data["options"].index(q_data["correct"])
                        except ValueError:
                            logger.warning(f"Правильный ответ для вопроса {i+1} в '{category}' не найден в опциях. Пропущен. Данные: {q_data}")
                            malformed_entries.append({"error_type": "correct_not_in_options", "category": category, "question_index": i, "data": q_data})
                            continue

                        question_entry = {
                            "id": f"{category.lower().replace(' ', '_')}_{i+1}", # Уникальный ID для вопроса
                            "question": q_data["question"],
                            "options": q_data["options"],
                            "correct_option_text": q_data["correct"], # Сохраняем текст правильного ответа
                            "correct_option_index": correct_option_index,
                            "original_category": category
                        }
                        if has_solution and is_solution_valid:
                            question_entry["solution"] = q_data["solution"].strip()
                        
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
                    logger.error(f"Не удалось записать некорректные записи в {self.paths_config.malformed_questions_file}: {e_mf}")

        except FileNotFoundError:
            logger.error(f"{self.paths_config.questions_file} не найден.")
        except json.JSONDecodeError:
            logger.error(f"Ошибка декодирования JSON в {self.paths_config.questions_file}.")
        except Exception as e:
            logger.error(f"Непредвиденная ошибка загрузки вопросов: {e}", exc_info=True)
        
        if not self.state.quiz_data: # Если ничего не загрузилось, state.quiz_data останется пустым
             logger.warning("Словарь quiz_data пуст после попытки загрузки.")


    def load_user_data(self) -> None:
        try:
            if self.paths_config.users_file.exists() and self.paths_config.users_file.stat().st_size > 0:
                with open(self.paths_config.users_file, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                # Преобразуем ключи chat_id из str в int, если это необходимо (нет, user_scores ключи строк)
                # и внутренние списки в множества
                self.state.user_scores = self._convert_user_scores_lists_to_sets(loaded_data)
                logger.info(f"Данные пользователей загружены из {self.paths_config.users_file}.")
            else:
                logger.info(f"{self.paths_config.users_file} не найден или пуст. Старт с пустыми данными пользователей.")
                self.state.user_scores = {}
        except json.JSONDecodeError:
            logger.error(f"Ошибка декодирования JSON в {self.paths_config.users_file}. Использование пустых данных.")
            self.state.user_scores = {}
        except Exception as e:
            logger.error(f"Непредвиденная ошибка загрузки данных пользователей: {e}", exc_info=True)
            self.state.user_scores = {}

    def load_chat_settings(self) -> None:
        """Загружает настройки чатов и мигрирует старые подписки, если необходимо."""
        loaded_settings: Dict[int, Dict[str, Any]] = {} # Ключ - int(chat_id)
        migrated_something = False

        # 1. Загрузка существующих настроек чатов
        if self.paths_config.chat_settings_file.exists() and self.paths_config.chat_settings_file.stat().st_size > 0:
            try:
                with open(self.paths_config.chat_settings_file, 'r', encoding='utf-8') as f:
                    raw_settings = json.load(f)
                # Преобразуем строковые ключи chat_id в int
                for chat_id_str, settings_val in raw_settings.items():
                    try:
                        loaded_settings[int(chat_id_str)] = settings_val
                    except ValueError:
                        logger.warning(f"Некорректный chat_id '{chat_id_str}' в {self.paths_config.chat_settings_file}. Пропущен.")
                logger.info(f"Настройки чатов загружены из {self.paths_config.chat_settings_file}.")
            except json.JSONDecodeError:
                logger.error(f"Ошибка декодирования JSON в {self.paths_config.chat_settings_file}. Использование пустых настроек.")
            except Exception as e:
                logger.error(f"Непредвиденная ошибка загрузки настроек чатов: {e}", exc_info=True)
        else:
            logger.info(f"{self.paths_config.chat_settings_file} не найден или пуст. Старт с пустыми настройками чатов.")
        
        self.state.chat_settings = loaded_settings # Записываем загруженные (или пустые) настройки

        # 2. Миграция из OLD_DAILY_QUIZ_SUBSCRIPTIONS_FILE
        # Используем self.app_config.default_chat_settings для шаблона
        default_settings_template = copy.deepcopy(self.app_config.default_chat_settings)

        if self.paths_config.old_daily_quiz_subscriptions_file.exists() and \
           self.paths_config.old_daily_quiz_subscriptions_file.stat().st_size > 0:
            logger.info(f"Обнаружен файл старых подписок {self.paths_config.old_daily_quiz_subscriptions_file}. Попытка миграции...")
            try:
                with open(self.paths_config.old_daily_quiz_subscriptions_file, 'r', encoding='utf-8') as f:
                    old_subs_data = json.load(f)

                if isinstance(old_subs_data, dict): # Формат {chat_id_str: {details}}
                    for chat_id_str, sub_details in old_subs_data.items():
                        try:
                            chat_id_int = int(chat_id_str)
                        except ValueError:
                            logger.warning(f"Миграция: некорректный chat_id '{chat_id_str}' в старых подписках. Пропущен.")
                            continue

                        if chat_id_int not in self.state.chat_settings:
                            self.state.chat_settings[chat_id_int] = copy.deepcopy(default_settings_template)
                        
                        current_chat_s = self.state.chat_settings[chat_id_int]
                        if "daily_quiz" not in current_chat_s or not isinstance(current_chat_s["daily_quiz"], dict):
                            current_chat_s["daily_quiz"] = copy.deepcopy(default_settings_template.get("daily_quiz", {}))

                        current_chat_s["daily_quiz"]["enabled"] = True
                        current_chat_s["daily_quiz"]["hour_msk"] = sub_details.get("hour", self.app_config.daily_quiz_default_hour_msk)
                        current_chat_s["daily_quiz"]["minute_msk"] = sub_details.get("minute", self.app_config.daily_quiz_default_minute_msk)
                        current_chat_s["daily_quiz"]["categories"] = sub_details.get("categories") # Может быть None
                        # num_questions и другие новые поля возьмутся из default_settings_template или глобальных дефолтов AppConfig
                        current_chat_s["daily_quiz"].setdefault("num_questions", default_settings_template.get("daily_quiz",{}).get("num_questions", self.app_config.daily_quiz_questions_count_default))
                        current_chat_s["daily_quiz"].setdefault("interval_seconds", default_settings_template.get("daily_quiz",{}).get("interval_seconds", 60)) # Пример
                        current_chat_s["daily_quiz"].setdefault("poll_open_seconds", default_settings_template.get("daily_quiz",{}).get("poll_open_seconds", 600)) # Пример
                        migrated_something = True
                    logger.info(f"Миграция из {self.paths_config.old_daily_quiz_subscriptions_file} (формат словаря) завершена.")

                elif isinstance(old_subs_data, list): # Совсем старый формат (список ID)
                    for chat_id_val in old_subs_data:
                        chat_id_int = int(chat_id_val) # Предполагаем, что это уже int или str(int)
                        if chat_id_int not in self.state.chat_settings:
                            self.state.chat_settings[chat_id_int] = copy.deepcopy(default_settings_template)

                        current_chat_s = self.state.chat_settings[chat_id_int]
                        if "daily_quiz" not in current_chat_s or not isinstance(current_chat_s["daily_quiz"], dict):
                            current_chat_s["daily_quiz"] = copy.deepcopy(default_settings_template.get("daily_quiz", {}))
                        
                        current_chat_s["daily_quiz"]["enabled"] = True
                        current_chat_s["daily_quiz"]["hour_msk"] = self.app_config.daily_quiz_default_hour_msk
                        current_chat_s["daily_quiz"]["minute_msk"] = self.app_config.daily_quiz_default_minute_msk
                        current_chat_s["daily_quiz"]["categories"] = None # Random
                        current_chat_s["daily_quiz"]["num_questions"] = self.app_config.daily_quiz_questions_count_default
                        current_chat_s["daily_quiz"].setdefault("interval_seconds", default_settings_template.get("daily_quiz",{}).get("interval_seconds", 60))
                        current_chat_s["daily_quiz"].setdefault("poll_open_seconds", default_settings_template.get("daily_quiz",{}).get("poll_open_seconds", 600))
                        migrated_something = True
                    logger.info(f"Миграция из {self.paths_config.old_daily_quiz_subscriptions_file} (формат списка) завершена.")
                
                if migrated_something:
                    try:
                        # Переименовываем старый файл после успешной миграции
                        os.rename(self.paths_config.old_daily_quiz_subscriptions_file, str(self.paths_config.old_daily_quiz_subscriptions_file) + ".migrated")
                        logger.info(f"Старый файл подписок переименован в {str(self.paths_config.old_daily_quiz_subscriptions_file) + '.migrated'}")
                    except OSError as e:
                        logger.error(f"Не удалось переименовать старый файл подписок: {e}")
            
            except Exception as e:
                logger.error(f"Ошибка при миграции данных из {self.paths_config.old_daily_quiz_subscriptions_file}: {e}", exc_info=True)

        if migrated_something:
            self.save_chat_settings() # Сохраняем изменения после миграции


    def get_chat_settings(self, chat_id: int) -> Dict[str, Any]:
        """Возвращает настройки для чата, используя дефолтные значения, если нет специфичных."""
        # Глубокое копирование шаблона по умолчанию, чтобы избежать его изменения
        defaults = copy.deepcopy(self.app_config.default_chat_settings)
        
        if chat_id in self.state.chat_settings:
            chat_specific = self.state.chat_settings[chat_id]
            
            # Слияние: настройки из chat_specific переопределяют defaults
            # Это простое обновление для верхнего уровня. Для вложенных словарей нужно глубже.
            merged_settings = defaults.copy() # Начинаем с копии дефолтов
            
            for key, value in chat_specific.items():
                if key == "daily_quiz" and isinstance(value, dict) and "daily_quiz" in merged_settings and isinstance(merged_settings["daily_quiz"], dict):
                    # Глубокое слияние для daily_quiz
                    default_daily = merged_settings["daily_quiz"].copy()
                    default_daily.update(value)
                    merged_settings["daily_quiz"] = default_daily
                else:
                    # Простое обновление для других ключей или если daily_quiz не словарь в одном из источников
                    merged_settings[key] = value
            return merged_settings
        return defaults

    # --- Сохранение данных ---
    def save_user_data(self) -> None:
        # Преобразуем множества в списки для JSON-сериализации
        data_to_save = self._convert_sets_to_lists_recursively(self.state.user_scores)
        try:
            with open(self.paths_config.users_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
            logger.debug(f"Данные пользователей сохранены в {self.paths_config.users_file}")
        except Exception as e:
            logger.error(f"Ошибка сохранения данных пользователей: {e}", exc_info=True)

    def save_chat_settings(self) -> None:
        # Преобразуем ключи chat_id (int) в строки для JSON
        data_to_save = {str(chat_id): settings for chat_id, settings in self.state.chat_settings.items()}
        try:
            with open(self.paths_config.chat_settings_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
            logger.debug(f"Настройки чатов сохранены в {self.paths_config.chat_settings_file}. Количество: {len(data_to_save)}")
        except Exception as e:
            logger.error(f"Ошибка сохранения настроек чатов: {e}", exc_info=True)

    def save_all_data(self) -> None:
        """Сохраняет все данные, которые управляются этим менеджером."""
        logger.info("Сохранение всех данных...")
        self.save_user_data()
        self.save_chat_settings()
        # Если есть другие данные для сохранения, добавить здесь
        logger.info("Сохранение всех данных завершено.")

    def load_all_data(self) -> None:
        """Загружает все данные."""
        logger.info("Загрузка всех данных...")
        self.load_questions()
        self.load_user_data()
        self.load_chat_settings() # Миграция происходит внутри
        logger.info("Загрузка всех данных завершена.")

    # --- Дополнительные методы для прямого управления данными (если нужно) ---
    def update_chat_setting(self, chat_id: int, key_path: List[str], value: Any) -> None:
        """
        Обновляет конкретную настройку чата по пути ключей.
        Пример: update_chat_setting(123, ["daily_quiz", "enabled"], True)
        """
        if chat_id not in self.state.chat_settings:
            # Если чата нет, создаем его на основе дефолтных настроек
            self.state.chat_settings[chat_id] = copy.deepcopy(self.app_config.default_chat_settings)
        
        current_level = self.state.chat_settings[chat_id]
        for i, key_part in enumerate(key_path):
            if i == len(key_path) - 1: # Последний ключ, устанавливаем значение
                current_level[key_part] = value
            else: # Промежуточный ключ
                if key_part not in current_level or not isinstance(current_level[key_part], dict):
                    current_level[key_part] = {} # Создаем словарь, если его нет
                current_level = current_level[key_part]
        
        self.save_chat_settings() # Сохраняем изменения

    def get_all_questions(self) -> Dict[str, List[Dict[str, Any]]]:
        """Возвращает все загруженные вопросы."""
        return self.state.quiz_data
