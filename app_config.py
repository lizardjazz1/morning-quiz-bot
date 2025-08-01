#app_config.py
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)
logger.debug("Модуль app_config.py начал загружаться.")

try:
    from dotenv import load_dotenv
    PYTHON_DOTENV_AVAILABLE = True
    logger.debug("Модуль dotenv успешно импортирован.")
except ImportError:
    PYTHON_DOTENV_AVAILABLE = False
    logger.warning("Модуль python-dotenv не найден. Переменные окружения из .env файла не будут загружены.")
    def load_dotenv(dotenv_path=None, verbose=False, override=False, interpolate=True, encoding="utf-8"):
        logger.debug("Вызвана заглушка load_dotenv (python-dotenv не установлен).")
        pass

CURRENT_FILE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_FILE_DIR # Предполагается, что app_config.py в корне проекта
logger.debug(f"app_config.py: CURRENT_FILE_DIR = {CURRENT_FILE_DIR}")
logger.debug(f"app_config.py: PROJECT_ROOT = {PROJECT_ROOT}")

dotenv_path = PROJECT_ROOT / '.env'
logger.debug(f"app_config.py: Путь к .env файлу: {dotenv_path}")

if PYTHON_DOTENV_AVAILABLE:
    logger.debug("app_config.py: Попытка загрузить переменные из .env...")
    try:
        load_dotenv(dotenv_path=dotenv_path, verbose=True)
        logger.debug("app_config.py: load_dotenv() выполнен.")
    except Exception as e_dotenv:
        logger.error(f"app_config.py: Ошибка при вызове load_dotenv: {e_dotenv}", exc_info=True)
else:
    logger.debug("app_config.py: Пропуск load_dotenv, так как модуль python-dotenv не доступен.")

class CommandConfig:
    def __init__(self, commands_data: Dict[str, str]):
        logger.debug("CommandConfig.__init__ начат.")
        self.start: str = commands_data.get("start", "start")
        self.help: str = commands_data.get("help", "help")
        self.quiz: str = commands_data.get("quiz", "quiz")
        self.categories: str = commands_data.get("categories", "categories")
        self.top: str = commands_data.get("top", "top")
        self.global_top: str = commands_data.get("globaltop", "globaltop")
        self.mystats: str = commands_data.get("mystats", "mystats")
        self.stop_quiz: str = commands_data.get("stopquiz", "stopquiz")
        self.cancel: str = commands_data.get("cancel", "cancel")

        # Имена команд для администрирования
        self.config: str = commands_data.get("config", "config") # Старая команда config, оставлена для совместимости, если где-то используется
        self.admin_settings: str = commands_data.get("admin_settings", "adminsettings") # Новая команда для ConversationHandler настроек
        self.view_chat_config: str = commands_data.get("view_chat_config", "viewchatconfig") # Для просмотра конфига чата

        self.adddailyquiz: str = commands_data.get("adddailyquiz", "adddailyquiz")
        self.removedailyquiz: str = commands_data.get("removedailyquiz", "removedailyquiz")
        self.listdailyquizzes: str = commands_data.get("listdailyquizzes", "listdailyquizzes")
        self.reloadcfg: str = commands_data.get("reloadcfg", "reloadcfg")
        logger.debug("CommandConfig.__init__ завершен.")

