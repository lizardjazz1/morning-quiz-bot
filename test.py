# bot/app_config.py
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv

# Определяем базовый путь к директории 'bot'
BASE_DIR = Path(__file__).resolve().parent # bot/
PROJECT_ROOT = BASE_DIR.parent # Корень проекта, на уровень выше bot/

# Загрузка переменных окружения из .env файла в корне проекта
dotenv_path = PROJECT_ROOT / '.env'
load_dotenv(dotenv_path=dotenv_path)

logger = logging.getLogger(__name__)

class CommandConfig:
    """Класс для хранения имен команд."""
    def __init__(self, commands_data: Dict[str, str]):
        # Команды для пользователя
        self.start: str = commands_data.get("start", "start")
        self.help: str = commands_data.get("help", "help")
        self.quiz: str = commands_data.get("quiz", "quiz")
        self.categories: str = commands_data.get("categories", "categories")
        self.top: str = commands_data.get("top", "top") # Общий рейтинг в чате
        self.global_top: str = commands_data.get("globaltop", "globaltop") # Глобальный топ
        self.mystats: str = commands_data.get("mystats", "mystats") # Статистика пользователя

        # Команды управления викториной
        self.stop_quiz: str = commands_data.get("stopquiz", "stopquiz")
        self.cancel: str = commands_data.get("cancel", "cancel") # Для отмены ConversationHandler

        # Команды конфигурации чата (админские)
        self.set_quiz_type: str = commands_data.get("set_quiz_type", "setquiztype")
        self.set_quiz_questions: str = commands_data.get("set_quiz_questions", "setquizquestions")
        self.set_quiz_open_period: str = commands_data.get("set_quiz_open_period", "setquizopenperiod")
        self.enable_category: str = commands_data.get("enable_category", "enablecategory")
        self.disable_category: str = commands_data.get("disable_category", "disablecategory")
        self.reset_chat_config: str = commands_data.get("reset_chat_config", "resetchatconfig")
        self.view_chat_config: str = commands_data.get("view_chat_config", "viewchatconfig")

        # Команды ежедневной викторины (админские)
        self.subscribe_daily_quiz: str = commands_data.get("subscribe_daily_quiz", "subdaily")
        self.unsubscribe_daily_quiz: str = commands_data.get("unsubscribe_daily_quiz", "unsubdaily")
        self.set_daily_quiz_time: str = commands_data.get("set_daily_quiz_time", "setdailytime")
        self.set_daily_quiz_categories: str = commands_data.get("set_daily_quiz_categories", "setdailycats")
        self.set_daily_quiz_num_questions: str = commands_data.get("set_daily_quiz_num_questions", "setdailynumq")
        self.view_daily_quiz_config: str = commands_data.get("view_daily_quiz_config", "viewdailyconfig")


class PathConfig:
    """Класс для хранения путей к файлам и директориям."""
    def __init__(self, base_dir: Path, data_dir_name: str = "data", config_dir_name: str = "config"):
        self.base_dir: Path = base_dir
        self.data_dir: Path = base_dir / data_dir_name
        self.config_dir: Path = base_dir / config_dir_name

        # Файлы данных
        self.questions_file: Path = self.data_dir / "questions.json"
        self.malformed_questions_file: Path = self.data_dir / "malformed_questions.json"
        self.users_file: Path = self.data_dir / "users.json"
        self.chat_settings_file: Path = self.data_dir / "chat_settings.json"
        self.old_daily_quiz_subscriptions_file: Path = self.data_dir / "daily_quiz_subscriptions.json" # Для миграции

        # Файлы конфигурации
        self.quiz_config_file: Path = self.config_dir / "quiz_config.json"

        # Файл для PTB Persistence
        self.ptb_persistence_file: Path = self.data_dir / "ptb_persistence.pickle"

        # Создание директорий, если они не существуют
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)


