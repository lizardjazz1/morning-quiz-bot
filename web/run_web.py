#!/usr/bin/env python3
"""
Скрипт для запуска веб-интерфейса
"""
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в sys.path
# Это нужно для корректного импорта модуля web
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import uvicorn
from web.main import app

if __name__ == "__main__":
    import os
    
    # В продакшене (systemd) отключаем reload
    # Для разработки можно установить RELOAD=true в окружении
    reload = os.getenv("RELOAD", "false").lower() == "true"
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=reload,  # Автоперезагрузка только если RELOAD=true
        log_level="info"
    )
