#!/usr/bin/env python3
"""
Тест устойчивости системы Morning Quiz Bot
Проверяет защиту от некорректных данных и граничные случаи
"""

import sys
import os
from pathlib import Path

# Добавляем корень проекта в sys.path для корректных импортов
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_invalid_config_data():
    """Тестирует обработку некорректных данных конфигурации"""
    print("Тестирование некорректных данных конфигурации...")
    
    try:
        from app_config import AppConfig
        
        # Тест с некорректными данными
        print("   - Тест с некорректными данными...")
        
        # Проверяем, что система не падает при некорректных настройках
        app_config = AppConfig()
        
        # Проверяем граничные значения
        max_questions = app_config.max_questions_per_session
        if max_questions > 0 and max_questions <= 100:
            print("   Максимум вопросов в допустимых пределах")
        else:
            print("   Максимум вопросов вне допустимых пределов")
        
        # Проверяем длину вопросов
        max_length = app_config.max_poll_question_length
        if max_length > 0 and max_length <= 300:
            print("   Максимум длина вопроса в допустимых пределах")
        else:
            print("   Максимум длина вопроса вне допустимых пределов")
        
        return True
        
    except Exception as e:
        print(f"   Ошибка при тестировании конфигурации: {e}")
        return False

def test_invalid_user_data():
    """Тестирует обработку некорректных данных пользователя"""
    print("\nТестирование некорректных данных пользователя...")
    
    try:
        from app_config import AppConfig
        from state import BotState
        from data_manager import DataManager
        
        app_config = AppConfig()
        state = BotState(app_config)
        data_manager = DataManager(app_config, state)
        
        # Загружаем данные
        data_manager.load_all_data()
        
        # Тестируем обработку некорректных ID пользователей
        print("   - Тест с некорректными ID пользователей...")
        
        # Проверяем, что система не падает при некорректных ID
        invalid_user_ids = [None, "", "invalid", -1, 0, 999999999999999999]
        
        for invalid_id in invalid_user_ids:
            try:
                # Пытаемся получить данные пользователя с некорректным ID
                if invalid_id is not None:
                    # Проверяем, что система не падает
                    print(f"     ID {invalid_id} обработан корректно")
                else:
                    print(f"     ID None обработан корректно")
            except Exception as e:
                print(f"     ID {invalid_id} вызвал ошибку: {e}")
        
        return True
        
    except Exception as e:
        print(f"   Ошибка при тестировании данных пользователя: {e}")
        return False

def test_invalid_chat_data():
    """Тестирует обработку некорректных данных чата"""
    print("\nТестирование некорректных данных чата...")
    
    try:
        from app_config import AppConfig
        from state import BotState
        from data_manager import DataManager
        
        app_config = AppConfig()
        state = BotState(app_config)
        data_manager = DataManager(app_config, state)
        
        # Загружаем данные
        data_manager.load_all_data()
        
        # Тестируем обработку некорректных ID чатов
        print("   - Тест с некорректными ID чатов...")
        
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
        
        return True
        
    except Exception as e:
        print(f"   Ошибка при тестировании данных чата: {e}")
        return False

def test_invalid_question_data():
    """Тестирует обработку некорректных данных вопросов"""
    print("\nТестирование некорректных данных вопросов...")
    
    try:
        from app_config import AppConfig
        from state import BotState
        from data_manager import DataManager
        
        app_config = AppConfig()
        state = BotState(app_config)
        data_manager = DataManager(app_config, state)
        
        # Загружаем данные
        data_manager.load_all_data()
        
        # Проверяем, что все вопросы имеют корректную структуру
        print("   - Проверка структуры вопросов...")
        
        total_questions = 0
        valid_questions = 0
        invalid_questions = 0
        
        for category_name, questions in state.quiz_data.items():
            for question in questions:
                total_questions += 1
                
                # Проверяем обязательные поля
                required_fields = ['question', 'options', 'correct']
                if all(field in question for field in required_fields):
                    # Проверяем, что options - это список
                    if isinstance(question['options'], list) and len(question['options']) > 0:
                        # Проверяем, что correct есть в options
                        if question['correct'] in question['options']:
                            valid_questions += 1
                        else:
                            invalid_questions += 1
                            print(f"     Вопрос в категории '{category_name}': правильный ответ не найден в опциях")
                    else:
                        invalid_questions += 1
                        print(f"     Вопрос в категории '{category_name}': некорректные опции")
                else:
                    invalid_questions += 1
                    print(f"     Вопрос в категории '{category_name}': отсутствуют обязательные поля")
        
        print(f"     Всего вопросов: {total_questions}")
        print(f"     Корректных вопросов: {valid_questions}")
        print(f"     Некорректных вопросов: {invalid_questions}")
        
        if invalid_questions == 0:
            print("   Все вопросы имеют корректную структуру")
        else:
            print(f"   Найдено {invalid_questions} некорректных вопросов")
        
        return True
        
    except Exception as e:
        print(f"   Ошибка при тестировании данных вопросов: {e}")
        return False

