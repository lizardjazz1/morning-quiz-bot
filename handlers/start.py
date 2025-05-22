# handlers/start.py

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from services.score_service import update_user_score

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name

    if chat_id not in context.bot_data.get("user_scores", {}):
        context.bot_data["user_scores"][chat_id] = {}

    if str(user_id) not in context.bot_data["user_scores"].get(chat_id, {}):
        context.bot_data["user_scores"][chat_id][str(user_id)] = {"name": user_name, "score": 0}

    await update.message.reply_text("Привет! Я буду присылать вам утреннюю викторину в формате опроса!")

    active_chats = context.bot_data.get("active_chats", set())
    active_chats.add(chat_id)
    context.bot_data["active_chats"] = active_chats

start = CommandHandler("start", start)