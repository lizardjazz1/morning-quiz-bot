#state.py
import copy
from typing import Dict, Any, Set, Optional, List, TYPE_CHECKING
from collections import defaultdict
from datetime import datetime, timedelta
from modules.logger_config import get_logger

from utils import get_current_utc_time # utils.py должен быть доступен

if TYPE_CHECKING:
    from app_config import AppConfig
    from telegram.ext import Application

logger = get_logger(__name__)

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
        self.results_message_ids: Set[int] = set() # ID сообщений с результатами викторины для удаления через 2 мин

    def get_current_question_data(self) -> Optional[Dict[str, Any]]:
        if 0 <= self.current_question_index < len(self.questions):
            return self.questions[self.current_question_index]
        return None

    def __getstate__(self):
        """
        Подготавливает объект для сериализации через pickle
        Исключает несериализуемые объекты
        """
        state = self.__dict__.copy()
        
        # Исключаем несериализуемые объекты
        if 'next_question_job_name' in state:
            del state['next_question_job_name']
            
        logger.debug(f"QuizState для чата {self.chat_id} подготовлен для сериализации")
        return state

    def __setstate__(self, state):
        """
        Восстанавливает объект после десериализации
        Устанавливает несериализуемые объекты в None
        """
        self.__dict__.update(state)
        
        # Восстанавливаем несериализуемые объекты как None
        self.next_question_job_name = None
        
        logger.debug(f"QuizState для чата {self.chat_id} восстановлен после десериализации")

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

    def add_message_for_deletion(self, chat_id: int, message_id: int, delay_seconds: int = 300) -> None:
        """
        Добавляет сообщение и планирует его удаление через delay_seconds (по умолчанию 5 минут).
        """
        self.generic_messages_to_delete[chat_id].add(message_id)
        logger.debug(f"Сообщение {message_id} добавлено для удаления в чате {chat_id}")

        # Планируем удаление через N секунд если есть application
        if self.application and hasattr(self.application, "job_queue") and self.application.job_queue:
            job_name = f"del_msg_{chat_id}_{message_id}"
            # Удаляем старый job если есть
            existing = self.application.job_queue.get_jobs_by_name(job_name)
            for job in existing:
                job.schedule_removal()
            # Планируем новый
            self.application.job_queue.run_once(
                self._delete_message_job,
                when=timedelta(seconds=delay_seconds),
                name=job_name,
                data={"chat_id": chat_id, "message_id": message_id}
            )
            logger.debug(f"Запланировано удаление сообщения {message_id} через {delay_seconds} сек")

    async def _delete_message_job(self, context) -> None:
        """Job для удаления одного сообщения через запланированное время"""
        data = context.job.data
        chat_id = data["chat_id"]
        message_id = data["message_id"]

        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            logger.debug(f"Удалено сообщение {message_id} из чата {chat_id}")
        except Exception as e:
            error_str = str(e).lower()
            if "not found" in error_str or "cant be deleted" in error_str:
                logger.debug(f"Сообщение {message_id} уже удалено или недоступно")
            else:
                logger.warning(f"Не удалось удалить сообщение {message_id}: {e}")

        # Удаляем из списка
        if chat_id in self.generic_messages_to_delete:
            self.generic_messages_to_delete[chat_id].discard(message_id)
            if not self.generic_messages_to_delete[chat_id]:
                del self.generic_messages_to_delete[chat_id]


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

    def __getstate__(self):
        """
        Подготавливает объект для сериализации через pickle
        Исключает несериализуемые объекты
        """
        state = self.__dict__.copy()
        
        # Исключаем несериализуемые объекты
        if 'application' in state:
            del state['application']
        if 'data_manager' in state:
            del state['data_manager']
        if 'app_config' in state:
            del state['app_config']
        
        # Дополнительная очистка current_polls от потенциально проблемных данных
        if 'current_polls' in state:
            cleaned_polls = {}
            for poll_id, poll_data in state['current_polls'].items():
                if isinstance(poll_data, dict):
                    # Создаем копию без потенциально проблемных полей
                    cleaned_poll = poll_data.copy()
                    # Удаляем поля, которые могут содержать несериализуемые объекты
                    cleaned_poll.pop('job_poll_end_name', None)
                    cleaned_poll.pop('next_question_job_name', None)
                    cleaned_polls[poll_id] = cleaned_poll
                else:
                    # Если poll_data не dict, пропускаем
                    logger.warning(f"Пропущен невалидный poll_data для {poll_id}: {type(poll_data)}")
            state['current_polls'] = cleaned_polls
            
        logger.debug("BotState подготовлен для сериализации (исключены несериализуемые объекты)")
        return state

    def __setstate__(self, state):
        """
        Восстанавливает объект после десериализации
        Устанавливает несериализуемые объекты в None
        """
        self.__dict__.update(state)
        
        # Восстанавливаем несериализуемые объекты как None
        self.application = None
        self.data_manager = None
        self.app_config = None
        
        logger.debug("BotState восстановлен после десериализации (несериализуемые объекты установлены в None)")

    def prepare_for_persistence(self):
        """
        Подготавливает состояние для сохранения через persistence
        Очищает несериализуемые объекты
        """
        # Временно очищаем несериализуемые объекты
        self.application = None
        self.data_manager = None
        self.app_config = None
        
        # Очищаем current_polls от потенциально проблемных данных
        if hasattr(self, 'current_polls'):
            cleaned_polls = {}
            for poll_id, poll_data in self.current_polls.items():
                if isinstance(poll_data, dict):
                    cleaned_poll = poll_data.copy()
                    cleaned_poll.pop('job_poll_end_name', None)
                    cleaned_poll.pop('next_question_job_name', None)
                    cleaned_polls[poll_id] = cleaned_poll
            self.current_polls = cleaned_polls
        
        logger.debug("BotState подготовлен для persistence (временная очистка)")
        
    def restore_after_persistence(self, app_config, data_manager=None):
        """
        Восстанавливает несериализуемые объекты после загрузки из persistence
        """
        self.app_config = app_config
        self.data_manager = data_manager
        logger.debug("BotState восстановлен после persistence")

