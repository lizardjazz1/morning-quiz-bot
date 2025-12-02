#backup_manager.py
import json
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import zipfile
import os

logger = logging.getLogger(__name__)

class BackupManager:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.backup_dir = project_root / "backups"
        self.backup_dir.mkdir(exist_ok=True)
        
        # Файлы для бекапа
        self.critical_files = [
            "data/questions.json",
            "data/users.json", 
            "data/chat_settings.json",
            "data/daily_quiz_subscriptions.json",
            "config/quiz_config.json",
            "config/admins.json"
        ]
        
        # Максимальное количество бекапов для хранения
        self.max_backups = 10
        
        logger.info(f"BackupManager инициализирован. Директория бекапов: {self.backup_dir}")
    
    def create_backup(self, backup_name: str = None, description: str = "") -> Tuple[bool, str]:
        """Создает бекап критических файлов системы
        
        Args:
            backup_name: Имя бекапа (если None, генерируется автоматически)
            description: Описание бекапа
            
        Returns:
            (success, backup_path_or_error_message)
        """
        try:
            # Генерируем имя бекапа если не указано
            if not backup_name:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_name = f"auto_backup_{timestamp}"
            
            # Создаем директорию для бекапа
            backup_path = self.backup_dir / backup_name
            backup_path.mkdir(exist_ok=True)
            
            # Создаем файл с метаданными
            metadata = {
                "backup_name": backup_name,
                "created_at": datetime.now().isoformat(),
                "description": description,
                "files_backed_up": [],
                "total_size_bytes": 0
            }
            
            total_size = 0
            backed_up_files = []
            
            # Копируем критические файлы
            for file_path in self.critical_files:
                source_path = self.project_root / file_path
                if source_path.exists():
                    # Создаем структуру директорий в бекапе
                    backup_file_path = backup_path / file_path
                    backup_file_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Копируем файл
                    shutil.copy2(source_path, backup_file_path)
                    
                    file_size = source_path.stat().st_size
                    total_size += file_size
                    backed_up_files.append({
                        "path": str(file_path),
                        "size_bytes": file_size,
                        "backed_up": True
                    })
                    
                    logger.debug(f"Файл {file_path} скопирован в бекап (размер: {file_size} байт)")
                else:
                    backed_up_files.append({
                        "path": str(file_path),
                        "size_bytes": 0,
                        "backed_up": False,
                        "error": "Файл не найден"
                    })
                    logger.warning(f"Файл {file_path} не найден для бекапа")
            
            # Обновляем метаданные
            metadata["files_backed_up"] = backed_up_files
            metadata["total_size_bytes"] = total_size
            
            # Сохраняем метаданные
            metadata_path = backup_path / "backup_metadata.json"
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            # Создаем ZIP архив для удобства
            zip_path = self.backup_dir / f"{backup_name}.zip"
            self._create_zip_archive(backup_path, zip_path)
            
            # Удаляем временную директорию
            shutil.rmtree(backup_path)
            
            # Очищаем старые бекапы
            self._cleanup_old_backups()
            
            logger.info(f"Бекап {backup_name} успешно создан. Размер: {total_size} байт")
            return True, str(zip_path)
            
        except Exception as e:
            error_msg = f"Ошибка при создании бекапа: {e}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg
    
    def _create_zip_archive(self, source_dir: Path, zip_path: Path) -> None:
        """Создает ZIP архив из директории"""
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in source_dir.rglob('*'):
                    if file_path.is_file():
                        arcname = file_path.relative_to(source_dir)
                        zipf.write(file_path, arcname)
            logger.debug(f"ZIP архив создан: {zip_path}")
        except Exception as e:
            logger.error(f"Ошибка при создании ZIP архива: {e}")
            raise
    
    def _cleanup_old_backups(self) -> None:
        """Удаляет старые бекапы, оставляя только последние max_backups"""
        try:
            # Получаем список всех ZIP бекапов
            backup_files = list(self.backup_dir.glob("*.zip"))
            
            if len(backup_files) <= self.max_backups:
                return
            
            # Сортируем по времени создания (новые в конце)
            backup_files.sort(key=lambda x: x.stat().st_mtime)
            
            # Удаляем старые бекапы
            files_to_remove = backup_files[:-self.max_backups]
            for file_path in files_to_remove:
                try:
                    file_path.unlink()
                    logger.info(f"Удален старый бекап: {file_path.name}")
                except Exception as e:
                    logger.warning(f"Не удалось удалить старый бекап {file_path.name}: {e}")
                    
        except Exception as e:
            logger.error(f"Ошибка при очистке старых бекапов: {e}")
    
    def list_backups(self) -> List[Dict[str, Any]]:
        """Возвращает список всех доступных бекапов"""
        try:
            backups = []
            for zip_path in self.backup_dir.glob("*.zip"):
                try:
                    # Получаем информацию о файле
                    stat = zip_path.stat()
                    created_time = datetime.fromtimestamp(stat.st_mtime)
                    
                    # Пытаемся прочитать метаданные из ZIP
                    metadata = self._extract_metadata_from_zip(zip_path)
                    
                    backup_info = {
                        "name": zip_path.stem,
                        "file_path": str(zip_path),
                        "size_bytes": stat.st_size,
                        "created_at": created_time.isoformat(),
                        "description": metadata.get("description", ""),
                        "files_count": len(metadata.get("files_backed_up", [])),
                        "total_size_backed_up": metadata.get("total_size_bytes", 0)
                    }
                    backups.append(backup_info)
                    
                except Exception as e:
                    logger.warning(f"Не удалось прочитать информацию о бекапе {zip_path.name}: {e}")
                    # Добавляем базовую информацию
                    stat = zip_path.stat()
                    created_time = datetime.fromtimestamp(stat.st_mtime)
                    backups.append({
                        "name": zip_path.stem,
                        "file_path": str(zip_path),
                        "size_bytes": stat.st_size,
                        "created_at": created_time.isoformat(),
                        "description": "Метаданные недоступны",
                        "files_count": 0,
                        "total_size_backed_up": 0
                    })
            
            # Сортируем по времени создания (новые в начале)
            backups.sort(key=lambda x: x["created_at"], reverse=True)
            return backups
            
        except Exception as e:
            logger.error(f"Ошибка при получении списка бекапов: {e}")
            return []
    
    def _extract_metadata_from_zip(self, zip_path: Path) -> Dict[str, Any]:
        """Извлекает метаданные из ZIP архива"""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                if "backup_metadata.json" in zipf.namelist():
                    with zipf.open("backup_metadata.json") as f:
                        metadata = json.load(f)
                        return metadata
        except Exception as e:
            logger.warning(f"Не удалось извлечь метаданные из {zip_path.name}: {e}")
        
        return {}
    
    def restore_backup(self, backup_name: str, target_dir: Path = None) -> Tuple[bool, str]:
        """Восстанавливает файлы из бекапа
        
        Args:
            backup_name: Имя бекапа для восстановления
            target_dir: Директория для восстановления (по умолчанию - корень проекта)
            
        Returns:
            (success, message)
        """
        try:
            if target_dir is None:
                target_dir = self.project_root
            
            zip_path = self.backup_dir / f"{backup_name}.zip"
            if not zip_path.exists():
                return False, f"Бекап {backup_name} не найден"
            
            # Создаем временную директорию для распаковки
            temp_dir = self.backup_dir / f"temp_restore_{int(time.time())}"
            temp_dir.mkdir(exist_ok=True)
            
            try:
                # Распаковываем ZIP
                with zipfile.ZipFile(zip_path, 'r') as zipf:
                    zipf.extractall(temp_dir)
                
                # Читаем метаданные
                metadata_path = temp_dir / "backup_metadata.json"
                if metadata_path.exists():
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                else:
                    return False, "Метаданные бекапа не найдены"
                
                # Восстанавливаем файлы
                restored_count = 0
                for file_info in metadata.get("files_backed_up", []):
                    if file_info.get("backed_up", False):
                        source_path = temp_dir / file_info["path"]
                        target_path = target_dir / file_info["path"]
                        
                        if source_path.exists():
                            # Создаем директории если нужно
                            target_path.parent.mkdir(parents=True, exist_ok=True)
                            
                            # Копируем файл
                            shutil.copy2(source_path, target_path)
                            restored_count += 1
                            logger.debug(f"Восстановлен файл: {file_info['path']}")
                
                # Очищаем временную директорию
                shutil.rmtree(temp_dir)
                
                logger.info(f"Бекап {backup_name} успешно восстановлен. Восстановлено файлов: {restored_count}")
                return True, f"Восстановлено файлов: {restored_count}"
                
            except Exception as e:
                # Очищаем временную директорию в случае ошибки
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
                raise
                
        except Exception as e:
            error_msg = f"Ошибка при восстановлении бекапа: {e}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg
    
    def delete_backup(self, backup_name: str) -> Tuple[bool, str]:
        """Удаляет указанный бекап"""
        try:
            zip_path = self.backup_dir / f"{backup_name}.zip"
            if not zip_path.exists():
                return False, f"Бекап {backup_name} не найден"
            
            zip_path.unlink()
            logger.info(f"Бекап {backup_name} удален")
            return True, f"Бекап {backup_name} успешно удален"
            
        except Exception as e:
            error_msg = f"Ошибка при удалении бекапа: {e}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg
    
    def get_backup_stats(self) -> Dict[str, Any]:
        """Возвращает статистику по бекапам"""
        try:
            backups = self.list_backups()
            
            total_backups = len(backups)
            total_size = sum(b["size_bytes"] for b in backups)
            total_files_backed_up = sum(b["files_count"] for b in backups)
            
            # Размер директории бекапов
            backup_dir_size = sum(f.stat().st_size for f in self.backup_dir.glob("*.zip"))
            
            return {
                "total_backups": total_backups,
                "total_size_bytes": total_size,
                "backup_dir_size_bytes": backup_dir_size,
                "total_files_backed_up": total_files_backed_up,
                "max_backups": self.max_backups,
                "oldest_backup": backups[-1]["created_at"] if backups else None,
                "newest_backup": backups[0]["created_at"] if backups else None
            }
            
        except Exception as e:
            logger.error(f"Ошибка при получении статистики бекапов: {e}")
            return {}
