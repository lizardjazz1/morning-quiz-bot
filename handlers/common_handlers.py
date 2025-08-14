#handlers/common_handlers.py
import logging
from typing import List, Optional

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, ConversationHandler # ИСПРАВЛЕНО: Добавлен ConversationHandler
from telegram.constants import ParseMode

from app_config import AppConfig
from state import BotState
from utils import escape_markdown_v2
from modules.category_manager import CategoryManager

logger = logging.getLogger(__name__)

class CommonHandlers:
    def __init__(self, app_config: AppConfig, category_manager: CategoryManager, bot_state: BotState):
        self.app_config = app_config
        self.category_manager = category_manager
        self.bot_state = bot_state # bot_state сохраняется, но не используется методами этого класса

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.message:
            return

        user = update.effective_user
        welcome_text = (
            f"Привет, {escape_markdown_v2(user.first_name)}\\! Я бот для проведения викторин\\.\n\n"
            f"Доступные команды:\n"
            f"/{self.app_config.commands.quiz} \\- {escape_markdown_v2('начать викторину')}\n"
            f"/{self.app_config.commands.top} \\- {escape_markdown_v2('посмотреть рейтинг чата')}\n"
            f"/{self.app_config.commands.categories} \\- {escape_markdown_v2('посмотреть доступные категории')}\n"
            f"/{self.app_config.commands.help} \\- {escape_markdown_v2('показать эту справку')}"
        )
        try:
            sent_msg = await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN_V2)
            # Добавляем сообщение в список для удаления
            bot_state = context.bot_data.get('bot_state')
            if bot_state:
                bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
        except Exception as e:
            logger.error(f"Ошибка при отправке start_command: {e}")


    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return

        help_full_text = (
            f"*{escape_markdown_v2('Справка по командам:')}*\n\n"
            f"*{escape_markdown_v2('📝 Викторина')}*\n"
            f"/{self.app_config.commands.quiz} \\- {escape_markdown_v2('начать викторину (можно с параметрами)')}\n"
            f"{escape_markdown_v2('Примеры:')}\n"
            f"`/{self.app_config.commands.quiz} 5` \\- {escape_markdown_v2('викторина из 5 вопросов')}\n"
            f"`/{self.app_config.commands.quiz} {escape_markdown_v2('Название Категории')}` \\- {escape_markdown_v2('викторина по категории')}\n"
            f"`/{self.app_config.commands.quiz} 10 {escape_markdown_v2('Название Категории')}` \\- {escape_markdown_v2('комбинированный вариант')}\n"
            f"`/{self.app_config.commands.quiz} announce` \\- {escape_markdown_v2('викторина с анонсом')}\n"
            f"/{self.app_config.commands.stop_quiz} \\- {escape_markdown_v2('остановить текущую викторину (админ/инициатор)')}\n\n"

            f"*{escape_markdown_v2('📚 Категории')}*\n"
            f"/{self.app_config.commands.categories} \\- {escape_markdown_v2('показать список всех категорий вопросов')}\n\n"

            f"*{escape_markdown_v2('📊 Рейтинг и Статистика')}*\n"
            f"/{self.app_config.commands.top} \\- {escape_markdown_v2('показать рейтинг текущего чата')}\n"
            f"/{self.app_config.commands.global_top} \\- {escape_markdown_v2('показать глобальный рейтинг')}\n"
            f"/{self.app_config.commands.mystats} \\- {escape_markdown_v2('показать вашу личную статистику')}\n\n"

            f"*{escape_markdown_v2('⚙️ Настройки (для администраторов чата)')}*\n"
            f"/{getattr(self.app_config.commands, 'admin_settings', 'adminsettings')} \\- {escape_markdown_v2('открыть меню настроек чата')}\n"
            f"/{getattr(self.app_config.commands, 'view_chat_config', 'viewchatconfig')} \\- {escape_markdown_v2('посмотреть текущие настройки чата')}\n\n"


            f"*{escape_markdown_v2('❓ Общие')}*\n"
            f"/{self.app_config.commands.help} \\- {escape_markdown_v2('показать эту справку')}\n"
            f"/{self.app_config.commands.start} \\- {escape_markdown_v2('начать работу с ботом')}\n"
            f"/{self.app_config.commands.cancel} \\- {escape_markdown_v2('отмена текущего диалога (например, настройки)')}"
        )
        try:
            sent_msg = await update.message.reply_text(help_full_text, parse_mode=ParseMode.MARKDOWN_V2)
            # Добавляем сообщение в список для удаления
            bot_state = context.bot_data.get('bot_state')
            if bot_state:
                bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
        except Exception as e:
            logger.error(f"Ошибка при отправке help_command: {e}")

    async def categories_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        # Получаем список категорий (только имена)
        categories_data = self.category_manager.get_all_category_names(with_question_counts=True)

        if not categories_data:
            try:
                sent_msg = await update.message.reply_text(escape_markdown_v2("Категории вопросов еще не загружены или отсутствуют."), parse_mode=ParseMode.MARKDOWN_V2)
                # Добавляем сообщение в список для удаления
                bot_state = context.bot_data.get('bot_state')
                if bot_state:
                    bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
            except Exception as e:
                 logger.error(f"Ошибка при отправке categories_command (нет категорий): {e}")
            return

        response_lines = [f"*{escape_markdown_v2('📚 Доступные категории вопросов (кол-во вопросов):')}*"]
        for cat_info in sorted(categories_data, key=lambda x: x.get('name', '').lower()):
            cat_name_escaped = escape_markdown_v2(cat_info.get('name', 'N/A'))
            q_count = cat_info.get('count', 0)
            response_lines.append(f"{escape_markdown_v2('-')} `{cat_name_escaped}` {escape_markdown_v2(f'({q_count})')}")

        full_message = "\n".join(response_lines)

        try:
            if len(full_message) > 4096:
                logger.warning("Список категорий слишком длинный, будет отправлен частями.")
                part_buffer = response_lines[0] + "\n"
                for line_idx, line_content in enumerate(response_lines[1:], 1):
                    if len(part_buffer) + len(line_content) + 1 > 4000:
                        sent_msg = await update.message.reply_text(part_buffer.strip(), parse_mode=ParseMode.MARKDOWN_V2)
                        # Добавляем сообщение в список для удаления
                        bot_state = context.bot_data.get('bot_state')
                        if bot_state:
                            bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
                        part_buffer = line_content
                    else:
                        part_buffer += "\n" + line_content
                if part_buffer.strip():
                    sent_msg = await update.message.reply_text(part_buffer.strip(), parse_mode=ParseMode.MARKDOWN_V2)
                    # Добавляем сообщение в список для удаления
                    bot_state = context.bot_data.get('bot_state')
                    if bot_state:
                        bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
            else:
                sent_msg = await update.message.reply_text(full_message, parse_mode=ParseMode.MARKDOWN_V2)
                # Добавляем сообщение в список для удаления
                bot_state = context.bot_data.get('bot_state')
                if bot_state:
                    bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
        except Exception as e:
            logger.error(f"Ошибка при отправке списка категорий: {e}\nТекст сообщения (начало): {full_message[:500]}")
            try:
                sent_msg = await update.message.reply_text(
                    escape_markdown_v2("Произошла ошибка при отображении списка категорий."),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                # Добавляем сообщение в список для удаления
                bot_state = context.bot_data.get('bot_state')
                if bot_state:
                    bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
            except Exception as e_fallback:
                 logger.error(f"Ошибка при отправке fallback-сообщения для categories_command: {e_fallback}")


    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
        if not update.message or not update.effective_user or not update.effective_chat:
             return ConversationHandler.END # type: ignore [attr-defined]

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        cancel_message = escape_markdown_v2("Команда отмены получена. Если вы были в диалоге, он должен завершиться.")
        try:
            sent_msg = await update.message.reply_text(cancel_message, parse_mode=ParseMode.MARKDOWN_V2)
            # Добавляем сообщение в список для удаления
            bot_state = context.bot_data.get('bot_state')
            if bot_state:
                bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
        except Exception as e:
            logger.error(f"Ошибка при отправке cancel_command сообщения: {e}")

        logger.info(f"Пользователь {user_id} в чате {chat_id} вызвал /{self.app_config.commands.cancel}.")
        return ConversationHandler.END # type: ignore [attr-defined]

    def get_handlers(self) -> List[CommandHandler]:
        handlers_list = [
            CommandHandler(self.app_config.commands.start, self.start_command),
            CommandHandler(self.app_config.commands.help, self.help_command),
            CommandHandler(self.app_config.commands.categories, self.categories_command),
            CommandHandler(self.app_config.commands.cancel, self.cancel_command),
        ]
        return handlers_list
