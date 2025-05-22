# handlers/rating.py

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

import logging

logger = logging.getLogger(__name__)

async def rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    scores = context.bot_data.get("user_scores", {}).get(chat_id, {})
    
    if not scores:
        await update.message.reply_text("Никто ещё не отвечал.")
        return

    try:
        sorted_scores = sorted(scores.items(), key=lambda x: x[1]['score'], reverse=True)
        rating_text = "🏆 Таблица лидеров:\n"
        for idx, (uid, data) in enumerate(sorted_scores, 1):
            rating_text += f"{idx}. {data['name']} — {data['score']} очков\n"
        await update.message.reply_text(rating_text)
    except Exception as e:
        logger.error(f"Ошибка при выводе рейтинга в чате {chat_id}: {e}")
        await update.message.reply_text("❌ Не могу показать рейтинг — произошла ошибка")

rating_handler = CommandHandler("rating", rating)