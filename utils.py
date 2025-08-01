#utils.py
import logging
import html
from typing import List, Dict, Any, Optional, Callable, Coroutine, Union
from datetime import datetime, timedelta, timezone

from telegram import Update, User as TelegramUser
from telegram.ext import ContextTypes, JobQueue
from telegram.constants import ChatMemberStatus

logger = logging.getLogger(__name__)

def get_current_utc_time() -> datetime:
    return datetime.now(timezone.utc)

def get_username_or_firstname(user: Optional[TelegramUser]) -> str:
    if user:
        if user.username:
            return f"@{user.username}"
        return user.first_name
    return "Неизвестный пользователь"

def get_mention_html(user_id: int, name: str) -> str:
    escaped_name = html.escape(name)
    return f'<a href="tg://user?id={user_id}">{escaped_name}</a>'

def escape_markdown_v2(text: str) -> str:
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception: 
            logger.warning(f"Не удалось преобразовать в строку для escape_markdown_v2: {type(text)}")
            return ""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return "".join(f'\\{char}' if char in escape_chars else char for char in text)

def pluralize(count: int, one: str, few: str, many: str) -> str:
    try:
        count = abs(int(count))
    except (ValueError, TypeError):
        logger.warning(f"Некорректное значение для count в pluralize: {count}. Используется 0.")
        count = 0

    if count % 10 == 1 and count % 100 != 11:
        return f"{count} {one}"
    if 2 <= count % 10 <= 4 and (count % 100 < 10 or count % 100 >= 20):
        return f"{count} {few}"
    return f"{count} {many}"

def schedule_job_unique(
    job_queue: JobQueue,
    job_name: str,
    callback: Callable[..., Union[None, Coroutine[Any, Any, None]]],
    when: Union[timedelta, float, datetime],
    data: Any = None,
) -> None:
    current_jobs = job_queue.get_jobs_by_name(job_name)
    if current_jobs:
        logger.info(f"Найдены существующие задачи ({len(current_jobs)}) с именем '{job_name}'. Удаляем...")
        for job in current_jobs:
            job.schedule_removal()
        logger.info(f"Все старые задачи '{job_name}' удалены.")
    else:
        logger.debug(f"Задачи с именем '{job_name}' не найдены. Создаем новую.")

    job_queue.run_once(callback, when, data=data, name=job_name) # type: ignore

    when_display = when
    if isinstance(when, (float, int)): when_display = f"{when} сек"
    elif isinstance(when, datetime): when_display = when.isoformat()
    elif isinstance(when, timedelta): when_display = f"через {when}"

    logger.info(f"Задача '{job_name}' запланирована на {when_display}.")

async def is_user_admin_in_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.effective_chat or not update.effective_user:
        return False
    if update.effective_chat.type == "private":
        return True
    try:
        chat_member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        return chat_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса админа для {update.effective_user.id} в {update.effective_chat.id}: {e}")
        return False

def format_seconds_to_human_readable_time(total_seconds: Optional[Union[int, float]]) -> str:
    """
    Форматирует секунды в человекочитаемый формат (X мин Y сек или Z сек).
    Возвращает "N/A" если входные данные некорректны.
    """
    if total_seconds is None or not isinstance(total_seconds, (int, float)) or total_seconds < 0:
        return "N/A"
    
    total_seconds_int = int(total_seconds)

    if total_seconds_int < 60:
        return f"{total_seconds_int} сек"
    
    minutes = total_seconds_int // 60
    seconds = total_seconds_int % 60
    
    if seconds == 0:
        return f"{minutes} мин"
    else:
        return f"{minutes} мин {seconds} сек"

