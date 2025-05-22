import logging
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
import random

# Загружаем переменные из .env
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Пример вопросов
quiz_questions = [
    {
        "question": "Сколько будет 2+2?",
        "options": ["3", "4", "5", "6"],
        "correct": "4"
    },
    {
        "question": "Какой цвет получается при смешивании красного и синего?",
        "options": ["Зелёный", "Фиолетовый", "Оранжевый", "Чёрный"],
        "correct": "Фиолетовый"
    },
    {
        "question": "Столица Франции?",
        "options": ["Лондон", "Москва", "Париж", "Рим"],
        "correct": "Париж"
    }
]

current_quiz = {}

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    
    # Получаем список активных чатов или создаём новый
    active_chats = context.bot_data.get("active_chats", set())
    active_chats.add(chat_id)
    context.bot_data["active_chats"] = active_chats

    await update.message.reply_text("Привет! Я буду присылать тебе утреннюю викторину!")
    logging.info(f"Бот добавлен в чат {chat_id}")

# Отправка викторины
async def send_quiz(context: ContextTypes.DEFAULT_TYPE):
    active_chats = context.bot_data.get("active_chats", set())
    
    if not active_chats:
        logging.warning("Нет активных чатов для рассылки")
        return

    question_data = random.choice(quiz_questions)
    options = question_data["options"]
    keyboard = [[InlineKeyboardButton(option, callback_data=option)] for option in options]
    reply_markup = InlineKeyboardMarkup(keyboard)

    for chat_id in active_chats:
        try:
            message = await context.bot.send_message(chat_id=chat_id, text=question_data["question"], reply_markup=reply_markup)
            current_quiz[chat_id] = {"message_id": message.message_id, "correct": question_data["correct"]}
        except Exception as e:
            logging.error(f"Ошибка при отправке сообщения в чат {chat_id}: {e}")

# Обработка ответов
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = str(query.message.chat_id)
    user_answer = query.data
    correct_answer = current_quiz.get(chat_id, {}).get("correct")

    if user_answer == correct_answer:
        await query.edit_message_text(text="Правильно! 👏")
    else:
        await query.edit_message_text(text=f"Неправильно. Правильный ответ: {correct_answer}.")

# Основная функция
if __name__ == '__main__':
    if not TOKEN:
        raise ValueError("Токен не найден. Убедитесь, что он указан в файле .env")

    application = ApplicationBuilder().token(TOKEN).build()

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_click))

    # Настройка планировщика
    scheduler = BackgroundScheduler()
    scheduler.add_job(send_quiz, 'cron', hour=8, minute=0, args=[application])  # Каждое утро в 8:00
    scheduler.start()

    # Запуск бота
    application.run_polling()