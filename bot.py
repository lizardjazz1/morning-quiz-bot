# bot.py
import asyncio
from datetime import datetime

from telegram.ext import (Application, CommandHandler, PollAnswerHandler, CallbackQueryHandler,
                          MessageHandler, filters, Defaults)
from telegram.constants import ParseMode
import pytz # Для работы с часовыми поясами

from config import TOKEN, logger
import state
from data_manager import load_quiz_data, load_user_scores, save_user_scores, \
                         load_daily_quiz_subscriptions, save_daily_quiz_subscriptions
from quiz_logic import handle_poll_answer
from handlers.quiz_session_handlers import (quiz_command, quiz10_command, stop_quiz_command,
                                            show_quiz_categories_command, handle_quiz10_category_selection,
                                            quiz10_notify_command)
from handlers.rating_handlers import top_command, my_stats_command, clear_stats_command
from handlers.admin_handlers import reload_questions_command, get_log_command, get_users_command, \
                                    get_daily_subs_command, admin_help_command, broadcast_command
from handlers.daily_quiz_handlers import (subscribe_daily_quiz_command, unsubscribe_daily_quiz_command,
                                          set_daily_quiz_time_command, set_daily_quiz_categories_command,
                                          show_daily_quiz_settings_command, handle_daily_quiz_category_selection,
                                          _schedule_or_reschedule_daily_quiz_for_chat) # Импорт для инициализации

