# main.py

import logging
from telegram.ext import ApplicationBuilder, CommandHandler, PollAnswerHandler
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
import os
import json
from telegram import Update
from telegram.ext import ContextTypes

# Логирование
logging.basicConfig(level=logging.INFO)

# Подгружаем токен
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# Загрузка данных
def load_questions():
    try:
        with open('questions.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Ошибка при загрузке вопросов: {e}")
        return {}

def load_user_data():
    if not os.path.exists('users.json'):
        save_user_data({})
    try:
        with open('users.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Ошибка при загрузке рейтинга: {e}")
        return {}

def save_user_data(data):
    with open('users.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Периодический вывод для Replit
def keep_alive():
    print("⏰ Бот всё ещё работает...")
    threading.Timer(7200, keep_alive).start()

keep_alive()

# Глобальные данные
quiz_data = load_questions()
user_scores = load_user_data()
current_poll = {}  # {poll_id: {...}}
current_quiz_session = {}  # {chat_id: {...}}

# Инициализируем бота
from handlers.start_handler import start
from handlers.quiz_handler import manual_quiz, start_quiz10, handle_poll_answer
from handlers.rating_handler import rating

application = ApplicationBuilder().token(TOKEN).build()

# Регистрация команд
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("quiz", manual_quiz))
application.add_handler(CommandHandler("quiz10", start_quiz10))
application.add_handler(CommandHandler("rating", rating))
application.add_handler(PollAnswerHandler(handle_poll_answer))

# Планировщик ежедневного квиза
scheduler = BackgroundScheduler()
scheduler.add_job(manual_quiz, 'cron', hour=8, minute=0, args=[application])
scheduler.start()

# Запуск бота
print("✅ Бот запущен. Ожидание сообщений...")
application.run_polling()