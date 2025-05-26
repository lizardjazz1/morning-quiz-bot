# quiz_logic.py
import random
from typing import List, Dict, Any, Tuple, Optional
from datetime import timedelta
from telegram import Update, Poll # Update не используется напрямую здесь
from telegram.ext import ContextTypes
from telegram.error import BadRequest # Для обработки ошибок редактирования

from config import (logger, NUMBER_OF_QUESTIONS_IN_SESSION,
                    DEFAULT_POLL_OPEN_PERIOD, JOB_GRACE_PERIOD)
import state
from utils import pluralize # MODIFIED: pluralize_points -> pluralize
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

async def send_solution_if_available(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id_str: str,
    question_details: Dict[str, Any],
    q_index_for_log: int = -1, # For logging /quiz10 or daily_quiz question number
    poll_id_for_placeholder_lookup: Optional[str] = None
):
    """Отправляет пояснение к вопросу, если оно доступно. Редактирует заглушку, если она была."""
    solution = question_details.get("solution")
    if not solution:
        return

    q_text_for_header = question_details.get("question", "завершенному вопросу")
    log_q_ref_text = f"«{q_text_for_header[:30]}...»" if len(q_text_for_header) > 30 else f"«{q_text_for_header}»"
    log_q_ref_suffix = f" (вопрос сессии/ежедневной {q_index_for_log + 1})" if q_index_for_log != -1 else ""
    log_q_ref = f"{log_q_ref_text}{log_q_ref_suffix}"

    solution_message_full = f"💡{solution}"
    MAX_MESSAGE_LENGTH = 4096 # Telegram message length limit
    if len(solution_message_full) > MAX_MESSAGE_LENGTH:
        truncate_at = MAX_MESSAGE_LENGTH - 3 # For "..."
        solution_message_full = solution_message_full[:truncate_at] + "..."
        logger.warning(f"Пояснение для вопроса {log_q_ref} в чате {chat_id_str} было усечено.")

    placeholder_message_id: Optional[int] = None
    if poll_id_for_placeholder_lookup:
        poll_info = state.current_poll.get(poll_id_for_placeholder_lookup)
        if poll_info:
            placeholder_message_id = poll_info.get("solution_placeholder_message_id")
    
    if placeholder_message_id:
        logger.debug(f"Attempting to edit solution placeholder message {placeholder_message_id} in chat {chat_id_str} for question {log_q_ref}. Text: '{solution_message_full[:100]}...'")
        try:
            await context.bot.edit_message_text(
                text=solution_message_full,
                chat_id=chat_id_str,
                message_id=placeholder_message_id
            )
            logger.info(f"Отредактировано сообщение-заглушка с пояснением для вопроса {log_q_ref} в чате {chat_id_str}.")
            return # Успешно отредактировано
        except BadRequest as e:
            if "Message to edit not found" in str(e) or "message is not modified" in str(e).lower():
                logger.warning(f"Не удалось отредактировать заглушку ({placeholder_message_id}) для вопроса {log_q_ref} в чате {chat_id_str} (возможно, удалена или не изменена): {e}. Попытка отправить новое сообщение.")
            else:
                logger.error(f"Ошибка BadRequest при редактировании заглушки ({placeholder_message_id}) для вопроса {log_q_ref} в чате {chat_id_str}: {e}", exc_info=True)
            # Переходим к отправке нового сообщения в случае ошибки редактирования
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при редактировании заглушки ({placeholder_message_id}) для вопроса {log_q_ref} в чате {chat_id_str}: {e}", exc_info=True)
            # Переходим к отправке нового сообщения

    # Отправка нового сообщения, если заглушки не было или редактирование не удалось
    logger.debug(f"Attempting to send new solution message to chat {chat_id_str} for question {log_q_ref}. Text: '{solution_message_full[:100]}...'")
    try:
        await context.bot.send_message(chat_id=chat_id_str, text=solution_message_full)
        logger.info(f"Отправлено (новое) пояснение для вопроса {log_q_ref} в чате {chat_id_str}.")
    except Exception as e:
        logger.error(f"Ошибка при отправке (нового) пояснения для вопроса {log_q_ref} в чате {chat_id_str}: {e}", exc_info=True)

