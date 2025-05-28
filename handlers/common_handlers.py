#handlers/common_handlers.py
import logging
from typing import List, Optional

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, ConversationHandler
from telegram.constants import ParseMode

from app_config import AppConfig
from state import BotState
from utils import escape_markdown_v2 # Убедитесь, что эта функция верна
from modules.category_manager import CategoryManager

logger = logging.getLogger(__name__)

class CommonHandlers:
    def __init__(self, app_config: AppConfig, category_manager: CategoryManager, bot_state: BotState):
        self.app_config = app_config
        self.category_manager = category_manager
        self.bot_state = bot_state

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user: return
        user_name = update.effective_user.first_name
        cmds = self.app_config.commands
        
        cmd_quiz_escaped = escape_markdown_v2(cmds.quiz)
        cmd_categories_escaped = escape_markdown_v2(cmds.categories)
        cmd_help_escaped = escape_markdown_v2(cmds.help)

        # Используем \\ для экранирования специальных символов MarkdownV2 в статических частях строки
        welcome_text = (
            f"👋 Привет, {escape_markdown_v2(user_name)}\\!\n\n"
            f"Я бот для проведения викторин\\! Вот что я умею:\n" # Пример: точка и восклицательный знак
            f"\\- Запускать викторины по команде `/{cmd_quiz_escaped}`\\.\n"
            f"\\- Показывать список доступных категорий: `/{cmd_categories_escaped}`\\.\n"
            f"\\- Помощь по командам: `/{cmd_help_escaped}`\\.\n\n"
            f"Чтобы начать, просто выбери одну из команд\\."
        )
        try:
            await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Ошибка при отправке start_command сообщения: {e}\nТекст сообщения: {welcome_text}")
            await update.message.reply_text(
                "Произошла ошибка при отображении приветственного сообщения.", 
                parse_mode=None
            )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        cmds = self.app_config.commands
        
        # Используем \\ для экранирования специальных символов MarkdownV2 в статических частях строки
        help_text_lines = [
            "*Основные команды:*",
            f"`/{escape_markdown_v2(cmds.start)}` \\- Начальное приветствие",
            f"`/{escape_markdown_v2(cmds.help)}` \\- Эта справка",
            f"`/{escape_markdown_v2(cmds.quiz)}` \\- Начать викторину \\(можно указать параметры, например: `/{escape_markdown_v2(cmds.quiz)} 5 Наука`\\)",
            f"`/{escape_markdown_v2(cmds.categories)}` \\- Показать список категорий",
            f"`/{escape_markdown_v2(cmds.top)}` \\- Рейтинг игроков в этом чате",
            f"`/{escape_markdown_v2(cmds.global_top)}` \\- Общий рейтинг игроков",
            f"`/{escape_markdown_v2(cmds.mystats)}` \\- Ваша статистика",
            f"`/{escape_markdown_v2(cmds.stop_quiz)}` \\- Остановить текущую викторину \\(для админов/инициатора\\)",
            f"`/{escape_markdown_v2(cmds.cancel)}` \\- Отменить текущее действие/диалог \\(если поддерживается\\)",
            "",
            "*Команды администратора чата:*",
            f"`/{escape_markdown_v2(cmds.admin_settings)}` \\- Меню настроек викторин для чата",
            f"`/{escape_markdown_v2(cmds.view_chat_config)}` \\- Показать настройки чата",
        ]
        help_full_text = "\n".join(help_text_lines)
        try:
            await update.message.reply_text(help_full_text, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Ошибка при отправке help_command сообщения: {e}\nТекст сообщения: {help_full_text}")
            await update.message.reply_text(
                "Произошла ошибка при отображении справки.", 
                parse_mode=None
            )

    async def categories_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        categories_data = self.category_manager.get_all_category_names(with_question_counts=True)
        if not categories_data:
            try:
                await update.message.reply_text("Категории вопросов еще не загружены или отсутствуют.", parse_mode=None)
            except Exception as e:
                 logger.error(f"Ошибка при отправке categories_command (нет категорий): {e}")
            return

        response_lines = ["*📚 Доступные категории вопросов \\(кол\\-во вопросов\\):*"] # Заголовок
        for cat_info in sorted(categories_data, key=lambda x: x['name'].lower()):
            cat_name_escaped = escape_markdown_v2(cat_info.get('name', 'N/A'))
            q_count = cat_info.get('count', 0)
            # Экранируем скобки вокруг q_count и дефис для списка
            response_lines.append(f"\\- `{cat_name_escaped}` \\({q_count}\\)")

        full_message = "\n".join(response_lines)
        
        try:
            if len(full_message) > 4096:
                logger.warning("Список категорий слишком длинный, будет отправлен частями.")
                current_message_part = ""
                for line in response_lines:
                    if len(current_message_part) + len(line) + 1 > 4000: 
                        await update.message.reply_text(current_message_part, parse_mode=ParseMode.MARKDOWN_V2)
                        current_message_part = line
                    else:
                        if current_message_part: current_message_part += "\n"
                        current_message_part += line
                if current_message_part:
                    await update.message.reply_text(current_message_part, parse_mode=ParseMode.MARKDOWN_V2)
            else:
                await update.message.reply_text(full_message, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Ошибка при отправке списка категорий: {e}\nТекст сообщения: {full_message}")
            await update.message.reply_text(
                "Произошла ошибка при отображении списка категорий.", 
                parse_mode=None
            )

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
        if not update.message or not update.effective_user or not update.effective_chat:
             return None

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        try:
            await update.message.reply_text(
                "Команда отмены получена. Если вы были в диалоге, он должен завершиться.", 
                parse_mode=None
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке cancel_command сообщения: {e}")

        logger.info(f"Пользователь {user_id} в чате {chat_id} вызвал /cancel.")
        return ConversationHandler.END


    def get_handlers(self) -> List[CommandHandler]:
        handlers_list = [
            CommandHandler(self.app_config.commands.start, self.start_command),
            CommandHandler(self.app_config.commands.help, self.help_command),
            CommandHandler(self.app_config.commands.categories, self.categories_command),
            CommandHandler(self.app_config.commands.cancel, self.cancel_command),
        ]
        return handlers_list
