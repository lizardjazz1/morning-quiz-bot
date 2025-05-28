#poll_answer_handler.py
import logging
from typing import Optional, TYPE_CHECKING

from telegram import Update, PollAnswer, User as TelegramUser
from telegram.ext import ContextTypes, PollAnswerHandler as PTBPollAnswerHandler

if TYPE_CHECKING:
    from app_config import AppConfig
    from state import BotState
    from modules.score_manager import ScoreManager
    from handlers.quiz_manager import QuizManager

logger = logging.getLogger(__name__)

class CustomPollAnswerHandler:
    def __init__(
        self,
        state: 'BotState',
        score_manager: 'ScoreManager',
        app_config: 'AppConfig'
    ):
        self.state = state
        self.score_manager = score_manager
        self.app_config = app_config
        self.quiz_manager_ref: Optional['QuizManager'] = None

    def set_quiz_manager(self, quiz_manager: 'QuizManager') -> None:
        self.quiz_manager_ref = quiz_manager

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

        score_was_updated, motivational_msg_text = await self.score_manager.update_score_and_get_motivation(
            chat_id=chat_id_int,
            user=user,
            poll_id=answered_poll_id,
            is_correct=is_answer_correct,
            quiz_type_of_poll=quiz_type_of_poll
        )

        if motivational_msg_text:
            try:
                await context.bot.send_message(chat_id=user.id, text=motivational_msg_text)
            except Exception as e:
                logger.error(f"Не удалось отправить мотивационное сообщение пользователю {user.id} в ЛС: {e}")

        active_quiz_session = self.state.get_active_quiz(chat_id_int)
        if active_quiz_session and \
           active_quiz_session.quiz_mode == "serial_immediate" and \
           active_quiz_session.current_poll_id == answered_poll_id:

            if not poll_info_from_state.get("processed_by_early_answer", False) and self.quiz_manager_ref:
                is_last_q_in_poll = poll_info_from_state.get("is_last_question_in_series", False)
                if not is_last_q_in_poll:
                    poll_info_from_state["processed_by_early_answer"] = True
                    logger.info(
                        f"Ранний ответ на опрос {answered_poll_id} в сессии (serial_immediate) в чате {chat_id_int}. "
                        f"Попытка немедленного запуска следующего вопроса."
                    )
                    await self.quiz_manager_ref._handle_early_answer_for_session(context, chat_id_int, answered_poll_id)
                else:
                    logger.info(f"Ранний ответ на последний опрос {answered_poll_id} в сессии (serial_immediate). Финализация по таймауту.")

    def get_handler(self) -> PTBPollAnswerHandler:
        return PTBPollAnswerHandler(self.handle_poll_answer)
