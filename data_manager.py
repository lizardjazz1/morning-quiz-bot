#data_manager.py
import json
import os
import copy
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Set, Optional, TYPE_CHECKING
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import aiofiles
from modules.logger_config import get_logger

if TYPE_CHECKING:
    from app_config import AppConfig
    from state import BotState

logger = get_logger(__name__)

class DataManager:
    """
    Правильный DataManager для Telegram Bot API
    Работает с консолидированными данными в data/ и интегрируется с PTB persistence
    """
    
    def __init__(self, app_config: 'AppConfig', state: 'BotState'):
        # Логируем только при ошибках инициализации
        self.app_config = app_config
        self.paths_config = app_config.paths
        self.state = state
        
        # Структура папок для консолидированных данных
        self.data_dir = Path("data")
        self.chats_dir = self.data_dir / "chats"
        self.global_dir = self.data_dir / "global"
        self.statistics_dir = self.data_dir / "statistics"
        self.system_dir = self.data_dir / "system"
        self.questions_dir = self.data_dir / "questions"

        # Дополнительные директории для будущих модулей
        self.images_dir = self.data_dir / "images"  # Для хранения изображений квизов
        self.media_dir = self.data_dir / "media"    # Для медиафайлов
        
        # Создаем папки, если их нет
        self._ensure_directories()
        
        # Паттерн для символов, которые могут вызвать проблемы в Telegram
        self._problematic_chars_pattern = re.compile(r'[_\*\\[\\]\\(\\)\~\\`\\>\\#\\+\\-\=\\|\\{\\}\\.\\!]')
        # Инициализация завершена без ошибок

    # ===== ВНУТРЕННИЕ ХЕЛПЕРЫ =====

    def _default_maintenance_status(self) -> Dict[str, Any]:
        """Возвращает структуру по умолчанию для файла maintenance_status.json"""
        return {
            "maintenance_mode": False,
            "reason": "Техническое обслуживание",
            "start_time": None,
            "chats_notified": [],
            "notification_messages": []
        }

    def _write_json_file(self, file_path: Path, data: Dict[str, Any]) -> bool:
        """Синхронная запись JSON файла с созданием директорий"""
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Ошибка записи JSON в {file_path}: {e}", exc_info=True)
            return False

    def _load_and_sanitize_maintenance_status(self, maintenance_file: Path) -> Dict[str, Any]:
        """
        Загружает maintenance_status.json, устраняя ошибки формата
        и автоматически восстанавливая структуру при повреждении файла.
        """
        default_status = self._default_maintenance_status()

        if not maintenance_file.exists():
            return default_status

        try:
            with open(maintenance_file, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
        except json.JSONDecodeError as e:
            logger.warning(
                f"Файл обслуживания {maintenance_file} поврежден (JSONDecodeError: {e}). "
                "Будет восстановлена структура по умолчанию."
            )
            self._write_json_file(maintenance_file, default_status)
            return default_status
        except Exception as e:
            logger.error(f"Ошибка чтения {maintenance_file}: {e}", exc_info=True)
            return default_status

        if not isinstance(raw_data, dict):
            logger.warning(
                f"Некорректный тип данных в {maintenance_file}: ожидается dict, получено {type(raw_data)}. "
                "Файл будет перезаписан."
            )
            self._write_json_file(maintenance_file, default_status)
            return default_status

        sanitized_status = self._default_maintenance_status()

        sanitized_status["maintenance_mode"] = bool(raw_data.get("maintenance_mode", False))
        sanitized_status["reason"] = str(raw_data.get("reason", sanitized_status["reason"]))
        sanitized_status["start_time"] = raw_data.get("start_time")

        chats_notified = raw_data.get("chats_notified", [])
        if isinstance(chats_notified, list):
            sanitized_status["chats_notified"] = [int(chat_id) for chat_id in chats_notified if chat_id is not None]

        notification_messages = raw_data.get("notification_messages", [])
        if isinstance(notification_messages, list):
            clean_notifications = []
            for msg in notification_messages:
                if isinstance(msg, dict):
                    chat_id = msg.get("chat_id")
                    message_id = msg.get("message_id")
                    timestamp = msg.get("timestamp")
                    if chat_id is not None and message_id is not None:
                        clean_notifications.append({
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "timestamp": timestamp
                        })
            sanitized_status["notification_messages"] = clean_notifications

        # Если данные были скорректированы, перезаписываем файл
        if sanitized_status != raw_data:
            self._write_json_file(maintenance_file, sanitized_status)

        return sanitized_status

    def _ensure_directories(self):
        """Создает необходимые директории"""
        directories = [
            self.chats_dir, self.global_dir, self.statistics_dir,
            self.system_dir, self.questions_dir, self.images_dir, self.media_dir
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Директория {directory} проверена/создана")

    # ===== АСИНХРОННЫЕ МЕТОДЫ ДЛЯ РАБОТЫ С ФАЙЛАМИ =====

    async def _read_json_async(self, file_path: Path) -> Dict[str, Any]:
        """Асинхронное чтение JSON файла"""
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        except FileNotFoundError:
            logger.debug(f"Файл {file_path} не найден, возвращаем пустой словарь")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON в файле {file_path}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Ошибка чтения файла {file_path}: {e}")
            return {}

    async def _write_json_async(self, file_path: Path, data: Dict[str, Any]) -> bool:
        """Асинхронная запись JSON файла"""
        try:
            # Создаем директорию, если она не существует
            file_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
            return True
        except Exception as e:
            logger.error(f"Ошибка записи файла {file_path}: {e}")
            return False

    async def _read_file_async(self, file_path: Path) -> str:
        """Асинхронное чтение текстового файла"""
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                return await f.read()
        except FileNotFoundError:
            logger.debug(f"Файл {file_path} не найден")
            return ""
        except Exception as e:
            logger.error(f"Ошибка чтения файла {file_path}: {e}")
            return ""

    async def _write_file_async(self, file_path: Path, content: str) -> bool:
        """Асинхронная запись текстового файла"""
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(content)
            return True
        except Exception as e:
            logger.error(f"Ошибка записи файла {file_path}: {e}")
            return False

    async def _run_in_executor(self, func, *args, **kwargs):
        """Выполняет синхронную функцию в executor'е"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args, **kwargs)

    # ===== МЕТОДЫ ДЛЯ РАБОТЫ С ИЗОБРАЖЕНИЯМИ (ГОТОВИМСЯ К БУДУЩЕМУ МОДУЛЮ) =====

    async def _download_image_async(self, url: str, filename: str) -> Optional[Path]:
        """
        Асинхронно скачивает изображение по URL
        Возвращает путь к сохраненному файлу или None при ошибке
        """
        try:
            import aiohttp

            image_path = self.images_dir / filename
            image_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        async with aiofiles.open(image_path, 'wb') as f:
                            await f.write(await response.read())
                        logger.debug(f"Изображение скачано: {image_path}")
                        return image_path
                    else:
                        logger.error(f"Ошибка скачивания изображения: HTTP {response.status}")
                        return None
        except ImportError:
            logger.warning("aiohttp не установлен, используем requests")
            return await self._download_image_sync_async(url, filename)
        except Exception as e:
            logger.error(f"Ошибка скачивания изображения {url}: {e}")
            return None

    async def _download_image_sync_async(self, url: str, filename: str) -> Optional[Path]:
        """Синхронная загрузка изображения в executor'е"""
        def download_sync():
            try:
                import requests
                from pathlib import Path

                image_path = Path("data/images") / filename
                image_path.parent.mkdir(parents=True, exist_ok=True)

                response = requests.get(url, timeout=30)
                if response.status_code == 200:
                    with open(image_path, 'wb') as f:
                        f.write(response.content)
                    return image_path
                return None
            except Exception as e:
                logger.error(f"Ошибка синхронной загрузки: {e}")
                return None

        return await self._run_in_executor(download_sync)

    async def save_image_metadata_async(self, image_id: str, metadata: Dict[str, Any]) -> bool:
        """
        Асинхронно сохраняет метаданные изображения
        """
        metadata_file = self.images_dir / f"{image_id}_metadata.json"
        return await self._write_json_async(metadata_file, metadata)

    async def load_image_metadata_async(self, image_id: str) -> Dict[str, Any]:
        """
        Асинхронно загружает метаданные изображения
        """
        metadata_file = self.images_dir / f"{image_id}_metadata.json"
        return await self._read_json_async(metadata_file)

    def _sanitize_text_for_telegram(self, text: str) -> str:
        """Sanitizes text to prevent Telegram API errors in plain text fields."""
        if not isinstance(text, str):
            return ""
        sanitized_text = text.replace('(', '(').replace(')', ')')
        return sanitized_text

    def _convert_sets_to_lists_recursively(self, obj: Any) -> Any:
        """Конвертирует множества в списки для JSON сериализации"""
        if isinstance(obj, dict):
            return {k: self._convert_sets_to_lists_recursively(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._convert_sets_to_lists_recursively(elem) for elem in obj]
        if isinstance(obj, set):
            return sorted([str(item) for item in obj])
        return obj

    def _convert_user_scores_lists_to_sets(self, scores_data: Dict[str, Any]) -> Dict[str, Any]:
        """Конвертирует списки в множества при загрузке данных"""
        if not isinstance(scores_data, dict): 
            return scores_data
        
        # ОПТИМИЗАЦИЯ: Ограничиваем количество обрабатываемых чатов
        max_chats_to_process = 100
        processed_chats = 0
        
        for chat_id_str, users_in_chat in scores_data.items():
            if processed_chats >= max_chats_to_process:
                logger.warning(f"Достигнут лимит обрабатываемых чатов ({max_chats_to_process}), пропускаем остальные")
                break
                
            if isinstance(users_in_chat, dict):
                # ОПТИМИЗАЦИЯ: Ограничиваем количество пользователей в чате
                max_users_per_chat = 100
                processed_users = 0
                
                for user_id_str, user_data_val in list(users_in_chat.items()):
                    if processed_users >= max_users_per_chat:
                        logger.warning(f"Чат {chat_id_str}: достигнут лимит пользователей ({max_users_per_chat}), пропускаем остальных")
                        break
                        
                    if isinstance(user_data_val, dict):
                        # Поля, которые должны быть типа set
                        answered_polls_list = user_data_val.get('answered_polls', [])
                        user_data_val['answered_polls'] = set(answered_polls_list) if isinstance(answered_polls_list, list) else set()

                        milestones_list = user_data_val.get('milestones_achieved', [])
                        user_data_val['milestones_achieved'] = set(milestones_list) if isinstance(milestones_list, list) else set()

                        # Основные поля для обратной совместимости
                        if 'name' not in user_data_val:
                            user_data_val['name'] = f"Player {user_id_str}"
                        if 'score' not in user_data_val:
                            user_data_val['score'] = 0
                        if 'first_answer_time' not in user_data_val:
                            user_data_val['first_answer_time'] = None
                        if 'last_answer_time' not in user_data_val:
                            user_data_val['last_answer_time'] = None
                            
                        processed_users += 1
                        
                processed_chats += 1
        
        return scores_data

    def load_questions(self) -> None:
        """Загружает вопросы из консолидированной структуры (по категориям)"""
        logger.debug("Загрузка вопросов из консолидированной структуры...")
        processed_questions_count = 0
        valid_categories_count = 0
        malformed_entries: List[Dict[str, Any]] = []
        temp_quiz_data: Dict[str, List[Dict[str, Any]]] = {}
        
        try:
            # Загружаем вопросы из каждой категории
            for category_file in self.questions_dir.glob("*.json"):
                category_name = category_file.stem
                try:
                    with open(category_file, 'r', encoding='utf-8') as f:
                        questions_list = json.load(f)
                    
                    if isinstance(questions_list, list):
                        valid_questions = []
                        for i, question in enumerate(questions_list):
                            if isinstance(question, dict) and 'question' in question:
                                # Создаем поле correct_option_text из correct для совместимости
                                if 'correct' in question and 'correct_option_text' not in question:
                                    question['correct_option_text'] = question['correct']
                                # Добавляем поле категории для корректного обновления статистики
                                question['original_category'] = category_name
                                valid_questions.append(question)
                            else:
                                malformed_entries.append({
                                    "error_type": "invalid_question",
                                    "category": category_name,
                                    "data": question
                                })
                        
                        if valid_questions:
                            temp_quiz_data[category_name] = valid_questions
                            processed_questions_count += len(valid_questions)
                            valid_categories_count += 1
                            logger.debug(f"Категория '{category_name}': {len(valid_questions)} вопросов")
                        else:
                            logger.warning(f"Категория '{category_name}' не содержит валидных вопросов")
                    else:
                        logger.error(f"Файл категории {category_name} должен содержать список вопросов")
                        malformed_entries.append({
                            "error_type": "category_not_list",
                            "category": category_name,
                            "data": questions_list
                        })
                        
                except Exception as e:
                    logger.error(f"Ошибка загрузки категории {category_name}: {e}")
                    malformed_entries.append({
                        "error_type": "load_error",
                        "category": category_name,
                        "error": str(e)
                    })
            
            # Сохраняем малформированные вопросы
            if malformed_entries:
                self._save_malformed_questions(malformed_entries)
            
            self.state.quiz_data = temp_quiz_data
            logger.info(f"Вопросы загружены: {valid_categories_count} категорий, {processed_questions_count} вопросов")
            
            # Автоматически обновляем global/categories.json
            self._update_categories_file(temp_quiz_data)
            
        except Exception as e:
            logger.error(f"Критическая ошибка при загрузке вопросов: {e}", exc_info=True)

    def _save_malformed_questions(self, malformed_entries: List[Dict[str, Any]]) -> None:
        """Сохраняет малформированные вопросы и пытается их исправить"""
        try:
            malformed_file = self.system_dir / "malformed_questions.json"
            
            # Загружаем существующие проблемные записи
            existing_malformed = []
            if malformed_file.exists():
                try:
                    with open(malformed_file, 'r', encoding='utf-8') as f:
                        existing_malformed = json.load(f)
                except Exception:
                    existing_malformed = []
            
            # Объединяем с новыми проблемами
            all_malformed = existing_malformed + malformed_entries
            
            # Убираем дубликаты
            unique_malformed = []
            seen_categories = set()
            for entry in all_malformed:
                category = entry.get("category")
                if category not in seen_categories:
                    unique_malformed.append(entry)
                    seen_categories.add(category)
            
            # Сохраняем обновленный список
            with open(malformed_file, 'w', encoding='utf-8') as f:
                json.dump(unique_malformed, f, ensure_ascii=False, indent=2)
            
            logger.warning(f"Сохранено {len(unique_malformed)} малформированных записей в {malformed_file}")
            
            # Отправляем уведомление разработчику о новых проблемах
            self._notify_developer_about_malformed(unique_malformed)
            
            # Пытаемся автоматически исправить некоторые проблемы
            self._try_auto_fix_malformed_files(unique_malformed)
            
        except Exception as e:
            logger.error(f"Ошибка сохранения малформированных вопросов: {e}")
            # Уведомляем об ошибке сохранения
            self._notify_developer_about_error("save_malformed_error", str(e), "Сохранение малформированных вопросов")

    def _try_auto_fix_malformed_files(self, malformed_entries: List[Dict[str, Any]]) -> None:
        """Пытается автоматически исправить некоторые проблемы с файлами"""
        fixed_count = 0
        fixed_categories = []
        
        for entry in malformed_entries:
            category = entry.get("category")
            error_type = entry.get("error_type")
            
            if error_type == "load_error":
                category_file = self.questions_dir / f"{category}.json"
                if category_file.exists():
                    try:
                        # Читаем содержимое файла
                        with open(category_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        # Убираем лишние пробелы и переносы строк в конце
                        cleaned_content = content.rstrip()
                        
                        # Проверяем, что после очистки файл валиден
                        json.loads(cleaned_content)
                        
                        # Сохраняем исправленный файл
                        with open(category_file, 'w', encoding='utf-8') as f:
                            f.write(cleaned_content)
                        
                        logger.info(f"Автоматически исправлен файл {category}")
                        fixed_count += 1
                        fixed_categories.append(category)
                        
                    except Exception as e:
                        logger.debug(f"Не удалось автоматически исправить {category}: {e}")
        
        if fixed_count > 0:
            logger.info(f"Автоматически исправлено {fixed_count} файлов")
            # Уведомляем разработчика об успешном исправлении
            self._notify_developer_about_auto_fix(fixed_categories)
            # Очищаем список исправленных файлов
            self._cleanup_fixed_malformed_files(fixed_categories)

    def _cleanup_fixed_malformed_files(self, fixed_categories: List[str]) -> None:
        """Очищает список исправленных файлов из malformed_questions.json"""
        try:
            malformed_file = self.system_dir / "malformed_questions.json"
            if not malformed_file.exists():
                return
            
            with open(malformed_file, 'r', encoding='utf-8') as f:
                malformed_entries = json.load(f)
            
            # Убираем исправленные категории
            original_count = len(malformed_entries)
            malformed_entries = [entry for entry in malformed_entries 
                               if entry.get("category") not in fixed_categories]
            
            if len(malformed_entries) < original_count:
                # Сохраняем обновленный список
                with open(malformed_file, 'w', encoding='utf-8') as f:
                    json.dump(malformed_entries, f, ensure_ascii=False, indent=2)
                
                logger.info(f"Очищен список проблемных файлов: {original_count - len(malformed_entries)} исправленных файлов удалено")
        
        except Exception as e:
            logger.error(f"Ошибка очистки списка проблемных файлов: {e}")

    def _update_categories_file(self, quiz_data: Dict[str, List[Dict[str, Any]]]) -> None:
        """Автоматически обновляет global/categories.json на основе загруженных вопросов"""
        try:
            import hashlib
            
            categories_file = self.global_dir / "categories.json"
            current_categories = {}
            
            # Загружаем существующие категории, если файл есть
            if categories_file.exists():
                try:
                    with open(categories_file, 'r', encoding='utf-8') as f:
                        current_categories = json.load(f)
                except Exception as e:
                    logger.warning(f"Не удалось загрузить существующий categories.json: {e}")
            
            updated_count = 0
            added_count = 0
            
            # Обновляем информацию о каждой категории
            for category_name, questions in quiz_data.items():
                category_file = self.questions_dir / f"{category_name}.json"
                
                if category_file.exists():
                    # Вычисляем новую информацию о категории
                    file_size = category_file.stat().st_size
                    question_count = len(questions)
                    
                    # Создаем checksum на основе содержимого файла
                    with open(category_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        checksum = hashlib.md5(content.encode('utf-8')).hexdigest()
                    
                    new_category_info = {
                        "question_count": question_count,
                        "file_path": f"questions/{category_name}.json",
                        "last_updated": None,
                        "file_size": file_size,
                        "checksum": checksum
                    }
                    
                    # Проверяем, нужно ли обновить категорию
                    if (category_name not in current_categories or
                        current_categories[category_name].get("question_count") != question_count or
                        current_categories[category_name].get("file_size") != file_size or
                        current_categories[category_name].get("checksum") != checksum):
                        
                        current_categories[category_name] = new_category_info
                        if category_name in current_categories:
                            updated_count += 1
                            logger.debug(f"Категория '{category_name}' обновлена")
                        else:
                            added_count += 1
                            logger.debug(f"Категория '{category_name}' добавлена")
            
            # Сохраняем обновленный файл
            with open(categories_file, 'w', encoding='utf-8') as f:
                json.dump(current_categories, f, ensure_ascii=False, indent=2)
            
            if updated_count > 0 or added_count > 0:
                logger.info(f"categories.json обновлен: {added_count} добавлено, {updated_count} обновлено")
            
        except Exception as e:
            logger.error(f"Ошибка обновления categories.json: {e}", exc_info=True)

    def _get_default_chat_settings(self) -> Dict[str, Any]:
        """Возвращает настройки по умолчанию для чата"""
        return {
            "default_quiz_type": "session",
            "default_num_questions": 10,
            "default_open_period_seconds": 30,
            "default_announce_quiz": False,
            "default_announce_delay_seconds": 30,
            "enabled_categories": None,
            "disabled_categories": [],
            "num_categories_per_quiz": 3,
            "daily_quiz": {
                "enabled": True,
                "times_msk": [
                    {
                        "hour": 8,
                        "minute": 0
                    },
                    {
                        "hour": 12,
                        "minute": 0
                    }
                ],
                "categories_mode": "random",
                "num_random_categories": 3,
                "specific_categories": [],
                "num_questions": 10,
                "interval_seconds": 60,
                "poll_open_seconds": 600
            },
            "auto_delete_bot_messages": True
        }

    def _update_chats_index(self, chat_ids: List[int]) -> None:
        """Обновляет chats_index.json, чтобы отразить, что у всех чатов есть настройки"""
        try:
            chats_index_file = self.global_dir / "chats_index.json"
            if not chats_index_file.exists():
                logger.warning("Файл chats_index.json не найден")
                return
            
            with open(chats_index_file, 'r', encoding='utf-8') as f:
                chats_index = json.load(f)
            
            updated_count = 0
            
            # Обновляем статус has_settings для всех чатов
            for chat_id in chat_ids:
                chat_id_str = str(chat_id)
                if chat_id_str in chats_index:
                    if not chats_index[chat_id_str].get("has_settings", False):
                        chats_index[chat_id_str]["has_settings"] = True
                        updated_count += 1
                        logger.debug(f"Обновлен статус has_settings для чата {chat_id}")
            
            # Сохраняем обновленный файл
            if updated_count > 0:
                with open(chats_index_file, 'w', encoding='utf-8') as f:
                    json.dump(chats_index, f, ensure_ascii=False, indent=2)
                logger.info(f"chats_index.json обновлен: {updated_count} чатов")
            
        except Exception as e:
            logger.error(f"Ошибка обновления chats_index.json: {e}", exc_info=True)

    def load_user_data(self) -> None:
        """
        Загружает данные пользователей из консолидированной структуры data/
        Правильно интегрируется с Telegram Bot API persistence system
        """
        logger.debug("Загрузка данных пользователей из консолидированной структуры...")
        loaded_scores: Dict[int, Dict[str, Any]] = {}
        
        try:
            # Загружаем данные из каждого чата
            for chat_dir in self.chats_dir.iterdir():
                if chat_dir.is_dir():
                    chat_id_str = chat_dir.name
                    try:
                        chat_id = int(chat_id_str)
                        loaded_scores[chat_id] = {}
                        
                        # Загружаем users.json (основной источник данных)
                        users_file = chat_dir / "users.json"
                        if users_file.exists():
                            try:
                                with open(users_file, 'r', encoding='utf-8') as f:
                                    chat_users = json.load(f)
                                if isinstance(chat_users, dict):
                                    for user_id_str, user_data in chat_users.items():
                                        user_data_copy = user_data.copy()
                                        # Конвертируем списки в множества для эффективной работы
                                        if "answered_polls" in user_data_copy and isinstance(user_data_copy["answered_polls"], list):
                                            user_data_copy["answered_polls"] = set(user_data_copy["answered_polls"])
                                        if "milestones_achieved" in user_data_copy and isinstance(user_data_copy["milestones_achieved"], list):
                                            user_data_copy["milestones_achieved"] = set(user_data_copy["milestones_achieved"])
                                        # НОВОЕ: Конвертируем список ачивок за серию в множество
                                        if "streak_achievements_earned" in user_data_copy and isinstance(user_data_copy["streak_achievements_earned"], list):
                                            user_data_copy["streak_achievements_earned"] = set(user_data_copy["streak_achievements_earned"])
                                        # НОВОЕ: Устанавливаем значения по умолчанию для новых полей, если их нет
                                        if "consecutive_correct" not in user_data_copy:
                                            user_data_copy["consecutive_correct"] = 0
                                        if "max_consecutive_correct" not in user_data_copy:
                                            user_data_copy["max_consecutive_correct"] = 0
                                        if "streak_achievements_earned" not in user_data_copy:
                                            user_data_copy["streak_achievements_earned"] = set()
                                        # НОВОЕ: Добавляем поля для ежедневной защиты от накрутки
                                        if "daily_answered_polls" not in user_data_copy:
                                            user_data_copy["daily_answered_polls"] = set()
                                        elif isinstance(user_data_copy["daily_answered_polls"], list):
                                            user_data_copy["daily_answered_polls"] = set(user_data_copy["daily_answered_polls"])
                                        if "last_daily_reset" not in user_data_copy:
                                            from datetime import date
                                            user_data_copy["last_daily_reset"] = date.today().isoformat()
                                        
                                        loaded_scores[chat_id][user_id_str] = user_data_copy
                                        logger.debug(f"Загружен пользователь {user_id_str} в чате {chat_id}")
                                    
                                    logger.debug(f"Загружены данные из users.json для чата {chat_id}: {len(chat_users)} пользователей")
                                else:
                                    logger.warning(f"Некорректный формат users.json в чате {chat_id}")
                            except Exception as e:
                                logger.warning(f"Ошибка загрузки users.json для чата {chat_id}: {e}")
                        else:
                            logger.debug(f"Файл users.json не найден для чата {chat_id}")
                        
                        # Проверяем stats.json для дополнительной информации
                        stats_file = chat_dir / "stats.json"
                        if stats_file.exists():
                            try:
                                with open(stats_file, 'r', encoding='utf-8') as f:
                                    stats_data = json.load(f)
                                if "total_score" in stats_data:
                                    logger.debug(f"Чат {chat_id}: общий счет {stats_data['total_score']}")
                                if "total_answered" in stats_data:
                                    logger.debug(f"Чат {chat_id}: всего ответов {stats_data['total_answered']}")
                            except Exception as e:
                                logger.warning(f"Ошибка загрузки stats.json для чата {chat_id}: {e}")
                        
                    except ValueError:
                        logger.warning(f"Некорректный chat_id '{chat_id_str}'")
                    except Exception as e:
                        logger.error(f"Ошибка загрузки данных чата {chat_id_str}: {e}")
            
            # Загружаем глобальные данные
            global_users_file = self.global_dir / "users.json"
            if global_users_file.exists():
                try:
                    with open(global_users_file, 'r', encoding='utf-8') as f:
                        global_users = json.load(f)
                    logger.debug(f"Загружены глобальные данные: {len(global_users)} пользователей")
                except Exception as e:
                    logger.warning(f"Ошибка загрузки глобальных данных: {e}")
            
            # Сохраняем загруженные данные в состояние
            self.state.user_scores = loaded_scores
            
            # Синхронизируем ачивки между чатами
            self.sync_achievements_across_chats()
            
            total_users = sum(len(users) for users in loaded_scores.values())
            logger.info(f"Данные пользователей загружены: {len(loaded_scores)} чатов, {total_users} пользователей")
            
        except Exception as e:
            logger.error(f"Критическая ошибка при загрузке данных пользователей: {e}", exc_info=True)

    def load_chat_settings(self) -> None:
        """Загружает настройки чатов из консолидированной структуры data/"""
        logger.debug("Загрузка настроек чатов из консолидированной структуры...")
        loaded_settings: Dict[int, Dict[str, Any]] = {}
        
        try:
            # Загружаем настройки из каждого чата
            for chat_dir in self.chats_dir.iterdir():
                if chat_dir.is_dir():
                    chat_id_str = chat_dir.name
                    settings_file = chat_dir / "settings.json"
                    
                    if settings_file.exists():
                        try:
                            chat_id = int(chat_id_str)
                            with open(settings_file, 'r', encoding='utf-8') as f:
                                chat_settings = json.load(f)
                            
                            if isinstance(chat_settings, dict):
                                loaded_settings[chat_id] = chat_settings
                                logger.debug(f"Загружены настройки для чата {chat_id}")
                            
                        except Exception as e:
                            logger.error(f"Ошибка загрузки настроек чата {chat_id_str}: {e}")
                    else:
                        # Автоматически создаем настройки по умолчанию для чатов без настроек
                        try:
                            chat_id = int(chat_id_str)
                            default_settings = self._get_default_chat_settings()
                            loaded_settings[chat_id] = default_settings
                            
                            # Сохраняем настройки по умолчанию
                            with open(settings_file, 'w', encoding='utf-8') as f:
                                json.dump(default_settings, f, ensure_ascii=False, indent=2)
                            
                            logger.info(f"Созданы настройки по умолчанию для чата {chat_id}")
                            
                        except Exception as e:
                            logger.error(f"Ошибка создания настроек по умолчанию для чата {chat_id_str}: {e}")
            
            self.state.chat_settings = loaded_settings
            logger.info(f"Настройки чатов загружены: {len(loaded_settings)} чатов")
            
            # Обновляем chats_index.json, чтобы отразить, что у всех чатов есть настройки
            self._update_chats_index(loaded_settings.keys())
            
        except Exception as e:
            logger.error(f"Критическая ошибка при загрузке настроек чатов: {e}", exc_info=True)

    def load_messages_to_delete(self) -> None:
        """Загружает сообщения для удаления из консолидированной структуры с поддержкой миграции"""
        import time
        try:
            messages_file = self.system_dir / "messages_to_delete.json"
            if not messages_file.exists():
                logger.debug("Файл сообщений для удаления не найден")
                return

            # Проверка на пустой файл
            if messages_file.stat().st_size == 0:
                logger.debug("Файл сообщений для удаления пустой, пропускаем загрузку")
                return

            with open(messages_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            current_time = time.time()
            max_age_seconds = 24 * 3600  # 24 часа
            migrated_count = 0
            filtered_count = 0

            # Преобразуем данные с миграцией из старого формата
            for chat_id_str, message_data in data.items():
                try:
                    chat_id = int(chat_id_str)

                    # Проверяем формат данных
                    if isinstance(message_data, list):
                        # Старый формат: List[int] -> мигрируем в Dict[int, float]
                        logger.info(f"Миграция из старого формата для чата {chat_id}")
                        for msg_id in message_data:
                            # Устанавливаем текущий timestamp для старых сообщений
                            self.state.generic_messages_to_delete[chat_id][msg_id] = current_time
                        migrated_count += len(message_data)

                    elif isinstance(message_data, dict):
                        # Новый формат: Dict[str, float] -> преобразуем ключи в int
                        for msg_id_str, timestamp in message_data.items():
                            msg_id = int(msg_id_str)
                            age = current_time - timestamp

                            # Фильтруем сообщения старше 24 часов
                            if age <= max_age_seconds:
                                self.state.generic_messages_to_delete[chat_id][msg_id] = timestamp
                            else:
                                filtered_count += 1
                                logger.debug(f"Фильтрация старого сообщения {msg_id} (возраст: {age/3600:.1f} часов)")
                    else:
                        logger.warning(f"Неизвестный формат данных для чата {chat_id}: {type(message_data)}")

                except (ValueError, TypeError) as e:
                    logger.warning(f"Ошибка преобразования данных для чата {chat_id_str}: {e}")

            total_messages = sum(len(msgs) for msgs in self.state.generic_messages_to_delete.values())
            logger.info(f"Загружено {total_messages} сообщений для удаления из {len(self.state.generic_messages_to_delete)} чатов")
            if migrated_count > 0:
                logger.info(f"🔄 Мигрировано {migrated_count} сообщений из старого формата")
            if filtered_count > 0:
                logger.info(f"🗑️ Отфильтровано {filtered_count} старых сообщений (>24ч)")

        except json.JSONDecodeError as e:
            logger.warning(f"Файл messages_to_delete.json поврежден или содержит невалидный JSON: {e}. Пропускаем загрузку.")
        except Exception as e:
            logger.error(f"Ошибка загрузки сообщений для удаления: {e}", exc_info=True)

    def save_user_data(self, chat_id: int) -> None:
        """
        Сохраняет данные пользователей чата в консолидированную структуру
        Правильно интегрируется с Telegram Bot API persistence system
        """
        try:
            if chat_id not in self.state.user_scores:
                logger.warning(f"Нет данных для сохранения в чате {chat_id}")
                return
            
            chat_dir = self.chats_dir / str(chat_id)
            chat_dir.mkdir(parents=True, exist_ok=True)
            
            chat_users = self.state.user_scores[chat_id]
            if not chat_users:
                logger.debug(f"Нет пользователей для сохранения в чате {chat_id}")
                return
            
            # Сохраняем users.json
            users_data = {}
            for user_id, user_data in chat_users.items():
                user_data_copy = user_data.copy()
                # Конвертируем множества в списки для JSON
                if "answered_polls" in user_data_copy:
                    user_data_copy["answered_polls"] = list(user_data_copy["answered_polls"])
                if "milestones_achieved" in user_data_copy:
                    user_data_copy["milestones_achieved"] = list(user_data_copy["milestones_achieved"])
                # НОВОЕ: Конвертируем множество ачивок за серию в список для JSON
                if "streak_achievements_earned" in user_data_copy:
                    user_data_copy["streak_achievements_earned"] = list(user_data_copy["streak_achievements_earned"])
                # НОВОЕ: Конвертируем ежедневные ответы в список для JSON
                if "daily_answered_polls" in user_data_copy:
                    user_data_copy["daily_answered_polls"] = list(user_data_copy["daily_answered_polls"])
                users_data[user_id] = user_data_copy
            
            users_file = chat_dir / "users.json"
            with open(users_file, 'w', encoding='utf-8') as f:
                json.dump(users_data, f, ensure_ascii=False, indent=2)
            
            # Создаем stats.json для синхронизации
            stats_data = {
                "chat_id": str(chat_id),
                "total_users": len(users_data),
                "total_score": sum(user.get("score", 0) for user in users_data.values()),
                "total_answered": sum(len(user.get("answered_polls", [])) for user in users_data.values()),
                "user_activity": {}
            }
            
            for user_id, user_data in users_data.items():
                stats_data["user_activity"][user_id] = {
                    "name": user_data.get("name", f"User {user_id}"),
                    "score": user_data.get("score", 0),
                    "answered_count": len(user_data.get("answered_polls", [])),
                    "first_answer": user_data.get("first_answer_time"),
                    "last_answer": user_data.get("last_answer_time"),
                    # НОВОЕ: Добавляем статистику серий
                    "consecutive_correct": user_data.get("consecutive_correct", 0),
                    "max_consecutive_correct": user_data.get("max_consecutive_correct", 0),
                    "streak_achievements_count": len(user_data.get("streak_achievements_earned", []))
                }
            
            stats_file = chat_dir / "stats.json"
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(stats_data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"Данные пользователей чата {chat_id} сохранены (users.json + stats.json)")
            
            # Обновляем глобальную статистику
            self.update_global_statistics()
            
        except Exception as e:
            logger.error(f"Ошибка сохранения данных пользователей чата {chat_id}: {e}", exc_info=True)

    def save_chat_settings(self) -> None:
        """Сохраняет настройки чатов в консолидированную структуру"""
        logger.debug("Сохранение настроек чатов в консолидированную структуру...")
        
        saved_count = 0
        failed_count = 0
        
        for chat_id, settings in self.state.chat_settings.items():
            # Пропускаем чаты с устаревшими настройками
            if "quiz_categories_mode" in settings or "quiz_categories_pool" in settings or "quiz_settings" in settings:
                logger.debug(f"Пропускаем чат {chat_id} - устаревшие настройки")
                continue
                
            try:
                chat_dir = self.chats_dir / str(chat_id)
                chat_dir.mkdir(parents=True, exist_ok=True)
                
                settings_file = chat_dir / "settings.json"
                with open(settings_file, 'w', encoding='utf-8') as f:
                    json.dump(settings, f, ensure_ascii=False, indent=2)
                
                logger.debug(f"Настройки чата {chat_id} сохранены")
                saved_count += 1
                
            except Exception as e:
                logger.warning(f"Ошибка сохранения настроек чата {chat_id}: {e}")
                failed_count += 1
                continue
        
        if failed_count > 0:
            logger.warning(f"Сохранение настроек завершено: {saved_count} успешно, {failed_count} с ошибками")
        else:
            logger.info(f"Настройки чатов сохранены в консолидированную структуру: {saved_count} чатов")

    def save_modified_chat_settings(self) -> None:
        """Сохраняет только измененные настройки чатов для быстрой работы"""
        if not hasattr(self.state, '_chat_settings_modified') or not self.state._chat_settings_modified:
            logger.debug("Нет измененных настроек чатов для сохранения")
            return
        
        logger.debug(f"Сохранение измененных настроек для {len(self.state._chat_settings_modified)} чатов...")
        
        saved_count = 0
        failed_count = 0
        
        for chat_id in self.state._chat_settings_modified:
            try:
                if chat_id in self.state.chat_settings:
                    chat_dir = self.chats_dir / str(chat_id)
                    chat_dir.mkdir(parents=True, exist_ok=True)
                    
                    settings_file = chat_dir / "settings.json"
                    with open(settings_file, 'w', encoding='utf-8') as f:
                        json.dump(self.state.chat_settings[chat_id], f, ensure_ascii=False, indent=2)
                    
                    logger.debug(f"Измененные настройки чата {chat_id} сохранены")
                    saved_count += 1
                
            except Exception as e:
                logger.warning(f"Ошибка сохранения измененных настроек чата {chat_id}: {e}")
                failed_count += 1
                continue
        
        # Очищаем список измененных настроек
        self.state._chat_settings_modified.clear()
        
        if failed_count > 0:
            logger.warning(f"Сохранение измененных настроек завершено: {saved_count} успешно, {failed_count} с ошибками")
        else:
            logger.info(f"Измененные настройки чатов сохранены: {saved_count} чатов")

    async def save_modified_chat_settings_async(self) -> None:
        """Асинхронно сохраняет только измененные настройки чатов"""
        if not hasattr(self.state, '_chat_settings_modified') or not self.state._chat_settings_modified:
            logger.debug("Нет измененных настроек чатов для сохранения")
            return

        logger.debug(f"Асинхронное сохранение измененных настроек для {len(self.state._chat_settings_modified)} чатов...")

        # Создаем задачи для параллельного сохранения
        tasks = []

        for chat_id in self.state._chat_settings_modified:
            if chat_id in self.state.chat_settings:
                task = self._save_single_chat_settings_async(chat_id, self.state.chat_settings[chat_id])
                tasks.append(task)

        # Выполняем все задачи параллельно
        results = await asyncio.gather(*tasks, return_exceptions=True)

        saved_count = sum(1 for result in results if result is True)
        failed_count = sum(1 for result in results if isinstance(result, Exception) or result is False)

        # Очищаем список измененных настроек
        self.state._chat_settings_modified.clear()

        if failed_count > 0:
            logger.warning(f"Асинхронное сохранение настроек завершено: {saved_count} успешно, {failed_count} с ошибками")
        else:
            logger.info(f"Измененные настройки чатов сохранены асинхронно: {saved_count} чатов")

    async def _save_single_chat_settings_async(self, chat_id: int, settings: Dict[str, Any]) -> bool:
        """Асинхронно сохраняет настройки одного чата"""
        try:
            chat_dir = self.chats_dir / str(chat_id)
            settings_file = chat_dir / "settings.json"
            return await self._write_json_async(settings_file, settings)
        except Exception as e:
            logger.warning(f"Ошибка асинхронного сохранения настроек чата {chat_id}: {e}")
            return False

    def save_messages_to_delete(self) -> None:
        """Сохраняет сообщения для удаления в консолидированную структуру с timestamp"""
        try:
            # Преобразуем Dict[int, Dict[int, float]] в JSON-совместимый формат
            # chat_id (str) -> {message_id (str): timestamp (float)}
            data_to_save = {}
            for chat_id, messages_dict in self.state.generic_messages_to_delete.items():
                data_to_save[str(chat_id)] = {str(msg_id): timestamp for msg_id, timestamp in messages_dict.items()}

            with open(self.system_dir / "messages_to_delete.json", 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)

            total_messages = sum(len(msgs) for msgs in self.state.generic_messages_to_delete.values())
            logger.debug(f"Сообщения для удаления сохранены ({len(data_to_save)} чатов, {total_messages} сообщений)")

        except Exception as e:
            logger.error(f"Ошибка сохранения сообщений для удаления: {e}", exc_info=True)

    def save_all_data(self) -> None:
        """Сохраняет все данные в консолидированную структуру"""
        logger.info("Сохранение всех данных в консолидированную структуру...")
        # Сохраняем данные пользователей для каждого чата
        for chat_id in self.state.user_scores.keys():
            self.save_user_data(chat_id)

        # Сохраняем только измененные настройки чатов
        self.save_modified_chat_settings()
        self.save_messages_to_delete()
        logger.info("Сохранение всех данных завершено")

    async def save_all_data_async(self) -> None:
        """Асинхронно сохраняет все данные в консолидированную структуру"""
        logger.info("Асинхронное сохранение всех данных...")

        # Создаем задачи для параллельного сохранения
        tasks = []

        # Сохраняем данные пользователей для каждого чата параллельно
        for chat_id in self.state.user_scores.keys():
            tasks.append(self._run_in_executor(self.save_user_data, chat_id))

        # Добавляем задачи для сохранения настроек и сообщений
        tasks.append(self.save_modified_chat_settings_async())
        tasks.append(self._run_in_executor(self.save_messages_to_delete))

        # Выполняем все задачи параллельно
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Асинхронное сохранение всех данных завершено")

    async def load_all_data_async(self) -> None:
        """Асинхронно загружает все данные из консолидированной структуры с ограничением параллелизма"""
        logger.debug("Начало асинхронной загрузки всех данных из консолидированной структуры...")

        # Создаем семафор для ограничения количества одновременных операций чтения файлов
        semaphore = asyncio.Semaphore(3)  # Максимум 3 одновременных операции чтения

        async def load_with_semaphore(load_func):
            async with semaphore:
                # Выполняем синхронную функцию в executor
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, load_func)

        # Загружаем данные параллельно, но с ограничением
        await asyncio.gather(
            load_with_semaphore(self.load_questions),
            load_with_semaphore(self.load_user_data),
            load_with_semaphore(self.load_chat_settings),
            load_with_semaphore(self.load_messages_to_delete)
        )

        logger.debug("Асинхронная загрузка всех данных завершена")

    def load_all_data(self) -> None:
        """Загружает все данные из консолидированной структуры (синхронная версия для совместимости)"""
        logger.debug("Начало загрузки всех данных из консолидированной структуры...")
        self.load_questions()
        self.load_user_data()
        self.load_chat_settings()
        self.load_messages_to_delete()
        logger.debug("Загрузка всех данных завершена")

    def update_chat_setting(self, chat_id: int, key_path: List[str], value: Any) -> None:
        """Обновляет настройку конкретного чата"""
        if chat_id not in self.state.chat_settings:
            self.state.chat_settings[chat_id] = copy.deepcopy(self.app_config.default_chat_settings)
        
        current_level = self.state.chat_settings[chat_id]
        for i, key_part in enumerate(key_path):
            if i == len(key_path) - 1:
                current_level[key_part] = value
            else:
                current_level = current_level.setdefault(key_part, {})
        
        # НЕМЕДЛЕННОЕ СОХРАНЕНИЕ: Сохраняем настройки сразу для надежности
        self.save_chat_settings()

        # Помечаем, что настройки изменены и требуют сохранения (для совместимости)
        if not hasattr(self.state, '_chat_settings_modified'):
            self.state._chat_settings_modified = set()
        self.state._chat_settings_modified.add(chat_id)
        
        logger.info(f"Настройка '{'.'.join(key_path)}' для чата {chat_id} обновлена на: {value}")

    def update_quiz_setting(self, chat_id: int, setting_name: str, value: Any) -> None:
        """Обновляет настройку квиза для конкретного чата"""
        logger.debug(f"ОТЛАДКА: update_quiz_setting вызван для чата {chat_id}, настройка '{setting_name}', значение {value}")
        
        # Сохраняем в новую структуру quiz.*
        key_path = ["quiz", setting_name]
        self.update_chat_setting(chat_id, key_path, value)
        
        # ДОПОЛНИТЕЛЬНО: Сохраняем в основные настройки чата для совместимости
        if setting_name == "num_questions":
            self.update_chat_setting(chat_id, ["default_num_questions"], value)
        elif setting_name == "open_period_seconds":
            self.update_chat_setting(chat_id, ["default_open_period_seconds"], value)
        elif setting_name == "announce":
            self.update_chat_setting(chat_id, ["default_announce_quiz"], value)
        elif setting_name == "interval_seconds":
            self.update_chat_setting(chat_id, ["default_interval_seconds"], value)
        
        logger.info(f"Настройка квиза '{setting_name}' для чата {chat_id} обновлена на: {value}")
        
        # ОТЛАДКА: Проверяем, что настройка действительно сохранилась
        current_value = self.get_quiz_setting(chat_id, setting_name)
        logger.debug(f"ОТЛАДКА: После сохранения настройка '{setting_name}' для чата {chat_id} = {current_value}")

    def get_quiz_setting(self, chat_id: int, setting_name: str, default_value: Any = None) -> Any:
        """Получает настройку квиза для конкретного чата"""
        chat_settings = self.get_chat_settings(chat_id)
        quiz_settings = chat_settings.get("quiz", {})
        result = quiz_settings.get(setting_name, default_value)
        logger.debug(f"ОТЛАДКА: get_quiz_setting для чата {chat_id}, настройка '{setting_name}' = {result}")
        return result

    def reset_chat_settings(self, chat_id: int) -> None:
        """Сбрасывает настройки конкретного чата"""
        if chat_id in self.state.chat_settings:
            del self.state.chat_settings[chat_id]
            logger.info(f"Настройки для чата {chat_id} сброшены")
            self.save_chat_settings()
        else:
            logger.info(f"Для чата {chat_id} не было специфичных настроек для сброса")

    def get_chat_settings(self, chat_id: int) -> Dict[str, Any]:
        """Получает настройки конкретного чата"""
        defaults = copy.deepcopy(self.app_config.default_chat_settings)
        if chat_id in self.state.chat_settings:
            chat_specific = self.state.chat_settings[chat_id]
            self._deep_merge_dicts(defaults, chat_specific)
        return defaults

    def _deep_merge_dicts(self, base_dict: Dict[Any, Any], updates_dict: Dict[Any, Any]) -> None:
        """Глубоко объединяет словари"""
        for key, value in updates_dict.items():
            if isinstance(value, dict) and key in base_dict and isinstance(base_dict[key], dict):
                self._deep_merge_dicts(base_dict[key], value)
            else:
                base_dict[key] = value

    async def update_chat_metadata(self, chat_id: int, bot=None) -> bool:
        """
        Обновляет метаданные чата (название, тип) через Telegram API.
        Вызывается при первом взаимодействии с чатом или периодически для обновления.
        
        Args:
            chat_id: ID чата
            bot: Экземпляр Bot для запросов к API (если None, попытается получить из application)
            
        Returns:
            bool: True если метаданные обновлены, False при ошибке
        """
        try:
            # Если бот не передан, пытаемся получить из application
            if bot is None:
                if self.state.application:
                    bot = self.state.application.bot
                else:
                    logger.debug(f"Не удалось получить bot для обновления метаданных чата {chat_id}")
                    return False
            
            if not bot:
                return False
            
            # Получаем информацию о чате через Telegram API
            chat = await bot.get_chat(chat_id)
            
            # Определяем название и тип
            chat_title = None
            if chat.title:
                chat_title = chat.title
            elif chat.first_name:
                chat_title = chat.first_name
                if chat.last_name:
                    chat_title += f" {chat.last_name}"
            
            chat_type = chat.type if hasattr(chat, 'type') else None
            
            # Получаем текущие настройки
            if chat_id not in self.state.chat_settings:
                self.state.chat_settings[chat_id] = {}
            
            current_title = self.state.chat_settings[chat_id].get("title")
            current_type = self.state.chat_settings[chat_id].get("chat_type")
            
            # Обновляем только если данные изменились или отсутствуют
            updated = False
            if chat_title and (current_title is None or current_title != chat_title):
                self.state.chat_settings[chat_id]["title"] = chat_title
                updated = True
                logger.info(f"Обновлено название чата {chat_id}: {chat_title}")
            
            if chat_type and (current_type is None or current_type != chat_type):
                self.state.chat_settings[chat_id]["chat_type"] = chat_type
                updated = True
                logger.debug(f"Обновлен тип чата {chat_id}: {chat_type}")
            
            # Сохраняем настройки если были изменения
            if updated:
                self.save_chat_settings()
            
            return updated
            
        except Exception as e:
            error_msg = str(e).lower()
            # Не логируем ошибки для чатов, где бот не состоит или недоступен
            if "chat not found" in error_msg or "not found" in error_msg:
                logger.debug(f"Чат {chat_id} не найден в Telegram (возможно, бот удален из чата)")
            else:
                logger.debug(f"Не удалось обновить метаданные чата {chat_id}: {e}")
            return False

    def disable_daily_quiz_for_chat(self, chat_id: int, reason: str = "blocked") -> bool:
        """
        Автоматически отключает ежедневную рассылку викторин для чата.
        Используется когда бот заблокирован или чат недоступен.

        Args:
            chat_id: ID чата
            reason: Причина отключения (blocked, not_found, etc)

        Returns:
            bool: True если успешно отключено, False при ошибке
        """
        try:
            # Получаем текущие настройки чата
            if chat_id not in self.state.chat_settings:
                self.state.chat_settings[chat_id] = {}

            # Отключаем ежедневную рассылку
            if "daily_quiz" not in self.state.chat_settings[chat_id]:
                self.state.chat_settings[chat_id]["daily_quiz"] = {}

            self.state.chat_settings[chat_id]["daily_quiz"]["enabled"] = False

            # Сохраняем настройки
            self.save_chat_settings()

            logger.warning(f"🔕 Автоматически отключена ежедневная рассылка для чата {chat_id}. Причина: {reason}")
            return True

        except Exception as e:
            logger.error(f"Ошибка при отключении рассылки для чата {chat_id}: {e}")
            return False

    def get_all_questions(self) -> Dict[str, List[Dict[str, Any]]]:
        """Получает все вопросы"""
        return self.state.quiz_data

    def get_global_setting(self, key: str, default_value: Any = None) -> Any:
        """Получает глобальную настройку"""
        if not hasattr(self.state, 'global_settings'):
            self.state.global_settings = {}
        return self.state.global_settings.get(key, default_value)

    def update_global_setting(self, key: str, value: Any) -> None:
        """Обновляет глобальную настройку"""
        if not hasattr(self.state, 'global_settings'):
            self.state.global_settings = {}
        self.state.global_settings[key] = value
        logger.debug(f"Глобальная настройка '{key}' обновлена")

    # Методы для работы с консолидированной структурой
    def get_chat_statistics(self, chat_id: int) -> Dict[str, Any]:
        """Получает статистику конкретного чата"""
        try:
            stats_file = self.chats_dir / str(chat_id) / "stats.json"
            if stats_file.exists():
                with open(stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки статистики чата {chat_id}: {e}")
        return {}

    def get_global_statistics(self) -> Dict[str, Any]:
        """Получает глобальную статистику"""
        try:
            stats_file = self.statistics_dir / "global_stats.json"
            if stats_file.exists():
                with open(stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки глобальной статистики: {e}")
        return {}

    def get_category_statistics(self) -> Dict[str, Any]:
        """Получает статистику по категориям"""
        try:
            stats_file = self.statistics_dir / "categories_stats.json"
            if stats_file.exists():
                with open(stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки статистики категорий: {e}")
        return {}

    def sync_achievements_across_chats(self) -> None:
        """Синхронизирует ачивки между всеми чатами для предотвращения дублирования"""
        logger.debug("Синхронизация ачивок между чатами...")
        
        try:
            # Собираем все ачивки каждого пользователя из всех чатов
            user_achievements: Dict[str, Set[str]] = {}
            
            for chat_id, chat_users in self.state.user_scores.items():
                for user_id_str, user_data in chat_users.items():
                    if user_id_str not in user_achievements:
                        user_achievements[user_id_str] = set()
                    
                    user_milestones = user_data.get("milestones_achieved", set())
                    if isinstance(user_milestones, list):
                        user_milestones = set(user_milestones)
                    
                    user_achievements[user_id_str].update(user_milestones)
            
            # Применяем синхронизированные ачивки ко всем чатам
            for chat_id, chat_users in self.state.user_scores.items():
                for user_id_str, user_data in chat_users.items():
                    if user_id_str in user_achievements:
                        user_data["milestones_achieved"] = user_achievements[user_id_str].copy()
            
            logger.info(f"Ачивки синхронизированы для {len(user_achievements)} пользователей")
            
        except Exception as e:
            logger.error(f"Ошибка синхронизации ачивок: {e}", exc_info=True)

    def update_global_statistics(self) -> None:
        """Обновляет глобальную статистику на основе текущих данных"""
        try:
            # Загружаем текущие глобальные данные
            global_users_file = self.global_dir / "users.json"
            if not global_users_file.exists():
                logger.warning("Глобальный файл пользователей не найден, создаем новый")
                self._create_initial_global_statistics()
                return
            
            with open(global_users_file, 'r', encoding='utf-8') as f:
                global_users = json.load(f)
            
            # Обновляем глобальные очки и ачивки на основе текущих данных
            updated = False
            for chat_id_str, chat_users in self.state.user_scores.items():
                for user_id_str, user_data in chat_users.items():
                    if user_id_str in global_users:
                        current_global_score = global_users[user_id_str].get("global_score", 0)
                        current_chat_score = user_data.get("score", 0)
                        
                        # Правильно вычисляем общий счет
                        total_score = 0
                        for other_chat_id, other_chat_users in self.state.user_scores.items():
                            if user_id_str in other_chat_users:
                                total_score += other_chat_users[user_id_str].get("score", 0)
                        
                        # Проверяем, нужно ли обновить глобальные очки
                        if global_users[user_id_str]["global_score"] != total_score:
                            global_users[user_id_str]["global_score"] = total_score
                            updated = True
                            logger.debug(f"Обновлены глобальные очки для пользователя {user_id_str}: {total_score}")
                        
                        # Синхронизируем ачивки глобально
                        all_user_milestones = set()
                        for other_chat_id, other_chat_users in self.state.user_scores.items():
                            if user_id_str in other_chat_users:
                                chat_milestones = other_chat_users[user_id_str].get("milestones_achieved", set())
                                all_user_milestones.update(chat_milestones)
                        
                        if all_user_milestones:
                            global_milestones = global_users[user_id_str].get("milestones_achieved", [])
                            global_milestones_set = set(global_milestones)
                            
                            # Добавляем новые ачивки
                            new_milestones = all_user_milestones - global_milestones_set
                            if new_milestones:
                                global_milestones.extend(list(new_milestones))
                                global_users[user_id_str]["milestones_achieved"] = global_milestones
                                updated = True
                                logger.debug(f"Добавлены новые ачивки для пользователя {user_id_str}: {new_milestones}")
                                
                                # Синхронизируем ачивки во всех чатах
                                for sync_chat_id, sync_chat_users in self.state.user_scores.items():
                                    if user_id_str in sync_chat_users:
                                        sync_user_achievements = sync_chat_users[user_id_str].setdefault("milestones_achieved", set())
                                        sync_user_achievements.update(new_milestones)
            
            # Сохраняем обновленные данные
            if updated:
                with open(global_users_file, 'w', encoding='utf-8') as f:
                    json.dump(global_users, f, ensure_ascii=False, indent=2)
                
                # Обновляем глобальную статистику
                self._update_global_stats_file(global_users)
                logger.info("Глобальная статистика обновлена")
            
        except Exception as e:
            logger.error(f"Ошибка обновления глобальной статистики: {e}", exc_info=True)

    def _create_initial_global_statistics(self) -> None:
        """Создает начальную глобальную статистику"""
        try:
            global_users = {}
            
            # Собираем данные из всех чатов
            for chat_id_str, chat_users in self.state.user_scores.items():
                for user_id_str, user_data in chat_users.items():
                    if user_id_str not in global_users:
                        global_users[user_id_str] = {
                            "name": user_data.get("name", f"User {user_id_str}"),
                            "global_score": 0,
                            "total_answered": 0,
                            "chats_participated": [],
                            "first_answer_time": None,
                            "last_answer_time": None,
                            "milestones_achieved": []
                        }
                    
                    # Суммируем очки
                    global_users[user_id_str]["global_score"] += user_data.get("score", 0)
                    global_users[user_id_str]["total_answered"] += len(user_data.get("answered_polls", set()))
                    
                    if chat_id_str not in global_users[user_id_str]["chats_participated"]:
                        global_users[user_id_str]["chats_participated"].append(chat_id_str)
                    
                    # Объединяем ачивки глобально
                    if user_id_str not in global_users:
                        global_users[user_id_str]["milestones_achieved"] = []
                    
                    # Добавляем ачивки из текущего чата
                    current_milestones = user_data.get("milestones_achieved", set())
                    if current_milestones:
                        global_milestones = global_users[user_id_str]["milestones_achieved"]
                        global_milestones_set = set(global_milestones)
                        
                        # Добавляем новые ачивки
                        new_milestones = current_milestones - global_milestones_set
                        if new_milestones:
                            global_milestones.extend(list(new_milestones))
                            global_users[user_id_str]["milestones_achieved"] = global_milestones
                    
                    # Обновляем временные метки
                    if user_data.get("first_answer_time"):
                        if not global_users[user_id_str]["first_answer_time"] or user_data["first_answer_time"] < global_users[user_id_str]["first_answer_time"]:
                            global_users[user_id_str]["first_answer_time"] = user_data["first_answer_time"]
                    
                    if user_data.get("last_answer_time"):
                        if not global_users[user_id_str]["last_answer_time"] or user_data["last_answer_time"] > global_users[user_id_str]["last_answer_time"]:
                            global_users[user_id_str]["last_answer_time"] = user_data["last_answer_time"]
            
            # Сохраняем глобальные данные
            with open(self.global_dir / "users.json", 'w', encoding='utf-8') as f:
                json.dump(global_users, f, ensure_ascii=False, indent=2)
            
            # Создаем глобальную статистику
            self._update_global_stats_file(global_users)
            logger.info("Создана начальная глобальная статистика")
            
        except Exception as e:
            logger.error(f"Ошибка создания начальной глобальной статистики: {e}", exc_info=True)

    def _update_global_stats_file(self, global_users: Dict[str, Any]) -> None:
        """Обновляет файл глобальной статистики"""
        try:
            total_users = len(global_users)
            total_score = sum(user.get("global_score", 0) for user in global_users.values())
            total_answered = sum(user.get("total_answered", 0) for user in global_users.values())
            
            # Анализ активности
            active_users = [uid for uid, user in global_users.items() if user.get("total_answered", 0) > 0]
            inactive_users = [uid for uid, user in global_users.items() if user.get("total_answered", 0) == 0]
            
            # Распределение очков
            scores = [user.get("global_score", 0) for user in global_users.values()]
            score_distribution = {
                "0-1": len([s for s in scores if 0 <= s <= 1]),
                "1-5": len([s for s in scores if 1 < s <= 5]),
                "5-10": len([s for s in scores if 5 < s <= 10]),
                "10-25": len([s for s in scores if 10 < s <= 25]),
                "25-50": len([s for s in scores if 25 < s <= 50]),
                "50+": len([s for s in scores if s > 50])
            }
            
            # Топ пользователей
            top_users = sorted(global_users.items(), key=lambda x: x[1].get("global_score", 0), reverse=True)[:20]
            
            global_stats = {
                "total_users": total_users,
                "active_users": len(active_users),
                "inactive_users": len(inactive_users),
                # ИСПРАВЛЕНО: Округляем общий счет до 1 знака после запятой
                "total_score": round(total_score, 1),
                "total_answered_polls": total_answered,
                # ИСПРАВЛЕНО: Округляем средний счет до 2 знаков после запятой
                "average_score": round(total_score / total_users, 2) if total_users > 0 else 0,
                "average_answered_per_user": total_answered / total_users if total_users > 0 else 0,
                "score_distribution": score_distribution,
                # ИСПРАВЛЕНО: Округляем очки пользователей до 1 знака после запятой
                "top_users": [{"user_id": uid, "name": user.get("name", f"User {uid}"), "global_score": round(user.get("global_score", 0), 1)} for uid, user in top_users],
                "last_updated": datetime.now().isoformat()
            }
            
            with open(self.statistics_dir / "global_stats.json", 'w', encoding='utf-8') as f:
                json.dump(global_stats, f, ensure_ascii=False, indent=2)
            
            # Обновляем статистику категорий
            self._update_categories_stats_file()
                
        except Exception as e:
            logger.error(f"Ошибка обновления файла глобальной статистики: {e}", exc_info=True)
            # Уведомляем об ошибке
            self._notify_developer_about_error("stats_update_error", str(e), "Обновление глобальной статистики")

    def _update_categories_stats_file(self) -> None:
        """Обновляет глобальную статистику категорий на основе данных из всех чатов"""
        try:
            global_categories_stats = {}
            
            # Проходим по всем чатам и собираем статистику категорий
            for chat_dir in self.chats_dir.iterdir():
                if chat_dir.is_dir() and chat_dir.name.startswith('-') or chat_dir.name.isdigit():
                    chat_categories_file = chat_dir / "categories_stats.json"
                    if chat_categories_file.exists():
                        try:
                            with open(chat_categories_file, 'r', encoding='utf-8') as f:
                                chat_categories = json.load(f)
                            
                            # Агрегируем статистику по категориям
                            for category, stats in chat_categories.items():
                                if category not in global_categories_stats:
                                    global_categories_stats[category] = {
                                        "total_usage": 0,
                                        "chat_usage": 0,
                                        "last_used": 0,
                                        "chats_used_in": set()
                                    }
                                
                                global_categories_stats[category]["total_usage"] += stats.get("total_usage", 0)
                                global_categories_stats[category]["chat_usage"] += stats.get("chat_usage", 0)
                                global_categories_stats[category]["chats_used_in"].add(chat_dir.name)
                                
                                # Обновляем время последнего использования
                                last_used = stats.get("last_used", 0)
                                if last_used > global_categories_stats[category]["last_used"]:
                                    global_categories_stats[category]["last_used"] = last_used
                                    
                        except Exception as e:
                            logger.warning(f"Ошибка чтения статистики категорий чата {chat_dir.name}: {e}")
            
            # Преобразуем set в list для JSON сериализации
            for category_stats in global_categories_stats.values():
                category_stats["chats_used_in"] = list(category_stats["chats_used_in"])
            
            # Сохраняем глобальную статистику категорий
            categories_stats_file = self.statistics_dir / "categories_stats.json"
            with open(categories_stats_file, 'w', encoding='utf-8') as f:
                json.dump(global_categories_stats, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Обновлена глобальная статистика категорий: {len(global_categories_stats)} категорий")
            
        except Exception as e:
            logger.error(f"Ошибка обновления статистики категорий: {e}", exc_info=True)
            # Уведомляем об ошибке
            self._notify_developer_about_error("categories_stats_update_error", str(e), "Обновление статистики категорий")

    def _notify_developer_about_malformed(self, malformed_entries: List[Dict[str, Any]]) -> None:
        """Уведомляет разработчика о малформированных вопросах"""
        try:
            # Проверяем, есть ли доступ к уведомлениям
            if hasattr(self, 'developer_notifier') and self.developer_notifier:
                self.developer_notifier.notify_malformed_questions(malformed_entries)
        except Exception as e:
            logger.debug(f"Не удалось отправить уведомления разработчику: {e}")

    def _notify_developer_about_error(self, error_type: str, error_details: str, context: str = "") -> None:
        """Уведомляет разработчика об ошибке"""
        try:
            # Проверяем, есть ли доступ к уведомлениям
            if hasattr(self, 'developer_notifier') and self.developer_notifier:
                self.developer_notifier.notify_data_error(error_type, error_details, context)
        except Exception as e:
            logger.debug(f"Не удалось отправить уведомление об ошибке разработчику: {e}")

    def _notify_developer_about_auto_fix(self, fixed_categories: List[str]) -> None:
        """Уведомляет разработчика об успешном автоисправлении"""
        try:
            # Проверяем, есть ли доступ к уведомлениям
            if hasattr(self, 'developer_notifier') and self.developer_notifier:
                self.developer_notifier.notify_auto_fix_success(fixed_categories)
        except Exception as e:
            logger.debug(f"Не удалось отправить уведомление об автоисправлении разработчику: {e}")

    async def update_category_statistics(self, chat_id: int, category: str) -> None:
        """Обновляет статистику использования категории в чате"""
        try:
            chat_dir = self.chats_dir / str(chat_id)
            categories_stats_file = chat_dir / "categories_stats.json"
            
            # Загружаем существующую статистику или создаем новую
            categories_stats = {}
            if categories_stats_file.exists():
                try:
                    with open(categories_stats_file, 'r', encoding='utf-8') as f:
                        categories_stats = json.load(f)
                except Exception as e:
                    logger.warning(f"Ошибка загрузки статистики категорий чата {chat_id}: {e}")
                    categories_stats = {}
            
            # Обновляем статистику для данной категории
            if category not in categories_stats:
                categories_stats[category] = {
                    "chat_usage": 0,
                    "total_usage": 0,
                    "last_used": 0
                }
            
            # Увеличиваем счетчики
            categories_stats[category]["chat_usage"] += 1
            categories_stats[category]["total_usage"] += 1
            categories_stats[category]["last_used"] = datetime.now().timestamp()
            
            # Сохраняем обновленную статистику
            with open(categories_stats_file, 'w', encoding='utf-8') as f:
                json.dump(categories_stats, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"Обновлена статистика категории '{category}' в чате {chat_id}")
            
        except Exception as e:
            logger.error(f"Ошибка обновления статистики категории '{category}' в чате {chat_id}: {e}")

    def set_developer_notifier(self, notifier) -> None:
        """Устанавливает уведомления разработчика"""
        self.developer_notifier = notifier
        logger.info("Уведомления разработчика установлены")

    # ===== СИСТЕМА СОХРАНЕНИЯ АКТИВНЫХ ВИКТОРИН =====

    def get_active_quizzes_file_path(self) -> Path:
        """Возвращает путь к файлу активных викторин"""
        return Path(self.app_config.data_dir) / "active_quizzes.json"

    def _convert_sets_to_lists(self, obj):
        """
        Рекурсивно конвертирует set() в list() для JSON сериализации.
        Обрабатывает вложенные словари и списки.
        """
        if isinstance(obj, set):
            return list(obj)
        elif isinstance(obj, dict):
            return {key: self._convert_sets_to_lists(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_sets_to_lists(item) for item in obj]
        else:
            return obj

    def save_active_quizzes(self) -> None:
        """
        Сохраняет активные викторины для восстановления после перезапуска.
        Сохраняются только сериализуемые данные викторины.
        """
        if not hasattr(self, 'state') or not self.state:
            logger.warning("DataManager.save_active_quizzes: state не инициализирован")
            return

        active_quizzes_file = self.get_active_quizzes_file_path()
        active_quizzes_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Собираем данные активных викторин
            quizzes_data = {}

            for chat_id, quiz_state in self.state.active_quizzes.items():
                try:
                    # Создаем сериализуемые данные викторины
                    quiz_data = {
                        "chat_id": quiz_state.chat_id,
                        "quiz_type": quiz_state.quiz_type,
                        "quiz_mode": quiz_state.quiz_mode,
                        "num_questions_to_ask": quiz_state.num_questions_to_ask,
                        "open_period_seconds": quiz_state.open_period_seconds,
                        "created_by_user_id": quiz_state.created_by_user_id,
                        "original_command_message_id": quiz_state.original_command_message_id,
                        "announce_message_id": quiz_state.announce_message_id,
                        "interval_seconds": quiz_state.interval_seconds,
                        "quiz_start_time": quiz_state.quiz_start_time.isoformat() if quiz_state.quiz_start_time else None,
                        "current_question_index": quiz_state.current_question_index,
                        "scores": self._convert_sets_to_lists(dict(quiz_state.scores)),  # Конвертируем set() в list()
                        "active_poll_ids_in_session": list(quiz_state.active_poll_ids_in_session),
                        "latest_poll_id_sent": quiz_state.latest_poll_id_sent,
                        "progression_triggered_for_poll": dict(quiz_state.progression_triggered_for_poll),
                        "message_ids_to_delete": list(quiz_state.message_ids_to_delete),
                        "is_stopping": quiz_state.is_stopping,
                        "poll_and_solution_message_ids": quiz_state.poll_and_solution_message_ids.copy(),
                        "results_message_ids": list(quiz_state.results_message_ids),
                        # Сохраняем вопросы (без потенциально проблемных данных)
                        "questions": [
                            {
                                k: v for k, v in q.items()
                                if k not in ['job_poll_end_name', 'next_question_job_name']  # Исключаем несериализуемые объекты
                            } for q in quiz_state.questions
                        ]
                    }

                    quizzes_data[str(chat_id)] = quiz_data
                    logger.debug(f"Подготовлена викторина чата {chat_id} для сохранения")

                except Exception as e:
                    logger.error(f"Ошибка при подготовке викторины чата {chat_id} для сохранения: {e}")
                    continue

            # Сохраняем в файл
            with open(active_quizzes_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "active_quizzes": quizzes_data
                }, f, ensure_ascii=False, indent=2)

            logger.info(f"✅ Сохранено {len(quizzes_data)} активных викторин в {active_quizzes_file}")

        except Exception as e:
            logger.error(f"❌ Ошибка сохранения активных викторин: {e}")

    def load_active_quizzes(self) -> Dict[int, Dict[str, Any]]:
        """
        Загружает сохраненные активные викторины.
        Возвращает словарь chat_id -> quiz_data для восстановления.
        """
        active_quizzes_file = self.get_active_quizzes_file_path()

        if not active_quizzes_file.exists():
            logger.info("Файл активных викторин не найден, восстановление не требуется")
            return {}

        try:
            with open(active_quizzes_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            quizzes_data = data.get("active_quizzes", {})
            saved_timestamp = data.get("timestamp")

            if not quizzes_data:
                logger.info("В файле активных викторин нет данных")
                return {}

            logger.info(f"Загружено {len(quizzes_data)} активных викторин (сохранено: {saved_timestamp})")

            # Очищаем устаревшие викторины (старше 2 часов)
            # ИСПРАВЛЕНИЕ: Используем UTC для совместимости с quiz_start_time (который сохраняется как UTC через get_current_utc_time())
            from datetime import timezone
            current_time = datetime.now(timezone.utc)
            valid_quizzes = {}

            for chat_id_str, quiz_data in quizzes_data.items():
                try:
                    chat_id = int(chat_id_str)

                    # Проверяем актуальность викторины
                    quiz_start_time_str = quiz_data.get("quiz_start_time")
                    if quiz_start_time_str:
                        quiz_start_time = datetime.fromisoformat(quiz_start_time_str)
                        # Нормализуем quiz_start_time к UTC, если он timezone-aware
                        if quiz_start_time.tzinfo is not None:
                            quiz_start_time = quiz_start_time.astimezone(timezone.utc)
                        # Если quiz_start_time timezone-naive, считаем его UTC и делаем aware
                        else:
                            quiz_start_time = quiz_start_time.replace(tzinfo=timezone.utc)
                        time_diff = current_time - quiz_start_time

                        # Если викторина старше 2 часов, пропускаем
                        if time_diff.total_seconds() > 7200:  # 2 часа
                            logger.warning(f"Викторина чата {chat_id} слишком старая ({time_diff}), пропускаем")
                            continue

                    valid_quizzes[chat_id] = quiz_data
                    logger.debug(f"Восстановлена викторина чата {chat_id}")

                except Exception as e:
                    logger.error(f"Ошибка при обработке викторины чата {chat_id_str}: {e}")
                    continue

            logger.info(f"✅ Доступно для восстановления {len(valid_quizzes)} актуальных викторин")
            return valid_quizzes

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки активных викторин: {e}")
            return {}

    def cleanup_stale_quizzes(self) -> None:
        """
        Очищает файл активных викторин от устаревших записей.
        Вызывается автоматически при запуске бота.
        """
        active_quizzes_file = self.get_active_quizzes_file_path()

        if not active_quizzes_file.exists():
            return

        try:
            # Загружаем текущие данные
            current_data = self.load_active_quizzes()

            if not current_data:
                # Если нет валидных викторин, удаляем файл
                active_quizzes_file.unlink()
                logger.info("Файл активных викторин очищен (нет валидных викторин)")
                return

            # Пересохраняем только валидные викторины
            with open(active_quizzes_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "active_quizzes": {
                        str(chat_id): quiz_data
                        for chat_id, quiz_data in current_data.items()
                    }
                }, f, ensure_ascii=False, indent=2)

            logger.info(f"Очищено, осталось {len(current_data)} актуальных викторин")

        except Exception as e:
            logger.error(f"Ошибка очистки устаревших викторин: {e}")

    def delete_active_quizzes_file(self) -> None:
        """Удаляет файл активных викторин (при успешном завершении всех викторин)"""
        active_quizzes_file = self.get_active_quizzes_file_path()
        if active_quizzes_file.exists():
            active_quizzes_file.unlink()
            logger.info("Файл активных викторин удален")

    # ===== СИСТЕМА УПРАВЛЕНИЯ ТЕХНИЧЕСКИМ ОБСЛУЖИВАНИЕМ =====

    def get_maintenance_file_path(self) -> Path:
        """Возвращает путь к файлу состояния технического обслуживания"""
        return Path(self.app_config.paths.config_dir) / "maintenance_status.json"

    def enable_maintenance_mode(self, reason: str = "Техническое обслуживание") -> None:
        """
        Включает режим технического обслуживания.
        Сохраняет состояние и время начала обслуживания.
        """
        maintenance_file = self.get_maintenance_file_path()
        maintenance_file.parent.mkdir(parents=True, exist_ok=True)

        maintenance_data = {
            "maintenance_mode": True,
            "reason": reason,
            "start_time": datetime.now().isoformat(),
            "chats_notified": [],  # Чаты, которым отправили уведомления
            "notification_messages": []  # ID отправленных сообщений об обслуживании
        }

        try:
            with open(maintenance_file, 'w', encoding='utf-8') as f:
                json.dump(maintenance_data, f, ensure_ascii=False, indent=2)
            logger.info(f"✅ Режим технического обслуживания включен: {reason}")
        except Exception as e:
            logger.error(f"❌ Ошибка включения режима обслуживания: {e}")

    def disable_maintenance_mode(self) -> Dict[str, Any]:
        """
        Выключает режим технического обслуживания.
        Возвращает данные для очистки уведомлений.
        """
        maintenance_file = self.get_maintenance_file_path()

        if not maintenance_file.exists():
            logger.info("Режим обслуживания уже выключен")
            return {}

        try:
            with open(maintenance_file, 'r', encoding='utf-8') as f:
                maintenance_data = json.load(f)

            # Удаляем файл обслуживания
            maintenance_file.unlink()
            logger.info("✅ Режим технического обслуживания выключен")

            return maintenance_data

        except Exception as e:
            logger.error(f"❌ Ошибка выключения режима обслуживания: {e}")
            return {}

    def is_maintenance_mode(self) -> bool:
        """Проверяет, включен ли режим технического обслуживания"""
        maintenance_file = self.get_maintenance_file_path()
        if not maintenance_file.exists():
            return False

        try:
            with open(maintenance_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get("maintenance_mode", False)
        except Exception as e:
            logger.warning(f"Ошибка чтения файла обслуживания: {e}")
            return False

    def get_maintenance_status(self) -> Dict[str, Any]:
        """Возвращает статус технического обслуживания"""
        maintenance_file = self.get_maintenance_file_path()
        if not maintenance_file.exists():
            return {"maintenance_mode": False}

        try:
            with open(maintenance_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка чтения статуса обслуживания: {e}")
            return {"maintenance_mode": False}

    def add_maintenance_notification(self, chat_id: int, message_id: int) -> None:
        """
        Добавляет информацию об отправленном уведомлении об обслуживании.
        Это нужно для последующей очистки сообщений при запуске бота.
        """
        if not self.is_maintenance_mode():
            return

        try:
            maintenance_data = self.get_maintenance_status()

            # Добавляем чат в список уведомленных
            if chat_id not in maintenance_data.get("chats_notified", []):
                maintenance_data.setdefault("chats_notified", []).append(chat_id)

            # Добавляем ID сообщения для удаления
            maintenance_data.setdefault("notification_messages", []).append({
                "chat_id": chat_id,
                "message_id": message_id,
                "timestamp": datetime.now().isoformat()
            })

            # Сохраняем обновленные данные
            maintenance_file = self.get_maintenance_file_path()
            with open(maintenance_file, 'w', encoding='utf-8') as f:
                json.dump(maintenance_data, f, ensure_ascii=False, indent=2)

            logger.debug(f"Добавлено уведомление об обслуживании: чат {chat_id}, сообщение {message_id}")

        except Exception as e:
            logger.error(f"Ошибка добавления уведомления об обслуживании: {e}")
