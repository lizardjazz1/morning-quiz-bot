# utils/keep_alive.py

import threading
import time

def keep_alive():
    print("⏰ Бот всё ещё работает...")
    threading.Timer(7200, keep_alive).start()