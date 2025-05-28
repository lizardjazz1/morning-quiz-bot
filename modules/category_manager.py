# bot/modules/category_manager.py
import random
import logging
from typing import List, Dict, Any, Optional, Set

# from ..app_config import AppConfig # Не нужен прямой импорт, если получаем через конструктор
# from ..state import BotState # Не нужен прямой импорт

logger = logging.getLogger(__name__)

class CategoryManager:
    def __init__(self, questions_by_category: Dict[str, List[Dict[str, Any]]], app_config: 'AppConfig'):
        # questions_by_category передается из BotState при инициализации CategoryManager
        self.all_questions_data: Dict[str, List[Dict[str, Any]]] = questions_by_category
        self.app_config = app_config
        self.all_category_names_cache: Optional[List[str]] = None # Кэш для имен категорий

    def get_all_category_names(self, with_question_counts: bool = False) -> Union[List[str], List[Dict[str, Any]]]:
        """
        Возвращает список всех доступных названий категорий.
        Если with_question_counts is True, возвращает список словарей {'name': str, 'count': int}.
        """
        if not self.all_questions_data:
            return []

        if not with_question_counts and self.all_category_names_cache is not None:
             return sorted(list(self.all_category_names_cache)) # Возвращаем отсортированную копию

        categories_info = []
        temp_names_cache = []
        for cat_name, questions in self.all_questions_data.items():
            if isinstance(questions, list) and questions: # Учитываем только категории с вопросами
                temp_names_cache.append(cat_name)
                if with_question_counts:
                    categories_info.append({"name": cat_name, "count": len(questions)})
        
        if not self.all_category_names_cache: # Обновляем кэш при первом вызове или если он пуст
            self.all_category_names_cache = temp_names_cache

        if with_question_counts:
            return sorted(categories_info, key=lambda x: x['name'])
        else:
            return sorted(temp_names_cache)


    def get_questions(
        self,
        num_questions_needed: int,
        allowed_specific_categories: Optional[List[str]] = None,
        chat_enabled_categories: Optional[List[str]] = None, # Категории, разрешенные для чата (из chat_settings)
        chat_disabled_categories: Optional[List[str]] = None, # Категории, запрещенные для чата
        mode: str = "random_from_pool" # "random_from_pool", "specific_only", "all_from_pool"
    ) -> List[Dict[str, Any]]:
        """
        Подбирает вопросы согласно указанным параметрам.

        Args:
            num_questions_needed: Сколько вопросов нужно.
            allowed_specific_categories: Список категорий, явно запрошенных для этой викторины.
                                         Если указаны, то `mode` часто будет "specific_only" или
                                         эти категории будут приоритетными в "random_from_pool".
            chat_enabled_categories: Категории, глобально разрешенные для данного чата (из настроек чата).
                                     Если None, все категории считаются разрешенными на уровне чата.
            chat_disabled_categories: Категории, глобально запрещенные для данного чата.
            mode:
                "random_from_pool": Случайные вопросы из итогового пула доступных категорий.
                "specific_only": Только из `allowed_specific_categories` (если они есть и доступны).
                "all_from_pool": Все вопросы из итогового пула (с учетом лимита num_questions_needed).

        Returns:
            Список словарей вопросов.
        """
        if not self.all_questions_data or num_questions_needed <= 0:
            return []

        candidate_pool: Dict[str, List[Dict[str, Any]]] = {}

        # 1. Определяем базовый пул категорий (все или только разрешенные чатом)
        if chat_enabled_categories is not None: # Если есть список разрешенных для чата
            for cat_name in chat_enabled_categories:
                if cat_name in self.all_questions_data:
                    candidate_pool[cat_name] = self.all_questions_data[cat_name]
        else: # Все категории разрешены на уровне чата
            candidate_pool = {k: v for k, v in self.all_questions_data.items() if v}


        # 2. Применяем явно запрещенные чатом категории
        if chat_disabled_categories:
            disabled_set = set(chat_disabled_categories)
            candidate_pool = {
                cat_name: q_list for cat_name, q_list in candidate_pool.items()
                if cat_name not in disabled_set
            }

        # 3. Если запрошены специфичные категории для этой викторины
        if allowed_specific_categories:
            if mode == "specific_only":
                # Оставляем в candidate_pool только те, что есть в allowed_specific_categories
                specific_pool = {}
                for cat_name in allowed_specific_categories:
                    if cat_name in candidate_pool: # Проверяем, что категория не была отфильтрована ранее
                        specific_pool[cat_name] = candidate_pool[cat_name]
                candidate_pool = specific_pool
            # Если mode="random_from_pool", но есть allowed_specific_categories,
            # то эти категории будут предпочтительны, но это сложнее реализовать тут.
            # Пока что, если есть allowed_specific_categories, будем считать, что нужны только они,
            # если не сказано иное. Для "random_from_pool" с allowed_specific_categories,
            # можно просто отфильтровать candidate_pool по allowed_specific_categories.
            elif mode == "random_from_pool": # Отбираем из указанных категорий, но случайным образом
                filtered_pool = {}
                for cat_name in allowed_specific_categories:
                    if cat_name in candidate_pool:
                         filtered_pool[cat_name] = candidate_pool[cat_name]
                candidate_pool = filtered_pool


        if not candidate_pool:
            logger.warning(
                f"Пул категорий пуст после применения фильтров. "
                f"AllowedSpecific: {allowed_specific_categories}, ChatEnabled: {chat_enabled_categories}, "
                f"ChatDisabled: {chat_disabled_categories}, Mode: {mode}"
            )
            return []

        # 4. Собираем все вопросы из отобранных категорий
        all_selected_questions: List[Dict[str, Any]] = []
        for cat_name, questions_in_category in candidate_pool.items():
            for q in questions_in_category:
                # Добавляем копию, чтобы избежать модификации оригинала в BotState
                # и добавляем/обновляем 'current_category' для этого экземпляра вопроса
                q_copy = q.copy()
                q_copy['current_category_name'] = cat_name # Категория, из которой вопрос взят для этой сессии
                all_selected_questions.append(q_copy)


        if not all_selected_questions:
            logger.warning("Список вопросов пуст после сбора из категорий.")
            return []

        # 5. Перемешиваем и выбираем нужное количество
        random.shuffle(all_selected_questions)
        
        return all_selected_questions[:min(num_questions_needed, len(all_selected_questions))]

    def get_category_details(self, category_name: str) -> Optional[List[Dict[str, Any]]]:
        """Возвращает список вопросов для конкретной категории или None, если категория не найдена."""
        return self.all_questions_data.get(category_name)

