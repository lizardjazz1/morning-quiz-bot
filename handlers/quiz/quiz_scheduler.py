"""
Планировщик викторин для Morning Quiz Bot
Отвечает за планирование, отложенные задачи и управление расписанием викторин
"""

from __future__ import annotations
import logging
import asyncio
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta, time
from dataclasses import dataclass

from .quiz_types import QuizSession, QuizConfig, QuizMode, QuizState
from utils import schedule_job_unique, get_current_utc_time

logger = logging.getLogger(__name__)


@dataclass
class ScheduledQuiz:
    """Запланированная викторина"""
    quiz_id: str
    chat_id: int
    config: QuizConfig
    scheduled_time: datetime
    job_id: Optional[str] = None
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class QuizScheduler:
    """Планировщик викторин"""

    def __init__(self, application):
        self.application = application
        self.scheduled_quizzes: Dict[str, ScheduledQuiz] = {}
        self.job_callbacks: Dict[str, Callable] = {}

        # Инициализация ежедневных викторин
        self.daily_quiz_configs: Dict[int, Dict[str, Any]] = {}

    async def schedule_quiz(
        self,
        chat_id: int,
        config: QuizConfig,
        delay_seconds: int,
        callback: Callable,
        quiz_id: Optional[str] = None
    ) -> str:
        """Запланировать викторину с задержкой"""
        if quiz_id is None:
            quiz_id = f"quiz_{chat_id}_{int(datetime.now().timestamp())}"

        scheduled_time = datetime.now() + timedelta(seconds=delay_seconds)

        # Создаем запланированную викторину
        scheduled_quiz = ScheduledQuiz(
            quiz_id=quiz_id,
            chat_id=chat_id,
            config=config,
            scheduled_time=scheduled_time
        )

        # Сохраняем callback
        self.job_callbacks[quiz_id] = callback

        # Планируем задачу
        job_id = schedule_job_unique(
            self.application.job_queue,
            scheduled_time,
            self._quiz_job_wrapper,
            quiz_id
        )

        scheduled_quiz.job_id = job_id
        self.scheduled_quizzes[quiz_id] = scheduled_quiz

        logger.info(f"📅 Запланирована викторина {quiz_id} на {scheduled_time}")
        return quiz_id

    async def schedule_daily_quiz(
        self,
        chat_id: int,
        config: QuizConfig,
        quiz_time: time,
        callback: Callable
    ) -> str:
        """Запланировать ежедневную викторину"""
        quiz_id = f"daily_{chat_id}_{quiz_time.strftime('%H%M')}"

        # Вычисляем время следующего запуска
        now = datetime.now()
        scheduled_time = datetime.combine(now.date(), quiz_time)

        if scheduled_time <= now:
            # Если время уже прошло сегодня, планируем на завтра
            scheduled_time += timedelta(days=1)

        # Создаем запланированную викторину
        scheduled_quiz = ScheduledQuiz(
            quiz_id=quiz_id,
            chat_id=chat_id,
            config=config,
            scheduled_time=scheduled_time
        )

        # Сохраняем callback
        self.job_callbacks[quiz_id] = callback

        # Планируем ежедневную задачу
        job_id = schedule_job_unique(
            self.application.job_queue,
            scheduled_time,
            self._daily_quiz_job_wrapper,
            quiz_id
        )

        scheduled_quiz.job_id = job_id
        self.scheduled_quizzes[quiz_id] = scheduled_quiz

        # Сохраняем конфигурацию ежедневной викторины
        self.daily_quiz_configs[chat_id] = {
            'quiz_time': quiz_time,
            'config': config,
            'callback': callback
        }

        logger.info(f"📅 Запланирована ежедневная викторина {quiz_id} на {scheduled_time}")
        return quiz_id

    async def cancel_scheduled_quiz(self, quiz_id: str) -> bool:
        """Отменить запланированную викторину"""
        if quiz_id not in self.scheduled_quizzes:
            logger.warning(f"Викторина {quiz_id} не найдена в запланированных")
            return False

        scheduled_quiz = self.scheduled_quizzes[quiz_id]

        # Отменяем задачу
        if scheduled_quiz.job_id:
            try:
                self.application.job_queue.scheduler.remove_job(scheduled_quiz.job_id)
                logger.info(f"Отменена задача {scheduled_quiz.job_id} для викторины {quiz_id}")
            except Exception as e:
                logger.error(f"Ошибка при отмене задачи {scheduled_quiz.job_id}: {e}")

        # Удаляем из запланированных
        del self.scheduled_quizzes[quiz_id]
        if quiz_id in self.job_callbacks:
            del self.job_callbacks[quiz_id]

        logger.info(f"❌ Отменена викторина {quiz_id}")
        return True

    async def cancel_chat_quizzes(self, chat_id: int) -> int:
        """Отменить все викторины для чата"""
        quiz_ids_to_cancel = [
            quiz_id for quiz_id, quiz in self.scheduled_quizzes.items()
            if quiz.chat_id == chat_id
        ]

        cancelled_count = 0
        for quiz_id in quiz_ids_to_cancel:
            if await self.cancel_scheduled_quiz(quiz_id):
                cancelled_count += 1

        if quiz_ids_to_cancel:
            logger.info(f"Отменено {cancelled_count} викторин для чата {chat_id}")

        return cancelled_count

    def get_scheduled_quizzes(self, chat_id: Optional[int] = None) -> List[ScheduledQuiz]:
        """Получить список запланированных викторин"""
        if chat_id is None:
            return list(self.scheduled_quizzes.values())

        return [
            quiz for quiz in self.scheduled_quizzes.values()
            if quiz.chat_id == chat_id
        ]

    def get_upcoming_quizzes(self, within_hours: int = 24) -> List[ScheduledQuiz]:
        """Получить предстоящие викторины в ближайшие часы"""
        now = datetime.now()
        cutoff_time = now + timedelta(hours=within_hours)

        return [
            quiz for quiz in self.scheduled_quizzes.values()
            if now <= quiz.scheduled_time <= cutoff_time
        ]

    async def _quiz_job_wrapper(self, quiz_id: str):
        """Обертка для выполнения запланированной викторины"""
        try:
            if quiz_id not in self.scheduled_quizzes:
                logger.warning(f"Викторина {quiz_id} не найдена при выполнении")
                return

            if quiz_id not in self.job_callbacks:
                logger.error(f"Callback для викторины {quiz_id} не найден")
                return

            scheduled_quiz = self.scheduled_quizzes[quiz_id]
            callback = self.job_callbacks[quiz_id]

            logger.info(f"🚀 Запускается запланированная викторина {quiz_id}")

            # Выполняем callback
            await callback(scheduled_quiz)

            # Удаляем выполненную викторину
            del self.scheduled_quizzes[quiz_id]
            del self.job_callbacks[quiz_id]

        except Exception as e:
            logger.error(f"❌ Ошибка при выполнении викторины {quiz_id}: {e}")

    async def _daily_quiz_job_wrapper(self, quiz_id: str):
        """Обертка для выполнения ежедневной викторины"""
        try:
            if quiz_id not in self.scheduled_quizzes:
                logger.warning(f"Ежедневная викторина {quiz_id} не найдена")
                return

            scheduled_quiz = self.scheduled_quizzes[quiz_id]
            callback = self.job_callbacks[quiz_id]

            logger.info(f"🌅 Запускается ежедневная викторина {quiz_id}")

            # Выполняем callback
            await callback(scheduled_quiz)

            # Планируем следующий запуск через 24 часа
            next_time = scheduled_quiz.scheduled_time + timedelta(days=1)
            scheduled_quiz.scheduled_time = next_time

            # Перепланируем задачу
            new_job_id = schedule_job_unique(
                self.application.job_queue,
                next_time,
                self._daily_quiz_job_wrapper,
                quiz_id
            )

            scheduled_quiz.job_id = new_job_id
            logger.info(f"📅 Следующий запуск ежедневной викторины {quiz_id} в {next_time}")

        except Exception as e:
            logger.error(f"❌ Ошибка при выполнении ежедневной викторины {quiz_id}: {e}")

    async def update_daily_quiz_config(
        self,
        chat_id: int,
        quiz_time: Optional[time] = None,
        config: Optional[QuizConfig] = None
    ) -> bool:
        """Обновить конфигурацию ежедневной викторины"""
        if chat_id not in self.daily_quiz_configs:
            logger.warning(f"Ежедневная викторина для чата {chat_id} не найдена")
            return False

        current_config = self.daily_quiz_configs[chat_id]

        # Находим и отменяем старую викторину
        old_quiz_id = f"daily_{chat_id}_{current_config['quiz_time'].strftime('%H%M')}"
        await self.cancel_scheduled_quiz(old_quiz_id)

        # Обновляем конфигурацию
        if quiz_time:
            current_config['quiz_time'] = quiz_time
        if config:
            current_config['config'] = config

        # Создаем новую викторину
        new_quiz_id = await self.schedule_daily_quiz(
            chat_id=chat_id,
            config=current_config['config'],
            quiz_time=current_config['quiz_time'],
            callback=current_config['callback']
        )

        logger.info(f"🔄 Обновлена ежедневная викторина для чата {chat_id}")
        return True

    def get_daily_quiz_info(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Получить информацию о ежедневной викторине для чата"""
        return self.daily_quiz_configs.get(chat_id)

    async def cleanup_expired_quizzes(self) -> int:
        """Очистить истекшие викторины"""
        now = datetime.now()
        expired_quizzes = []

        for quiz_id, quiz in self.scheduled_quizzes.items():
            # Если викторина должна была начаться более часа назад
            if (now - quiz.scheduled_time).total_seconds() > 3600:
                expired_quizzes.append(quiz_id)

        for quiz_id in expired_quizzes:
            await self.cancel_scheduled_quiz(quiz_id)

        if expired_quizzes:
            logger.info(f"🧹 Очищено {len(expired_quizzes)} истекших викторин")

        return len(expired_quizzes)

    def get_scheduler_stats(self) -> Dict[str, Any]:
        """Получить статистику планировщика"""
        now = datetime.now()
        upcoming_24h = [q for q in self.scheduled_quizzes.values()
                       if now <= q.scheduled_time <= now + timedelta(hours=24)]

        return {
            'total_scheduled': len(self.scheduled_quizzes),
            'upcoming_24h': len(upcoming_24h),
            'daily_quizzes': len(self.daily_quiz_configs),
            'next_quiz': min(upcoming_24h, key=lambda q: q.scheduled_time) if upcoming_24h else None
        }
