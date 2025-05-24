# quiz_logic.py
import random
from typing import List, Dict, Any, Tuple
from datetime import timedelta
from telegram import Update, Poll # Update нужен для ContextTypes.DEFAULT_TYPE, Poll для типов
from telegram.ext import ContextTypes

# Импорты из других модулей проекта
from config import (logger, NUMBER_OF_QUESTIONS_IN_SESSION,
                    DEFAULT_POLL_OPEN_PERIOD, FINAL_ANSWER_WINDOW_SECONDS, JOB_GRACE_PERIOD)
import state # Для доступа к quiz_data, current_quiz_session, current_poll
from utils import pluralize_points # Обновленная функция для склонения слова "очки"
# Импортируем get_player_display для единообразного отображения в результатах сессии
from handlers.rating_handlers import get_player_display

# --- Вспомогательные функции для викторины ---

# get_random_questions: Возвращает случайные вопросы из указанной категории.
# Используется в command_handlers.py (/quiz, /quiz10).
def get_random_questions(category: str, count: int = 1) -> List[Dict[str, Any]]:
    cat_q_list = state.quiz_data.get(category)
    if not isinstance(cat_q_list, list) or not cat_q_list:
        return []
    return [q.copy() for q in random.sample(cat_q_list, min(count, len(cat_q_list)))]

# get_random_questions_from_all: Возвращает случайные вопросы из всех категорий.
# Используется в command_handlers.py (/quiz, /quiz10).
def get_random_questions_from_all(count: int) -> List[Dict[str, Any]]:
    all_q = [q.copy() for questions_in_category in state.quiz_data.values() if isinstance(questions_in_category, list) for q in questions_in_category]
    if not all_q:
        return []
    return random.sample(all_q, min(count, len(all_q)))

# prepare_poll_options: Готовит данные для отправки опроса (Poll).
# Используется в command_handlers.py (/quiz) и здесь же в send_next_question_in_session.
def prepare_poll_options(q_details: Dict[str, Any]) -> Tuple[str, List[str], int, List[str]]:
    q_text, opts_orig = q_details["question"], q_details["options"]
    correct_answer_text = opts_orig[q_details["correct_option_index"]] # Текст правильного ответа

    opts_shuffled = list(opts_orig) # Копируем, чтобы не изменять оригинальный список
    random.shuffle(opts_shuffled)

    try:
        new_correct_idx = opts_shuffled.index(correct_answer_text)
    except ValueError: # На случай, если что-то пошло не так (например, дубликаты или изменение во время копирования)
        logger.error(f"Не удалось найти '{correct_answer_text}' в перемешанных опциях: {opts_shuffled}. Используем оригинальный индекс.")
        return q_text, list(opts_orig), q_details["correct_option_index"], list(opts_orig)

    return q_text, opts_shuffled, new_correct_idx, list(opts_orig) # Возвращаем копию оригинальных опций

async def send_solution_if_available(context: ContextTypes.DEFAULT_TYPE, chat_id_str: str, question_details: Dict[str, Any], q_index_for_log: int = -1):
    """Отправляет пояснение к вопросу, если оно доступно."""
    solution = question_details.get("solution")
    # Для лога и заголовка используем короткую версию вопроса или стандартный текст
    q_text_for_header = question_details.get("question", "завершенному вопросу")
    log_q_ref_text = f"«{q_text_for_header[:30]}...»" if len(q_text_for_header) > 30 else f"«{q_text_for_header}»"
    # Для лога: добавляем индекс вопроса сессии, если он предоставлен (q_index_for_log != -1)
    log_q_ref_suffix = f" (вопрос сессии {q_index_for_log + 1})" if q_index_for_log != -1 else ""
    log_q_ref = f"{log_q_ref_text}{log_q_ref_suffix}"


    if solution:
        try:
            # Сообщение с пояснением: заголовок указывает на вопрос, к которому оно относится
            solution_message = f"💡 Пояснение к вопросу {log_q_ref_text}:\n{solution}"

            MAX_MESSAGE_LENGTH = 4096 # Telegram message length limit
            if len(solution_message) > MAX_MESSAGE_LENGTH:
                truncate_at = MAX_MESSAGE_LENGTH - 3 # Для "..."
                solution_message = solution_message[:truncate_at] + "..."
                logger.warning(f"Пояснение для вопроса {log_q_ref} в чате {chat_id_str} было усечено до {MAX_MESSAGE_LENGTH} символов.")

            await context.bot.send_message(chat_id=chat_id_str, text=solution_message)
            logger.info(f"Отправлено пояснение для вопроса {log_q_ref} в чате {chat_id_str}.")
        except Exception as e:
            logger.error(f"Ошибка при отправке пояснения для вопроса {log_q_ref} в чате {chat_id_str}: {e}", exc_info=True)

