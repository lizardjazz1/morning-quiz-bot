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
# │   └── rating_handlers.py   # Для /rating, /globaltop
# ├── poll_answer_handler.py # Обработчик ответов на опросы
# └── .env                   # Для BOT_TOKEN
# └── questions.json         # Наш файл с вопросами
# └── users.json             # Данные пользователей

from telegram.ext import (ApplicationBuilder, CommandHandler, PollAnswerHandler,
                          CallbackQueryHandler, ContextTypes)

# Импорты из других модулей проекта
from config import (TOKEN, logger, CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY,
                    CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY) # CALLBACK_DATA_QUIZ10_NOTIFY_START_NOW здесь не нужен для регистрации
from data_manager import load_questions, load_user_data

# Импорт обработчиков из нового пакета handlers
from handlers.common_handlers import start_command, categories_command
from handlers.quiz_single_handler import quiz_command
from handlers.quiz_session_handlers import (quiz10_command, handle_quiz10_category_selection,
                                            quiz10notify_command, stop_quiz_command)
from handlers.rating_handlers import rating_command, global_top_command

# Импорт обработчика ответов на опросы
from poll_answer_handler import handle_poll_answer # Этот файл остался на верхнем уровне, как в вашем `BOT.txt`

# --- Обработчик ошибок ---
# Эта функция будет вызываться при возникновении ошибок в других обработчиках.
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Произошла ошибка при обработке обновления:", exc_info=context.error)

# --- Основная функция для запуска бота ---
def main():
    if not TOKEN:
        print("Токен BOT_TOKEN не найден! Пожалуйста, проверьте ваш .env файл и переменную BOT_TOKEN.")
        return

    logger.info("Загрузка вопросов...")
    load_questions()
    logger.info("Загрузка данных пользователей...")
    load_user_data()

    application = ApplicationBuilder().token(TOKEN).build()

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

    # Обработчик для кнопок выбора категории /quiz10
    application.add_handler(CallbackQueryHandler(handle_quiz10_category_selection,
                                                 pattern=f"^{CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY}|^({CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY})$"))

    # ВНИМАНИЕ: Callback для CALLBACK_DATA_QUIZ10_NOTIFY_START_NOW (если он был бы) не нужен,
    # так как старт происходит через job_queue и функцию _start_scheduled_quiz10_job_callback

    application.add_handler(PollAnswerHandler(handle_poll_answer))
    application.add_error_handler(error_handler)

    logger.info("Бот успешно настроен и запускается...")
    application.run_polling()
    logger.info("Бот остановлен.")

if __name__ == '__main__':
    main()
