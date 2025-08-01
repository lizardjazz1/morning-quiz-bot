#handlers/daily_quiz_scheduler.py
from __future__ import annotations
import logging
from datetime import time, timedelta
import asyncio
from typing import TYPE_CHECKING, List, Dict, Any

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

    def _get_job_name_for_time_entry(self, chat_id: int, time_entry_index: int) -> str:
        """Генерирует уникальное имя задачи для конкретного времени запуска в чате."""
        return f"daily_quiz_for_chat_{chat_id}_time_idx_{time_entry_index}"

    async def _trigger_daily_quiz_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.job or not isinstance(context.job.data, dict) or "chat_id" not in context.job.data:
            logger.error("_trigger_daily_quiz_job вызван без chat_id в context.job.data.")
            return

        chat_id: int = context.job.data["chat_id"]
        logger.info(f"Запуск задачи ежедневной викторины для чата {chat_id} (Job: {context.job.name if context.job else 'N/A'}).")

        active_quiz_in_chat = self.state.get_active_quiz(chat_id)
        if active_quiz_in_chat and not active_quiz_in_chat.is_stopping:
            logger.warning(f"Запуск ежедневной викторины в чате {chat_id} пропущен: другая викторина уже активна.")
            return

        chat_settings = self.data_manager.get_chat_settings(chat_id)
        daily_quiz_cfg_chat = chat_settings.get("daily_quiz", {})
        daily_quiz_defaults_app = self.app_config.daily_quiz_defaults

        if not daily_quiz_cfg_chat.get("enabled", daily_quiz_defaults_app.get("enabled")):
            logger.info(f"Ежедневная викторина для чата {chat_id} отключена в настройках. Пропуск запуска.")
            return

        num_questions = daily_quiz_cfg_chat.get("num_questions", daily_quiz_defaults_app["num_questions"])
        open_period = daily_quiz_cfg_chat.get("poll_open_seconds", daily_quiz_defaults_app.get("poll_open_seconds", 600))
        interval_seconds = daily_quiz_cfg_chat.get("interval_seconds", daily_quiz_defaults_app["interval_seconds"])
        categories_mode = daily_quiz_cfg_chat.get("categories_mode", daily_quiz_defaults_app["categories_mode"])

        category_names_for_quiz: Optional[List[str]] = None
        is_random_categories_mode_for_quiz = False

        if categories_mode == "specific":
            category_names_for_quiz = daily_quiz_cfg_chat.get("specific_categories", daily_quiz_defaults_app.get("specific_categories", []))
            if not category_names_for_quiz:
                 logger.warning(f"Ежедневная викторина (чат {chat_id}): режим 'specific', но список категорий пуст. Будут случайные.")
                 is_random_categories_mode_for_quiz = True
        elif categories_mode == "random":
            is_random_categories_mode_for_quiz = True
        elif categories_mode == "all_enabled":
            category_names_for_quiz = None
            is_random_categories_mode_for_quiz = False

        daily_quiz_type_config_from_app = self.app_config.quiz_types_config.get("daily", {})

        await self.quiz_manager._initiate_quiz_session(
            context=context, chat_id=chat_id, initiated_by_user=None,
            quiz_type="daily",
            quiz_mode=daily_quiz_type_config_from_app.get("mode", "serial_interval"),
            num_questions=num_questions, open_period_seconds=open_period,
            announce=daily_quiz_type_config_from_app.get("announce", True),
            announce_delay_seconds=daily_quiz_type_config_from_app.get("announce_delay_seconds", 0),
            category_names_for_quiz=category_names_for_quiz,
            is_random_categories_mode=is_random_categories_mode_for_quiz,
            interval_seconds=interval_seconds
        )

    async def reschedule_job_for_chat(self, chat_id: int) -> None:
        if not self.application.job_queue:
            logger.error("JobQueue не доступен в DailyQuizScheduler. Невозможно перепланировать задачи.")
            return

        job_queue: JobQueue = self.application.job_queue # type: ignore

        prefix_job_name_base = f"daily_quiz_for_chat_{chat_id}_time_idx_"
        existing_jobs_for_chat = [job for job in job_queue.jobs() if job.name and job.name.startswith(prefix_job_name_base)]

        if existing_jobs_for_chat:
            for job in existing_jobs_for_chat:
                job.schedule_removal()
            logger.info(f"Удалены существующие задачи ({len(existing_jobs_for_chat)}) с префиксом '{prefix_job_name_base}' для чата {chat_id} перед перепланировкой.")

        chat_settings = self.data_manager.get_chat_settings(chat_id)
        daily_quiz_cfg_chat = chat_settings.get("daily_quiz", {})
        daily_quiz_defaults_app = self.app_config.daily_quiz_defaults

        if not daily_quiz_cfg_chat.get("enabled", daily_quiz_defaults_app.get("enabled")):
            logger.info(f"Ежедневная викторина для чата {chat_id} отключена. Задачи не будут запланированы.")
            return

        times_msk_list: List[Dict[str, int]] = daily_quiz_cfg_chat.get("times_msk", daily_quiz_defaults_app.get("times_msk", []))

        if not times_msk_list:
            logger.info(f"Для чата {chat_id} не настроено ни одного времени запуска ежедневной викторины. Задачи не запланированы.")
            return

        planned_count_for_this_chat = 0
        for i, time_entry in enumerate(times_msk_list):
            hour_msk = time_entry.get("hour")
            minute_msk = time_entry.get("minute")

            if hour_msk is None or minute_msk is None:
                logger.warning(f"Некорректная запись времени (индекс {i}) для чата {chat_id}: {time_entry}. Пропуск.")
                continue

            job_name_for_this_time = self._get_job_name_for_time_entry(chat_id, i)

            try:
                target_time_in_moscow_tz = time(hour=hour_msk, minute=minute_msk, tzinfo=self.moscow_tz)
            except ValueError as e_time_format:
                logger.error(f"Некорректное время ({hour_msk}:{minute_msk}) для ежедневной викторины (индекс {i}) в чате {chat_id}: {e_time_format}. Задача не запланирована.")
                continue

            job_queue.run_daily(
                callback=self._trigger_daily_quiz_job,
                time=target_time_in_moscow_tz,
                data={"chat_id": chat_id, "time_entry_index": i},
                name=job_name_for_this_time
            )
            logger.info(f"Ежедневная викторина для чата {chat_id} (время {i+1}) успешно запланирована на {target_time_in_moscow_tz.strftime('%H:%M %Z')}. Имя задачи: {job_name_for_this_time}")
            planned_count_for_this_chat +=1

        if planned_count_for_this_chat > 0:
            logger.info(f"Всего запланировано {planned_count_for_this_chat} задач для ежедневной викторины в чате {chat_id}.")
        elif times_msk_list :
            logger.warning(f"Ни одна задача для ежедневной викторины не была запланирована для чата {chat_id}, хотя времена были указаны.")

    # ИЗМЕНЕНИЕ: Переименован для соответствия вызову в bot.py
    async def schedule_all_daily_quizzes_from_startup(self) -> None:
        logger.info("Инициализация задач для ежедневных викторин при запуске бота...")
        if not self.application.job_queue:
            logger.error("JobQueue не доступен при schedule_all_daily_quizzes_from_startup. Задачи не будут инициализированы.")
            return

        all_chat_ids_with_settings = list(self.state.chat_settings.keys())

        if not all_chat_ids_with_settings:
            logger.info("Нет сохраненных настроек чатов. Задачи для ежедневных викторин не инициализируются.")
            return

        reschedule_tasks = [self.reschedule_job_for_chat(chat_id_int) for chat_id_int in all_chat_ids_with_settings]

        if reschedule_tasks:
            results = await asyncio.gather(*reschedule_tasks, return_exceptions=True)
            successful_initializations = 0
            for i, result in enumerate(results):
                chat_id_for_log = all_chat_ids_with_settings[i]
                if isinstance(result, Exception):
                    logger.error(f"Ошибка при инициализации/перепланировке задач для чата {chat_id_for_log}: {result}", exc_info=result)
                else:
                    successful_initializations += 1
            logger.info(f"Инициализация/перепланировка задач ежедневных викторин завершена. Попыток: {len(all_chat_ids_with_settings)}, успешных вызовов reschedule_job_for_chat: {successful_initializations}.")
        else:
            logger.info("Нет чатов для инициализации/перепланировки задач ежедневных викторин.")

    def get_handlers(self) -> list:
        return []

