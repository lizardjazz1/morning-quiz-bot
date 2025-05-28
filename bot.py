# bot/bot.py
import logging
import asyncio
import signal # Для корректной обработки сигналов завершения

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes,
    PicklePersistence, # Для сохранения состояния ConversationHandler между перезапусками
    PollAnswerHandler as PTBPollAnswerHandler, # Переименовываем для ясности
)
from telegram.constants import ParseMode

from .app_config import AppConfig
from .state import BotState
from .data_manager import DataManager
# Мы будем использовать CustomPollAnswerHandler, который предоставляет callback
from .poll_answer_handler import CustomPollAnswerHandler
from .utils import load_commands_from_config # Предполагаем, что эта утилита будет создана

# Импорт менеджеров и их классов-обработчиков
from .modules.category_manager import CategoryManager
from .modules.score_manager import ScoreManager
from .handlers.quiz_manager import QuizManager
from .handlers.rating_handlers import RatingHandlers
from .handlers.config_handlers import ConfigHandlers
from .handlers.daily_quiz_scheduler import DailyQuizScheduler
from .handlers.common_handlers import CommonHandlers
# from .handlers.cleanup_handler import CleanupHandler # Раскомментировать, если будет реализован

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'), # Логи в файл
        logging.StreamHandler()                           # Логи в консоль
    ]
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.vendor.ptb_urllib3.urllib3.connectionpool").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные переменные для управления graceful shutdown
stop_signals_received = asyncio.Event()

