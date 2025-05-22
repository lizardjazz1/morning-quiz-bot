# handlers/rating_handler.py

from telegram import Update
from telegram.ext import ContextTypes
from utils.users import user_scores

async def rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    scores = user_scores.get(chat_id, {})

    if not scores:
        await update.message.reply_text("Никто ещё не отвечал.")
        return

    sorted_scores = sorted(scores.items(), key=lambda x: x[1]['score'], reverse=True)
    rating_text = "🏆 Таблица лидеров:\n\n"
    for idx, (uid, data) in enumerate(sorted_scores, 1):
        rating_text += f"{idx}. {data['name']} — {data['score']} очков\n"

    await update.message.reply_text(rating_text)