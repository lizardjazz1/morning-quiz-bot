#!/usr/bin/env python3
"""
Скрипт для настройки уведомлений разработчику
"""

import json
import os
from pathlib import Path

def setup_developer_notifications():
    """Настраивает уведомления разработчику"""
    config_file = Path("config/quiz_config.json")
    
    if not config_file.exists():
        print("❌ Файл конфигурации не найден: config/quiz_config.json")
        return
    
    try:
        # Загружаем текущую конфигурацию
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        print("🔧 Настройка уведомлений разработчику")
        print("=" * 50)
        
        # Проверяем текущие настройки
        dev_notifications = config.get("global_settings", {}).get("developer_notifications", {})
        current_enabled = dev_notifications.get("enabled", False)
        current_user_id = dev_notifications.get("developer_user_id")
        
        print(f"Текущие настройки:")
        print(f"  Включено: {'✅' if current_enabled else '❌'}")
        print(f"  Developer User ID: {current_user_id or 'Не установлен'}")
        print()
        
        # Запрашиваем новые настройки
        print("Введите ваш Telegram User ID (или нажмите Enter для пропуска):")
        print("(Чтобы узнать свой ID, напишите боту @userinfobot)")
        
        new_user_id = input("User ID: ").strip()
        
        if new_user_id:
            try:
                user_id = int(new_user_id)
                print(f"✅ Установлен User ID: {user_id}")
            except ValueError:
                print("❌ Неверный формат User ID. Должно быть число.")
                return
        else:
            user_id = current_user_id
            print("ℹ️ User ID оставлен без изменений")
        
        print()
        print("Включить уведомления? (y/n):")
        enable_input = input("Включить: ").strip().lower()
        
        if enable_input in ['y', 'yes', 'да', 'д']:
            enabled = True
            print("✅ Уведомления включены")
        else:
            enabled = False
            print("❌ Уведомления отключены")
        
        # Обновляем конфигурацию
        if "global_settings" not in config:
            config["global_settings"] = {}
        
        if "developer_notifications" not in config["global_settings"]:
            config["global_settings"]["developer_notifications"] = {}
        
        config["global_settings"]["developer_notifications"].update({
            "enabled": enabled,
            "developer_user_id": user_id,
            "notify_on_malformed_questions": True,
            "notify_on_data_errors": True,
            "notify_on_system_errors": False
        })
        
        # Сохраняем обновленную конфигурацию
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        print()
        print("✅ Конфигурация обновлена!")
        print()
        print("Финальные настройки:")
        print(f"  Включено: {'✅' if enabled else '❌'}")
        print(f"  Developer User ID: {user_id}")
        print(f"  Уведомления о проблемных вопросах: ✅")
        print(f"  Уведомления об ошибках данных: ✅")
        print(f"  Уведомления о системных ошибках: ❌")
        print()
        print("Теперь вы можете протестировать уведомления командой /test_notifications")
        
    except Exception as e:
        print(f"❌ Ошибка при настройке: {e}")

def test_notifications():
    """Тестирует уведомления (для проверки настроек)"""
    config_file = Path("config/quiz_config.json")
    
    if not config_file.exists():
        print("❌ Файл конфигурации не найден")
        return
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        dev_notifications = config.get("global_settings", {}).get("developer_notifications", {})
        enabled = dev_notifications.get("enabled", False)
        user_id = dev_notifications.get("developer_user_id")
        
        print("🧪 Тест настроек уведомлений")
        print("=" * 30)
        print(f"Включено: {'✅' if enabled else '❌'}")
        print(f"Developer User ID: {user_id or 'Не установлен'}")
        
        if not enabled:
            print("❌ Уведомления отключены")
            return
        
        if not user_id:
            print("❌ Developer User ID не установлен")
            return
        
        print("✅ Настройки корректны")
        print("Теперь запустите бота и используйте команду /test_notifications для тестирования")
        
    except Exception as e:
        print(f"❌ Ошибка при проверке настроек: {e}")

if __name__ == "__main__":
    print("🔧 Настройка уведомлений разработчику для Morning Quiz Bot")
    print()
    
    while True:
        print("Выберите действие:")
        print("1. Настроить уведомления")
        print("2. Проверить текущие настройки")
        print("3. Выход")
        
        choice = input("\nВаш выбор (1-3): ").strip()
        
        if choice == "1":
            setup_developer_notifications()
        elif choice == "2":
            test_notifications()
        elif choice == "3":
            print("👋 До свидания!")
            break
        else:
            print("❌ Неверный выбор. Попробуйте снова.")
        
        print("\n" + "=" * 50 + "\n")
