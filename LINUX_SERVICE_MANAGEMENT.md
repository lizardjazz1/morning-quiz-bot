# 🐧 Управление Linux сервисами Morning Quiz Bot
## ЭТОТ ФАЙЛ НУЖЕН ДЛЯ АДМИНА НЕ ТРОГАТЬ ## 
## 📋 Обзор

Данный документ описывает управление Morning Quiz Bot как systemd сервиса на Linux системах.

## 🚀 Основные команды управления сервисом

### 📊 Статус сервиса
```bash
# Проверить статус бота
sudo systemctl status quiz-bot

# Краткий статус
sudo systemctl is-active quiz-bot
sudo systemctl is-enabled quiz-bot
```

### 🔄 Управление запуском
```bash
# Запустить бота для тестов
python bot.py   
# Настройка уведомлений
python setup_developer_notifications.py
# Запустить бота
sudo systemctl start quiz-bot

# Остановить бота
sudo systemctl stop quiz-bot

# Перезапустить бота
sudo systemctl restart quiz-bot

# Перезагрузить конфигурацию
sudo systemctl reload quiz-bot
```

### ⚙️ Автозапуск
```bash
# Включить автозапуск при загрузке системы
sudo systemctl enable quiz-bot

# Отключить автозапуск
sudo systemctl disable quiz-bot
```

### 📝 Просмотр логов
```bash
# Просмотр логов в реальном времени
sudo journalctl -u quiz-bot -f

# Последние 100 строк логов
sudo journalctl -u quiz-bot -n 100

# Логи за последний час
sudo journalctl -u quiz-bot --since "1 hour ago"

# Логи за сегодня
sudo journalctl -u quiz-bot --since "today"

# Логи за определенную дату
sudo journalctl -u quiz-bot --since "2025-08-25" --until "2025-08-26"

# Поиск ошибок в логах
sudo journalctl -u quiz-bot | grep -i error
sudo journalctl -u quiz-bot | grep -i critical
```

## 🛠️ Полезные скрипты управления

### 📜 Скрипт перезапуска
```bash
#!/bin/bash
# quiz-bot-restart
sudo systemctl restart quiz-bot
echo "Quiz Bot перезапущен"
sudo systemctl status quiz-bot
```

### 📜 Скрипт просмотра логов
```bash
#!/bin/bash
# quiz-bot-logs
sudo journalctl -u quiz-bot -f
```

### 📜 Скрипт статуса
```bash
#!/bin/bash
# quiz-bot-status
sudo systemctl status quiz-bot
```

### 📜 Скрипт обновления
```bash
#!/bin/bash
# quiz-bot-update
cd /home/quizbot/morning-quiz-bot
sudo -u quizbot git pull origin main
sudo -u quizbot bash -c "source venv/bin/activate && pip install -r requirements.txt"
sudo systemctl restart quiz-bot
echo "Quiz Bot обновлен и перезапущен"
```

## 🔧 Установка скриптов управления

```bash
# Создание скриптов в /usr/local/bin
sudo nano /usr/local/bin/quiz-bot-restart
sudo nano /usr/local/bin/quiz-bot-logs
sudo nano /usr/local/bin/quiz-bot-status
sudo nano /usr/local/bin/quiz-bot-update

# Установка прав на выполнение
sudo chmod +x /usr/local/bin/quiz-bot-*

# Теперь можно использовать команды:
quiz-bot-status
quiz-bot-logs
quiz-bot-restart
quiz-bot-update
```

## 📁 Структура сервиса

### 🗂️ Файл сервиса
```ini
# /etc/systemd/system/quiz-bot.service
[Unit]
Description=Morning Quiz Bot
After=network.target

[Service]
Type=simple
User=quizbot
Group=quizbot
WorkingDirectory=/home/quizbot/morning-quiz-bot
Environment=PATH=/home/quizbot/morning-quiz-bot/venv/bin
ExecStart=/home/quizbot/morning-quiz-bot/venv/bin/python bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 🔄 Перезагрузка systemd
```bash
# После изменения конфигурации сервиса
sudo systemctl daemon-reload

# Перезапуск сервиса
sudo systemctl restart quiz-bot
```

## 🚨 Устранение неполадок

### ❌ Сервис не запускается
```bash
# Проверить статус
sudo systemctl status quiz-bot

