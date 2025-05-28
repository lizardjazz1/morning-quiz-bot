#bot.py
import sys
import os

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# --- Далее идут все ваши остальные импорты ---
import logging
import asyncio
import signal
import copy # Для deepcopy default_chat_settings

from telegram import Update, BotCommand, Message
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ContextTypes, PicklePersistence, ConversationHandler, JobQueue,
    Defaults # <--- Добавлен импорт Defaults
)
from telegram.constants import ParseMode
from telegram.error import BadRequest

# Модули приложения
from app_config import AppConfig # Точка входа для конфигурации
from state import BotState, QuizState
from data_manager import DataManager
from poll_answer_handler import CustomPollAnswerHandler # Обработчик ответов на опросы
from utils import get_current_utc_time, schedule_job_unique, escape_markdown_v2, is_user_admin_in_update, get_mention_html, pluralize

# Менеджеры логики
from modules.category_manager import CategoryManager
from modules.score_manager import ScoreManager
from modules.quiz_engine import QuizEngine

# Обработчики команд и колбэков
from handlers.quiz_manager import QuizManager
from handlers.rating_handlers import RatingHandlers
from handlers.config_handlers import ConfigHandlers
from handlers.daily_quiz_scheduler import DailyQuizScheduler
from handlers.common_handlers import CommonHandlers
from handlers.cleanup_handler import schedule_cleanup_job

# Настройка логирования
LOG_LEVEL_DEFAULT = logging.INFO
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=LOG_LEVEL_DEFAULT,
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

stop_event = asyncio.Event()

async def sigterm_handler(_signum, _frame):
    logger.info(f"Получен сигнал SIGTERM/SIGINT ({_signum}), начинаю корректное завершение...")
    stop_event.set()

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Исключение при обработке обновления:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat:
        try:
            from utils import escape_markdown_v2 as local_escape_markdown_v2 # Используем псевдоним для ясности
            error_text = "Произошла внутренняя ошибка\\. Мы уже работаем над этим\\."
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=error_text,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception as e_send:
            logger.error(f"Не удалось отправить сообщение об ошибке пользователю: {e_send}")

async def post_init_actions(application: Application) -> None:
    logger.info("Выполняется post_init_actions...")
    app_config: AppConfig = application.bot_data['app_config'] # type: ignore

    daily_quiz_scheduler: DailyQuizScheduler = application.bot_data.get('daily_quiz_scheduler') # type: ignore
    if daily_quiz_scheduler:
        await daily_quiz_scheduler.initialize_jobs()
    else:
        logger.error("DailyQuizScheduler не найден в application.bot_data во время post_init_actions.")

    bot_commands = [
        BotCommand(app_config.commands.start, "🚀 Запуск/Информация"),
        BotCommand(app_config.commands.help, "❓ Помощь"),
        BotCommand(app_config.commands.quiz, "🎮 Викторина (с настройкой или быстрая)"),
        BotCommand(app_config.commands.categories, "📚 Категории вопросов"),
        BotCommand(app_config.commands.top, "🏆 Рейтинг чата"),
        BotCommand(app_config.commands.global_top, "🌍 Глобальный рейтинг"),
        BotCommand(app_config.commands.mystats, "📊 Моя статистика"),
        BotCommand(app_config.commands.stop_quiz, "🛑 Остановить викторину (админ/инициатор)"),
        BotCommand(app_config.commands.admin_settings, "🛠️ Админ. настройки чата (админ)"),
        BotCommand(app_config.commands.view_chat_config, "👁️ Посмотреть настройки чата"),
        BotCommand(app_config.commands.cancel, "❌ Отмена текущего действия/диалога"),
    ]
    try:
        await application.bot.set_my_commands(bot_commands)
        logger.info("Команды бота успешно установлены.")
    except Exception as e:
        logger.error(f"Не удалось установить команды бота: {e}")

    if application.job_queue:
        schedule_cleanup_job(application.job_queue)
    else:
        logger.warning("JobQueue не доступен в application.post_init. Задача очистки не запланирована.")

    logger.info("post_init_actions завершены.")

async def pre_shutdown_actions(application: Application) -> None:
    logger.info("Выполняется pre_shutdown_actions (сохранение данных)...")
    data_manager: DataManager = application.bot_data.get('data_manager') # type: ignore
    if data_manager:
        data_manager.save_all_data()
        logger.info("Все данные сохранены.")
    else:
        logger.warning("DataManager не найден в application.bot_data при завершении. Данные не сохранены.")
    logger.info("pre_shutdown_actions завершены.")

