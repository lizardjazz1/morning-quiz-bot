#!/usr/bin/env python3
"""
Централизованная конфигурация логирования для проекта

Включает:
- Настройку уровней логирования
- Форматирование сообщений
- Ротацию логов
- Единообразное логирование для всех модулей
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

class ColoredFormatter(logging.Formatter):
    """Форматтер с цветным выводом для консоли"""
    
    # ANSI цветовые коды
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }
    
    def format(self, record):
        # Добавляем цвет к уровню логирования
        if record.levelname in self.COLORS:
            record.levelname = f"{self.COLORS[record.levelname]}{record.levelname}{self.COLORS['RESET']}"
        
        # Добавляем цвет к имени модуля
        if hasattr(record, 'module'):
            record.module = f"\033[34m{record.module}\033[0m"
        
        return super().format(record)

class StructuredFormatter(logging.Formatter):
    """Структурированный форматтер для файлов логов"""
    
    def format(self, record):
        # Добавляем дополнительные поля
        record.timestamp = datetime.fromtimestamp(record.created).isoformat()
        record.process_name = f"PID:{record.process}"
        record.thread_name = f"Thread:{record.threadName}"
        
        # Форматируем сообщение
        log_entry = {
            'timestamp': record.timestamp,
            'level': record.levelname,
            'logger': record.name,
            'module': getattr(record, 'module', 'unknown'),
            'function': record.funcName,
            'line': record.lineno,
            'process': record.process_name,
            'thread': record.thread_name,
            'message': record.getMessage()
        }
        
        # Добавляем исключение, если есть
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        # Добавляем дополнительные поля
        if hasattr(record, 'user_id'):
            log_entry['user_id'] = record.user_id
        if hasattr(record, 'chat_id'):
            log_entry['chat_id'] = record.chat_id
        if hasattr(record, 'quiz_id'):
            log_entry['quiz_id'] = record.quiz_id
        
        return f"{log_entry['timestamp']} | {log_entry['level']:8} | {log_entry['logger']:20} | {log_entry['module']:15} | {log_entry['function']:20} | {log_entry['line']:3} | {log_entry['message']}"

def setup_logging(
    log_level: str = "INFO",
    log_dir: str = "logs",
    max_log_size: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
    console_output: bool = True,
    file_output: bool = True
) -> None:
    """
    Настраивает централизованное логирование для проекта
    
    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Директория для логов
        max_log_size: Максимальный размер файла лога в байтах
        backup_count: Количество файлов бэкапа
        console_output: Включить вывод в консоль
        file_output: Включить вывод в файл
    """
    
    # Создаем директорию для логов
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)
    
    # Получаем корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Очищаем существующие обработчики
    root_logger.handlers.clear()
    
    # Форматеры
    console_formatter = ColoredFormatter(
        '%(asctime)s | %(levelname)-8s | %(name)-20s | %(module)-15s | %(funcName)-20s | %(lineno)-3d | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    file_formatter = StructuredFormatter(
        '%(asctime)s | %(levelname)-8s | %(name)-20s | %(module)-15s | %(funcName)-20s | %(lineno)-3d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Консольный обработчик
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
    
    # Файловый обработчик с ротацией по времени
    if file_output:
        # Основной лог файл с датой
        main_log_file = log_path / f"bot_{datetime.now().strftime('%d.%m.%y')}.log"
        file_handler = logging.handlers.TimedRotatingFileHandler(
            main_log_file,
            when='midnight',
            interval=1,
            backupCount=3,  # Храним только 3 дня
            encoding='utf-8'
        )
        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
        
        # Лог ошибок с датой
        error_log_file = log_path / f"errors_{datetime.now().strftime('%d.%m.%y')}.log"
        error_handler = logging.handlers.TimedRotatingFileHandler(
            error_log_file,
            when='midnight',
            interval=1,
            backupCount=3,  # Храним только 3 дня
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter)
        root_logger.addHandler(error_handler)
        
        # Лог для отладки с датой (если уровень DEBUG)
        if log_level.upper() == "DEBUG":
            debug_log_file = log_path / f"debug_{datetime.now().strftime('%d.%m.%y')}.log"
            debug_handler = logging.handlers.TimedRotatingFileHandler(
                debug_log_file,
                when='midnight',
                interval=1,
                backupCount=3,  # Храним только 3 дня
                encoding='utf-8'
            )
            debug_handler.setLevel(logging.DEBUG)
            debug_handler.setFormatter(file_formatter)
            root_logger.addHandler(debug_handler)
    
    # Настраиваем логирование для сторонних библиотек
    logging.getLogger('telegram').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    
    # Логируем успешную настройку
    logger = logging.getLogger(__name__)
    logger.info(f"Логирование настроено: уровень={log_level}, консоль={console_output}, файл={file_output}")
    logger.info(f"Директория логов: {log_path.absolute()}")

def get_logger(name: str) -> logging.Logger:
    """
    Получает логгер с заданным именем
    
    Args:
        name: Имя логгера (обычно __name__)
        
    Returns:
        Настроенный логгер
    """
    return logging.getLogger(name)

def log_with_context(
    logger: logging.Logger,
    level: str,
    message: str,
    user_id: Optional[int] = None,
    chat_id: Optional[int] = None,
    quiz_id: Optional[str] = None,
    **kwargs
) -> None:
    """
    Логирует сообщение с дополнительным контекстом
    
    Args:
        logger: Логгер для записи
        level: Уровень логирования
        message: Сообщение для логирования
        user_id: ID пользователя (опционально)
        chat_id: ID чата (опционально)
        quiz_id: ID викторины (опционально)
        **kwargs: Дополнительные поля контекста
    """
    
    # Создаем запись с дополнительными полями
    extra = {}
    if user_id is not None:
        extra['user_id'] = user_id
    if chat_id is not None:
        extra['chat_id'] = chat_id
    if quiz_id is not None:
        extra['quiz_id'] = quiz_id
    
    # Добавляем дополнительные поля
    extra.update(kwargs)
    
    # Логируем с контекстом
    log_method = getattr(logger, level.lower())
    if extra:
        log_method(message, extra=extra)
    else:
        log_method(message)

def log_quiz_event(
    logger: logging.Logger,
    event_type: str,
    message: str,
    chat_id: int,
    user_id: Optional[int] = None,
    quiz_id: Optional[str] = None,
    **kwargs
) -> None:
    """
    Специализированная функция для логирования событий викторины
    
    Args:
        logger: Логгер для записи
        event_type: Тип события (start, answer, finish, error)
        message: Сообщение для логирования
        chat_id: ID чата
        user_id: ID пользователя (опционально)
        quiz_id: ID викторины (опционально)
        **kwargs: Дополнительные поля
    """
    
    # Форматируем сообщение с типом события
    formatted_message = f"[QUIZ:{event_type.upper()}] {message}"
    
    # Логируем с контекстом викторины
    log_with_context(
        logger=logger,
        level='info',
        message=formatted_message,
        user_id=user_id,
        chat_id=chat_id,
        quiz_id=quiz_id,
        event_type=event_type,
        **kwargs
    )

def log_user_action(
    logger: logging.Logger,
    action: str,
    message: str,
    user_id: int,
    chat_id: Optional[int] = None,
    **kwargs
) -> None:
    """
    Специализированная функция для логирования действий пользователей
    
    Args:
        logger: Логгер для записи
        action: Тип действия (command, poll_answer, achievement)
        message: Сообщение для логирования
        user_id: ID пользователя
        chat_id: ID чата (опционально)
        **kwargs: Дополнительные поля
    """
    
    # Форматируем сообщение с типом действия
    formatted_message = f"[USER:{action.upper()}] {message}"
    
    # Логируем с контекстом пользователя
    log_with_context(
        logger=logger,
        level='info',
        message=formatted_message,
        user_id=user_id,
        chat_id=chat_id,
        action_type=action,
        **kwargs
    )

# Экспортируем основные функции
__all__ = [
    'setup_logging',
    'get_logger',
    'log_with_context',
    'log_quiz_event',
    'log_user_action',
    'ColoredFormatter',
    'StructuredFormatter'
]
