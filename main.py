# main.py

from telegram import Update
from telegram.ext import ContextTypes, ApplicationBuilder, CommandHandler, PollAnswerHandler
from apscheduler.schedulers.background import BackgroundScheduler
import logging

# Локальные импорты
from config.settings import BOT_TOKEN
from handlers.start import start
from handlers.quiz import manual_quiz_handler, start_quiz10_handler
from handlers.rating import rating_handler
from handlers.poll_answer import poll_answer_handler
from utils.scheduler_utils import keep_alive
from services.quiz_service import send_quiz
from storage.data_loader import load_json
from services.score_service import init_user_scores
from storage.state_manager import state

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Периодический вывод для Replit
keep_alive()

# Инициализация приложения
application = ApplicationBuilder().token(BOT_TOKEN).build()

# Инициализация данных при запуске
async def post_init(app):
    app.bot_data["quiz_data"] = load_json("questions.json")
    app.bot_data["user_scores"] = load_json("users.json")
    app.bot_data["active_chats"] = set(app.bot_data["user_scores"].keys())
    app.bot_data["state"] = state
    logging.info("✅ Данные загружены")

application.post_init = post_init

# Регистрация обработчиков
application.add_handler(start)
application.add_handler(manual_quiz_handler)
application.add_handler(start_quiz10_handler)
application.add_handler(rating_handler)
application.add_handler(poll_answer_handler)

# Планировщик
scheduler = BackgroundScheduler()
scheduler.add_job(send_quiz, 'cron', hour=8, minute=0, args=[application])
scheduler.start()

# Запуск
if __name__ == '__main__':
    print("✅ Бот запущен. Ожидание сообщений...")
    application.run_polling()