# bot/utils.py
import logging
from typing import List, Dict, Any, Optional, Callable, Coroutine
from datetime import datetime, timedelta, timezone

from telegram import BotCommand, Update
from telegram.ext import ContextTypes, JobQueue

from .app_config import CommandConfig # Для типизации

logger = logging.getLogger(__name__)

def load_commands_from_config(command_config: CommandConfig) -> List[BotCommand]:
    """
    Загружает список команд бота из объекта конфигурации команд.
    """
    commands = [
        BotCommand(command_config.start, "🚀 Запустить бота / Показать приветствие"),
        BotCommand(command_config.help, "❓ Помощь по командам бота"),
        BotCommand(command_config.quiz, "🎮 Начать новую викторину (с настройками)"),
        BotCommand(command_config.categories, "📚 Показать список категорий вопросов"),
        BotCommand(command_config.top, "🏆 Показать топ игроков в этом чате"),
        BotCommand(command_config.global_top, "🌍 Показать глобальный топ игроков"),
        BotCommand(command_config.mystats, "📊 Показать мою статистику"),
        BotCommand(command_config.stop_quiz, "🛑 Остановить текущую викторину в чате (для админов/инициатора)"),
        BotCommand(command_config.cancel, "❌ Отменить текущее действие/диалог"),
    ]

    admin_commands = [
        BotCommand(command_config.set_quiz_type, "⚙️ [Админ] Установить тип викторины по умолчанию для чата"),
        BotCommand(command_config.set_quiz_questions, "⚙️ [Админ] Установить кол-во вопросов для викторины по умолчанию"),
        BotCommand(command_config.set_quiz_interval, "⚙️ [Админ] Установить интервал для ежедневной викторины"),
        BotCommand(command_config.set_quiz_open_period, "⚙️ [Админ] Установить время на ответ для викторины"),
        BotCommand(command_config.add_chat_category, "⚙️ [Админ] Добавить категорию по умолчанию для чата"),
        BotCommand(command_config.remove_chat_category, "⚙️ [Админ] Удалить категорию по умолчанию для чата"),
        BotCommand(command_config.list_chat_categories, "⚙️ [Админ] Показать категории по умолчанию для чата"),
        BotCommand(command_config.exclude_chat_category, "⚙️ [Админ] Исключить категорию для чата"),
        BotCommand(command_config.unexclude_chat_category, "⚙️ [Админ] Вернуть исключенную категорию для чата"),
        BotCommand(command_config.list_excluded_categories, "⚙️ [Админ] Показать исключенные категории для чата"),
        BotCommand(command_config.set_daily_quiz_time, "⏰ [Админ] Установить время ежедневной викторины"),
        BotCommand(command_config.enable_daily_quiz, "🗓️ [Админ] Включить ежедневную викторину"),
        BotCommand(command_config.disable_daily_quiz, "🗓️ [Админ] Отключить ежедневную викторину"),
        BotCommand(command_config.get_chat_settings, "⚙️ [Админ] Показать текущие настройки чата"),
        # BotCommand(command_config.cleanup_messages, "🧹 [Админ] Настроить удаление старых сообщений"), # Если будет
    ]
    # Для простоты пока объединим, но можно будет разделять для set_my_commands по scope
    all_commands = commands + admin_commands
    logger.info(f"Загружено {len(all_commands)} команд для бота.")
    return all_commands


def get_username_or_firstname(update: Update) -> str:
    """Возвращает username пользователя, если есть, иначе first_name."""
    if update.effective_user:
        if update.effective_user.username:
            return f"@{update.effective_user.username}"
        return update.effective_user.first_name
    return "Неизвестный пользователь"

