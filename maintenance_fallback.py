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

from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters
from telegram.constants import ParseMode

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
        self.application: Optional[Application] = None

    def get_current_mode(self) -> str:
        """Получает текущий режим работы"""
        if not self.mode_file.exists():
            return "main"

        try:
            with open(self.mode_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get("mode", "main")
        except Exception as e:
            logger.error(f"Ошибка чтения режима: {e}")
            return "main"

    def should_run_fallback(self) -> bool:
        """Проверяет, должен ли работать fallback бот"""
        return self.get_current_mode() == "maintenance"

    def create_application(self) -> Application:
        """Создает Telegram приложение"""
        application = Application.builder().token(self.token).build()

        # Добавляем обработчик всех сообщений
        application.add_handler(MessageHandler(filters.ALL, self.fallback_message_handler))

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
                # Получаем информацию о режиме
                mode_data = {}
                if self.mode_file.exists():
                    with open(self.mode_file, 'r', encoding='utf-8') as f:
                        mode_data = json.load(f)

                reason = mode_data.get("reason", "Техническое обслуживание")

                # Экранируем комментарий для MarkdownV2
                escaped_reason = self.escape_markdown_v2(reason)

                # Отправляем сообщение об обслуживании
                message_text = f"""[SERVICE] **Режим технического обслуживания**

[REASON] {escaped_reason}

[INFO] Бот будет доступен после завершения обслуживания"""


                await update.message.reply_text(
                    message_text,
                    parse_mode=None,  # Отправляем как обычный текст
                    reply_markup=None
                )

                logger.info(f"[SENT] Отправлено сообщение об обслуживании пользователю {user_name}")
            else:
                # Режим обслуживания отключен, игнорируем сообщения
                logger.info(f"[INFO] Режим обслуживания отключен, игнорируем сообщение от {user_name}")

        except Exception as e:
            logger.error(f"[ERROR] Ошибка при обработке сообщения: {e}")
            try:
                await update.message.reply_text(
                    """[SERVICE] Бот находится на техническом обслуживании.
Попробуйте позже.""",
                    parse_mode=None
                )
            except Exception as reply_error:
                logger.error(f"Не удалось отправить сообщение об ошибке: {reply_error}")

    async def run(self):
        """Запускает fallback бот"""
        logger.info("🚀 Maintenance Fallback Bot запущен")

        # Создаем приложение
        self.application = self.create_application()

        logger.info("📡 Запускаем polling для обработки сообщений...")

        # Запускаем polling с оптимальными настройками
        try:
            await self.application.run_polling(
                poll_interval=5.0,  # Опрашиваем реже (каждые 5 секунд)
                timeout=10,         # Короче таймаут
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query"]
            )
        except Exception as e:
            logger.error(f"[ERROR] Ошибка в polling fallback бота: {e}")
            # Не позволяем исключению всплыть выше, чтобы systemd не перезапускал бесконечно
            return


def main():
    """Главная функция"""
    # Включаем поддержку вложенных event loops
    nest_asyncio.apply()

    # Получаем токен из переменной окружения
    token = os.getenv('BOT_TOKEN')
    if not token:
        logger.error("Не найден токен бота! Установите BOT_TOKEN")
        return

    # Создаем бота
    bot = MaintenanceFallbackBot(token=token)

    # Запускаем
    asyncio.run(bot.run())


if __name__ == "__main__":
    main()
