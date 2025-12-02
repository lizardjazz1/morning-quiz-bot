#!/usr/bin/env python3
"""
Скрипт для запуска всех тестов Morning Quiz Bot
"""

import sys
import subprocess
from pathlib import Path

def run_test(test_file):
    """Запускает тест и возвращает результат"""
    print(f"\n{'='*60}")
    print(f"Запуск теста: {test_file}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run([sys.executable, test_file], 
                              capture_output=True, text=True, cwd=Path(__file__).parent)
        
        print(result.stdout)
        if result.stderr:
            print(f"STDERR: {result.stderr}")
        
        return result.returncode == 0
    except Exception as e:
        print(f"Ошибка запуска теста {test_file}: {e}")
        return False

def main():
    """Основная функция запуска всех тестов"""
    print("ЗАПУСК ВСЕХ ТЕСТОВ MORNING QUIZ BOT")
    print("=" * 60)
    
    # Список тестов в порядке выполнения
    tests = [
        "system_integrity_test.py",
        "robustness_test.py", 
        "menu_navigation_test.py"
    ]
    
    results = {}
    total_tests = len(tests)
    passed_tests = 0
    
    for test_file in tests:
        success = run_test(test_file)
        results[test_file] = success
        if success:
            passed_tests += 1
    
    # Итоговый отчет
    print(f"\n{'='*60}")
    print("ИТОГОВЫЙ ОТЧЕТ ПО ТЕСТИРОВАНИЮ")
    print(f"{'='*60}")
    
    for test_file, success in results.items():
        status = "ПРОЙДЕН" if success else "НЕ ПРОЙДЕН"
        print(f"{test_file}: {status}")
    
    print(f"\nРезультат: {passed_tests}/{total_tests} тестов пройдено")
    
    if passed_tests == total_tests:
        print("ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("Система готова к работе")
        return 0
    else:
        print("НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОЙДЕНЫ")
        print("Требуется исправление выявленных проблем")
        return 1

if __name__ == "__main__":
    sys.exit(main())
