# quiz_logic.py
import random
from typing import List, Dict, Any, Tuple
from datetime import timedelta
from telegram import Update, Poll # Update не используется напрямую здесь
from telegram.ext import ContextTypes

from config import (logger, NUMBER_OF_QUESTIONS_IN_SESSION,
                    DEFAULT_POLL_OPEN_PERIOD, JOB_GRACE_PERIOD) # FINAL_ANSWER_WINDOW_SECONDS убран
import state
from utils import pluralize_points
from handlers.rating_handlers import get_player_display # Используется в show_quiz_session_results

# --- Вспомогательные функции (get_random_questions, get_random_questions_from_all, prepare_poll_options) ---
def get_random_questions(category: str, count: int = 1) -> List[Dict[str, Any]]:
    cat_q_list = state.quiz_data.get(category)
    if not isinstance(cat_q_list, list) or not cat_q_list:
        return []
    return [q.copy() for q in random.sample(cat_q_list, min(count, len(cat_q_list)))]

def get_random_questions_from_all(count: int) -> List[Dict[str, Any]]:
    all_q = [q.copy() for questions_in_category in state.quiz_data.values() if isinstance(questions_in_category, list) for q in questions_in_category]
    if not all_q:
        return []
    return random.sample(all_q, min(count, len(all_q)))

def prepare_poll_options(q_details: Dict[str, Any]) -> Tuple[str, List[str], int, List[str]]:
    q_text, opts_orig = q_details["question"], q_details["options"]
    correct_answer_text = opts_orig[q_details["correct_option_index"]]
    opts_shuffled = list(opts_orig)
    random.shuffle(opts_shuffled)
    try:
        new_correct_idx = opts_shuffled.index(correct_answer_text)
    except ValueError:
        logger.error(f"Не удалось найти '{correct_answer_text}' в перемешанных опциях: {opts_shuffled}. Используем оригинальный индекс.")
        return q_text, list(opts_orig), q_details["correct_option_index"], list(opts_orig)
    return q_text, opts_shuffled, new_correct_idx, list(opts_orig)

async def send_solution_if_available(context: ContextTypes.DEFAULT_TYPE, chat_id_str: str, question_details: Dict[str, Any], q_index_for_log: int = -1):
    """Отправляет пояснение к вопросу, если оно доступно."""
    solution = question_details.get("solution")
    q_text_for_header = question_details.get("question", "завершенному вопросу")
    log_q_ref_text = f"«{q_text_for_header[:30]}...»" if len(q_text_for_header) > 30 else f"«{q_text_for_header}»"
    log_q_ref_suffix = f" (вопрос сессии {q_index_for_log + 1})" if q_index_for_log != -1 else ""
    log_q_ref = f"{log_q_ref_text}{log_q_ref_suffix}"

    if solution:
        solution_message = f"💡{solution}"
        MAX_MESSAGE_LENGTH = 4096
        if len(solution_message) > MAX_MESSAGE_LENGTH:
            truncate_at = MAX_MESSAGE_LENGTH - 3
            solution_message = solution_message[:truncate_at] + "..."
            logger.warning(f"Пояснение для вопроса {log_q_ref} в чате {chat_id_str} было усечено.")
        
        logger.debug(f"Attempting to send solution to chat {chat_id_str} for question {log_q_ref}. Text: '{solution_message[:100]}...'")
        try:
            await context.bot.send_message(chat_id=chat_id_str, text=solution_message)
            logger.info(f"Отправлено пояснение для вопроса {log_q_ref} в чате {chat_id_str}.")
        except Exception as e:
            logger.error(f"Ошибка при отправке пояснения для вопроса {log_q_ref} в чате {chat_id_str}: {e}", exc_info=True)

