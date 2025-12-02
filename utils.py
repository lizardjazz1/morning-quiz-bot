#utils.py
import html
from typing import List, Dict, Any, Optional, Callable, Coroutine, Union
from datetime import datetime, timedelta, timezone
from collections import OrderedDict
from modules.logger_config import get_logger

from telegram import Update, User as TelegramUser
from telegram.ext import ContextTypes, JobQueue
from telegram.constants import ChatMemberStatus

import json
from pathlib import Path

logger = get_logger(__name__)

def get_current_utc_time() -> datetime:
    return datetime.now(timezone.utc)

def get_username_or_firstname(user: Optional[TelegramUser]) -> str:
    if user:
        # ИСПРАВЛЕНО: Приоритет у first_name, username только как fallback
        if user.first_name:
            return user.first_name
        elif user.username:
            return f"@{user.username}"
        else:
            return f"User {user.id}"
    return "Неизвестный пользователь"

def get_mention_html(user_id: int, name: str) -> str:
    escaped_name = html.escape(name)
    return f'<a href="tg://user?id={user_id}">{escaped_name}</a>'

# КЭШИРОВАННАЯ ТАБЛИЦА ЗАМЕН для быстрой работы escape_markdown_v2
_MARKDOWN_V2_ESCAPE_TABLE = str.maketrans({
    '_': '\\_', '*': '\\*', '[': '\\[', ']': '\\]', 
    '(': '\\(', ')': '\\)', '~': '\\~', '`': '\\`',
    '>': '\\>', '#': '\\#', '+': '\\+', '-': '\\-',
    '=': '\\=', '|': '\\|', '{': '\\{', '}': '\\}',
    '.': '\\.', '!': '\\!'
})

class LRUCache:
    """
    LRU (Least Recently Used) Cache implementation using OrderedDict
    """

    def __init__(self, max_size: int = 1000):
        self.cache = OrderedDict()
        self.max_size = max_size

    def get(self, key: str) -> Optional[str]:
        """Get value from cache, move to end if exists"""
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def put(self, key: str, value: str) -> None:
        """Put value in cache with LRU eviction"""
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            if len(self.cache) >= self.max_size:
                self.cache.popitem(last=False)  # Remove oldest (LRU)
        self.cache[key] = value

    def clear(self) -> None:
        """Clear all cache entries"""
        self.cache.clear()

    def __len__(self) -> int:
        return len(self.cache)

    def __contains__(self, key: str) -> bool:
        return key in self.cache

# КЭШ для часто используемых строк (ускоряет работу кнопок и меню)
# Инициализируем базовым размером, потом можно будет перенастроить
_MARKDOWN_V2_CACHE = LRUCache(max_size=1000)

# ПРЕДВАРИТЕЛЬНОЕ ЭКРАНИРОВАНИЕ часто используемых строк для быстрой работы кнопок
_COMMON_STRINGS = [
    "Начать викторину", "Остановить викторину", "Настройки", "Рейтинг", "Помощь",
    "Категории", "Статистика", "Мои очки", "Глобальный рейтинг", "Админ. настройки чата",
    "Отмена", "Назад", "Сохранить", "Изменить", "Удалить", "Добавить", "Просмотр"
]

# Заполняем кэш предварительно экранированными строками
for common_string in _COMMON_STRINGS:
    escaped = common_string.translate(_MARKDOWN_V2_ESCAPE_TABLE)
    _MARKDOWN_V2_CACHE.put(common_string, escaped)

