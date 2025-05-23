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
from utils import pluralize_points # Новая функция для склонения слова "очки"

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
    all_q = [q.copy() for q_list in state.quiz_data.values() if isinstance(q_list, list) for q in q_list]
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
        # В этом маловероятном случае, возвращаем оригинальные опции и индекс
        # Это предотвратит падение, но может привести к тому, что опции не будут перемешаны.
        return q_text, list(opts_orig), q_details["correct_option_index"], list(opts_orig)
        
    return q_text, opts_shuffled, new_correct_idx, list(opts_orig) # Возвращаем копию оригинальных опций

# --- Логика сессии /quiz10 ---

# send_next_question_in_session: Отправляет следующий вопрос в рамках сессии /quiz10.
# Вызывается из command_handlers.py (при старте /quiz10),
# из poll_answer_handler.py (при досрочном ответе),
# и из handle_current_poll_end (по тайм-ауту).
async def send_next_question_in_session(context: ContextTypes.DEFAULT_TYPE, chat_id_str: str):
    session = state.current_quiz_session.get(chat_id_str)
    if not session:
        logger.warning(f"send_next_question_in_session: Сессия для чата {chat_id_str} не найдена или уже удалена.")
        return

    if job := session.get("next_question_job"):
        try:
            job.schedule_removal()
        except Exception:
            pass
        session["next_question_job"] = None

    current_q_idx = session["current_index"]
    actual_num_q = session["actual_num_questions"]

    if current_q_idx >= actual_num_q:
        logger.info(f"Все {actual_num_q} вопросов сессии {chat_id_str} были отправлены. Завершение сессии.")
        await show_quiz_session_results(context, chat_id_str)
        return

    q_details = session["questions"][current_q_idx]
    is_last_question = (current_q_idx == actual_num_q - 1)
    poll_open_period = FINAL_ANSWER_WINDOW_SECONDS if is_last_question else DEFAULT_POLL_OPEN_PERIOD

    question_display_text = f"Вопрос {current_q_idx + 1}/{actual_num_q}\n"
    if original_cat := q_details.get("original_category"):
        question_display_text += f"Категория: {original_cat}\n"
    # Текст самого вопроса для Poll.API не должен быть слишком длинным.
    # Telegram ограничивает длину вопроса в Poll до 255-300 символов (зависит от клиента).
    # Мы передаем `question_display_text` в `question` параметра `send_poll`.
    # Если `q_details['question']` сам по себе длинный, то `question_display_text` может превысить лимит.
    # Для простоты пока оставляем как есть, но стоит помнить о лимите.
    poll_question_text_for_api = q_details['question'] # Текст вопроса из JSON

    # Формируем заголовок, который будет виден над вариантами ответов
    # Этот текст будет в поле "question" опроса.
    full_poll_question_header = f"Вопрос {current_q_idx + 1}/{actual_num_q}"
    if original_cat := q_details.get("original_category"):
        full_poll_question_header += f" (Кат: {original_cat})"
    full_poll_question_header += f"\n{poll_question_text_for_api}"


    # Убедимся, что длина заголовка не превышает лимиты Telegram для поля question в Poll
    # Обычно это около 255-300 символов. Лучше ориентироваться на 255.
    MAX_POLL_QUESTION_LENGTH = 255 
    if len(full_poll_question_header) > MAX_POLL_QUESTION_LENGTH:
        truncate_at = MAX_POLL_QUESTION_LENGTH - 3 # для "..."
        full_poll_question_header = full_poll_question_header[:truncate_at] + "..."
        logger.warning(f"Текст вопроса для poll в чате {chat_id_str} был усечен до {MAX_POLL_QUESTION_LENGTH} символов.")


    _, poll_options, poll_correct_option_id, _ = prepare_poll_options(q_details)

    try:
        sent_poll_msg = await context.bot.send_poll(
            chat_id=chat_id_str,
            question=full_poll_question_header, # Используем сформированный и, возможно, усеченный заголовок
            options=poll_options,
            type=Poll.QUIZ,
            correct_option_id=poll_correct_option_id,
            open_period=poll_open_period,
            is_anonymous=False
        )

        session["current_poll_id"] = sent_poll_msg.poll.id
        session["current_index"] += 1

        state.current_poll[sent_poll_msg.poll.id] = {
            "chat_id": chat_id_str,
            "message_id": sent_poll_msg.message_id,
            "correct_index": poll_correct_option_id,
            "quiz_session": True,
            "question_details": q_details,
            "associated_quiz_session_chat_id": chat_id_str,
            "is_last_question": is_last_question,
            "next_q_triggered_by_answer": False
        }
        logger.info(f"Отправлен вопрос {current_q_idx + 1}/{actual_num_q} сессии {chat_id_str}. Poll ID: {sent_poll_msg.poll.id}")

        job_delay_seconds = poll_open_period + JOB_GRACE_PERIOD
        job_name = f"poll_end_timeout_{chat_id_str}_{sent_poll_msg.poll.id}"

        if context.job_queue:
            # Удаляем предыдущие jobs с таким же именем, если они существуют
            # Это может произойти, если бот перезапускался или были ошибки
            existing_jobs = context.job_queue.get_jobs_by_name(job_name)
            for old_job in existing_jobs:
                old_job.schedule_removal()
                logger.debug(f"Удален дублирующийся/старый job: {old_job.name}")
                
            next_question_timeout_job = context.job_queue.run_once(
                handle_current_poll_end,
                timedelta(seconds=job_delay_seconds),
                data={"chat_id": chat_id_str, "ended_poll_id": sent_poll_msg.poll.id, "ended_poll_q_idx": current_q_idx},
                name=job_name
            )
            session["next_question_job"] = next_question_timeout_job
    except Exception as e:
        logger.error(f"Ошибка при отправке вопроса сессии в чате {chat_id_str}: {e}", exc_info=True)
        await show_quiz_session_results(context, chat_id_str, error_occurred=True)

