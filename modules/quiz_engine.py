# modules/quiz_engine.py
import random
import logging
from typing import List, Dict, Any, Tuple, Optional, TYPE_CHECKING

from utils import escape_markdown_v2
from modules.rate_limiter import TelegramRateLimiter
from modules.telegram_utils import safe_send_message

if TYPE_CHECKING:
    from app_config import AppConfig
    from state import BotState
    from data_manager import DataManager

from telegram import Poll, Message
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest, TimedOut, NetworkError
import asyncio

logger = logging.getLogger(__name__)

class QuizEngine:
    def __init__(self, state: 'BotState', app_config: 'AppConfig', data_manager: 'DataManager'):
        self.state = state
        self.app_config = app_config
        self.data_manager = data_manager
        logger.debug("QuizEngine initialized.")
        
        # Инициализируем rate limiter для соблюдения лимитов Telegram API
        self.rate_limiter = TelegramRateLimiter(
            max_requests_per_second=25,  # Консервативное значение (Telegram ~30)
            max_requests_per_minute_per_chat=18  # Консервативное значение (Telegram ~20)
        )

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

        # Retry механизм для отправки опроса (важно для таймаутов в России)
        max_retries = 4  # 1 основная попытка + 4 повтора = всего 5 попыток (best practice 2025)
        base_delay = 2.0  # Увеличенная начальная задержка для нестабильных сетей
        max_delay = 15.0  # Максимальная задержка 15 секунд (рекомендация для RU→EU)
        
        sent_poll_msg: Optional[Message] = None
        last_exception = None
        
        for attempt in range(max_retries + 1):
            # Применяем rate limiting перед каждой попыткой
            await self.rate_limiter.acquire(chat_id)
            try:
                sent_poll_msg = await context.bot.send_poll(
                    chat_id=chat_id,
                    question=question_for_api,
                    options=options_for_api,
                    type=Poll.QUIZ,
                    correct_option_id=correct_option_idx_shuffled,
                    open_period=open_period_seconds,
                    is_anonymous=False
                )
                # Успешно отправлено, выходим из цикла retry
                break
            except Exception as e:
                last_exception = e
                error_message = str(e).lower()
                error_type = type(e).__name__
                
                # Не повторяем для ошибок блокировки/недоступности чата
                if "blocked" in error_message or "not found" in error_message or "forbidden" in error_message:
                    logger.error(f"Ошибка при отправке опроса (тип: {quiz_type}) в чате {chat_id}: {e}", exc_info=True)
                    logger.error(f"Текст вопроса (экранированный), который вызвал ошибку: {question_for_api}")
                    logger.error(f"Опции (экранированные), которые вызвали ошибку: {options_for_api}")
                    
                    # Автоматическое отключение рассылки при блокировке или недоступности чата
                    if quiz_type == "daily":
                        logger.warning(f"⚠️ Обнаружена блокировка/недоступность чата {chat_id} при отправке опроса. Автоматически отключаю ежедневную рассылку.")
                        self.data_manager.disable_daily_quiz_for_chat(
                            chat_id,
                            reason="blocked" if "blocked" in error_message else "not_found"
                        )
                    return None
                
                # Повторяем только для таймаутов и сетевых ошибок
                if isinstance(e, (TimedOut, NetworkError)) and attempt < max_retries:
                    # Exponential backoff с коэффициентом 2.0 (best practice)
                    base_delay_calc = min(base_delay * (2.0 ** attempt), max_delay)
                    # Добавляем jitter (±30%) для избежания синхронных повторов
                    jitter = random.uniform(-0.3 * base_delay_calc, 0.3 * base_delay_calc)
                    delay = max(0.5, base_delay_calc + jitter)  # Минимум 0.5 секунды
                    logger.warning(f"Таймаут/сетевая ошибка при отправке опроса в чате {chat_id}, повтор через {delay:.1f}с (попытка {attempt + 1}/{max_retries + 1}): {e}")
                    await asyncio.sleep(delay)
                    continue  # Повторяем попытку
                
                # Для других ошибок или исчерпания попыток - логируем и возвращаем None
                logger.error(f"Ошибка при отправке опроса (тип: {quiz_type}) в чате {chat_id} (попытка {attempt + 1}/{max_retries + 1}): {e}", exc_info=True)
                logger.error(f"Текст вопроса (экранированный), который вызвал ошибку: {question_for_api}")
                logger.error(f"Опции (экранированные), которые вызвали ошибку: {options_for_api}")
                
                # Для других ошибок (не TimedOut/NetworkError) не повторяем
                return None
        
        # Проверяем, была ли успешная отправка
        if sent_poll_msg is None:
            logger.error(f"Все попытки отправки опроса исчерпаны для чата {chat_id}: {last_exception}")
            return None

        if not sent_poll_msg.poll:
            logger.error(f"Сообщение с опросом не было отправлено или не содержит опрос (чат: {chat_id}).")
            return None

        poll_id_str: str = sent_poll_msg.poll.id
        
        # Защита от дубликатов: проверяем, не был ли уже отправлен опрос с таким же poll_id
        existing_poll = self.state.get_current_poll_data(poll_id_str)
        if existing_poll:
            logger.warning(f"Опрос с poll_id {poll_id_str} уже существует в state. Это дубликат, пропускаем повторную отправку для чата {chat_id}.")
            return poll_id_str
        
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

        # Отправляем placeholder для решения только если его еще нет
        if question_data.get("solution"):
            # Проверяем, не был ли уже отправлен placeholder для этого опроса
            poll_data_after_add = self.state.get_current_poll_data(poll_id_str)
            if poll_data_after_add and not poll_data_after_add.get("solution_placeholder_message_id"):
                try:
                    placeholder_msg = await safe_send_message(
                        bot=context.bot,
                        chat_id=chat_id,
                        text="💡",
                        parse_mode=None
                    )
                    if poll_id_str in self.state.current_polls:
                        self.state.current_polls[poll_id_str]["solution_placeholder_message_id"] = placeholder_msg.message_id
                        logger.debug(f"Отправлен placeholder сообщение 💡 для poll_id {poll_id_str} в чате {chat_id}.")
                except Exception as e_placeholder:
                    logger.error(f"Не удалось отправить сообщение-заглушку '💡' для решения: {e_placeholder}")
            else:
                logger.debug(f"Placeholder сообщение для poll_id {poll_id_str} уже существует, пропускаем повторную отправку.")
        return poll_id_str

    async def send_solution_if_available(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, poll_id: str) -> Optional[int]:
        poll_info = self.state.get_current_poll_data(poll_id)
        solution_sent_or_edited_msg_id: Optional[int] = None

        if not poll_info:
            logger.warning(f"send_solution_if_available: Информация для poll_id {poll_id} не найдена.")
            return None

        # Защита от повторной отправки решения: проверяем, не было ли уже отправлено решение
        if poll_info.get("solution_sent", False):
            logger.debug(f"Решение для poll_id {poll_id} уже было отправлено ранее. Пропускаем повторную отправку.")
            return poll_info.get("solution_message_id")

        solution_text_raw = poll_info.get("question_details", {}).get("solution")
        if not solution_text_raw:
            return None

        # ОПТИМИЗАЦИЯ: Ограничиваем длину текста решения
        max_solution_length = 4000  # Оставляем запас для заголовка
        if len(solution_text_raw) > max_solution_length:
            logger.warning(f"Текст решения слишком длинный ({len(solution_text_raw)} символов), обрезаем до {max_solution_length}")
            solution_text_raw = solution_text_raw[:max_solution_length] + "..."

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
                new_solution_msg = await safe_send_message(
                    bot=context.bot,
                    chat_id=chat_id,
                    text=solution_message_full_truncated,
                    parse_mode=None
                )
                solution_sent_or_edited_msg_id = new_solution_msg.message_id
            
            # Помечаем, что решение было отправлено, чтобы избежать дубликатов
            if poll_id in self.state.current_polls:
                self.state.current_polls[poll_id]["solution_sent"] = True
                self.state.current_polls[poll_id]["solution_message_id"] = solution_sent_or_edited_msg_id
            
            logger.info(f"Отправлено/обновлено пояснение для {log_q_ref_text_plain} в чате {chat_id} (parse_mode=None). ID: {solution_sent_or_edited_msg_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки/редактирования пояснения (parse_mode=None) для {log_q_ref_text_plain} в чате {chat_id}: {e}", exc_info=True)
            logger.error(f"Текст (простой), вызвавший ошибку (parse_mode=None): '{solution_message_full_truncated}'")

            if placeholder_msg_id and isinstance(e, BadRequest) and "message to edit not found" in str(e).lower() or "message is not modified" not in str(e).lower() :
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=placeholder_msg_id)
                except Exception: pass
                try:
                    new_fallback_solution_msg = await safe_send_message(
                        bot=context.bot,
                        chat_id=chat_id,
                        text=solution_message_full_truncated,
                        parse_mode=None
                    )
                    solution_sent_or_edited_msg_id = new_fallback_solution_msg.message_id
                    logger.info(f"Пояснение для {log_q_ref_text_plain} отправлено как новое сообщение (fallback, parse_mode=None). ID: {solution_sent_or_edited_msg_id}")
                except Exception as e_send_fallback:
                    logger.error(f"Не удалось отправить пояснение (fallback, parse_mode=None) для {log_q_ref_text_plain}: {e_send_fallback}")

        return solution_sent_or_edited_msg_id

