# handlers/common_handlers.py
from telegram import Update
from telegram.ext import ContextTypes

from config import logger, QUIZ10_NOTIFY_DELAY_MINUTES, DAILY_QUIZ_DEFAULT_HOUR_MSK, DAILY_QUIZ_DEFAULT_MINUTE_MSK
import state
from data_manager import save_user_data

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user:
        logger.warning("start_command: message, chat or user is None.")
        return

    user = update.effective_user
    chat_id_str = str(update.effective_chat.id)
    user_id_str = str(user.id)

    # Инициализация пользователя, если его нет
    state.user_scores.setdefault(chat_id_str, {}).setdefault(user_id_str, {"name": user.full_name, "score": 0, "answered_polls": set(), "milestones_achieved": set()})
    # Обновление имени пользователя (может измениться)
    state.user_scores[chat_id_str][user_id_str]["name"] = user.full_name
    # Гарантируем, что answered_polls и milestones_achieved являются множествами
    if not isinstance(state.user_scores[chat_id_str][user_id_str].get("answered_polls"), set):
        state.user_scores[chat_id_str][user_id_str]["answered_polls"] = set(state.user_scores[chat_id_str][user_id_str].get("answered_polls", []))
    if not isinstance(state.user_scores[chat_id_str][user_id_str].get("milestones_achieved"), set):
        state.user_scores[chat_id_str][user_id_str]["milestones_achieved"] = set(state.user_scores[chat_id_str][user_id_str].get("milestones_achieved", []))

    save_user_data()
    
    start_message_text = (
        f"Привет, {user.first_name}! Я бот для викторин.\n\n"
        "Доступные команды:\n"
        "/quiz `[категория]` - 1 случайный вопрос (можно без категории).\n"
        "/quiz10 - Сессия из 10 вопросов с выбором категории.\n"
        f"/quiz10notify `[категория]` - Анонс /quiz10 через {QUIZ10_NOTIFY_DELAY_MINUTES} мин.\n"
        "/categories - Список всех доступных категорий.\n"
        "/rating - Топ-10 игроков в этом чате.\n"
        "/globaltop - Топ-10 игроков по всем чатам.\n"
        "/stopquiz - Остановить текущую или запланированную /quiz10.\n\n"
        "Ежедневная викторина:\n"
        f"/subscribe_daily_quiz - Подписаться на ежедневную викторину (в ~{DAILY_QUIZ_DEFAULT_HOUR_MSK:02d}:{DAILY_QUIZ_DEFAULT_MINUTE_MSK:02d} МСК).\n"
        "/unsubscribe_daily_quiz - Отписаться от ежедневной викторины."
    )
    logger.debug(f"Attempting to send start message to {chat_id_str}. Text: '{start_message_text[:100]}...'")
    await update.message.reply_text(start_message_text)

async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        return
        
    chat_id_str = str(update.effective_chat.id)
    text_to_send = ""

    if not state.quiz_data:
        text_to_send = "Категории вопросов еще не загружены. Попробуйте позже."
    else:
        category_names = []
        for name, questions_list in state.quiz_data.items():
            if isinstance(questions_list, list) and questions_list:
                category_names.append(f"- {name} (вопросов: {len(questions_list)})")
        
        if category_names:
            text_to_send = "Доступные категории:\n" + "\n".join(sorted(category_names)) # Сортируем для порядка
        else:
            text_to_send = "На данный момент нет доступных категорий с вопросами."
    
    logger.debug(f"Attempting to send categories list to {chat_id_str}. Text: '{text_to_send[:100]}...'")
    await update.message.reply_text(text_to_send)
