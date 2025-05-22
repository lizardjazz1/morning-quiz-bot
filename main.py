# main.py

import logging
from apscheduler.schedulers.background import BackgroundScheduler

from telegram.ext import ApplicationBuilder

# Импорты из наших модулей
from config.settings import BOT_TOKEN
from handlers.start import start
from handlers.quiz import manual_quiz, start_quiz10
from handlers.rating import rating
from handlers.poll_answer import poll_answer_handler
from utils.scheduler_utils import keep_alive
from services.quiz_service import send_quiz


# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Периодический вывод для Replit
keep_alive()

# Инициализация приложения
application = ApplicationBuilder().token(BOT_TOKEN).build()

# Регистрация обработчиков
application.add_handler(start)
application.add_handler(manual_quiz)
application.add_handler(start_quiz10)
application.add_handler(rating)
application.add_handler(poll_answer_handler)

# Планировщик
scheduler = BackgroundScheduler()
scheduler.add_job(send_quiz, 'cron', hour=8, minute=0, args=[application])  # Каждое утро в 8:00
scheduler.start()

# Точка запуска
if __name__ == '__main__':
    print("✅ Бот запущен. Ожидание сообщений...")
    application.run_polling()