class PathConfig:
    def __init__(self, project_root_path: Path, data_dir_name: str = "data", config_dir_name: str = "config"):
        logger.debug(f"PathConfig.__init__ начат. project_root_path: {project_root_path}")
        self.project_root: Path = project_root_path

        logger.debug(f"PathConfig: Попытка определить data_dir ({data_dir_name})...")
        self.data_dir: Path = self.project_root / data_dir_name
        logger.debug(f"PathConfig: data_dir = {self.data_dir}")

        logger.debug(f"PathConfig: Попытка определить config_dir ({config_dir_name})...")
        self.config_dir: Path = self.project_root / config_dir_name
        logger.debug(f"PathConfig: config_dir = {self.config_dir}")

        self.questions_file: Path = self.data_dir / "questions.json"
        self.malformed_questions_file: Path = self.data_dir / "malformed_questions.json"
        self.users_file: Path = self.data_dir / "users.json"
        self.chat_settings_file: Path = self.data_dir / "chat_settings.json"
        self.old_daily_quiz_subscriptions_file: Path = self.data_dir / "daily_quiz_subscriptions.json"

        self.quiz_config_file: Path = self.config_dir / "quiz_config.json"
        self.persistence_file_name: str = "ptb_persistence.pickle"

        logger.debug(f"PathConfig: Пути к файлам определены: questions={self.questions_file}, config={self.quiz_config_file}")

        try:
            logger.debug(f"PathConfig: Попытка создать директорию данных: {self.data_dir}")
            self.data_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"PathConfig: Директория данных {self.data_dir} проверена/создана.")
        except Exception as e:
            logger.error(f"PathConfig: Ошибка при создании/проверке директории данных {self.data_dir}: {e}", exc_info=True)

        try:
            logger.debug(f"PathConfig: Попытка создать директорию конфигурации: {self.config_dir}")
            self.config_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"PathConfig: Директория конфигурации {self.config_dir} проверена/создана.")
        except Exception as e:
            logger.error(f"PathConfig: Ошибка при создании/проверке директории конфигурации {self.config_dir}: {e}", exc_info=True)

        logger.debug("PathConfig.__init__ завершен.")