# --- Логика сессии /quiz10 ---

# send_next_question_in_session: Отправляет следующий вопрос в рамках сессии /quiz10.
async def send_next_question_in_session(context: ContextTypes.DEFAULT_TYPE, chat_id_str: str):
    session = state.current_quiz_session.get(chat_id_str)
    if not session:
        logger.warning(f"send_next_question_in_session: Сессия для чата {chat_id_str} не найдена или уже удалена.")
        return

    if job := session.get("next_question_job"): # Отменяем предыдущий таймаут job, если он был
        try:
            job.schedule_removal()
        except Exception:
            pass # Job мог быть уже выполнен или удален
        session["next_question_job"] = None

    current_q_idx = session["current_index"]
    actual_num_q = session["actual_num_questions"]

    if current_q_idx >= actual_num_q:
        logger.info(f"Все {actual_num_q} вопросов сессии {chat_id_str} были отправлены. Завершение сессии.")
        # Пояснение к последнему вопросу должно было быть отправлено в handle_current_poll_end или poll_answer_handler (при досрочном ответе)
        await show_quiz_session_results(context, chat_id_str)
        return

    q_details = session["questions"][current_q_idx]
    is_last_question = (current_q_idx == actual_num_q - 1)
    poll_open_period = FINAL_ANSWER_WINDOW_SECONDS if is_last_question else DEFAULT_POLL_OPEN_PERIOD

    poll_question_text_for_api = q_details['question']

    full_poll_question_header = f"Вопрос {current_q_idx + 1}/{actual_num_q}"
    if original_cat := q_details.get("original_category"):
        full_poll_question_header += f" (Кат: {original_cat})"
    full_poll_question_header += f"\n{poll_question_text_for_api}"

    MAX_POLL_QUESTION_LENGTH = 255 # Технический лимит Telegram
    if len(full_poll_question_header) > MAX_POLL_QUESTION_LENGTH:
        truncate_at = MAX_POLL_QUESTION_LENGTH - 3
        full_poll_question_header = full_poll_question_header[:truncate_at] + "..."
        logger.warning(f"Текст вопроса для poll в чате {chat_id_str} был усечен до {MAX_POLL_QUESTION_LENGTH} символов.")

    _, poll_options, poll_correct_option_id, _ = prepare_poll_options(q_details)

    try:
        sent_poll_msg = await context.bot.send_poll(
            chat_id=chat_id_str,
            question=full_poll_question_header,
            options=poll_options,
            type=Poll.QUIZ,
            correct_option_id=poll_correct_option_id,
            open_period=poll_open_period,
            is_anonymous=False
        )

        session["current_poll_id"] = sent_poll_msg.poll.id
        session["current_index"] += 1 # Индекс инкрементируется здесь, указывая на следующий вопрос

        state.current_poll[sent_poll_msg.poll.id] = {
            "chat_id": chat_id_str,
            "message_id": sent_poll_msg.message_id,
            "correct_index": poll_correct_option_id,
            "quiz_session": True,
            "question_details": q_details, # Сохраняем детали, включая solution
            "associated_quiz_session_chat_id": chat_id_str,
            "is_last_question": is_last_question,
            "next_q_triggered_by_answer": False,
            "question_session_index": current_q_idx # Сохраняем индекс вопроса в сессии
        }
        logger.info(f"Отправлен вопрос {current_q_idx + 1}/{actual_num_q} сессии {chat_id_str}. Poll ID: {sent_poll_msg.poll.id}")

        job_delay_seconds = poll_open_period + JOB_GRACE_PERIOD
        job_name = f"poll_end_timeout_{chat_id_str}_{sent_poll_msg.poll.id}"

        if context.job_queue:
            existing_jobs = context.job_queue.get_jobs_by_name(job_name)
            for old_job in existing_jobs:
                old_job.schedule_removal() # Удаляем дубликаты, если есть
                logger.debug(f"Удален дублирующийся/старый job: {old_job.name}")

            next_question_timeout_job = context.job_queue.run_once(
                handle_current_poll_end, # Эта функция обработает таймаут для сессионного вопроса
                timedelta(seconds=job_delay_seconds),
                data={"chat_id": chat_id_str, "ended_poll_id": sent_poll_msg.poll.id},
                name=job_name
            )
            session["next_question_job"] = next_question_timeout_job
    except Exception as e:
        logger.error(f"Ошибка при отправке вопроса сессии в чате {chat_id_str}: {e}", exc_info=True)
        await show_quiz_session_results(context, chat_id_str, error_occurred=True)

