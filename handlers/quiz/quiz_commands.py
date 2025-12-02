"""
Обработчики команд викторин
Отвечает за обработку команд пользователя (/quiz, /stop_quiz и т.д.)
"""

from __future__ import annotations
import logging
from typing import List, Optional, Dict, Any, Union
from datetime import datetime

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from telegram.ext import ContextTypes, ConversationHandler

from .quiz_types import QuizConfig, QuizMode
from .quiz_validator import QuizValidator
from utils import escape_markdown_v2
from modules.telegram_utils import safe_send_message
from modules.category_manager import CategoryManager

logger = logging.getLogger(__name__)


class QuizCommands:
    """Обработчики команд викторин"""

    def __init__(self, app_config: 'AppConfig', quiz_engine: 'QuizEngine',
                 data_manager: 'DataManager', category_manager: CategoryManager):
        self.app_config = app_config
        self.quiz_engine = quiz_engine
        self.data_manager = data_manager
        self.category_manager = category_manager

    async def quiz_command_entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        """Обработчик команды /quiz"""
        if not update.effective_user or not update.message:
            return None

        user = update.effective_user
        chat_id = update.effective_chat.id if update.effective_chat else None

        if not chat_id:
            await safe_send_message(
                context.bot,
                chat_id=user.id,
                text=escape_markdown_v2("Не удалось определить чат для викторины."),
                parse_mode='MarkdownV2'
            )
            return None

        # Проверяем, есть ли уже активная викторина
        active_session = self.quiz_engine.get_active_session(chat_id)
        if active_session:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Посмотреть статус", callback_data=f"quiz_status_{chat_id}")],
                [InlineKeyboardButton("🛑 Остановить", callback_data=f"stop_quiz_{chat_id}")]
            ])

            await safe_send_message(
                context.bot,
                chat_id=chat_id,
                text=escape_markdown_v2(
                    f"В этом чате уже идет викторина!\n"
                    f"Вопрос {active_session.current_question + 1} из {len(active_session.questions)}\n"
                    f"Участников: {len(active_session.participants)}"
                ),
                reply_markup=keyboard,
                parse_mode='MarkdownV2'
            )
            return None

        # Показываем меню конфигурации викторины
        await self._send_quiz_config_menu(update, context)
        return "QUIZ_CONFIG"

    async def _send_quiz_config_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показать меню конфигурации викторины"""
        if not update.effective_chat:
            return

        chat_id = update.effective_chat.id

        # Получаем текущие настройки чата
        chat_settings = self.data_manager.get_chat_settings(chat_id)
        default_questions = chat_settings.get('default_num_questions', 10)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🎯 Начать ({default_questions} вопросов)",
                                callback_data="quiz_start_default")],
            [InlineKeyboardButton("⚙️ Настроить", callback_data="quiz_configure")],
            [InlineKeyboardButton("📚 Выбрать категории", callback_data="quiz_categories")],
            [InlineKeyboardButton("❌ Отмена", callback_data="quiz_cancel")]
        ])

        text = (
            "🎮 *Настройка викторины*\n\n"
            "• 🎯 Быстрый старт с настройками по умолчанию\n"
            "• ⚙️ Настроить количество вопросов и время\n"
            "• 📚 Выбрать конкретные категории\n"
            "• ❌ Отменить настройку\n\n"
            f"Текущие настройки: {default_questions} вопросов"
        )

        await safe_send_message(
            context.bot,
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    async def handle_quiz_config_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        """Обработчик callback-запросов от меню конфигурации викторины"""
        query = update.callback_query
        if not query:
            return None

        await query.answer()

        callback_data = query.data
        chat_id = query.message.chat_id if query.message else None

        if not chat_id:
            return None

        if callback_data == "quiz_start_default":
            # Начать викторину с настройками по умолчанию
            config = self._get_default_quiz_config(chat_id)
            success, message, session = await self.quiz_engine.create_quiz_session(chat_id, config, context)

            if success and session:
                await safe_send_message(
                    context.bot,
                    chat_id=chat_id,
                    text=escape_markdown_v2(f"✅ Викторина запущена!\n{message}"),
                    parse_mode='MarkdownV2'
                )
                return None
            else:
                await safe_send_message(
                    context.bot,
                    chat_id=chat_id,
                    text=escape_markdown_v2(f"❌ Ошибка запуска викторины: {message}"),
                    parse_mode='MarkdownV2'
                )
                return "QUIZ_CONFIG"

        elif callback_data == "quiz_configure":
            # Показать меню настройки параметров
            await self._send_quiz_params_menu(query, context)
            return "QUIZ_CONFIG"

        elif callback_data == "quiz_categories":
            # Показать меню выбора категорий
            await self._send_categories_menu(query, context)
            return "QUIZ_CONFIG"

        elif callback_data == "quiz_cancel":
            # Отменить настройку
            await safe_send_message(
                context.bot,
                chat_id=chat_id,
                text=escape_markdown_v2("Настройка викторины отменена."),
                parse_mode='MarkdownV2'
            )
            return None

        return "QUIZ_CONFIG"

    def _get_default_quiz_config(self, chat_id: int) -> QuizConfig:
        """Получить конфигурацию викторины по умолчанию"""
        chat_settings = self.data_manager.get_chat_settings(chat_id)

        return QuizConfig(
            mode=QuizMode.SERIAL_IMMEDIATE,
            num_questions=chat_settings.get('default_num_questions', 10),
            open_period_seconds=chat_settings.get('default_open_period_seconds', 30),
            interval_seconds=chat_settings.get('default_interval_seconds', 30),
            categories_mode="random",
            specific_categories=[],
            announce_quiz=False
        )

    async def _send_quiz_params_menu(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показать меню настройки параметров викторины"""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("5 вопросов", callback_data="quiz_questions_5"),
             InlineKeyboardButton("10 вопросов", callback_data="quiz_questions_10")],
            [InlineKeyboardButton("15 вопросов", callback_data="quiz_questions_15"),
             InlineKeyboardButton("20 вопросов", callback_data="quiz_questions_20")],
            [InlineKeyboardButton("Назад", callback_data="quiz_back_to_main")]
        ])

        text = (
            "⚙️ *Настройка викторины*\n\n"
            "Выберите количество вопросов:"
        )

        await query.edit_message_text(
            text=text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    async def _send_categories_menu(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показать меню выбора категорий"""
        # Получить доступные категории
        categories = self.category_manager.get_all_category_names(with_question_counts=True)

        if not categories:
            await safe_send_message(
                context.bot,
                chat_id=query.message.chat_id,
                text=escape_markdown_v2("Категории пока не загружены."),
                parse_mode='MarkdownV2'
            )
            return

        keyboard = []
        for category in categories[:10]:  # Показать первые 10
            cat_name = category.get('name', 'N/A')
            keyboard.append([InlineKeyboardButton(
                f"📚 {cat_name}",
                callback_data=f"quiz_cat_{cat_name}"
            )])

        keyboard.append([InlineKeyboardButton("Назад", callback_data="quiz_back_to_main")])

        text = (
            "📚 *Выбор категорий*\n\n"
            "Выберите категории для викторины:"
        )

        await query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    async def stop_quiz_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /stop_quiz"""
        if not update.effective_chat:
            return

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id if update.effective_user else None

        # Проверяем права администратора
        if not self._is_admin(user_id, chat_id):
            await safe_send_message(
                context.bot,
                chat_id=chat_id,
                text=escape_markdown_v2("❌ Только администраторы могут останавливать викторины."),
                parse_mode='MarkdownV2'
            )
            return

        # Останавливаем викторину
        success, message = await self.quiz_engine.stop_quiz_session(chat_id, context)

        if success:
            await safe_send_message(
                context.bot,
                chat_id=chat_id,
                text=escape_markdown_v2(f"✅ Викторина остановлена!\n{message}"),
                parse_mode='MarkdownV2'
            )
        else:
            await safe_send_message(
                context.bot,
                chat_id=chat_id,
                text=escape_markdown_v2(f"❌ Ошибка остановки викторины: {message}"),
                parse_mode='MarkdownV2'
            )

    def _is_admin(self, user_id: Optional[int], chat_id: int) -> bool:
        """Проверить, является ли пользователь администратором"""
        if not user_id:
            return False

        # Получить список администраторов
        admins = self.data_manager.get_admins()
        return user_id in admins

    def get_handlers(self) -> List:
        """Получить список обработчиков команд"""
        return [
            # Обработчики команд будут добавлены в основной QuizManager
        ]
