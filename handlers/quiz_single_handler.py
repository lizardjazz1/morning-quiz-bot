# handlers/quiz_single_handler.py
import random
from datetime import timedelta
from telegram import Update, Poll
from telegram.ext import ContextTypes

from config import logger, DEFAULT_POLL_OPEN_PERIOD, JOB_GRACE_PERIOD
import state
from quiz_logic import (get_random_questions, prepare_poll_options,
                        handle_single_quiz_poll_end) # send_solution_if_available будет вызван из handle_single_quiz_poll_end

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        logger.warning("quiz_command: message or effective_chat is None.")
        return

    chat_id = update.effective_chat.id
    chat_id_str = str(chat_id)
    reply_text_to_send = "" # Для логгирования перед отправкой

    if state.current_quiz_session.get(chat_id_str):
        reply_text_to_send = "В этом чате уже идет игра /quiz10. Дождитесь ее окончания или используйте /stopquiz."
        logger.debug(f"Attempting to send message to {chat_id_str} (quiz_command blocked by /quiz10). Text: '{reply_text_to_send}'")
        await update.message.reply_text(reply_text_to_send)
        return
    if state.pending_scheduled_quizzes.get(chat_id_str):
        reply_text_to_send = f"В этом чате уже запланирована игра /quiz10notify. Дождитесь ее начала или используйте /stopquiz."
        logger.debug(f"Attempting to send message to {chat_id_str} (quiz_command blocked by /quiz10notify). Text: '{reply_text_to_send}'")
        await update.message.reply_text(reply_text_to_send)
        return

    category_arg = " ".join(context.args) if context.args else None
    question_details_list = []
    message_prefix = ""

    if not state.quiz_data:
        reply_text_to_send = "Вопросы еще не загружены. Попробуйте /start позже."
        logger.debug(f"Attempting to send message to {chat_id_str} (quiz_command, no questions loaded). Text: '{reply_text_to_send}'")
        await update.message.reply_text(reply_text_to_send)
        return

    if not category_arg:
        available_categories = [cat_name for cat_name, q_list in state.quiz_data.items() if isinstance(q_list, list) and q_list]
        if not available_categories:
            reply_text_to_send = "Нет доступных категорий с вопросами."
            logger.debug(f"Attempting to send message to {chat_id_str} (quiz_command, no categories with questions). Text: '{reply_text_to_send}'")
            await update.message.reply_text(reply_text_to_send)
            return
        chosen_category = random.choice(available_categories)
        question_details_list = get_random_questions(chosen_category, 1)
        message_prefix = f"Случайный вопрос из категории: {chosen_category}\n"
    else:
        question_details_list = get_random_questions(category_arg, 1)

    if not question_details_list:
        reply_text_to_send = f"Не найдено вопросов в категории '{category_arg if category_arg else 'случайной'}'. Проверьте список категорий: /categories"
        logger.debug(f"Attempting to send message to {chat_id_str} (quiz_command, no questions in category). Text: '{reply_text_to_send}'")
        await update.message.reply_text(reply_text_to_send)
        return

    single_question_details = question_details_list[0]
    poll_question_header = f"{message_prefix}{single_question_details['question']}"
    MAX_POLL_QUESTION_LENGTH = 255
    if len(poll_question_header) > MAX_POLL_QUESTION_LENGTH:
        truncate_at = MAX_POLL_QUESTION_LENGTH - 3
        poll_question_header = poll_question_header[:truncate_at] + "..."
        logger.warning(f"Текст вопроса для /quiz в чате {chat_id_str} был усечен.")

    _, poll_options, poll_correct_option_id, _ = prepare_poll_options(single_question_details)

    logger.debug(f"Attempting to send /quiz poll to {chat_id_str}. Question header: '{poll_question_header[:100]}...'")
    try:
        sent_poll_msg = await context.bot.send_poll(
            chat_id=chat_id,
            question=poll_question_header,
            options=poll_options,
            type=Poll.QUIZ,
            correct_option_id=poll_correct_option_id,
            open_period=DEFAULT_POLL_OPEN_PERIOD,
            is_anonymous=False
        )
        poll_state_entry = {
            "chat_id": chat_id_str,
            "message_id": sent_poll_msg.message_id,
            "correct_index": poll_correct_option_id,
            "quiz_session": False, # Не /quiz10 сессия
            "daily_quiz": False,   # Не ежедневный квиз
            "question_details": single_question_details,
            "associated_quiz_session_chat_id": None,
            "next_q_triggered_by_answer": False,
            "solution_job": None # Будет установлен ниже, если есть решение
        }
        state.current_poll[sent_poll_msg.poll.id] = poll_state_entry

        if single_question_details.get("solution") and context.job_queue:
            job_delay_seconds = DEFAULT_POLL_OPEN_PERIOD + JOB_GRACE_PERIOD
            job_name = f"single_quiz_solution_chat_{chat_id_str}_poll_{sent_poll_msg.poll.id}"
            
            # Удаляем старые джобы с таким же именем, если они есть
            existing_jobs = context.job_queue.get_jobs_by_name(job_name)
            for old_job in existing_jobs:
                old_job.schedule_removal()
                logger.debug(f"Removed old job '{old_job.name}' for single quiz solution.")

            solution_job = context.job_queue.run_once(
                handle_single_quiz_poll_end, # Эта функция вызовет send_solution_if_available
                timedelta(seconds=job_delay_seconds),
                data={"chat_id_str": chat_id_str, "poll_id": sent_poll_msg.poll.id},
                name=job_name
            )
            # Сохраняем ссылку на job в poll_state_entry
            state.current_poll[sent_poll_msg.poll.id]["solution_job"] = solution_job
            logger.info(f"Запланирован job '{job_name}' для обработки таймаута poll {sent_poll_msg.poll.id} (одиночный квиз /quiz).")
    except Exception as e:
        logger.error(f"Ошибка при создании опроса для /quiz в чате {chat_id_str}: {e}", exc_info=True)
        error_reply_text = "Произошла ошибка при попытке создать вопрос."
        logger.debug(f"Attempting to send error message for /quiz to {chat_id_str}. Text: '{error_reply_text}'")
        await update.message.reply_text(error_reply_text)
