# quiz_bot/utils.py
import threading
import time

def keep_alive(interval_seconds=7200):
    """Периодический вывод для поддержания активности (например, на Replit)."""
    print("⏰ Бот всё ещё работает...")
    # Повторный запуск таймера
    threading.Timer(interval_seconds, keep_alive, [interval_seconds]).start()

