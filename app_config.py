import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv

CURRENT_FILE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_FILE_DIR

dotenv_path = PROJECT_ROOT / '.env'
load_dotenv(dotenv_path=dotenv_path)

logger = logging.getLogger(__name__)

class CommandConfig:
    def __init__(self, commands_data: Dict[str, str]):
        self.start: str = commands_data.get("start", "start")
        self.help: str = commands_data.get("help", "help")
        self.quiz: str = commands_data.get("quiz", "quiz")
        self.categories: str = commands_data.get("categories", "categories")
        self.top: str = commands_data.get("top", "top")
        self.global_top: str = commands_data.get("globaltop", "globaltop")
        self.mystats: str = commands_data.get("mystats", "mystats")
        self.stop_quiz: str = commands_data.get("stopquiz", "stopquiz")
        self.cancel: str = commands_data.get("cancel", "cancel")
        self.admin_settings: str = commands_data.get("admin_settings", "adminsettings")
        self.view_chat_config: str = commands_data.get("view_chat_config", "viewchatconfig")

class PathConfig:
    def __init__(self, project_root_path: Path, data_dir_name: str = "data", config_dir_name: str = "config"):
        self.project_root: Path = project_root_path
        self.data_dir: Path = self.project_root / data_dir_name
        self.config_dir: Path = self.project_root / config_dir_name

        self.questions_file: Path = self.data_dir / "questions.json"
        self.malformed_questions_file: Path = self.data_dir / "malformed_questions.json"
        self.users_file: Path = self.data_dir / "users.json"
        self.chat_settings_file: Path = self.data_dir / "chat_settings.json"
        self.old_daily_quiz_subscriptions_file: Path = self.data_dir / "daily_quiz_subscriptions.json"

        self.quiz_config_file: Path = self.config_dir / "quiz_config.json"
        self.ptb_persistence_file: Path = self.data_dir / "ptb_persistence.pickle"

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)