# --- Логика сессий /quiz10 ---
async def send_next_question_in_session(context: ContextTypes.DEFAULT_TYPE, chat_id_str: str):
    session = state.current_quiz_session.get(chat_id_str)
    if not session:
        logger.warning(f"send_next_question_in_session: Сессия для чата {chat_id_str} не найдена.")
        return

    current_q_idx = session["current_index"]
    actual_num_q = session["actual_num_questions"]

    if current_q_idx >= actual_num_q:
        logger.info(f"Все {actual_num_q} вопросов сессии {chat_id_str} были отправлены. Завершение сессии управляется handle_current_poll_end.")
        # handle_current_poll_end для последнего вопроса вызовет show_quiz_session_results
        return

    q_details = session["questions"][current_q_idx]
    is_last_question = (current_q_idx == actual_num_q - 1)
    poll_open_period = DEFAULT_POLL_OPEN_PERIOD

    poll_question_text_for_api = q_details['question']
    full_poll_question_header = f"Вопрос {current_q_idx + 1}/{actual_num_q}"
    if original_cat := q_details.get("original_category"):
        full_poll_question_header += f" (Кат: {original_cat})"
    full_poll_question_header += f"\n{poll_question_text_for_api}" # Текст вопроса после заголовка

    MAX_POLL_QUESTION_LENGTH = 255 # Telegram API limit for poll question text
    if len(full_poll_question_header) > MAX_POLL_QUESTION_LENGTH:
        truncate_at = MAX_POLL_QUESTION_LENGTH - 3 # For "..."
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
        session["current_poll_id"] = sent_poll_msg.poll.id # Обновляем ID текущего опроса в сессии
        session["current_index"] += 1 # Увеличиваем индекс для следующего вопроса

        # Сохраняем информацию о новом опросе в state.current_poll
        current_poll_entry = {
            "chat_id": chat_id_str, "message_id": sent_poll_msg.message_id,
            "correct_index": poll_correct_option_id, "quiz_session": True,
            "question_details": q_details, "associated_quiz_session_chat_id": chat_id_str,
            "is_last_question": is_last_question,
            "next_q_triggered_by_answer": False, # Флаг для досрочного ответа
            "question_session_index": current_q_idx, # 0-based index for this question in session
            "solution_placeholder_message_id": None, # Инициализация
            "processed_by_early_answer": False # Инициализация
        }
        state.current_poll[sent_poll_msg.poll.id] = current_poll_entry
        logger.info(f"Отправлен вопрос {current_q_idx + 1}/{actual_num_q} сессии {chat_id_str}. Poll ID: {sent_poll_msg.poll.id}. Is last: {is_last_question}")

        # Отправка заглушки, если есть пояснение
        if q_details.get("solution"):
            try:
                placeholder_msg = await context.bot.send_message(chat_id=chat_id_str, text="💡")
                # Сохраняем ID заглушки в state.current_poll для данного poll_id
                state.current_poll[sent_poll_msg.poll.id]["solution_placeholder_message_id"] = placeholder_msg.message_id
                logger.info(f"Отправлена заглушка '💡' для poll {sent_poll_msg.poll.id} в чате {chat_id_str}.")
            except Exception as e_sol_pl:
                 logger.error(f"Не удалось отправить заглушку '💡' для poll {sent_poll_msg.poll.id} в чате {chat_id_str}: {e_sol_pl}")

        # Планируем задачу для обработки конца этого опроса
        job_delay_seconds = poll_open_period + JOB_GRACE_PERIOD
        job_name = f"poll_end_timeout_chat_{chat_id_str}_poll_{sent_poll_msg.poll.id}"
        if context.job_queue:
            # Удаляем старые job'ы с таким же именем (на всякий случай, если что-то пошло не так)
            existing_jobs = context.job_queue.get_jobs_by_name(job_name)
            for old_job in existing_jobs: old_job.schedule_removal()

            current_poll_end_job = context.job_queue.run_once(
                handle_current_poll_end, timedelta(seconds=job_delay_seconds),
                data={"chat_id_str": chat_id_str, "ended_poll_id": sent_poll_msg.poll.id}, # Передаем ID завершенного опроса
                name=job_name
            )
            # Сохраняем ссылку на job в сессии (для таймаута *этого* отправленного вопроса)
            session["next_question_job"] = current_poll_end_job 
    except Exception as e:
        logger.error(f"Ошибка при отправке вопроса сессии ({current_q_idx + 1}) в чате {chat_id_str}: {e}", exc_info=True)
        # Если ошибка, завершаем сессию с текущими результатами
        await show_quiz_session_results(context, chat_id_str, error_occurred=True)

