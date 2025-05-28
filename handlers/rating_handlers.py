# bot/handlers/rating_handlers.py
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode # For Markdown if needed

from app_config import logger
from modules import score_manager
from utils import pluralize, escape_markdown_v2


def get_player_display(player_name: str, player_score: int, separator: str = " - ") -> str:
    """Форматирует отображение игрока для рейтингов."""
    icon = ""
    if player_score > 0:
        if player_score >= QUIZ_CONFIG.get("global_settings",{}).get("motivational_messages",{}).get("1000_threshold", 1000): icon = "🌟"
        elif player_score >= QUIZ_CONFIG.get("global_settings",{}).get("motivational_messages",{}).get("500_threshold", 500): icon = "🏆"
        # ... add more thresholds from config if desired
        else: icon = "👍"
    elif player_score < 0: icon = "💀"
    else: icon = "😐"
    
    score_text = pluralize(player_score, "очко", "очка", "очков")
    # Ensure name is escaped if using Markdown
    # For plain text, no need to escape. Current implementation sends plain text.
    return f"{icon} {player_name}{separator}{score_text}"


async def rating_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat: return
    chat_id_str = str(update.effective_chat.id)
    
    top_players = score_manager.get_chat_rating(chat_id_str, top_n=10)
    
    if not top_players:
        reply_text = "В этом чате еще нет статистики игроков."
    else:
        text_parts = ["📊 Топ-10 игроков в этом чате (/rating):\n"]
        for i, player_data in enumerate(top_players):
            rank_prefix = f"{i+1}."
            if player_data["score"] > 0:
                if i == 0: rank_prefix = "🥇"
                elif i == 1: rank_prefix = "🥈"
                elif i == 2: rank_prefix = "🥉"
            
            # Ensure names are safe for Telegram (escaping if needed, but get_player_display currently doesn't use Markdown)
            display_name = player_data['name'] # get_player_display handles complex names
            text_parts.append(f"{rank_prefix} {get_player_display(display_name, player_data['score'])}")
        reply_text = "\n".join(text_parts)
        
    await update.message.reply_text(reply_text) # ParseMode not needed if get_player_display returns plain text


async def global_top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    
    top_global_players = score_manager.get_global_rating(top_n=10)
    
    if not top_global_players:
        reply_text = "Пока нет данных о рейтингах игроков ни в одном чате."
    else:
        text_parts = ["🌍 Глобальный Топ-10 игроков (/globaltop):\n"]
        for i, player_data in enumerate(top_global_players):
            rank_prefix = f"{i+1}."
            if player_data["score"] > 0:
                if i == 0: rank_prefix = "🥇"
                elif i == 1: rank_prefix = "🥈"
                elif i == 2: rank_prefix = "🥉"
            display_name = player_data['name']
            text_parts.append(f"{rank_prefix} {get_player_display(display_name, player_data['score'])}")
        reply_text = "\n".join(text_parts)
        
    await update.message.reply_text(reply_text)

# Placeholder for future rating flexibility
# async def custom_rating_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     # Args: /rating type=quiz quiz_id=X, /rating category=Y
#     # This would require score_manager to support more complex queries
#     await update.message.reply_text("Гибкий рейтинг в разработке.")
