#!/usr/bin/env python3
"""
Универсальный скрипт конвертации изображений в WebP и добавления метаданных
Поддерживает PNG, JPG, JPEG, BMP, TIFF, GIF
Автоматически генерирует метаданные для фото-викторины
"""

import os
import json
import sys
from pathlib import Path
import logging

# Проверяем наличие Pillow
try:
    from PIL import Image
except ImportError:
    print("❌ ОШИБКА: Библиотека Pillow не установлена!")
    print("📦 Установите её одной из команд:")
    print("   sudo apt install python3-pil")
    print("   или")
    print("   pip install --user Pillow")
    print("   или")
    print("   pip install --break-system-packages Pillow")
    sys.exit(1)

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def normalize_name(name: str) -> str:
    """Нормализует имя, убирая номера в конце (например, 'Лиса2' -> 'Лиса')"""
    import re
    # Убираем номера в конце имени (например, "Лиса2" -> "Лиса")
    normalized = re.sub(r'\d+$', '', name)
    return normalized.strip()

def generate_hints(correct_answer):
    """
    Генерирует подсказки на основе правильного ответа
    
    Args:
        correct_answer: Правильный ответ
        
    Returns:
        dict: Словарь с подсказками
    """
    length = len(correct_answer)
    first_letter = correct_answer[0] if correct_answer else "?"
    
    # Генерируем частичную подсказку
    if length <= 2:
        partial = correct_answer
    elif length <= 4:
        # Для коротких слов показываем первую и последнюю буквы
        partial = f"{correct_answer[0]}{'_' * (length - 2)}{correct_answer[-1]}"
    else:
        # Для длинных слов показываем первую букву и несколько последних
        partial = f"{correct_answer[0]}{'_' * (length - 4)}{correct_answer[-3:]}"
    
    return {
        "length": length,
        "first_letter": first_letter,
        "partial": partial,
        "fifth_letter": first_letter  # Для совместимости
    }

def load_metadata():
    """Загружает существующие метаданные"""
    metadata_file = Path("data/photo_quiz_metadata.json")
    
    if metadata_file.exists():
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки метаданных: {e}")
            return {}
    else:
        logger.warning("Файл метаданных не найден, создаю новый")
        return {}

def save_metadata(metadata):
    """Сохраняет метаданные в файл"""
    metadata_file = Path("data/photo_quiz_metadata.json")
    
    try:
        # Создаем папку data если её нет
        metadata_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ Метаданные сохранены в {metadata_file}")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения метаданных: {e}")

def convert_and_add_metadata(source_dir="data/images", quality=85):
    """
    Конвертирует изображения в WebP и добавляет метаданные
    
    Args:
        source_dir: Папка с изображениями
        quality: Качество WebP (1-100)
    """
    images_dir = Path(source_dir)
    
    if not images_dir.exists():
        logger.error(f"Папка {source_dir} не найдена!")
        return
    
    # Загружаем существующие метаданные
    metadata = load_metadata()
    
    # Находим все изображения кроме WebP
    image_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.gif'}
    image_files = [f for f in images_dir.iterdir() 
                   if f.is_file() and f.suffix.lower() in image_extensions]
    
    if not image_files:
        logger.info("Изображения для конвертации не найдены")
        return
    
    logger.info(f"Найдено {len(image_files)} изображений для конвертации")
    
    converted = 0
    added_metadata = 0
    total_saved = 0
    
    for image_file in image_files:
        try:
            # Получаем имя без расширения и нормализуем его
            image_name = image_file.stem
            correct_answer = normalize_name(image_name)
            
            # Открываем изображение
            with Image.open(image_file) as img:
                # Конвертируем в RGB если нужно
                if img.mode in ('RGBA', 'LA', 'P'):
                    # Создаем белый фон для прозрачных изображений
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Создаем WebP файл
                webp_file = image_file.with_suffix('.webp')
                original_size = image_file.stat().st_size
                
                # Сохраняем в WebP
                img.save(webp_file, 'WebP', quality=quality, optimize=True)
                
                # Считаем экономию
                webp_size = webp_file.stat().st_size
                saved = original_size - webp_size
                total_saved += saved
                
                logger.info(f"✅ {image_file.name} -> {webp_file.name} (сэкономлено: {saved:,} байт)")
                
                # Добавляем метаданные если их еще нет (используем нормализованное имя)
                if correct_answer not in metadata:
                    hints = generate_hints(correct_answer)
                    metadata[correct_answer] = {
                        "correct_answer": correct_answer,
                        "hints": hints
                    }
                    added_metadata += 1
                    logger.info(f"📝 Добавлены метаданные для: {correct_answer} (из {image_name})")
                else:
                    logger.info(f"ℹ️ Метаданные для {correct_answer} уже существуют (из {image_name})")
                
                # Удаляем оригинальный файл
                image_file.unlink()
                converted += 1
                
        except Exception as e:
            logger.error(f"❌ Ошибка конвертации {image_file.name}: {e}")
    
    # Сохраняем обновленные метаданные
    if added_metadata > 0:
        save_metadata(metadata)
    
    logger.info(f"🎉 Конвертировано: {converted} файлов")
    logger.info(f"📝 Добавлено метаданных: {added_metadata} записей")
    logger.info(f"💾 Сэкономлено: {total_saved / 1024 / 1024:.2f} MB")

def add_metadata_for_existing_webp(source_dir="data/images"):
    """
    Добавляет метаданные для уже существующих WebP файлов
    
    Args:
        source_dir: Папка с изображениями
    """
    images_dir = Path(source_dir)
    
    if not images_dir.exists():
        logger.error(f"Папка {source_dir} не найдена!")
        return
    
    # Загружаем существующие метаданные
    metadata = load_metadata()
    
    # Находим все WebP файлы
    webp_files = [f for f in images_dir.iterdir() 
                  if f.is_file() and f.suffix.lower() == '.webp']
    
    if not webp_files:
        logger.info("WebP изображения не найдены")
        return
    
    logger.info(f"Найдено {len(webp_files)} WebP изображений")
    
    added_metadata = 0
    
    for webp_file in webp_files:
        try:
            correct_answer = webp_file.stem
            
            # Добавляем метаданные если их еще нет
            if correct_answer not in metadata:
                hints = generate_hints(correct_answer)
                metadata[correct_answer] = {
                    "correct_answer": correct_answer,
                    "hints": hints
                }
                added_metadata += 1
                logger.info(f"📝 Добавлены метаданные для: {correct_answer}")
            else:
                logger.info(f"ℹ️ Метаданные для {correct_answer} уже существуют")
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки {webp_file.name}: {e}")
    
    # Сохраняем обновленные метаданные
    if added_metadata > 0:
        save_metadata(metadata)
    
    logger.info(f"📝 Добавлено метаданных: {added_metadata} записей")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--metadata-only":
        # Режим только добавления метаданных для существующих WebP
        add_metadata_for_existing_webp()
    else:
        # Обычный режим конвертации + метаданные
        convert_and_add_metadata()
