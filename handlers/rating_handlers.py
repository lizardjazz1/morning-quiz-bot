# handlers/rating_handlers.py
from telegram import Update
from telegram.ext import ContextTypes

# Импорты из других модулей проекта
from config import logger
import state # Для доступа к user_scores
from utils import pluralize # MODIFIED: pluralize_points -> pluralize

def get_player_display(player_name: str, player_score: int, separator: str = " - ") -> str:
    icon = ""
    if player_score > 0:
        if player_score >= 1000: icon = "🌟" # Легенда
        elif player_score >= 500: icon = "🏆" # Чемпион
        elif player_score >= 100: icon = "👑" # Лапочка
        elif player_score >= 50: icon = "🔥" # Огонь
        elif player_score >= 10: icon = "👍" # Новичок с очками
        else: icon = "🙂" # Мало очков
    elif player_score < 0:
        icon = "💀" # Отрицательный рейтинг
    else: # player_score == 0
        icon = "😐" # Нейтрально

    # MODIFIED: pluralize_points -> pluralize, providing specific forms for "очко"
    score_text = pluralize(player_score, "очко", "очка", "очков")
    # Используем f-string, чтобы корректно вставить separator
    if separator == ":": # Обычно для сессионного рейтинга
        return f"{icon} {player_name}{separator} {score_text}"
    else: # Для общего рейтинга
        return f"{icon} {player_name} {separator} {score_text}"

async def rating_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        logger.warning("rating_command: message or effective_chat is None.")
        return
    chat_id_str = str(update.effective_chat.id)
    reply_text_to_send = ""

    if chat_id_str not in state.user_scores or not state.user_scores[chat_id_str]:
        reply_text_to_send = "В этом чате еще нет статистики игроков."
    else:
        # Сортируем по убыванию очков, затем по имени (для стабильности при равных очках)
        sorted_scores_list = sorted(
            state.user_scores[chat_id_str].items(),
            key=lambda item: (-item[1].get("score", 0), item[1].get("name", "").lower())
        )

        if not sorted_scores_list: # Should be caught by the first if, but good for robustness
            reply_text_to_send = "Пока нет игроков с набранными очками в этом чате."
        else:
            top_players_text_parts = ["📊 Топ-10 игроков в этом чате (/rating):\n"]
            for i, (user_id, data) in enumerate(sorted_scores_list[:10]):
                player_name = data.get('name', f'Игрок {user_id}')
                player_score = data.get('score', 0)
                rank_prefix = f"{i+1}."
                # Медальки для первых трех мест с положительным счетом
                if player_score > 0:
                    if i == 0: rank_prefix = "🥇"
                    elif i == 1: rank_prefix = "🥈"
                    elif i == 2: rank_prefix = "🥉"
                
                top_players_text_parts.append(f"{rank_prefix} {get_player_display(player_name, player_score)}")
            reply_text_to_send = "\n".join(top_players_text_parts)

    logger.debug(f"Attempting to send chat rating to {chat_id_str}. Text: '{reply_text_to_send[:100]}...'")
    await update.message.reply_text(reply_text_to_send) # No parse_mode needed as get_player_display returns plain text with emoji

async def global_top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat: # effective_chat нужен для chat_id в логах
         logger.warning("global_top_command: message or effective_chat is None.")
         return

    chat_id_str = str(update.effective_chat.id) # Для логгирования, откуда пришла команда
    reply_text_to_send = ""

    if not state.user_scores:
        reply_text_to_send = "Пока нет данных о рейтингах игроков ни в одном чате."
    else:
        aggregated_global_scores: Dict[str, Dict[str, Any]] = {} # {user_id: {"name": str, "total_score": int}}
        for users_in_chat_data in state.user_scores.values(): # Итерируемся по значениям (словарям юзеров в чате)
            for user_id, data in users_in_chat_data.items():
                user_name = data.get("name", f"Игрок {user_id}")
                user_chat_score = data.get("score", 0)

                if user_id not in aggregated_global_scores:
                    aggregated_global_scores[user_id] = {"name": user_name, "total_score": 0}
                
                aggregated_global_scores[user_id]["total_score"] += user_chat_score
                # Обновляем имя на самое "полное" или последнее встреченное, если текущее короче
                if len(user_name) > len(aggregated_global_scores[user_id]["name"]):
                     aggregated_global_scores[user_id]["name"] = user_name
                # Или если имя было "Игрок X", а стало нормальным
                elif aggregated_global_scores[user_id]["name"].startswith("Игрок ") and not user_name.startswith("Игрок "):
                     aggregated_global_scores[user_id]["name"] = user_name
        
        if not aggregated_global_scores:
            reply_text_to_send = "Нет игроков для отображения в глобальном рейтинге."
        else:
            # Сортируем по убыванию общего счета, затем по имени
            sorted_global_scores = sorted(
                aggregated_global_scores.items(),
                key=lambda item: (-item[1]["total_score"], item[1]["name"].lower())
            )

            global_top_text_parts = ["🌍 Глобальный Топ-10 игроков (/globaltop):\n"]
            for i, (user_id, data) in enumerate(sorted_global_scores[:10]):
                player_name = data["name"]
                player_total_score = data["total_score"]
                rank_prefix = f"{i+1}."
                if player_total_score > 0:
                    if i == 0: rank_prefix = "🥇"
                    elif i == 1: rank_prefix = "🥈"
                    elif i == 2: rank_prefix = "🥉"
                
                global_top_text_parts.append(f"{rank_prefix} {get_player_display(player_name, player_total_score)}")
            reply_text_to_send = "\n".join(global_top_text_parts)
            
    logger.debug(f"Attempting to send global rating (invoked in {chat_id_str}). Text: '{reply_text_to_send[:100]}...'")
    await update.message.reply_text(reply_text_to_send) # No parse_mode needed
