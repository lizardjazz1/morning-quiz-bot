# bot/modules/score_manager.py
import logging
from typing import Dict, Any, Set, Optional, Tuple, List

from telegram import User as TelegramUser

# from ..app_config import AppConfig # Через конструктор
# from ..state import BotState # Через конструктор
# from ..data_manager import DataManager # Через конструктор

logger = logging.getLogger(__name__)

class ScoreManager:
    def __init__(self, app_config: 'AppConfig', state: 'BotState', data_manager: 'DataManager'):
        self.app_config = app_config
        self.state = state
        self.data_manager = data_manager
        # Мотивационные сообщения уже распарсены в app_config.parsed_motivational_messages
        self.motivational_messages: Dict[int, str] = self.app_config.parsed_motivational_messages

    def _ensure_user_initialized(self, chat_id: int, user: TelegramUser) -> Dict[str, Any]:
        """
        Гарантирует, что пользователь существует в user_scores для данного чата,
        и возвращает его данные. Chat_id - int, user_id - str.
        """
        chat_id_str = str(chat_id) # Ключи в user_scores - строки для chat_id
        user_id_str = str(user.id)

        self.state.user_scores.setdefault(chat_id_str, {})
        
        user_data = self.state.user_scores[chat_id_str].get(user_id_str)
        if user_data is None:
            user_data = {
                "name": user.full_name,
                "score": 0,
                "answered_polls": set(), # Set[str] - poll_id
                "milestones_achieved": set() # Set[int] - пороги очков
            }
            self.state.user_scores[chat_id_str][user_id_str] = user_data
        else:
            # Обновляем имя, если оно изменилось
            user_data["name"] = user.full_name
            # Гарантируем, что answered_polls и milestones_achieved являются множествами
            if not isinstance(user_data.get("answered_polls"), set):
                user_data["answered_polls"] = set(user_data.get("answered_polls", []))
            if not isinstance(user_data.get("milestones_achieved"), set):
                user_data["milestones_achieved"] = set(user_data.get("milestones_achieved", []))
        return user_data

    async def update_score_and_get_motivation(
        self,
        chat_id: int, # ID чата, где произошел ответ
        user: TelegramUser,
        poll_id: str,
        is_correct: bool,
        quiz_type_of_poll: str # "single", "session", "daily" (из poll_info_from_state)
    ) -> Tuple[bool, Optional[str]]:
        """
        Обновляет глобальный счет пользователя и сессионный (если применимо).
        Возвращает кортеж: (был ли изменен глобальный счет этим ответом, текст мотивационного сообщения или None).
        """
        global_user_data = self._ensure_user_initialized(chat_id, user)
        user_id_str = str(user.id)
        
        score_updated_this_time = False
        motivational_message_to_send: Optional[str] = None
        
        previous_global_score = global_user_data["score"]

        if poll_id not in global_user_data["answered_polls"]:
            score_change = 1 if is_correct else -1
            global_user_data["score"] += score_change
            global_user_data["answered_polls"].add(poll_id)
            score_updated_this_time = True
            
            logger.info(
                f"User '{user.full_name}' ({user_id_str}) in chat {chat_id} answered poll {poll_id} "
                f"{'correctly' if is_correct else 'incorrectly'} (quiz_type: {quiz_type_of_poll}). "
                f"Global score change: {score_change:+}. New global score: {global_user_data['score']}."
            )

            current_global_score = global_user_data["score"]
            milestones_achieved_set = global_user_data["milestones_achieved"]

            # Проверка и формирование мотивационных сообщений
            for threshold in sorted(self.motivational_messages.keys()): # Используем self.motivational_messages
                if threshold in milestones_achieved_set:
                    continue

                send_motivational = False
                if threshold > 0: # Позитивные пороги
                    if previous_global_score < threshold <= current_global_score:
                        send_motivational = True
                elif threshold < 0: # Негативные пороги
                    if previous_global_score > threshold >= current_global_score: # score упал ниже порога
                        send_motivational = True
                
                if send_motivational:
                    motivational_text_template = self.motivational_messages[threshold]
                    # Форматируем имя пользователя (можно добавить first_name, full_name и т.д. в шаблон)
                    motivational_message_to_send = motivational_text_template.format(
                        user_name=user.first_name, # или user.full_name
                        user_score=current_global_score # Можно добавить текущий счет в сообщение
                    )
                    milestones_achieved_set.add(threshold)
                    logger.debug(f"Prepared motivational message for {threshold} score for user {user_id_str}.")
                    # Отправка сообщения будет в poll_answer_handler
                    break # Обычно одно мотивационное сообщение за раз

            self.data_manager.save_user_data() # Сохраняем после всех обновлений глобального счета
        else:
            logger.debug(
                f"User {user.full_name} ({user_id_str}) already answered poll {poll_id}. "
                "Global score not changed by this specific answer."
            )

        # Обновление сессионного счета (если это сессионная или ежедневная викторина)
        active_quiz_session = self.state.active_quizzes.get(chat_id) # chat_id здесь int
        if active_quiz_session and \
           active_quiz_session["quiz_type"] in ["session", "daily"] and \
           active_quiz_session.get("current_poll_id") == poll_id: # Убедимся, что это текущий опрос сессии

            session_scores = active_quiz_session.setdefault("session_scores", {})
            user_session_data = session_scores.setdefault(
                user_id_str,
                {"name": user.full_name, "score": 0, "answered_this_session_polls": set()}
            )
            user_session_data["name"] = user.full_name # Обновить имя
            
            # Гарантируем, что answered_this_session_polls является множеством
            if not isinstance(user_session_data.get("answered_this_session_polls"), set):
                 user_session_data["answered_this_session_polls"] = set(user_session_data.get("answered_this_session_polls", []))

            if poll_id not in user_session_data["answered_this_session_polls"]:
                session_score_change = 1 if is_correct else -1
                user_session_data["score"] += session_score_change
                user_session_data["answered_this_session_polls"].add(poll_id)
                logger.info(
                    f"User {user.full_name} ({user_id_str}) session score in chat {chat_id} "
                    f"changed by {session_score_change:+} for poll {poll_id}. "
                    f"New session score: {user_session_data['score']}."
                )
        return score_updated_this_time, motivational_message_to_send

    def get_chat_rating(self, chat_id: int, top_n: int = 10) -> List[Dict[str, Any]]:
        """Возвращает топ-N игроков для указанного чата. chat_id - int."""
        chat_id_str = str(chat_id)
        if chat_id_str not in self.state.user_scores or not self.state.user_scores[chat_id_str]:
            return []
        
        # Сортируем по убыванию очков, затем по имени (алфавитный порядок)
        sorted_scores = sorted(
            self.state.user_scores[chat_id_str].items(),
            key=lambda item: (-item[1].get("score", 0), item[1].get("name", "").lower())
        )
        
        top_players = []
        for user_id_str, data in sorted_scores[:top_n]:
            top_players.append({
                "user_id": user_id_str, # ID пользователя (строка)
                "name": data.get("name", f"Игрок {user_id_str}"),
                "score": data.get("score", 0)
            })
        return top_players

    def get_global_rating(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """Возвращает глобальный топ-N игроков."""
        if not self.state.user_scores:
            return []

        aggregated_scores: Dict[str, Dict[str, Any]] = {} # {user_id_str: {"name": str, "total_score": int}}
        
        for users_in_chat_data in self.state.user_scores.values(): # users_in_chat_data это Dict[str(user_id), user_details_dict]
            for user_id_str, data in users_in_chat_data.items():
                user_name = data.get("name", f"Игрок {user_id_str}")
                user_chat_score = data.get("score", 0)

                if user_id_str not in aggregated_scores:
                    aggregated_scores[user_id_str] = {"name": user_name, "total_score": 0}
                
                aggregated_scores[user_id_str]["total_score"] += user_chat_score
                # Обновляем имя, если нашли более полное/актуальное
                if len(user_name) > len(aggregated_scores[user_id_str]["name"]) or \
                   (aggregated_scores[user_id_str]["name"].startswith("Игрок ") and not user_name.startswith("Игрок ")):
                    aggregated_scores[user_id_str]["name"] = user_name
                    
        if not aggregated_scores:
            return []
            
        sorted_global = sorted(
            aggregated_scores.items(),
            key=lambda item: (-item[1]["total_score"], item[1]["name"].lower())
        )
        
        top_players = []
        for user_id_str, data in sorted_global[:top_n]:
            top_players.append({
                "user_id": user_id_str,
                "name": data["name"],
                "score": data["total_score"] # Используем "score" для консистентности с get_chat_rating
            })
        return top_players

    def get_user_stats_in_chat(self, chat_id: int, user_id: str) -> Optional[Dict[str, Any]]:
        """Возвращает статистику пользователя в конкретном чате."""
        chat_id_str = str(chat_id)
        user_data = self.state.user_scores.get(chat_id_str, {}).get(user_id)
        if user_data:
            return {
                "name": user_data.get("name", f"Игрок {user_id}"),
                "score": user_data.get("score", 0),
                "answered_polls_count": len(user_data.get("answered_polls", set()))
            }
        return None

    def format_scores(
        self,
        scores_list: List[Dict[str, Any]], # Список словарей вида {"name": str, "score": int}
        title: str,
        is_session_score: bool = False, # Для сессии можно добавить кол-во правильных из общего числа
        num_questions_in_session: Optional[int] = None
        ) -> str:
        """Универсальная функция для форматирования списка очков в текстовое сообщение."""
        if not scores_list:
            return f"{title}\n\nПока нет данных для отображения."

        from ..utils import pluralize, escape_markdown_v2 # Локальный импорт для избежания циклов на уровне модуля

        text_parts = [f"*{escape_markdown_v2(title)}*\n"]
        medals = ["🥇", "🥈", "🥉"]

        for i, player_data in enumerate(scores_list):
            name = escape_markdown_v2(player_data.get("name", "Неизвестный игрок"))
            score = player_data.get("score", 0)
            
            rank_prefix = f"{i + 1}\\."
            if i < len(medals) and score > 0 : # Медали только за положительный счет
                 rank_prefix = medals[i]
            
            score_str = pluralize(score, "очко", "очка", "очков")
            if is_session_score and num_questions_in_session is not None:
                # Для сессии показываем "X из Y вопросов" (примерно, если 1 балл за вопрос)
                # Точнее было бы хранить кол-во правильных ответов в сессии, а не только счет
                # Пока просто покажем счет и общее кол-во вопросов.
                score_display = f"{score} {pluralize(score, 'балл', 'балла', 'баллов')} из {num_questions_in_session} вопр\\."
            else:
                score_display = score_str

            text_parts.append(f"{rank_prefix} {name} \\- {escape_markdown_v2(score_display)}")
        
        return "\n".join(text_parts)

