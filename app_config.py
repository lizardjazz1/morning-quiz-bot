#app_config.py
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from modules.logger_config import get_logger

logger = get_logger(__name__)
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
        self.chatcategories: str = commands_data.get("chatcategories", "chatcategories")
        self.stop_quiz: str = commands_data.get("stopquiz", "stopquiz")
        self.cancel: str = commands_data.get("cancel", "cancel")

        # Имена команд для администрирования
        self.admin_settings: str = commands_data.get("admin_settings", "adminsettings") # Новая команда для ConversationHandler настроек

        self.adddailyquiz: str = commands_data.get("adddailyquiz", "adddailyquiz")
        self.removedailyquiz: str = commands_data.get("removedailyquiz", "removedailyquiz")
        self.listdailyquizzes: str = commands_data.get("listdailyquizzes", "listdailyquizzes")
        self.reloadcfg: str = commands_data.get("reloadcfg", "reloadcfg")
        self.reset_categories_stats: str = commands_data.get("reset_categories_stats", "reset_categories_stats")
        self.chat_stats: str = commands_data.get("chat_stats", "chat_stats")
        self.category_stats: str = commands_data.get("category_stats", "category_stats")
        self.daily_wisdom: str = commands_data.get("daily_wisdom", "dailywisdom")
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
        self.messages_to_delete_file: Path = self.data_dir / "messages_to_delete.json"

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

        # Получаем режим работы из переменной окружения
        mode = os.getenv("MODE", "production").lower()
        self.debug_mode: bool = mode == "testing"
        
        # Автоматически определяем уровень логирования на основе режима
        if mode == "testing":
            self.log_level_str: str = "DEBUG"
            logger.debug("🔧 Режим TESTING: установлен уровень логирования DEBUG")
        else:
            self.log_level_str: str = "INFO"
            logger.debug("🔧 Режим PRODUCTION: установлен уровень логирования INFO")
        
        logger.debug(f"AppConfig: MODE считан: {mode} (debug_mode={self.debug_mode}, log_level={self.log_level_str})")

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

        # ===== НАСТРОЙКИ ОПТИМИЗАЦИИ CPU USAGE =====
        # Минимальный интервал между сохранениями данных (секунды)
        self.data_save_throttle_seconds: int = self.global_settings.get("data_save_throttle_seconds", 30)

        # Максимальное количество одновременных I/O операций
        self.max_concurrent_io_operations: int = self.global_settings.get("max_concurrent_io_operations", 5)

        # Интервал очистки кэшей (секунды)
        self.cache_cleanup_interval_seconds: int = self.global_settings.get("cache_cleanup_interval_seconds", 300)

        # Размер LRU кэша для markdown
        self.markdown_cache_size: int = self.global_settings.get("markdown_cache_size", 1000)

        # Rate limiting для API вызовов (запросов в минуту)
        self.api_rate_limit_per_minute: int = self.global_settings.get("api_rate_limit_per_minute", 30)

        logger.debug("AppConfig: Глобальные параметры и оптимизации CPU установлены.")

        self.parsed_chat_achievements: Dict[int, str] = self._parse_achievement_messages(
            self.global_settings.get("chat_achievements", {})
        )
        logger.debug("AppConfig: Чатовые ачивки обработаны.")
        
        # Streak ачивки теперь загружаются из data/system/streak_achievements.json
        self.parsed_streak_achievements: Dict[int, str] = {}
        logger.debug("AppConfig: Streak ачивки пропущены (загружаются из отдельного файла).")

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
        
        # Контакт поддержки
        self.support_contact: str = self.global_settings.get("support_contact", "@Ilzrd")

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
                "num_categories_per_quiz": 3, # ИЗМЕНЕНИЕ: Количество категорий для обычных викторин
                "quiz_categories_mode": "all", # НОВОЕ: Режим выбора категорий для /quiz
                "quiz_categories_pool": [], # НОВОЕ: Пул категорий для /quiz
                # НОВОЕ: Настройки для /quiz команды
                "quiz_settings": {
                    "default_categories_mode": "all",  # all, random, specific
                    "default_num_random_categories": 3,
                    "default_specific_categories": [],
                    "default_interval_seconds": 30,
                    "default_open_period_seconds": 30,
                    "default_announce_quiz": False,
                    "default_announce_delay_seconds": 5
                },
                "daily_quiz": {
                    "enabled": False, "times_msk": [{"hour": 7, "minute": 0}], "categories_mode": "random",
                    "num_random_categories": 3, "specific_categories": [], "num_questions": 10,
                    "interval_seconds": 60, "poll_open_seconds": 600
                }
            },
            "quiz_types_config": {
                "single": {"type": "single", "mode": "single_question", "default_num_questions": 1, "default_open_period_seconds": 30, "announce": False, "announce_delay_seconds": 0},
                "session": {"type": "session", "mode": "serial_immediate", "default_num_questions": 10, "default_open_period_seconds": 30, "default_interval_seconds": 30, "announce": False, "announce_delay_seconds": 30},
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
                    "chatcategories": "chatcategories", "config": "config", "admin_settings": "adminsettings",
                    "view_chat_config": "viewchatconfig", "adddailyquiz": "adddailyquiz", "removedailyquiz": "removedailyquiz",
                    "listdailyquizzes": "listdailyquizzes", "reloadcfg": "reloadcfg",
                    "reset_categories_stats": "reset_categories_stats", "chat_stats": "chat_stats", "category_stats": "category_stats",
                    "daily_wisdom": "dailywisdom"
                },
                "max_questions_per_session": 50, "max_interactive_categories_to_show": 10,
                "job_grace_period_seconds": 3, "max_poll_question_length": 280,
                "max_poll_option_length": 90, "rating_display_limit": 10,
                "max_daily_quiz_times_per_chat": 5,
                "chat_achievements": {
                    "-100": "💀 {user_name}, ты блин издеваешься, такое не возможно вообще! Попробуй не вытворять больше!",
                    "-50": "😵 {user_name}, ну и нуб, прям с порога падает... Поправься уже!",
                    "-25": "⚰️ {user_name}, это уже эпично... {user_score} очков. Нужен герой!",
                    "-20": "🤦‍♂️ {user_name}, опять промах? Кажется, тебе пора на тренировку.",
                    "-10": "🙃 {user_name}, ну ничего, даже у профессионалов бывают плохие дни... правда?",
                    "-5": "😔 {user_name}, не везет... У тебя {user_score} очков. Не сдавайся!",
                    "0": "😐 {user_name}, нейтральная территория. {user_score} очков. Время действовать!",
                    "15": "🎯 {user_name} первый шаг! 15 очков — начало пути!",
                    "30": "🔥 {user_name} разогревается и зажигает чат! 30 очков!",
                    "50": "🌟 {user_name} - легенда чата! {user_score} очков!",
                    "75": "⚡ {user_name} повышает уровень — 75 очков в кармане!",
                    "100": "💎 {user_name} - бриллиант чата! {user_score} очков!",
                    "150": "🏅 {user_name} уверенно входит в топ — 150 очков!",
                    "250": "💎 Ого ого! {user_name} набрал {user_score} очков!",
                    "300": "💎 {user_name} набрал 300 очков! Ты настоящий алмаз в нашем сообществе!",
                    "350": "🪐 {user_name} полёт на орбиту знаний — 350 очков!",
                    "500": "🏆 {user_name} набрал 500 очков! Настоящий чемпион!",
                    "600": "👑 {user_name} новый БОСС викторины! 600 очков — вершина земного уровня!",
                    "750": "🌈 {user_name} набрал 750 очков! Дал дал ушёл!",
                    "800": "🌈 {user_name} переступает грань возможного — 800 очков!",
                    "1000": "✨ {user_name} набрал 1000 очков! Ты легенда!",
                    "1200": "✨ {user_name} — легенда вне понимания! 1200 очков!",
                    "1500": "🔥 {user_name} набрал 1500 очков! Огонь неистощимой энергии!",
                    "1700": "🌋🔥 {user_name} взрывается, как суперновая звезда! 1700 очков!",
                    "2000": "🚀 {user_name} набрал 2000 очков! Сверхзвездный уровень!",
                    "2200": "🌀 {user_name} достиг(ла) вихря космического сознания! 2200 очков!",
                    "2500": "⚔️ {user_name} набрал 2500 очков! Персонаж мифов и легенд!",
                    "2700": "⚔️ {user_name} теперь персонаж мифов и легенд! 2700 очков!",
                    "3000": "👑 {user_name} набрал 3000 очков! Царь и бог знаний!",
                    "3200": "👾 {user_name} властвует над мультивселенной знаний! 3200 очков!",
                    "3500": "🌌 {user_name} набрал 3500 очков! Космический уровень!",
                    "3700": "🌌⚡ {user_name} разрывает пространство и время! 3700 очков!",
                    "4000": "🌟 {user_name} набрал 4000 очков! Звездный уровень!",
                    "4200": "⛩️ {user_name} вошёл(ла) в ранг божества всезнания! 4200 очков!",
                    "4500": "💫 {user_name} набрал 4500 очков! Божественный уровень!",
                    "4700": "🧬 {user_name} переписал(а) ДНК самой викторины! 4700 очков!",
                    "5000": "💥 {user_name} набрал 5000 очков! Э-э-это ты создатель вселенной?!",
                    "5200": "💀🚫 ВСЁ, {user_name} СЛОМАЛ(А) СИСТЕМУ! 5200 очков!",
                    "5500": "🌌 {user_name} набрал 5500 очков! За пределами понимания!",
                    "6000": "💎✨ {user_name} достиг абсолютного совершенства! 6000 очков! Конец игры!",
                    "5": "🎯 {user_name} начинает свой путь в этом чате! {user_score} очков!",
                    "10": "🔥 {user_name} разогревается! {user_score} очков в чате!",
                    "25": "👑 {user_name} - король этого чата! {user_score} очков!"
                },
                # УДАЛЕНО: Streak ачивки теперь загружаются из data/system/streak_achievements.json
                # НОВОЕ: Настройки бонусов за серию
                "streak_bonuses": {
                    "enabled": True,
                    "base_multiplier": 0.2,
                    "max_multiplier": 3.0,
                    "min_streak_for_bonus": 5
                },
                # Контакт поддержки
                "support_contact": "@Ilzrd"
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

    def _parse_achievement_messages(self, messages_config: Dict[str, str]) -> Dict[int, str]:
        logger.debug("AppConfig._parse_achievement_messages начат.")
        parsed_messages: Dict[int, str] = {}
        if not isinstance(messages_config, dict):
            logger.warning("AppConfig._parse_achievement_messages: Конфигурация 'chat_achievements' не является словарем.")
            return {}
        for k_str, v_str in messages_config.items():
            try:
                parsed_messages[int(k_str)] = str(v_str)
            except ValueError:
                logger.warning(f"AppConfig._parse_achievement_messages: Не удалось конвертировать ключ '{k_str}' в int.")
        logger.debug(f"AppConfig._parse_achievement_messages завершен. Обработано {len(parsed_messages)} сообщений.")
        return parsed_messages

logger.debug("Модуль app_config.py завершил загрузку.")