# handle_current_poll_end: Обрабатывает завершение опроса по тайм-ауту в сессии /quiz10.
async def handle_current_poll_end(context: ContextTypes.DEFAULT_TYPE):
    if not context.job or not context.job.data: # type: ignore
        logger.error("handle_current_poll_end вызван без job data.")
        return

    job_data = context.job.data # type: ignore
    chat_id_str: str = job_data["chat_id"]
    ended_poll_id: str = job_data["ended_poll_id"]

    poll_info_that_ended = state.current_poll.pop(ended_poll_id, None)
    q_idx_from_poll_info = poll_info_that_ended.get("question_session_index", -1) if poll_info_that_ended else -1
    logger.info(f"Job 'handle_current_poll_end' сработал для чата {chat_id_str}, poll_id {ended_poll_id} (вопрос сессии ~{q_idx_from_poll_info + 1}).")

    session = state.current_quiz_session.get(chat_id_str)
    if not session:
        logger.warning(f"Сессия {chat_id_str} не найдена при обработке job для poll {ended_poll_id}. Опрос завершен.")
        if poll_info_that_ended and poll_info_that_ended.get("question_details"):
            await send_solution_if_available(context, chat_id_str, poll_info_that_ended["question_details"], q_idx_from_poll_info)
        return

    if not poll_info_that_ended:
        logger.warning(f"Poll {ended_poll_id} не найден в state.current_poll при обработке job (вероятно, обработан досрочным ответом). Job для {chat_id_str} завершен.")
        return

    if poll_info_that_ended.get("next_q_triggered_by_answer"):
        logger.info(f"Job для poll {ended_poll_id} (вопрос {q_idx_from_poll_info + 1}) сработал, но следующий вопрос/пояснение уже инициированы ответом. Job завершен.")
        return

    # Отправляем пояснение для сессионного вопроса, который завершился по таймауту
    await send_solution_if_available(context, chat_id_str, poll_info_that_ended["question_details"], q_idx_from_poll_info)

    is_last_q_from_poll_info = poll_info_that_ended.get("is_last_question", False)
    if is_last_q_from_poll_info:
        logger.info(f"Время для последнего вопроса (индекс {q_idx_from_poll_info}) сессии {chat_id_str} истекло. Показ результатов.")
        await show_quiz_session_results(context, chat_id_str)
    else:
        if session["current_index"] == q_idx_from_poll_info + 1:
             logger.info(f"Тайм-аут для вопроса {q_idx_from_poll_info + 1} в сессии {chat_id_str} (poll {ended_poll_id}). Отправляем следующий.")
             await send_next_question_in_session(context, chat_id_str)
        else:
            logger.warning(f"Job для poll {ended_poll_id} в сессии {chat_id_str} завершен. "
                           f"Состояние индекса: current_index в сессии={session['current_index']}, "
                           f"индекс завершенного вопроса={q_idx_from_poll_info}. "
                           "Следующий вопрос не отправлен этим job'ом, так как состояние индексов расходится с ожидаемым для простого таймаута.")


