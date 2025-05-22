import logging
import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
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
current_quiz = {}  # Хранение текущего вопроса для проверки ответов

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

    await update.message.reply_text("Привет! Я буду присылать тебе утреннюю викторину!")
    logging.info(f"Бот добавлен в чат {chat_id}")

    # Добавляем чат в список активных
    active_chats = context.bot_data.get("active_chats", set())
    active_chats.add(chat_id)
    context.bot_data["active_chats"] = active_chats

# Отправка случайного вопроса
async def send_quiz(context: ContextTypes.DEFAULT_TYPE):
    active_chats = context.bot_data.get("active_chats", set())
    if not active_chats:
        logging.warning("Нет активных чатов для рассылки")
        return

    categories = list(quiz_data.keys())
    category = random.choice(categories)
    question_data = random.choice(quiz_data[category])
    options = question_data["options"]
    keyboard = [[InlineKeyboardButton(option, callback_data=f"{option}|{category}") for option in options]]
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
    user_id = str(query.from_user.id)
    user_name = query.from_user.full_name
    answer, category = query.data.split("|") if "|" in query.data else (query.data, "Общее")

    correct_answer = current_quiz.get(chat_id, {}).get("correct")

    # Инициализация
    if chat_id not in user_scores:
        user_scores[chat_id] = {}
    if user_id not in user_scores[chat_id]:
        user_scores[chat_id][user_id] = {"name": user_name, "score": 0}

    if answer == correct_answer:
        user_scores[chat_id][user_id]["score"] += 1
        await query.edit_message_text(text="Правильно! 👏")
    else:
        await query.edit_message_text(text=f"Неправильно. Правильный ответ: {correct_answer}.")

    save_user_data(user_scores)

# Команда /rating — таблица лидеров
async def rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    scores = user_scores.get(chat_id, {})

    if not scores:
        await update.message.reply_text("Никто ещё не отвечал.")
        return

    sorted_scores = sorted(scores.items(), key=lambda x: x[1]['score'], reverse=True)
    rating_text = "🏆 Таблица лидеров:\n\n"
    for idx, (uid, data) in enumerate(sorted_scores, 1):
        rating_text += f"{idx}. {data['name']} — {data['score']} очков\n"

    await update.message.reply_text(rating_text)

# Команда /quiz — вручную запускает викторину
async def manual_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)

    if chat_id not in context.bot_data.get("active_chats", set()):
        await update.message.reply_text("Сначала нужно запустить бота через /start")
        return

    await update.message.reply_text("🧠 Запускаю викторину вручную...")
    await send_quiz(context)

# Основная функция
if __name__ == '__main__':
    print("🔧 Запуск бота...")

    if not TOKEN:
        raise ValueError("❌ Токен не найден. Убедитесь, что он указан в файле .env")

    print(f"✅ Токен: {TOKEN[:5]}...{TOKEN[-5:]}")

    application = ApplicationBuilder().token(TOKEN).build()

    # Регистрация команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("rating", rating))
    application.add_handler(CommandHandler("quiz", manual_quiz))  # Новая команда
    application.add_handler(CallbackQueryHandler(button_click))

    # Планировщик
    scheduler = BackgroundScheduler()
    scheduler.add_job(send_quiz, 'cron', hour=8, minute=0, args=[application])  # Каждое утро в 8:00
    scheduler.start()

    print("✅ Бот запущен. Ожидание сообщений...")

    # Запуск бота
    application.run_polling()