async def send_next_question_in_session(context: ContextTypes.DEFAULT_TYPE, chat_id_str: str):
    session = state.current_quiz_session.get(chat_id_str)
    if not session:
        logger.warning(f"send_next_question_in_session: Сессия для чата {chat_id_str} не найдена.")
        return

    if job := session.get("next_question_job"):
        try: job.schedule_removal()
        except Exception: pass # Подавляем ошибки, если job уже выполнен или удален
        session["next_question_job"] = None

    current_q_idx = session["current_index"]
    actual_num_q = session["actual_num_questions"]

    if current_q_idx >= actual_num_q:
        logger.info(f"Все {actual_num_q} вопросов сессии {chat_id_str} были отправлены. Завершение сессии управляется handle_current_poll_end.")
        return

    q_details = session["questions"][current_q_idx]
    is_last_question = (current_q_idx == actual_num_q - 1)
    poll_open_period = DEFAULT_POLL_OPEN_PERIOD # Все вопросы в сессии /quiz10 имеют одинаковое время

    poll_question_text_for_api = q_details['question']
    full_poll_question_header = f"Вопрос {current_q_idx + 1}/{actual_num_q}"
    if original_cat := q_details.get("original_category"):
        full_poll_question_header += f" (Кат: {original_cat})"
    full_poll_question_header += f"\n{poll_question_text_for_api}"

    MAX_POLL_QUESTION_LENGTH = 255
    if len(full_poll_question_header) > MAX_POLL_QUESTION_LENGTH:
        truncate_at = MAX_POLL_QUESTION_LENGTH - 3
        full_poll_question_header = full_poll_question_header[:truncate_at] + "..."
        logger.warning(f"Текст вопроса для poll в чате {chat_id_str} был усечен (вопрос сессии {current_q_idx + 1}).")

    _, poll_options, poll_correct_option_id, _ = prepare_poll_options(q_details)

    logger.debug(f"Attempting to send /quiz10 question {current_q_idx + 1} to chat {chat_id_str}. Header: '{full_poll_question_header[:100]}...'")
    try:
        sent_poll_msg = await context.bot.send_poll(
            chat_id=chat_id_str, question=full_poll_question_header, options=poll_options,
            type=Poll.QUIZ, correct_option_id=poll_correct_option_id,
            open_period=poll_open_period, is_anonymous=False
        )
        session["current_poll_id"] = sent_poll_msg.poll.id
        session["current_index"] += 1 # Увеличиваем индекс для СЛЕДУЮЩЕГО вопроса
        
        state.current_poll[sent_poll_msg.poll.id] = {
            "chat_id": chat_id_str, "message_id": sent_poll_msg.message_id,
            "correct_index": poll_correct_option_id, "quiz_session": True,
            "question_details": q_details, "associated_quiz_session_chat_id": chat_id_str,
            "is_last_question": is_last_question,
            "next_q_triggered_by_answer": False,
            "question_session_index": current_q_idx # Индекс ТЕКУЩЕГО отправленного вопроса
        }
        logger.info(f"Отправлен вопрос {current_q_idx + 1}/{actual_num_q} сессии {chat_id_str}. Poll ID: {sent_poll_msg.poll.id}. Is last: {is_last_question}")

        job_delay_seconds = poll_open_period + JOB_GRACE_PERIOD
        job_name = f"poll_end_timeout_chat_{chat_id_str}_poll_{sent_poll_msg.poll.id}"
        if context.job_queue:
            existing_jobs = context.job_queue.get_jobs_by_name(job_name)
            for old_job in existing_jobs: old_job.schedule_removal()
            
            current_poll_end_job = context.job_queue.run_once(
                handle_current_poll_end, timedelta(seconds=job_delay_seconds),
                data={"chat_id_str": chat_id_str, "ended_poll_id": sent_poll_msg.poll.id},
                name=job_name
            )
            session["next_question_job"] = current_poll_end_job
    except Exception as e:
        logger.error(f"Ошибка при отправке вопроса сессии ({current_q_idx + 1}) в чате {chat_id_str}: {e}", exc_info=True)
        await show_quiz_session_results(context, chat_id_str, error_occurred=True) # Завершаем сессию при ошибке

async def handle_current_poll_end(context: ContextTypes.DEFAULT_TYPE):
    if not context.job or not context.job.data:
        logger.error("handle_current_poll_end вызван без job data.")
        return

    job_data = context.job.data
    chat_id_str: str = job_data["chat_id_str"]
    ended_poll_id: str = job_data["ended_poll_id"]

    poll_info = state.current_poll.get(ended_poll_id) # Получаем, не удаляя сразу
    session = state.current_quiz_session.get(chat_id_str)

    if not session:
        logger.warning(f"Сессия {chat_id_str} не найдена при обработке job для poll {ended_poll_id}. Опрос мог быть уже обработан.")
        if poll_info and poll_info.get("question_details"): # Если инфо об опросе есть, но сессии нет (странно)
            await send_solution_if_available(context, chat_id_str, poll_info["question_details"], poll_info.get("question_session_index", -1))
        state.current_poll.pop(ended_poll_id, None)
        return

    if not poll_info:
        logger.info(f"Poll {ended_poll_id} не найден в state.current_poll при обработке job (вероятно, обработан досрочным ответом на не последний вопрос). Job завершен.")
        return

    q_idx_from_poll_info = poll_info.get("question_session_index", -1)
    logger.info(f"Job 'handle_current_poll_end' сработал для чата {chat_id_str}, poll_id {ended_poll_id} (вопрос сессии ~{q_idx_from_poll_info + 1}).")

    await send_solution_if_available(context, chat_id_str, poll_info["question_details"], q_idx_from_poll_info)
    
    state.current_poll.pop(ended_poll_id, None) # Удаляем инфо об опросе после отправки пояснения
    logger.debug(f"Poll {ended_poll_id} удален из state.current_poll после обработки таймаута.")


    is_last_q = poll_info.get("is_last_question", False)

    if is_last_q:
        logger.info(f"Время для ПОСЛЕДНЕГО вопроса (индекс {q_idx_from_poll_info}, poll {ended_poll_id}) сессии {chat_id_str} истекло. Показ результатов.")
        await show_quiz_session_results(context, chat_id_str)
    else: # НЕ последний вопрос
        # Если досрочный ответ уже инициировал следующий вопрос, poll_info.get("next_q_triggered_by_answer") будет True
        # и poll_answer_handler уже вызвал send_next_question_in_session и удалил poll_info.
        # Таким образом, если мы здесь с poll_info, это означает, что досрочного ответа, который бы запустил следующий вопрос, НЕ БЫЛО.
        # Поэтому мы просто запускаем следующий вопрос по таймауту.
        logger.info(f"Тайм-аут для НЕ последнего вопроса (индекс {q_idx_from_poll_info}, poll {ended_poll_id}) в сессии {chat_id_str}. Отправляем следующий.")
        await send_next_question_in_session(context, chat_id_str)


