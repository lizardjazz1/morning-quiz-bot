# bot/modules/quiz_engine.py
import asyncio
import random
import logging
from typing import List, Dict, Any, Tuple, Optional
from datetime import timedelta

from telegram import Poll, Message
from telegram.ext import ContextTypes, JobQueue
from telegram.error import BadRequest

# from ..app_config import AppConfig # Через конструктор
# from ..state import BotState # Через конструктор
# from ..data_manager import DataManager # Может быть нужен для прямого доступа, но лучше через QuizManager

logger = logging.getLogger(__name__)

class QuizEngine:
    def __init__(self, state: 'BotState', app_config: 'AppConfig'): # data_manager пока не нужен напрямую
        self.state = state
        self.app_config = app_config
        # QuizManager будет вызывать методы этого QuizEngine

    def _prepare_poll_options(self, question_details: Dict[str, Any]) -> Tuple[str, List[str], int, str]:
        """
        Готовит текст вопроса, варианты ответов (обрезанные и перемешанные),
        индекс правильного ответа в перемешанном списке и оригинальный текст правильного ответа.
        """
        q_text: str = question_details["question"]
        original_options: List[str] = question_details["options"]
        # correct_option_index_original: int = question_details["correct_option_index"]
        correct_answer_text_original: str = question_details["correct_option_text"] # Используем текст

        processed_options_temp: List[str] = []
        for opt_text in original_options:
            if len(opt_text) > self.app_config.max_poll_option_length:
                truncated_text = opt_text[:self.app_config.max_poll_option_length - 3] + "..."
                processed_options_temp.append(truncated_text)
                # Логирование усечения (можно сделать более детальным)
                # logger.debug(f"Option for poll truncated: '{opt_text}' -> '{truncated_text}'")
            else:
                processed_options_temp.append(opt_text)
        
        # Находим текст правильного ответа в обработанных (возможно, усеченных) опциях
        # Это важно, т.к. Telegram сравнивает по тексту для correct_option_id
        correct_answer_text_for_matching: Optional[str] = None
        # Ищем оригинальный правильный ответ среди обработанных опций
        for i, p_opt in enumerate(processed_options_temp):
            if original_options[i] == correct_answer_text_original: # Сравниваем оригиналы
                correct_answer_text_for_matching = p_opt # Берем обработанный вариант
                break
        
        if correct_answer_text_for_matching is None:
            # Это критическая ситуация: не удалось найти соответствующий правильный ответ
            # после обработки. Такое может случиться, если усечение изменило его до неузнаваемости
            # или если в `question_details` ошибка.
            logger.error(f"Не удалось найти правильный ответ ('{correct_answer_text_original}') среди обработанных опций: {processed_options_temp} для вопроса: {q_text[:50]}...")
            # В качестве fallback можно взять первый вариант как правильный, но это нежелательно.
            # Лучше остановить процесс или выдать ошибку.
            # Для простоты, вернем как есть, но залогируем.
            # Это должно быть поймано на этапе валидации вопросов.
            # Если мы дошли сюда, предполагаем, что correct_answer_text_original ЕСТЬ в original_options
            # и его усеченная версия (если усекался) будет в processed_options_temp.

            # Попытка найти по оригинальному тексту в усеченных, если первый поиск не удался
            if correct_answer_text_original in processed_options_temp:
                 correct_answer_text_for_matching = correct_answer_text_original
            else: # Очень плохой fallback
                 logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА: правильный ответ не найден даже после fallback! Q: {q_text}")
                 # Вернем первый как правильный, чтобы не упасть, но это некорректно
                 correct_answer_text_for_matching = processed_options_temp[0] if processed_options_temp else "Ошибка"


        final_shuffled_options: List[str] = list(processed_options_temp) # Копия
        random.shuffle(final_shuffled_options)
        
        try:
            new_correct_idx_in_shuffled = final_shuffled_options.index(correct_answer_text_for_matching)
        except ValueError:
            logger.error(
                f"КРИТИЧЕСКАЯ ОШИБКА: Текст правильного ответа ('{correct_answer_text_for_matching}') "
                f"не найден в перемешанных опциях: {final_shuffled_options}. Исходные: {original_options}. Вопрос: '{q_text[:50]}...'. "
                f"Используется индекс 0 как fallback."
            )
            # Это может случиться, если из-за усечения несколько вариантов стали одинаковыми,
            # или из-за очень редкой коллизии при перемешивании (маловероятно с list.index).
            if not final_shuffled_options: # Полностью пустые опции
                 return q_text, [], 0, correct_answer_text_original # Катастрофа
            new_correct_idx_in_shuffled = 0 
            
        return q_text, final_shuffled_options, new_correct_idx_in_shuffled, correct_answer_text_original


    async def send_quiz_poll(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int, # int
        question_data: Dict[str, Any], # Один вопрос из BotState.questions_by_category
        poll_title_prefix: str, # Например, "Вопрос 1/10"
        open_period_seconds: int,
        quiz_type: str, # "single", "session", "daily" - для current_polls
        is_last_question: bool = False,
        question_session_index: int = 0, # 0-based
        current_category_name: Optional[str] = None # Категория этого вопроса
    ) -> Optional[str]: # Возвращает poll_id (str) или None при ошибке
        """Отправляет опрос викторины и регистрирует его в BotState.current_polls."""

        full_question_text = question_data['question']
        
        poll_header_parts = [poll_title_prefix]
        if current_category_name:
            poll_header_parts.append(f"(Кат: {current_category_name})")
        poll_header_parts.append(full_question_text)
        
        poll_question_display_text = "\n".join(poll_header_parts)

        if len(poll_question_display_text) > self.app_config.max_poll_question_length:
            # Пытаемся усечь только сам текст вопроса, сохраняя префикс и категорию
            base_len = len(poll_title_prefix) + (len(f"\n(Кат: {current_category_name})\n") if current_category_name else len("\n"))
            available_len_for_q = self.app_config.max_poll_question_length - base_len - 3 # -3 for "..."
            
            if available_len_for_q > 20: # Если есть место для осмысленного усечения
                truncated_q_text = full_question_text[:available_len_for_q] + "..."
                poll_header_parts[-1] = truncated_q_text # Заменяем последнюю часть (текст вопроса)
                poll_question_display_text = "\n".join(poll_header_parts)
            else: # Если даже после усечения не влезает, усекаем всё сообщение
                poll_question_display_text = poll_question_display_text[:self.app_config.max_poll_question_length - 3] + "..."
            logger.warning(f"Текст вопроса для poll в чате {chat_id} был усечен.")

        _, poll_options, poll_correct_option_id_in_shuffled, _ = self._prepare_poll_options(question_data)

        if not poll_options:
            logger.error(f"Не удалось подготовить варианты ответов для вопроса в чате {chat_id}. Вопрос: {full_question_text[:50]}")
            return None

        logger.debug(f"Попытка отправки опроса в чат {chat_id}. Заголовок: '{poll_question_display_text[:100]}...'")
        
        try:
            sent_poll_msg: Message = await context.bot.send_poll(
                chat_id=chat_id,
                question=poll_question_display_text,
                options=poll_options,
                type=Poll.QUIZ,
                correct_option_id=poll_correct_option_id_in_shuffled,
                open_period=open_period_seconds,
                is_anonymous=False # Важно для подсчета очков
            )
        except BadRequest as e:
            logger.error(f"Ошибка BadRequest при отправке опроса ({quiz_type}) в чат {chat_id}: {e}. Вопрос: '{poll_question_display_text[:100]}...'. Опции: {poll_options}")
            return None
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при отправке опроса ({quiz_type}) в чате {chat_id}: {e}", exc_info=True)
            return None

        if not sent_poll_msg or not sent_poll_msg.poll:
            logger.error(f"Не удалось отправить опрос или получить информацию о нем в чате {chat_id}.")
            return None

        poll_id_str: str = sent_poll_msg.poll.id
        
        current_poll_entry = {
            "chat_id": chat_id, # int
            "message_id": sent_poll_msg.message_id, # int
            "question_details": question_data, # Полные детали исходного вопроса
            "correct_option_index": poll_correct_option_id_in_shuffled, # Индекс в отправленных опциях
            "quiz_type": quiz_type, # "single", "session", "daily"
            "is_last_question_in_series": is_last_question,
            "question_session_index": question_session_index,
            "associated_quiz_id": chat_id if quiz_type in ["session", "daily"] else None, # Связь с сессией
            "job_poll_end_name": None, # Будет установлено QuizManager
            "solution_placeholder_message_id": None,
            "processed_by_early_answer": False,
            "open_timestamp": sent_poll_msg.date.timestamp() # float
        }
        self.state.current_polls[poll_id_str] = current_poll_entry
        
        logger.info(f"Отправлен опрос (тип: {quiz_type}, poll_id: {poll_id_str}) в чат {chat_id}. Последний в серии: {is_last_question}.")

        # Отправка заглушки для пояснения, если оно есть
        if question_data.get("solution"):
            try:
                placeholder_msg = await context.bot.send_message(chat_id=chat_id, text="💡")
                self.state.current_polls[poll_id_str]["solution_placeholder_message_id"] = placeholder_msg.message_id
            except Exception as e_sol_pl:
                 logger.error(f"Не удалось отправить заглушку '💡' для poll {poll_id_str} в чате {chat_id}: {e_sol_pl}")
        
        return poll_id_str


    async def send_solution_if_available(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int, # int
        poll_id: str # ID опроса, для которого отправляем решение
    ):
        """Отправляет пояснение к вопросу, если оно есть, редактируя заглушку или новым сообщением."""
        poll_info = self.state.current_polls.get(poll_id)
        if not poll_info:
            logger.warning(f"send_solution: Информация об опросе {poll_id} не найдена для чата {chat_id}.")
            return

        question_details = poll_info.get("question_details", {})
        solution_text = question_details.get("solution")
        if not solution_text:
            return

        q_text_short = question_details.get("question", "вопросу")[:30]
        q_session_idx = poll_info.get("question_session_index", -1)
        log_q_ref = f"«{q_text_short}...»" + (f" (вопрос {q_session_idx + 1})" if q_session_idx != -1 else "")
        
        solution_message_full = f"💡 Пояснение к вопросу {log_q_ref}:\n{solution_text}"
        
        # Ограничение длины сообщения Telegram
        MAX_MSG_LEN = 4096 # Telegram API limit
        if len(solution_message_full) > MAX_MSG_LEN:
            solution_message_full = solution_message_full[:MAX_MSG_LEN - 3] + "..."
            logger.warning(f"Пояснение для {log_q_ref} в чате {chat_id} усечено.")

        placeholder_id: Optional[int] = poll_info.get("solution_placeholder_message_id")

        if placeholder_id:
            try:
                await context.bot.edit_message_text(
                    text=solution_message_full,
                    chat_id=chat_id,
                    message_id=placeholder_id,
                    parse_mode=ParseMode.HTML # Используем HTML, если нужны будут теги
                )
                logger.info(f"Отредактирована заглушка с пояснением для {log_q_ref} в чате {chat_id}.")
                return
            except BadRequest as e:
                if "Message to edit not found" in str(e) or "message is not modified" in str(e).lower():
                    logger.warning(f"Не удалось отредактировать заглушку ({placeholder_id}) для {log_q_ref} (возможно, удалена): {e}. Отправка нового сообщения.")
                else: # Другая ошибка BadRequest
                    logger.error(f"Ошибка BadRequest при редактировании заглушки ({placeholder_id}) для {log_q_ref}: {e}. Текст: {solution_message_full}", exc_info=True)
            except Exception as e: # Другие ошибки
                logger.error(f"Ошибка при редактировании заглушки ({placeholder_id}) для {log_q_ref}: {e}", exc_info=True)
        
        # Если не удалось отредактировать или не было заглушки, отправляем новое сообщение
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=solution_message_full,
                parse_mode=ParseMode.HTML
            )
            logger.info(f"Отправлено новое пояснение для {log_q_ref} в чате {chat_id}.")
        except Exception as e:
            logger.error(f"Ошибка при отправке нового пояснения для {log_q_ref} в чате {chat_id}: {e}", exc_info=True)

    # handle_poll_timeout и другие методы, управляющие жизненным циклом опроса (например, закрытие)
    # теперь будут вызываться из QuizManager, так как QuizManager отвечает за всю сессию.
    # QuizEngine предоставляет строительные блоки.

