# handlers/quiz_single_handler.py
import random
from telegram import Update, Poll
from telegram.ext import ContextTypes
# from telegram.chat import Chat as TelegramChat # Для аннотации типов, если используется

# Импорты из других модулей проекта
from config import logger, DEFAULT_POLL_OPEN_PERIOD
import state # Для доступа к quiz_data, current_quiz_session, current_poll, pending_scheduled_quizzes
from quiz_logic import (get_random_questions, prepare_poll_options) # Основная логика викторины

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        logger.warning("quiz_command: message or effective_chat is None.")
        return

    chat_id = update.effective_chat.id
    chat_id_str = str(chat_id)

    if state.current_quiz_session.get(chat_id_str):
        await update.message.reply_text("В этом чате уже идет игра /quiz10. Дождитесь ее окончания или используйте /stopquiz.") # type: ignore
        return
    if state.pending_scheduled_quizzes.get(chat_id_str):
        await update.message.reply_text(f"В этом чате уже запланирована игра /quiz10notify. Дождитесь ее начала или используйте /stopquiz.") # type: ignore
        return

    category_arg = " ".join(context.args) if context.args else None # type: ignore
    question_details_list = []
    message_prefix = ""

    if not state.quiz_data:
        await update.message.reply_text("Вопросы еще не загружены. Попробуйте /start позже.") # type: ignore
        return

    if not category_arg:
        available_categories = [cat_name for cat_name, q_list in state.quiz_data.items() if isinstance(q_list, list) and q_list]
        if not available_categories:
            await update.message.reply_text("Нет доступных категорий с вопросами.") # type: ignore
            return
        chosen_category = random.choice(available_categories)
        question_details_list = get_random_questions(chosen_category, 1)
        message_prefix = f"Случайный вопрос из категории: {chosen_category}\n"
    else:
        question_details_list = get_random_questions(category_arg, 1)

    if not question_details_list:
        await update.message.reply_text(f"Не найдено вопросов в категории '{category_arg if category_arg else 'случайной'}'.") # type: ignore
        return

    single_question_details = question_details_list[0]

    try:
        # Текст для отображения пользователю (может включать категорию)
        poll_question_header = f"{message_prefix}{single_question_details['question']}"

        MAX_POLL_QUESTION_LENGTH = 255
        if len(poll_question_header) > MAX_POLL_QUESTION_LENGTH:
            truncate_at = MAX_POLL_QUESTION_LENGTH - 3
            poll_question_header = poll_question_header[:truncate_at] + "..."
            logger.warning(f"Текст вопроса для /quiz в чате {chat_id_str} был усечен.")

        # prepare_poll_options ожидает только сам вопрос, без префиксов
        _, poll_options, poll_correct_option_id, _ = prepare_poll_options(single_question_details)

        sent_poll_msg = await context.bot.send_poll(
            chat_id=chat_id,
            question=poll_question_header, # Отображаемый текст
            options=poll_options,
            type=Poll.QUIZ,
            correct_option_id=poll_correct_option_id,
            open_period=DEFAULT_POLL_OPEN_PERIOD,
            is_anonymous=False
        )
        state.current_poll[sent_poll_msg.poll.id] = {
            "chat_id": chat_id_str,
            "message_id": sent_poll_msg.message_id,
            "correct_index": poll_correct_option_id,
            "quiz_session": False,
            "question_details": single_question_details, # Важно для показа правильного ответа
            "associated_quiz_session_chat_id": None,
            "next_q_triggered_by_answer": False
        }
    except Exception as e:
        logger.error(f"Ошибка при создании опроса для /quiz в чате {chat_id_str}: {e}", exc_info=True)
        await update.message.reply_text("Произошла ошибка при попытке создать вопрос.") # type: ignore

