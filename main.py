import logging
import os
import json
from telegram import Update, Poll
from telegram.ext import ApplicationBuilder, CommandHandler, PollAnswerHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
import random
import time
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
    except Exception as e:
        logging.error(f"Ошибка при загрузке рейтинга: {e}")
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
current_poll = {}  # {poll_id: {"chat_id": ..., "correct_index": ..., "message_id": ...}}

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name

    # Регистрация пользователя
    if chat_id not in user_scores:
        user_scores[chat_id] = {}
    if str(user_id) not in user_scores[chat_id]:
        user_scores[chat_id][str(user_id)] = {"name": user_name, "score": 0}
        save_user_data(user_scores)

    await update.message.reply_text("Привет! Я буду присылать утреннюю викторину в формате опроса!")
    logging.info(f"Бот добавлен в чат {chat_id}")

    # Добавляем чат в список активных
    active_chats = context.bot_data.get("active_chats", set())
    active_chats.add(chat_id)
    context.bot_data["active_chats"] = active_chats

# Отправка случайного вопроса в виде опроса
async def send_quiz(context: ContextTypes.DEFAULT_TYPE):
    active_chats = context.bot_data.get("active_chats", set())
    if not active_chats:
        logging.warning("Нет активных чатов для рассылки")
        return

    categories = list(quiz_data.keys())
    category = random.choice(categories)
    question_data = random.choice(quiz_data[category])
    options = question_data["options"]
    correct_answer = question_data["correct"]

    for chat_id in active_chats:
        try:
            message = await context.bot.send_poll(
                chat_id=chat_id,
                question=question_data["question"],
                options=options,
                type=Poll.QUIZ,
                correct_option_id=options.index(correct_answer),
                is_anonymous=False  # Включаем неанонимность
            )

            poll_id = message.poll.id
            correct_index = options.index(correct_answer)

            current_poll[poll_id] = {
                "chat_id": chat_id,
                "correct_index": correct_index,
                "user_answers": {},  # {user_id: {"name": ..., "option": ...}}
                "message_id": message.message_id
            }

        except Exception as e:
            logging.error(f"Ошибка при отправке опроса в чат {chat_id}: {e}")

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
    poll_info["user_answers"][user_id] = {"name": user_name, "option": option}

    # Инициализация user_scores, если нужно
    if chat_id not in user_scores:
        user_scores[chat_id] = {}

    # Если пользователь дал правильный ответ
    if option == correct_index:
        if user_id not in user_scores[chat_id]:
            user_scores[chat_id][user_id] = {"name": user_name, "score": 1}
        else:
            user_scores[chat_id][user_id]["score"] += 1
        await context.bot.send_message(chat_id=chat_id, text=f"{user_name} правильно ответил(а)! 👏")
        save_user_data(user_scores)

# Основная функция
if __name__ == '__main__':
    print("🔧 Запуск бота...")

    if not TOKEN:
        raise ValueError("❌ Токен не найден. Убедитесь, что он указан в файле .env")

    print(f"✅ Токен: {TOKEN[:5]}...{TOKEN[-5:]}")

    application = ApplicationBuilder().token(TOKEN).build()

    # Регистрация команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(PollAnswerHandler(handle_poll_answer))

    # Планировщик
    scheduler = BackgroundScheduler()
    scheduler.add_job(send_quiz, 'cron', hour=8, minute=0, args=[application])  # Каждое утро в 8:00
    scheduler.start()

    print("✅ Бот запущен. Ожидание сообщений...")

    # Запуск бота
    application.run_polling()