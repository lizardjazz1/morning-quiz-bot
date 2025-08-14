# Morning Quiz Bot Beta

Telegram-бот для проведения интерактивных викторин с системой очков, рейтингов и различных режимов игры.

## 🎯 Возможности

- **Различные типы викторин**: одиночные вопросы, сессии, ежедневные автоматические викторины
- **Система категорий**: Математика, География, Кино и другие расширяемые категории
- **Система очков и рейтингов**: подсчет очков, рейтинги по чатам и глобальные
- **Административные функции**: настройка параметров, управление категориями
- **Интерактивность**: poll-опросы с таймером, кнопки настройки
- **Автоматизация**: планирование ежедневных викторин, очистка данных

## 🚀 Быстрый старт

### Локальная установка

1. **Клонируйте репозиторий**
```bash
git clone https://github.com/your-username/morning-quiz-bot-beta.git
cd morning-quiz-bot-beta
```

2. **Создайте виртуальное окружение**
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

3. **Установите зависимости**
```bash
pip install -r requirements.txt
```

4. **Настройте переменные окружения**
Создайте файл `.env` в корне проекта:
```env
BOT_TOKEN=your_telegram_bot_token_here
LOG_LEVEL=INFO
```

5. **Запустите бота**
```bash
# Windows
run_bot.bat
# Linux/Mac
python bot.py
```

### Развертывание на Ubuntu сервере

1. **Подготовка сервера**
```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Python и pip
sudo apt install python3 python3-pip python3-venv -y

# Установка Git
sudo apt install git -y
```

2. **Клонирование и настройка**
```bash
# Клонирование репозитория
git clone https://github.com/your-username/morning-quiz-bot-beta.git
cd morning-quiz-bot-beta

# Создание виртуального окружения
python3 -m venv venv
source venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt
```

3. **Настройка переменных окружения**
```bash
# Создание .env файла
nano .env
```

Добавьте в файл:
```env
BOT_TOKEN=your_telegram_bot_token_here
LOG_LEVEL=INFO
```

4. **Настройка systemd сервиса**
```bash
# Создание файла сервиса
sudo nano /etc/systemd/system/quiz-bot.service
```

Добавьте содержимое:
```ini
[Unit]
Description=Morning Quiz Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/morning-quiz-bot-beta
Environment=PATH=/path/to/morning-quiz-bot-beta/venv/bin
ExecStart=/path/to/morning-quiz-bot-beta/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

5. **Запуск сервиса**
```bash
# Перезагрузка systemd
sudo systemctl daemon-reload

# Включение автозапуска
sudo systemctl enable quiz-bot

# Запуск сервиса
sudo systemctl start quiz-bot

# Проверка статуса
sudo systemctl status quiz-bot
```

## 📁 Структура проекта

```
morning-quiz-bot-beta/
├── bot.py                 # Главный файл бота
├── app_config.py          # Конфигурация приложения
├── data_manager.py        # Управление данными
├── state.py              # Управление состоянием
├── utils.py              # Вспомогательные функции
├── requirements.txt       # Зависимости Python
├── .env                  # Переменные окружения
├── config/               # Конфигурационные файлы
│   └── quiz_config.json
├── data/                 # Файлы данных
│   ├── questions.json
│   ├── users.json
│   └── chat_settings.json
├── modules/              # Основные модули
│   ├── quiz_engine.py
│   ├── score_manager.py
│   └── category_manager.py
└── handlers/             # Обработчики команд
    ├── quiz_manager.py
    ├── rating_handlers.py
    └── config_handlers.py
```

## ⚙️ Конфигурация

### Основные настройки в `config/quiz_config.json`:

- **Типы викторин**: single, session, daily
- **Параметры по умолчанию**: количество вопросов, время ответа
- **Мотивационные сообщения**: для разных уровней очков
- **Команды бота**: настраиваемые команды

### Переменные окружения:

- `BOT_TOKEN` - токен Telegram бота (обязательно)
- `LOG_LEVEL` - уровень логирования (INFO, DEBUG, WARNING, ERROR)

## 🎮 Команды бота

- `/start` - начало работы с ботом
- `/quiz` - запуск викторины
- `/categories` - выбор категорий
- `/top` - рейтинг в чате
- `/globaltop` - глобальный рейтинг
- `/mystats` - личная статистика
- `/stopquiz` - остановка текущей викторины
- `/adminsettings` - настройки администратора

## 🔧 Администрирование

### Просмотр логов
```bash
# Локально
tail -f bot.log

# На сервере через systemd
sudo journalctl -u quiz-bot -f
```

### Перезапуск бота
```bash
# На сервере
sudo systemctl restart quiz-bot
```

### Обновление кода
```bash
git pull origin main
sudo systemctl restart quiz-bot
```

## 📊 Мониторинг

Бот автоматически ведет логи в файл `bot.log` и выводит информацию в консоль. Основные события:

- Запуск/остановка бота
- Проведение викторин
- Ошибки и предупреждения
- Статистика использования

## 🤝 Вклад в проект

1. Форкните репозиторий
2. Создайте ветку для новой функции
3. Внесите изменения
4. Создайте Pull Request

## 📄 Лицензия

MIT License

## 🆘 Поддержка

При возникновении проблем:

1. Проверьте логи бота
2. Убедитесь в правильности токена
3. Проверьте права доступа к файлам
4. Создайте Issue в репозитории

## 🔄 Обновления

Для обновления бота:

```bash
git pull origin main
pip install -r requirements.txt
sudo systemctl restart quiz-bot
``` 