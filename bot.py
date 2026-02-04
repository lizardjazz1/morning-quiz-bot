#bot.py
import logging
import logging.handlers
import asyncio
import os
import sys
import subprocess
from typing import Optional
from pathlib import Path
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, PicklePersistence, ConversationHandler,
    Defaults, filters
)
from telegram.constants import ParseMode
from telegram.error import BadRequest

# Модули приложения
from app_config import AppConfig
from state import BotState
from data_manager import DataManager
from handlers.poll_answer_handler import CustomPollAnswerHandler
from utils import escape_markdown_v2

# Менеджеры логики
from modules.category_manager import CategoryManager
from modules.score_manager import ScoreManager
from modules.photo_quiz_manager import PhotoQuizManager
from modules.bot_commands_setup import setup_bot_commands
from backup_manager import BackupManager

# Обработчики команд и колбэков
from handlers.quiz_manager import QuizManager
from handlers.rating_handlers import RatingHandlers
from handlers.config_handlers import ConfigHandlers
from handlers.daily_quiz_scheduler import DailyQuizScheduler
from handlers.wisdom_scheduler import WisdomScheduler
from handlers.common_handlers import CommonHandlers
from handlers.cleanup_handler import schedule_cleanup_job
from handlers.backup_handlers import BackupHandlers
from handlers.photo_quiz_handlers import PhotoQuizHandlers
from datetime import timedelta

# Настройка логирования
# Сначала создаем временный уровень для инициализации
TEMP_LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL_MAP = {
    "DEBUG": logging.DEBUG, "INFO": logging.INFO,
    "WARNING": logging.WARNING, "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL
}
TEMP_LOG_LEVEL_DEFAULT = LOG_LEVEL_MAP.get(TEMP_LOG_LEVEL_STR, logging.INFO)

# Создаем папку logs если её нет
logs_dir = Path("logs")
logs_dir.mkdir(exist_ok=True)

# Создаем logger ДО его использования
logger = logging.getLogger(__name__)

# Используем простое имя файла для ежедневной ротации
log_filename = "bot.log"
log_filepath = logs_dir / log_filename

