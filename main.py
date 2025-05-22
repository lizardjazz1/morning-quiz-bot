# main.py

import logging
from telegram.ext import ApplicationBuilder, CommandHandler, PollAnswerHandler
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from handlers.start_handler import start
from handlers.quiz_handler import handle_poll_answer, send_quiz
from handlers.rating_handler import rating

# Логирование
logging.basicConfig(level=logging.INFO)

# Подгружаем токен из .env
from config import BOT_TOKEN

# Инициализируем бота
application = ApplicationBuilder().token(BOT_TOKEN).build()

# Регистрируем команды
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("quiz", send_quiz))
application.add_handler(CommandHandler("quiz10", start_quiz10))
application.add_handler(CommandHandler("rating", rating))
application.add_handler(PollAnswerHandler(handle_poll_answer))

# Планировщик ежедневного квиза
scheduler = BackgroundScheduler()
scheduler.add_job(send_quiz, 'cron', hour=8, minute=0, args=[application])
scheduler.start()

# Защита от сна Replit
from utils.keep_alive import keep_alive
keep_alive()

# Запуск бота
print("✅ Бот запущен. Ожидание сообщений...")
application.run_polling()