# Инструкции по развертыванию Morning Quiz Bot

## 🚀 Способы развертывания

### 1. Локальная установка (Windows/Linux/Mac)

#### Требования
- Python 3.8+
- Git

#### Шаги установки

1. **Клонирование репозитория**
```bash
git clone https://github.com/your-username/morning-quiz-bot-beta.git
cd morning-quiz-bot-beta
```

2. **Создание виртуального окружения**
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

3. **Установка зависимостей**
```bash
pip install -r requirements.txt
```

4. **Настройка переменных окружения**
Создайте файл `.env`:
```env
BOT_TOKEN=your_telegram_bot_token_here
LOG_LEVEL=INFO
```

5. **Запуск**
```bash
# Windows
run_bot.bat

# Linux/Mac
python bot.py
```

### 2. Развертывание на Ubuntu сервере

#### Автоматическое развертывание

1. **Скачайте скрипт развертывания**
```bash
wget https://raw.githubusercontent.com/your-username/morning-quiz-bot-beta/main/deploy.sh
chmod +x deploy.sh
```

2. **Запустите скрипт**
```bash
sudo ./deploy.sh
```

3. **Настройте токен бота**
```bash
sudo nano /home/quizbot/morning-quiz-bot-beta/.env
```

4. **Перезапустите бота**
```bash
sudo systemctl restart quiz-bot
```

#### Ручное развертывание

1. **Подготовка сервера**
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv git -y
```

2. **Создание пользователя**
```bash
sudo useradd -m -s /bin/bash quizbot
```

3. **Клонирование и настройка**
```bash
sudo -u quizbot git clone https://github.com/your-username/morning-quiz-bot-beta.git /home/quizbot/morning-quiz-bot-beta
cd /home/quizbot/morning-quiz-bot-beta
sudo -u quizbot python3 -m venv venv
sudo -u quizbot bash -c "source venv/bin/activate && pip install -r requirements.txt"
```

4. **Создание systemd сервиса**
```bash
sudo nano /etc/systemd/system/quiz-bot.service
```

Содержимое файла:
```ini
[Unit]
Description=Morning Quiz Bot
After=network.target

[Service]
Type=simple
User=quizbot
Group=quizbot
WorkingDirectory=/home/quizbot/morning-quiz-bot-beta
Environment=PATH=/home/quizbot/morning-quiz-bot-beta/venv/bin
ExecStart=/home/quizbot/morning-quiz-bot-beta/venv/bin/python bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

5. **Запуск сервиса**
```bash
sudo systemctl daemon-reload
sudo systemctl enable quiz-bot
sudo systemctl start quiz-bot
```

### 3. Развертывание с Docker

#### Требования
- Docker
- Docker Compose

#### Быстрый старт

1. **Клонирование репозитория**
```bash
git clone https://github.com/your-username/morning-quiz-bot-beta.git
cd morning-quiz-bot-beta
```

2. **Настройка переменных окружения**
```bash
cp .env.example .env
nano .env
```

3. **Запуск с Docker Compose**
```bash
docker-compose up -d
```

#### Ручная сборка Docker образа

1. **Сборка образа**
```bash
docker build -t morning-quiz-bot .
```

2. **Запуск контейнера**
```bash
docker run -d \
  --name morning-quiz-bot \
  -e BOT_TOKEN=your_token_here \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config:/app/config \
  morning-quiz-bot
```

### 4. Развертывание на VPS/Облачных платформах

#### DigitalOcean

1. **Создание Droplet**
   - Ubuntu 20.04 LTS
   - Минимум 1GB RAM
   - 25GB SSD

2. **Подключение и настройка**
```bash
ssh root@your_server_ip
```

3. **Выполнение автоматического развертывания**
```bash
wget https://raw.githubusercontent.com/your-username/morning-quiz-bot-beta/main/deploy.sh
chmod +x deploy.sh
sudo ./deploy.sh
```

#### AWS EC2

1. **Создание инстанса**
   - Amazon Linux 2 или Ubuntu
   - t2.micro или больше
   - Настройка Security Groups (открыть порт 22)

2. **Подключение и развертывание**
```bash
ssh -i your-key.pem ubuntu@your-instance-ip
# Далее следуйте инструкциям для Ubuntu
```

#### Google Cloud Platform

1. **Создание VM Instance**
   - Ubuntu 20.04 LTS
   - e2-micro или больше
   - Настройка firewall rules

2. **Развертывание**
```bash
gcloud compute ssh your-instance-name
# Далее следуйте инструкциям для Ubuntu
```

## 🔧 Управление ботом

### Команды systemd (Ubuntu)

