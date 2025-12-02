"""
Типы данных для викторин Morning Quiz Bot
Содержит все структуры данных, используемые в системе викторин
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any, Union, Literal
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class QuizMode(Enum):
    """Режимы викторин"""
    SINGLE = "single"
    SESSION = "session"
    TIMED = "timed"
    DAILY = "daily"


class QuizState(Enum):
    """Состояния викторины"""
    CREATED = "created"
    STARTED = "started"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class QuizConfig:
    """Конфигурация викторины"""
    mode: QuizMode
    num_questions: int
    categories: List[str]
    interval_seconds: Optional[int] = None
    open_period_seconds: Optional[int] = None
    announce_quiz: bool = True
    category_pool_mode: bool = False
    chat_id: Optional[int] = None

    def __post_init__(self):
        """Валидация после создания"""
        if self.num_questions < 1:
            raise ValueError("Количество вопросов должно быть положительным")
        if self.interval_seconds is not None and self.interval_seconds < 1:
            raise ValueError("Интервал должен быть положительным")
        if self.open_period_seconds is not None and self.open_period_seconds < 1:
            raise ValueError("Период открытия должен быть положительным")


@dataclass
class QuizQuestion:
    """Вопрос викторины"""
    question_id: str
    text: str
    options: List[str]
    correct_option: int
    category: str
    explanation: Optional[str] = None
    image_url: Optional[str] = None

    def __post_init__(self):
        """Валидация после создания"""
        if not self.text.strip():
            raise ValueError("Текст вопроса не может быть пустым")
        if len(self.options) < 2:
            raise ValueError("Вопрос должен иметь минимум 2 варианта ответа")
        if self.correct_option < 0 or self.correct_option >= len(self.options):
            raise ValueError("Индекс правильного ответа выходит за пределы вариантов")


@dataclass
class QuizAnswer:
    """Ответ пользователя на вопрос"""
    user_id: int
    question_id: str
    selected_option: int
    timestamp: datetime
    is_correct: bool = False
    response_time: Optional[float] = None

    def __post_init__(self):
        """Валидация после создания"""
        if self.response_time is not None and self.response_time < 0:
            raise ValueError("Время ответа не может быть отрицательным")


@dataclass
class QuizSession:
    """Сессия викторины"""
    session_id: str
    chat_id: int
    config: QuizConfig
    questions: List[QuizQuestion] = field(default_factory=list)
    answers: Dict[str, List[QuizAnswer]] = field(default_factory=dict)
    current_question_index: int = 0
    state: QuizState = QuizState.CREATED
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    message_ids: List[int] = field(default_factory=list)
    scheduled_job_id: Optional[str] = None

    @property
    def is_active(self) -> bool:
        """Проверяет, активна ли викторина"""
        return self.state in [QuizState.STARTED, QuizState.ACTIVE]

    @property
    def is_completed(self) -> bool:
        """Проверяет, завершена ли викторина"""
        return self.state in [QuizState.COMPLETED, QuizState.CANCELLED, QuizState.TIMEOUT]

    @property
    def current_question(self) -> Optional[QuizQuestion]:
        """Текущий вопрос"""
        if 0 <= self.current_question_index < len(self.questions):
            return self.questions[self.current_question_index]
        return None

    @property
    def progress(self) -> tuple[int, int]:
        """Прогресс викторины (текущий вопрос, всего вопросов)"""
        return (self.current_question_index + 1, len(self.questions))

    @property
    def duration(self) -> Optional[timedelta]:
        """Длительность викторины"""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        elif self.started_at:
            return datetime.now() - self.started_at
        return None

    def get_user_answers(self, user_id: int) -> List[QuizAnswer]:
        """Получить ответы пользователя"""
        all_answers = []
        for question_answers in self.answers.values():
            user_answers = [a for a in question_answers if a.user_id == user_id]
            all_answers.extend(user_answers)
        return sorted(all_answers, key=lambda x: x.timestamp)


@dataclass
class QuizResult:
    """Результат викторины для пользователя"""
    user_id: int
    session_id: str
    chat_id: int
    total_questions: int
    correct_answers: int
    total_time: Optional[float] = None
    answers: List[QuizAnswer] = field(default_factory=list)
    completed_at: datetime = field(default_factory=datetime.now)

    @property
    def accuracy(self) -> float:
        """Точность ответов в процентах"""
        if self.total_questions == 0:
            return 0.0
        return (self.correct_answers / self.total_questions) * 100

    @property
    def average_time(self) -> Optional[float]:
        """Среднее время ответа на вопрос"""
        if not self.answers or self.total_questions == 0:
            return None

        valid_times = [a.response_time for a in self.answers if a.response_time is not None]
        if not valid_times:
            return None

        return sum(valid_times) / len(valid_times)


@dataclass
class QuizStatistics:
    """Статистика викторины"""
    session_id: str
    chat_id: int
    total_participants: int
    total_questions: int
    total_answers: int
    average_accuracy: float
    completion_rate: float
    average_time: Optional[float] = None
    generated_at: datetime = field(default_factory=datetime.now)


@dataclass
class CallbackData:
    """Данные callback-запроса для викторин"""
    action: str
    session_id: Optional[str] = None
    question_index: Optional[int] = None
    user_id: Optional[int] = None
    data: Optional[str] = None

    @classmethod
    def from_callback_data(cls, callback_data: str) -> 'CallbackData':
        """Создать объект из строки callback-данных"""
        parts = callback_data.split('_', 2)
        if len(parts) < 2:
            raise ValueError("Неверный формат callback-данных")

        action = parts[0]
        session_id = parts[1] if len(parts) > 1 and parts[1] != 'None' else None
        data = parts[2] if len(parts) > 2 else None

        return cls(
            action=action,
            session_id=session_id,
            data=data
        )

    def to_callback_data(self) -> str:
        """Преобразовать в строку для callback"""
        parts = [self.action]
        if self.session_id:
            parts.append(self.session_id)
        else:
            parts.append('None')

        if self.data:
            parts.append(self.data)

        return '_'.join(parts)


@dataclass
class QuizStateData:
    """Данные состояния викторины для сохранения"""
    session_id: str
    chat_id: int
    config: Dict[str, Any]
    questions: List[Dict[str, Any]]
    answers: Dict[str, List[Dict[str, Any]]]
    current_question_index: int
    state: str
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    message_ids: List[int]
    scheduled_job_id: Optional[str]

    @classmethod
    def from_session(cls, session: QuizSession) -> 'QuizStateData':
        """Создать из объекта QuizSession"""
        return cls(
            session_id=session.session_id,
            chat_id=session.chat_id,
            config={
                'mode': session.config.mode.value,
                'num_questions': session.config.num_questions,
                'categories': session.config.categories,
                'interval_seconds': session.config.interval_seconds,
                'open_period_seconds': session.config.open_period_seconds,
                'announce_quiz': session.config.announce_quiz,
                'category_pool_mode': session.config.category_pool_mode
            },
            questions=[{
                'question_id': q.question_id,
                'text': q.text,
                'options': q.options,
                'correct_option': q.correct_option,
                'category': q.category,
                'explanation': q.explanation,
                'image_url': q.image_url
            } for q in session.questions],
            answers={
                qid: [{
                    'user_id': a.user_id,
                    'question_id': a.question_id,
                    'selected_option': a.selected_option,
                    'timestamp': a.timestamp.isoformat(),
                    'is_correct': a.is_correct,
                    'response_time': a.response_time
                } for a in answers]
                for qid, answers in session.answers.items()
            },
            current_question_index=session.current_question_index,
            state=session.state.value,
            created_at=session.created_at.isoformat(),
            started_at=session.started_at.isoformat() if session.started_at else None,
            completed_at=session.completed_at.isoformat() if session.completed_at else None,
            message_ids=session.message_ids,
            scheduled_job_id=session.scheduled_job_id
        )

    def to_session(self) -> QuizSession:
        """Преобразовать в объект QuizSession"""
        config = QuizConfig(
            mode=QuizMode(self.config['mode']),
            num_questions=self.config['num_questions'],
            categories=self.config['categories'],
            interval_seconds=self.config.get('interval_seconds'),
            open_period_seconds=self.config.get('open_period_seconds'),
            announce_quiz=self.config.get('announce_quiz', True),
            category_pool_mode=self.config.get('category_pool_mode', False)
        )

        questions = [
            QuizQuestion(
                question_id=q['question_id'],
                text=q['text'],
                options=q['options'],
                correct_option=q['correct_option'],
                category=q['category'],
                explanation=q.get('explanation'),
                image_url=q.get('image_url')
            ) for q in self.questions
        ]

        answers = {}
        for qid, ans_list in self.answers.items():
            answers[qid] = [
                QuizAnswer(
                    user_id=a['user_id'],
                    question_id=a['question_id'],
                    selected_option=a['selected_option'],
                    timestamp=datetime.fromisoformat(a['timestamp']),
                    is_correct=a.get('is_correct', False),
                    response_time=a.get('response_time')
                ) for a in ans_list
            ]

        return QuizSession(
            session_id=self.session_id,
            chat_id=self.chat_id,
            config=config,
            questions=questions,
            answers=answers,
            current_question_index=self.current_question_index,
            state=QuizState(self.state),
            created_at=datetime.fromisoformat(self.created_at),
            started_at=datetime.fromisoformat(self.started_at) if self.started_at else None,
            completed_at=datetime.fromisoformat(self.completed_at) if self.completed_at else None,
            message_ids=self.message_ids,
            scheduled_job_id=self.scheduled_job_id
        )


# Типы для обратной совместимости
QuizParams = Dict[str, Any]  # Для старых функций
UserQuizResult = QuizResult  # Для совместимости
