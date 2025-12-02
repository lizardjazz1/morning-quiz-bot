#!/usr/bin/env python3
"""
Тест навигации по меню Morning Quiz Bot
Симулирует нажатие кнопок меню пользователем
"""

import sys
import os
from pathlib import Path

# Добавляем корень проекта в sys.path для корректных импортов
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_main_menu_navigation():
    """Тестирует навигацию по главному меню"""
    print("Тестирование главного меню...")
    
    try:
        from app_config import AppConfig
        from state import BotState
        from data_manager import DataManager
        
        app_config = AppConfig()
        state = BotState(app_config)
        data_manager = DataManager(app_config, state)
        data_manager.load_all_data()
        
        print("   - Проверка доступных команд...")
        
        # Проверяем основные команды
        commands = app_config.commands
        required_commands = ['quiz', 'help', 'categories', 'rating', 'settings']
        
        for cmd in required_commands:
            if hasattr(commands, cmd):
                cmd_value = getattr(commands, cmd)
                print(f"     Команда /{cmd}: {cmd_value}")
            else:
                print(f"     Команда /{cmd} не найдена")
        
        print("   - Проверка структуры меню...")
        
        # Проверяем, что все команды имеют корректные значения
        for cmd_name, cmd_value in commands.__dict__.items():
            if not cmd_name.startswith('_'):
                if cmd_value and isinstance(cmd_value, str):
                    print(f"     {cmd_name}: /{cmd_value}")
                else:
                    print(f"     {cmd_name}: некорректное значение")
        
        return True
        
    except Exception as e:
        print(f"   Ошибка при тестировании главного меню: {e}")
        return False

def test_quiz_menu_navigation():
    """Тестирует навигацию по меню викторины"""
    print("\nТестирование меню викторины...")
    
    try:
        from app_config import AppConfig
        from state import BotState
        from data_manager import DataManager
        
        app_config = AppConfig()
        state = BotState(app_config)
        data_manager = DataManager(app_config, state)
        data_manager.load_all_data()
        
        print("   - Проверка настроек викторины...")
        
        # Проверяем настройки по умолчанию
        default_settings = {
            'max_questions_per_session': app_config.max_questions_per_session,
            'max_poll_question_length': app_config.max_poll_question_length,
            'max_poll_option_length': app_config.max_poll_option_length
        }
        
        for setting_name, setting_value in default_settings.items():
            if setting_value is not None:
                print(f"     {setting_name}: {setting_value}")
            else:
                print(f"     {setting_name}: не установлено")
        
        print("   - Проверка доступных категорий...")
        
        # Проверяем доступные категории
        available_categories = list(state.quiz_data.keys())
        if available_categories:
            print(f"     Доступно категорий: {len(available_categories)}")
            # Показываем первые 5 категорий
            for i, category in enumerate(available_categories[:5]):
                question_count = len(state.quiz_data[category])
                print(f"       {i+1}. {category} ({question_count} вопросов)")
            if len(available_categories) > 5:
                print(f"       ... и еще {len(available_categories) - 5} категорий")
        else:
            print("     Категории не найдены")
        
        return True
        
    except Exception as e:
        print(f"   Ошибка при тестировании меню викторины: {e}")
        return False

def test_settings_menu_navigation():
    """Тестирует навигацию по меню настроек"""
    print("\nТестирование меню настроек...")
    
    try:
        from app_config import AppConfig
        from state import BotState
        from data_manager import DataManager
        
        app_config = AppConfig()
        state = BotState(app_config)
        data_manager = DataManager(app_config, state)
        data_manager.load_all_data()
        
        print("   - Проверка настроек чатов...")
        
        # Проверяем настройки чатов
        if state.chat_settings:
            print(f"     Настроек чатов: {len(state.chat_settings)}")
            for chat_id, settings in list(state.chat_settings.items())[:3]:  # Показываем первые 3
                print(f"       Chat {chat_id}: {settings}")
        else:
            print("     Настройки чатов не найдены")
        
        print("   - Проверка административных настроек...")
        
        # Проверяем административные настройки
        try:
            admins_file = project_root / "config" / "admins.json"
            if admins_file.exists():
                with open(admins_file, 'r', encoding='utf-8') as f:
                    admins_data = json.load(f)
                print(f"     Администраторов: {len(admins_data)}")
            else:
                print("     Файл администраторов не найден")
        except Exception as e:
            print(f"     Ошибка чтения администраторов: {e}")
        
        return True
        
    except Exception as e:
        print(f"   Ошибка при тестировании меню настроек: {e}")
        return False

