#poll_answer_handler.py
import logging
from typing import Optional, TYPE_CHECKING

from telegram import Update, PollAnswer, User as TelegramUser
from telegram.ext import ContextTypes, PollAnswerHandler as PTBPollAnswerHandler
from telegram.constants import ParseMode 

from utils import escape_markdown_v2 

if TYPE_CHECKING:
    from app_config import AppConfig
    from state import BotState
    from modules.score_manager import ScoreManager
    from handlers.quiz_manager import QuizManager
    from data_manager import DataManager

logger = logging.getLogger(__name__)

class CustomPollAnswerHandler:
    def __init__(
        self,
        app_config: 'AppConfig',
        state: 'BotState',
        score_manager: 'ScoreManager',
        data_manager: 'DataManager',
        quiz_manager: 'QuizManager'
    ):
        self.app_config = app_config
        self.state = state
        self.score_manager = score_manager
        self.data_manager = data_manager
        self.quiz_manager = quiz_manager

    async def handle_poll_answer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.poll_answer:
            logger.debug("handle_poll_answer: update.poll_answer is None, игнорируется.")
            return

        poll_answer: PollAnswer = update.poll_answer
        user: TelegramUser = poll_answer.user
        answered_poll_id: str = poll_answer.poll_id

        poll_info_from_state = self.state.get_current_poll_data(answered_poll_id)

        if not poll_info_from_state:
            logger.debug(
                f"Информация для poll_id {answered_poll_id} не найдена в state.current_polls. "
                f"Ответ от {user.full_name} (ID: {user.id}) проигнорирован."
            )
            return

        chat_id_int: int = poll_info_from_state["chat_id"]
        quiz_type_of_poll: str = poll_info_from_state.get("quiz_type", "unknown_type")
        correct_option_index_for_this_poll: int = poll_info_from_state["correct_option_index"]

        is_answer_correct = (
            len(poll_answer.option_ids) == 1 and
            poll_answer.option_ids[0] == correct_option_index_for_this_poll
        )

        score_was_updated, motivational_msg_text_md_escaped = await self.score_manager.update_score_and_get_motivation(
            chat_id=chat_id_int,
            user=user,
            poll_id=answered_poll_id,
            is_correct=is_answer_correct,
            quiz_type_of_poll=quiz_type_of_poll
        )

        if motivational_msg_text_md_escaped:
            try:
                await context.bot.send_message(
                    chat_id=user.id, 
                    text=motivational_msg_text_md_escaped,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            except Exception as e:
                logger.error(f"Не удалось отправить мотивационное сообщение пользователю {user.id} в ЛС: {e}")

        active_quiz_session = self.state.get_active_quiz(chat_id_int)
        if active_quiz_session and answered_poll_id in active_quiz_session.active_poll_ids_in_session: # ИСПРАВЛЕНО ИМЯ
             if self.quiz_manager:
                 await self.quiz_manager._handle_early_answer_for_session(context, chat_id_int, answered_poll_id)

    def get_handler(self) -> PTBPollAnswerHandler:
        return PTBPollAnswerHandler(self.handle_poll_answer)

