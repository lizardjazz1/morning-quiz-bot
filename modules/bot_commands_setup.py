"""
Модуль для установки команд бота в Telegram Bot API.
Отвечает за регистрацию всех команд бота для различных скоупов.
"""

import logging
from typing import TYPE_CHECKING

from telegram import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllChatAdministrators,
)

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
        
        # Админские команды
        BotCommand(app_config.commands.admin_settings, "⚙️ Настройки бота (админ)"),
        BotCommand(app_config.commands.reset_categories_stats, "🔄 Сброс статистики категорий (админ)"),
        BotCommand(app_config.commands.chat_stats, "📊 Статистика викторин (админ)"),
        BotCommand("scheduler_status", "📅 Статус планировщика (админ)"),
        BotCommand("maintenance", "🔧 Режим обслуживания (админ)"),
        
        # Команды бэкапов
        BotCommand("backup", "💾 Создать бэкап (админ)"),
        BotCommand("backups", "📋 Список бэкапов (админ)"),
        BotCommand("restore", "🔄 Восстановить из бэкапа (админ)"),
        BotCommand("deletebackup", "🗑️ Удалить бэкап (админ)"),
        BotCommand("backupstats", "📊 Статистика бэкапов (админ)"),
    ]
    
    try:
        # Устанавливаем команды по умолчанию
        await application.bot.set_my_commands(bot_commands)
        # Приватные чаты
        await application.bot.set_my_commands(
            bot_commands,
            scope=BotCommandScopeAllPrivateChats()
        )
        # Группы и супергруппы
        await application.bot.set_my_commands(
            bot_commands,
            scope=BotCommandScopeAllGroupChats()
        )
        # Администраторские чаты
        await application.bot.set_my_commands(
            bot_commands,
            scope=BotCommandScopeAllChatAdministrators()
        )
        logger.info(f"✅ Команды бота успешно установлены для всех скоупов ({len(bot_commands)} команд).")
    except Exception as e_set_cmd:
        logger.error(f"❌ Не удалось установить команды бота: {e_set_cmd}", exc_info=True)