async def handle_single_quiz_poll_end(context: ContextTypes.DEFAULT_TYPE):
    if not context.job or not context.job.data:
        logger.error("handle_single_quiz_poll_end: Job data missing.")
        return

    job_data = context.job.data
    chat_id_str: str = job_data["chat_id_str"]
    poll_id: str = job_data["poll_id"]
    logger.info(f"Job 'handle_single_quiz_poll_end' сработал для poll_id {poll_id} в чате {chat_id_str}.")

    poll_info = state.current_poll.pop(poll_id, None)
    if poll_info:
        question_details = poll_info.get("question_details")
        is_quiz_session_poll = poll_info.get("quiz_session", False)
        # Проверяем, что это одиночный квиз, есть детали и есть решение
        if not is_quiz_session_poll and question_details and question_details.get("solution"):
            await send_solution_if_available(context, chat_id_str, question_details)
            logger.info(f"Пояснение отправлено для одиночного квиза (poll {poll_id}) в чате {chat_id_str} по таймауту.")
        logger.info(f"Одиночный квиз (poll {poll_id}) обработан и удален из state.current_poll после таймаута.")
    else:
        logger.warning(f"handle_single_quiz_poll_end: Информация для poll_id {poll_id} (чат {chat_id_str}) не найдена. Пояснение не отправлено.")

async def show_quiz_session_results(context: ContextTypes.DEFAULT_TYPE, chat_id_str: str, error_occurred: bool = False):
    session = state.current_quiz_session.get(chat_id_str)
    if not session:
        logger.warning(f"show_quiz_session_results: Сессия для чата {chat_id_str} не найдена.")
        state.current_quiz_session.pop(chat_id_str, None) # Убедимся, что очищено
        return

    if job := session.get("next_question_job"):
        try:
            job.schedule_removal()
            session["next_question_job"] = None
        except Exception: pass

    num_q_in_session = session.get("actual_num_questions", NUMBER_OF_QUESTIONS_IN_SESSION)
    results_header = "🏁 Викторина завершена! 🏁\n\nРезультаты сессии:\n" if not error_occurred else "Викторина прервана.\n\nПромежуточные результаты сессии:\n"
    results_body = ""
    
    session_scores_data = session.get("session_scores")
    if not session_scores_data:
        results_body = "В этой сессии никто не участвовал или не набрал очков."
    else:
        sorted_session_participants = sorted(
            session_scores_data.items(),
            key=lambda item: (-item[1].get("score", 0), item[1].get("name", "").lower())
        )
        for rank, (user_id, data) in enumerate(sorted_session_participants):
            user_name = data.get("name", f"User {user_id}")
            session_score = data.get("score", 0)
            global_score_data = state.user_scores.get(chat_id_str, {}).get(user_id, {})
            global_score = global_score_data.get("score", 0)
            rank_prefix = f"{rank + 1}."
            
            # Медальки для сессионного рейтинга
            if rank == 0 and session_score > 0 : rank_prefix = "🥇"
            elif rank == 1 and session_score > 0 : rank_prefix = "🥈"
            elif rank == 2 and session_score > 0 : rank_prefix = "🥉"

            session_display = get_player_display(user_name, session_score, separator=":")
            results_body += (f"{rank_prefix} {session_display} (из {num_q_in_session} вопр.)\n"
                             f"    Общий счёт в чате: {pluralize_points(global_score)}\n")
        if len(sorted_session_participants) > 3:
             results_body += "\nОтличная игра, остальные участники!"
    
    full_results_text = results_header + results_body
    logger.debug(f"Attempting to send /quiz10 session results to chat {chat_id_str}. Text: '{full_results_text[:100]}...'")
    try:
        await context.bot.send_message(chat_id=chat_id_str, text=full_results_text)
    except Exception as e:
        logger.error(f"Ошибка при отправке результатов сессии в чат {chat_id_str}: {e}", exc_info=True)

    # Очистка current_poll от последнего опроса этой сессии, если он там еще есть
    current_poll_id_of_session = session.get("current_poll_id")
    if current_poll_id_of_session:
        poll_info_to_remove = state.current_poll.get(current_poll_id_of_session)
        # Убедимся, что это действительно опрос этой сессии
        if poll_info_to_remove and \
           poll_info_to_remove.get("quiz_session") and \
           poll_info_to_remove.get("associated_quiz_session_chat_id") == chat_id_str:
            state.current_poll.pop(current_poll_id_of_session, None)
            logger.debug(f"Poll {current_poll_id_of_session} (сессия) удален из state.current_poll при завершении сессии {chat_id_str}.")

    state.current_quiz_session.pop(chat_id_str, None)
    logger.info(f"Сессия /quiz10 для чата {chat_id_str} очищена.")