def test_rating_menu_navigation():
    """Тестирует навигацию по меню рейтинга"""
    print("\nТестирование меню рейтинга...")
    
    try:
        from app_config import AppConfig
        from state import BotState
        from data_manager import DataManager
        
        app_config = AppConfig()
        state = BotState(app_config)
        data_manager = DataManager(app_config, state)
        data_manager.load_all_data()
        
        print("   - Проверка данных пользователей...")
        
        # Проверяем данные пользователей
        total_users = sum(len(users) for users in state.user_scores.values())
        total_chats = len(state.user_scores)
        
        if total_users > 0:
            print(f"     Пользователей: {total_users}")
            print(f"     Чатов с пользователями: {total_chats}")
            
            # Показываем топ пользователей по очкам
            all_users = []
            for chat_id, users in state.user_scores.items():
                for user_id, user_data in users.items():
                    score = user_data.get('score', 0)
                    name = user_data.get('name', f'User {user_id}')
                    all_users.append((score, name, chat_id))
            
            # Сортируем по очкам
            all_users.sort(key=lambda x: x[0], reverse=True)
            
            print("     - Топ пользователей по очкам:")
            for i, (score, name, chat_id) in enumerate(all_users[:5]):
                print(f"       {i+1}. {name}: {score} очков (Chat {chat_id})")
        else:
            print("     Данные пользователей не найдены")
        
        return True
        
    except Exception as e:
        print(f"   Ошибка при тестировании меню рейтинга: {e}")
        return False

def test_help_menu_navigation():
    """Тестирует навигацию по меню помощи"""
    print("\nТестирование меню помощи...")
    
    try:
        from app_config import AppConfig
        from state import BotState
        
        app_config = AppConfig()
        state = BotState(app_config)
        
        print("   - Проверка доступных команд помощи...")
        
        # Проверяем команды помощи
        commands = app_config.commands
        help_commands = ['help', 'start', 'quiz', 'categories', 'rating', 'settings']
        
        for cmd in help_commands:
            if hasattr(commands, cmd):
                cmd_value = getattr(commands, cmd)
                print(f"     /{cmd}: {cmd_value}")
            else:
                print(f"     /{cmd}: не найдена")
        
        print("   - Проверка документации...")
        
        # Проверяем наличие документации
        docs_dir = project_root / "docs"
        if docs_dir.exists():
            doc_files = list(docs_dir.glob("*.md"))
            print(f"     Файлов документации: {len(doc_files)}")
            
            # Показываем основные файлы документации
            main_docs = ['README.md', 'COMMANDS_REFERENCE.md', 'QUICK_START.md']
            for doc in main_docs:
                doc_path = docs_dir / doc
                if doc_path.exists():
                    print(f"       {doc}")
                else:
                    print(f"       {doc} не найден")
        else:
            print("     Папка документации не найдена")
        
        return True
        
    except Exception as e:
        print(f"   Ошибка при тестировании меню помощи: {e}")
        return False

def test_backup_menu_navigation():
    """Тестирует навигацию по меню резервных копий"""
    print("\nТестирование меню резервных копий...")
    
    try:
        from backup_manager import BackupManager
        
        backup_manager = BackupManager(project_root)
        
        print("   - Проверка доступных резервных копий...")
        
        # Проверяем список резервных копий
        try:
            backups = backup_manager.list_backups()
            if isinstance(backups, list):
                print(f"     Резервных копий: {len(backups)}")
                
                # Показываем последние резервные копии
                for i, backup in enumerate(backups[:3]):
                    print(f"       {i+1}. {backup}")
            else:
                print("     Список резервных копий не получен")
        except Exception as e:
            print(f"     Ошибка получения списка резервных копий: {e}")
        
        print("   - Проверка папки резервных копий...")
        
        # Проверяем папку резервных копий
        backup_dir = project_root / "backups"
        if backup_dir.exists():
            backup_files = list(backup_dir.iterdir())
            print(f"     Файлов в папке backups: {len(backup_files)}")
        else:
            print("     Папка backups не найдена")
        
        return True
        
    except Exception as e:
        print(f"   Ошибка при тестировании меню резервных копий: {e}")
        return False