class AppConfig:
    def __init__(self):
        self.bot_token: Optional[str] = os.getenv("BOT_TOKEN")
        self.log_level_str: str = os.getenv("LOG_LEVEL", "INFO").upper()

        self.paths = PathConfig(PROJECT_ROOT)

        self._raw_quiz_config: Dict[str, Any] = self._load_json_config(self.paths.quiz_config_file)

        self.default_chat_settings: Dict[str, Any] = self._raw_quiz_config.get("default_chat_settings", {})
        self.quiz_types_config: Dict[str, Any] = self._raw_quiz_config.get("quiz_types_config", {})
        self.global_settings: Dict[str, Any] = self._raw_quiz_config.get("global_settings", {})

        self.commands = CommandConfig(self.global_settings.get("commands", {}))

        self.max_questions_per_session: int = self.global_settings.get("max_questions_per_session", 50)
        self.max_interactive_categories_to_show: int = self.global_settings.get("max_interactive_categories_to_show", 10)
        self.job_grace_period_seconds: int = self.global_settings.get("job_grace_period_seconds", 3)
        self.max_poll_question_length: int = self.global_settings.get("max_poll_question_length", 280)
        self.max_poll_option_length: int = self.global_settings.get("max_poll_option_length", 90)

        self.rating_display_limit: int = self.global_settings.get("rating_display_limit", 10)

        self.parsed_motivational_messages: Dict[int, str] = self._parse_motivational_messages(
            self.global_settings.get("motivational_messages", {})
        )

        _daily_type_cfg = self.quiz_types_config.get("daily", {})
        _daily_chat_defaults_from_config = self.default_chat_settings.get("daily_quiz", {})

        self.daily_quiz_defaults: Dict[str, Any] = {
            "hour_msk": _daily_chat_defaults_from_config.get("hour_msk", _daily_type_cfg.get("default_hour_msk", 7)),
            "minute_msk": _daily_chat_defaults_from_config.get("minute_msk", _daily_type_cfg.get("default_minute_msk", 0)),
            "num_questions": _daily_chat_defaults_from_config.get("num_questions", _daily_type_cfg.get("default_num_questions", 10)),
            "categories_mode": _daily_chat_defaults_from_config.get("categories_mode", _daily_type_cfg.get("default_categories_mode", "random")),
            "num_random_categories": _daily_chat_defaults_from_config.get("num_random_categories", _daily_type_cfg.get("default_num_random_categories", 3)),
            "specific_categories": _daily_chat_defaults_from_config.get("specific_categories", _daily_type_cfg.get("default_specific_categories", [])),
            "open_period_seconds": _daily_chat_defaults_from_config.get("poll_open_seconds", _daily_type_cfg.get("default_open_period_seconds", 600)),
            "interval_seconds": _daily_chat_defaults_from_config.get("interval_seconds", _daily_type_cfg.get("default_interval_seconds", 60)),
            "enabled": _daily_chat_defaults_from_config.get("enabled", _daily_type_cfg.get("enabled", False)) # Ensure 'enabled' has a default
        }
        self.daily_quiz_questions_count_default = self.daily_quiz_defaults["num_questions"]

        if not self.bot_token:
            logger.critical("Токен BOT_TOKEN не найден! Пожалуйста, проверьте ваш .env файл.")

    def _load_json_config(self, file_path: Path) -> Dict[str, Any]:
        default_config_structure = {
            "default_chat_settings": {
                "default_quiz_type": "session",
                "default_num_questions": 10,
                "default_open_period_seconds": 30,
                "default_announce_quiz": False,
                "default_announce_delay_seconds": 30,
                "enabled_categories": None,
                "disabled_categories": [],
                "daily_quiz": {
                    "enabled": False, "hour_msk": 7, "minute_msk": 0, "categories_mode": "random",
                    "num_random_categories": 3, "specific_categories": [], "num_questions": 10,
                    "interval_seconds": 60, "poll_open_seconds": 600
                }
            },
            "quiz_types_config": {
                "single": {"type": "single", "mode": "single_question", "default_num_questions": 1, "default_open_period_seconds": 30, "announce": False, "announce_delay_seconds": 0},
                "session": {"type": "session", "mode": "serial_immediate", "default_num_questions": 10, "default_open_period_seconds": 30, "announce": False, "announce_delay_seconds": 30},
                "daily": {"type": "daily", "mode": "serial_interval", "default_num_questions": 10, "default_open_period_seconds": 600, "default_interval_seconds": 60, "announce": True, "announce_delay_seconds": 0, "default_categories_mode": "random", "default_num_random_categories": 3, "default_specific_categories": []}
            },
            "global_settings": {
                "commands": {"start": "start", "help": "help", "quiz": "quiz", "categories": "categories", "top": "top", "global_top": "globaltop", "mystats": "mystats", "stop_quiz": "stopquiz", "cancel": "cancel", "admin_settings": "adminsettings", "view_chat_config": "viewchatconfig"},
                "max_questions_per_session": 50, "max_interactive_categories_to_show": 10,
                "job_grace_period_seconds": 3, "max_poll_question_length": 280, "max_poll_option_length": 90,
                "motivational_messages": {}
            }
        }
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            for key, default_value_template in default_config_structure.items():
                if key not in config_data:
                    config_data[key] = default_value_template
                    logger.warning(f"В {file_path} отсутствует ключ '{key}'. Используется значение по умолчанию.")
                elif not isinstance(config_data[key], type(default_value_template)):
                    logger.warning(f"В {file_path} ключ '{key}' имеет неверный тип (ожидается {type(default_value_template)}, получено {type(config_data[key])}). Используется значение по умолчанию.")
                    config_data[key] = default_value_template
                elif isinstance(default_value_template, dict): # Проверка вложенных ключей
                    for sub_key, sub_default_value in default_value_template.items():
                        if sub_key not in config_data[key]:
                             config_data[key][sub_key] = sub_default_value
                             logger.warning(f"В {file_path} в секции '{key}' отсутствует ключ '{sub_key}'. Используется значение по умолчанию.")
                        elif not isinstance(config_data[key][sub_key], type(sub_default_value)) and sub_default_value is not None : # Allow None to be overridden
                             logger.warning(f"В {file_path} ключ '{key}.{sub_key}' имеет неверный тип (ожидается {type(sub_default_value)}, получено {type(config_data[key][sub_key])}). Используется значение по умолчанию.")
                             config_data[key][sub_key] = sub_default_value
                        elif isinstance(sub_default_value, dict): # Проверка еще одного уровня вложенности (например, daily_quiz)
                            for ssub_key, ssub_default_value in sub_default_value.items():
                                if ssub_key not in config_data[key][sub_key]:
                                    config_data[key][sub_key][ssub_key] = ssub_default_value
                                    logger.warning(f"В {file_path} в секции '{key}.{sub_key}' отсутствует ключ '{ssub_key}'. Используется значение по умолчанию.")
                                elif not isinstance(config_data[key][sub_key][ssub_key], type(ssub_default_value)):
                                    logger.warning(f"В {file_path} ключ '{key}.{sub_key}.{ssub_key}' имеет неверный тип. Используется значение по умолчанию.")
                                    config_data[key][sub_key][ssub_key] = ssub_default_value
            return config_data
        except FileNotFoundError:
            logger.error(f"{file_path} не найден! Будет использована структура по умолчанию.")
        except json.JSONDecodeError:
            logger.error(f"Ошибка декодирования JSON в {file_path}! Будет использована структура по умолчанию.")
        except Exception as e:
            logger.error(f"Непредвиденная ошибка загрузки {file_path}: {e}. Будет использована структура по умолчанию.")
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
