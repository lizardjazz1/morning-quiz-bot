# handlers/quiz.py

from telegram.ext import CommandHandler
from telegram import Update
from telegram.ext import ContextTypes

import random
from storage.state_manager import state

logger = logging.getLogger(__name__)

# --- Функции ---
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
    questions = get_quiz_questions(10)
    if not questions:
        await update.message.reply_text("Не могу начать квиз — нет вопросов 😕")
        return

    state.current_quiz_session[chat_id] = {
        "questions": questions,
        "correct_answers": {},
        "current_index": 0,
        "active": True
    }

    await update.message.reply_text("📚 Серия из 10 вопросов началась! 🧠")
    await send_next_quiz_question(chat_id, context)

# --- Вспомогательные функции ---
def get_quiz_questions(count=10):
    all_questions = []
    for category in quiz_data.values():
        all_questions.extend(category)
    return random.sample(all_questions, min(count, len(all_questions)))

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

# --- Обработчики ---
manual_quiz_handler = CommandHandler("quiz", manual_quiz)
start_quiz10_handler = CommandHandler("quiz10", start_quiz10)