# quiz_bot/scheduler_setup.py
from apscheduler.schedulers.background import BackgroundScheduler
from quiz_logic import broadcast_quiz_to_active_chats
import logging

def setup_scheduler(application):
    scheduler = BackgroundScheduler(timezone="Europe/Moscow") # Укажите ваш часовой пояс
    # Передаем application (или context.application в новых версиях) для доступа к bot_data
    scheduler.add_job(broadcast_quiz_to_active_chats, 'cron', hour=8, minute=0, args=[application])
    # В новых версиях python-telegram-bot v20+ context передается автоматически,
    # и args=[application] может быть args=[application.context_types.DEFAULT_TYPE(application=application, chat_id=None, user_id=None)]
    # или проще всего - передать сам application, и внутри broadcast_quiz_to_active_chats использовать context=application
    # Однако, стандартный способ - это передать объект, у которого есть атрибут .bot_data и .bot
    # `application` имеет `application.bot` и `application.bot_data`
    scheduler.start()
    logging.info("Планировщик запущен: ежедневная викторина в 8:00.")
    return scheduler

