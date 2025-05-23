# handlers/rating_handlers.py
from telegram import Update
from telegram.ext import ContextTypes

# Импорты из других модулей проекта
from config import logger
import state # Для доступа к user_scores
from utils import pluralize_points # Обновленная функция для склонения слова "очки"

def get_player_display(player_name: str, player_score: int, separator: str = " - ") -> str:
    """
    Формирует строку отображения игрока с иконкой, именем, разделителем и счетом.
    """
    icon = ""
    if player_score > 0:
        if player_score >= 50: # Пример порога для особой медали
            icon = "🌟"
        elif player_score >= 10:
            icon = "🏆"
        else:
            icon = "👍"
    elif player_score < 0:
        icon = "👎"
    else: # player_score == 0
        icon = "😐"
    
    # Используем f-string, чтобы корректно вставить separator без лишних пробелов вокруг него, если он ":"
    # и с пробелами, если он " - "
    if separator == ":":
        return f"{icon} {player_name}{separator} {pluralize_points(player_score)}"
    else: # Для " - " и других возможных разделителей, которые предполагают пробелы вокруг
        return f"{icon} {player_name} {separator} {pluralize_points(player_score)}"


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

    top_players_text = "📊 Топ-10 игроков в этом чате (/rating):\n\n"
    for i, (user_id, data) in enumerate(sorted_scores_list[:10]):
        player_name = data.get('name', f'Игрок {user_id}')
        player_score = data.get('score', 0)
        rank_prefix = f"{i+1}."
        if i == 0 and player_score > 0 : rank_prefix = "🥇"
        elif i == 1 and player_score > 0 : rank_prefix = "🥈"
        elif i == 2 and player_score > 0 : rank_prefix = "🥉"
        
        # Здесь используется separator по умолчанию (" - ")
        top_players_text += f"{rank_prefix} {get_player_display(player_name, player_score)}\n"

    await update.message.reply_text(top_players_text) # type: ignore

async def global_top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return

    if not state.user_scores:
        await update.message.reply_text("Пока нет данных о рейтингах игроков.") # type: ignore
        return

    aggregated_global_scores = {}
    for chat_id, chat_users in state.user_scores.items():
        for user_id, data in chat_users.items():
            user_name = data.get("name", f"Игрок {user_id}")
            user_chat_score = data.get("score", 0)

            if user_id not in aggregated_global_scores:
                aggregated_global_scores[user_id] = {"name": user_name, "total_score": 0}
            
            # Суммируем очки из разных чатов для одного user_id
            aggregated_global_scores[user_id]["total_score"] += user_chat_score
            # Обновляем имя на самое "полное" или последнее встреченное
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
        rank_prefix = f"{i+1}."
        if i == 0 and player_total_score > 0 : rank_prefix = "🥇"
        elif i == 1 and player_total_score > 0 : rank_prefix = "🥈"
        elif i == 2 and player_total_score > 0 : rank_prefix = "🥉"

        # Здесь используется separator по умолчанию (" - ")
        global_top_text += f"{rank_prefix} {get_player_display(player_name, player_total_score)}\n"

    await update.message.reply_text(global_top_text) # type: ignore

