# handlers/quiz_handler.py

import random
from telegram.ext import ContextTypes
from telegram import Poll
from utils.questions import load_questions
from config import USERS_FILE

quiz_data = load_questions()
current_quiz_session = {}  # {chat_id: {...}}
current_poll = {}  # {poll_id: {...}}

async def send_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id=None):
    from handlers.quiz_handler import manual_quiz, send_next_quiz_question
    pass  # Импорт ниже


async def manual_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)

    if chat_id not in context.bot_data.get("active_chats", set()):
        await update.message.reply_text("Сначала нужно запустить бота через /start")
        return

    await update.message.reply_text("🧠 Запускаю викторину вручную...")
    await send_quiz(context, chat_id=chat_id)


async def start_quiz10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)

    if chat_id not in context.bot_data.get("active_chats", set()):
        await update.message.reply_text("Сначала нужно запустить бота через /start")
        return

    questions = load_questions().values()
    all_questions = [q for cat in questions for q in cat]
    session_questions = random.sample(all_questions, min(10, len(all_questions)))

    if not session_questions:
        await update.message.reply_text("Не могу начать квиз — нет вопросов 😕")
        return

    current_quiz_session[chat_id] = {
        "questions": session_questions,
        "correct_answers": {},
        "current_index": 0,
        "total_questions": 10
    }

    await update.message.reply_text("📚 Серия из 10 вопросов началась! 🧠")
    await send_next_quiz_question(chat_id, context)


async def send_next_quiz_question(chat_id, context):
    session = current_quiz_session.get(chat_id)
    if not session or session["current_index"] >= len(session["questions"]):
        await show_final_results(chat_id, context)
        return

    question_data = session["questions"][session["current_index"]]
    options = question_data["options"]
    correct_answer = question_data["correct"]

    message = await context.bot.send_poll(
        chat_id=chat_id,
        question=f"📌 Вопрос {session['current_index'] + 1}:\n{question_data['question']}",
        options=options,
        type=Poll.QUIZ,
        correct_option_id=options.index(correct_answer),
        is_anonymous=False
    )

    poll_id = message.poll.id
    correct_index = options.index(correct_answer)

    current_poll[poll_id] = {
        "chat_id": chat_id,
        "correct_index": correct_index,
        "message_id": message.message_id,
        "quiz_session": True
    }

    session["current_index"] += 1


async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = answer.poll_id
    user_id = str(answer.user.id)
    option = answer.option_ids[0]
    user_name = answer.user.full_name

    poll_info = current_poll.get(poll_id)
    if not poll_info:
        return

    chat_id = poll_info["chat_id"]
    correct_index = poll_info["correct_index"]
    is_quiz_session = poll_info.get("quiz_session", False)

    del current_poll[poll_id]

    # Обновление общего рейтинга
    from utils.users import user_scores, save_user_data

    if chat_id not in user_scores:
        user_scores[chat_id] = {}

    if option == correct_index:
        if user_id not in user_scores[chat_id]:
            user_scores[chat_id][user_id] = {"name": user_name, "score": 1}
        else:
            user_scores[chat_id][user_id]["score"] += 1
        save_user_data(user_scores)

    # Если это часть серии квизов
    if is_quiz_session and chat_id in current_quiz_session:
        session = current_quiz_session[chat_id]
        if user_id not in session["correct_answers"]:
            session["correct_answers"][user_id] = {"name": user_name, "count": 0}

        if option == correct_index:
            session["correct_answers"][user_id]["count"] += 1

        await send_next_quiz_question(chat_id, context)


async def show_final_results(chat_id, context):
    session = current_quiz_session.pop(chat_id, None)
    if not session:
        return

    results = sorted(session["correct_answers"].items(), key=lambda x: x[1]['count'], reverse=True)

    result_text = "🏁 Вот как вы прошли квиз из 10 вопросов:\n\n"
    for idx, (uid, data) in enumerate(results, 1):
        total = data["count"]
        emoji = "✨" if total == 10 else "👏" if total >= 7 else "👍" if total >= 5 else "🙂"
        result_text += f"{idx}. {data['name']} — {total}/10 {emoji}\n"

    result_text += "\n🔥 Молодцы! Теперь вы знаете ещё больше!"
    await context.bot.send_message(chat_id=chat_id, text=result_text)