```bash
# Проверка статуса
sudo systemctl status quiz-bot

# Просмотр логов
sudo journalctl -u quiz-bot -f

# Перезапуск
sudo systemctl restart quiz-bot

# Остановка
sudo systemctl stop quiz-bot

# Включение автозапуска
sudo systemctl enable quiz-bot
```

### Команды Docker

```bash
# Просмотр логов
docker-compose logs -f quiz-bot

# Перезапуск
docker-compose restart quiz-bot

# Остановка
docker-compose down

# Обновление
docker-compose pull
docker-compose up -d
```

### Скрипты управления (после развертывания)

```bash
# Статус бота
quiz-bot-status

# Просмотр логов
quiz-bot-logs

# Перезапуск
quiz-bot-restart

# Обновление
quiz-bot-update
```

## 📊 Мониторинг

### Проверка работоспособности

1. **Проверка логов**
```bash
# Systemd
sudo journalctl -u quiz-bot -n 50

# Docker
docker-compose logs --tail=50 quiz-bot
```

2. **Проверка процесса**
```bash
# Systemd
sudo systemctl is-active quiz-bot

# Docker
docker ps | grep quiz-bot
```

3. **Проверка ресурсов**
```bash
# Использование памяти
free -h

# Использование диска
df -h

# Загрузка CPU
top
```

### Настройка мониторинга

#### С Prometheus + Grafana

1. **Установка Prometheus**
```bash
# Добавление репозитория
sudo apt install prometheus
```

2. **Настройка экспорта метрик**
```bash
# Создание конфигурации
sudo nano /etc/prometheus/prometheus.yml
```

3. **Установка Grafana**
```bash
sudo apt install grafana
sudo systemctl enable grafana-server
sudo systemctl start grafana-server
```

## 🔒 Безопасность

### Рекомендации по безопасности

1. **Обновление системы**
```bash
sudo apt update && sudo apt upgrade -y
```

2. **Настройка firewall**
```bash
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 80
sudo ufw allow 443
```

3. **Настройка SSL (опционально)**
```bash
# Установка Certbot
sudo apt install certbot python3-certbot-nginx

# Получение сертификата
sudo certbot --nginx -d your-domain.com
```

4. **Регулярные бэкапы**
```bash
# Создание скрипта бэкапа
nano backup.sh
```

```bash
#!/bin/bash
BACKUP_DIR="/backup/quiz-bot"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR
tar -czf $BACKUP_DIR/quiz-bot-$DATE.tar.gz /home/quizbot/morning-quiz-bot-beta/data

# Удаление старых бэкапов (старше 30 дней)
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete
```

5. **Настройка cron для бэкапов**
```bash
crontab -e
# Добавить строку:
0 2 * * * /path/to/backup.sh
```

## 🆘 Устранение неполадок

### Частые проблемы

1. **Бот не запускается**
```bash
# Проверка токена
cat /home/quizbot/morning-quiz-bot-beta/.env

# Проверка логов
sudo journalctl -u quiz-bot -n 100
```

2. **Ошибки подключения к Telegram**
```bash
# Проверка интернет-соединения
ping api.telegram.org

# Проверка токена
curl "https://api.telegram.org/botYOUR_TOKEN/getMe"
```

3. **Проблемы с правами доступа**
```bash
# Исправление прав
sudo chown -R quizbot:quizbot /home/quizbot/morning-quiz-bot-beta
sudo chmod -R 755 /home/quizbot/morning-quiz-bot-beta
```

4. **Проблемы с памятью**
```bash
# Проверка использования памяти
free -h

# Очистка кэша
sudo sync && sudo echo 3 > /proc/sys/vm/drop_caches
```

### Получение поддержки

1. **Проверьте логи**
2. **Убедитесь в правильности токена**
3. **Проверьте права доступа к файлам**
4. **Создайте Issue в репозитории с подробным описанием проблемы**

## 🔄 Обновления

### Автоматическое обновление

```bash
# Создание скрипта автообновления
nano auto-update.sh
```

```bash
#!/bin/bash
cd /home/quizbot/morning-quiz-bot-beta
git pull origin main
sudo -u quizbot bash -c "source venv/bin/activate && pip install -r requirements.txt"
sudo systemctl restart quiz-bot
```

### Ручное обновление

```bash
# Остановка бота
sudo systemctl stop quiz-bot

# Обновление кода
cd /home/quizbot/morning-quiz-bot-beta
git pull origin main

# Обновление зависимостей
sudo -u quizbot bash -c "source venv/bin/activate && pip install -r requirements.txt"

# Запуск бота
sudo systemctl start quiz-bot
``` 