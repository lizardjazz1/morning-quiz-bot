# bot/handlers/daily_quiz_scheduler.py
from datetime import time
import pytz
from telegram.ext import Application, JobQueue, ContextTypes

import state
from app_config import logger, QUIZ_CONFIG
from data_manager import get_chat_settings # To get daily quiz settings for each chat
from handlers.quiz_manager import _initiate_quiz # To start the daily quiz


def moscow_time_obj(hour: int, minute: int) -> time:
    """Creates a datetime.time object for the specified hour and minute in Moscow time."""
    moscow_tz = pytz.timezone('Europe/Moscow')
    return time(hour=hour, minute=minute, tzinfo=moscow_tz)


async def _trigger_daily_quiz_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id_str: str = job_data["chat_id_str"]

    logger.info(f"Daily quiz trigger job running for chat {chat_id_str}.")

    chat_q_settings = get_chat_settings(chat_id_str)
    daily_settings = chat_q_settings.get("daily_quiz", {})

    if not daily_settings.get("enabled", False):
        logger.info(f"Daily quiz for chat {chat_id_str} is disabled. Skipping.")
        return

    if chat_id_str in state.active_quizzes:
        logger.warning(f"Attempted to start daily quiz in {chat_id_str}, but another quiz ('{state.active_quizzes[chat_id_str]['quiz_type']}') is active.")
        try: await context.bot.send_message(chat_id_str, "Не удалось начать ежедневную викторину: уже идет другая игра.")
        except: pass
        return
    
    if chat_id_str in state.pending_scheduled_quizzes:
        logger.warning(f"Attempted to start daily quiz in {chat_id_str}, but a /quiz10notify is pending.")
        try: await context.bot.send_message(chat_id_str, "Не удалось начать ежедневную викторину: запланирована другая игра.")
        except: pass
        return

    num_questions = daily_settings.get("num_questions", QUIZ_CONFIG.get("quiz_types_config",{}).get("daily",{}).get("default_num_questions",10))
    open_period = daily_settings.get("poll_open_seconds", QUIZ_CONFIG.get("quiz_types_config",{}).get("daily",{}).get("default_open_period_seconds",600))
    interval_seconds = daily_settings.get("interval_seconds", QUIZ_CONFIG.get("quiz_types_config",{}).get("daily",{}).get("default_interval_seconds",60))
    
    # category_names_arg for _initiate_quiz will be handled internally by it based on quiz_type="daily"
    # and chat_settings.
    
    await _initiate_quiz(
        context=context,
        chat_id_str=chat_id_str,
        user_id_str="DAILY_SCHEDULER", # Special user ID for scheduled tasks
        quiz_type="daily",
        num_questions=num_questions,
        open_period=open_period,
        interval_seconds=interval_seconds
        # category_names_arg and is_random_category are determined by daily_settings within _initiate_quiz
    )

async def schedule_or_reschedule_daily_quiz_for_chat(application: Application, chat_id_str: str):
    job_queue: JobQueue | None = application.job_queue
    if not job_queue:
        logger.error(f"JobQueue not available. Cannot schedule daily quiz for chat {chat_id_str}.")
        return

    job_name = f"daily_quiz_trigger_chat_{chat_id_str}"
    
    # Remove existing job first
    existing_jobs = job_queue.get_jobs_by_name(job_name)
    for old_job in existing_jobs:
        old_job.schedule_removal()
    logger.debug(f"Removed existing daily quiz jobs for chat {chat_id_str} before rescheduling.")

    chat_q_settings = get_chat_settings(chat_id_str) # Get merged chat settings
    daily_settings = chat_q_settings.get("daily_quiz", {})

    if not daily_settings.get("enabled", False):
        logger.info(f"Daily quiz is disabled for chat {chat_id_str}. No job scheduled.")
        return

    hour = daily_settings.get("hour_msk", QUIZ_CONFIG.get("default_chat_settings",{}).get("daily_quiz",{}).get("hour_msk",7))
    minute = daily_settings.get("minute_msk", QUIZ_CONFIG.get("default_chat_settings",{}).get("daily_quiz",{}).get("minute_msk",0))
    
    target_time_msk = moscow_time_obj(hour, minute)
    
    job_queue.run_daily(
        _trigger_daily_quiz_job,
        time=target_time_msk,
        data={"chat_id_str": chat_id_str},
        name=job_name
    )
    logger.info(f"Daily quiz for chat {chat_id_str} scheduled for {hour:02d}:{minute:02d} MSK. Job: {job_name}")


async def schedule_all_daily_quizzes_on_startup(application: Application):
    """Schedules daily quizzes for all chats that have it enabled in their settings."""
    if not state.chat_settings: # chat_settings should be loaded by data_manager before this
        logger.info("No chat settings loaded. Cannot schedule daily quizzes on startup.")
        return

    logger.info(f"Scheduling daily quizzes for {len(state.chat_settings)} chats with settings...")
    scheduled_count = 0
    for chat_id_str, settings in state.chat_settings.items():
        if settings.get("daily_quiz", {}).get("enabled", False):
            try:
                await schedule_or_reschedule_daily_quiz_for_chat(application, chat_id_str)
                scheduled_count += 1
            except Exception as e:
                logger.error(f"Error scheduling daily quiz for chat {chat_id_str} on startup: {e}", exc_info=True)
    logger.info(f"Startup daily quiz scheduling complete. Scheduled for {scheduled_count} chats.")

