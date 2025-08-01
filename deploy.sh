#!/bin/bash

# Morning Quiz Bot - Deployment Script for Ubuntu
# Этот скрипт автоматически развертывает бота на Ubuntu сервере

set -e  # Остановка при ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функции для вывода
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Проверка прав администратора
check_sudo() {
    if [[ $EUID -ne 0 ]]; then
        print_error "Этот скрипт должен быть запущен с правами sudo"
        exit 1
    fi
}

# Обновление системы
update_system() {
    print_info "Обновление системы..."
    apt update && apt upgrade -y
    print_success "Система обновлена"
}

# Установка зависимостей
install_dependencies() {
    print_info "Установка необходимых пакетов..."
    apt install -y python3 python3-pip python3-venv git curl wget
    print_success "Зависимости установлены"
}

# Создание пользователя для бота
create_bot_user() {
    print_info "Создание пользователя для бота..."
    
    if id "quizbot" &>/dev/null; then
        print_warning "Пользователь quizbot уже существует"
    else
        useradd -m -s /bin/bash quizbot
        print_success "Пользователь quizbot создан"
    fi
}

# Клонирование репозитория
clone_repository() {
    print_info "Клонирование репозитория..."
    
    BOT_DIR="/home/quizbot/morning-quiz-bot-beta"
    
    if [ -d "$BOT_DIR" ]; then
        print_warning "Директория уже существует, обновляем..."
        cd "$BOT_DIR"
        git pull origin main
    else
        cd /home/quizbot
        git clone https://github.com/your-username/morning-quiz-bot-beta.git
    fi
    
    # Установка прав доступа
    chown -R quizbot:quizbot "$BOT_DIR"
    print_success "Репозиторий готов"
}

# Настройка виртуального окружения
setup_venv() {
    print_info "Настройка виртуального окружения..."
    
    BOT_DIR="/home/quizbot/morning-quiz-bot-beta"
    cd "$BOT_DIR"
    
    # Создание виртуального окружения
    sudo -u quizbot python3 -m venv venv
    
    # Активация и установка зависимостей
    sudo -u quizbot bash -c "source venv/bin/activate && pip install -r requirements.txt"
    
    print_success "Виртуальное окружение настроено"
}

# Создание .env файла
create_env_file() {
    print_info "Создание файла .env..."
    
    BOT_DIR="/home/quizbot/morning-quiz-bot-beta"
    ENV_FILE="$BOT_DIR/.env"
    
    if [ ! -f "$ENV_FILE" ]; then
        cat > "$ENV_FILE" << EOF
# Morning Quiz Bot Environment Variables
BOT_TOKEN=your_telegram_bot_token_here
LOG_LEVEL=INFO
EOF
        chown quizbot:quizbot "$ENV_FILE"
        print_warning "Файл .env создан. Не забудьте указать BOT_TOKEN!"
    else
        print_warning "Файл .env уже существует"
    fi
}

# Создание systemd сервиса
create_systemd_service() {
    print_info "Создание systemd сервиса..."
    
    SERVICE_FILE="/etc/systemd/system/quiz-bot.service"
    
    cat > "$SERVICE_FILE" << EOF
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
EOF
    
    # Перезагрузка systemd
    systemctl daemon-reload
    
    # Включение автозапуска
    systemctl enable quiz-bot
    
    print_success "Systemd сервис создан"
}

# Настройка логирования
setup_logging() {
    print_info "Настройка логирования..."
    
    LOG_DIR="/var/log/quiz-bot"
    mkdir -p "$LOG_DIR"
    chown quizbot:quizbot "$LOG_DIR"
    
    print_success "Логирование настроено"
}

# Создание скриптов управления
create_management_scripts() {
    print_info "Создание скриптов управления..."
    
    BOT_DIR="/home/quizbot/morning-quiz-bot-beta"
    
    # Скрипт перезапуска
    cat > /usr/local/bin/quiz-bot-restart << EOF
#!/bin/bash
sudo systemctl restart quiz-bot
echo "Quiz Bot перезапущен"
EOF
    
    # Скрипт просмотра логов
    cat > /usr/local/bin/quiz-bot-logs << EOF
#!/bin/bash
sudo journalctl -u quiz-bot -f
EOF
    
    # Скрипт статуса
    cat > /usr/local/bin/quiz-bot-status << EOF
#!/bin/bash
sudo systemctl status quiz-bot
EOF
    
    # Скрипт обновления
    cat > /usr/local/bin/quiz-bot-update << EOF
#!/bin/bash
cd /home/quizbot/morning-quiz-bot-beta
sudo -u quizbot git pull origin main
sudo -u quizbot bash -c "source venv/bin/activate && pip install -r requirements.txt"
sudo systemctl restart quiz-bot
echo "Quiz Bot обновлен и перезапущен"
EOF
    
    # Установка прав на выполнение
    chmod +x /usr/local/bin/quiz-bot-*
    
    print_success "Скрипты управления созданы"
}

# Создание файла конфигурации nginx (опционально)
create_nginx_config() {
    print_info "Создание конфигурации nginx (опционально)..."
    
    NGINX_CONF="/etc/nginx/sites-available/quiz-bot"
    
    cat > "$NGINX_CONF" << EOF
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        return 200 "Morning Quiz Bot is running!";
        add_header Content-Type text/plain;
    }
    
    location /status {
        proxy_pass http://localhost:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF
    
    # Создание символической ссылки
    ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/
    
    print_warning "Конфигурация nginx создана. Не забудьте настроить домен и перезапустить nginx"
}

# Финальная настройка
final_setup() {
    print_info "Финальная настройка..."
    
    # Запуск сервиса
    systemctl start quiz-bot
    
    # Проверка статуса
    if systemctl is-active --quiet quiz-bot; then
        print_success "Quiz Bot успешно запущен!"
    else
        print_error "Ошибка запуска Quiz Bot"
        systemctl status quiz-bot
        exit 1
    fi
}

# Вывод инструкций
print_instructions() {
    echo ""
    print_success "=== РАЗВЕРТЫВАНИЕ ЗАВЕРШЕНО ==="
    echo ""
    echo "Полезные команды:"
    echo "  quiz-bot-status    - проверить статус бота"
    echo "  quiz-bot-logs      - просмотреть логи"
    echo "  quiz-bot-restart   - перезапустить бота"
    echo "  quiz-bot-update    - обновить бота"
    echo ""
    echo "Не забудьте:"
    echo "  1. Указать BOT_TOKEN в файле /home/quizbot/morning-quiz-bot-beta/.env"
    echo "  2. Перезапустить бота: sudo systemctl restart quiz-bot"
    echo "  3. Проверить логи: sudo journalctl -u quiz-bot -f"
    echo ""
}

# Главная функция
main() {
    echo "=== Morning Quiz Bot - Deployment Script ==="
    echo ""
    
    check_sudo
    update_system
    install_dependencies
    create_bot_user
    clone_repository
    setup_venv
    create_env_file
    create_systemd_service
    setup_logging
    create_management_scripts
    create_nginx_config
    final_setup
    print_instructions
}

# Запуск скрипта
main "$@" 