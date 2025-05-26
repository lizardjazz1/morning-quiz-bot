# state.py
from typing import List, Dict, Any, Set

# --- Глобальные переменные состояния ---
# Эти словари хранят данные во время работы бота.
# Они импортируются и используются другими модулями для доступа и изменения состояния.

# quiz_data: {category_name: [question_dict, ...]}
# Загружается из questions.json модулем data_manager.py
# Используется в quiz_logic.py для получения вопросов, command_handlers.py для /categories
quiz_data: Dict[str, List[Dict[str, Any]]] = {}

# user_scores: {chat_id: {user_id: {"name": str, "score": int, "answered_polls": set, "milestones_achieved": set}}}
# Загружается из users.json и сохраняется модулем data_manager.py
# Обновляется в command_handlers.py (/start) и poll_answer_handler.py
user_scores: Dict[str, Dict[str, Any]] = {}

# current_poll: {poll_id: poll_details_dict}
# Хранит информацию о текущих активных опросах (Poll).
# Обновляется в command_handlers.py (/quiz) и quiz_logic.py (для /quiz10).
# Используется в poll_answer_handler.py для проверки ответов.
current_poll: Dict[str, Dict[str, Any]] = {}

# current_quiz_session: {chat_id: session_details_dict}
# Хранит информацию об активных сессиях /quiz10.
# Управляется в command_handlers.py (/quiz10, /stopquiz) и quiz_logic.py.
# Используется в poll_answer_handler.py.
current_quiz_session: Dict[str, Dict[str, Any]] = {}

# pending_scheduled_quizzes: {chat_id: {"job_name": str, "category_name": str or None, "scheduled_time": datetime, "starter_user_id": str}}
# Хранит информацию о квизах /quiz10notify, которые были анонсированы и ожидают запуска.
pending_scheduled_quizzes: Dict[str, Dict[str, Any]] = {}

# daily_quiz_subscriptions: {chat_id_str}
# Хранит ID чатов, подписанных на ежедневную викторину.
# Загружается и сохраняется модулем data_manager.py
daily_quiz_subscriptions: Set[str] = set()

# active_daily_quizzes: {chat_id_str: {"current_question_index": int, "questions": list, "job_name_next_q": str | None}}
# Хранит состояние активных ежедневных викторин
active_daily_quizzes: Dict[str, Dict[str, Any]] = {}

