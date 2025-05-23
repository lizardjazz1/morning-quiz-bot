# handlers/common_handlers.py
from telegram import Update
from telegram.ext import ContextTypes
# TelegramUser импортируется, но не используется напрямую в этих функциях,
# но может быть полезен для type hinting, если effective_user проверяется строже.
# from telegram.user import User as TelegramUser 

# Импорты из других модулей проекта
from config import logger, QUIZ10_NOTIFY_DELAY_MINUTES # QUIZ10_NOTIFY_DELAY_MINUTES для текста /start
import state # Для доступа к quiz_data, user_scores
from data_manager import save_user_data # Для сохранения данных пользователя

# --- Обработчики команд ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id_str = str(update.effective_chat.id)

    if user is None:
        logger.warning("start_command: update.effective_user is None")
        # Сообщение пользователю не отправляем, т.к. update.message может быть None
        return

    user_id_str = str(user.id)

    state.user_scores.setdefault(chat_id_str, {}).setdefault(user_id_str, {"name": user.full_name, "score": 0, "answered_polls": set()})
    state.user_scores[chat_id_str][user_id_str]["name"] = user.full_name
    if not isinstance(state.user_scores[chat_id_str][user_id_str].get("answered_polls"), set):
        current_answered_polls = state.user_scores[chat_id_str][user_id_str].get("answered_polls", [])
        state.user_scores[chat_id_str][user_id_str]["answered_polls"] = set(current_answered_polls)

    save_user_data()
    await update.message.reply_text( # type: ignore
        f"Привет, {user.first_name}! Я бот для викторин.\n\n"
        "Доступные команды:\n"
        "/quiz [категория] - 1 случайный вопрос (можно без категории).\n"
        "/quiz10 - Сессия из 10 вопросов с выбором категории.\n"
        f"/quiz10notify [категория] - Анонс /quiz10 через {QUIZ10_NOTIFY_DELAY_MINUTES} мин. (можно без категории).\n"
        "/categories - Список всех доступных категорий.\n"
        "/rating - Топ-10 игроков в этом чате.\n"
        "/globaltop - Топ-10 игроков по всем чатам.\n"
        "/stopquiz - Остановить текущую или запланированную викторину /quiz10 (для админов или начавшего)."
    )

async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    if not state.quiz_data:
        await update.message.reply_text("Категории вопросов еще не загружены. Попробуйте позже.")
        return

    category_names = []
    for name, questions_list in state.quiz_data.items():
        if isinstance(questions_list, list) and questions_list: # Проверяем, что список не пустой
            category_names.append(f"- {name} (вопросов: {len(questions_list)})")

    if category_names:
        await update.message.reply_text("Доступные категории:\n" + "\n".join(category_names)) # type: ignore
    else:
        await update.message.reply_text("На данный момент нет доступных категорий с вопросами.") # type: ignore