async def main() -> None:
    logger.info("Запуск бота...")

    app_config = AppConfig()

    log_level_from_config_str = app_config.log_level_str
    log_level_from_config = getattr(logging, log_level_from_config_str.upper(), logging.INFO)
    logging.getLogger().setLevel(log_level_from_config)
    for handler_obj in logging.getLogger().handlers:
        handler_obj.setLevel(log_level_from_config)
    logger.info(f"Уровень логирования установлен на: {log_level_from_config_str}")

    if not app_config.bot_token:
        logger.critical("Токен бота BOT_TOKEN не найден. Завершение работы.")
        return

    bot_state = BotState(app_config=app_config)
    data_manager = DataManager(app_config=app_config, state=bot_state)

    try:
        logger.info("Первичная загрузка данных...")
        data_manager.load_all_data()
        logger.info("Первичная загрузка данных завершена.")
        if not bot_state.quiz_data:
             logger.warning("Данные вопросов (quiz_data) не загружены или пусты.")
    except Exception as e:
        logger.error(f"Критическая ошибка при первичной загрузке данных: {e}", exc_info=True)
        return

    persistence = PicklePersistence(filepath=app_config.paths.ptb_persistence_file)

    # --- ИСПРАВЛЕНИЕ УСТАНОВКИ PARSE_MODE ---
    defaults = Defaults(parse_mode=ParseMode.MARKDOWN_V2)
    application_builder = Application.builder().token(app_config.bot_token).persistence(persistence).defaults(defaults)
    # -----------------------------------------

    application_builder.post_init(post_init_actions)
    application_builder.post_shutdown(pre_shutdown_actions)
    # application_builder.parse_mode(ParseMode.MARKDOWN_V2) # <--- ЭТА СТРОКА БЫЛА НЕВЕРНОЙ И УДАЛЕНА

    application = application_builder.build()

    application.bot_data['app_config'] = app_config
    application.bot_data['bot_state'] = bot_state
    application.bot_data['data_manager'] = data_manager

    category_manager = CategoryManager(state=bot_state, app_config=app_config)
    application.bot_data['category_manager'] = category_manager # Добавляем в bot_data для доступа из других мест если нужно

    score_manager = ScoreManager(app_config=app_config, state=bot_state, data_manager=data_manager)
    application.bot_data['score_manager'] = score_manager

    quiz_manager = QuizManager(
        app_config=app_config, state=bot_state, category_manager=category_manager,
        score_manager=score_manager, data_manager=data_manager, application=application
    )
    rating_handlers = RatingHandlers(score_manager=score_manager, app_config=app_config)
    config_handlers_instance = ConfigHandlers(
        app_config=app_config, state=bot_state, data_manager=data_manager,
        category_manager=category_manager, application=application
    )
    common_handlers_instance = CommonHandlers(app_config=app_config, category_manager=category_manager, bot_state=bot_state)

    daily_quiz_scheduler = DailyQuizScheduler(
        app_config=app_config, state=bot_state, data_manager=data_manager,
        quiz_manager=quiz_manager, application=application
    )
    config_handlers_instance.set_daily_quiz_scheduler(daily_quiz_scheduler)
    application.bot_data['daily_quiz_scheduler'] = daily_quiz_scheduler

    custom_poll_answer_handler = CustomPollAnswerHandler(
        state=bot_state, score_manager=score_manager, app_config=app_config
    )
    custom_poll_answer_handler.set_quiz_manager(quiz_manager)

    logger.info("Все менеджеры и обработчики команд инициализированы.")

    application.add_handler(custom_poll_answer_handler.get_handler())
    application.add_handlers(config_handlers_instance.get_handlers())
    application.add_handlers(quiz_manager.get_handlers())
    application.add_handlers(rating_handlers.get_handlers())
    application.add_handlers(common_handlers_instance.get_handlers())
    application.add_handlers(daily_quiz_scheduler.get_handlers())

    application.add_error_handler(error_handler)
    logger.info("Все обработчики PTB зарегистрированы.")

    logger.info("Запуск бота (polling)...")

    await application.initialize()
    await application.start()
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    await stop_event.wait()

    logger.info("Начало процедуры остановки бота...")
    await application.updater.stop()
    await application.stop()
    await application.shutdown()
    logger.info("Бот успешно остановлен.")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()

    if sys.platform != "win32":
        if hasattr(signal, "SIGTERM"):
            try:
                loop.add_signal_handler(
                    signal.SIGTERM,
                    lambda signum_arg=signal.SIGTERM, frame_arg=None: asyncio.create_task(sigterm_handler(signum_arg, frame_arg))
                )
            except (NotImplementedError, RuntimeError) as e:
                logger.warning(f"Не удалось установить обработчик SIGTERM: {e}")

        try:
            loop.add_signal_handler(
                signal.SIGINT,
                lambda signum_arg=signal.SIGINT, frame_arg=None: asyncio.create_task(sigterm_handler(signum_arg, frame_arg))
            )
        except (NotImplementedError, RuntimeError) as e:
            logger.warning(f"Не удалось установить обработчик SIGINT: {e}")
    else:
        logger.info("Обработчики сигналов SIGTERM/SIGINT не устанавливаются в Windows. Используйте Ctrl+C для KeyboardInterrupt.")

    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Приложение прервано через KeyboardInterrupt.")
        if not stop_event.is_set():
            stop_event.set()
    finally:
        if not stop_event.is_set():
            logger.warning("stop_event не был установлен при выходе из (KeyboardInterrupt/finally). Попытка установить.")
            stop_event.set()
        logger.info("Программа бота завершена.")

