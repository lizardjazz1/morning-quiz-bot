# bot/state.py
import logging
from typing import Dict, Any, Set, Optional, Tuple, List
from collections import defaultdict
# from telegram import Message # Этот импорт не используется, можно удалить

logger = logging.getLogger(__name__)

class QuizState:
    def __init__(self, quiz_type: str, message_id: int, chat_id: int, user_id: int,
                 questions: List[Dict[str, Any]], current_question_index: int = 0,
                 user_answers: Optional[Dict[int, Any]] = None, # question_index -> user_answer
                 poll_ids: Optional[Dict[int, str]] = None, # question_index -> poll_id
                 scores: Optional[Dict[str, int]] = None, # user_id_str -> score
                 participants: Optional[Set[int]] = None, # user_ids
                 correct_option_ids: Optional[Dict[int, int]] = None, # question_index -> correct_option_id
                 scheduled_job_next_question = None,
                 scheduled_job_stop_quiz = None,
                 announce_message_id: Optional[int] = None,
                 last_question_message_id: Optional[int] = None):
        self.quiz_type: str = quiz_type
        self.message_id: int = message_id
        self.chat_id: int = chat_id
        self.initiator_user_id: int = user_id
        self.questions: List[Dict[str, Any]] = questions
        self.current_question_index: int = current_question_index
        self.user_answers: Dict[int, Any] = user_answers if user_answers is not None else {}
        self.poll_ids: Dict[int, str] = poll_ids if poll_ids is not None else {}
        self.scores: Dict[str, int] = scores if scores is not None else defaultdict(int)
        self.participants: Set[int] = participants if participants is not None else set()
        self.correct_option_ids: Dict[int, int] = correct_option_ids if correct_option_ids is not None else {}
        self.scheduled_job_next_question = scheduled_job_next_question
        self.scheduled_job_stop_quiz = scheduled_job_stop_quiz
        self.announce_message_id: Optional[int] = announce_message_id
        self.last_question_message_id: Optional[int] = last_question_message_id
        logger.debug(f"QuizState создан для чата {chat_id}, тип {quiz_type}, {len(questions)} вопросов.")

    def get_current_question(self) -> Optional[Dict[str, Any]]:
        if 0 <= self.current_question_index < len(self.questions):
            return self.questions[self.current_question_index]
        return None

    def get_current_poll_id(self) -> Optional[str]:
        return self.poll_ids.get(self.current_question_index)

    def get_current_correct_option_id(self) -> Optional[int]:
        return self.correct_option_ids.get(self.current_question_index)

