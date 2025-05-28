import logging
import random
from typing import List, Dict, Any, Set, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from app_config import AppConfig
    from state import BotState

logger = logging.getLogger(__name__)

class CategoryManager:
    def __init__(self, state: 'BotState', app_config: 'AppConfig'):
        self.state = state
        self.app_config = app_config
        logger.info("CategoryManager инициализирован.")

    @property
    def _questions_by_category_from_state(self) -> Dict[str, List[Dict[str, Any]]]:
        return self.state.quiz_data

    def get_all_category_names(self, with_question_counts: bool = False) -> Union[List[str], List[Dict[str, Any]]]:
        if not self._questions_by_category_from_state:
            return []
        if with_question_counts:
            return [{"name": name, "count": len(qs)} for name, qs in self._questions_by_category_from_state.items() if qs]
        else:
            return [name for name, qs in self._questions_by_category_from_state.items() if qs]

    def get_questions(
        self,
        num_questions_needed: int,
        chat_id: Optional[int] = None,
        allowed_specific_categories: Optional[List[str]] = None,
        mode: str = "random_from_pool"
    ) -> List[Dict[str, Any]]:
        
        source_categories_names: List[str] = []
        
        chat_settings = self.data_manager.get_chat_settings(chat_id) if chat_id else self.app_config.default_chat_settings
        chat_enabled_cats_setting: Optional[List[str]] = chat_settings.get("enabled_categories")
        chat_disabled_cats_setting: Set[str] = set(chat_settings.get("disabled_categories", []))
        
        all_system_category_names = list(self._questions_by_category_from_state.keys())

        if mode == "specific_only" or mode == "random_specific": # 'random_specific' not fully distinct here
            if not allowed_specific_categories:
                logger.warning("get_questions: 'specific' mode без allowed_specific_categories.")
                return []
            source_categories_names = [
                cat for cat in allowed_specific_categories 
                if cat in all_system_category_names and cat not in chat_disabled_cats_setting
            ]
        elif mode == "random_from_pool":
            # Determine num_random_categories if daily quiz "random" mode
            num_random_categories_to_pick: Optional[int] = None
            if chat_id and chat_settings.get("daily_quiz", {}).get("categories_mode") == "random":
                 num_random_categories_to_pick = chat_settings.get("daily_quiz", {}).get("num_random_categories", self.app_config.daily_quiz_defaults["num_random_categories"])

            candidate_pool_for_random: List[str]
            if chat_enabled_cats_setting is not None:
                candidate_pool_for_random = [
                    cat for cat in chat_enabled_cats_setting 
                    if cat in all_system_category_names and cat not in chat_disabled_cats_setting and self._questions_by_category_from_state.get(cat)
                ]
            else: # All system categories are candidates
                candidate_pool_for_random = [
                    cat for cat in all_system_category_names 
                    if cat not in chat_disabled_cats_setting and self._questions_by_category_from_state.get(cat)
                ]
            
            if not candidate_pool_for_random:
                 logger.warning(f"get_questions (random_from_pool): Нет доступных категорий для чата {chat_id}.")
                 return []

            if num_random_categories_to_pick is not None and num_random_categories_to_pick > 0:
                actual_num_to_sample = min(num_random_categories_to_pick, len(candidate_pool_for_random))
                source_categories_names = random.sample(candidate_pool_for_random, actual_num_to_sample)
            else: # Use all from candidate_pool_for_random
                source_categories_names = candidate_pool_for_random
        else:
            logger.error(f"get_questions: Неизвестный режим '{mode}'.")
            return []

        if not source_categories_names:
            logger.warning(f"get_questions: Нет исходных категорий для режима '{mode}', чат {chat_id}.")
            return []

        temp_question_pool: List[Dict[str, Any]] = []
        for cat_name in source_categories_names:
            questions_in_cat = self._questions_by_category_from_state.get(cat_name, [])
            for q_data in questions_in_cat:
                q_copy = q_data.copy()
                q_copy['current_category_name_for_quiz'] = cat_name # Используется QuizManager для отображения
                temp_question_pool.append(q_copy)

        if not temp_question_pool:
            logger.warning(f"get_questions: Пул вопросов пуст для категорий: {source_categories_names}.")
            return []

        random.shuffle(temp_question_pool)
        final_questions = temp_question_pool[:num_questions_needed]

        logger.debug(f"Выбрано {len(final_questions)} вопросов. Режим: {mode}. Исходные кат: {source_categories_names}. Запрещ. в чате: {chat_disabled_cats_setting}")
        return final_questions

    @property
    def data_manager(self): # Позволяет CategoryManager получать доступ к DataManager через self.state
        # Предполагается, что DataManager доступен через bot_data -> state,
        # но это не очень хороший паттерн. Лучше передавать DataManager в конструктор, если он нужен напрямую.
        # Однако, для get_chat_settings, он уже вызывается из self.state.chat_settings,
        # которые загружает DataManager. Если нужен сам DataManager:
        # return self.state.app_config.data_manager # Если бы такая ссылка была
        # В данном случае, мы можем получить chat_settings напрямую из self.state.chat_settings (загруженные)
        # или вызывать self.state.data_manager.get_chat_settings(chat_id) если бы state имел ссылку на data_manager
        # Поскольку data_manager не хранится в state, а chat_settings в state уже загружены,
        # для get_questions, мы можем использовать self.state.chat_settings.get(chat_id)
        # или self.state.get_chat_settings(chat_id) который использует app_config для дефолтов
        # Но DataManager.get_chat_settings(chat_id) сам по себе уже сливает с дефолтами.
        # Для простоты и чтобы избежать циклических зависимостей, если CategoryManager нужен в DataManager,
        # лучше, чтобы CategoryManager не зависел от DataManager напрямую, а получал настройки через state или параметры.
        # В текущей реализации get_questions, chat_settings берутся из self.state или self.app_config.default_chat_settings
        # что нормально, так как DataManager их туда загружает/обновляет.
        # Этот property data_manager нужен только если мы хотим вызвать DataManager.get_chat_settings()
        # из CategoryManager, что сейчас не делается.
        raise NotImplementedError("DataManager не должен быть прямым свойством CategoryManager через state. Получайте настройки из state или app_config.")


    def get_random_category_names_for_daily(self, num_categories_to_pick: int, chat_id: int) -> List[str]:
        """Выбирает случайные категории для ежедневной викторины, учитывая настройки чата."""
        # Используем DataManager для получения актуальных, смерженных настроек
        chat_s = self.data_manager.get_chat_settings(chat_id)
        
        chat_enabled_cats: Optional[List[str]] = chat_s.get("enabled_categories")
        chat_disabled_cats: Set[str] = set(chat_s.get("disabled_categories", []))
        
        candidate_pool: List[str]
        if chat_enabled_cats is not None: # Если в чате задан список разрешенных
            candidate_pool = [
                cat for cat in chat_enabled_cats
                if cat in self._questions_by_category_from_state and self._questions_by_category_from_state[cat] and cat not in chat_disabled_cats
            ]
        else: # Иначе, все системные категории минус запрещенные в чате
            candidate_pool = [
                name for name, questions in self._questions_by_category_from_state.items()
                if questions and name not in chat_disabled_cats
            ]

        if not candidate_pool:
            return []
        
        actual_num_to_sample = min(num_categories_to_pick, len(candidate_pool))
        return random.sample(candidate_pool, actual_num_to_sample)

    def is_valid_category(self, category_name: str) -> bool:
        return category_name in self._questions_by_category_from_state and bool(self._questions_by_category_from_state[category_name])