def escape_markdown_v2(text: str) -> str:
    """
    Быстрое экранирование текста для Markdown V2 с кэшированием
    
    Args:
        text: Текст для экранирования
        
    Returns:
        Экранированный текст для Markdown V2
        
    Raises:
        ValueError: Если text is None
    """
    if text is None:
        raise ValueError("text не может быть None")
    
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception as e: 
            logger.warning(f"Не удалось преобразовать в строку для escape_markdown_v2: {type(text)}, ошибка: {e}")
            return ""
    
    if not text:  # Пустая строка
        return text
    
    # КЭШИРОВАНИЕ: Проверяем кэш для часто используемых строк
    cached_result = _MARKDOWN_V2_CACHE.get(text)
    if cached_result is not None:
        return cached_result

    # ИСПОЛЬЗУЕМ КЭШИРОВАННУЮ ТАБЛИЦУ для максимальной скорости
    result = text.translate(_MARKDOWN_V2_ESCAPE_TABLE)

    # КЭШИРОВАНИЕ: Сохраняем результат в кэш с LRU eviction
    _MARKDOWN_V2_CACHE.put(text, result)
    
    return result

# Centralized alias to emphasize intent when preparing text for MarkdownV2
# Use this in new code to standardize escaping across the project
def safe_md(text: str) -> str:
    return escape_markdown_v2(text)

def escape_markdown_v2_batch(texts: List[str]) -> List[str]:
    """
    Массовое экранирование списка строк для Markdown V2
    
    Args:
        texts: Список строк для экранирования
        
    Returns:
        Список экранированных строк
        
    Note:
        Быстрее чем вызов escape_markdown_v2 для каждой строки отдельно
    """
    if not texts:
        return texts
    
    # Фильтруем None и пустые строки
    valid_texts = [text for text in texts if text is not None and text]
    
    if not valid_texts:
        return texts
    
    # Используем одну операцию translate для всех строк
    return [text.translate(_MARKDOWN_V2_ESCAPE_TABLE) for text in valid_texts]

