#state.py
import logging
import copy
from typing import Dict, Any, Set, Optional, List, TYPE_CHECKING
from collections import defaultdict
from datetime import datetime

from utils import get_current_utc_time # utils.py должен быть доступен

if TYPE_CHECKING:
    from app_config import AppConfig
    from telegram.ext import Application

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
        self.quiz_mode: str = quiz_mode # 'single_question', 'serial_immediate', 'serial_interval'
        self.questions: List[Dict[str, Any]] = questions
        self.num_questions_to_ask: int = num_questions_to_ask
        self.open_period_seconds: int = open_period_seconds

        self.created_by_user_id: Optional[int] = created_by_user_id
        self.original_command_message_id: Optional[int] = original_command_message_id
        self.announce_message_id: Optional[int] = announce_message_id
        self.interval_seconds: Optional[int] = interval_seconds
        self.quiz_start_time: datetime = quiz_start_time if quiz_start_time else get_current_utc_time()

        self.current_question_index: int = 0
        self.scores: Dict[str, Dict[str, Any]] = {}

        self.active_poll_ids_in_session: Set[str] = set()
        self.latest_poll_id_sent: Optional[str] = None
        self.progression_triggered_for_poll: Dict[str, bool] = {}
        
        self.message_ids_to_delete: Set[int] = set()
        self.is_stopping: bool = False
        
        # ИЗМЕНЕНО: эти поля больше не нужны в QuizState, т.к. управляются для каждого опроса индивидуально
        # self.current_poll_id: Optional[str] = None 
        # self.current_poll_message_id: Optional[int] = None
        # self.question_start_time: Optional[datetime] = None
        # self.current_poll_end_job_name: Optional[str] = None
        self.next_question_job_name: Optional[str] = None # Для отложенной отправки следующего вопроса в режиме serial_interval после раннего ответа
        self.poll_and_solution_message_ids: List[Dict[str, Optional[int]]] = []

    def get_current_question_data(self) -> Optional[Dict[str, Any]]:
        if 0 <= self.current_question_index < len(self.questions):
            return self.questions[self.current_question_index]
        return None

class BotState:
    def __init__(self, app_config: 'AppConfig'):
        self.app_config: 'AppConfig' = app_config
        self.application: Optional['Application'] = None
        self.data_manager: Optional['DataManager'] = None  # Добавляем data_manager

        self.active_quizzes: Dict[int, QuizState] = {}
        self.current_polls: Dict[str, Dict[str, Any]] = {} # poll_id -> poll_data (включая chat_id, message_id, question_details, job_poll_end_name)

        self.quiz_data: Dict[str, List[Dict[str, Any]]] = {}
        self.user_scores: Dict[str, Any] = {}
        self.chat_settings: Dict[int, Dict[str, Any]] = {}
        self.global_settings: Dict[str, Any] = {}  # Глобальные настройки (статистика категорий и др.)

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
        if not hasattr(self, 'app_config') or self.app_config is None:
            logger.critical("CRITICAL: BotState.app_config не инициализирован!")
            return copy.deepcopy({})

        if chat_id in self.chat_settings:
            return copy.deepcopy(self.chat_settings[chat_id])
        return copy.deepcopy(self.app_config.default_chat_settings)

    def update_chat_settings(self, chat_id: int, new_settings: Dict[str, Any]) -> None:
        self.chat_settings[chat_id] = new_settings

    def add_message_for_deletion(self, chat_id: int, message_id: int) -> None:
        """Добавляет сообщение в список для периодического удаления"""
        self.generic_messages_to_delete[chat_id].add(message_id)
        logger.info(f"✅ Сообщение {message_id} добавлено в список для удаления в чате {chat_id}. Всего в чате: {len(self.generic_messages_to_delete[chat_id])}")
        
        # Автоматически сохраняем данные при добавлении сообщения
        try:
            if self.data_manager:
                self.data_manager.save_messages_to_delete()
                logger.info(f"💾 Данные сообщений для удаления автоматически сохранены")
            else:
                logger.warning(f"⚠️ data_manager не доступен в BotState")
        except Exception as e:
            logger.error(f"❌ Не удалось автоматически сохранить сообщения для удаления: {e}")

    def remove_message_from_deletion(self, chat_id: int, message_id: int) -> None:
        """Удаляет сообщение из списка для периодического удаления"""
        if chat_id in self.generic_messages_to_delete:
            self.generic_messages_to_delete[chat_id].discard(message_id)
            logger.info(f"❌ Сообщение {message_id} удалено из списка для удаления в чате {chat_id}. Осталось: {len(self.generic_messages_to_delete[chat_id])}")
            
            # Автоматически сохраняем данные при удалении сообщения
            try:
                if self.data_manager:
                    self.data_manager.save_messages_to_delete()
                    logger.info(f"💾 Данные сообщений для удаления автоматически сохранены")
                else:
                    logger.warning(f"⚠️ data_manager не доступен в BotState")
            except Exception as e:
                logger.error(f"❌ Не удалось автоматически сохранить сообщения для удаления: {e}")

