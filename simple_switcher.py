#!/usr/bin/env python3
"""
Простая система переключения ботов через файлы-флаги
"""

import os
import json
from pathlib import Path

class SimpleSwitcher:
    """Простой переключатель режимов"""

    def __init__(self):
        self.data_dir = Path("data")
        self.mode_file = self.data_dir / "bot_mode.json"
        self.data_dir.mkdir(exist_ok=True)

    def set_maintenance_mode(self, reason="Переключение в режим обслуживания"):
        """Включает режим обслуживания"""
        mode_data = {
            "mode": "maintenance",
            "reason": reason,
            "timestamp": "now"
        }

        try:
            with open(self.mode_file, 'w', encoding='utf-8') as f:
                json.dump(mode_data, f, ensure_ascii=True, indent=2)
            print("Режим обслуживания ВКЛЮЧЕН")
            print("Теперь fallback бот будет активен")
        except Exception as e:
            print(f"Ошибка при сохранении режима обслуживания: {e}")
            # Попробуем с ensure_ascii=False
            try:
                with open(self.mode_file, 'w', encoding='utf-8') as f:
                    json.dump(mode_data, f, ensure_ascii=False, indent=2)
                print("Режим обслуживания ВКЛЮЧЕН (альтернативный метод)")
                print("Теперь fallback бот будет активен")
            except Exception as e2:
                print(f"Критическая ошибка при сохранении: {e2}")

    def set_main_mode(self):
        """Включает режим основного бота"""
        mode_data = {
            "mode": "main",
            "reason": "Работа основного бота",
            "timestamp": "now"
        }

        try:
            with open(self.mode_file, 'w', encoding='utf-8') as f:
                json.dump(mode_data, f, ensure_ascii=True, indent=2)
            print("Режим основного бота ВКЛЮЧЕН")
            print("Теперь основной бот будет активен")
        except Exception as e:
            print(f"Ошибка при сохранении режима основного бота: {e}")
            # Попробуем с ensure_ascii=False
            try:
                with open(self.mode_file, 'w', encoding='utf-8') as f:
                    json.dump(mode_data, f, ensure_ascii=False, indent=2)
                print("Режим основного бота ВКЛЮЧЕН (альтернативный метод)")
                print("Теперь основной бот будет активен")
            except Exception as e2:
                print(f"Критическая ошибка при сохранении: {e2}")

    def get_current_mode(self):
        """Получает текущий режим"""
        if not self.mode_file.exists():
            return "main"  # По умолчанию основной бот

        try:
            with open(self.mode_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get("mode", "main")
        except:
            return "main"

    def show_status(self):
        """Показывает статус"""
        current_mode = self.get_current_mode()

        if current_mode == "maintenance":
            print("ТЕКУЩИЙ РЕЖИМ: ОБСЛУЖИВАНИЕ")
            print("Maintenance Fallback Bot активен")
        else:
            print("ТЕКУЩИЙ РЕЖИМ: ОСНОВНОЙ БОТ")
            print("Основной бот активен")

def main():
    """Главная функция"""
    switcher = SimpleSwitcher()

    if len(os.sys.argv) < 2:
        print("Использование:")
        print("  python simple_switcher.py status")
        print("  python simple_switcher.py to-maintenance [причина]")
        print("  python simple_switcher.py to-main")
        return

    command = os.sys.argv[1]

    if command == "status":
        switcher.show_status()
    elif command == "to-maintenance":
        reason = os.sys.argv[2] if len(os.sys.argv) > 2 else "Переключение в режим обслуживания"
        switcher.set_maintenance_mode(reason)
    elif command == "to-main":
        switcher.set_main_mode()
    else:
        print(f"❌ Неизвестная команда: {command}")

if __name__ == "__main__":
    main()
