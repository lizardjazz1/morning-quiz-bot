# modules/quiz_engine.py
import random
import logging
from typing import List, Dict, Any, Tuple, Optional

from telegram import Poll, Message # Внешние импорты
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest

# Если нужны AppConfig или BotState для тайп-хинтинга в конструкторе, то:
# from app_config import AppConfig
# from state import BotState
# Если нужен utils:
# from utils import some_util_function

logger = logging.getLogger(__name__)

class QuizEngine:
    def __init__(self, state: 'BotState', app_config: 'AppConfig'):
        self.state = state
        self.app_config = app_config

    def _prepare_poll_options(self, question_details: Dict[str, Any]) -> Tuple[str, List[str], int, str]:
        q_text: str = question_details["question"]
        original_options: List[str] = question_details["options"]
        correct_answer_text_original: str = question_details["correct_option_text"]

        processed_options_temp: List[str] = []
        for opt_text in original_options:
            if len(opt_text) > self.app_config.max_poll_option_length:
                processed_options_temp.append(opt_text[:self.app_config.max_poll_option_length - 3] + "...")
            else:
                processed_options_temp.append(opt_text)
        
        correct_answer_text_for_matching: Optional[str] = None
        original_correct_idx = original_options.index(correct_answer_text_original) # Should exist
        correct_answer_text_for_matching = processed_options_temp[original_correct_idx]

        final_shuffled_options: List[str] = list(processed_options_temp)
        random.shuffle(final_shuffled_options)
        
        try:
            new_correct_idx_in_shuffled = final_shuffled_options.index(correct_answer_text_for_matching)
        except ValueError: # Fallback if text matching failed due to extreme truncation/collision
            logger.error(f"CRITICAL: Correct answer text '{correct_answer_text_for_matching}' not found in shuffled options after processing: {final_shuffled_options}. Q: {q_text[:50]}. Using index 0.")
            new_correct_idx_in_shuffled = 0 if final_shuffled_options else -1 # -1 if list is empty

        return q_text, final_shuffled_options, new_correct_idx_in_shuffled, correct_answer_text_original

    async def send_quiz_poll(
        self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, question_data: Dict[str, Any],
        poll_title_prefix: str, open_period_seconds: int, quiz_type: str,
        is_last_question: bool = False, question_session_index: int = 0,
        current_category_name: Optional[str] = None
    ) -> Optional[str]:
        full_question_text = question_data['question']
        poll_header_parts = [poll_title_prefix]
        if current_category_name: poll_header_parts.append(f"(Кат: {current_category_name})")
        poll_header_parts.append(full_question_text)
        poll_question_display_text = "\n".join(poll_header_parts)

        if len(poll_question_display_text) > self.app_config.max_poll_question_length:
            base_len = len(poll_title_prefix) + (len(f"\n(Кат: {current_category_name})\n") if current_category_name else len("\n"))
            available_len_for_q = self.app_config.max_poll_question_length - base_len - 3
            if available_len_for_q > 20:
                poll_header_parts[-1] = full_question_text[:available_len_for_q] + "..."
                poll_question_display_text = "\n".join(poll_header_parts)
            else:
                poll_question_display_text = poll_question_display_text[:self.app_config.max_poll_question_length - 3] + "..."
            logger.warning(f"Текст вопроса для poll в чате {chat_id} был усечен.")

        _, poll_options, poll_correct_option_id_shuffled, _ = self._prepare_poll_options(question_data)
        if not poll_options or poll_correct_option_id_shuffled == -1 : # -1 indicates error from _prepare_poll_options
            logger.error(f"Не удалось подготовить варианты/правильный ответ для вопроса в чате {chat_id}. Q: {full_question_text[:50]}")
            return None

        try:
            sent_poll_msg: Message = await context.bot.send_poll(
                chat_id=chat_id, question=poll_question_display_text, options=poll_options,
                type=Poll.QUIZ, correct_option_id=poll_correct_option_id_shuffled,
                open_period=open_period_seconds, is_anonymous=False
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке опроса ({quiz_type}) в чат {chat_id}: {e}", exc_info=True)
            return None
        if not sent_poll_msg or not sent_poll_msg.poll: return None

        poll_id_str: str = sent_poll_msg.poll.id
        current_poll_entry = {
            "chat_id": chat_id, "message_id": sent_poll_msg.message_id,
            "question_details": question_data,
            "correct_option_index": poll_correct_option_id_shuffled, # This is the index in *sent* options
            "quiz_type": quiz_type, "is_last_question_in_series": is_last_question,
            "question_session_index": question_session_index,
            "solution_placeholder_message_id": None, "processed_by_early_answer": False,
            "open_timestamp": sent_poll_msg.date.timestamp(), "job_poll_end_name": None
        }
        self.state.add_current_poll(poll_id_str, current_poll_entry)
        logger.info(f"Отправлен опрос ({quiz_type}, ID: {poll_id_str}) в чат {chat_id}.")

        if question_data.get("solution"):
            try:
                placeholder_msg = await context.bot.send_message(chat_id=chat_id, text="💡")
                self.state.current_polls[poll_id_str]["solution_placeholder_message_id"] = placeholder_msg.message_id
            except Exception as e: logger.error(f"Не удалось отправить заглушку '💡': {e}")
        return poll_id_str

    async def send_solution_if_available(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, poll_id: str):
        poll_info = self.state.get_current_poll_data(poll_id) # Use getter
        if not poll_info: return

        solution_text = poll_info.get("question_details", {}).get("solution")
        if not solution_text: return

        q_text_short = poll_info.get("question_details", {}).get("question", "вопросу")[:30]
        idx = poll_info.get("question_session_index", -1)
        log_q_ref = f"«{q_text_short}...»" + (f" (вопрос {idx + 1})" if idx != -1 else "")
        solution_message_full = f"💡 Пояснение к вопросу {log_q_ref}:\n{solution_text}"
        if len(solution_message_full) > 4096: solution_message_full = solution_message_full[:4093] + "..."

        placeholder_id: Optional[int] = poll_info.get("solution_placeholder_message_id")
        try:
            if placeholder_id:
                await context.bot.edit_message_text(text=solution_message_full, chat_id=chat_id, message_id=placeholder_id, parse_mode=ParseMode.HTML)
            else:
                await context.bot.send_message(chat_id=chat_id, text=solution_message_full, parse_mode=ParseMode.HTML)
            logger.info(f"Отправлено/обновлено пояснение для {log_q_ref} в чате {chat_id}.")
        except Exception as e:
            logger.error(f"Ошибка отправки/редактирования пояснения для {log_q_ref}: {e}", exc_info=True)
            if placeholder_id: # Если редактирование не удалось, попробуем отправить новое
                try: await context.bot.send_message(chat_id=chat_id, text=solution_message_full, parse_mode=ParseMode.HTML)
                except: pass # Игнорируем ошибку повторной отправки