class AppConfig:
    def __init__(self):
        logger.debug("AppConfig.__init__ НАЧАТ.")

        self.bot_token: Optional[str] = os.getenv("BOT_TOKEN")
        logger.debug(f"AppConfig: BOT_TOKEN считан: {'Да' if self.bot_token else 'Нет'}")

        self.log_level_str: str = os.getenv("LOG_LEVEL", "INFO").upper()
        logger.debug(f"AppConfig: LOG_LEVEL считан: {self.log_level_str}")

        self.debug_mode: bool = os.getenv("DEBUG_MODE", "False").lower() == "true"
        logger.debug(f"AppConfig: DEBUG_MODE считан: {self.debug_mode}")

        logger.debug("AppConfig: Инициализация PathConfig...")
        self.paths = PathConfig(PROJECT_ROOT)
        logger.debug("AppConfig: PathConfig инициализирован.")

        logger.debug(f"AppConfig: Загрузка основного конфигурационного файла: {self.paths.quiz_config_file}")
        self._raw_quiz_config: Dict[str, Any] = self._load_json_config(self.paths.quiz_config_file)
        logger.debug("AppConfig: Основной конфигурационный файл загружен и обработан.")

        self.default_chat_settings: Dict[str, Any] = self._raw_quiz_config.get("default_chat_settings", {})
        self.quiz_types_config: Dict[str, Any] = self._raw_quiz_config.get("quiz_types_config", {})
        self.global_settings: Dict[str, Any] = self._raw_quiz_config.get("global_settings", {})
        logger.debug("AppConfig: Основные секции конфигурации извлечены.")

        self.commands = CommandConfig(self.global_settings.get("commands", {}))
        logger.debug("AppConfig: CommandConfig инициализирован.")

        self.max_questions_per_session: int = self.global_settings.get("max_questions_per_session", 50)
        self.max_interactive_categories_to_show: int = self.global_settings.get("max_interactive_categories_to_show", 10)
        self.job_grace_period_seconds: int = self.global_settings.get("job_grace_period_seconds", 3)
        self.max_poll_question_length: int = self.global_settings.get("max_poll_question_length", 280)
        self.max_poll_option_length: int = self.global_settings.get("max_poll_option_length", 90)
        self.rating_display_limit: int = self.global_settings.get("rating_display_limit", 10)
        self.max_daily_quiz_times_per_chat: int = self.global_settings.get("max_daily_quiz_times_per_chat", 5)
        logger.debug("AppConfig: Глобальные параметры установлены.")

        self.parsed_motivational_messages: Dict[int, str] = self._parse_motivational_messages(
            self.global_settings.get("motivational_messages", {})
        )
        logger.debug("AppConfig: Мотивационные сообщения обработаны.")

        _daily_type_cfg = self.quiz_types_config.get("daily", {})
        _daily_chat_defaults_from_config = self.default_chat_settings.get("daily_quiz", {})
        default_daily_times_msk = [{"hour": 7, "minute": 0}]

        self.daily_quiz_defaults: Dict[str, Any] = {
            "enabled": _daily_chat_defaults_from_config.get("enabled", _daily_type_cfg.get("enabled", False)),
            "times_msk": _daily_chat_defaults_from_config.get("times_msk", _daily_type_cfg.get("default_times_msk", default_daily_times_msk)),
            "categories_mode": _daily_chat_defaults_from_config.get("categories_mode", _daily_type_cfg.get("default_categories_mode", "random")),
            "num_random_categories": _daily_chat_defaults_from_config.get("num_random_categories", _daily_type_cfg.get("default_num_random_categories", 3)),
            "specific_categories": _daily_chat_defaults_from_config.get("specific_categories", _daily_type_cfg.get("default_specific_categories", [])),
            "num_questions": _daily_chat_defaults_from_config.get("num_questions", _daily_type_cfg.get("default_num_questions", 10)),
            "poll_open_seconds": _daily_chat_defaults_from_config.get("poll_open_seconds", _daily_type_cfg.get("default_open_period_seconds", 600)),
            "interval_seconds": _daily_chat_defaults_from_config.get("interval_seconds", _daily_type_cfg.get("default_interval_seconds", 60)),
        }
        logger.debug("AppConfig: daily_quiz_defaults установлены.")

        self.data_dir: Path = self.paths.data_dir
        self.persistence_file_name: str = self.paths.persistence_file_name

        if not self.bot_token:
            logger.critical("AppConfig: Токен BOT_TOKEN не найден! Проверьте .env файл.")

        logger.info("AppConfig.__init__ ЗАВЕРШЕН.")

    def _load_json_config(self, file_path: Path) -> Dict[str, Any]:
        logger.debug(f"AppConfig._load_json_config: Попытка загрузить JSON из {file_path}")
        default_config_structure = {
            "default_chat_settings": {
                "default_quiz_type": "session", "default_num_questions": 10, "default_open_period_seconds": 30,
                "default_announce_quiz": False, "default_announce_delay_seconds": 30,
                "enabled_categories": None, "disabled_categories": [],
                "auto_delete_bot_messages": True, # ИЗМЕНЕНИЕ: Добавлена новая настройка
                "daily_quiz": {
                    "enabled": False, "times_msk": [{"hour": 7, "minute": 0}], "categories_mode": "random",
                    "num_random_categories": 3, "specific_categories": [], "num_questions": 10,
                    "interval_seconds": 60, "poll_open_seconds": 600
                }
            },
            "quiz_types_config": {
                "single": {"type": "single", "mode": "single_question", "default_num_questions": 1, "default_open_period_seconds": 30, "announce": False, "announce_delay_seconds": 0},
                "session": {"type": "session", "mode": "serial_immediate", "default_num_questions": 10, "default_open_period_seconds": 30, "announce": False, "announce_delay_seconds": 30},
                "daily": {
                    "type": "daily", "mode": "serial_interval", "default_num_questions": 10,
                    "default_open_period_seconds": 600, "default_interval_seconds": 60, "announce": True,
                    "announce_delay_seconds": 0, "default_times_msk": [{"hour": 7, "minute": 0}],
                    "default_categories_mode": "random", "default_num_random_categories": 3,
                    "default_specific_categories": [], "enabled": False
                }
            },
            "global_settings": {
                "commands": {
                    "start": "start", "help": "help", "quiz": "quiz", "categories": "categories", "top": "top",
                    "global_top": "globaltop", "mystats": "mystats", "stop_quiz": "stopquiz", "cancel": "cancel",
                    "config": "config", "admin_settings": "adminsettings", "view_chat_config": "viewchatconfig",
                    "adddailyquiz": "adddailyquiz", "removedailyquiz": "removedailyquiz",
                    "listdailyquizzes": "listdailyquizzes", "reloadcfg": "reloadcfg"
                },
                "max_questions_per_session": 50, "max_interactive_categories_to_show": 10,
                "job_grace_period_seconds": 3, "max_poll_question_length": 280,
                "max_poll_option_length": 90, "rating_display_limit": 10,
                "max_daily_quiz_times_per_chat": 5,
                "motivational_messages": {"10": "Отличный старт, {user_name}! У тебя уже {user_score} очков!", "-5": "{user_name}, не везет... У тебя {user_score} очков. Не сдавайся!"}
            }
        }
        try:
            if not file_path.exists():
                logger.warning(f"AppConfig._load_json_config: Файл {file_path} не найден! Создаю его с дефолтной структурой.")
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(default_config_structure, f, ensure_ascii=False, indent=4)
                logger.info(f"AppConfig._load_json_config: Дефолтный файл {file_path} создан.")
                return default_config_structure

            with open(file_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            logger.debug(f"AppConfig._load_json_config: JSON успешно загружен из {file_path}")

            changed_during_merge = False
            for key, default_value_section in default_config_structure.items():
                if key not in config_data:
                    config_data[key] = default_value_section
                    logger.warning(f"AppConfig._load_json_config: В {file_path} отсутствует ключ верхнего уровня '{key}'. Используется значение по умолчанию.")
                    changed_during_merge = True
                elif isinstance(default_value_section, dict):
                    for sub_key, default_sub_value in default_value_section.items():
                        if sub_key not in config_data[key]: # type: ignore
                             config_data[key][sub_key] = default_sub_value # type: ignore
                             logger.warning(f"AppConfig._load_json_config: В {file_path} в секции '{key}' отсутствует ключ '{sub_key}'. Используется значение по умолчанию.")
                             changed_during_merge = True
                        elif isinstance(default_sub_value, dict) and isinstance(config_data[key].get(sub_key), dict): # type: ignore
                            for ssub_key, default_ssub_value in default_sub_value.items():
                                if ssub_key not in config_data[key][sub_key]: # type: ignore
                                    config_data[key][sub_key][ssub_key] = default_ssub_value # type: ignore
                                    logger.warning(f"AppConfig._load_json_config: В {file_path} в секции '{key}.{sub_key}' отсутствует ключ '{ssub_key}'. Используется значение по умолчанию.")
                                    changed_during_merge = True

            if changed_during_merge:
                logger.info(f"AppConfig._load_json_config: Конфигурация в {file_path} была дополнена недостающими ключами. Рекомендуется проверить файл.")
                try:
                    with open(file_path, 'w', encoding='utf-8') as f_rewrite:
                        json.dump(config_data, f_rewrite, ensure_ascii=False, indent=4)
                    logger.info(f"AppConfig._load_json_config: Файл {file_path} обновлен с дополненными ключами.")
                except Exception as e_rewrite:
                    logger.error(f"AppConfig._load_json_config: Не удалось перезаписать {file_path} с дополненными ключами: {e_rewrite}")
            return config_data

        except json.JSONDecodeError as e_json:
            logger.error(f"AppConfig._load_json_config: Ошибка декодирования JSON в {file_path}: {e_json}! Будет использована структура по умолчанию.")
        except Exception as e:
            logger.error(f"AppConfig._load_json_config: Непредвиденная ошибка загрузки {file_path}: {e}. Будет использована структура по умолчанию.", exc_info=True)

        logger.warning("AppConfig._load_json_config: Возвращается дефолтная структура конфигурации.")
        return default_config_structure

    def _parse_motivational_messages(self, messages_config: Dict[str, str]) -> Dict[int, str]:
        logger.debug("AppConfig._parse_motivational_messages начат.")
        parsed_messages: Dict[int, str] = {}
        if not isinstance(messages_config, dict):
            logger.warning("AppConfig._parse_motivational_messages: Конфигурация 'motivational_messages' не является словарем.")
            return {}
        for k_str, v_str in messages_config.items():
            try:
                parsed_messages[int(k_str)] = str(v_str)
            except ValueError:
                logger.warning(f"AppConfig._parse_motivational_messages: Не удалось конвертировать ключ '{k_str}' в int.")
        logger.debug(f"AppConfig._parse_motivational_messages завершен. Обработано {len(parsed_messages)} сообщений.")
        return parsed_messages

logger.debug("Модуль app_config.py завершил загрузку.")