class AppConfig:
    def __init__(self):
        self.bot_token: Optional[str] = os.getenv("BOT_TOKEN")
        self.log_level_str: str = os.getenv("LOG_LEVEL", "INFO").upper()

        self.paths = PathConfig(BASE_DIR)
        self._raw_quiz_config: Dict[str, Any] = self._load_json_config(self.paths.quiz_config_file)

        # Настройки из quiz_config.json
        self.default_chat_settings: Dict[str, Any] = self._raw_quiz_config.get("default_chat_settings", {})
        self.quiz_types_config: Dict[str, Any] = self._raw_quiz_config.get("quiz_types_config", {})
        self.global_settings: Dict[str, Any] = self._raw_quiz_config.get("global_settings", {})

        # Имена команд (из global_settings.commands или значения по умолчанию)
        self.commands = CommandConfig(self.global_settings.get("commands", {}))

        # Глобальные параметры викторин
        self.max_questions_per_session: int = self.global_settings.get("max_questions_per_session", 50)
        self.max_interactive_categories_to_show: int = self.global_settings.get("max_interactive_categories_to_show", 10)
        self.default_announce_delay_seconds: int = self.global_settings.get("default_announce_delay_seconds", 30)
        self.job_grace_period_seconds: int = self.global_settings.get("job_grace_period_seconds", 3)
        self.max_poll_question_length: int = self.global_settings.get("max_poll_question_length", 300) # Для Telegram Poll
        self.max_poll_option_length: int = self.global_settings.get("max_poll_option_length", 100) # Для Telegram Poll

        # Мотивационные сообщения (ключи уже должны быть int после парсинга)
        self.parsed_motivational_messages: Dict[int, str] = self._parse_motivational_messages(
            self.global_settings.get("motivational_messages", {})
        )

        # Настройки для ежедневной викторины (глобальные значения по умолчанию)
        self.daily_quiz_default_hour_msk: int = self.global_settings.get("daily_quiz_settings", {}).get("default_hour_msk", 7)
        self.daily_quiz_default_minute_msk: int = self.global_settings.get("daily_quiz_settings", {}).get("default_minute_msk", 0)
        self.daily_quiz_default_num_questions: int = self.global_settings.get("daily_quiz_settings", {}).get("default_num_questions", 10)
        self.daily_quiz_default_categories_mode: str = self.global_settings.get("daily_quiz_settings", {}).get("default_categories_mode", "random") # "random" или "all"
        self.daily_quiz_default_num_random_categories: int = self.global_settings.get("daily_quiz_settings", {}).get("default_num_random_categories", 3)
        self.daily_quiz_default_open_period_seconds: int = self.global_settings.get("daily_quiz_settings", {}).get("default_open_period_seconds", 600)
        self.daily_quiz_default_interval_seconds: int = self.global_settings.get("daily_quiz_settings", {}).get("default_interval_seconds", 60)

        # Проверка токена
        if not self.bot_token:
            logger.critical("Токен BOT_TOKEN не найден! Пожалуйста, проверьте ваш .env файл.")
            # В реальном приложении здесь можно было бы вызвать sys.exit(1)

        # Уровень логирования (устанавливается в bot.py, здесь только информационно)
        logger.info(f"AppConfig: Уровень логирования из .env: {self.log_level_str}")

    def _load_json_config(self, file_path: Path) -> Dict[str, Any]:
        default_config_structure = {
            "default_chat_settings": {},
            "quiz_types_config": {},
            "global_settings": {"commands": {}, "motivational_messages": {}, "daily_quiz_settings": {}}
        }
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                # Проверим наличие основных ключей
                for key in default_config_structure:
                    if key not in config_data:
                        config_data[key] = default_config_structure[key]
                        logger.warning(f"В {file_path} отсутствует ключ '{key}'. Используется значение по умолчанию.")
                    elif isinstance(default_config_structure[key], dict): # Для вложенных словарей
                        for sub_key in default_config_structure[key]:
                             if sub_key not in config_data[key]:
                                 config_data[key][sub_key] = default_config_structure[key][sub_key]
                return config_data
        except FileNotFoundError:
            logger.error(f"{file_path} не найден! Используется структура по умолчанию.")
        except json.JSONDecodeError:
            logger.error(f"Ошибка декодирования JSON в {file_path}! Используется структура по умолчанию.")
        except Exception as e:
            logger.error(f"Непредвиденная ошибка загрузки {file_path}: {e}. Используется структура по умолчанию.")
        return default_config_structure

    def _parse_motivational_messages(self, messages_config: Dict[str, str]) -> Dict[int, str]:
        parsed_messages: Dict[int, str] = {}
        if not isinstance(messages_config, dict):
            logger.warning("Конфигурация 'motivational_messages' не является словарем.")
            return {}
        for k_str, v_str in messages_config.items():
            try:
                parsed_messages[int(k_str)] = str(v_str)
            except ValueError:
                logger.warning(f"Не удалось конвертировать ключ '{k_str}' в int для motivational_messages.")
        return parsed_messages

    def get_raw_quiz_config(self) -> Dict[str, Any]:
        """Возвращает весь загруженный словарь из quiz_config.json."""
        return self._raw_quiz_config

