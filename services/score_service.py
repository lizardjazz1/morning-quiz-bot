# services/score_service.py

import logging
from storage.data_loader import save_json

DATA_PATH = "users.json"
logger = logging.getLogger(__name__)


def init_user_scores(context):
    if not context.bot_data.get("user_scores"):
        context.bot_data["user_scores"] = {}


def update_user_score(chat_id, user_id, user_name, context, points=1):
    chat_id = str(chat_id)
    user_id = str(user_id)

    if chat_id not in context.bot_data["user_scores"]:
        context.bot_data["user_scores"][chat_id] = {}

    scores = context.bot_data["user_scores"][chat_id]

    if user_id not in scores:
        scores[user_id] = {"name": user_name, "score": points}
    else:
        scores[user_id]["score"] += points

    save_json(DATA_PATH, context.bot_data["user_scores"])
    return scores[user_id]["score"]