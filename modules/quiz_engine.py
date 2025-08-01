# modules/quiz_engine.py
import random
import logging
from typing import List, Dict, Any, Tuple, Optional, TYPE_CHECKING

from utils import escape_markdown_v2

if TYPE_CHECKING:
    from app_config import AppConfig
    from state import BotState
    from data_manager import DataManager

from telegram import Poll, Message
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest

logger = logging.getLogger(__name__)

class QuizEngine:
    def __init__(self, state: 'BotState', app_config: 'AppConfig', data_manager: 'DataManager'):
        self.state = state
        self.app_config = app_config
        self.data_manager = data_manager
        logger.debug("QuizEngine initialized.")

    def _prepare_poll_options(self, question_details: Dict[str, Any]) -> Tuple[str, List[str], int, str]:
        q_text: str = question_details["question"]
        original_options: List[str] = question_details["options"]
        correct_answer_text_original: str = question_details["correct_option_text"]

        processed_options_plain_truncated: List[str] = []
        for opt_text in original_options:
            if len(opt_text) > self.app_config.max_poll_option_length:
                processed_options_plain_truncated.append(opt_text[:self.app_config.max_poll_option_length - 3] + "...")
            else:
                processed_options_plain_truncated.append(opt_text)

        correct_answer_text_for_matching_in_processed: Optional[str] = None
        try:
            original_correct_idx = original_options.index(correct_answer_text_original)
            correct_answer_text_for_matching_in_processed = processed_options_plain_truncated[original_correct_idx]
        except ValueError:
            logger.error(f"Критическая ошибка: текст правильного ответа '{correct_answer_text_original}' не найден в оригинальных опциях {original_options}. Вопрос: {q_text[:50]}")
            return q_text, [], -1, ""

        final_shuffled_options_plain_truncated: List[str] = list(processed_options_plain_truncated)
        random.shuffle(final_shuffled_options_plain_truncated)

        try:
            new_correct_idx_in_shuffled = final_shuffled_options_plain_truncated.index(correct_answer_text_for_matching_in_processed)
        except ValueError:
            logger.warning(f"Текст правильного ответа '{correct_answer_text_for_matching_in_processed}' (ориг: '{correct_answer_text_original}') не найден в перемешанных и обработанных опциях: {final_shuffled_options_plain_truncated}. Ошибка может повлиять на определение правильного ответа.")
            new_correct_idx_in_shuffled = -1

        return q_text, final_shuffled_options_plain_truncated, new_correct_idx_in_shuffled, correct_answer_text_original

    async def send_quiz_poll(
        self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, question_data: Dict[str, Any],
        poll_title_prefix: str,
        open_period_seconds: int, quiz_type: str,
        is_last_question: bool = False, question_session_index: int = 0,
        current_category_name: Optional[str] = None
    ) -> Optional[str]:
        original_plain_question_text = question_data['question']
        _, plain_truncated_shuffled_options, correct_option_idx_shuffled, _ = self._prepare_poll_options(question_data)

        if not plain_truncated_shuffled_options or correct_option_idx_shuffled == -1 :
            logger.error(f"Не удалось подготовить варианты/правильный ответ для вопроса в чате {chat_id}. Вопрос: {original_plain_question_text[:50]}")
            return None

        sanitized_poll_title_prefix = self.data_manager._sanitize_text_for_telegram(poll_title_prefix)
        sanitized_current_category_name = self.data_manager._sanitize_text_for_telegram(current_category_name) if current_category_name else None

        poll_header_parts = [sanitized_poll_title_prefix]
        if sanitized_current_category_name:
            poll_header_parts.append(f"Категория: {sanitized_current_category_name}")

        temp_header_plain = "\n".join(poll_header_parts)
        full_question_text_plain = f"{temp_header_plain}\n{self.data_manager._sanitize_text_for_telegram(original_plain_question_text)}"

        truncated_full_question_text_plain: str
        if len(full_question_text_plain) > self.app_config.max_poll_question_length:
            truncated_full_question_text_plain = full_question_text_plain[:self.app_config.max_poll_question_length - 3] + "..."
            logger.warning(f"Простой текст вопроса для poll в чате {chat_id} был усечен. Оригинал (начало): '{full_question_text_plain[:50]}', Усеченный: '{truncated_full_question_text_plain[:50]}'")
        else:
            truncated_full_question_text_plain = full_question_text_plain

        question_for_api = escape_markdown_v2(truncated_full_question_text_plain)
        options_for_api = [escape_markdown_v2(opt) for opt in plain_truncated_shuffled_options]

        try:
            sent_poll_msg: Message = await context.bot.send_poll(
                chat_id=chat_id,
                question=question_for_api,
                options=options_for_api,
                type=Poll.QUIZ,
                correct_option_id=correct_option_idx_shuffled,
                open_period=open_period_seconds,
                is_anonymous=False
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке опроса (тип: {quiz_type}) в чате {chat_id}: {e}", exc_info=True)
            logger.error(f"Текст вопроса (экранированный), который вызвал ошибку: {question_for_api}")
            logger.error(f"Опции (экранированные), которые вызвали ошибку: {options_for_api}")
            return None

        if not sent_poll_msg or not sent_poll_msg.poll:
            logger.error(f"Сообщение с опросом не было отправлено или не содержит опрос (чат: {chat_id}).")
            return None

        poll_id_str: str = sent_poll_msg.poll.id
        current_poll_entry_data = {
            "chat_id": chat_id,
            "message_id": sent_poll_msg.message_id,
            "question_details": question_data,
            "correct_option_index": correct_option_idx_shuffled,
            "quiz_type": quiz_type,
            "is_last_question_in_series": is_last_question,
            "question_session_index": question_session_index,
            "solution_placeholder_message_id": None,
            "processed_by_early_answer": False,
            "open_timestamp": sent_poll_msg.date.timestamp(),
            "next_q_triggered_by_answer": False, # ИЗМЕНЕНО: Добавлен флаг
            "job_poll_end_name": None
        }
        self.state.add_current_poll(poll_id_str, current_poll_entry_data)
        logger.info(f"Отправлен опрос (тип: {quiz_type}, ID опроса: {poll_id_str}, ID сообщения: {sent_poll_msg.message_id}) в чат {chat_id}.")

        if question_data.get("solution"):
            try:
                placeholder_msg = await context.bot.send_message(chat_id=chat_id, text="💡", parse_mode=None)
                if poll_id_str in self.state.current_polls:
                     self.state.current_polls[poll_id_str]["solution_placeholder_message_id"] = placeholder_msg.message_id
            except Exception as e_placeholder:
                logger.error(f"Не удалось отправить сообщение-заглушку '💡' для решения: {e_placeholder}")
        return poll_id_str

    async def send_solution_if_available(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, poll_id: str) -> Optional[int]:
        poll_info = self.state.get_current_poll_data(poll_id)
        solution_sent_or_edited_msg_id: Optional[int] = None

        if not poll_info:
            logger.warning(f"send_solution_if_available: Информация для poll_id {poll_id} не найдена.")
            return None

        solution_text_raw = poll_info.get("question_details", {}).get("solution")
        if not solution_text_raw:
            return None

        q_text_short_plain_for_log = poll_info.get("question_details", {}).get("question", "вопросу")[:30]
        idx_session_for_log = poll_info.get("question_session_index", -1)
        log_q_ref_text_plain = f"«{self.data_manager._sanitize_text_for_telegram(q_text_short_plain_for_log)}...»"
        if idx_session_for_log != -1:
            log_q_ref_text_plain += f" (вопрос {idx_session_for_log + 1})"

        solution_message_header_plain = f"💡"
        solution_message_full_plain = (
            self.data_manager._sanitize_text_for_telegram(solution_message_header_plain) +
            self.data_manager._sanitize_text_for_telegram(solution_text_raw)
        )

        solution_message_full_truncated: str
        fixed_header_len = len(solution_message_header_plain)
        if len(solution_message_full_plain) > 4096:
            available_len_for_solution_part = 4096 - fixed_header_len - 20
            if available_len_for_solution_part > 0:
                truncated_solution_part = self.data_manager._sanitize_text_for_telegram(solution_text_raw)[:available_len_for_solution_part]
                solution_message_full_truncated = solution_message_header_plain + truncated_solution_part + "..."
            else:
                solution_message_full_truncated = solution_message_header_plain[:4096-20] + "..."
        else:
            solution_message_full_truncated = solution_message_full_plain

        placeholder_msg_id: Optional[int] = poll_info.get("solution_placeholder_message_id")

        try:
            if placeholder_msg_id:
                await context.bot.edit_message_text(
                    text=solution_message_full_truncated,
                    chat_id=chat_id,
                    message_id=placeholder_msg_id,
                    parse_mode=None
                )
                solution_sent_or_edited_msg_id = placeholder_msg_id
            else:
                new_solution_msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text=solution_message_full_truncated,
                    parse_mode=None
                )
                solution_sent_or_edited_msg_id = new_solution_msg.message_id
            logger.info(f"Отправлено/обновлено пояснение для {log_q_ref_text_plain} в чате {chat_id} (parse_mode=None). ID: {solution_sent_or_edited_msg_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки/редактирования пояснения (parse_mode=None) для {log_q_ref_text_plain} в чате {chat_id}: {e}", exc_info=True)
            logger.error(f"Текст (простой), вызвавший ошибку (parse_mode=None): '{solution_message_full_truncated}'")

            if placeholder_msg_id and isinstance(e, BadRequest) and "message to edit not found" in str(e).lower() or "message is not modified" not in str(e).lower() :
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=placeholder_msg_id)
                except Exception: pass
                try:
                    new_fallback_solution_msg = await context.bot.send_message(
                        chat_id=chat_id,
                        text=solution_message_full_truncated,
                        parse_mode=None
                    )
                    solution_sent_or_edited_msg_id = new_fallback_solution_msg.message_id
                    logger.info(f"Пояснение для {log_q_ref_text_plain} отправлено как новое сообщение (fallback, parse_mode=None). ID: {solution_sent_or_edited_msg_id}")
                except Exception as e_send_fallback:
                    logger.error(f"Не удалось отправить пояснение (fallback, parse_mode=None) для {log_q_ref_text_plain}: {e_send_fallback}")

        return solution_sent_or_edited_msg_id

