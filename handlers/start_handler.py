# handlers/start_handler.py

from telegram.ext import ContextTypes, CommandHandler
from telegram import Update
from utils.users import load_user_data, save_user_data
from config import USERS_FILE

user_scores = load_user_data()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.full_name

    # Регистрация пользователя
    if chat_id not in user_scores:
        user_scores[chat_id] = {}
    if user_id not in user_scores.get(chat_id, {}):
        user_scores[chat_id][user_id] = {"name": user_name, "score": 0}
        save_user_data(user_scores)

    await update.message.reply_text("Привет! Я буду присылать вам утреннюю викторину в формате опроса!")

    # Добавляем чат в список активных
    active_chats = context.bot_data.get("active_chats", set())
    active_chats.add(chat_id)
    context.bot_data["active_chats"] = active_chats