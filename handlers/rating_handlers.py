# handlers/rating_handlers.py
from telegram import Update
from telegram.ext import ContextTypes

from config import logger
import state
from utils import plural_pts # Renamed function

def get_player_display(p_name: str, p_score: int, sep: str = " - ") -> str: # Renamed args
    icon = ""
    if p_score > 0:
        if p_score >= 1000: icon = "🌟"
        elif p_score >= 500: icon = "🏆"
        elif p_score >= 100: icon = "👑"
        elif p_score >= 50: icon = "🔥"
        elif p_score >= 10: icon = "👍"
        else: icon = "🙂"
    elif p_score < 0: icon = "💀"
    else: icon = "😐"
    # Adjusted separator logic to match prompt example output for quiz_logic.py
    if sep == ":":
         return f"{icon} {p_name}{sep} {plural_pts(p_score)}"
    return f"{icon} {p_name} {sep} {plural_pts(p_score)}"


async def rating_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat: return
    cid_str = str(update.effective_chat.id) # Renamed
    reply_txt = "" # Renamed

    if cid_str not in state.usr_scores or not state.usr_scores[cid_str]:
        reply_txt = "В этом чате еще нет статистики игроков."
    else:
        sorted_sc_list = sorted( # Renamed
            state.usr_scores[cid_str].items(),
            key=lambda item: (-item[1].get("score", 0), item[1].get("name", "").lower())
        )
        if not sorted_sc_list:
            reply_txt = "Пока нет игроков с очками в этом чате."
        else:
            top_parts = ["📊 Топ-10 игроков в этом чате (/rating):\n"] # Renamed
            for i, (uid, data) in enumerate(sorted_sc_list[:10]): # Renamed user_id to uid
                p_name = data.get('name', f'Игрок {uid}') # Renamed
                p_score = data.get('score', 0) # Renamed
                rank_pfx = f"{i+1}." # Renamed
                if p_score > 0: # Check score before assigning medal
                    if i == 0: rank_pfx = "🥇"
                    elif i == 1: rank_pfx = "🥈"
                    elif i == 2: rank_pfx = "🥉"
                top_parts.append(f"{rank_pfx} {get_player_display(p_name, p_score)}")
            reply_txt = "\n".join(top_parts)
    await update.message.reply_text(reply_txt)

async def global_top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat: return
    # cid_str = str(update.effective_chat.id) # Not used
    reply_txt = ""

    if not state.usr_scores:
        reply_txt = "Пока нет данных о рейтингах игроков."
    else:
        agg_g_scores: Dict[str, Dict[str, Any]] = {} # Renamed
        for users_in_chat in state.usr_scores.values(): # Renamed
            for uid, data in users_in_chat.items(): # Renamed user_id to uid
                usr_name = data.get("name", f"Игрок {uid}") # Renamed
                chat_score = data.get("score", 0) # Renamed

                if uid not in agg_g_scores:
                    agg_g_scores[uid] = {"name": usr_name, "total_score": 0}
                
                # Use the longest or non-generic name encountered for the user
                current_agg_name = agg_g_scores[uid]["name"]
                if len(usr_name) > len(current_agg_name) or \
                   (current_agg_name.startswith("Игрок ") and not usr_name.startswith("Игрок ")):
                     agg_g_scores[uid]["name"] = usr_name
                
                agg_g_scores[uid]["total_score"] += chat_score


        if not agg_g_scores:
            reply_txt = "Нет игроков для глобального рейтинга."
        else:
            sorted_g_scores = sorted( # Renamed
                agg_g_scores.items(),
                key=lambda item: (-item[1]["total_score"], item[1]["name"].lower())
            )
            g_top_parts = ["🌍 Глобальный Топ-10 игроков (/globaltop):\n"] # Renamed
            for i, (uid, data) in enumerate(sorted_g_scores[:10]):
                p_name = data["name"]
                total_score = data["total_score"] # Renamed
                rank_pfx = f"{i+1}."
                if total_score > 0: # Check score before assigning medal
                    if i == 0: rank_pfx = "🥇"
                    elif i == 1: rank_pfx = "🥈"
                    elif i == 2: rank_pfx = "🥉"
                g_top_parts.append(f"{rank_pfx} {get_player_display(p_name, total_score)}")
            reply_txt = "\n".join(g_top_parts)
    await update.message.reply_text(reply_txt)
