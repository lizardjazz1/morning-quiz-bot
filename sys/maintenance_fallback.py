#!/usr/bin/env python3
"""
Maintenance Fallback Bot - простой бот для режима обслуживания
Работает только когда включен режим обслуживания через simple_switcher.py
"""

import os
import json
import asyncio
import logging
import nest_asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from telegram import Update, CallbackQuery
from telegram.ext import Application, MessageHandler, ContextTypes, filters, CommandHandler, CallbackQueryHandler
from telegram.constants import ParseMode
from telegram.error import TimedOut, NetworkError, RetryAfter

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class MaintenanceFallbackBot:
    """Простой fallback бот для режима обслуживания"""

    def __init__(self, token: str, data_dir: str = "data"):
        self.token = token
        self.data_dir = Path(data_dir)
        self.mode_file = self.data_dir / "bot_mode.json"
        self.maintenance_file = Path(__file__).parent / "config" / "maintenance_status.json"
        self.application: Optional[Application] = None

    def get_current_mode(self) -> str:
        """Получает текущий режим работы"""
        # Сначала проверяем maintenance_status.json (актуальный файл, который читает основной бот)
        if self.maintenance_file.exists():
            try:
                with open(self.maintenance_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get("maintenance_mode", False):
                        return "maintenance"
            except Exception as e:
                logger.warning(f"Ошибка чтения maintenance_status.json: {e}")
        
        # Если maintenance_status.json не указывает на maintenance, проверяем bot_mode.json
        if self.mode_file.exists():
            try:
                with open(self.mode_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("mode", "main")
            except Exception as e:
                logger.warning(f"Ошибка чтения bot_mode.json: {e}")
        
        return "main"

    def should_run_fallback(self) -> bool:
        """Проверяет, должен ли работать fallback бот"""
        return self.get_current_mode() == "maintenance"

    def get_maintenance_message(self) -> str:
        """Получает сообщение об обслуживании с причиной"""
        try:
            if self.maintenance_file.exists():
                with open(self.maintenance_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    reason = data.get("reason", "Техническое обслуживание")
                    start_time_str = data.get("start_time", "")
                    
                    if start_time_str:
                        try:
                            from datetime import timezone
                            start_time = datetime.fromisoformat(start_time_str)
                            # ИСПРАВЛЕНИЕ: Нормализуем timezone для корректного сравнения
                            if start_time.tzinfo is None:
                                start_time = start_time.replace(tzinfo=timezone.utc)
                            current_time = datetime.now(timezone.utc)
                            time_diff = current_time - start_time
                            hours = int(time_diff.total_seconds() // 3600)
                            minutes = int((time_diff.total_seconds() % 3600) // 60)
                            
                            duration_text = ""
                            if hours > 0:
                                duration_text = f"{hours} ч. {minutes} мин."
                            else:
                                duration_text = f"{minutes} мин."
                            
                            return f"""🔧 Я сейчас на техническом обслуживании!

Причина: {reason}
⏱️ Длительность: {duration_text}

Сейчас обновляю базу знаний и улучшаю вопросы для викторин. Скоро вернусь и задам вам новые интересные вопросы! 💡
Приносим извинения за временные неудобства."""
                        except Exception:
                            pass
                    
                    return f"""🔧 Я сейчас на техническом обслуживании!

Причина: {reason}

Сейчас обновляю базу знаний и улучшаю вопросы для викторин. Скоро вернусь и задам вам новые интересные вопросы! 💡
Приносим извинения за временные неудобства."""
            
            # Фоллбек, если файл не найден
            logger.warning(f"Файл maintenance_status.json не найден: {self.maintenance_file}")
            return """🔧 Я сейчас на техническом обслуживании!

Сейчас обновляю базу знаний и улучшаю вопросы для викторин. Скоро вернусь и задам вам новые интересные вопросы! 💡
Приносим извинения за временные неудобства."""
        except Exception as e:
            logger.error(f"Ошибка при получении сообщения об обслуживании: {e}")
            return """🔧 Я сейчас на техническом обслуживании!

Сейчас обновляю базу знаний и улучшаю вопросы для викторин. Скоро вернусь и задам вам новые интересные вопросы! 💡
Приносим извинения за временные неудобства."""

    async def fallback_command_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик всех команд в режиме обслуживания"""
        if not update.message or not update.effective_chat:
            return
        
        user_name = update.effective_user.first_name if update.effective_user else "Пользователь"
        
        try:
            current_mode = self.get_current_mode()
            
            if current_mode == "maintenance":
                message_text = self.get_maintenance_message()
                
                await update.message.reply_text(
                    message_text,
                    parse_mode=None
                )
                
                logger.info(f"[SENT] Отправлено сообщение об обслуживании на команду '{command_name}' пользователю {user_name}")
            else:
                logger.warning(f"[WARN] Режим обслуживания отключен, но fallback-бот все еще работает. Игнорируем команду '{command_name}' от {user_name}")
        except Exception as e:
            logger.error(f"[ERROR] Ошибка при обработке команды: {e}", exc_info=True)
            # Не отправляем дополнительное сообщение при ошибке, чтобы не спамить пользователя
    
    async def fallback_callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик callback_query (кнопки) в режиме обслуживания"""
        query = update.callback_query
        if not query:
            return
        
        try:
            await query.answer()  # Подтверждаем получение callback
            
            current_mode = self.get_current_mode()
            
            if current_mode == "maintenance":
                message_text = self.get_maintenance_message()
                
                await query.message.reply_text(
                    message_text,
                    parse_mode=None
                )
                
                logger.info(f"[SENT] Отправлено сообщение об обслуживании на callback пользователю {query.from_user.first_name if query.from_user else 'Unknown'}")
            else:
                logger.info(f"[INFO] Режим обслуживания отключен, игнорируем callback")
        except Exception as e:
            logger.error(f"[ERROR] Ошибка при обработке callback: {e}")
            try:
                await query.answer("🔧 Бот на техническом обслуживании", show_alert=True)
            except Exception:
                pass

    def create_application(self) -> Application:
        """Создает Telegram приложение"""
        application = Application.builder().token(self.token).build()

        # Обработчик ВСЕХ команд (перехватывает любую команду, включая /start, /quiz, /help и т.д.)
        # Используем MessageHandler с фильтром COMMAND для перехвата всех команд
        application.add_handler(MessageHandler(filters.COMMAND, self.fallback_command_handler))
        
        # Обработчик callback_query (кнопки)
        application.add_handler(CallbackQueryHandler(self.fallback_callback_handler))
        
        # Обработчик всех остальных сообщений (текст, фото, документы и т.д.)
        # Команды уже обработаны выше, этот обработчик сработает только для обычных сообщений (не команд)
        application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, self.fallback_message_handler))

        return application

    def escape_markdown_v2(self, text: str) -> str:
        """Экранирует специальные символы для MarkdownV2"""
        if not text:
            return ""
        # Экранируем только специальные символы форматирования MarkdownV2
        escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '!']
        for char in escape_chars:
            text = text.replace(char, f'\\{char}')
        return text

    async def fallback_message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик всех сообщений в режиме обслуживания"""
        if not update.message or not update.effective_chat:
            return

        user_name = update.effective_user.first_name if update.effective_user else "Пользователь"

        try:
            # Проверяем текущий режим в реальном времени
            current_mode = self.get_current_mode()

            if current_mode == "maintenance":
                # Получаем сообщение об обслуживании с причиной
                message_text = self.get_maintenance_message()

                await update.message.reply_text(
                    message_text,
                    parse_mode=None
                )

                logger.info(f"[SENT] Отправлено сообщение об обслуживании пользователю {user_name}")
            else:
                # Режим обслуживания отключен, игнорируем сообщения
                logger.info(f"[INFO] Режим обслуживания отключен, игнорируем сообщение от {user_name}")

        except Exception as e:
            logger.error(f"[ERROR] Ошибка при обработке сообщения '{message_preview}': {e}", exc_info=True)
            # Не отправляем дополнительное сообщение при ошибке, чтобы не спамить пользователя

    async def run(self):
        """Запускает fallback бот"""
        logger.info("🚀 Maintenance Fallback Bot запущен")
        
        # Проверяем режим обслуживания при запуске
        current_mode = self.get_current_mode()
        logger.info(f"📋 Текущий режим при запуске: {current_mode}")
        
        if current_mode != "maintenance":
            logger.warning(f"⚠️ ВНИМАНИЕ: Fallback-бот запущен, но режим обслуживания не активен (режим: {current_mode})")
            logger.warning(f"⚠️ Fallback-бот будет отвечать только если режим обслуживания будет включен")

        # Создаем приложение
        self.application = self.create_application()

        logger.info("📡 Запускаем polling для обработки сообщений...")

        # Запускаем polling с оптимальными настройками и обработкой ошибок
        max_retries = 10
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                await self.application.run_polling(
                    poll_interval=5.0,  # Опрашиваем реже (каждые 5 секунд)
                    timeout=20,         # Увеличиваем таймаут для более стабильной работы
                    drop_pending_updates=True,
                    allowed_updates=["message", "callback_query"],
                    close_loop=False  # Не закрываем event loop при ошибках
                )
                # Если polling завершился без ошибок, выходим
                break
            except Exception as e:
                retry_count += 1
                error_type = type(e).__name__
                logger.warning(f"[WARN] Ошибка в polling fallback бота ({retry_count}/{max_retries}): {error_type}: {e}")
                
                # Для TimedOut и NetworkError ошибок ждем меньше и продолжаем
                if isinstance(e, (TimedOut, NetworkError)):
                    logger.info(f"[INFO] Проблема с подключением к Telegram API ({error_type}), повторная попытка через 5 секунд...")
                    await asyncio.sleep(5)
                    continue
                
                # Для RetryAfter ошибок ждем указанное время
                if isinstance(e, RetryAfter):
                    wait_time = e.retry_after
                    logger.info(f"[INFO] Telegram API просит подождать {wait_time} секунд...")
                    await asyncio.sleep(wait_time)
                    continue
                
                # Для других ошибок ждем дольше
                if retry_count < max_retries:
                    wait_time = min(10 * retry_count, 60)  # Максимум 60 секунд
                    logger.info(f"[INFO] Повторная попытка через {wait_time} секунд...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"[ERROR] Достигнуто максимальное количество попыток. Останавливаем fallback-бота.")
                    return


def main():
    """Главная функция"""
    # Включаем поддержку вложенных event loops
    nest_asyncio.apply()

    # Получаем токен из переменной окружения или из .env файла
    token = os.getenv('BOT_TOKEN')
    
    # Если не нашли в переменной окружения, пробуем загрузить из .env
    if not token:
        try:
            from dotenv import load_dotenv
            load_dotenv()
            token = os.getenv('BOT_TOKEN')
        except ImportError:
            pass
    
    if not token:
        logger.error("Не найден токен бота! Установите BOT_TOKEN в переменной окружения или .env файле")
        return

    # Создаем бота
    bot = MaintenanceFallbackBot(token=token)

    # Запускаем
    asyncio.run(bot.run())


if __name__ == "__main__":
    main()
