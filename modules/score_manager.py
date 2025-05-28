# modules/score_manager.py
import logging
from typing import Dict, Any, Set, Optional, Tuple, List

from telegram import User as TelegramUser

# ИСПРАВЛЕНО: Абсолютный импорт utils и других корневых модулей (если бы они были нужны здесь)
from utils import pluralize, escape_markdown_v2, get_mention_html
# Если бы State, AppConfig, DataManager импортировались напрямую, было бы:
# from state import BotState
# from app_config import AppConfig
# from data_manager import DataManager
# Но они передаются через конструктор, так что эти строки не нужны.

logger = logging.getLogger(__name__)

class ScoreManager:
    def __init__(self, app_config: 'AppConfig', state: 'BotState', data_manager: 'DataManager'):
        self.app_config = app_config
        self.state = state
        self.data_manager = data_manager
        self.motivational_messages: Dict[int, str] = self.app_config.parsed_motivational_messages

    def _ensure_user_initialized(self, chat_id: int, user: TelegramUser) -> Dict[str, Any]:
        chat_id_str = str(chat_id)
        user_id_str = str(user.id)
        self.state.user_scores.setdefault(chat_id_str, {})
        user_data = self.state.user_scores[chat_id_str].get(user_id_str)
        if user_data is None:
            user_data = {"name": user.full_name, "score": 0, "answered_polls": set(), "milestones_achieved": set()}
            self.state.user_scores[chat_id_str][user_id_str] = user_data
        else:
            user_data["name"] = user.full_name # Update name
            user_data.setdefault("answered_polls", set()) # Ensure keys exist as sets
            user_data.setdefault("milestones_achieved", set())
            if not isinstance(user_data["answered_polls"], set): user_data["answered_polls"] = set(user_data["answered_polls"])
            if not isinstance(user_data["milestones_achieved"], set): user_data["milestones_achieved"] = set(user_data["milestones_achieved"])
        return user_data

    async def update_score_and_get_motivation(
        self, chat_id: int, user: TelegramUser, poll_id: str, is_correct: bool, quiz_type_of_poll: str
    ) -> Tuple[bool, Optional[str]]:
        user_chat_data = self._ensure_user_initialized(chat_id, user)
        user_id_str = str(user.id)
        score_updated_this_time = False
        motivational_message_to_send: Optional[str] = None
        previous_score = user_chat_data["score"]

        if poll_id not in user_chat_data["answered_polls"]:
            score_change = 1 if is_correct else -1
            user_chat_data["score"] += score_change
            user_chat_data["answered_polls"].add(poll_id)
            score_updated_this_time = True
            logger.info(f"User '{user.full_name}' score in chat {chat_id} for poll {poll_id}: {score_change:+}. New score: {user_chat_data['score']}.")

            current_score = user_chat_data["score"]
            milestones_achieved = user_chat_data["milestones_achieved"]
            for threshold in sorted(self.motivational_messages.keys()):
                if threshold not in milestones_achieved:
                    if (threshold > 0 and previous_score < threshold <= current_score) or \
                       (threshold < 0 and previous_score > threshold >= current_score):
                        motivational_text = self.motivational_messages[threshold]
                        try:
                            motivational_message_to_send = motivational_text.format(
                                user_name=user.first_name, user_score=current_score
                            )
                        except KeyError: # If format keys are missing
                            motivational_message_to_send = motivational_text
                        milestones_achieved.add(threshold)
                        break
            self.data_manager.save_user_scores()
        else:
            logger.debug(f"User {user_id_str} already answered poll {poll_id} in chat {chat_id}.")

        active_quiz = self.state.get_active_quiz(chat_id)
        if active_quiz and active_quiz.quiz_type in ["session", "daily"] and active_quiz.current_poll_id == poll_id:
            session_user_data = active_quiz.session_scores.setdefault(
                user_id_str, {"name": user.full_name, "score": 0, "answered_this_session_polls": set()}
            )
            session_user_data["name"] = user.full_name
            if poll_id not in session_user_data["answered_this_session_polls"]:
                session_score_change = 1 if is_correct else -1
                session_user_data["score"] += session_score_change
                session_user_data["answered_this_session_polls"].add(poll_id)
        return score_updated_this_time, motivational_message_to_send

    def get_chat_rating(self, chat_id: int, top_n: int = 10) -> List[Dict[str, Any]]:
        chat_id_str = str(chat_id)
        chat_scores = self.state.user_scores.get(chat_id_str, {})
        if not chat_scores: return []
        sorted_scores = sorted(chat_scores.items(), key=lambda item: (-item[1].get("score", 0), item[1].get("name", "").lower()))
        return [{"user_id": uid, "name": data.get("name", f"UID {uid}"), "score": data.get("score", 0)} for uid, data in sorted_scores[:top_n]]

    def get_global_rating(self, top_n: int = 10) -> List[Dict[str, Any]]:
        aggregated: Dict[str, Dict[str, Any]] = {}
        for chat_data in self.state.user_scores.values():
            for user_id_str, data in chat_data.items():
                if user_id_str not in aggregated:
                    aggregated[user_id_str] = {"name": data.get("name", f"UID {user_id_str}"), "total_score": 0}
                aggregated[user_id_str]["total_score"] += data.get("score", 0)
                if len(data.get("name", "")) > len(aggregated[user_id_str]["name"]): # Prefer longer names
                    aggregated[user_id_str]["name"] = data.get("name")
        if not aggregated: return []
        sorted_global = sorted(aggregated.items(), key=lambda item: (-item[1]["total_score"], item[1]["name"].lower()))
        return [{"user_id": uid, "name": data["name"], "score": data["total_score"]} for uid, data in sorted_global[:top_n]]

    def get_user_stats_in_chat(self, chat_id: int, user_id_str: str) -> Optional[Dict[str, Any]]:
        chat_id_s = str(chat_id)
        user_data = self.state.user_scores.get(chat_id_s, {}).get(user_id_str)
        if user_data:
            return {
                "name": user_data.get("name", f"UID {user_id_str}"),
                "score": user_data.get("score", 0),
                "answered_polls_count": len(user_data.get("answered_polls", set()))
            }
        return None

    def format_scores(self, scores_list: List[Dict[str, Any]], title: str,
                      is_session_score: bool = False, num_questions_in_session: Optional[int] = None) -> str:
        if not scores_list:
            return f"{escape_markdown_v2(title)}\n\nПока нет данных для отображения."
        text_parts = [f"*{escape_markdown_v2(title)}*\n"]
        medals = ["🥇", "🥈", "🥉"]
        for i, player_data in enumerate(scores_list):
            name = escape_markdown_v2(player_data.get("name", "Неизвестный"))
            score = player_data.get("score", 0)
            rank_prefix = f"{i + 1}\\."
            if i < len(medals) and score > 0: rank_prefix = medals[i]
            score_display = pluralize(score, "очко", "очка", "очков")
            if is_session_score and num_questions_in_session is not None:
                 score_display = f"{score} {pluralize(score, 'балл', 'балла', 'баллов')} из {num_questions_in_session} вопр\\."
            text_parts.append(f"{rank_prefix} {name} \\- {escape_markdown_v2(score_display)}")
        return "\n".join(text_parts)