# handle_current_poll_end: Обрабатывает завершение опроса по тайм-ауту в сессии /quiz10.
# Вызывается через JobQueue, запланированный в send_next_question_in_session.
async def handle_current_poll_end(context: ContextTypes.DEFAULT_TYPE):
    if not context.job or not context.job.data: # type: ignore
        logger.error("handle_current_poll_end вызван без job data.")
        return

    job_data = context.job.data # type: ignore
    chat_id_str: str = job_data["chat_id"]
    ended_poll_id: str = job_data["ended_poll_id"]
    ended_poll_q_idx: int = job_data["ended_poll_q_idx"]

    logger.info(f"Job 'handle_current_poll_end' сработал для чата {chat_id_str}, poll_id {ended_poll_id} (вопрос {ended_poll_q_idx + 1}).")

    session = state.current_quiz_session.get(chat_id_str)
    if not session:
        logger.warning(f"Сессия {chat_id_str} не найдена при обработке job для poll {ended_poll_id}.")
        # Попытка удалить из current_poll, если опрос там остался
        state.current_poll.pop(ended_poll_id, None)
        return

    # Удаляем информацию о завершившемся опросе из state.current_poll
    poll_info_that_ended = state.current_poll.pop(ended_poll_id, None)
    if poll_info_that_ended:
        logger.debug(f"Poll {ended_poll_id} удален из state.current_poll для чата {chat_id_str} (тайм-аут).")
    else:
        logger.warning(f"Poll {ended_poll_id} не найден в state.current_poll при обработке job (возможно, уже обработан).")

    # Проверка, что job соответствует текущему активному опросу сессии, на случай гонки состояний
    # или если /stopquiz был вызван и current_poll_id в сессии уже None или другой.
    if session.get("current_poll_id") != ended_poll_id and session.get("current_poll_id") is not None:
        logger.info(f"Job для poll {ended_poll_id} сработал, но активный poll в сессии {chat_id_str} уже {session.get('current_poll_id')}. Job проигнорирован.")
        return

    if poll_info_that_ended and poll_info_that_ended.get("next_q_triggered_by_answer"):
        logger.info(f"Следующий вопрос для сессии {chat_id_str} уже был инициирован ответом на poll {ended_poll_id}. Job завершен.")
        return

    if ended_poll_q_idx >= session["actual_num_questions"] - 1:
        if session["current_index"] >= session["actual_num_questions"]:
             logger.info(f"Время для последнего вопроса (индекс {ended_poll_q_idx}) сессии {chat_id_str} истекло. Показ результатов.")
             await show_quiz_session_results(context, chat_id_str)
        else:
            logger.warning(f"Job для последнего вопроса {ended_poll_q_idx} сессии {chat_id_str} сработал, "
                           f"но current_index={session['current_index']}. Завершаем сессию и показываем результаты.")
            await show_quiz_session_results(context, chat_id_str)
        return

    if session["current_index"] == ended_poll_q_idx + 1:
        logger.info(f"Тайм-аут для вопроса {ended_poll_q_idx + 1} в сессии {chat_id_str} (poll {ended_poll_id}). Отправляем следующий.")
        await send_next_question_in_session(context, chat_id_str)
    else:
        logger.debug(f"Job для poll {ended_poll_id} в сессии {chat_id_str} завершен. "
                     f"Следующий вопрос (индекс {session['current_index']}) уже был инициирован ранее.")

