# bot/handlers/common_handlers.py
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from app_config import logger, QUIZ10_NOTIFY_DELAY_MINUTES, DAILY_QUIZ_DEFAULT_HOUR_MSK, DAILY_QUIZ_DEFAULT_MINUTE_MSK
from utils import escape_markdown_v2
from modules import category_manager
from modules.score_manager import _ensure_user_initialized # For /start side effect
from data_manager import save_user_data # For /start side effect


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user:
        logger.warning("help_command: message, chat or user is None.")
        return

    user = update.effective_user
    chat_id_str = str(update.effective_chat.id)

    # Инициализация пользователя (побочный эффект /help, как в старом /start)
    _ensure_user_initialized(chat_id_str, user)
    save_user_data() # Сохраняем, если были изменения (например, новое имя)

    # Глобальные настройки из app_config, которые могут быть использованы в тексте помощи
    notify_delay = QUIZ10_NOTIFY_DELAY_MINUTES
    daily_default_H = DAILY_QUIZ_DEFAULT_HOUR_MSK
    daily_default_M = DAILY_QUIZ_DEFAULT_MINUTE_MSK


    help_text = (
        f"Привет, {escape_markdown_v2(user.first_name)}\\! Я бот для викторин\\.\n\n"
        "Доступные команды:\n"
        "`/help` \\- Показать это сообщение\\.\n"
        "`/quiz [категория]` \\- 1 случайный вопрос \\(можно без категории\\)\\.\n"
        "`/quiz10 [категория]` \\- Сессия из 10 вопросов \\(можно с конкретной категорией или выбрать из меню\\)\\.\n"
        f"`/quiz10notify [категория]` \\- Анонс /quiz10 через {notify_delay} мин \\(можно без категории\\)\\.\n"
        "`/categories` \\- Список всех доступных категорий\\.\n"
        "`/rating` \\- Топ\\-10 игроков в этом чате\\.\n"
        "`/globaltop` \\- Топ\\-10 игроков по всем чатам\\.\n"
        "`/stopquiz` \\- Остановить текущую или запланированную викторину (/quiz10, /quiz10notify, ежедневная)\\.\n\n"
        "*Ежедневная викторина*:\n"
        "`/dailyquiz` \\- Подписаться/показать статус/настроить ежедневную викторину\\.\n"
        "`/subdaily` \\- Подписаться на ежедневную викторину \\(время по умолч\\.: {daily_default_H:02d}:{daily_default_M:02d} МСК\\)\\.\n"
        "`/unsubdaily` \\- Отписаться от ежедневной викторины\\.\n\n"
        "*Настройки викторин в чате* \\(для админов\\):\n"
        "`/setquiztype <тип>` \\- Установить тип викторины по умолчанию для `/quiz` \\(normal/session\\)\\.\n"
        "`/setquizquestions <N>` \\- Количество вопросов для сессии по умолчанию\\.\n"
        "`/setquizcategories [кат1] [кат2] ...` \\- Категории по умолчанию для чата \\(через пробел, `random` для случайных\\)\\.\n"
        "`/excludecategories [кат1] [кат2] ...` \\- Исключить категории из выбора для чата \\(пусто для очистки\\)\\.\n"
        "`/showchatsettings` \\- Показать текущие настройки викторин для этого чата\\."
    )
    logger.debug(f"Attempting to send help message to {chat_id_str}.")
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN_V2)

async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        return

    chat_id_str = str(update.effective_chat.id)
    
    available_categories_info = category_manager.get_available_categories(with_question_counts=True)

    if not available_categories_info:
        text_to_send = "Категории вопросов еще не загружены или отсутствуют. Попробуйте позже."
        parse_mode = None
    else:
        category_lines = []
        for cat_info in available_categories_info:
            escaped_name = escape_markdown_v2(cat_info['name'])
            count = cat_info['count']
            category_lines.append(f"\\- *{escaped_name}* \\(вопросов: {count}\\)")
        
        if category_lines:
            text_to_send = "Доступные категории:\n" + "\n".join(category_lines)
            parse_mode = ParseMode.MARKDOWN_V2
        else: # Should be caught by the first if, but for safety
            text_to_send = "На данный момент нет доступных категорий с вопросами."
            parse_mode = None
            
    logger.debug(f"Attempting to send categories list to {chat_id_str}.")
    await update.message.reply_text(text_to_send, parse_mode=parse_mode)
