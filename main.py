# quiz_bot/main.py
import logging
from telegram.ext import ApplicationBuilder, CommandHandler, PollAnswerHandler

from config import TOKEN, setup_logging
from data_manager import load_questions, load_user_data
from handlers import start, manual_quiz, start_quiz10, rating, handle_poll_answer
from scheduler_setup import setup_scheduler
from utils import keep_alive

def main():
    # 1. Настройка логирования
    setup_logging()
    logging.info("🔧 Запуск бота...")

    if not TOKEN: # Проверка уже есть в config.py, но для надежности
        logging.critical("❌ Токен не найден в config.py. Завершение работы.")
        return

    print(f"✅ Токен загружен: {TOKEN[:5]}...{TOKEN[-5:]}")

    # 2. Создание экземпляра Application
    application = ApplicationBuilder().token(TOKEN).build()

    # 3. Загрузка данных и инициализация bot_data
    # Эти данные будут доступны во всех хендлерах через context.bot_data
    application.bot_data['quiz_data'] = load_questions()
    application.bot_data['user_scores'] = load_user_data()
    application.bot_data['current_poll'] = {}  # {poll_id: {"chat_id": ..., "correct_index": ..., "message_id": ..., "quiz_session": True/False}}
    application.bot_data['current_quiz_session'] = {} # {chat_id: {"questions": [...], "correct_answers": {}, "current_index": 0, "active": True}}
    application.bot_data['active_chats'] = set() # {chat_id_str, ...}
    # При старте можно загружать active_chats из файла, если нужна персистентность
    # Например, при первом /start чат добавляется и сохраняется в users.json или отдельный файл.

    logging.info(f"Загружено вопросов: {sum(len(v) for v in application.bot_data['quiz_data'].values())}")
    logging.info(f"Загружено пользовательских данных для {len(application.bot_data['user_scores'])} чатов.")


    # 4. Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("quiz", manual_quiz))
    application.add_handler(CommandHandler("quiz10", start_quiz10))
    application.add_handler(CommandHandler("rating", rating))
    application.add_handler(PollAnswerHandler(handle_poll_answer))
    logging.info("Обработчики команд зарегистрированы.")

    # 5. Настройка и запуск планировщика
    # Передаем application, чтобы планировщик имел доступ к bot_data и bot
    scheduler = setup_scheduler(application)

    # 6. Функция для поддержания активности (если нужно, например, для Replit)
    keep_alive() # Запускаем keep_alive один раз, он сам себя будет перезапускать

    # 7. Запуск бота
    logging.info("✅ Бот запущен. Ожидание сообщений...")
    application.run_polling()

    # Остановка планировщика при завершении работы бота (если бот останавливается корректно)
    logging.info("Остановка планировщика...")
    scheduler.shutdown()
    logging.info("Бот остановлен.")


if __name__ == '__main__':
    main()
