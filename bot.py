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
import pytz

from telegram.ext import (Application, ApplicationBuilder, CommandHandler, PollAnswerHandler,
                          CallbackQueryHandler, ContextTypes, JobQueue)
from telegram import Update

from config import (TOKEN, logger, CB_Q10_CAT_PFX, CB_Q10_RND_CAT) # Renamed constants
import state
from data_manager import load_qs, load_usr_data, load_daily_q_subs # Renamed functions

from handlers.common_handlers import start_command, categories_command
from handlers.quiz_single_handler import quiz_command
from handlers.quiz_session_handlers import (quiz10_command, on_q10_cat_select, # Renamed handler
                                            quiz10notify_command, stop_quiz_command)
from handlers.rating_handlers import rating_command, global_top_command
from handlers.daily_quiz_handlers import (subscribe_daily_quiz_command, unsubscribe_daily_quiz_command,
                                          set_daily_quiz_time_command, set_daily_quiz_categories_command,
                                          show_daily_quiz_settings_command, _sched_daily_q_chat) # Renamed handler

from poll_answer_handler import on_poll_answer # Renamed handler

async def error_hndlr(update: object, context: ContextTypes.DEFAULT_TYPE) -> None: # Renamed
    logger.error("Произошла ошибка при обработке обновления:", exc_info=context.error)
    # if isinstance(update, Update) and update.effective_chat:
    #     try:
    #         await context.bot.send_message(chat_id=update.effective_chat.id, text="Произошла внутренняя ошибка.")
    #     except Exception as e: logger.error(f"Не удалось отправить сообщение об ошибке: {e}")

async def sched_all_daily_qs_startup(app: Application): # Renamed app from application
    if not state.daily_q_subs: # Use renamed state var
        logger.info("Нет чатов с подписками на DQ. Планирование DQ при запуске не требуется.")
        return

    logger.info(f"Планирование DQ для {len(state.daily_q_subs)} чатов при запуске...")
    sched_cnt = 0 # Renamed
    # Iterate over a copy of keys if modifications to state.daily_q_subs can happen during iteration elsewhere
    # For startup, this is likely safe, but good practice for dynamic dicts.
    for cid_str in list(state.daily_q_subs.keys()): # Renamed, use renamed state var
        try:
            # _sched_daily_q_chat expects the application instance
            await _sched_daily_q_chat(app, cid_str) # Renamed
            sched_cnt += 1
        except Exception as e:
            logger.error(f"Ошибка планирования DQ для чата {cid_str} при запуске: {e}", exc_info=True)
    logger.info(f"Завершено планирование DQ при запуске. Запланировано для {sched_cnt} чатов.")


def main():
    if not TOKEN:
        # Use logger for critical startup errors as well
        logger.critical("Токен BOT_TOKEN не найден в .env файле! Пожалуйста, проверьте .env и переменную BOT_TOKEN. Бот не будет запущен.")
        return # Exit if no token

    logger.info("Загрузка вопросов...")
    load_qs()
    logger.info("Загрузка данных пользователей...")
    load_usr_data()
    logger.info("Загрузка подписок на ежедневную викторину...") # Corrected log message
    load_daily_q_subs()

    app_builder = ApplicationBuilder().token(TOKEN) # Renamed
    # Increase default connection pool size for potentially more concurrent requests (e.g., many daily quiz jobs)
    # These are reasonable defaults, adjust if specific issues (like ReadTimeout) are observed.
    app_builder.http_version('1.1').pool_timeout(60).connect_timeout(30).read_timeout(30) # Added timeouts
    app = app_builder.build() # Renamed

    # Register command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("categories", categories_command))
    app.add_handler(CommandHandler("quiz", quiz_command))
    app.add_handler(CommandHandler("quiz10", quiz10_command))
    app.add_handler(CommandHandler("quiz10notify", quiz10notify_command))
    app.add_handler(CommandHandler("stopquiz", stop_quiz_command))
    app.add_handler(CommandHandler("rating", rating_command))
    app.add_handler(CommandHandler("globaltop", global_top_command))
    
    # Daily Quiz command handlers
    app.add_handler(CommandHandler("subscribe_daily_quiz", subscribe_daily_quiz_command))
    app.add_handler(CommandHandler("unsubscribe_daily_quiz", unsubscribe_daily_quiz_command))
    app.add_handler(CommandHandler("setdailyquiztime", set_daily_quiz_time_command))
    app.add_handler(CommandHandler("setdailyquizcategories", set_daily_quiz_categories_command))
    app.add_handler(CommandHandler("showdailyquizsettings", show_daily_quiz_settings_command))

    # Register other handlers
    # Pattern for quiz10 category selection callback
    app.add_handler(CallbackQueryHandler(on_q10_cat_select, # Renamed handler
                                         pattern=f"^{CB_Q10_CAT_PFX}|^({CB_Q10_RND_CAT})$")) # Renamed consts
    app.add_handler(PollAnswerHandler(on_poll_answer)) # Renamed handler
    
    # Register error handler
    app.add_error_handler(error_hndlr) # Renamed handler

    # Post-initialization hook for scheduling daily quizzes
    async def post_init_hook(current_app: Application): # Renamed app to current_app
        logger.info("Выполняется post_init хук для планирования DQ...")
        await sched_all_daily_qs_startup(current_app)
        logger.info("Post-init хук выполнен: DQ (пере)запланированы.")

    app.post_init = post_init_hook

    logger.info("Бот настроен и запускается...")
    # Run the bot until the user presses Ctrl-C
    # Using allowed_updates=Update.ALL_TYPES for simplicity, can be refined for production
    app.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Бот остановлен.")

if __name__ == '__main__':
    main()
