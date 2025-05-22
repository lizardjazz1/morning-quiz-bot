# utils/scheduler_utils.py

import threading

def keep_alive():
    print("⏰ Бот всё ещё работает...")
    threading.Timer(7200, keep_alive).start()