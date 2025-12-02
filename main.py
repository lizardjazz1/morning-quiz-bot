#!/usr/bin/env python3
"""
Main entry point for Morning Quiz Bot
"""

import asyncio
import sys
from pathlib import Path

# Add current directory to path for imports
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

try:
    from bot import main
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print("Убедитесь, что все зависимости установлены в виртуальном окружении")
    sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            print(f"Event loop already closed: {e}")
        else:
            print(f"Unhandled RuntimeError: {e}")
            raise
    except (KeyboardInterrupt, SystemExit):
        print("Program interrupted.")
    except Exception as e:
        print(f"Unhandled exception: {e}")
        raise
    finally:
        print("Program terminated.")