async def post_init(application: Application):
    """Выполняется после инициализации Application и его компонентов (например, job_queue)."""
    logger.info("post_init: Загрузка подписок на ежедневные викторины...")
    load_daily_quiz_subscriptions()
    if state.daily_quiz_subscriptions:
        logger.info(f"Загружено {len(state.daily_quiz_subscriptions)} подписок.")
        # Перепланируем все сохраненные ежедневные викторины
        for chat_id_str in state.daily_quiz_subscriptions.keys():
            # Не используем await здесь, т.к. _schedule_or_reschedule ожидает Application, а не его корутину
            # Он сам по себе асинхронный внутри, если нужно.
            # И _schedule_or_reschedule_daily_quiz_for_chat уже async
            await _schedule_or_reschedule_daily_quiz_for_chat(application, chat_id_str)
            # Добавил await, так как функция сама по себе async
    else:
        logger.info("Подписки на ежедневные викторины не найдены или пусты.")

    # Установка команд бота
    commands = [
        ("quiz", "🎲 Случайный вопрос"),
        ("quiz10", "🔟 Викторина из 10 вопросов (можно указать категорию)"),
        ("stopquiz", "⛔ Остановить текущую/отменить запланированную викторину (/quiz10, /quiz10notify, ежедневную)"),
        ("top", "🏆 Показать топ-10 игроков чата"),
        ("mystats", "📊 Моя статистика в этом чате"),
        ("quiz10notify", "🗓️ Запланировать /quiz10 с уведомлением ([мин_до_старта] [время_на_ответ] [категория])"),

        ("subdaily", "📅 Подписаться на ежедневную викторину (админ)"),
        ("unsubdaily", "✖️ Отписаться от ежедневной викторины (админ)"),
        ("setdailyquiztime", "⏰ Установить время ежедневной викторины (ЧЧ:ММ МСК, админ)"),
        ("setdailyquizcategories", "🏷️ Установить категории для ежедневной викторины (админ)"),
        ("showdailyquizsettings", "⚙️ Показать настройки ежедневной викторины"),

        ("adminhelp", "🛠️ Справка по админ-командам (для владельца бота)"),
        # ("reloadquestions", "🔄 Перезагрузить вопросы (владелец бота)"), # Скрыл, есть в adminhelp
        # ("getlog", "📄 Получить лог-файл (владелец бота)"), # Скрыл, есть в adminhelp
        # ("getusers", "👥 Получить файл пользователей (владелец бота)"), # Скрыл, есть в adminhelp
        # ("getdailysubs", "📋 Получить файл подписок на ежедневные (владелец бота)"), # Скрыл, есть в adminhelp
        # ("clearstats", "🗑️ Очистить статистику чата (админ)"), # Скрыл, есть в adminhelp
        # ("broadcast", "📢 Рассылка сообщения (владелец бота)") # Скрыл, есть в adminhelp
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Команды бота установлены.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логирует ошибки, вызванные обновлениями."""
    logger.error(msg="Исключение при обработке обновления:", exc_info=context.error)
    # Можно добавить отправку сообщения пользователю или разработчику при критических ошибках


def main() -> None:
    """Запускает бота."""
    logger.info("Запуск бота...")

    # Загрузка данных при старте
    load_quiz_data()
    load_user_scores()
    # load_daily_quiz_subscriptions() # Перенесено в post_init

    # Установка настроек по умолчанию для всех обработчиков (например, parse_mode)
    defaults = Defaults(parse_mode=ParseMode.HTML, tzinfo=pytz.timezone('Europe/Moscow'))

    application = Application.builder().token(TOKEN).defaults(defaults).post_init(post_init).build()

    # --- Регистрация обработчиков ---

    # Команды викторин и сессий
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("quiz10", quiz10_command)) # Для прямого вызова с аргументами
    application.add_handler(CommandHandler("stopquiz", stop_quiz_command))
    application.add_handler(CommandHandler("quizcategories", show_quiz_categories_command)) # Альяс для show_quiz_categories_command
    application.add_handler(CommandHandler("qcat", show_quiz_categories_command)) # Короткий альяс
    
    # Callback для выбора категории /quiz10
    application.add_handler(CallbackQueryHandler(handle_quiz10_category_selection, pattern=f"^{CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT}|^({CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY})$"))

    # Команда для уведомления /quiz10notify
    application.add_handler(CommandHandler("quiz10notify", quiz10_notify_command))

    # Обработчик ответов на опросы (для всех викторин)
    application.add_handler(PollAnswerHandler(handle_poll_answer))

    # Команды рейтинга
    application.add_handler(CommandHandler("top", top_command))
    application.add_handler(CommandHandler("mystats", my_stats_command))

    # Команды ежедневной викторины
    application.add_handler(CommandHandler("subdaily", subscribe_daily_quiz_command))
    application.add_handler(CommandHandler("unsubdaily", unsubscribe_daily_quiz_command))
    application.add_handler(CommandHandler("setdailyquiztime", set_daily_quiz_time_command))
    application.add_handler(CommandHandler("setdailyquizcategories", set_daily_quiz_categories_command))
    application.add_handler(CommandHandler("showdailyquizsettings", show_daily_quiz_settings_command))
    # Callback для выбора категории ежедневной викторины
    application.add_handler(CallbackQueryHandler(handle_daily_quiz_category_selection, pattern=f"^{CALLBACK_DATA_PREFIX_DAILY_QUIZ_CATEGORY_SHORT}|^({CALLBACK_DATA_DAILY_QUIZ_RANDOM_CATEGORY})$"))


    # Админ-команды
    application.add_handler(CommandHandler("adminhelp", admin_help_command))
    application.add_handler(CommandHandler("reloadquestions", reload_questions_command))
    application.add_handler(CommandHandler("getlog", get_log_command))
    application.add_handler(CommandHandler("getusers", get_users_command))
    application.add_handler(CommandHandler("getdailysubs", get_daily_subs_command))
    application.add_handler(CommandHandler("clearstats", clear_stats_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))

    # Обработчик ошибок
    application.add_error_handler(error_handler)

    # Запуск бота
    logger.info("Бот начинает опрос...")
    application.run_polling()

    # Сохранение данных при штатном завершении (Ctrl+C)
    # Этот блок может не всегда выполняться, если процесс убит иначе
    logger.info("Бот останавливается. Сохранение данных...")
    save_user_scores()
    save_daily_quiz_subscriptions()
    logger.info("Данные сохранены. Выход.")


if __name__ == '__main__':
    main()