def initialize_markdown_cache(cache_size: int = 1000) -> None:
    """
    Перенастраивает LRU кэш для markdown с заданным размером

    Args:
        cache_size: Максимальный размер кэша
    """
    global _MARKDOWN_V2_CACHE
    old_cache = _MARKDOWN_V2_CACHE

    # Создаем новый кэш с новым размером
    _MARKDOWN_V2_CACHE = LRUCache(max_size=cache_size)

    # Если был старый кэш, переносим данные которые влезут
    if old_cache is not None and hasattr(old_cache, 'cache'):
        # Переносим наиболее часто используемые элементы
        items_to_transfer = min(len(old_cache.cache), cache_size // 2)
        for i, (key, value) in enumerate(list(old_cache.cache.items())[:items_to_transfer]):
            _MARKDOWN_V2_CACHE.put(key, value)

    # Заполняем кэш предварительно экранированными строками
    for common_string in _COMMON_STRINGS:
        escaped = common_string.translate(_MARKDOWN_V2_ESCAPE_TABLE)
        _MARKDOWN_V2_CACHE.put(common_string, escaped)

    logger.debug(f"Кэш markdown перенастроен с размером {cache_size}")

def get_markdown_v2_cache_stats() -> Dict[str, Any]:
    """
    Получает статистику кэша escape_markdown_v2

    Returns:
        Словарь со статистикой кэша
    """
    if _MARKDOWN_V2_CACHE is None:
        return {"error": "Cache not initialized"}
    return {
        "cache_size": len(_MARKDOWN_V2_CACHE),
        "max_size": _MARKDOWN_V2_CACHE.max_size,
        "cache_usage_percent": (len(_MARKDOWN_V2_CACHE) / _MARKDOWN_V2_CACHE.max_size) * 100
    }

def clear_markdown_v2_cache() -> None:
    """
    Очищает кэш escape_markdown_v2

    Note:
        Полезно при тестировании или при нехватке памяти
    """
    _MARKDOWN_V2_CACHE.clear()
    # Восстанавливаем предварительно кэшированные строки
    for common_string in _COMMON_STRINGS:
        escaped = common_string.translate(_MARKDOWN_V2_ESCAPE_TABLE)
        _MARKDOWN_V2_CACHE.put(common_string, escaped)
    logger.debug("Кэш escape_markdown_v2 очищен и восстановлены базовые строки")

# ===== НОВЫЕ УДОБНЫЕ ФУНКЦИИ ДЛЯ РАБОТЫ С MARKDOWN =====

def md_bold(text: str) -> str:
    """Создает жирный текст в Markdown V2"""
    return f"**{escape_markdown_v2(text)}**"

def md_italic(text: str) -> str:
    """Создает курсивный текст в Markdown V2"""
    return f"*{escape_markdown_v2(text)}*"

def md_code(text: str) -> str:
    """Создает inline код в Markdown V2"""
    return f"`{escape_markdown_v2(text)}`"

def md_code_block(text: str, language: str = "") -> str:
    """Создает блок кода в Markdown V2"""
    escaped_text = escape_markdown_v2(text)
    if language:
        return f"```{language}\n{escaped_text}\n```"
    return f"```\n{escaped_text}\n```"

def md_link(text: str, url: str) -> str:
    """Создает ссылку в Markdown V2"""
    escaped_text = escape_markdown_v2(text)
    escaped_url = escape_markdown_v2(url)
    return f"[{escaped_text}]({escaped_url})"

def md_header(text: str, level: int = 1) -> str:
    """Создает заголовок в Markdown V2"""
    if not 1 <= level <= 6:
        level = 1
    hashes = "#" * level
    return f"{hashes} {escape_markdown_v2(text)}"

def md_list_item(text: str, level: int = 0) -> str:
    """Создает элемент списка в Markdown V2"""
    indent = "  " * level
    return f"{indent}- {escape_markdown_v2(text)}"

def md_quote(text: str) -> str:
    """Создает цитату в Markdown V2"""
    return f"> {escape_markdown_v2(text)}"

# ===== УДОБНЫЕ ШАБЛОНЫ ДЛЯ ЧАСТО ИСПОЛЬЗУЕМЫХ СТРОК =====

class MarkdownTemplates:
    """Шаблоны для часто используемых Markdown конструкций"""

    @staticmethod
    def command_help(command: str, description: str) -> str:
        """Шаблон для описания команды в справке"""
        return f"/{escape_markdown_v2(command)} \\- {escape_markdown_v2(description)}"

    @staticmethod
    def section_header(title: str, emoji: str = "") -> str:
        """Шаблон для заголовка секции"""
        emoji_part = f"{emoji} " if emoji else ""
        return f"*{escape_markdown_v2(f'{emoji_part}{title}')}*"

    @staticmethod
    def error_message(message: str) -> str:
        """Шаблон для сообщения об ошибке"""
        return f"❌ *{escape_markdown_v2('Ошибка')}*\\: {escape_markdown_v2(message)}"

    @staticmethod
    def success_message(message: str) -> str:
        """Шаблон для сообщения об успехе"""
        return f"✅ *{escape_markdown_v2('Успешно')}*\\: {escape_markdown_v2(message)}"

    @staticmethod
    def info_message(message: str) -> str:
        """Шаблон для информационного сообщения"""
        return f"ℹ️ *{escape_markdown_v2('Информация')}*\\: {escape_markdown_v2(message)}"

    @staticmethod
    def warning_message(message: str) -> str:
        """Шаблон для предупреждения"""
        return f"⚠️ *{escape_markdown_v2('Предупреждение')}*\\: {escape_markdown_v2(message)}"

    @staticmethod
    def user_mention(user_id: int, name: str) -> str:
        """Шаблон для упоминания пользователя"""
        return f"[{escape_markdown_v2(name)}](tg://user?id={user_id})"

# ===== УДОБНЫЕ АЛИАСЫ =====

# Создаем глобальный экземпляр шаблонов для удобства
md = MarkdownTemplates()

# Короткие алиасы для самых частых операций
bold = md_bold
italic = md_italic
code = md_code
link = md_link

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

