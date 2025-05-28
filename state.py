#state.py
import logging
import copy
from typing import Dict, Any, Set, Optional, List, TYPE_CHECKING
from collections import defaultdict
from datetime import datetime

from utils import get_current_utc_time

if TYPE_CHECKING:
    from app_config import AppConfig

logger = logging.getLogger(__name__)

class QuizState:
    def __init__(self,
                 chat_id: int,
                 quiz_type: str,
                 quiz_mode: str,
                 questions: List[Dict[str, Any]],
                 num_questions_to_ask: int,
                 open_period_seconds: int,
                 created_by_user_id: Optional[int] = None,
                 original_command_message_id: Optional[int] = None,
                 announce_message_id: Optional[int] = None,
                 interval_seconds: Optional[int] = None,
                 quiz_start_time: Optional[datetime] = None
                 ):

        self.chat_id: int = chat_id
        self.quiz_type: str = quiz_type
        self.quiz_mode: str = quiz_mode
        self.questions: List[Dict[str, Any]] = questions
        self.num_questions_to_ask: int = num_questions_to_ask
        self.open_period_seconds: int = open_period_seconds
        
        self.created_by_user_id: Optional[int] = created_by_user_id
        self.original_command_message_id: Optional[int] = original_command_message_id
        self.announce_message_id: Optional[int] = announce_message_id
        self.interval_seconds: Optional[int] = interval_seconds
        self.quiz_start_time: datetime = quiz_start_time if quiz_start_time else get_current_utc_time()

        self.current_question_index: int = 0
        self.scores: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"name": "", "score": 0, "answered_this_session_polls": set()})

        self.current_poll_id: Optional[str] = None
        self.current_poll_message_id: Optional[int] = None
        self.question_start_time: Optional[datetime] = None

        self.message_ids_to_delete: Set[int] = set()
        self.is_stopping: bool = False
        self.next_question_job_name: Optional[str] = None
        self.current_poll_end_job_name: Optional[str] = None

    def get_current_question_data(self) -> Optional[Dict[str, Any]]:
        if 0 <= self.current_question_index < len(self.questions):
            return self.questions[self.current_question_index]
        return None

class BotState:
    def __init__(self, app_config: 'AppConfig'):
        self.app_config: 'AppConfig' = app_config
        
        self.active_quizzes: Dict[int, QuizState] = {}
        self.current_polls: Dict[str, Dict[str, Any]] = {}

        self.quiz_data: Dict[str, List[Dict[str, Any]]] = {}
        self.user_scores: Dict[str, Any] = {}
        self.chat_settings: Dict[int, Dict[str, Any]] = {}

        self.global_command_cooldowns: Dict[str, Dict[int, datetime]] = defaultdict(dict)
        self.generic_messages_to_delete: Dict[int, Set[int]] = defaultdict(set)

    def get_active_quiz(self, chat_id: int) -> Optional[QuizState]:
        return self.active_quizzes.get(chat_id)

    def add_active_quiz(self, chat_id: int, quiz_state: QuizState) -> None:
        self.active_quizzes[chat_id] = quiz_state

    def remove_active_quiz(self, chat_id: int) -> Optional[QuizState]:
        return self.active_quizzes.pop(chat_id, None)

    def get_current_poll_data(self, poll_id: str) -> Optional[Dict[str, Any]]:
        return self.current_polls.get(poll_id)

    def add_current_poll(self, poll_id: str, poll_data: Dict[str, Any]) -> None:
        self.current_polls[poll_id] = poll_data
    
    def remove_current_poll(self, poll_id: str) -> Optional[Dict[str, Any]]:
        return self.current_polls.pop(poll_id, None)

    def get_chat_settings(self, chat_id: int) -> Dict[str, Any]:
        if chat_id in self.chat_settings:
            return copy.deepcopy(self.chat_settings[chat_id])
        return copy.deepcopy(self.app_config.default_chat_settings)

    def update_chat_settings(self, chat_id: int, new_settings: Dict[str, Any]) -> None:
        self.chat_settings[chat_id] = new_settings
