# Настройка sudo без пароля для веб-панели

## Проблема
Веб-панель не может перезапускать бота из-за требования пароля для sudo:
```
Interactive authentication required. See system logs and 'systemctl status quiz-bot.service' for details.
```

## Решение: Настройка sudo без пароля

### Шаг 1: Определить пользователя веб-сервера

```bash
# Проверить, под каким пользователем запущен веб-сервер
sudo systemctl status quiz-bot-web | grep "Main PID"
ps aux | grep "quiz-bot-web\|uvicorn\|gunicorn" | grep -v grep
```

Обычно это пользователь `lizard` (согласно `/etc/systemd/system/quiz-bot-web.service`).

### Шаг 2: Настроить sudo без пароля (РЕКОМЕНДУЕТСЯ)

#### Вариант A: Создать отдельный файл sudoers (более безопасно)

```bash
# Создать файл конфигурации
sudo nano /etc/sudoers.d/quiz-bot-web

# Добавить следующее (замените lizard на имя пользователя веб-сервера):
lizard ALL=(ALL) NOPASSWD: /bin/systemctl start quiz-bot
lizard ALL=(ALL) NOPASSWD: /bin/systemctl stop quiz-bot
lizard ALL=(ALL) NOPASSWD: /bin/systemctl restart quiz-bot
lizard ALL=(ALL) NOPASSWD: /bin/systemctl status quiz-bot
lizard ALL=(ALL) NOPASSWD: /bin/systemctl is-active quiz-bot

# Сохранить и установить правильные права
sudo chmod 0440 /etc/sudoers.d/quiz-bot-web
```

#### Вариант B: Редактировать основной файл sudoers

```bash
# Открыть файл sudoers для редактирования
sudo visudo

# Добавить в конец файла:
lizard ALL=(ALL) NOPASSWD: /bin/systemctl start quiz-bot
lizard ALL=(ALL) NOPASSWD: /bin/systemctl stop quiz-bot
lizard ALL=(ALL) NOPASSWD: /bin/systemctl restart quiz-bot
lizard ALL=(ALL) NOPASSWD: /bin/systemctl status quiz-bot
lizard ALL=(ALL) NOPASSWD: /bin/systemctl is-active quiz-bot
lizard ALL=(ALL) NOPASSWD: /bin/systemctl start maintenance-fallback
lizard ALL=(ALL) NOPASSWD: /bin/systemctl stop maintenance-fallback
lizard ALL=(ALL) NOPASSWD: /bin/systemctl restart maintenance-fallback
```

### Шаг 3: Проверить конфигурацию

```bash
# Проверить синтаксис
sudo visudo -c

# Протестировать команду (должно работать без пароля)
sudo -u lizard sudo -n systemctl restart quiz-bot
```

### Шаг 4: Перезапустить веб-сервер

```bash
sudo systemctl restart quiz-bot-web
```

## Альтернативные решения

### Вариант 1: Запуск веб-сервера от root (НЕ рекомендуется)

⚠️ **Не рекомендуется для продакшена!**

Если веб-сервер запущен от root, он сможет выполнять systemctl без sudo:

```bash
sudo nano /etc/systemd/system/quiz-bot-web.service

# Изменить строки:
User=root
Group=root

sudo systemctl daemon-reload
sudo systemctl restart quiz-bot-web
```

### Вариант 2: Использование systemd user сервисов

Если бот запущен как пользовательский сервис:

```bash
# Проверить
systemctl --user list-units | grep quiz-bot

# Веб-панель автоматически попробует использовать systemctl --user
```

## После настройки

1. Перезапусти веб-сервер:
   ```bash
   sudo systemctl restart quiz-bot-web
   ```

2. Проверь функционал в веб-панели:
   - Открой Настройки
   - Нажми кнопку "🔄 Перезапустить"
   - Должно работать без ошибок

## Безопасность

⚠️ **Важно**: 
- Настройка sudo без пароля для конкретных systemctl командам - это минимальная привилегия
- Ограничьте команды только необходимыми (`start`, `stop`, `restart`, `status`, `is-active`)
- Не давайте полный доступ ко всем systemctl командам
- Регулярно проверяйте логи безопасности: `sudo journalctl -u quiz-bot-web -f`

## Улучшения в коде

Веб-панель теперь:
- Пробует несколько методов перезапуска (sudo, systemctl --user, обычный systemctl)
- Выводит понятные сообщения об ошибках с инструкциями по решению
- Логирует все попытки для отладки

## Дата создания
2026-01-02
