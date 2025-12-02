#!/usr/bin/env python3
"""
Скрипт для создания полного бэкапа проекта Morning Quiz Bot

Создает архив со всеми файлами проекта, исключая:
- venv/ (виртуальное окружение)
- __pycache__/ (кэш Python)
- .git/ (система контроля версий)
- logs/ (логи)
- временные файлы
"""

import os
import zipfile
import datetime
from pathlib import Path

def create_full_backup():
    """Создает полный бэкап проекта"""
    
    # Получаем текущую дату и время для имени архива
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"morning_quiz_bot_full_backup_{timestamp}"
    backup_path = f"backups/{backup_name}.zip"
    
    # Создаем папку backups если её нет
    os.makedirs("backups", exist_ok=True)
    
    # Папки и файлы для исключения
    exclude_dirs = {
        "venv", "__pycache__", ".git", "logs", 
        "node_modules", ".vscode", ".idea"
    }
    
    exclude_files = {
        ".DS_Store", "Thumbs.db", "*.tmp", "*.log",
        "*.pyc", "*.pyo", "*.pyd"
    }
    
    print(f"🔄 Создание полного бэкапа проекта...")
    print(f"📁 Исключаемые папки: {', '.join(exclude_dirs)}")
    print(f"📄 Исключаемые файлы: {', '.join(exclude_files)}")
    
    # Создаем ZIP архив
    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Проходим по всем файлам и папкам
        for root, dirs, files in os.walk('.'):
            # Исключаем ненужные папки
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            # Пропускаем папку backups (чтобы не включать старые бэкапы)
            if 'backups' in root:
                continue
                
            # Обрабатываем файлы
            for file in files:
                file_path = os.path.join(root, file)
                
                # Пропускаем сам архив бэкапа
                if file_path == backup_path:
                    continue
                    
                # Проверяем расширения файлов для исключения
                should_exclude = False
                for exclude_pattern in exclude_files:
                    if exclude_pattern.startswith('*'):
                        if file.endswith(exclude_pattern[1:]):
                            should_exclude = True
                            break
                    elif file == exclude_pattern:
                        should_exclude = True
                        break
                
                if should_exclude:
                    continue
                
                # Добавляем файл в архив
                try:
                    # Относительный путь для архива
                    arcname = os.path.relpath(file_path, '.')
                    zipf.write(file_path, arcname)
                    print(f"✅ Добавлен: {arcname}")
                except Exception as e:
                    print(f"⚠️ Ошибка добавления {file_path}: {e}")
    
    # Получаем размер архива
    archive_size = os.path.getsize(backup_path)
    size_mb = archive_size / (1024 * 1024)
    
    print(f"\n🎉 Полный бэкап создан успешно!")
    print(f"📦 Файл: {backup_path}")
    print(f"📏 Размер: {size_mb:.2f} MB")
    print(f"🕐 Время создания: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Создаем README файл с описанием бэкапа
    readme_content = f"""# Morning Quiz Bot - Полный бэкап

## Информация о бэкапе
- **Дата создания**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **Версия**: Полный бэкап проекта
- **Размер**: {size_mb:.2f} MB

## Что включено в бэкап
- ✅ Все исходные файлы Python
- ✅ Конфигурационные файлы
- ✅ Документация
- ✅ Модули и обработчики
- ✅ Система ачивок (включая новые streak ачивки)
- ✅ Настройки и конфигурации

## Что исключено
- ❌ Виртуальное окружение (venv/)
- ❌ Кэш Python (__pycache__/)
- ❌ Логи (logs/)
- ❌ Система контроля версий (.git/)
- ❌ Временные файлы

## Как восстановить
1. Распакуйте архив в новую папку
2. Создайте виртуальное окружение: `python -m venv venv`
3. Активируйте окружение: `venv\\Scripts\\activate` (Windows) или `source venv/bin/activate` (Linux/Mac)
4. Установите зависимости: `pip install -r requirements.txt`
5. Настройте переменные окружения в `.env` файле
6. Запустите бота: `python bot.py`

## Особенности этой версии
- 🔥 Исправлена система ачивок (streak ачивки не отправляются в личку)
- 🗑️ Streak ачивки удаляются немедленно при показе результатов
- 💎 Чатовые ачивки остаются в чате навсегда
- 🎲 Streak ачивки загружаются из data/system/streak_achievements.json
- 🎯 Случайные сообщения для streak ачивок (5 вариантов для каждого уровня)
- ⚡ Streak бонусы за серию правильных ответов
"""
    
    readme_path = f"backups/{backup_name}_README.md"
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(readme_content)
    
    print(f"📝 Создан README файл: {readme_path}")
    
    return backup_path

if __name__ == "__main__":
    try:
        backup_file = create_full_backup()
        print(f"\n🚀 Бэкап готов! Файл: {backup_file}")
    except Exception as e:
        print(f"💥 Ошибка создания бэкапа: {e}")
        import traceback
        traceback.print_exc()
