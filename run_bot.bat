@echo off
cd /d %~dp0%

:: Проверяем, запущен ли уже bot.py
echo Проверяю, не запущен ли уже бот...
tasklist | findstr /C:"python bot.py" >nul 2>&1

if %errorlevel% == 0 (
    echo Бот уже запущен! Один экземпляр уже работает.
    pause
    exit /b
)

echo Активирую виртуальное окружение...
call venv\Scripts\activate

echo Запускаю бота...
python bot.py

echo Бот остановлен.
pause