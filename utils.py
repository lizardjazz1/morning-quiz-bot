#utils.py
import logging
import html
from typing import List, Dict, Any, Optional, Callable, Coroutine, Union
from datetime import datetime, timedelta, timezone

from telegram import Update, User as TelegramUser
from telegram.ext import ContextTypes, JobQueue
from telegram.constants import ChatMemberStatus

import json
from pathlib import Path

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

# Centralized alias to emphasize intent when preparing text for MarkdownV2
# Use this in new code to standardize escaping across the project
def safe_md(text: str) -> str:
    return escape_markdown_v2(text)

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
        logger.warning("is_user_admin_in_update: Нет chat или user в update")
        return False
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    
    logger.info(f"Проверка админа: user_id={user_id}, chat_id={chat_id}, chat_type={chat_type}")
    
    # В личных сообщениях всегда администратор
    if chat_type == "private":
        logger.info(f"Личные сообщения - пользователь {user_id} считается администратором")
        return True
    
    try:
        # Проверяем статус участника чата
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        status = chat_member.status
        logger.info(f"Статус пользователя {user_id} в чате {chat_id}: {status}")
        
        is_admin = status in [ChatMemberStatus.ADMINISTRATOR, "creator"]
        logger.info(f"Пользователь {user_id} {'является' if is_admin else 'НЕ является'} администратором")
        
        return is_admin
        
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса админа для {user_id} в {chat_id}: {e}")
        # Если не можем проверить, возвращаем False для безопасности
        return False

async def add_admin_to_config(user_id: int, username: str = None) -> bool:
    """Добавляет пользователя в список администраторов"""
    try:
        admin_config_path = Path(__file__).parent / "config" / "admins.json"
        
        # Создаем файл если не существует
        if not admin_config_path.exists():
            admin_config = {
                "admin_user_ids": [],
                "admin_usernames": [],
                "description": "Список администраторов бота"
            }
        else:
            with open(admin_config_path, 'r', encoding='utf-8') as f:
                admin_config = json.load(f)
        
        # Добавляем ID если его нет
        if user_id not in admin_config.get("admin_user_ids", []):
            admin_config.setdefault("admin_user_ids", []).append(user_id)
            logger.info(f"Добавлен администратор по ID: {user_id}")
        
        # Добавляем username если его нет
        if username and f"@{username}" not in admin_config.get("admin_usernames", []):
            admin_config.setdefault("admin_usernames", []).append(f"@{username}")
            logger.info(f"Добавлен администратор по username: @{username}")
        
        # Сохраняем файл
        with open(admin_config_path, 'w', encoding='utf-8') as f:
            json.dump(admin_config, f, indent=4, ensure_ascii=False)
        
        logger.info(f"Администратор {user_id} (@{username}) успешно добавлен в конфигурацию")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при добавлении администратора {user_id}: {e}")
        return False

async def is_user_admin_by_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет, является ли пользователь администратором"""
    if not update.effective_user:
        return False
    
    # Сначала проверяем по конфигурации
    try:
        admin_config_path = Path(__file__).parent / "config" / "admins.json"
        if admin_config_path.exists():
            with open(admin_config_path, 'r', encoding='utf-8') as f:
                admin_config = json.load(f)
            
            user_id = update.effective_user.id
            username = update.effective_user.username
            
            # Проверяем по ID
            if user_id in admin_config.get("admin_user_ids", []):
                logger.info(f"Пользователь {user_id} найден в списке администраторов по ID")
                return True
            
            # Проверяем по username
            if username and f"@{username}" in admin_config.get("admin_usernames", []):
                logger.info(f"Пользователь @{username} найден в списке администраторов по username")
                return True
    except Exception as e:
        logger.error(f"Ошибка при проверке администратора по конфигурации: {e}")
    
    # Если не найден в конфигурации, используем автоматическое определение
    return await is_user_admin_in_update(update, context)

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