async def handle_current_poll_end(context: ContextTypes.DEFAULT_TYPE):
    if not context.job or not context.job.data:
        logger.error("handle_current_poll_end вызван без job data.")
        return

    job_data = context.job.data
    chat_id_str: str = job_data["chat_id_str"]
    ended_poll_id: str = job_data["ended_poll_id"] # ID опроса, для которого сработал таймаут

    poll_info = state.current_poll.get(ended_poll_id) # Сначала получаем, потом удаляем
    session = state.current_quiz_session.get(chat_id_str) # Сессия может быть уже завершена, если это /stopquiz

    if not poll_info:
        logger.warning(
            f"Job 'handle_current_poll_end' для poll {ended_poll_id} в чате {chat_id_str}: poll_info не найден. "
            f"Возможно, сессия была прервана или poll уже обработан иначе."
        )
        # If poll_info is gone, but it was a quiz_session and the session is still active, it's an error.
        # This check is mostly for quiz10, not daily quiz, as daily quiz doesn't remove its poll_info early.
        if session and poll_info.get("quiz_session"):
            logger.error(f"Нештатная ситуация: poll_info для {ended_poll_id} отсутствует, но сессия {chat_id_str} активна. Завершение сессии.")
            await show_quiz_session_results(context, chat_id_str, error_occurred=True)
        return
    
    q_idx_from_poll_info = poll_info.get("question_session_index", -1)
    logger.info(f"Job 'handle_current_poll_end' сработал для чата {chat_id_str}, poll_id {ended_poll_id} (вопрос сессии/ежедневной ~{q_idx_from_poll_info + 1}).")

    # Отправить решение для завершенного опроса
    await send_solution_if_available(
        context, chat_id_str, 
        poll_info["question_details"], 
        q_idx_from_poll_info, 
        poll_id_for_placeholder_lookup=ended_poll_id
    )
    
    is_last_q_from_poll_info = poll_info.get("is_last_question", False)
    processed_early = poll_info.get("processed_by_early_answer", False)
    is_quiz10_session_poll = poll_info.get("quiz_session", False)
    is_daily_quiz_poll = poll_info.get("daily_quiz", False) # NEW: Check if it's a daily quiz poll
    
    state.current_poll.pop(ended_poll_id, None) # Удаляем инфо об опросе ПОСЛЕ использования
    logger.debug(f"Poll {ended_poll_id} удален из state.current_poll после обработки таймаута.")

    # NEW: If it's a daily quiz poll, we are done. The next question is handled by a separate job.
    if is_daily_quiz_poll:
        logger.info(f"Таймаут ежедневной викторины для poll {ended_poll_id} в чате {chat_id_str}. Решение отправлено. Следующий вопрос управляется отдельным Job'ом.")
        return

    if not session: # If a /quiz10 session was stopped by /stopquiz before this moment
        logger.info(f"Сессия {chat_id_str} уже не активна при обработке таймаута poll {ended_poll_id}. Результаты были (или будут) показаны stopquiz.")
        return

    # Existing /quiz10 session logic below this point
    if is_last_q_from_poll_info and is_quiz10_session_poll:
        logger.info(f"Время для ПОСЛЕДНЕГО вопроса (индекс {q_idx_from_poll_info}, poll {ended_poll_id}) сессии {chat_id_str} истекло. Показ результатов.")
        await show_quiz_session_results(context, chat_id_str)
    elif is_quiz10_session_poll: # НЕ последний вопрос /quiz10
        if not processed_early:
            logger.info(f"Тайм-аут для НЕ последнего вопроса (индекс {q_idx_from_poll_info}, poll {ended_poll_id}) в сессии {chat_id_str}. Отправляем следующий.")
            await send_next_question_in_session(context, chat_id_str)
        else:
            logger.info(
                f"Таймаут для poll {ended_poll_id} (вопрос сессии {q_idx_from_poll_info + 1}), "
                f"но следующий вопрос уже был отправлен из-за досрочного ответа. Решение для poll {ended_poll_id} отправлено."
            )

# --- Логика одиночного /quiz ---
async def handle_single_quiz_poll_end(context: ContextTypes.DEFAULT_TYPE):
    if not context.job or not context.job.data:
        logger.error("handle_single_quiz_poll_end: Job data missing.")
        return

    job_data = context.job.data
    chat_id_str: str = job_data["chat_id_str"]
    poll_id: str = job_data["poll_id"]
    logger.info(f"Job 'handle_single_quiz_poll_end' сработал для poll_id {poll_id} в чате {chat_id_str}.")

    poll_info = state.current_poll.get(poll_id) # Сначала получаем, потом удаляем

    if poll_info:
        question_details = poll_info.get("question_details")
        # Проверяем, что это одиночный квиз, есть детали и есть решение
        if not poll_info.get("quiz_session", False) and not poll_info.get("daily_quiz", False) and question_details: # Убедимся, что это не сессионный/дейли
            await send_solution_if_available(
                context, chat_id_str,
                question_details, 
                # q_index_for_log не релевантен для одиночного, можно опустить или -1
                poll_id_for_placeholder_lookup=poll_id
            )
        state.current_poll.pop(poll_id, None) # Удаляем после обработки
        logger.info(f"Одиночный квиз (poll {poll_id}) обработан и удален из state.current_poll после таймаута.")
    else:
        logger.warning(f"handle_single_quiz_poll_end: Информация для poll_id {poll_id} (чат {chat_id_str}) не найдена. Пояснение не отправлено.")