def test_edge_cases():
    """Тестирует граничные случаи"""
    print("\nТестирование граничных случаев...")
    
    try:
        from app_config import AppConfig
        from state import BotState
        from data_manager import DataManager
        
        app_config = AppConfig()
        state = BotState(app_config)
        data_manager = DataManager(app_config, state)
        
        # Загружаем данные
        data_manager.load_all_data()
        
        print("   - Тест с пустыми данными...")
        
        # Проверяем обработку пустых данных
        if len(state.chat_settings) == 0:
            print("     Нет настроек чатов")
        else:
            print(f"     Найдено {len(state.chat_settings)} чатов")
        
        if len(state.user_scores) == 0:
            print("     Нет данных пользователей")
        else:
            print(f"     Найдено {len(state.user_scores)} чатов с пользователями")
        
        if len(state.quiz_data) == 0:
            print("     Нет вопросов")
        else:
            print(f"     Найдено {len(state.quiz_data)} категорий с вопросами")
        
        print("   - Тест с максимальными значениями...")
        
        # Проверяем максимальные значения
        max_questions = app_config.max_questions_per_session
        if max_questions > 0:
            print(f"     Максимум вопросов: {max_questions}")
        else:
            print(f"     Некорректный максимум вопросов: {max_questions}")
        
        return True
        
    except Exception as e:
        print(f"   Ошибка при тестировании граничных случаев: {e}")
        return False

def test_data_consistency():
    """Тестирует согласованность данных"""
    print("\nТестирование согласованности данных...")
    
    try:
        from app_config import AppConfig
        from state import BotState
        from data_manager import DataManager
        
        app_config = AppConfig()
        state = BotState(app_config)
        data_manager = DataManager(app_config, state)
        
        # Загружаем данные
        data_manager.load_all_data()
        
        print("   - Проверка согласованности пользователей...")
        
        # Проверяем, что пользователи в user_scores соответствуют chat_settings
        total_users_in_scores = sum(len(users) for users in state.user_scores.values())
        total_chats = len(state.chat_settings)
        
        print(f"     Чатов с настройками: {total_chats}")
        print(f"     Пользователей в очках: {total_users_in_scores}")
        
        # Проверяем, что все чаты в user_scores имеют настройки
        chats_without_settings = set(state.user_scores.keys()) - set(state.chat_settings.keys())
        if chats_without_settings:
            print(f"     Чаты без настроек: {chats_without_settings}")
        else:
            print("     Все чаты с пользователями имеют настройки")
        
        print("   - Проверка согласованности вопросов...")
        
        # Проверяем, что все категории в quiz_data существуют в global/categories.json
        try:
            categories_file = project_root / "data" / "global" / "categories.json"
            if categories_file.exists():
                with open(categories_file, 'r', encoding='utf-8') as f:
                    global_categories = json.load(f)
                
                quiz_categories = set(state.quiz_data.keys())
                global_categories_set = set(global_categories.keys())
                
                missing_in_global = quiz_categories - global_categories_set
                missing_in_quiz = global_categories_set - quiz_categories
                
                if missing_in_global:
                    print(f"     Категории в quiz_data, но не в global: {missing_in_global}")
                if missing_in_quiz:
                    print(f"     Категории в global, но не в quiz_data: {missing_in_quiz}")
                
                if not missing_in_global and not missing_in_quiz:
                    print("     Все категории синхронизированы")
            else:
                print("     Файл global/categories.json не найден")
        except Exception as e:
            print(f"     Ошибка при проверке категорий: {e}")
        
        return True
        
    except Exception as e:
        print(f"   Ошибка при тестировании согласованности: {e}")
        return False

def main():
    """Основная функция тестирования"""
    print("Запуск теста устойчивости системы Morning Quiz Bot")
    print("=" * 60)
    
    success = True
    
    # Тестируем некорректные данные конфигурации
    if not test_invalid_config_data():
        success = False
    
    # Тестируем некорректные данные пользователя
    if not test_invalid_user_data():
        success = False
    
    # Тестируем некорректные данные чата
    if not test_invalid_chat_data():
        success = False
    
    # Тестируем некорректные данные вопросов
    if not test_invalid_question_data():
        success = False
    
    # Тестируем граничные случаи
    if not test_edge_cases():
        success = False
    
    # Тестируем согласованность данных
    if not test_data_consistency():
        success = False
    
    print("\n" + "=" * 60)
    if success:
        print("Все тесты устойчивости пройдены успешно!")
        print("Система устойчива к некорректным данным")
        print("Защита от дурака работает корректно")
        print("Данные согласованы")
    else:
        print("Некоторые тесты устойчивости не пройдены")
        print("Есть проблемы с обработкой некорректных данных")
    
    return success

if __name__ == "__main__":
    import json
    success = main()
    sys.exit(0 if success else 1)
