#modules/category_manager.py
import logging
import random
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
        logger.info("CategoryManager инициализирован.")

    @property
    def _questions_by_category_from_state(self) -> Dict[str, List[Dict[str, Any]]]:
        if not hasattr(self.state, 'quiz_data') or not isinstance(self.state.quiz_data, dict):
            logger.warning("state.quiz_data отсутствует или имеет неверный тип в CategoryManager. Возвращен пустой словарь.")
            return {}
        return self.state.quiz_data

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

            if num_random_categories_to_pick is not None and num_random_categories_to_pick > 0:
                actual_num_to_sample_from_pool = min(num_random_categories_to_pick, len(candidate_pool_for_random))
                if actual_num_to_sample_from_pool > 0 :
                    source_categories_names = random.sample(candidate_pool_for_random, actual_num_to_sample_from_pool)
                else:
                      source_categories_names = []
            else:
                source_categories_names = candidate_pool_for_random
        else:
            logger.error(f"get_questions: Неизвестный режим '{mode}'.")
            return []

        if not source_categories_names:
            logger.warning(f"get_questions: Нет доступных категорий для подбора вопросов. Режим: '{mode}', Чат ID: {chat_id}, Разрешенные в запросе: {allowed_specific_categories}, Запрещенные в чате: {chat_disabled_cats_setting}.")
            return []

        temp_question_pool: List[Dict[str, Any]] = []
        for cat_name_for_pool in source_categories_names:
            questions_in_this_cat = self._questions_by_category_from_state.get(cat_name_for_pool, [])
            for q_data_from_cat in questions_in_this_cat:
                q_copy = q_data_from_cat.copy()
                q_copy['current_category_name_for_quiz'] = cat_name_for_pool
                temp_question_pool.append(q_copy)

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