# --- Отображение результатов сессии /quiz10 ---
async def show_quiz_session_results(context: ContextTypes.DEFAULT_TYPE, chat_id_str: str, error_occurred: bool = False):
    session = state.current_quiz_session.get(chat_id_str) # Получаем сессию
    # Не удаляем сессию здесь, это должно быть последним действием

    if not session:
        logger.warning(f"show_quiz_session_results: Сессия для чата {chat_id_str} не найдена (возможно, уже завершена).")
        # Убедимся, что она точно удалена, если кто-то вызвал show_quiz_session_results для уже несуществующей сессии
        state.current_quiz_session.pop(chat_id_str, None) 
        return

    # Отменяем job следующего вопроса, если он еще есть (это job для ПОСЛЕДНЕГО отправленного poll'а)
    # Этот job должен был бы завершиться естественным образом, но /stopquiz может вызвать show_quiz_session_results досрочно.
    if job := session.get("next_question_job"):
        try:
            job.schedule_removal()
            session["next_question_job"] = None # Обнуляем ссылку в сессии
            logger.debug(f"Job {job.name} (таймаут последнего вопроса) удален при показе результатов сессии {chat_id_str}.")
        except Exception: pass # Может быть уже удален

    num_q_in_session = session.get("actual_num_questions", NUMBER_OF_QUESTIONS_IN_SESSION)
    results_header = "🏁 Викторина завершена! 🏁\n\nРезультаты сессии:\n" if not error_occurred else "Викторина прервана.\n\nПромежуточные результаты сессии:\n"
    results_body = ""

    session_scores_data = session.get("session_scores")
    if not session_scores_data:
        results_body = "В этой сессии никто не участвовал или не набрал очков."
    else:
        sorted_session_participants = sorted(
            session_scores_data.items(),
            key=lambda item: (-item[1].get("score", 0), item[1].get("name", "").lower()) # Сортировка по очкам (убыв), затем по имени (возр)
        )
        for rank, (user_id, data) in enumerate(sorted_session_participants):
            user_name = data.get("name", f"User {user_id}")
            session_score = data.get("score", 0)
            global_score_data = state.user_scores.get(chat_id_str, {}).get(user_id, {})
            global_score = global_score_data.get("score", 0)
            rank_prefix = f"{rank + 1}."

            if rank == 0 and session_score > 0 : rank_prefix = "🥇"
            elif rank == 1 and session_score > 0 : rank_prefix = "🥈"
            elif rank == 2 and session_score > 0 : rank_prefix = "🥉"

            session_display = get_player_display(user_name, session_score, separator=":")
            # MODIFIED: pluralize_points -> pluralize, providing specific forms for "очко"
            global_score_display = pluralize(global_score, "очко", "очка", "очков")
            results_body += (f"{rank_prefix} {session_display} (из {num_q_in_session} вопр.)\n"
                             f"    Общий счёт в чате: {global_score_display}\n")
        if len(sorted_session_participants) > 3: # Небольшое сообщение для остальных
             results_body += "\nОтличная игра, остальные участники!"
    
    full_results_text = results_header + results_body
    logger.debug(f"Attempting to send /quiz10 session results to chat {chat_id_str}. Text: '{full_results_text[:100]}...'")
    try:
        await context.bot.send_message(chat_id=chat_id_str, text=full_results_text)
    except Exception as e:
        logger.error(f"Ошибка при отправке результатов сессии в чат {chat_id_str}: {e}", exc_info=True)

    # Очистка current_poll от последнего опроса этой сессии, если он там еще есть и принадлежит этой сессии
    # (на случай если poll не был удален в handle_current_poll_end по какой-то причине, e.g. /stopquiz)
    current_poll_id_of_session = session.get("current_poll_id")
    if current_poll_id_of_session:
        poll_info_to_remove = state.current_poll.get(current_poll_id_of_session)
        if poll_info_to_remove and \
           poll_info_to_remove.get("quiz_session") and \
           str(poll_info_to_remove.get("associated_quiz_session_chat_id")) == str(chat_id_str): # Сравнение как строки на всякий случай
            state.current_poll.pop(current_poll_id_of_session, None)
            logger.debug(f"Poll {current_poll_id_of_session} (сессия) удален из state.current_poll при завершении сессии {chat_id_str} (show_quiz_session_results).")

    state.current_quiz_session.pop(chat_id_str, None) # Удаляем сессию из активных
    logger.info(f"Сессия /quiz10 для чата {chat_id_str} очищена (show_quiz_session_results).")
