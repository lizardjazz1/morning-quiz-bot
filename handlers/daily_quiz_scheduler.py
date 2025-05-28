#handlers/daily_quiz_scheduler.py
from __future__ import annotations
import logging
from datetime import time, timedelta, datetime
import asyncio
from typing import TYPE_CHECKING, List, Optional

import pytz
from telegram.ext import Application, ContextTypes, JobQueue

from app_config import AppConfig
from state import BotState
from data_manager import DataManager

if TYPE_CHECKING:
    from .quiz_manager import QuizManager

logger = logging.getLogger(__name__)

class DailyQuizScheduler:
    def __init__(
        self,
        app_config: AppConfig,
        state: BotState,
        data_manager: DataManager,
        quiz_manager: QuizManager,
        application: Application
    ):
        self.app_config = app_config
        self.state = state
        self.data_manager = data_manager
        self.quiz_manager = quiz_manager
        self.application = application
        self.moscow_tz = pytz.timezone('Europe/Moscow')

    def _get_job_name(self, chat_id: int) -> str:
        return f"daily_quiz_for_chat_{chat_id}"

    async def _trigger_daily_quiz_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.job or not context.job.data or "chat_id" not in context.job.data:
            logger.error("_trigger_daily_quiz_job вызван без chat_id.")
            return
            
        chat_id: int = context.job.data["chat_id"]
        logger.info(f"Запуск задачи ежедневной викторины для чата {chat_id}.")

        active_quiz_in_chat = self.state.get_active_quiz(chat_id)
        if active_quiz_in_chat and not active_quiz_in_chat.is_stopping:
            logger.warning(f"Запуск ежедневной викторины в чате {chat_id} пропущен: другая викторина активна.")
            return

        chat_settings = self.data_manager.get_chat_settings(chat_id)
        daily_quiz_cfg_chat = chat_settings.get("daily_quiz", {})
        daily_quiz_defaults_app = self.app_config.daily_quiz_defaults

        if not daily_quiz_cfg_chat.get("enabled", daily_quiz_defaults_app.get("enabled", False)):
            logger.info(f"Ежедневная викторина для чата {chat_id} отключена. Пропуск.")
            return

        num_questions = daily_quiz_cfg_chat.get("num_questions", daily_quiz_defaults_app["num_questions"])
        open_period = daily_quiz_cfg_chat.get("poll_open_seconds", daily_quiz_defaults_app["open_period_seconds"])
        interval_seconds = daily_quiz_cfg_chat.get("interval_seconds", daily_quiz_defaults_app["interval_seconds"])
        categories_mode = daily_quiz_cfg_chat.get("categories_mode", daily_quiz_defaults_app["categories_mode"])

        category_names_for_quiz: Optional[List[str]] = None
        is_random_categories_mode_for_quiz = False

        if categories_mode == "specific":
            category_names_for_quiz = daily_quiz_cfg_chat.get("specific_categories", daily_quiz_defaults_app["specific_categories"])
            if not category_names_for_quiz:
                 logger.warning(f"Ежедневная викторина (чат {chat_id}): режим 'specific', но категории не выбраны. Используется 'random_from_pool'.")
                 is_random_categories_mode_for_quiz = True
        elif categories_mode == "random":
            is_random_categories_mode_for_quiz = True
        elif categories_mode == "all_enabled":
            is_random_categories_mode_for_quiz = False
            category_names_for_quiz = None
        
        daily_quiz_type_config = self.app_config.quiz_types_config.get("daily", {})
        
        await self.quiz_manager._initiate_quiz_session(
            context=context,
            chat_id=chat_id,
            initiated_by_user=None,
            quiz_type="daily",
            quiz_mode=daily_quiz_type_config.get("mode", "serial_interval"),
            num_questions=num_questions,
            open_period_seconds=open_period,
            announce=daily_quiz_type_config.get("announce", True),
            announce_delay_seconds=daily_quiz_type_config.get("announce_delay_seconds", 0),
            category_names_for_quiz=category_names_for_quiz,
            is_random_categories_mode=is_random_categories_mode_for_quiz,
            interval_seconds=interval_seconds
        )

    async def reschedule_job_for_chat(self, chat_id: int) -> None:
        if not self.application.job_queue:
            logger.error("JobQueue не доступен в DailyQuizScheduler.")
            return
            
        job_queue: JobQueue = self.application.job_queue
        job_name = self._get_job_name(chat_id)

        current_jobs = job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()
            logger.info(f"Удалена задача '{job_name}' для чата {chat_id}.")

        chat_settings = self.data_manager.get_chat_settings(chat_id)
        daily_quiz_cfg_chat = chat_settings.get("daily_quiz", {})
        daily_quiz_defaults_app = self.app_config.daily_quiz_defaults

        if not daily_quiz_cfg_chat.get("enabled", daily_quiz_defaults_app.get("enabled", False)):
            logger.info(f"Ежедневная викторина для чата {chat_id} отключена. Задача не запланирована.")
            return

        hour_msk = daily_quiz_cfg_chat.get("hour_msk", daily_quiz_defaults_app["hour_msk"])
        minute_msk = daily_quiz_cfg_chat.get("minute_msk", daily_quiz_defaults_app["minute_msk"])

        try:
            target_time_msk = time(hour=hour_msk, minute=minute_msk, tzinfo=self.moscow_tz)
        except ValueError as e_time:
            logger.error(f"Некорректное время ({hour_msk}:{minute_msk}) для чата {chat_id}: {e_time}")
            return

        job_queue.run_daily(
            callback=self._trigger_daily_quiz_job,
            time=target_time_msk,
            data={"chat_id": chat_id},
            name=job_name
        )
        logger.info(f"Ежедневная викторина для чата {chat_id} запланирована на {target_time_msk.strftime('%H:%M')} МСК. Имя: {job_name}")

    async def initialize_jobs(self) -> None:
        logger.info("Инициализация задач для ежедневных викторин...")
        all_chat_ids_with_settings = list(self.state.chat_settings.keys())
        scheduled_count = 0
        for chat_id in all_chat_ids_with_settings:
            chat_s_from_state = self.state.chat_settings.get(chat_id) 
            if chat_s_from_state: # Проверяем, что настройки еще существуют
                daily_cfg = chat_s_from_state.get("daily_quiz", {})
                is_enabled_in_state = daily_cfg.get("enabled", self.app_config.daily_quiz_defaults.get("enabled", False))
                if is_enabled_in_state:
                    try:
                        await self.reschedule_job_for_chat(chat_id)
                        scheduled_count +=1
                    except Exception as e_init_job:
                        logger.error(f"Ошибка инициализации задачи для чата {chat_id}: {e_init_job}", exc_info=True)
        
        logger.info(f"Инициализация задач ежедневных викторин завершена. Запланировано для {scheduled_count} чатов.")

    def get_handlers(self) -> list:
        return []