# Выводим информацию о файле лога
logger.info(f"📝 Логи сохраняются в: {log_filepath} (ежедневная ротация, хранение 7 дней)")
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=TEMP_LOG_LEVEL_DEFAULT,
    handlers=[
        logging.handlers.TimedRotatingFileHandler(
            log_filepath,
            when='midnight',         # Ротация в полночь
            interval=1,              # Каждый день
            backupCount=7,           # Хранить последние 7 дней
            encoding='utf-8',
            utc=False                # Использовать локальное время
        ),
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

def check_and_kill_duplicate_bots() -> None:
    """Проверяет и завершает дублирующие процессы бота (кроссплатформенная версия)"""
    try:
        # Получаем текущий PID
        current_pid = os.getpid()
        logger.info(f"Текущий PID бота: {current_pid}")

        # Пытаемся использовать psutil (более надежный кроссплатформенный способ)
        try:
            import psutil
            pids = []
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info.get('cmdline', [])
                    if cmdline and any('bot.py' in str(arg) for arg in cmdline):
                        pid = proc.info['pid']
                        if pid != current_pid:
                            pids.append(str(pid))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if pids:
                logger.warning(f"Найдены дублирующие процессы бота (через psutil): {pids}")
                for pid in pids:
                    try:
                        logger.info(f"Завершение дублирующего процесса: {pid}")
                        proc = psutil.Process(int(pid))
                        proc.terminate()
                        proc.wait(timeout=5)
                        logger.info(f"Процесс {pid} завершен")
                    except psutil.TimeoutExpired:
                        logger.warning(f"Не удалось завершить процесс {pid} за отведенное время, принудительное завершение")
                        try:
                            proc.kill()
                        except:
                            pass
                    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                        logger.warning(f"Не удалось завершить процесс {pid}: {e}")
            else:
                logger.info("Дублирующие процессы бота не найдены (проверка через psutil)")
            return
        except ImportError:
            logger.debug("psutil не установлен, используем системные команды")
        except Exception as e:
            logger.debug(f"Ошибка при использовании psutil: {e}, переходим к системным командам")

        # Fallback: используем системные команды
        pids = []
        is_windows = os.name == 'nt'
        
        if is_windows:
            # Windows: используем tasklist
            try:
                result = subprocess.run(
                    ['tasklist', '/FI', 'IMAGENAME eq python.exe', '/FO', 'CSV', '/NH'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    for line in result.stdout.strip().split('\n'):
                        if line and 'bot.py' in line:
                            # Извлекаем PID из CSV (второе поле)
                            parts = line.split(',')
                            if len(parts) > 1:
                                pid = parts[1].strip('"')
                                if pid and pid != str(current_pid):
                                    pids.append(pid)
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logger.warning(f"Не удалось использовать tasklist: {e}")
        else:
            # Linux/Unix: используем pgrep
            try:
                # Проверяем доступность команды pgrep
                subprocess.run(['which', 'pgrep'], capture_output=True, check=True, timeout=5)
                
                # Ищем все процессы Python, содержащие bot.py
                result = subprocess.run(
                    ['pgrep', '-f', 'python.*bot.py'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                if result.returncode == 0:
                    pids = result.stdout.strip().split('\n')
                    pids = [pid for pid in pids if pid and pid != str(current_pid)]
            except (subprocess.CalledProcessError, FileNotFoundError):
                logger.warning("Команда 'pgrep' недоступна. Пропускаем проверку дублирующих процессов.")
                return

        # Завершаем найденные процессы
        if pids:
            logger.warning(f"Найдены дублирующие процессы бота: {pids}")
            for pid in pids:
                try:
                    logger.info(f"Завершение дублирующего процесса: {pid}")
                    if is_windows:
                        subprocess.run(['taskkill', '/F', '/PID', pid], timeout=5, capture_output=True)
                    else:
                        subprocess.run(['kill', '-TERM', pid], timeout=5)
                        # Ждем завершения процесса
                        import time
                        time.sleep(2)
                    logger.info(f"Процесс {pid} завершен")
                except subprocess.TimeoutExpired:
                    logger.warning(f"Не удалось завершить процесс {pid} за отведенное время")
                except Exception as e:
                    logger.error(f"Ошибка при завершении процесса {pid}: {e}")
        else:
            logger.info("Дублирующие процессы бота не найдены")

    except subprocess.TimeoutExpired:
        logger.warning("Таймаут при проверке дублирующих процессов")
    except Exception as e:
        logger.error(f"Ошибка при проверке дублирующих процессов: {e}")


async def autosave_messages_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Периодическое автосохранение сообщений для удаления"""
    try:
        data_manager = context.bot_data.get('data_manager')
        if data_manager:
            data_manager.save_messages_to_delete()
            logger.info("💾 Периодическое автосохранение сообщений для удаления выполнено")
        else:
            logger.warning("⚠️ data_manager не найден в bot_data для автосохранения")
    except Exception as e:
        logger.error(f"❌ Ошибка периодического автосохранения: {e}")


def schedule_autosave_job(job_queue, data_manager) -> None:
    """Планирует периодическое автосохранение сообщений для удаления"""
    try:
        job_name = "autosave_messages_to_delete"

        # Удаляем старую задачу если есть
        existing_jobs = job_queue.get_jobs_by_name(job_name)
        for job in existing_jobs:
            job.schedule_removal()

        # Создаем новую задачу
        job_queue.run_repeating(
            autosave_messages_callback,
            interval=timedelta(minutes=15),
            first=timedelta(minutes=15),
            name=job_name
        )
        logger.info("📅 Запланировано периодическое автосохранение сообщений (каждые 15 минут)")
    except Exception as e:
        logger.error(f"❌ Ошибка планирования автосохранения: {e}")


async def save_state_on_shutdown(application: Application) -> None:
    """Сохранение состояния при остановке бота"""
    try:
        data_manager = application.bot_data.get('data_manager')
        if data_manager:
            data_manager.save_messages_to_delete()
            logger.info("💾 Сообщения для удаления сохранены при shutdown")
        else:
            logger.warning("⚠️ data_manager не найден в bot_data при shutdown")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения при shutdown: {e}")


async def main() -> None:
    """Main entry point for the Morning Quiz Bot"""
    # Проверяем и завершаем дублирующие процессы бота
    check_and_kill_duplicate_bots()

    logger.info("Запуск бота...")
    
    # Создаем PID файл для мониторинга статуса бота
    pid_file = Path("bot.pid")
    try:
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
        logger.info(f"📝 PID файл создан: {pid_file.absolute()} (PID: {os.getpid()})")
    except Exception as e:
        logger.warning(f"Не удалось создать PID файл: {e}")
    
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
        # Добавляем category_manager в data_manager для доступа при завершении работы
        data_manager.category_manager = category_manager
        score_manager = ScoreManager(app_config=app_config, state=bot_state, data_manager=data_manager)
        
        # Инициализируем PhotoQuizManager
        photo_quiz_manager = PhotoQuizManager(data_manager=data_manager, score_manager=score_manager)
        
        # Инициализируем BackupManager
        backup_manager = BackupManager(project_root=Path.cwd())

        persistence_path = os.path.join(app_config.data_dir, app_config.persistence_file_name)
        persistence = PicklePersistence(filepath=persistence_path)
        defaults = Defaults(parse_mode=ParseMode.MARKDOWN_V2)

        # HTTPXRequest с таймаутами под RU→EU маршруты (СПб → Amsterdam Telegram DC)
        # С 30.12.2025 маршрутизация стала критически медленной для send_poll()
        # send_poll() обработка: +8-15с + Peak нагрузка: +3-7с = нужны 60с таймауты
        from telegram.request import HTTPXRequest
        
        request = HTTPXRequest(
            read_timeout=60.0,       # Восстановлено: критично для send_poll() при RU→EU маршрутизации
            write_timeout=45.0,      # Восстановлено: для больших запросов (polls с опциями)
            connect_timeout=20.0,    # Восстановлено: подключение через VPN/прокси может быть медленным
            pool_timeout=30.0,       # Восстановлено: ожидание свободного соединения из пула
            media_write_timeout=60.0,  # Для отправки медиа файлов (фото-викторины)
            connection_pool_size=8   # Увеличен пул соединений для параллельных запросов (default=1)
        )
        
        application_builder = (
            Application.builder()
            .token(app_config.bot_token)
            .persistence(persistence)
            .defaults(defaults)
            .concurrent_updates(True)
            .request(request)
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

        # Инициализируем WisdomScheduler
        wisdom_scheduler = WisdomScheduler(
            app_config=app_config, data_manager=data_manager, bot_state=bot_state, 
            application=application_instance, category_manager=category_manager
        )
        if hasattr(config_handlers, 'set_wisdom_scheduler'):
            config_handlers.set_wisdom_scheduler(wisdom_scheduler)

        # Инициализируем BackupHandlers
        backup_handlers = BackupHandlers(app_config=app_config, backup_manager=backup_manager)
        
        # Инициализируем PhotoQuizHandlers
        photo_quiz_handlers = PhotoQuizHandlers(photo_quiz_manager=photo_quiz_manager)

        # ===== ПРОВЕРКА РЕЖИМА ТЕХНИЧЕСКОГО ОБСЛУЖИВАНИЯ =====
        if data_manager.is_maintenance_mode():
            logger.info("🔧 Обнаружен режим технического обслуживания. Добавляем обработчики обслуживания.")
            # Добавляем обработчики обслуживания с высоким приоритетом
            maintenance_handlers = common_handlers_instance.get_maintenance_handlers()
            for handler in maintenance_handlers:
                application_instance.add_handler(handler)
            logger.info(f"✅ Добавлено {len(maintenance_handlers)} обработчиков режима обслуживания")
        else:
            logger.info("✅ Режим технического обслуживания не активен")

        logger.debug("Регистрация обработчиков PTB...")
        application_instance.add_handlers(quiz_manager.get_handlers())
        application_instance.add_handlers(rating_handlers.get_handlers())
        application_instance.add_handlers(common_handlers_instance.get_handlers())
        application_instance.add_handlers(config_handlers.get_handlers())
        application_instance.add_handlers(backup_handlers.get_handlers())
        application_instance.add_handler(poll_answer_handler_instance.get_handler())
        
        # Добавляем обработчики фото-викторины
        application_instance.add_handlers(photo_quiz_handlers.get_handlers())

        # ===== ВОССТАНОВЛЕНИЕ АКТИВНЫХ ВИКТОРИН =====
        logger.info("🔄 Восстановление активных викторин после перезапуска...")
        try:
            # Очищаем устаревшие викторины
            data_manager.cleanup_stale_quizzes()

            # Восстанавливаем актуальные викторины
            await quiz_manager.restore_all_active_quizzes()

            # Настраиваем автоматическое сохранение викторин
            quiz_manager.schedule_quiz_auto_save()

            logger.info("✅ Система восстановления викторин инициализирована")

        except Exception as e:
            logger.error(f"❌ Ошибка при инициализации системы восстановления викторин: {e}", exc_info=True)

        # ===== ОЧИСТКА УВЕДОМЛЕНИЙ ОБ ОБСЛУЖИВАНИИ =====
        logger.info("🧹 Проверка необходимости очистки уведомлений об обслуживании...")
        try:
            # Создаем временный контекст для очистки
            temp_context = type('TempContext', (), {
                'bot_data': application_instance.bot_data,
                'application': application_instance
            })()

            await common_handlers_instance.cleanup_maintenance_notifications(temp_context)
            logger.info("✅ Проверка очистки уведомлений об обслуживании завершена")

        except Exception as e:
            logger.error(f"❌ Ошибка при очистке уведомлений об обслуживании: {e}", exc_info=True)

        async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
            logger.error("Исключение при обработке обновления:", exc_info=context.error)
            if isinstance(update, Update) and update.effective_chat:
                error_message_user = escape_markdown_v2(
                    "Произошла внутренняя ошибка. Пожалуйста, сообщите разработчику, если проблема повторится."
                )
                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id, text=error_message_user,
                        parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True
                    )
                except Exception as e_send_err_notify:
                    logger.error(f"Не удалось отправить уведомление об ошибке пользователю: {e_send_err_notify}")

        application_instance.add_error_handler(error_handler)
        logger.debug("Все обработчики PTB зарегистрированы.")

        application_instance.bot_data['daily_quiz_scheduler'] = daily_quiz_scheduler
        logger.info("Планировщик ежедневных викторин добавлен в bot_data")

        application_instance.bot_data['wisdom_scheduler'] = wisdom_scheduler
        logger.info("Планировщик мудрости дня добавлен в bot_data")

        # Устанавливаем команды бота ДО запуска (правильный порядок для python-telegram-bot 21.7 и Telegram Bot API 9.2)
        await setup_bot_commands(application_instance, app_config)

        # Инициализируем Application перед запуском (требуется для python-telegram-bot 21.7)
        await application_instance.initialize()
        
        # Запускаем планировщики после инициализации
        await daily_quiz_scheduler.schedule_all_daily_quizzes_from_startup()
        wisdom_scheduler.schedule_all_wisdoms_from_startup()
        wisdom_scheduler.start()

        if application_instance.updater:
            logger.info(f"Запуск бота (polling) с уровнем логирования: {logging.getLevelName(logger.getEffectiveLevel())}")
            await application_instance.updater.start_polling(
                allowed_updates=Update.ALL_TYPES,
                poll_interval=1.0,  # 1 секунда между запросами (снижает нагрузку на CPU)
                timeout=30,  # Long polling таймаут (30 секунд)
                drop_pending_updates=False  # Не пропускаем накопленные обновления
            )
            await application_instance.start()
            
            # Добавляем data_manager в bot_data после start() (на случай, если bot_data очищается)
            application_instance.bot_data['data_manager'] = data_manager
            logger.debug(f"🔧 data_manager добавлен в bot_data после start(): {data_manager}")
            logger.debug(f"🔧 Доступные ключи в bot_data после start(): {list(application_instance.bot_data.keys())}")
            
            schedule_cleanup_job(application_instance.job_queue, bot_state)
            schedule_autosave_job(application_instance.job_queue, data_manager)
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

        # Сохраняем состояние перед остановкой
        if application_instance:
            await save_state_on_shutdown(application_instance)

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

            # Останавливаем планировщик мудрости дня
            if 'wisdom_scheduler' in application_instance.bot_data:
                try:
                    wisdom_scheduler = application_instance.bot_data['wisdom_scheduler']
                    wisdom_scheduler.shutdown()
                    logger.info("✅ Планировщик мудрости дня остановлен")
                except Exception as e:
                    logger.warning(f"❌ Ошибка при остановке планировщика мудрости дня: {e}")
        else:
            logger.warning("Экземпляр Application не был создан, пропуск шагов остановки PTB в main().finally.")

        if data_manager_instance:
            # Сохраняем активные викторины перед завершением работы
            logger.info("💾 Сохранение активных викторин перед завершением...")
            try:
                if hasattr(data_manager_instance, 'save_active_quizzes'):
                    data_manager_instance.save_active_quizzes()
                    logger.info("✅ Активные викторины сохранены перед завершением")
                else:
                    logger.warning("Метод save_active_quizzes не найден в data_manager")
            except Exception as e:
                logger.warning(f"❌ Ошибка при сохранении активных викторин: {e}")

            # Включаем режим обслуживания при остановке бота
            logger.info("🔧 Включение режима обслуживания при остановке бота...")
            try:
                if hasattr(data_manager_instance, 'enable_maintenance_mode'):
                    data_manager_instance.enable_maintenance_mode("Остановка бота")
                    logger.info("✅ Режим обслуживания включен при остановке бота")
                else:
                    logger.warning("Метод enable_maintenance_mode не найден в data_manager")
            except Exception as e:
                logger.warning(f"❌ Ошибка при включении режима обслуживания: {e}")

            logger.info("Сохранение данных DataManager в main().finally...")
            data_manager_instance.save_all_data()
            logger.info("Данные DataManager сохранены в main().finally.")
            
            # Сохраняем статистику категорий
            try:
                if hasattr(data_manager_instance, 'category_manager'):
                    logger.info("Сохранение статистики категорий в main().finally...")
                    data_manager_instance.category_manager.force_save_all_stats()
                    logger.info("Статистика категорий сохранена в main().finally.")
                else:
                    logger.debug("category_manager не доступен в data_manager")
            except Exception as e:
                logger.warning(f"Не удалось сохранить статистику категорий: {e}")
        else:
            logger.warning("Экземпляр DataManager не был создан, пропуск сохранения данных в main().finally.")
        
        # Удаляем PID файл при завершении
        pid_file = Path("bot.pid")
        try:
            if pid_file.exists():
                pid_file.unlink()
                logger.info(f"🗑️ PID файл удален: {pid_file.absolute()}")
        except Exception as e:
            logger.warning(f"Не удалось удалить PID файл: {e}")
        
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


