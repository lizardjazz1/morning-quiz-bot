# bot.py

# ├── bot.py                 # Основная точка входа, запуск бота, регистрация обработчиков
# ├── config.py              # Константы, токен, настройка логгера
# ├── state.py               # Глобальные переменные состояния (quiz_data, user_scores, и т.д.)
# ├── data_manager.py        # Функции для загрузки/сохранения вопросов и данных пользователей
# ├── quiz_logic.py          # Логика викторины (случайные вопросы, подготовка опроса, управление сессиями /quiz10)
# ├── utils.py               # Вспомогательные функции (например, pluralize_points)
# ├── handlers/
# │   ├── __init__.py
# │   ├── common_handlers.py   # Для /start, /categories
# │   ├── quiz_single_handler.py # Для /quiz
# │   ├── quiz_session_handlers.py # Для /quiz10, /quiz10notify, /stopquiz и связанной логики
# │   ├── rating_handlers.py   # Для /rating, /globaltop
# │   └── daily_quiz_handlers.py # Для ежедневной викторины
# ├── poll_answer_handler.py # Обработчик ответов на опросы
# └── .env                   # Для BOT_TOKEN
# └── questions.json         # Наш файл с вопросами
# └── users.json             # Данные пользователей
# └── daily_quiz_subscriptions.json # Данные о подписках на ежедневную викторину

import datetime
import pytz # Для работы с временными зонами

from telegram.ext import (ApplicationBuilder, CommandHandler, PollAnswerHandler,
                          CallbackQueryHandler, ContextTypes, JobQueue)
from telegram import Update # Только для error_handler type hint, если раскомментировать часть

# Импорты из других модулей проекта
from config import (TOKEN, logger,
                    CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT,
                    CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY,
                    DAILY_QUIZ_DEFAULT_HOUR_MSK, DAILY_QUIZ_DEFAULT_MINUTE_MSK)
from data_manager import load_questions, load_user_data, load_daily_quiz_subscriptions

# Импорт обработчиков из нового пакета handlers
from handlers.common_handlers import start_command, categories_command
from handlers.quiz_single_handler import quiz_command
from handlers.quiz_session_handlers import (quiz10_command, handle_quiz10_category_selection,
                                            quiz10notify_command, stop_quiz_command)
from handlers.rating_handlers import rating_command, global_top_command
from handlers.daily_quiz_handlers import (subscribe_daily_quiz_command, unsubscribe_daily_quiz_command,
                                          master_daily_quiz_scheduler_job) # Импорт для ежедневной викторины

# Импорт обработчика ответов на опросы
from poll_answer_handler import handle_poll_answer

# --- Вспомогательная функция для времени по МСК ---
def moscow_time(hour: int, minute: int) -> datetime.time:
    """Создает объект datetime.time для указанного часа и минуты по Московскому времени."""
    moscow_tz = pytz.timezone('Europe/Moscow')
    return datetime.time(hour=hour, minute=minute, tzinfo=moscow_tz)

# --- Обработчик ошибок ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Произошла ошибка при обработке обновления:", exc_info=context.error)
    # Можно добавить отправку сообщения пользователю, если ошибка критична или понятна
    # if isinstance(update, Update) and update.effective_chat:
    #     try:
    #         error_message_text = "Произошла внутренняя ошибка. Пожалуйста, попробуйте позже."
    #         logger.debug(f"Attempting to send error message to {update.effective_chat.id}. Text: '{error_message_text}'")
    #         await context.bot.send_message(chat_id=update.effective_chat.id, text=error_message_text)
    #     except Exception as e:
    #         logger.error(f"Не удалось отправить сообщение об ошибке пользователю: {e}")

# --- Основная функция для запуска бота ---
def main():
    if not TOKEN:
        print("Токен BOT_TOKEN не найден! Пожалуйста, проверьте ваш .env файл и переменную BOT_TOKEN.")
        return

    logger.info("Загрузка вопросов...")
    load_questions()
    logger.info("Загрузка данных пользователей...")
    load_user_data()
    logger.info("Загрузка подписок на ежедневную викторину...")
    load_daily_quiz_subscriptions()


    application = ApplicationBuilder().token(TOKEN).build()
    job_queue: JobQueue | None = application.job_queue
    if not job_queue:
        logger.error("JobQueue не инициализирован. Запланированные задачи не будут работать.")
        # Можно решить падать здесь или продолжать без JobQueue
        # return

    # Регистрация общих команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("categories", categories_command))

    # Регистрация команды для одиночного квиза
    application.add_handler(CommandHandler("quiz", quiz_command))

    # Регистрация команд для сессий квиза
    application.add_handler(CommandHandler("quiz10", quiz10_command))
    application.add_handler(CommandHandler("quiz10notify", quiz10notify_command))
    application.add_handler(CommandHandler("stopquiz", stop_quiz_command))

    # Регистрация команд для рейтинга
    application.add_handler(CommandHandler("rating", rating_command))
    application.add_handler(CommandHandler("globaltop", global_top_command))

    # Регистрация команд для ежедневной викторины
    application.add_handler(CommandHandler("subscribe_daily_quiz", subscribe_daily_quiz_command))
    application.add_handler(CommandHandler("unsubscribe_daily_quiz", unsubscribe_daily_quiz_command))

    # Обработчик для кнопок выбора категории /quiz10
    application.add_handler(CallbackQueryHandler(handle_quiz10_category_selection,
                                                 pattern=f"^{CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT}|^({CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY})$"))

    application.add_handler(PollAnswerHandler(handle_poll_answer))
    application.add_error_handler(error_handler)

    # Планирование ежедневной викторины
    if job_queue:
        target_time_msk = moscow_time(DAILY_QUIZ_DEFAULT_HOUR_MSK, DAILY_QUIZ_DEFAULT_MINUTE_MSK)
        job_queue.run_daily(
            master_daily_quiz_scheduler_job,
            time=target_time_msk,
            name="master_daily_quiz_scheduler"
        )
        logger.info(f"Ежедневный мастер-планировщик викторин запланирован на {DAILY_QUIZ_DEFAULT_HOUR_MSK:02d}:{DAILY_QUIZ_DEFAULT_MINUTE_MSK:02d} МСК.")
    else:
        logger.warning("JobQueue не доступен, ежедневная викторина не будет запланирована.")


    logger.info("Бот успешно настроен и запускается...")
    application.run_polling()
    logger.info("Бот остановлен.")

if __name__ == '__main__':
    main()

