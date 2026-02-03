"""
Модуль для установки команд бота в Telegram Bot API.
Отвечает за регистрацию всех команд бота для различных скоупов.
"""

import logging
import asyncio
from typing import TYPE_CHECKING

from telegram import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllChatAdministrators,
)
from telegram.error import TimedOut, NetworkError

if TYPE_CHECKING:
    from telegram.ext import Application
    from app_config import AppConfig

logger = logging.getLogger(__name__)


async def setup_bot_commands(application: "Application", app_config: "AppConfig") -> None:
    """
    Устанавливает команды бота для всех скоупов.
    Должна вызываться после регистрации всех обработчиков, но до запуска бота.
    
    Args:
        application: Экземпляр Application из python-telegram-bot
        app_config: Конфигурация приложения с настройками команд
    """
    # Команды для обычных пользователей и админов чатов
    bot_commands = [
        # Основные команды
        BotCommand(app_config.commands.start, "🚀 Начать работу с ботом"),
        BotCommand(app_config.commands.help, "ℹ️ Помощь по командам"),
        BotCommand(app_config.commands.quiz, "🏁 Начать викторину"),
        BotCommand(app_config.commands.categories, "📚 Список категорий"),
        BotCommand(app_config.commands.category_stats, "📊 Статистика категорий"),
        BotCommand(app_config.commands.chatcategories, "🎲 Очередь категорий с весами"),
        BotCommand(app_config.commands.top, "🏆 Показать рейтинг"),
        BotCommand(app_config.commands.global_top, "🏆 Показать глобальный рейтинг"),
        BotCommand(app_config.commands.mystats, "📊 Показать вашу статистику"),
        BotCommand(app_config.commands.stop_quiz, "🛑 Остановить текущую викторину"),
        BotCommand(app_config.commands.cancel, "↩️ Отменить текущее действие"),
        
        # Фото-викторина
        BotCommand("photo_quiz", "🖼️ Фото-викторина"),
        BotCommand("stop_photo_quiz", "🛑 Остановить фото-викторину"),
        BotCommand("photo_quiz_help", "ℹ️ Помощь по фото-викторине"),
        
        # Админские команды (безопасные для админов чатов)
        BotCommand(app_config.commands.admin_settings, "⚙️ Настройки бота (админ)"),
        BotCommand(app_config.commands.reset_categories_stats, "🔄 Сброс статистики категорий (админ)"),
        BotCommand(app_config.commands.chat_stats, "📊 Статистика викторин (админ)"),
        BotCommand("scheduler_status", "📅 Статус планировщика (админ)"),
    ]
    
    # Команды ТОЛЬКО для суперадминов (не показываются в меню)
    # Эти команды работают, но не отображаются в списке команд
    # Доступ к ним контролируется через проверку прав в обработчиках
    superadmin_commands = [
        # BotCommand("maintenance", "🔧 Режим обслуживания"),
        # BotCommand("backup", "💾 Создать бэкап"),
        # BotCommand("backups", "📋 Список бэкапов"),
        # BotCommand("restore", "🔄 Восстановить из бэкапа"),
        # BotCommand("deletebackup", "🗑️ Удалить бэкап"),
        # BotCommand("backupstats", "📊 Статистика бэкапов"),
    ]
    
    # Функция для установки команд с retry
    async def set_commands_with_retry(scope=None, max_retries=3):
        """Устанавливает команды с повторными попытками при таймаутах"""
        for attempt in range(max_retries):
            try:
                if scope:
                    await application.bot.set_my_commands(bot_commands, scope=scope)
                else:
                    await application.bot.set_my_commands(bot_commands)
                return True
            except (TimedOut, NetworkError) as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # 2, 4, 6 секунд
                    logger.warning(f"Таймаут при установке команд (попытка {attempt + 1}/{max_retries}), повтор через {wait_time}с: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Не удалось установить команды после {max_retries} попыток: {e}")
                    return False
            except Exception as e:
                logger.error(f"Ошибка при установке команд: {e}", exc_info=True)
                return False
        return False
    
    try:
        # Устанавливаем команды по умолчанию
        await set_commands_with_retry()
        # Приватные чаты
        await set_commands_with_retry(scope=BotCommandScopeAllPrivateChats())
        # Группы и супергруппы
        await set_commands_with_retry(scope=BotCommandScopeAllGroupChats())
        # Администраторские чаты
        await set_commands_with_retry(scope=BotCommandScopeAllChatAdministrators())
        logger.info(f"✅ Команды бота успешно установлены для всех скоупов ({len(bot_commands)} команд).")
    except Exception as e_set_cmd:
        logger.error(f"❌ Не удалось установить команды бота: {e_set_cmd}", exc_info=True)


