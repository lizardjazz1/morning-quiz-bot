# handlers/poll_answer.py

from telegram import Update
from telegram.ext import ContextTypes, PollAnswerHandler

import logging
from storage.state_manager import state
from services.score_service import update_user_score

logger = logging.getLogger(__name__)

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = answer.poll_id
    user_id = str(answer.user.id)
    option = answer.option_ids[0]
    user_name = answer.user.full_name

    poll_info = state.current_poll.get(poll_id)
    if not poll_info:
        return

    chat_id = poll_info["chat_id"]
    correct_index = poll_info["correct_index"]
    is_quiz_session = poll_info.get("quiz_session", False)

    del state.current_poll[poll_id]

    if option == correct_index:
        update_user_score(chat_id, user_id, user_name, context)

    if is_quiz_session and chat_id in state.current_quiz_session:
        session = state.current_quiz_session[chat_id]
        if user_id not in session["correct_answers"]:
            session["correct_answers"][user_id] = {"name": user_name, "count": 0}
        if option == correct_index:
            session["correct_answers"][user_id]["count"] += 1
        await send_next_quiz_question(chat_id, context)

async def send_next_quiz_question(chat_id, context):
    session = state.current_quiz_session.get(chat_id)
    if not session or session["current_index"] >= len(session["questions"]):
        await show_final_results(chat_id, context)
        return

    question_data = session["questions"][session["current_index"]]
    options = question_data["options"]
    correct_answer = question_data["correct"]

    try:
        message = await context.bot.send_poll(
            chat_id=chat_id,
            question=f"📌 Вопрос {session['current_index'] + 1}:\n{question_data['question']}",
            options=options,
            type="quiz",
            correct_option_id=options.index(correct_answer),
            is_anonymous=False
        )
        poll_id = message.poll.id
        correct_index = options.index(correct_answer)

        state.current_poll[poll_id] = {
            "chat_id": chat_id,
            "correct_index": correct_index,
            "message_id": message.message_id,
            "quiz_session": True
        }

        session["current_index"] += 1
    except Exception as e:
        from logging import getLogger
        logger = getLogger(__name__)
        logger.error(f"Ошибка отправки опроса в чат {chat_id}: {e}")

async def show_final_results(chat_id, context):
    session = state.current_quiz_session.pop(chat_id, None)
    if not session:
        return

    correct_answers = session["correct_answers"]
    results = sorted(correct_answers.items(), key=lambda x: x[1]['count'], reverse=True)
    result_text = "🏁 Вот как вы прошли квиз из 10 вопросов:\n"
    for idx, (uid, data) in enumerate(results, 1):
        total = data["count"]
        emoji = "✨" if total == 10 else "👏" if total >= 7 else "👍" if total >= 5 else "🙂"
        result_text += f"{idx}. {data['name']} — {total}/10 {emoji}\n"
    result_text += "\n🔥 Молодцы! Теперь вы знаете ещё больше!"
    await context.bot.send_message(chat_id=chat_id, text=result_text)

poll_answer_handler = PollAnswerHandler(handle_poll_answer)