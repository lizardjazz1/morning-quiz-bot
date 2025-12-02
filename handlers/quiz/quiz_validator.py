"""
Валидация данных для викторин Morning Quiz Bot
Содержит все проверки и валидацию данных викторин
"""

from __future__ import annotations
import logging
import re
from typing import Dict, List, Optional, Any, Union, Set
from datetime import datetime, timedelta

from .quiz_types import (
    QuizConfig, QuizSession, QuizQuestion, QuizAnswer,
    QuizMode, QuizState, QuizResult
)

logger = logging.getLogger(__name__)


class QuizValidator:
    """Валидатор данных викторин"""

    # Максимальные значения
    MAX_QUESTIONS_PER_SESSION = 50
    MAX_INTERVAL_SECONDS = 3600  # 1 час
    MAX_OPEN_PERIOD_SECONDS = 86400  # 24 часа
    MAX_QUESTION_TEXT_LENGTH = 4096
    MAX_OPTION_TEXT_LENGTH = 100
    MAX_OPTIONS_COUNT = 10
    MIN_OPTIONS_COUNT = 2
    MAX_CATEGORIES_COUNT = 20

    # Паттерны для валидации
    QUESTION_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,100}$')
    SAFE_TEXT_PATTERN = re.compile(r'^[a-zA-Zа-яА-Я0-9\s\.,!?\-\(\)\[\]{}:;"\'«»\n]*$')

    @classmethod
    def validate_quiz_config(cls, config: QuizConfig) -> List[str]:
        """Валидировать конфигурацию викторины"""
        errors = []

        # Валидация количества вопросов
        if not isinstance(config.num_questions, int) or config.num_questions < 1:
            errors.append("Количество вопросов должно быть положительным целым числом")
        elif config.num_questions > cls.MAX_QUESTIONS_PER_SESSION:
            errors.append(f"Максимальное количество вопросов: {cls.MAX_QUESTIONS_PER_SESSION}")

        # Валидация категорий
        if not config.categories or not isinstance(config.categories, list):
            errors.append("Должен быть указан список категорий")
        elif len(config.categories) > cls.MAX_CATEGORIES_COUNT:
            errors.append(f"Максимальное количество категорий: {cls.MAX_CATEGORIES_COUNT}")
        elif len(config.categories) == 0:
            errors.append("Должен быть указан хотя бы одна категория")
        else:
            for cat in config.categories:
                if not isinstance(cat, str) or not cat.strip():
                    errors.append("Названия категорий должны быть непустыми строками")

        # Валидация интервала
        if config.interval_seconds is not None:
            if not isinstance(config.interval_seconds, int) or config.interval_seconds < 1:
                errors.append("Интервал должен быть положительным целым числом")
            elif config.interval_seconds > cls.MAX_INTERVAL_SECONDS:
                errors.append(f"Максимальный интервал: {cls.MAX_INTERVAL_SECONDS} секунд")

        # Валидация периода открытия
        if config.open_period_seconds is not None:
            if not isinstance(config.open_period_seconds, int) or config.open_period_seconds < 1:
                errors.append("Период открытия должен быть положительным целым числом")
            elif config.open_period_seconds > cls.MAX_OPEN_PERIOD_SECONDS:
                errors.append(f"Максимальный период открытия: {cls.MAX_OPEN_PERIOD_SECONDS} секунд")

        return errors

    @classmethod
    def validate_question(cls, question: QuizQuestion) -> List[str]:
        """Валидировать вопрос викторины"""
        errors = []

        # Валидация ID вопроса
        if not question.question_id or not isinstance(question.question_id, str):
            errors.append("ID вопроса обязателен")
        elif not cls.QUESTION_ID_PATTERN.match(question.question_id):
            errors.append("ID вопроса содержит недопустимые символы")

        # Валидация текста вопроса
        if not question.text or not isinstance(question.text, str):
            errors.append("Текст вопроса обязателен")
        elif len(question.text.strip()) == 0:
            errors.append("Текст вопроса не может быть пустым")
        elif len(question.text) > cls.MAX_QUESTION_TEXT_LENGTH:
            errors.append(f"Текст вопроса слишком длинный (макс. {cls.MAX_QUESTION_TEXT_LENGTH} символов)")

        # Валидация вариантов ответа
        if not question.options or not isinstance(question.options, list):
            errors.append("Варианты ответа обязательны")
        elif len(question.options) < cls.MIN_OPTIONS_COUNT:
            errors.append(f"Минимум {cls.MIN_OPTIONS_COUNT} варианта ответа")
        elif len(question.options) > cls.MAX_OPTIONS_COUNT:
            errors.append(f"Максимум {cls.MAX_OPTIONS_COUNT} вариантов ответа")
        else:
            for i, option in enumerate(question.options):
                if not isinstance(option, str):
                    errors.append(f"Вариант {i+1} должен быть строкой")
                elif len(option.strip()) == 0:
                    errors.append(f"Вариант {i+1} не может быть пустым")
                elif len(option) > cls.MAX_OPTION_TEXT_LENGTH:
                    errors.append(f"Вариант {i+1} слишком длинный (макс. {cls.MAX_OPTION_TEXT_LENGTH} символов)")

        # Валидация правильного ответа
        if not isinstance(question.correct_option, int):
            errors.append("Индекс правильного ответа должен быть целым числом")
        elif question.correct_option < 0:
            errors.append("Индекс правильного ответа не может быть отрицательным")
        elif question.options and question.correct_option >= len(question.options):
            errors.append("Индекс правильного ответа выходит за пределы вариантов")

        # Валидация категории
        if not question.category or not isinstance(question.category, str):
            errors.append("Категория вопроса обязательна")
        elif not question.category.strip():
            errors.append("Категория вопроса не может быть пустой")

        # Валидация объяснения (опционально)
        if question.explanation is not None:
            if not isinstance(question.explanation, str):
                errors.append("Объяснение должно быть строкой")
            elif len(question.explanation) > cls.MAX_QUESTION_TEXT_LENGTH:
                errors.append(f"Объяснение слишком длинное (макс. {cls.MAX_QUESTION_TEXT_LENGTH} символов)")

        return errors

    @classmethod
    def validate_answer(cls, answer: QuizAnswer, question: Optional[QuizQuestion] = None) -> List[str]:
        """Валидировать ответ пользователя"""
        errors = []

        # Валидация ID пользователя
        if not isinstance(answer.user_id, int) or answer.user_id <= 0:
            errors.append("Неверный ID пользователя")

        # Валидация ID вопроса
        if not answer.question_id or not isinstance(answer.question_id, str):
            errors.append("Неверный ID вопроса")

        # Валидация выбранного варианта
        if not isinstance(answer.selected_option, int):
            errors.append("Выбранный вариант должен быть целым числом")
        elif answer.selected_option < 0:
            errors.append("Индекс выбранного варианта не может быть отрицательным")

        # Проверка соответствия вопросу
        if question is not None and answer.selected_option >= len(question.options):
            errors.append("Выбранный вариант выходит за пределы доступных вариантов")

        # Валидация времени ответа
        if answer.response_time is not None:
            if not isinstance(answer.response_time, (int, float)) or answer.response_time < 0:
                errors.append("Время ответа должно быть положительным числом")

        return errors

    @classmethod
    def validate_session(cls, session: QuizSession) -> List[str]:
        """Валидировать сессию викторины"""
        errors = []

        # Валидация базовых полей
        if not session.session_id or not isinstance(session.session_id, str):
            errors.append("ID сессии обязателен")

        if not isinstance(session.chat_id, int):
            errors.append("ID чата должен быть целым числом")

        # Валидация конфигурации
        if not session.config:
            errors.append("Конфигурация викторины обязательна")
        else:
            config_errors = cls.validate_quiz_config(session.config)
            errors.extend(config_errors)

        # Валидация вопросов
        if not session.questions:
            errors.append("Список вопросов не может быть пустым")
        else:
            for i, question in enumerate(session.questions):
                question_errors = cls.validate_question(question)
                if question_errors:
                    errors.extend([f"Вопрос {i+1}: {err}" for err in question_errors])

        # Валидация индекса текущего вопроса
        if session.current_question_index < 0:
            errors.append("Индекс текущего вопроса не может быть отрицательным")
        elif session.questions and session.current_question_index >= len(session.questions):
            errors.append("Индекс текущего вопроса выходит за пределы списка вопросов")

        # Валидация временных меток
        if session.started_at and session.created_at and session.started_at < session.created_at:
            errors.append("Время начала не может быть раньше времени создания")

        if session.completed_at and session.started_at and session.completed_at < session.started_at:
            errors.append("Время завершения не может быть раньше времени начала")

        return errors

    @classmethod
    def validate_user_input(cls, text: str, max_length: int = 4096) -> List[str]:
        """Валидировать пользовательский ввод"""
        errors = []

        if not isinstance(text, str):
            errors.append("Ввод должен быть строкой")
            return errors

        if len(text.strip()) == 0:
            errors.append("Ввод не может быть пустым")
            return errors

        if len(text) > max_length:
            errors.append(f"Ввод слишком длинный (макс. {max_length} символов)")

        # Проверка на безопасный текст (без HTML и потенциально опасных символов)
        if not cls.SAFE_TEXT_PATTERN.match(text):
            errors.append("Ввод содержит недопустимые символы")

        return errors

    @classmethod
    def validate_callback_data(cls, callback_data: str) -> List[str]:
        """Валидировать данные callback-запроса"""
        errors = []

        if not callback_data or not isinstance(callback_data, str):
            errors.append("Callback-данные обязательны")
            return errors

        if len(callback_data) > 64:  # Telegram ограничивает callback-данные
            errors.append("Callback-данные слишком длинные")

        # Проверка на допустимые символы
        if not re.match(r'^[a-zA-Z0-9_-]+$', callback_data.replace('_', '').replace('-', '')):
            errors.append("Callback-данные содержат недопустимые символы")

        return errors

    @classmethod
    def validate_categories_list(cls, categories: List[str], available_categories: Set[str]) -> List[str]:
        """Валидировать список категорий"""
        errors = []

        if not categories:
            errors.append("Список категорий не может быть пустым")
            return errors

        if len(categories) > cls.MAX_CATEGORIES_COUNT:
            errors.append(f"Слишком много категорий (макс. {cls.MAX_CATEGORIES_COUNT})")

        invalid_categories = set(categories) - available_categories
        if invalid_categories:
            errors.append(f"Недопустимые категории: {', '.join(invalid_categories)}")

        return errors

    @classmethod
    def sanitize_text(cls, text: str) -> str:
        """Очистить текст от потенциально опасных символов"""
        if not isinstance(text, str):
            return ""

        # Удаляем HTML-теги
        text = re.sub(r'<[^>]+>', '', text)

        # Удаляем потенциально опасные символы
        text = re.sub(r'[<>"&]', '', text)

        # Удаляем лишние пробелы
        text = ' '.join(text.split())

        return text.strip()

    @classmethod
    def is_valid_quiz_mode(cls, mode: str) -> bool:
        """Проверить валидность режима викторины"""
        try:
            QuizMode(mode)
            return True
        except ValueError:
            return False

    @classmethod
    def can_user_answer(cls, session: QuizSession, user_id: int, question_id: str) -> tuple[bool, str]:
        """Проверить, может ли пользователь ответить на вопрос"""
        # Проверяем, активна ли викторина
        if not session.is_active:
            return False, "Викторина не активна"

        # Проверяем, существует ли вопрос
        if question_id not in [q.question_id for q in session.questions]:
            return False, "Вопрос не найден"

        # Проверяем, отвечал ли уже пользователь на этот вопрос
        if question_id in session.answers:
            user_answers = [a for a in session.answers[question_id] if a.user_id == user_id]
            if user_answers:
                return False, "Вы уже отвечали на этот вопрос"

        return True, ""

    @classmethod
    def validate_quiz_duration(cls, session: QuizSession) -> List[str]:
        """Валидировать длительность викторины"""
        errors = []

        if not session.started_at:
            return errors

        duration = datetime.now() - session.started_at
        max_duration = timedelta(hours=2)  # Максимум 2 часа на викторину

        if duration > max_duration:
            errors.append("Викторина длится слишком долго и будет автоматически завершена")

        return errors

    @classmethod
    def check_quiz_limits(cls, chat_id: int, user_id: int, config: Any) -> List[str]:
        """Проверить лимиты викторин для чата и пользователя"""
        errors = []

        # Здесь можно добавить проверки на лимиты:
        # - Максимальное количество викторин в день для чата
        # - Максимальное количество викторин для пользователя
        # - Проверка на спам

        # Пока возвращаем пустой список - логика будет добавлена позже
        return errors
