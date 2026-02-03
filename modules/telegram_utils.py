#!/usr/bin/env python3
"""
Безопасные утилиты для работы с Telegram API

Включает:
- Декоратор для безопасной отправки сообщений с retry
- Обработка длинных сообщений
- Единообразная обработка ошибок Telegram API
"""

import logging
import asyncio
from functools import wraps
from typing import Optional, Union, List, Callable, Any
from telegram import Bot, Message, Update
from telegram.error import (
    BadRequest, NetworkError, RetryAfter, 
    TimedOut, TelegramError
)
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

class TelegramMessageError(Exception):
    """Базовое исключение для ошибок отправки сообщений"""
    pass

class MessageTooLongError(TelegramMessageError):
    """Сообщение слишком длинное для Telegram"""
    pass

class UserBlockedError(TelegramMessageError):
    """Пользователь заблокировал бота"""
    pass

class ChatNotFoundError(TelegramMessageError):
    """Чат не найден"""
    pass

def safe_telegram_call(
    max_retries: int = 1,  # Уменьшено с 2 до 1 (всего 2 попытки) - сеть работает быстро
    base_delay: float = 0.1,  # Уменьшено с 0.2 - быстрый retry
    max_delay: float = 0.5,  # Уменьшено с 1.0 - быстрый retry
    exponential_base: float = 1.5  # База для экспоненциального backoff
):
    """
    Декоратор для безопасного вызова Telegram API с retry
    
    Args:
        max_retries: Максимальное количество попыток
        base_delay: Базовая задержка между попытками (секунды)
        max_delay: Максимальная задержка между попытками (секунды)
        exponential_base: База для экспоненциального backoff
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                    
                except RetryAfter as e:
                    # Telegram просит подождать
                    wait_time = e.retry_after
                    logger.warning(f"Telegram API просит подождать {wait_time} секунд (попытка {attempt + 1}/{max_retries + 1})")
                    await asyncio.sleep(wait_time)
                    last_exception = e
                    
                except (NetworkError, TimedOut) as e:
                    # Сетевые ошибки - пробуем снова
                    if attempt < max_retries:
                        delay = min(base_delay * (exponential_base ** attempt), max_delay)
                        logger.warning(f"Сетевая ошибка, повтор через {delay:.1f}с (попытка {attempt + 1}/{max_retries + 1}): {e}")
                        await asyncio.sleep(delay)
                        last_exception = e
                    else:
                        logger.error(f"Исчерпаны попытки после сетевых ошибок: {e}")
                        raise TelegramMessageError(f"Не удалось выполнить операцию после {max_retries + 1} попыток: {e}")
                        
                except TelegramError as e:
                    # Общие ошибки Telegram API
                    if "unauthorized" in str(e).lower() or "bot was blocked" in str(e).lower():
                        logger.error(f"Бот не авторизован или заблокирован: {e}")
                        raise TelegramMessageError(f"Проблема с авторизацией бота: {e}")
                    else:
                        logger.error(f"Ошибка Telegram API: {e}")
                        raise TelegramMessageError(f"Ошибка Telegram API: {e}")
                    
                except BadRequest as e:
                    # Ошибки запроса - не повторяем
                    error_message = str(e).lower()
                    
                    if "message to edit not found" in error_message:
                        logger.warning(f"Сообщение для редактирования не найдено: {e}")
                        raise TelegramMessageError("Сообщение для редактирования не найдено")
                        
                    elif "message can't be deleted" in error_message:
                        logger.warning(f"Сообщение не может быть удалено: {e}")
                        raise TelegramMessageError("Сообщение не может быть удалено")
                        
                    elif "chat not found" in error_message:
                        logger.warning(f"Чат не найден: {e}")
                        raise ChatNotFoundError(f"Чат не найден: {e}")
                        
                    elif "bot was blocked by the user" in error_message:
                        logger.info(f"Пользователь заблокировал бота: {e}")
                        raise UserBlockedError(f"Пользователь заблокировал бота: {e}")
                        
                    elif "message is too long" in error_message:
                        logger.warning(f"Сообщение слишком длинное: {e}")
                        raise MessageTooLongError(f"Сообщение слишком длинное для Telegram")
                        
                    else:
                        logger.error(f"Ошибка запроса Telegram API: {e}")
                        raise TelegramMessageError(f"Ошибка запроса: {e}")
                        
                except Exception as e:
                    # Неожиданные ошибки
                    logger.error(f"Неожиданная ошибка при вызове {func.__name__}: {e}", exc_info=True)
                    raise TelegramMessageError(f"Неожиданная ошибка: {e}")
            
            # Если дошли до сюда, значит все попытки исчерпаны
            if last_exception:
                raise TelegramMessageError(f"Операция не удалась после {max_retries + 1} попыток. Последняя ошибка: {last_exception}")
            
        return wrapper
    return decorator

@safe_telegram_call(max_retries=2, base_delay=0.1)
async def safe_send_message(
    bot: Bot,
    chat_id: Union[int, str],
    text: str,
    parse_mode: Optional[ParseMode] = None,
    **kwargs
) -> Message:
    """
    Безопасная отправка сообщения с автоматическим разбиением длинных текстов
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        text: Текст сообщения
        parse_mode: Режим парсинга (Markdown, HTML)
        **kwargs: Дополнительные параметры для send_message
        
    Returns:
        Message: Отправленное сообщение
        
    Raises:
        MessageTooLongError: Если текст слишком длинный даже после разбиения
        TelegramMessageError: При других ошибках Telegram API
    """
    # Максимальная длина сообщения для Telegram
    MAX_MESSAGE_LENGTH = 4096
    
    if len(text) <= MAX_MESSAGE_LENGTH:
        # Сообщение нормальной длины
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            **kwargs
        )
    
    # Разбиваем длинное сообщение
    logger.info(f"Сообщение слишком длинное ({len(text)} символов), разбиваю на части")
    
    # Простое разбиение по строкам
    lines = text.split('\n')
    current_part = ""
    parts = []
    
    for line in lines:
        if len(current_part) + len(line) + 1 <= MAX_MESSAGE_LENGTH:
            current_part += (line + '\n') if current_part else line
        else:
            if current_part:
                parts.append(current_part.strip())
            current_part = line
    
    if current_part:
        parts.append(current_part.strip())
    
    # Отправляем части
    messages = []
    for i, part in enumerate(parts):
        if len(part) > MAX_MESSAGE_LENGTH:
            # Если часть все еще слишком длинная, обрезаем
            part = part[:MAX_MESSAGE_LENGTH - 3] + "..."
            logger.warning(f"Часть {i+1} обрезана до {MAX_MESSAGE_LENGTH} символов")
        
        message = await bot.send_message(
            chat_id=chat_id,
            text=part,
            parse_mode=parse_mode,
            **kwargs
        )
        messages.append(message)
        
        # Убираем задержку для быстрой работы кнопок
        # if i < len(parts) - 1:
        #     await asyncio.sleep(0.1)
    
    logger.info(f"Длинное сообщение разбито на {len(parts)} частей")
    
    # Возвращаем первое сообщение (для совместимости)
    return messages[0]

@safe_telegram_call(max_retries=1, base_delay=0.1)
async def safe_edit_message(
    bot: Bot,
    chat_id: Union[int, str],
    message_id: int,
    text: str,
    parse_mode: Optional[ParseMode] = None,
    **kwargs
) -> Message:
    """
    Безопасное редактирование сообщения
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        message_id: ID сообщения для редактирования
        text: Новый текст
        parse_mode: Режим парсинга
        **kwargs: Дополнительные параметры
        
    Returns:
        Message: Отредактированное сообщение
    """
    return await bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        parse_mode=parse_mode,
        **kwargs
    )

@safe_telegram_call(max_retries=1, base_delay=0.1)
async def safe_delete_message(
    bot: Bot,
    chat_id: Union[int, str],
    message_id: int
) -> bool:
    """
    Безопасное удаление сообщения
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        message_id: ID сообщения для удаления
        
    Returns:
        bool: True если сообщение удалено, False если не найдено
    """
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except BadRequest as e:
        if "message to delete not found" in str(e).lower():
            logger.debug(f"Сообщение {message_id} уже удалено")
            return False
        raise

def format_error_message(error: Exception, context: str = "") -> str:
    """
    Форматирует сообщение об ошибке для пользователя
    
    Args:
        error: Исключение
        context: Контекст операции
        
    Returns:
        str: Понятное сообщение об ошибке
    """
    if isinstance(error, UserBlockedError):
        return "Пользователь заблокировал бота"
    elif isinstance(error, ChatNotFoundError):
        return "Чат не найден"
    elif isinstance(error, MessageTooLongError):
        return "Сообщение слишком длинное"
    elif isinstance(error, TelegramMessageError):
        return f"Ошибка Telegram: {str(error)}"
    else:
        return f"Произошла ошибка: {str(error)}"

# Экспортируем основные функции
__all__ = [
    'safe_telegram_call',
    'safe_send_message', 
    'safe_edit_message',
    'safe_delete_message',
    'format_error_message',
    'TelegramMessageError',
    'MessageTooLongError',
    'UserBlockedError',
    'ChatNotFoundError'
]
