import logging
import os
import json
from telegram import Update, Poll
from telegram.ext import ApplicationBuilder, CommandHandler, PollAnswerHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
import random
import threading

# Загрузка токена
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# Логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Загрузка вопросов
def load_questions():
    try:
        with open('questions.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Ошибка при загрузке вопросов: {e}")
        return {}

# Загрузка пользовательских данных
def load_user_data():
    if not os.path.exists('users.json'):
        save_user_data({})
    try:
        with open('users.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        logging.error(f"Ошибка при загрузке рейтинга: {e}")
        save_user_data({})
        return {}

# Сохранение пользовательских данных
def save_user_data(data):
    with open('users.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Периодический вывод для Replit
def keep_alive():
    print("⏰ Бот всё ещё работает...")
    threading.Timer(7200, keep_alive).start()

keep_alive()

# Загружаем данные
quiz_data = load_questions()
user_scores = load_user_data()

# Хранение активных опросов
current_poll = {}  # {poll_id: {"chat_id": ..., "correct_index": ..., "quiz_session": True/False}

# Хранение сессии квиза из 10 вопросов
current_quiz_session = {}  # {chat_id: {"questions": [...], "correct_answers": {}, "current_index": 0, "completed_users": set()}}

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    # Регистрация пользователя
    if chat_id not in user_scores:
        user_scores[chat_id] = {}
    if str(user_id) not in user_scores.get(chat_id, {}):
        user_scores[chat_id][str(user_id)] = {"name": user_name, "score": 0}
        save_user_data(user_scores)
    await update.message.reply_text("Привет! Я буду присылать вам утреннюю викторину в формате опроса!")
    logging.info(f"Бот добавлен в чат {chat_id}")
    # Добавляем чат в список активных
    active_chats = context.bot_data.get("active_chats", set())
    active_chats.add(chat_id)
    context.bot_data["active_chats"] = active_chats

# Отправка случайного вопроса (опционально по одному чату или всем)
async def send_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id=None):
    active_chats = context.bot_data.get("active_chats", set())
    if not active_chats:
        logging.warning("Нет активных чатов для рассылки")
        return
    categories = list(quiz_data.keys())
    category = random.choice(categories)
    question_data = random.choice(quiz_data[category])
    options = question_data["options"]
    correct_answer = question_data["correct"]
    for cid in active_chats:
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
            current_poll[poll_id] = {
                "chat_id": cid,
                "correct_index": correct_index,
                "message_id": message.message_id,
                "quiz_session": False
            }
        except Exception as e:
            logging.error(f"Ошибка при отправке опроса в чат {cid}: {e}")

# Получить случайные вопросы для квиза
def get_quiz_questions(count=10):
    all_questions = []
    for category in quiz_data.values():
        all_questions.extend(category)
    return random.sample(all_questions, min(count, len(all_questions)))

# Команда /quiz — вручную запускает викторину ТОЛЬКО в текущем чате
async def manual_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id not in context.bot_data.get("active_chats", set()):
        await update.message.reply_text("Сначала нужно запустить бота через /start")
        return
    await update.message.reply_text("🧠 Запускаю викторину вручную...")
    await send_quiz(context, chat_id=chat_id)

# Команда /quiz10 — серия из 10 вопросов подряд
async def start_quiz10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if chat_id not in context.bot_data.get("active_chats", set()):
        await update.message.reply_text("Сначала нужно запустить бота через /start")
        return
    questions = get_quiz_questions(10)
    if not questions:
        await update.message.reply_text("Не могу начать квиз — нет вопросов 😕")
        return
    # Подготавливаем сессию
    current_quiz_session[chat_id] = {
        "questions": questions,
        "correct_answers": {},
        "current_index": 0,
        "completed_users": set()
    }
    await update.message.reply_text("📚 Серия из 10 вопросов началась! 🧠")
    await send_next_quiz_question(chat_id, context)

# Отправка следующего вопроса серии
async def send_next_quiz_question(chat_id, context):
    session = current_quiz_session.get(chat_id)
    if not session or session["current_index"] >= len(session["questions"]):
        await show_final_results_individual(chat_id, context)
        return
    question_data = session["questions"][session["current_index"]]
    options = question_data["options"]
    correct_answer = question_data["correct"]
    try:
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
            "quiz_session": True  # Это часть серии
        }
        session["current_index"] += 1  # Увеличиваем индекс
    except Exception as e:
        logging.error(f"Ошибка при отправке опроса в чат {chat_id}: {e}")
        await context.bot.send_message(chat_id=chat_id, text="❌ Не могу продолжить — ошибка отправки")

# Обработка ответов на опрос
async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = answer.poll_id
    user_id = str(answer.user.id)
    option = answer.option_ids[0]  # индекс выбранного варианта
    user_name = answer.user.full_name
    poll_info = current_poll.get(poll_id)
    if not poll_info:
        return
    chat_id = poll_info["chat_id"]
    correct_index = poll_info["correct_index"]
    is_quiz_session = poll_info.get("quiz_session", False)
    # Убираем опрос из списка активных
    del current_poll[poll_id]
    # Инициализация user_scores, если нужно
    if chat_id not in user_scores:
        user_scores[chat_id] = {}
    # Если пользователь дал правильный ответ
    if option == correct_index:
        if user_id not in user_scores[chat_id]:
            user_scores[chat_id][user_id] = {"name": user_name, "score": 1}
        else:
            user_scores[chat_id][user_id]["score"] += 1
        await context.bot.send_message(chat_id=chat_id, text=f"{user_name}, правильно! 👏")
        save_user_data(user_scores)
    # Если это часть серии квизов
    if is_quiz_session and chat_id in current_quiz_session:
        session = current_quiz_session[chat_id]
        if user_id not in session["correct_answers"]:
            session["correct_answers"][user_id] = {"name": user_name, "count": 0}
        if option == correct_index:
            session["correct_answers"][user_id]["count"] += 1
        # Отправляем следующий вопрос или обновляем результаты
        await send_next_quiz_question(chat_id, context)

# Финальные результаты для каждого пользователя отдельно
async def show_final_results_individual(chat_id, context):
    session = current_quiz_session.get(chat_id)
    if not session:
        return

    user = update.effective_user
    user_id = str(user.id)
    user_name = user.full_name

    # Добавляем пользователя в список завершивших (если ещё не добавлен)
    completed_users = session.get("completed_users", set())
    if user_id in completed_users:
        return
    completed_users.add(user_id)
    session["completed_users"] = completed_users

    # Собираем результаты только завершивших пользователей
    results = []
    for uid in completed_users:
        if uid in session["correct_answers"]:
            results.append((uid, session["correct_answers"][uid]))

    results.sort(key=lambda x: x[1]['count'], reverse=True)

    result_text = f"🏁 {user_name}, вот твои результаты:\n"
    for idx, (uid, data) in enumerate(results, 1):
        total = data["count"]
        emoji = "✨" if total == 10 else "👏" if total >= 7 else "👍" if total >= 5 else "🙂"
        result_text += f"{idx}. {data['name']} — {total}/10 {emoji}\n"
    result_text += "\n🔥 Молодцы! Теперь вы знаете ещё больше!"

    await context.bot.send_message(chat_id=chat_id, text=result_text)

# Команда /rating — показывает таблицу лидеров
async def rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    scores = user_scores.get(chat_id, {})
    if not scores:
        await update.message.reply_text("Никто ещё не отвечал.")
        return
    sorted_scores = sorted(scores.items(), key=lambda x: x[1]['score'], reverse=True)
    rating_text = "🏆 Таблица лидеров:\n"
    for idx, (uid, data) in enumerate(sorted_scores, 1):
        rating_text += f"{idx}. {data['name']} — {data['score']} очков\n"
    await update.message.reply_text(rating_text)

# Основная функция
if __name__ == '__main__':
    print("🔧 Запуск бота...")
    if not TOKEN:
        raise ValueError("❌ Токен не найден. Убедитесь, что он указан в файле .env")
    print(f"✅ Токен: {TOKEN[:5]}...{TOKEN[-5:]}")
    application = ApplicationBuilder().token(TOKEN).build()
    # Регистрация команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("quiz", manual_quiz))
    application.add_handler(CommandHandler("quiz10", start_quiz10))
    application.add_handler(CommandHandler("rating", rating))
    application.add_handler(PollAnswerHandler(handle_poll_answer))
    # Планировщик
    scheduler = BackgroundScheduler()
    scheduler.add_job(send_quiz, 'cron', hour=8, minute=0, args=[application])  # Каждое утро в 8:00
    scheduler.start()
    print("✅ Бот запущен. Ожидание сообщений...")
    # Запуск бота
    application.run_polling()