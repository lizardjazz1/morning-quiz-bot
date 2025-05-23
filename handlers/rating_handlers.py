# handlers/rating_handlers.py
from telegram import Update
from telegram.ext import ContextTypes

# Импорты из других модулей проекта
from config import logger
import state # Для доступа к user_scores
from utils import pluralize_points # Новая функция для склонения слова "очки"

async def rating_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        logger.warning("rating_command: message or effective_chat is None.")
        return
    chat_id_str = str(update.effective_chat.id)

    if chat_id_str not in state.user_scores or not state.user_scores[chat_id_str]:
        await update.message.reply_text("В этом чате еще нет статистики игроков.") # type: ignore
        return

    sorted_scores_list = sorted(
        state.user_scores[chat_id_str].items(),
        key=lambda item: item[1].get("score", 0),
        reverse=True
    )

    if not sorted_scores_list:
        await update.message.reply_text("Пока нет игроков с набранными очками в этом чате.") # type: ignore
        return

    top_players_text = "🏆 Топ-10 игроков в этом чате (/rating):\n\n"
    for i, (user_id, data) in enumerate(sorted_scores_list[:10]):
        player_name = data.get('name', f'Игрок {user_id}')
        player_score = data.get('score', 0)
        top_players_text += f"{i+1}. {player_name} - {pluralize_points(player_score)}\n" # Используем pluralize

    await update.message.reply_text(top_players_text) # type: ignore

async def global_top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return

    if not state.user_scores:
        await update.message.reply_text("Пока нет данных о рейтингах игроков.") # type: ignore
        return

    # Правильное агрегирование для глобального топа
    aggregated_global_scores = {} # user_id: {"name": name, "total_score": score}
    for chat_id, chat_users in state.user_scores.items(): # Итерация по всем чатам
        for user_id, data in chat_users.items():
            user_name = data.get("name", f"Игрок {user_id}")
            user_chat_score = data.get("score", 0)
            
            if user_id not in aggregated_global_scores:
                aggregated_global_scores[user_id] = {"name": user_name, "total_score": 0}
            
            aggregated_global_scores[user_id]["total_score"] += user_chat_score
            # Обновляем имя, если текущее "полнее" или просто последнее увиденное
            # Можно улучшить, например, храня глобальное имя пользователя
            if len(user_name) > len(aggregated_global_scores[user_id]["name"]):
                 aggregated_global_scores[user_id]["name"] = user_name


    if not aggregated_global_scores:
        await update.message.reply_text("Нет игроков для отображения в глобальном рейтинге.") # type: ignore
        return

    sorted_global_scores = sorted(
        aggregated_global_scores.items(),
        key=lambda item: item[1]["total_score"],
        reverse=True
    )

    global_top_text = "🌍 Глобальный Топ-10 игроков (/globaltop):\n\n"
    for i, (user_id, data) in enumerate(sorted_global_scores[:10]):
        player_name = data["name"]
        player_total_score = data["total_score"]
        global_top_text += f"{i+1}. {player_name} - {pluralize_points(player_total_score)}\n" # Используем pluralize

    await update.message.reply_text(global_top_text) # type: ignore