# show_quiz_session_results: Показывает результаты завершенной сессии /quiz10.
# Вызывается из send_next_question_in_session (когда вопросы кончились),
# handle_current_poll_end (когда истек таймер последнего вопроса),
# и command_handlers.py (/stopquiz).
async def show_quiz_session_results(context: ContextTypes.DEFAULT_TYPE, chat_id_str: str, error_occurred: bool = False):
    session = state.current_quiz_session.get(chat_id_str)
    if not session:
        logger.warning(f"show_quiz_session_results: Сессия для чата {chat_id_str} не найдена для показа результатов.")
        state.current_quiz_session.pop(chat_id_str, None)
        return

    if job := session.get("next_question_job"):
        try:
            job.schedule_removal()
        except Exception:
            pass

    num_q_in_session = session.get("actual_num_questions", NUMBER_OF_QUESTIONS_IN_SESSION)
    results_header = "🏁 Викторина завершена! 🏁\n\n" if not error_occurred else "Викторина прервана.\n\nПромежуточные результаты:\n"
    results_body = ""

    if not session.get("session_scores"):
        results_body = "В этой сессии никто не участвовал или не набрал очков."
    else:
        sorted_session_participants = sorted(
            session["session_scores"].items(),
            key=lambda item: (-item[1].get("score", 0), item[1].get("name", "").lower())
        )

        medals = ["🥇", "🥈", "🥉"]
        for rank, (user_id, data) in enumerate(sorted_session_participants):
            user_name = data.get("name", f"User {user_id}")
            session_score = data.get("score", 0)
            global_score_data = state.user_scores.get(chat_id_str, {}).get(user_id, {})
            global_score = global_score_data.get("score", 0)

            rank_display = medals[rank] if rank < len(medals) else f"{rank + 1}."
            # Используем pluralize_points для сессионных и глобальных очков
            results_body += (f"{rank_display} {user_name}: {pluralize_points(session_score)} из {num_q_in_session} "
                             f"(общий счёт: {pluralize_points(global_score)})\n")

        if len(sorted_session_participants) > 3:
             results_body += "\nОтличная игра, остальные участники!"

    try:
        await context.bot.send_message(chat_id=chat_id_str, text=results_header + results_body)
    except Exception as e:
        logger.error(f"Ошибка при отправке результатов сессии в чат {chat_id_str}: {e}", exc_info=True)

    current_poll_id_of_session = session.get("current_poll_id")
    if current_poll_id_of_session and current_poll_id_of_session in state.current_poll:
        if state.current_poll[current_poll_id_of_session].get("associated_quiz_session_chat_id") == chat_id_str:
            del state.current_poll[current_poll_id_of_session]

    state.current_quiz_session.pop(chat_id_str, None)
    logger.info(f"Сессия для чата {chat_id_str} очищена.")

