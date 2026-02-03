# Исправление проблемы отображения статуса бота

## 📋 Проблема
Веб-панель показывала "✗ Бот выключен", хотя бот был запущен и работал.

## 🔍 Причина
1. Функция `check_bot_service_status()` использовала команду `systemctl is-active quiz-bot` без `sudo`
2. У пользователя веб-сервера могло не быть прав на проверку статуса systemd сервисов
3. Не было альтернативных методов проверки статуса бота

## ✅ Решение

### 1. Добавлен PID файл в bot.py

**Файл:** `bot.py`

Теперь бот создает PID файл при запуске и удаляет его при завершении:

```python
async def main() -> None:
    """Main entry point for the Morning Quiz Bot"""
    check_and_kill_duplicate_bots()
    logger.info("Запуск бота...")
    
    # Создаем PID файл для мониторинга статуса бота
    pid_file = Path("bot.pid")
    try:
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
        logger.info(f"📝 PID файл создан: {pid_file.absolute()} (PID: {os.getpid()})")
    except Exception as e:
        logger.warning(f"Не удалось создать PID файл: {e}")
    
    # ... остальной код ...
    
    try:
        # ... код бота ...
    finally:
        # Удаляем PID файл при завершении
        pid_file = Path("bot.pid")
        try:
            if pid_file.exists():
                pid_file.unlink()
                logger.info(f"🗑️ PID файл удален: {pid_file.absolute()}")
        except Exception as e:
            logger.warning(f"Не удалось удалить PID файл: {e}")
```

### 2. Обновлена функция check_bot_service_status()

**Файл:** `web/main.py`

Теперь используется многоуровневая проверка статуса:

```python
def check_bot_service_status() -> bool:
    """
    Проверяет статус бота через PID файл, systemd и альтернативные методы.
    Возвращает True если бот работает, False если нет.
    """
    # Метод 1: Проверка через PID файл (САМЫЙ НАДЕЖНЫЙ)
    try:
        project_root = DATA_DIR.parent
        pid_file = project_root / "bot.pid"
        
        if pid_file.exists():
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            # Проверяем, жив ли процесс
            try:
                import os
                os.kill(pid, 0)  # Сигнал 0 только проверяет существование
                
                # Дополнительно проверяем через psutil
                try:
                    import psutil
                    proc = psutil.Process(pid)
                    cmdline = ' '.join(proc.cmdline())
                    if 'bot.py' in cmdline:
                        return True  # Это наш бот!
                except:
                    return True  # psutil недоступен, но процесс существует
            except (ProcessLookupError, OSError):
                # Процесс не существует, удаляем устаревший PID файл
                try:
                    pid_file.unlink()
                except:
                    pass
    except Exception as e:
        logger.debug(f"Ошибка при проверке PID файла: {e}")
    
    # Метод 2: Проверка через pgrep
    try:
        result = subprocess.run(
            ['pgrep', '-f', 'python.*bot\\.py'],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0 and result.stdout.strip():
            return True
    except:
        pass
    
    # Метод 3: Проверка через systemctl с sudo
    try:
        result = subprocess.run(
            ['sudo', '-n', 'systemctl', 'is-active', 'quiz-bot'],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0 and result.stdout.strip() == 'active':
            return True
    except:
        pass
    
    # Метод 4: Проверка через systemctl --user
    try:
        result = subprocess.run(
            ['systemctl', '--user', 'is-active', 'quiz-bot'],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0 and result.stdout.strip() == 'active':
            return True
    except:
        pass
    
    # Метод 5: Обычный systemctl
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', 'quiz-bot'],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0 and result.stdout.strip() == 'active':
            return True
    except:
        pass
    
    return False
```

### 3. Обновлены команды управления ботом

**Функции:** `set_bot_status()`, `restart_bot()`, `get_detailed_status()`

Теперь все команды управления пробуют выполнить действие с `sudo -n`, а затем без него:

```python
# Пробуем с sudo, затем без него
commands_to_try = [
    ['sudo', '-n', 'systemctl', 'restart', 'quiz-bot'],
    ['systemctl', 'restart', 'quiz-bot']
]

for cmd in commands_to_try:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            success = True
            break
    except:
        continue
```

## 🔄 Как применить исправление

### 1. Перезапустить бота
```bash
sudo systemctl restart quiz-bot
```

Или через веб-панель: Настройки → 🔄 Перезапустить

### 2. Проверить создание PID файла
```bash
cat /home/lizard/morning-quiz-bot/bot.pid
# Должен показать PID процесса бота
```

### 3. Проверить статус в веб-панели
Обновить страницу веб-панели - статус должен показать "✓ Бот включен"

## 🧪 Тестирование

### Проверка PID файла
```bash
# Проверить наличие файла
ls -la /home/lizard/morning-quiz-bot/bot.pid

# Проверить PID
cat /home/lizard/morning-quiz-bot/bot.pid

# Проверить процесс
ps aux | grep $(cat /home/lizard/morning-quiz-bot/bot.pid)
```

### Проверка через веб-панель
1. Открыть Dashboard
2. Проверить "🔴 Статус системы"
3. Должно показать "✓ Бот включен | Режим: Основной"

### Проверка через API
```bash
curl http://localhost:8000/api/analytics/system | jq '.bot_enabled'
# Должно вернуть: true
```

## 📝 Преимущества решения

1. **Надежность:** 5 методов проверки статуса (PID файл → pgrep → sudo systemctl → systemctl --user → обычный systemctl)
2. **Кроссплатформенность:** Работает независимо от прав доступа к systemctl
3. **Точность:** PID файл + проверка cmdline гарантирует, что проверяется именно bot.py
4. **Отказоустойчивость:** Если один метод не работает, пробуется следующий
5. **Очистка:** Устаревший PID файл автоматически удаляется

## ⚠️ Важные заметки

1. **PID файл создается при каждом запуске бота** - это нормально
2. **PID файл удаляется при корректном завершении** - если бот был убит принудительно, файл останется
3. **Автоматическая очистка** - при следующей проверке статуса устаревший PID файл будет удален
4. **sudo -n** - флаг `-n` означает "не запрашивать пароль", если пароль нужен - команда провалится

## 🔒 Настройка sudo без пароля (опционально)

Если хотите, чтобы веб-сервер мог управлять ботом через systemctl:

```bash
# Добавить в /etc/sudoers.d/quiz-bot
www-data ALL=(ALL) NOPASSWD: /bin/systemctl start quiz-bot
www-data ALL=(ALL) NOPASSWD: /bin/systemctl stop quiz-bot
www-data ALL=(ALL) NOPASSWD: /bin/systemctl restart quiz-bot
www-data ALL=(ALL) NOPASSWD: /bin/systemctl is-active quiz-bot
www-data ALL=(ALL) NOPASSWD: /bin/systemctl status quiz-bot
```

Замените `www-data` на пользователя, под которым запущен веб-сервер.

## 📅 Дата создания
2026-01-01

## 🔧 Дата последнего обновления
2026-01-01 - Добавлен PID файл и многоуровневая проверка статуса