class BotState:  # <--- Убедитесь, что этот класс ТОЧНО так определен
    def __init__(self):
        self.active_quizzes: Dict[int, QuizState] = {}
        self.messages_to_delete: Dict[int, Set[int]] = defaultdict(set)
        self.chat_settings: Dict[int, Dict[str, Any]] = {}
        self.user_global_scores: Dict[str, int] = defaultdict(int)
        self.user_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"correct": 0, "total_answered": 0, "games_played": 0})
        self.current_polls: Dict[str, Dict[str, Any]] = {} # Для опросов вне QuizState
        self.daily_quiz_subscriptions: Dict[int, Any] = {}
        self.conversation_states: Dict[Tuple[int, int], Dict[str, Any]] = {}
        self.scheduled_jobs: Dict[str, Any] = {} # Для общих запланированных задач
        logger.info("BotState инициализирован.")

    # --- Методы для управления активными викторинами ---
    def add_active_quiz(self, chat_id: int, quiz_state: QuizState):
        self.active_quizzes[chat_id] = quiz_state
        logger.info(f"Активная викторина добавлена для чата {chat_id}")

    def get_active_quiz(self, chat_id: int) -> Optional[QuizState]:
        return self.active_quizzes.get(chat_id)

    def remove_active_quiz(self, chat_id: int) -> Optional[QuizState]:
        quiz = self.active_quizzes.pop(chat_id, None)
        if quiz:
            logger.info(f"Активная викторина удалена для чата {chat_id}")
        return quiz

    # --- Методы для управления сообщениями к удалению ---
    def add_message_to_delete(self, chat_id: int, message_id: int):
        self.messages_to_delete[chat_id].add(message_id)

    def get_messages_to_delete(self, chat_id: int) -> Set[int]:
        return self.messages_to_delete.get(chat_id, set())

    def clear_messages_to_delete(self, chat_id: int):
        if chat_id in self.messages_to_delete:
            self.messages_to_delete.pop(chat_id)
            logger.debug(f"Список сообщений для удаления очищен для чата {chat_id}")

    # --- Методы для управления настройками чата ---
    def get_chat_settings(self, chat_id: int) -> Dict[str, Any]:
        return self.chat_settings.get(chat_id, {})

    def update_chat_setting(self, chat_id: int, key: str, value: Any):
        if chat_id not in self.chat_settings:
            self.chat_settings[chat_id] = {}
        self.chat_settings[chat_id][key] = value
        logger.info(f"Настройка чата {chat_id} обновлена: {key} = {value}")

    def delete_chat_setting(self, chat_id: int, key: str):
        if chat_id in self.chat_settings and key in self.chat_settings[chat_id]:
            del self.chat_settings[chat_id][key]
            logger.info(f"Настройка '{key}' удалена для чата {chat_id}")
            if not self.chat_settings[chat_id]:
                del self.chat_settings[chat_id]
                logger.info(f"Все настройки удалены для чата {chat_id}, запись о чате удалена.")

    # --- Методы для управления глобальным рейтингом и статистикой ---
    def update_user_score(self, user_id: int, chat_id: int, points: int, correct_answer: bool):
        user_id_str = str(user_id)
        self.user_global_scores[user_id_str] += points
        
        self.user_stats[user_id_str]["total_answered"] += 1
        if correct_answer:
            self.user_stats[user_id_str]["correct"] += 1
        logger.debug(f"Рейтинг пользователя {user_id_str} обновлен на {points} очков. Правильных ответов: {self.user_stats[user_id_str]['correct']}/{self.user_stats[user_id_str]['total_answered']}.")

    def increment_games_played(self, user_id: int):
        user_id_str = str(user_id)
        self.user_stats[user_id_str]["games_played"] += 1
        logger.debug(f"Количество сыгранных игр для пользователя {user_id_str} увеличено: {self.user_stats[user_id_str]['games_played']}.")

    def get_user_global_score(self, user_id: int) -> int:
        return self.user_global_scores.get(str(user_id), 0)

    def get_user_stats(self, user_id: int) -> Dict[str, int]:
        # Возвращаем копию, чтобы избежать изменения извне, если это defaultdict(lambda: {...})
        stats = self.user_stats.get(str(user_id))
        if stats is None: # Если пользователя нет в статистике
            return {"correct": 0, "total_answered": 0, "games_played": 0}
        return stats.copy() # Возвращаем копию существующей статистики

    def get_all_global_scores(self) -> Dict[str, int]:
        return dict(self.user_global_scores)

    def get_all_user_stats(self) -> Dict[str, Dict[str, int]]:
        return {uid: stats.copy() for uid, stats in self.user_stats.items()}

    # --- Методы для ConversationHandler ---
    def set_conversation_state(self, chat_id: int, user_id: int, data: Dict[str, Any]):
        self.conversation_states[(chat_id, user_id)] = data

    def get_conversation_state(self, chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        return self.conversation_states.get((chat_id, user_id))

    def clear_conversation_state(self, chat_id: int, user_id: int):
        return self.conversation_states.pop((chat_id, user_id), None)
        
    # --- Методы для подписок на ежедневные викторины ---
    def add_daily_quiz_subscription(self, chat_id: int, time_or_settings: Any):
        self.daily_quiz_subscriptions[chat_id] = time_or_settings
        logger.info(f"Подписка на ежедневную викторину добавлена/обновлена для чата {chat_id} с настройками: {time_or_settings}")

    def remove_daily_quiz_subscription(self, chat_id: int):
        if chat_id in self.daily_quiz_subscriptions:
            del self.daily_quiz_subscriptions[chat_id]
            logger.info(f"Подписка на ежедневную викторину удалена для чата {chat_id}")

    def get_daily_quiz_subscription(self, chat_id: int) -> Optional[Any]:
        return self.daily_quiz_subscriptions.get(chat_id)

    def get_all_daily_quiz_subscriptions(self) -> Dict[int, Any]:
        return dict(self.daily_quiz_subscriptions)

    # --- Методы для текущих опросов (не связанных с викторинами QuizState) ---
    def add_current_poll(self, poll_id: str, poll_data: Dict[str, Any]):
        self.current_polls[poll_id] = poll_data
        logger.debug(f"Добавлен текущий опрос: {poll_id}, данные: {poll_data}")

    def get_current_poll_data(self, poll_id: str) -> Optional[Dict[str, Any]]:
        return self.current_polls.get(poll_id)

    def remove_current_poll(self, poll_id: str):
        if poll_id in self.current_polls:
            del self.current_polls[poll_id]
            logger.debug(f"Удален текущий опрос: {poll_id}")

# Раскомментируйте эти строки для отладки, если проблема сохранится:
# print(f"[{__name__}] Module loaded. Checking for BotState...")
# if 'BotState' in globals():
#     print(f"[{__name__}] BotState is defined in globals.")
# else:
#     print(f"[{__name__}] BotState IS NOT DEFINED in globals. Available: {list(globals().keys())}")

