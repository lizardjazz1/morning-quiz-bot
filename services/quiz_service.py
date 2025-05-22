# services/quiz_service.py

import random
from telegram import Poll
from telegram.ext import ContextTypes

from storage.state_manager import state


async def send_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id=None):
    quiz_data = context.bot_data.get("quiz_data", {})
    active_chats = context.bot_data.get("active_chats", set())

    if not active_chats:
        return

    categories = list(quiz_data.keys())
    if not categories:
        return

    category = random.choice(categories)
    questions = quiz_data[category]
    if not questions:
        return

    question_data = random.choice(questions)
    options = question_data["options"]
    correct_answer = question_data["correct"]

    chats_to_send = [chat_id] if chat_id else active_chats

    for cid in chats_to_send:
        try:
            message = await context.bot.send_poll(
                chat_id=cid,
                question=question_data["question"],
                options=options,
                type=Poll.QUIZ,
                correct_option_id=options.index(correct_answer),
                is_anonymous=False
            )
            poll_id = message.poll.id
            correct_index = options.index(correct_answer)
            state.current_poll[poll_id] = {
                "chat_id": cid,
                "correct_index": correct_index,
                "message_id": message.message_id,
                "quiz_session": False
            }
        except Exception as e:
            from logging import getLogger
            logger = getLogger(__name__)
            logger.error(f"Ошибка отправки опроса в чат {cid}: {e}")