async def signal_handler(sig, frame):
    logger.info(f"Получен сигнал {sig}, начинаю завершение работы...")
    stop_signals_received.set()

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логирует ошибки, вызванные Updates."""
    logger.error(f"Исключение при обработке обновления {update}:", exc_info=context.error)
    # Дополнительно можно отправлять сообщение пользователю или разработчику
    # if isinstance(update, Update) and update.effective_chat:
    #     await context.bot.send_message(
    #         chat_id=update.effective_chat.id,
    #         text="Произошла внутренняя ошибка. Мы уже работаем над этим."
    #     )

async def main() -> None:
    """Основная функция запуска бота."""
    logger.info("Запуск бота...")

    # 1. Инициализация конфигурации
    app_config = AppConfig()
    logger.info("Конфигурация загружена.")

    # 2. Инициализация состояния бота
    bot_state = BotState()
    logger.info("Состояние бота инициализировано.")

    # 3. Инициализация менеджера данных и загрузка данных
    # DataManager теперь ожидает app_config, а не app_config.paths
    data_manager = DataManager(app_config=app_config, state=bot_state)
    await data_manager.load_all_data()
    logger.info("Данные загружены менеджером данных.")

    # 4. Инициализация менеджеров модулей
    # CategoryManager ожидает словарь questions_by_category и app_config
    category_manager = CategoryManager(
        questions_by_category=bot_state.questions_by_category,
        app_config=app_config
    )
    logger.info("CategoryManager инициализирован.")

    score_manager = ScoreManager(
        app_config=app_config,
        state=bot_state,
        data_manager=data_manager
    )
    logger.info("ScoreManager инициализирован.")

    # 5. Инициализация обработчика ответов на опросы (Polls)
    # CustomPollAnswerHandler должен быть классом, предоставляющим get_handler()
    custom_poll_answer_handler = CustomPollAnswerHandler(
        state=bot_state,
        score_manager=score_manager,
        app_config=app_config
    )
    logger.info("CustomPollAnswerHandler инициализирован.")

    # 6. Настройка персистентности для PTB (например, для ConversationHandler)
    # Убедитесь, что директория для файла персистентности существует
    persistence = PicklePersistence(filepath=app_config.paths.ptb_persistence_file)
    logger.info(f"PTB persistence будет использовать файл: {app_config.paths.ptb_persistence_file}")

    # 7. Создание экземпляра Application
    application = (
        Application.builder()
        .token(app_config.bot_token)
        .persistence(persistence)
        .parse_mode(ParseMode.HTML) # Установка режима парсинга по умолчанию
        .build()
    )
    logger.info("Экземпляр Application создан.")

    # 8. Инициализация классов-обработчиков команд
    # Передаем application в DailyQuizScheduler для доступа к job_queue
    # QuizManager теперь получает data_manager
    quiz_manager = QuizManager(
        app_config=app_config,
        state=bot_state,
        category_manager=category_manager,
        score_manager=score_manager,
        data_manager=data_manager,
        application=application # Для доступа к job_queue в QuizManager, если нужно
    )
    logger.info("QuizManager инициализирован.")

    rating_handlers = RatingHandlers(
        score_manager=score_manager,
        app_config=app_config
    )
    logger.info("RatingHandlers инициализирован.")

    config_handlers = ConfigHandlers(
        app_config=app_config,
        state=bot_state,
        data_manager=data_manager,
        category_manager=category_manager
    )
    logger.info("ConfigHandlers инициализирован.")

    common_handlers = CommonHandlers(
        app_config=app_config,
        category_manager=category_manager,
        bot_state=bot_state # Добавил bot_state, если, например, /start должен что-то из него читать
    )
    logger.info("CommonHandlers инициализирован.")

    # DailyQuizScheduler инициализируется после application, чтобы получить job_queue
    daily_quiz_scheduler = DailyQuizScheduler(
        app_config=app_config,
        state=bot_state,
        quiz_manager=quiz_manager, # Передаем QuizManager для запуска викторин
        data_manager=data_manager,
        application=application # Для доступа к job_queue
    )
    logger.info("DailyQuizScheduler инициализирован и запустит задачи планировщика.")
    await daily_quiz_scheduler.initialize_jobs() # Явный вызов для инициализации задач

    # cleanup_handler = CleanupHandler(app_config, bot_state, data_manager) # Если будет

    # 9. Регистрация обработчиков
    application.add_handler(custom_poll_answer_handler.get_handler()) # PTBPollAnswerHandler
    application.add_handlers(quiz_manager.get_handlers())
    application.add_handlers(rating_handlers.get_handlers())
    application.add_handlers(config_handlers.get_handlers())
    application.add_handlers(common_handlers.get_handlers())
    application.add_handlers(daily_quiz_scheduler.get_handlers()) # Если у него есть команды для управления
    # if cleanup_handler: application.add_handlers(cleanup_handler.get_handlers())

    # Регистрация обработчика ошибок
    application.add_error_handler(error_handler)
    logger.info("Все обработчики зарегистрированы.")

    # 10. Установка команд бота
    # bot_commands = load_commands_from_config(app_config)
    # Вместо load_commands_from_config можно определить команды вручную или в AppConfig
    bot_commands = [
        BotCommand(app_config.commands.start, "🚀 Запуск/перезапуск бота"),
        BotCommand(app_config.commands.help, "❓ Помощь по командам"),
        BotCommand(app_config.commands.quiz, "🎮 Начать викторину (гибкая настройка)"),
        BotCommand(app_config.commands.categories, "📚 Показать доступные категории"),
        BotCommand(app_config.commands.top, "🏆 Рейтинг игроков"),
        BotCommand(app_config.commands.mystats, "📊 Моя статистика"),
        # Команды для администрирования настроек чата
        BotCommand(app_config.commands.set_quiz_type, "⚙️ Тип викторины для чата (single/session)"),
        BotCommand(app_config.commands.set_quiz_questions, "⚙️ Кол-во вопросов для чата (для /quiz)"),
        BotCommand(app_config.commands.set_quiz_open_period, "⚙️ Время на ответ в чате (сек)"),
        BotCommand(app_config.commands.enable_category, "➕ Включить категорию для чата"),
        BotCommand(app_config.commands.disable_category, "➖ Выключить категорию для чата"),
        BotCommand(app_config.commands.reset_chat_config, "🔄 Сбросить настройки чата"),
        BotCommand(app_config.commands.view_chat_config, "👁️ Посмотреть настройки чата"),
        # Команды для управления ежедневной викториной
        BotCommand(app_config.commands.subscribe_daily_quiz, "📅 Подписаться на ежедневную викторину"),
        BotCommand(app_config.commands.unsubscribe_daily_quiz, "❌ Отписаться от ежедневной викторины"),
        BotCommand(app_config.commands.set_daily_quiz_time, "⏰ Установить время ежедневной викторины"),
    ]
    if bot_commands:
        await application.bot.set_my_commands(bot_commands)
        logger.info("Команды бота установлены.")

    # 11. Запуск бота
    logger.info("Запуск обработки обновлений...")
    await application.initialize() # Инициализация Application перед run_polling/run_webhook
    await application.start()
    await application.updater.start_polling() # Запускаем polling

    # Ожидаем сигнала завершения
    await stop_signals_received.wait()

    # Корректное завершение
    logger.info("Остановка обработки обновлений...")
    await application.updater.stop()
    await application.stop()
    await application.shutdown() # Освобождаем ресурсы
    logger.info("Бот остановлен.")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    # Установка обработчиков сигналов
    for sig_name in ('SIGINT', 'SIGTERM'):
        if hasattr(signal, sig_name): # Проверка для Windows, где SIGTERM может отсутствовать
            loop.add_signal_handler(getattr(signal, sig_name),
                                    lambda s=sig_name: asyncio.create_task(signal_handler(s, None)))
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Принудительное завершение через KeyboardInterrupt.")
    finally:
        logger.info("Цикл событий asyncio завершен.")