# ИЗМЕНЕНИЕ: Новая функция для обработки таймаута одиночного квиза и отправки пояснения
async def handle_single_quiz_poll_end(context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает завершение одиночного опроса (/quiz) по тайм-ауту.
    Отправляет пояснение, если оно есть, и очищает информацию об опросе из state.
    """
    if not context.job or not context.job.data: # type: ignore
        logger.error("handle_single_quiz_poll_end: Job data missing.")
        return

    job_data = context.job.data # type: ignore
    chat_id_str: str = job_data["chat_id_str"]
    poll_id: str = job_data["poll_id"]

    logger.info(f"Job 'handle_single_quiz_poll_end' сработал для poll_id {poll_id} в чате {chat_id_str}.")

    # Получаем информацию об опросе. Он должен быть еще в state.current_poll.
    # ВАЖНО: .pop() его здесь, чтобы избежать гонки состояний, если job как-то запустится дважды или другие обработчики попытаются его изменить
    poll_info = state.current_poll.pop(poll_id, None)

    if poll_info:
        question_details = poll_info.get("question_details")
        is_quiz_session_poll = poll_info.get("quiz_session", False)

        # Убедимся, что это действительно одиночный квиз
        if not is_quiz_session_poll and question_details and question_details.get("solution"):
            try:
                # Используем существующую функцию send_solution_if_available
                # q_index_for_log = -1 (по умолчанию) подходит для одиночных квизов, так как не выводит номер вопроса сессии
                await send_solution_if_available(context, chat_id_str, question_details)
                logger.info(f"Пояснение отправлено для одиночного квиза (poll {poll_id}) в чате {chat_id_str} по таймауту.")
            except Exception as e:
                logger.error(f"Ошибка при отправке пояснения для одиночного квиза (poll {poll_id}) в чате {chat_id_str} по таймауту: {e}", exc_info=True)
        
        # Информация об опросе уже удалена из state.current_poll вызовом .pop() выше.
        logger.info(f"Одиночный квиз (poll {poll_id}) обработан и удален из state.current_poll после таймаута в чате {chat_id_str}.")
    else:
        logger.warning(f"handle_single_quiz_poll_end: Информация для poll_id {poll_id} (чат {chat_id_str}) не найдена в state.current_poll (возможно, уже удален). "
                       "Пояснение не отправлено.")


# show_quiz_session_results: Показывает результаты завершенной сессии /quiz10.
async def show_quiz_session_results(context: ContextTypes.DEFAULT_TYPE, chat_id_str: str, error_occurred: bool = False):
    session = state.current_quiz_session.get(chat_id_str)
    if not session:
        logger.warning(f"show_quiz_session_results: Сессия для чата {chat_id_str} не найдена для показа результатов.")
        state.current_quiz_session.pop(chat_id_str, None) # Убедимся, что удалена, если как-то осталась
        return

    # Отменяем job на следующий вопрос, если он еще существует (например, при /stopquiz или если сессия завершилась до таймаута последнего вопроса)
    if job := session.get("next_question_job"):
        try:
            job.schedule_removal()
            session["next_question_job"] = None # Очищаем ссылку на job
        except Exception:
            pass

    num_q_in_session = session.get("actual_num_questions", NUMBER_OF_QUESTIONS_IN_SESSION)
    results_header = "🏁 Викторина завершена! 🏁\n\nРезультаты сессии:\n" if not error_occurred else "Викторина прервана.\n\nПромежуточные результаты сессии:\n"
    results_body = ""

    if not session.get("session_scores"):
        results_body = "В этой сессии никто не участвовал или не набрал очков."
    else:
        sorted_session_participants = sorted(
            session["session_scores"].items(),
            key=lambda item: (-item[1].get("score", 0), item[1].get("name", "").lower())
        )

        for rank, (user_id, data) in enumerate(sorted_session_participants):
            user_name = data.get("name", f"User {user_id}")
            session_score = data.get("score", 0)
            global_score_data = state.user_scores.get(chat_id_str, {}).get(user_id, {})
            global_score = global_score_data.get("score", 0) # Глобальный счет пользователя в этом чате

            rank_prefix = f"{rank + 1}."
            # Используем get_player_display для отображения сессионного счета,
            # передавая ":" в качестве разделителя
            session_display = get_player_display(user_name, session_score, separator=":")

            results_body += (f"{rank_prefix} {session_display} (из {num_q_in_session} вопр.)\n"
                             f"    Общий счёт в чате: {pluralize_points(global_score)}\n")

        if len(sorted_session_participants) > 3:
             results_body += "\nОтличная игра, остальные участники!"

    try:
        await context.bot.send_message(chat_id=chat_id_str, text=results_header + results_body)
    except Exception as e:
        logger.error(f"Ошибка при отправке результатов сессии в чат {chat_id_str}: {e}", exc_info=True)

    # Очищаем информацию о последнем опросе сессии из state.current_poll, если он там остался
    # Это может быть необходимо, если show_quiz_session_results вызывается до того, как poll был обработан таймаутом или досрочным ответом
    current_poll_id_of_session = session.get("current_poll_id")
    if current_poll_id_of_session and current_poll_id_of_session in state.current_poll:
        poll_data_to_check = state.current_poll.get(current_poll_id_of_session)
        if poll_data_to_check and poll_data_to_check.get("quiz_session") and poll_data_to_check.get("associated_quiz_session_chat_id") == chat_id_str:
            state.current_poll.pop(current_poll_id_of_session, None)
            logger.debug(f"Poll {current_poll_id_of_session} (сессия) удален из state.current_poll при завершении сессии {chat_id_str}.")

    state.current_quiz_session.pop(chat_id_str, None)
    logger.info(f"Сессия для чата {chat_id_str} очищена.")

