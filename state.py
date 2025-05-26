# state.py
from typing import List, Dict, Any, Set, Optional
import datetime # Added for pending_scheduled_quizzes type hint

# --- Глобальные переменные состояния ---
# Эти словари хранят данные во время работы бота.
# Они импортируются и используются другими модулями для доступа и изменения состояния.

# qs_data: {category_name: [question_dict, ...]}
# Загружается из questions.json модулем data_manager.py
# Используется в quiz_logic.py для получения вопросов, command_handlers.py для /categories
qs_data: Dict[str, List[Dict[str, Any]]] = {}

# usr_scores: {chat_id: {user_id: {"name": str, "score": int, "answered_polls": set, "milestones_achieved": set}}}
# Загружается из users.json и сохраняется модулем data_manager.py
# Обновляется в command_handlers.py (/start) и poll_answer_handler.py
usr_scores: Dict[str, Dict[str, Any]] = {}

# cur_polls: {poll_id: poll_details_dict}
# Хранит информацию о текущих активных опросах (Poll).
# Обновляется в command_handlers.py (/quiz) и quiz_logic.py (для /quiz10).
# Используется в poll_answer_handler.py для проверки ответов.
cur_polls: Dict[str, Dict[str, Any]] = {}

# cur_q_sessions: {chat_id: session_details_dict}
# Хранит информацию об активных сессиях /quiz10.
# Управляется в command_handlers.py (/quiz10, /stopquiz) и quiz_logic.py.
# Используется в poll_answer_handler.py.
cur_q_sessions: Dict[str, Dict[str, Any]] = {}

# pend_sched_qs: {chat_id: {"job_name": str, "category_name": str or None, "scheduled_time": datetime, "starter_user_id": str}}
# Хранит информацию о квизах /quiz10notify, которые были анонсированы и ожидают запуска.
pend_sched_qs: Dict[str, Dict[str, Any]] = {}

# daily_q_subs: {chat_id_str: {"hour": int, "minute": int, "categories": Optional[List[str]]}}
# Хранит ID чатов, подписанных на ежедневную викторину, и их настройки.
# Загружается и сохраняется модулем data_manager.py
daily_q_subs: Dict[str, Dict[str, Any]] = {}

# active_daily_qs: {chat_id_str: {"current_question_index": int, "questions": list, "job_name_next_q": str | None}}
# Хранит состояние активных ежедневных викторин
active_daily_qs: Dict[str, Dict[str, Any]] = {}
