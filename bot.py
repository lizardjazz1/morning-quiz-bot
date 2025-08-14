#bot.py
import sys
import os

# Добавляем корень проекта в sys.path для корректных импортов
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import logging
import asyncio
from typing import Optional # Добавлен Optional

from telegram import Update, BotCommand
from telegram.ext import (
    Application, CommandHandler,
    CallbackQueryHandler, ContextTypes, PicklePersistence, ConversationHandler,
    Defaults
)
from telegram.constants import ParseMode
from telegram.error import BadRequest

# Модули приложения
from app_config import AppConfig
from state import BotState
from data_manager import DataManager
from poll_answer_handler import CustomPollAnswerHandler
from utils import escape_markdown_v2

# Менеджеры логики
from modules.category_manager import CategoryManager
from modules.score_manager import ScoreManager

# Обработчики команд и колбэков
from handlers.quiz_manager import QuizManager
from handlers.rating_handlers import RatingHandlers
from handlers.config_handlers import ConfigHandlers
from handlers.daily_quiz_scheduler import DailyQuizScheduler
from handlers.common_handlers import CommonHandlers
from handlers.cleanup_handler import schedule_cleanup_job

# Настройка логирования
# Сначала создаем временный уровень для инициализации
TEMP_LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL_MAP = {
    "DEBUG": logging.DEBUG, "INFO": logging.INFO,
    "WARNING": logging.WARNING, "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL
}
TEMP_LOG_LEVEL_DEFAULT = LOG_LEVEL_MAP.get(TEMP_LOG_LEVEL_STR, logging.INFO)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=TEMP_LOG_LEVEL_DEFAULT,
    handlers=[
        logging.FileHandler("bot.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram.ext.ExtBot").setLevel(logging.INFO)
logging.getLogger("telegram.bot").setLevel(logging.INFO)
logging.getLogger("telegram.net.TelegramRetryer").setLevel(logging.INFO)
logging.getLogger("telegram.net.HTTPXRequest").setLevel(logging.INFO)
logging.getLogger("apscheduler").setLevel(logging.INFO)


logger = logging.getLogger(__name__)

def update_logging_level(app_config):
    """Обновляет уровень логирования на основе конфигурации приложения"""
    new_level = LOG_LEVEL_MAP.get(app_config.log_level_str, logging.INFO)
    
    # Обновляем корневой логгер
    logging.getLogger().setLevel(new_level)
    
    # Обновляем основные логгеры приложения
    logging.getLogger("__main__").setLevel(new_level)
    logging.getLogger("app_config").setLevel(new_level)
    logging.getLogger("state").setLevel(new_level)
    logging.getLogger("data_manager").setLevel(new_level)
    logging.getLogger("handlers").setLevel(new_level)
    logging.getLogger("modules").setLevel(new_level)
    
    logger.info(f"🔧 Уровень логирования обновлен: {app_config.log_level_str} (режим: {app_config.debug_mode and 'TESTING' or 'PRODUCTION'})")

async def main() -> None:
    logger.info("Запуск бота...")
    application_instance: Optional[Application] = None # Переименовано для ясности
    data_manager_instance: Optional[DataManager] = None

    try:
        logger.debug("Загрузка конфигурации из AppConfig...")
        app_config = AppConfig()
        if not app_config.bot_token:
            logger.critical("Токен бота не найден. Укажите BOT_TOKEN в .env или конфигурации.")
            return
        logger.debug(f"AppConfig инициализирован. Режим отладки: {app_config.debug_mode}")
        
        # Обновляем уровень логирования на основе конфигурации
        update_logging_level(app_config)

        bot_state = BotState(app_config=app_config)
        data_manager = DataManager(state=bot_state, app_config=app_config)
        data_manager.load_all_data()
        data_manager_instance = data_manager
        
        # Передаем data_manager в BotState для автоматического сохранения
        bot_state.data_manager = data_manager

        category_manager = CategoryManager(state=bot_state, app_config=app_config, data_manager=data_manager)
        score_manager = ScoreManager(app_config=app_config, state=bot_state, data_manager=data_manager)

        persistence_path = os.path.join(app_config.data_dir, app_config.persistence_file_name)
        persistence = PicklePersistence(filepath=persistence_path)
        defaults = Defaults(parse_mode=ParseMode.MARKDOWN_V2)

        application_builder = (
            Application.builder()
            .token(app_config.bot_token)
            .persistence(persistence)
            .defaults(defaults)
            .concurrent_updates(True)
            .read_timeout(30)
            .connect_timeout(30)
            .write_timeout(30)
            .pool_timeout(20)
        )
        application_instance = application_builder.build() # Присваиваем созданный application
        logger.info("Объект Application создан.")

        # Передаем application в BotState для автоматического сохранения
        bot_state.application = application_instance

        application_instance.bot_data['bot_state'] = bot_state
        application_instance.bot_data['app_config'] = app_config
        application_instance.bot_data['data_manager'] = data_manager
        logger.debug(f"🔧 data_manager добавлен в application.bot_data: {data_manager}")
        logger.debug(f"🔧 Доступные ключи в bot_data: {list(application_instance.bot_data.keys())}")

        common_handlers_instance = CommonHandlers(app_config=app_config, category_manager=category_manager, bot_state=bot_state)
        quiz_manager = QuizManager(
            app_config=app_config, state=bot_state, category_manager=category_manager,
            score_manager=score_manager, data_manager=data_manager, application=application_instance
        )
        rating_handlers = RatingHandlers(app_config=app_config, score_manager=score_manager)
        config_handlers = ConfigHandlers(
            app_config=app_config, data_manager=data_manager,
            category_manager=category_manager, application=application_instance
        )
        poll_answer_handler_instance = CustomPollAnswerHandler(
            app_config=app_config, state=bot_state, score_manager=score_manager,
            data_manager=data_manager, quiz_manager=quiz_manager
        )
        daily_quiz_scheduler = DailyQuizScheduler(
            app_config=app_config, state=bot_state, data_manager=data_manager,
            quiz_manager=quiz_manager, application=application_instance
        )
        if hasattr(config_handlers, 'set_daily_quiz_scheduler'):
            config_handlers.set_daily_quiz_scheduler(daily_quiz_scheduler)

        logger.info("Регистрация обработчиков PTB...")
        application_instance.add_handlers(quiz_manager.get_handlers())
        application_instance.add_handlers(rating_handlers.get_handlers())
        application_instance.add_handlers(common_handlers_instance.get_handlers())
        application_instance.add_handlers(config_handlers.get_handlers())
        application_instance.add_handler(poll_answer_handler_instance.get_handler())

        async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
            logger.error("Исключение при обработке обновления:", exc_info=context.error)
            if isinstance(update, Update) and update.effective_chat:
                error_message_user = escape_markdown_v2(
                    "Произошла внутренняя ошибка. Пожалуйста, сообщите администратору, если проблема повторится."
                )
                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id, text=error_message_user,
                        parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True
                    )
                except Exception as e_send_err_notify:
                    logger.error(f"Не удалось отправить уведомление об ошибке пользователю: {e_send_err_notify}")

        application_instance.add_error_handler(error_handler)
        logger.info("Все обработчики PTB зарегистрированы.")

        bot_commands = [
            BotCommand(app_config.commands.quiz, "🏁 Начать викторину"),
            BotCommand(app_config.commands.top, "🏆 Показать рейтинг"),
            BotCommand(app_config.commands.global_top, "🏆 Показать глобальный рейтинг"),
            BotCommand(app_config.commands.mystats, "📊 Показать вашу статистику"),
            BotCommand(app_config.commands.categories, "📚 Список категорий"),
            BotCommand(app_config.commands.help, "ℹ️ Помощь по командам"),
            BotCommand(app_config.commands.stop_quiz, "🛑 Остановить текущую викторину"),
            BotCommand(app_config.commands.cancel, "↩️ Отменить текущее действие"),
        ]
        admin_cmds = [
            (app_config.commands.admin_settings, "[Админ] ⚙️ Настройки бота"),
            (app_config.commands.add_admin, "[Админ] ➕ Добавить администратора"),
            (app_config.commands.reloadcfg, "[Админ] 🔄 Перезагрузить категории"),
        ]
        for cmd, desc in admin_cmds:
            if cmd: bot_commands.append(BotCommand(cmd, desc))
        try:
            await application_instance.bot.set_my_commands(bot_commands)
            logger.info("Команды бота успешно установлены.")
        except Exception as e_set_cmd:
            logger.error(f"Не удалось установить команды бота: {e_set_cmd}")

        await application_instance.initialize()
        await daily_quiz_scheduler.schedule_all_daily_quizzes_from_startup()

        if application_instance.updater:
            logger.info(f"Запуск бота (polling) с уровнем логирования: {logging.getLevelName(logger.getEffectiveLevel())}")
            await application_instance.updater.start_polling(
                allowed_updates=Update.ALL_TYPES
            )
            await application_instance.start()
            
            # Добавляем data_manager в bot_data после start() (на случай, если bot_data очищается)
            application_instance.bot_data['data_manager'] = data_manager
            logger.debug(f"🔧 data_manager добавлен в bot_data после start(): {data_manager}")
            logger.debug(f"🔧 Доступные ключи в bot_data после start(): {list(application_instance.bot_data.keys())}")
            
            schedule_cleanup_job(application_instance.job_queue, bot_state)
            logger.info("Бот запущен и готов принимать обновления.")
            while application_instance.updater.running:
                await asyncio.sleep(1)
            logger.info("Updater остановлен (внутри main).")
        else:
            logger.error("Updater не был создан. Бот не может быть запущен.")
            return

    except (KeyboardInterrupt, SystemExit):
        logger.info("Программа прервана (KeyboardInterrupt/SystemExit в main).")
    except Exception as e:
        logger.critical(f"Критическая ошибка в функции main: {e}", exc_info=True)
    finally:
        logger.info("Блок finally в main() начал выполнение.")
        if application_instance: # Используем application_instance
            if application_instance.updater and application_instance.updater.running:
                logger.info("Остановка Updater в main().finally...")
                await application_instance.updater.stop()
                logger.info("Updater остановлен в main().finally.")

            # Проверяем, запущен ли диспетчер более безопасным способом
            try:
                if hasattr(application_instance, 'running') and application_instance.running:
                    logger.info("Остановка Application в main().finally...")
                    await application_instance.stop()
                    logger.info("Application остановлен в main().finally.")
            except Exception as e:
                logger.warning(f"Ошибка при остановке Application: {e}")

            logger.info("Запуск Application.shutdown() в main().finally...")
            try:
                await application_instance.shutdown()
                logger.info("Application.shutdown() завершен в main().finally.")
            except Exception as e:
                logger.warning(f"Ошибка при shutdown Application: {e}")
        else:
            logger.warning("Экземпляр Application не был создан, пропуск шагов остановки PTB в main().finally.")

        if data_manager_instance:
            logger.info("Сохранение данных DataManager в main().finally...")
            data_manager_instance.save_all_data()
            logger.info("Данные DataManager сохранены в main().finally.")
        else:
            logger.warning("Экземпляр DataManager не был создан, пропуск сохранения данных в main().finally.")
        logger.info("Блок finally в main() завершил выполнение.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "Event loop is closed" in str(e): # Эта ошибка может возникать, если цикл закрывается где-то еще
            logger.info(f"Цикл событий asyncio уже закрыт: {e}")
        else: # Другие RuntimeErrors
            logger.critical(f"Необработанная RuntimeError на самом верхнем уровне: {e}", exc_info=True)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Программа прервана (KeyboardInterrupt/SystemExit на уровне __main__).")
    finally:
        logger.info("Программа завершена (блок finally в __main__).")