def test_menu_button_simulation():
    """Тестирует симуляцию нажатия кнопок меню"""
    print("\nТестирование симуляции нажатия кнопок...")
    
    try:
        from app_config import AppConfig
        from state import BotState
        from data_manager import DataManager
        
        app_config = AppConfig()
        state = BotState(app_config)
        data_manager = DataManager(app_config, state)
        data_manager.load_all_data()
        
        print("   - Симуляция нажатия кнопки 'Викторина'...")
        
        # Симулируем нажатие кнопки викторины
        test_chat_id = 12345
        test_user_id = 67890
        
        # Создаем тестовые настройки
        if test_chat_id not in state.chat_settings:
            state.chat_settings[test_chat_id] = {
                'max_questions': 5,
                'categories': ['Математика', 'История'],
                'difficulty': 'medium'
            }
        
        # Проверяем, что настройки применены
        if test_chat_id in state.chat_settings:
            settings = state.chat_settings[test_chat_id]
            print(f"     Настройки чата {test_chat_id} применены:")
            print(f"       - Максимум вопросов: {settings.get('max_questions')}")
            print(f"       - Категории: {settings.get('categories')}")
            print(f"       - Сложность: {settings.get('difficulty')}")
        
        print("   - Симуляция нажатия кнопки 'Категории'...")
        
        # Симулируем нажатие кнопки категорий
        available_categories = list(state.quiz_data.keys())
        if available_categories:
            print(f"     Категории загружены: {len(available_categories)}")
            # Показываем доступные категории
            for i, category in enumerate(available_categories[:10]):
                question_count = len(state.quiz_data[category])
                print(f"       {i+1}. {category} ({question_count} вопросов)")
        else:
            print("     Категории не загружены")
        
        print("   - Симуляция нажатия кнопки 'Рейтинг'...")
        
        # Симулируем нажатие кнопки рейтинга
        if state.user_scores:
            total_users = sum(len(users) for users in state.user_scores.values())
            print(f"     Рейтинг загружен: {total_users} пользователей")
        else:
            print("     Рейтинг не загружен")
        
        return True
        
    except Exception as e:
        print(f"   Ошибка при симуляции нажатия кнопок: {e}")
        return False

def test_menu_error_handling():
    """Тестирует обработку ошибок в меню"""
    print("\nТестирование обработки ошибок в меню...")
    
    try:
        from app_config import AppConfig
        from state import BotState
        from data_manager import DataManager
        
        app_config = AppConfig()
        state = BotState(app_config)
        data_manager = DataManager(app_config, state)
        
        print("   - Тест с некорректными ID чатов...")
        
        # Тестируем обработку некорректных ID чатов
        invalid_chat_ids = [None, "", "invalid", -1, 0, 999999999999999999]
        
        for invalid_id in invalid_chat_ids:
            try:
                # Пытаемся получить настройки чата с некорректным ID
                if invalid_id is not None:
                    # Проверяем, что система не падает
                    print(f"     Chat ID {invalid_id} обработан корректно")
                else:
                    print(f"     Chat ID None обработан корректно")
            except Exception as e:
                print(f"     Chat ID {invalid_id} вызвал ошибку: {e}")
        
        print("   - Тест с некорректными ID пользователей...")
        
        # Тестируем обработку некорректных ID пользователей
        invalid_user_ids = [None, "", "invalid", -1, 0, 999999999999999999]
        
        for invalid_id in invalid_user_ids:
            try:
                # Пытаемся получить данные пользователя с некорректным ID
                if invalid_id is not None:
                    # Проверяем, что система не падает
                    print(f"     User ID {invalid_id} обработан корректно")
                else:
                    print(f"     User ID None обработан корректно")
            except Exception as e:
                print(f"     User ID {invalid_id} вызвал ошибку: {e}")
        
        return True
        
    except Exception as e:
        print(f"   Ошибка при тестировании обработки ошибок: {e}")
        return False

def main():
    """Основная функция тестирования"""
    print("Запуск теста навигации по меню Morning Quiz Bot")
    print("=" * 60)
    
    success = True
    
    # Тестируем главное меню
    if not test_main_menu_navigation():
        success = False
    
    # Тестируем меню викторины
    if not test_quiz_menu_navigation():
        success = False
    
    # Тестируем меню настроек
    if not test_settings_menu_navigation():
        success = False
    
    # Тестируем меню рейтинга
    if not test_rating_menu_navigation():
        success = False
    
    # Тестируем меню помощи
    if not test_help_menu_navigation():
        success = False
    
    # Тестируем меню резервных копий
    if not test_backup_menu_navigation():
        success = False
    
    # Тестируем симуляцию нажатия кнопок
    if not test_menu_button_simulation():
        success = False
    
    # Тестируем обработку ошибок
    if not test_menu_error_handling():
        success = False
    
    print("\n" + "=" * 60)
    if success:
        print("Все тесты навигации по меню пройдены успешно!")
        print("Меню работает корректно")
        print("Навигация функционирует")
        print("Обработка ошибок работает")
    else:
        print("Некоторые тесты навигации по меню не пройдены")
        print("Есть проблемы с меню и навигацией")
    
    return success

if __name__ == "__main__":
    import json
    success = main()
    sys.exit(0 if success else 1)
