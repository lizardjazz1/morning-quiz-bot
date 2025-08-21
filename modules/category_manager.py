#modules/category_manager.py
import logging
import random
import time
from typing import List, Dict, Any, Set, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from app_config import AppConfig
    from state import BotState
    from data_manager import DataManager

logger = logging.getLogger(__name__)

class CategoryManager:
    def __init__(self, state: 'BotState', app_config: 'AppConfig', data_manager: 'DataManager'):
        self.state = state
        self.app_config = app_config
        self.data_manager = data_manager
        # Инициализируем статистику использования категорий
        self._category_usage_stats: Dict[str, Dict[str, Any]] = {}
        self._load_category_usage_stats()
        logger.info("CategoryManager инициализирован.")

    @property
    def _questions_by_category_from_state(self) -> Dict[str, List[Dict[str, Any]]]:
        if not hasattr(self.state, 'quiz_data') or not isinstance(self.state.quiz_data, dict):
            logger.warning("state.quiz_data отсутствует или имеет неверный тип в CategoryManager. Возвращен пустой словарь.")
            return {}
        return self.state.quiz_data

    def _load_category_usage_stats(self) -> None:
        """Загружает статистику использования категорий из data_manager"""
        try:
            self._category_usage_stats = self.data_manager.get_global_setting("category_usage_stats", {})
            logger.debug(f"Загружена статистика использования категорий: {len(self._category_usage_stats)} записей")
        except Exception as e:
            logger.warning(f"Не удалось загрузить статистику использования категорий: {e}")
            self._category_usage_stats = {}
            # Fallback: используем простой random.sample если что-то пошло не так
            logger.info("Используется fallback режим: простой random.sample")

    def _save_category_usage_stats(self) -> None:
        """Сохраняет статистику использования категорий в data_manager"""
        try:
            self.data_manager.update_global_setting("category_usage_stats", self._category_usage_stats)
            logger.debug("Статистика использования категорий сохранена")
        except Exception as e:
            logger.warning(f"Не удалось сохранить статистику использования категорий: {e}")

    def _update_category_usage(self, category_name: str, chat_id: Optional[int] = None) -> None:
        """Обновляет статистику использования категории"""
        current_time = time.time()
        
        if category_name not in self._category_usage_stats:
            self._category_usage_stats[category_name] = {
                "total_usage": 0,
                "last_used": current_time,
                "chat_usage": {}
            }
        
        # Обновляем общую статистику
        self._category_usage_stats[category_name]["total_usage"] += 1
        self._category_usage_stats[category_name]["last_used"] = current_time
        
        # Обновляем статистику по чатам
        if chat_id is not None:
            chat_id_str = str(chat_id)
            if chat_id_str not in self._category_usage_stats[category_name]["chat_usage"]:
                self._category_usage_stats[category_name]["chat_usage"][chat_id_str] = 0
            self._category_usage_stats[category_name]["chat_usage"][chat_id_str] += 1
        
        # Сохраняем статистику каждые 10 использований
        if self._category_usage_stats[category_name]["total_usage"] % 10 == 0:
            self._save_category_usage_stats()

    def _get_weighted_random_categories(self, candidate_pool: List[str], num_to_pick: int, chat_id: Optional[int] = None) -> List[str]:
        """Выбирает категории с учетом весов на основе частоты использования"""
        if not candidate_pool:
            return []
        
        if len(candidate_pool) <= num_to_pick:
            return candidate_pool.copy()
        
        try:
            # Вычисляем веса для каждой категории
            category_weights = []
            current_time = time.time()
            
            for category in candidate_pool:
                if category in self._category_usage_stats:
                    stats = self._category_usage_stats[category]
                    # Базовый вес = 1 / (1 + количество использований)
                    base_weight = 1.0 / (1.0 + stats["total_usage"])
                    
                    # Бонус за давность использования (категории, которые давно не использовались, получают приоритет)
                    time_since_last_use = current_time - stats["last_used"]
                    time_bonus = min(time_since_last_use / 86400.0, 7.0)  # Максимум 7 дней
                    
                    # Финальный вес
                    final_weight = base_weight * (1.0 + time_bonus)
                    category_weights.append((category, final_weight))
                else:
                    # Новые категории получают максимальный приоритет
                    category_weights.append((category, 10.0))
            
            # Сортируем по весам (по убыванию)
            category_weights.sort(key=lambda x: x[1], reverse=True)
            
            # Выбираем top категории, но добавляем элемент случайности
            top_categories = category_weights[:min(num_to_pick * 2, len(category_weights))]
            
            # Перемешиваем top категории для добавления случайности
            random.shuffle(top_categories)
            
            # Возвращаем нужное количество
            selected_categories = [cat for cat, _ in top_categories[:num_to_pick]]
            
            logger.debug(f"Выбрано {len(selected_categories)} категорий с весами: {[(cat, weight) for cat, weight in category_weights[:num_to_pick]]}")
            return selected_categories
            
        except Exception as e:
            # Fallback: если что-то пошло не так, используем простой random.sample
            logger.warning(f"Ошибка в системе весов категорий, используется fallback: {e}")
            return random.sample(candidate_pool, num_to_pick)

    def get_all_category_names(self, with_question_counts: bool = False) -> Union[List[str], List[Dict[str, Any]]]:
        quiz_data = self._questions_by_category_from_state
        if not quiz_data:
            return []

        if with_question_counts:
            return [{"name": name, "count": len(qs)} for name, qs in quiz_data.items() if qs]
        else:
            return [name for name, qs in quiz_data.items() if qs]

    def get_questions(
        self,
        num_questions_needed: int,
        chat_id: Optional[int] = None,
        allowed_specific_categories: Optional[List[str]] = None,
        mode: str = "random_from_pool"
    ) -> List[Dict[str, Any]]:

        if chat_id is not None:
            chat_settings = self.data_manager.get_chat_settings(chat_id)
        else:
            chat_settings = self.app_config.default_chat_settings

        chat_enabled_cats_setting: Optional[List[str]] = chat_settings.get("enabled_categories")
        chat_disabled_cats_setting: Set[str] = set(chat_settings.get("disabled_categories", []))

        all_system_category_names_with_questions = [
            name for name, questions in self._questions_by_category_from_state.items() if questions
        ]

        source_categories_names: List[str] = []

        if mode == "specific_only":
            if not allowed_specific_categories:
                logger.warning("get_questions: режим 'specific_only' вызван без 'allowed_specific_categories'.")
                return []
            source_categories_names = [
                cat_name for cat_name in allowed_specific_categories
                if cat_name in all_system_category_names_with_questions and cat_name not in chat_disabled_cats_setting
            ]
        elif mode == "random_from_pool":
            candidate_pool_for_random: List[str]
            if chat_enabled_cats_setting is not None:
                candidate_pool_for_random = [
                    cat_name for cat_name in chat_enabled_cats_setting
                    if cat_name in all_system_category_names_with_questions and cat_name not in chat_disabled_cats_setting
                ]
            else:
                candidate_pool_for_random = [
                    cat_name for cat_name in all_system_category_names_with_questions
                    if cat_name not in chat_disabled_cats_setting
                ]

            if not candidate_pool_for_random:
                logger.warning(f"get_questions (random_from_pool): Нет доступных категорий-кандидатов для чата {chat_id} (или глобально).")
                return []

            num_random_categories_to_pick: Optional[int] = None
            daily_quiz_settings = chat_settings.get("daily_quiz", {})
            if chat_id is not None and daily_quiz_settings.get("enabled") and daily_quiz_settings.get("categories_mode") == "random":
                num_random_categories_to_pick = daily_quiz_settings.get(
                    "num_random_categories", self.app_config.daily_quiz_defaults.get("num_random_categories", 3)
                )
                logger.debug(f"Ежедневная викторина: ограничение на {num_random_categories_to_pick} категорий")
            else:
                # Это обычная викторина - НЕ ограничиваем количество категорий
                logger.debug(f"Обычная викторина: используем все доступные категории")

            if num_random_categories_to_pick is not None and num_random_categories_to_pick > 0:
                actual_num_to_sample_from_pool = min(num_random_categories_to_pick, len(candidate_pool_for_random))
                if actual_num_to_sample_from_pool > 0:
                    # Используем систему с весами для более справедливого выбора
                    source_categories_names = self._get_weighted_random_categories(
                        candidate_pool_for_random, actual_num_to_sample_from_pool, chat_id
                    )
                else:
                    source_categories_names = []
            else:
                # Для обычных викторин используем все категории, но с весами
                source_categories_names = self._get_weighted_random_categories(
                    candidate_pool_for_random, len(candidate_pool_for_random), chat_id
                )
        else:
            logger.error(f"get_questions: Неизвестный режим '{mode}'.")
            return []

        if not source_categories_names:
            logger.warning(f"get_questions: Нет доступных категорий для подбора вопросов. Режим: '{mode}', Чат ID: {chat_id}, Разрешенные в запросе: {allowed_specific_categories}, Запрещенные в чате: {chat_disabled_cats_setting}.")
            return []

        logger.info(f"get_questions: Выбрано {len(source_categories_names)} категорий для викторины: {source_categories_names}")

        temp_question_pool: List[Dict[str, Any]] = []
        for cat_name_for_pool in source_categories_names:
            questions_in_this_cat = self._questions_by_category_from_state.get(cat_name_for_pool, [])
            for q_data_from_cat in questions_in_this_cat:
                q_copy = q_data_from_cat.copy()
                q_copy['current_category_name_for_quiz'] = cat_name_for_pool
                temp_question_pool.append(q_copy)
            
            # Обновляем статистику использования категории
            try:
                self._update_category_usage(cat_name_for_pool, chat_id)
            except Exception as e:
                logger.warning(f"Не удалось обновить статистику для категории {cat_name_for_pool}: {e}")
                # Продолжаем работу без обновления статистики

        if not temp_question_pool:
            logger.warning(f"get_questions: Пул вопросов пуст после обработки категорий: {source_categories_names}.")
            return []

        random.shuffle(temp_question_pool)
        final_questions = temp_question_pool[:num_questions_needed]

        logger.debug(f"Для викторины (режим: {mode}, чат: {chat_id}) отобрано {len(final_questions)} вопросов из категорий: {source_categories_names}.")
        return final_questions

    def is_valid_category(self, category_name: str) -> bool:
        quiz_data = self._questions_by_category_from_state
        return category_name in quiz_data and bool(quiz_data[category_name])

    def get_category_usage_stats(self, category_name: Optional[str] = None, read_only: bool = True) -> Dict[str, Any]:
        """Возвращает статистику использования категорий
        
        Args:
            category_name: Если указан, возвращает статистику только для этой категории
            read_only: Если True, статистика не будет обновляться при чтении
        """
        if category_name:
            return self._category_usage_stats.get(category_name, {})
        return self._category_usage_stats

    def reset_category_usage_stats(self, category_name: Optional[str] = None) -> None:
        """Сбрасывает статистику использования категорий"""
        if category_name:
            if category_name in self._category_usage_stats:
                del self._category_usage_stats[category_name]
                logger.info(f"Статистика использования категории '{category_name}' сброшена")
        else:
            self._category_usage_stats.clear()
            logger.info("Вся статистика использования категорий сброшена")
        self._save_category_usage_stats()