def parse_quiz_command_args(args: List[str]) -> Dict[str, Any]:
    """
    Парсит аргументы команды /quiz.
    Пример: /quiz 10 Наука Технологии announce
    """
    parsed_args = {
        "num_questions": None,
        "categories": [],
        "announce": False,
        "mode": None # single, session (пока не используется напрямую из команды)
    }
    
    remaining_args = []

    for arg in args:
        arg_lower = arg.lower()
        if arg_lower == "announce":
            parsed_args["announce"] = True
        elif arg_lower in ["single", "session", "быстрый", "сессия"]: # Варианты для режима
             if arg_lower in ["single", "быстрый"]:
                 parsed_args["mode"] = "single"
             elif arg_lower in ["session", "сессия"]:
                 parsed_args["mode"] = "session"
        elif arg.isdigit():
            if parsed_args["num_questions"] is None: # Первое число считаем количеством вопросов
                parsed_args["num_questions"] = int(arg)
            else: # Если число уже было, это может быть частью названия категории
                remaining_args.append(arg)
        else:
            remaining_args.append(arg)
    
    # Оставшиеся аргументы считаем категориями, объединяя многословные
    current_category = ""
    for part in remaining_args:
        if current_category:
            current_category += " " + part
        else:
            current_category = part
        # Здесь можно добавить логику проверки, является ли current_category полной категорией,
        # но для простоты пока считаем, что категории разделены пробелами или другими ключами
        # и если нет явных ключей, то все оставшееся - это категории.
        # Для более сложного парсинга категорий с пробелами, возможно, понадобится
        # передавать список доступных категорий и проверять по нему.
        # Пока просто добавляем все, что не распознано как число или флаг.
    if remaining_args:
         # Простой способ: все оставшиеся аргументы (не числа и не "announce") - это потенциальные категории.
         # Пользователь должен будет вводить категории через запятую или передавать список известных категорий для более точного парсинга.
         # Для текущей реализации, если категории содержат пробелы, их нужно передавать как один аргумент в кавычках
         # или мы можем просто считать каждый оставшийся аргумент отдельной категорией.
         # Пока что, если есть оставшиеся аргументы, считаем, что это список категорий.
         # Чтобы корректно парсить "История России", пользователь должен был бы ввести `/quiz "История России"`
         # или мы должны иметь список категорий и пытаться найти совпадения.
         # Для простоты, сейчас каждый remaining_arg будет отдельной категорией.
        parsed_args["categories"] = [arg for arg in remaining_args if not arg.isdigit() and arg.lower() != "announce"]


    logger.debug(f"Аргументы команды /quiz: {args}, распарсены в: {parsed_args}")
    return parsed_args


def get_mention_html(user_id: int, name: str) -> str:
    """Создает HTML-разметку для упоминания пользователя."""
    return f'<a href="tg://user?id={user_id}">{name}</a>'


async def SСHEDULE_JOB_UNIQUIE(
    job_queue: JobQueue,
    job_name: str,
    callback: Callable[..., Coroutine[Any, Any, None]],
    interval: timedelta | float,
    first: Optional[timedelta | float | datetime] = None,
    last: Optional[timedelta | float | datetime] = None,
    data: Any = None,
    user_id: Optional[int] = None,
    chat_id: Optional[int] = None,
    enabled: Optional[bool] = True,
) -> None:
    """
    Планирует задачу, удаляя предыдущую с тем же именем, если она существует.
    """
    # Удаляем существующие задачи с таким же именем
    # `get_jobs_by_name` возвращает кортеж, поэтому нужно пройтись по нему.
    # В python-telegram-bot v20+ он возвращает tuple, а не list
    current_jobs = job_queue.get_jobs_by_name(job_name)
    if current_jobs:
        logger.info(f"Найдены существующие задачи с именем '{job_name}': {len(current_jobs)}. Удаляем...")
        for job in current_jobs:
            job.schedule_removal()
            logger.info(f"Задача '{job_name}' удалена.")
    else:
        logger.info(f"Задачи с именем '{job_name}' не найдены. Создаем новую.")

    # Планируем новую задачу
    job_queue.run_repeating(
        callback=callback,
        interval=interval,
        first=first,
        last=last,
        data=data,
        name=job_name,
        user_id=user_id,
        chat_id=chat_id,
        # enabled=enabled, # Параметр enabled убрали в v20, управление через schedule_removal
    )
    logger.info(f"Задача '{job_name}' запланирована с интервалом {interval}.")

def get_current_utc_time() -> datetime:
    """Возвращает текущее время в UTC."""
    return datetime.now(timezone.utc)

def format_timedelta(td: timedelta) -> str:
    """Форматирует timedelta в строку типа "1д 2ч 3м 4с" """
    total_seconds = int(td.total_seconds())
    days = total_seconds // (24 * 3600)
    total_seconds %= (24 * 3600)
    hours = total_seconds // 3600
    total_seconds %= 3600
    minutes = total_seconds // 60
    seconds = total_seconds % 60

    parts = []
    if days > 0:
        parts.append(f"{days}д")
    if hours > 0:
        parts.append(f"{hours}ч")
    if minutes > 0:
        parts.append(f"{minutes}м")
    if seconds > 0 or not parts: # Показать секунды, если это единственное или есть другие части
        parts.append(f"{seconds}с")
    
    return " ".join(parts) if parts else "0с"

def is_user_admin_in_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Проверяет, является ли пользователь, вызвавший команду, админом чата.
    Работает для групповых чатов. В личных чатах всегда False (или можно считать True).
    """
    if not update.effective_chat or not update.effective_user:
        return False
    if update.effective_chat.type == "private":
        return True # В личке с ботом пользователь всегда "админ" своих действий

    try:
        chat_member = context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        return chat_member.status in ["administrator", "creator"]
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса админа для пользователя {update.effective_user.id} в чате {update.effective_chat.id}: {e}")
        return False