# Просмотреть детальные логи
sudo journalctl -u quiz-bot -n 50

# Проверить права доступа
ls -la /home/quizbot/morning-quiz-bot/
ls -la /home/quizbot/morning-quiz-bot/venv/bin/python

# Проверить конфигурацию
sudo systemctl cat quiz-bot
```

### 🔐 Проблемы с правами доступа
```bash
# Исправить права на файлы
sudo chown -R quizbot:quizbot /home/quizbot/morning-quiz-bot

# Проверить права на .env файл
sudo chmod 600 /home/quizbot/morning-quiz-bot/.env
```

### 🐍 Проблемы с Python
```bash
# Проверить виртуальное окружение
sudo -u quizbot bash -c "cd /home/quizbot/morning-quiz-bot && source venv/bin/activate && python --version"

# Пересоздать виртуальное окружение
sudo -u quizbot bash -c "cd /home/quizbot/morning-quiz-bot && rm -rf venv && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
```

## 📊 Мониторинг производительности

### 📈 Статистика сервиса
```bash
# Время работы сервиса
sudo systemctl show quiz-bot --property=ActiveEnterTimestamp

# Использование ресурсов
sudo systemctl show quiz-bot --property=CPUUsageNSec,MemoryCurrent

# Количество перезапусков
sudo systemctl show quiz-bot --property=RestartCount
```

### 🔍 Проверка процессов
```bash
# Найти процессы бота
ps aux | grep quiz-bot
ps aux | grep python.*bot.py

# Проверить порты
sudo netstat -tlnp | grep python
sudo ss -tlnp | grep python
```

## 🚀 Автоматизация управления

### 📅 Cron задачи для мониторинга
```bash
# Добавить в crontab (sudo crontab -e)
# Проверка статуса каждые 5 минут
*/5 * * * * systemctl is-active quiz-bot || systemctl restart quiz-bot

# Ежедневный перезапуск в 3:00
0 3 * * * systemctl restart quiz-bot

# Еженедельная очистка логов
0 2 * * 0 journalctl --vacuum-time=7d
```

### 📧 Уведомления о проблемах
```bash
# Скрипт для отправки уведомлений
#!/bin/bash
if ! systemctl is-active --quiet quiz-bot; then
    echo "Quiz Bot не работает!" | mail -s "Quiz Bot Alert" admin@example.com
    systemctl restart quiz-bot
fi
```

## 🔒 Безопасность

### 🛡️ Ограничение доступа
```bash
# Ограничить доступ к сервису только для определенных пользователей
sudo usermod -a -G quizbot admin_user

# Проверить права
sudo systemctl show quiz-bot --property=User,Group
```

### 📝 Логирование безопасности
```bash
# Включить детальное логирование
sudo systemctl set-property quiz-bot LogLevel=debug

# Просмотр системных логов
sudo journalctl -u quiz-bot --since "1 hour ago" | grep -i "security\|auth\|permission"
```

## 📚 Полезные команды

### 🔍 Поиск в логах
```bash
# Поиск по ключевым словам
sudo journalctl -u quiz-bot | grep -i "error\|warning\|critical"

# Поиск по времени
sudo journalctl -u quiz-bot --since "09:00" --until "10:00"

# Экспорт логов в файл
sudo journalctl -u quiz-bot --since "today" > quiz-bot-today.log
```

### 📊 Анализ производительности
```bash
# Время ответа сервиса
sudo systemctl show quiz-bot --property=ActiveEnterTimestamp,ActiveExitTimestamp

# Статистика перезапусков
sudo systemctl show quiz-bot --property=RestartCount,RestartUSec
```

## 🎯 Быстрые команды

```bash
# Полный статус
quiz-bot-status

# Просмотр логов
quiz-bot-logs

# Перезапуск
quiz-bot-restart

# Обновление
quiz-bot-update

# Проверка здоровья
systemctl is-active quiz-bot && echo "✅ Работает" || echo "❌ Не работает"
```

---

## 📞 Поддержка

При возникновении проблем:
1. Проверьте статус: `sudo systemctl status quiz-bot`
2. Просмотрите логи: `sudo journalctl -u quiz-bot -n 50`
3. Проверьте права доступа к файлам
4. Убедитесь, что .env файл настроен правильно

**Контакты**: @mrlizardfromrussia
