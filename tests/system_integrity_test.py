#!/usr/bin/env python3
"""
Тест целостности системы Morning Quiz Bot
Проверяет основные компоненты без запуска бота
"""

import sys
import os
from pathlib import Path

# Добавляем корень проекта в sys.path для корректных импортов
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_imports():
    """Тестирует импорты основных модулей"""
    print("Тестирование импортов...")
    
    try:
        from app_config import AppConfig
        print("AppConfig импортирован")
        
        from state import BotState
        print("BotState импортирован")
        
        from data_manager import DataManager
        print("DataManager импортирован")
        
        from backup_manager import BackupManager
        print("BackupManager импортирован")
        
        from handlers.poll_answer_handler import CustomPollAnswerHandler
        print("CustomPollAnswerHandler импортирован")
        
        from utils import escape_markdown_v2, get_current_utc_time
        print("Utils импортированы")
        
        return True
        
    except Exception as e:
        print(f"Ошибка импорта: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_configuration():
    """Тестирует загрузку конфигурации"""
    print("\nТестирование конфигурации...")
    
    try:
        from app_config import AppConfig
        
        app_config = AppConfig()
        print("AppConfig загружен")
        
        # Проверяем основные настройки
        print(f"   - Максимум вопросов: {app_config.max_questions_per_session}")
        print(f"   - Максимум длина вопроса: {app_config.max_poll_question_length}")
        print(f"   - Максимум длина опции: {app_config.max_poll_option_length}")
        
        # Проверяем команды
        commands = app_config.commands
        print(f"   - Команда quiz: /{commands.quiz}")
        print(f"   - Команда help: /{commands.help}")
        print(f"   - Команда categories: /{commands.categories}")
        
        return True
        
    except Exception as e:
        print(f"Ошибка конфигурации: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_data_structure():
    """Тестирует структуру данных"""
    print("\nТестирование структуры данных...")
    
    try:
        data_dir = project_root / "data"
        if not data_dir.exists():
            print("Папка data не найдена")
            return False
        
        # Проверяем обязательные директории
        required_dirs = ["chats", "global", "statistics", "system", "questions"]
        for dir_name in required_dirs:
            dir_path = data_dir / dir_name
            if not dir_path.exists():
                print(f"Папка {dir_name} не найдена")
                return False
            print(f"Папка {dir_name} найдена")
        
        # Проверяем файлы категорий
        questions_dir = data_dir / "questions"
        category_files = list(questions_dir.glob("*.json"))
        print(f"Найдено {len(category_files)} файлов категорий")
        
        # Проверяем чаты
        chats_dir = data_dir / "chats"
        chat_dirs = [d for d in chats_dir.iterdir() if d.is_dir()]
        print(f"Найдено {len(chat_dirs)} чатов")
        
        return True
        
    except Exception as e:
        print(f"Ошибка проверки структуры: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_data_loading():
    """Тестирует загрузку данных"""
    print("\nТестирование загрузки данных...")
    
    try:
        from app_config import AppConfig
        from state import BotState
        from data_manager import DataManager
        
        # Создаем объекты
        app_config = AppConfig()
        state = BotState(app_config)
        data_manager = DataManager(app_config, state)
        
        print("Объекты созданы")
        
        # Загружаем данные
        data_manager.load_all_data()
        print("Данные загружены")
        
        # Проверяем загруженные данные
        print(f"   - Чатов: {len(state.chat_settings)}")
        print(f"   - Пользователей: {sum(len(users) for users in state.user_scores.values())}")
        print(f"   - Категорий вопросов: {len(state.quiz_data)}")
        print(f"   - Всего вопросов: {sum(len(questions) for questions in state.quiz_data.values())}")
        
        return True
        
    except Exception as e:
        print(f"Ошибка загрузки данных: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_handlers():
    """Тестирует импорт обработчиков"""
    print("\nТестирование обработчиков...")
    
    try:
        # Проверяем основные обработчики
        from handlers.common_handlers import CommonHandlers
        print("CommonHandlers импортирован")
        
        from handlers.quiz_manager import QuizManager
        print("QuizManager импортирован")
        
        from handlers.config_handlers import ConfigHandlers
        print("ConfigHandlers импортирован")
        
        from handlers.rating_handlers import RatingHandlers
        print("RatingHandlers импортирован")
        
        from handlers.backup_handlers import BackupHandlers
        print("BackupHandlers импортирован")
        
        from handlers.cleanup_handler import schedule_cleanup_job
        print("CleanupHandler импортирован")
        
        from handlers.daily_quiz_scheduler import DailyQuizScheduler
        print("DailyQuizScheduler импортирован")
        
        return True
        
    except Exception as e:
        print(f"Ошибка импорта обработчиков: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_modules():
    """Тестирует импорт модулей логики"""
    print("\nТестирование модулей логики...")
    
    try:
        from modules.category_manager import CategoryManager
        print("CategoryManager импортирован")
        
        from modules.score_manager import ScoreManager
        print("ScoreManager импортирован")
        
        from modules.quiz_engine import QuizEngine
        print("QuizEngine импортирован")
        
        return True
        
    except Exception as e:
        print(f"Ошибка импорта модулей: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Основная функция тестирования"""
    print("Запуск теста целостности системы Morning Quiz Bot")
    print("=" * 60)
    
    success = True
    
    # Тестируем импорты
    if not test_imports():
        success = False
    
    # Тестируем конфигурацию
    if not test_configuration():
        success = False
    
    # Тестируем структуру данных
    if not test_data_structure():
        success = False
    
    # Тестируем загрузку данных
    if not test_data_loading():
        success = False
    
    # Тестируем обработчики
    if not test_handlers():
        success = False
    
    # Тестируем модули
    if not test_modules():
        success = False
    
    print("\n" + "=" * 60)
    if success:
        print("Все тесты пройдены успешно!")
        print("Система готова к работе")
        print("Все компоненты загружаются корректно")
        print("Структура данных в порядке")
    else:
        print("Некоторые тесты не пройдены")
        print("Есть проблемы, которые нужно исправить")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
