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

from telegram.ext import (Application, ApplicationBuilder, CommandHandler, PollAnswerHandler,
                          CallbackQueryHandler, ContextTypes, JobQueue)
from telegram import Update # Только для error_handler type hint, если раскомментировать часть

# Импорты из других модулей проекта
from config import (TOKEN, logger,
                    CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT,
                    CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY) # Убраны DAILY_QUIZ_DEFAULT_HOUR_MSK, DAILY_QUIZ_DEFAULT_MINUTE_MSK, т.к. мастер-джоб удален
import state # для schedule_all_daily_quizzes_on_startup
from data_manager import load_questions, load_user_data, load_daily_quiz_subscriptions

# Импорт обработчиков из нового пакета handlers
from handlers.common_handlers import start_command, categories_command
from handlers.quiz_single_handler import quiz_command
from handlers.quiz_session_handlers import (quiz10_command, handle_quiz10_category_selection,
                                            quiz10notify_command, stop_quiz_command)
from handlers.rating_handlers import rating_command, global_top_command
from handlers.daily_quiz_handlers import (subscribe_daily_quiz_command, unsubscribe_daily_quiz_command,
                                          set_daily_quiz_time_command, set_daily_quiz_categories_command,
                                          show_daily_quiz_settings_command, _schedule_or_reschedule_daily_quiz_for_chat)

# Импорт обработчика ответов на опросы
from poll_answer_handler import handle_poll_answer


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

# --- Функция для планирования всех ежедневных викторин при запуске ---
async def schedule_all_daily_quizzes_on_startup(application: Application):
    if not state.daily_quiz_subscriptions:
        logger.info("Нет чатов, подписанных на ежедневную викторину. Планирование не требуется.")
        return

    logger.info(f"Планирование ежедневных викторин для {len(state.daily_quiz_subscriptions)} подписанных чатов...")
    scheduled_count = 0
    for chat_id_str in state.daily_quiz_subscriptions.keys():
        try:
            # Передаем application в _schedule_or_reschedule_daily_quiz_for_chat
            await _schedule_or_reschedule_daily_quiz_for_chat(application, chat_id_str)
            scheduled_count += 1
        except Exception as e:
            logger.error(f"Ошибка при планировании ежедневной викторины для чата {chat_id_str} при запуске: {e}", exc_info=True)
    logger.info(f"Завершено планирование ежедневных викторин при запуске. Запланировано для {scheduled_count} чатов.")


# --- Основная функция для запуска бота ---
async def main_async(): # Переименовано в main_async для использования await
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
    job_queue: JobQueue | None = application.job_queue # JobQueue инициализируется через build()

    if not job_queue: # Эта проверка скорее для спокойствия, build() должен его создать
        logger.critical("JobQueue не инициализирован после ApplicationBuilder().build(). Задачи не будут работать.")
        return

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
    application.add_handler(CommandHandler("setdailyquiztime", set_daily_quiz_time_command))
    application.add_handler(CommandHandler("setdailyquizcategories", set_daily_quiz_categories_command))
    application.add_handler(CommandHandler("showdailyquizsettings", show_daily_quiz_settings_command))

    # Обработчик для кнопок выбора категории /quiz10
    application.add_handler(CallbackQueryHandler(handle_quiz10_category_selection,
                                                 pattern=f"^{CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT}|^({CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY})$"))

    application.add_handler(PollAnswerHandler(handle_poll_answer))
    application.add_error_handler(error_handler)

    # Планирование всех ежедневных викторин при запуске
    await schedule_all_daily_quizzes_on_startup(application) # Используем await

    logger.info("Бот успешно настроен и запускается...")
    # Используем run_polling с await, если это асинхронная функция в вашей версии PTB
    # Для PTB v20+ run_polling() обычно блокирующий.
    # Чтобы сделать main асинхронной, мы можем запустить application.initialize(), application.start(),
    # а затем application.updater.start_polling() или просто application.run_polling() если он не блокирует.
    # Однако, обычно run_polling() является последним вызовом.
    # В PTB 20+, run_polling() is blocking, and main() cannot be async like this without
    # an event loop manager like asyncio.run(main_async()).
    # Assuming the entry point will handle asyncio.run() if this main function is async.
    # For simplicity with the provided structure, let's keep main() synchronous and schedule_all_daily_quizzes_on_startup
    # will be awaited if necessary within an async context or called synchronously if possible.

    # Если schedule_all_daily_quizzes_on_startup действительно async, то main тоже должна быть.
    # Иначе, если PTB < 20 или используется специфичный запуск, application.start() и updater.start_polling() могут быть разделены.
    # PTB 21.x: application.run_polling() is blocking and should be the last call.
    # To call an async function like schedule_all_daily_quizzes_on_startup before run_polling,
    # application.job_queue.run_once(schedule_all_daily_quizzes_on_startup_job_wrapper, when=1, data=application)
    # or better, use application.post_init
    
    # A more robust way for post-initialization tasks in PTB 20+
    async def post_init_hook(app: Application):
        await schedule_all_daily_quizzes_on_startup(app)
        logger.info("Post-initialization hook executed: daily quizzes scheduled.")

    application.post_init = post_init_hook


    # Старый способ:
    # if job_queue:
    #     target_time_msk = moscow_time(DAILY_QUIZ_DEFAULT_HOUR_MSK, DAILY_QUIZ_DEFAULT_MINUTE_MSK) # Это было для мастер-джобы
    #     # Этот блок больше не нужен, так как нет мастер-джобы
    # else:
    #     logger.warning("JobQueue не доступен, ежедневная викторина не будет запланирована.")

    logger.info("Бот успешно настроен и запускается...")
    application.run_polling() # Это блокирующий вызов
    logger.info("Бот остановлен.")

def main(): # Оставляем main синхронным
    # Запуск асинхронной main_async, если бы она была полностью асинхронной
    # import asyncio
    # asyncio.run(main_async())
    # Но так как run_polling блокирующий, и post_init теперь используется,
    # логика из main_async переносится сюда, а post_init будет вызван PTB.

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
    
    # Регистрация обработчиков (как в main_async)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("categories", categories_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("quiz10", quiz10_command))
    application.add_handler(CommandHandler("quiz10notify", quiz10notify_command))
    application.add_handler(CommandHandler("stopquiz", stop_quiz_command))
    application.add_handler(CommandHandler("rating", rating_command))
    application.add_handler(CommandHandler("globaltop", global_top_command))
    application.add_handler(CommandHandler("subscribe_daily_quiz", subscribe_daily_quiz_command))
    application.add_handler(CommandHandler("unsubscribe_daily_quiz", unsubscribe_daily_quiz_command))
    application.add_handler(CommandHandler("setdailyquiztime", set_daily_quiz_time_command))
    application.add_handler(CommandHandler("setdailyquizcategories", set_daily_quiz_categories_command))
    application.add_handler(CommandHandler("showdailyquizsettings", show_daily_quiz_settings_command))
    application.add_handler(CallbackQueryHandler(handle_quiz10_category_selection,
                                                 pattern=f"^{CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT}|^({CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY})$"))
    application.add_handler(PollAnswerHandler(handle_poll_answer))
    application.add_error_handler(error_handler)

    # Назначаем post_init хук
    async def post_init_hook(app: Application):
        logger.info("Выполняется post_init хук для планирования ежедневных викторин...")
        await schedule_all_daily_quizzes_on_startup(app)
        logger.info("Post-initialization хук выполнен: ежедневные викторины запланированы.")

    application.post_init = post_init_hook
    
    logger.info("Бот успешно настроен и запускается...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Бот остановлен.")


if __name__ == '__main__':
    main()
