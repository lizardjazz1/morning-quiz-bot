#!/bin/bash

# Morning Quiz Bot - Улучшенный скрипт развертывания
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

# Запрос пути установки
get_install_path() {
    echo ""
    print_info "Где вы хотите установить бота?"
    echo "1. В домашней папке текущего пользователя (~/morning-quiz-bot)"
    echo "2. В корневой папке (/opt/morning-quiz-bot)"
    echo "3. Указать свой путь"
    echo ""
    read -p "Выберите вариант (1-3): " choice

    case $choice in
        1)
            INSTALL_PATH="$HOME/morning-quiz-bot"
            BOT_USER="$USER"
            ;;
        2)
            INSTALL_PATH="/opt/morning-quiz-bot"
            BOT_USER="root"
            ;;
        3)
            read -p "Введите полный путь для установки: " INSTALL_PATH
            read -p "Введите имя пользователя для запуска бота (или оставьте пустым для текущего): " BOT_USER
            if [ -z "$BOT_USER" ]; then
                BOT_USER="$USER"
            fi
            ;;
        *)
            print_error "Неверный выбор. Используется домашняя папка."
            INSTALL_PATH="$HOME/morning-quiz-bot"
            BOT_USER="$USER"
            ;;
    esac

    print_info "Бот будет установлен в: $INSTALL_PATH"
    print_info "Пользователь для запуска: $BOT_USER"
}

# Клонирование репозитория
clone_repository() {
    print_info "Клонирование репозитория..."
    
    # Создание директории
    mkdir -p "$(dirname "$INSTALL_PATH")"
    
    if [ -d "$INSTALL_PATH" ]; then
        print_warning "Директория уже существует, обновляем..."
        cd "$INSTALL_PATH"
        git pull origin main
    else
        cd "$(dirname "$INSTALL_PATH")"
        git clone https://github.com/lizardjazz1/morning-quiz-bot.git "$(basename "$INSTALL_PATH")"
    fi
    
    # Установка прав доступа
    chown -R "$BOT_USER:$BOT_USER" "$INSTALL_PATH"
    print_success "Репозиторий готов"
}

# Настройка виртуального окружения
setup_venv() {
    print_info "Настройка виртуального окружения..."
    
    cd "$INSTALL_PATH"
    
    # Создание виртуального окружения
    if [ "$BOT_USER" = "root" ]; then
        python3 -m venv venv
    else
        sudo -u "$BOT_USER" python3 -m venv venv
    fi
    
    # Активация и установка зависимостей
    if [ "$BOT_USER" = "root" ]; then
        source venv/bin/activate && pip install -r requirements.txt
    else
        sudo -u "$BOT_USER" bash -c "source venv/bin/activate && pip install -r requirements.txt"
    fi
    
    print_success "Виртуальное окружение настроено"
}

# Создание .env файла
create_env_file() {
    print_info "Создание файла .env..."
    
    ENV_FILE="$INSTALL_PATH/.env"
    
    if [ ! -f "$ENV_FILE" ]; then
        cat > "$ENV_FILE" << EOF
# Morning Quiz Bot Environment Variables
BOT_TOKEN=your_telegram_bot_token_here
LOG_LEVEL=INFO
EOF
        chown "$BOT_USER:$BOT_USER" "$ENV_FILE"
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
User=$BOT_USER
Group=$BOT_USER
WorkingDirectory=$INSTALL_PATH
Environment=PATH=$INSTALL_PATH/venv/bin
ExecStart=$INSTALL_PATH/venv/bin/python bot.py
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

# Создание скриптов управления
create_management_scripts() {
    print_info "Создание скриптов управления..."
    
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
cd $INSTALL_PATH
sudo -u $BOT_USER git pull origin main
sudo -u $BOT_USER bash -c "source venv/bin/activate && pip install -r requirements.txt"
sudo systemctl restart quiz-bot
echo "Quiz Bot обновлен и перезапущен"
EOF
    
    # Установка прав на выполнение
    chmod +x /usr/local/bin/quiz-bot-*
    
    print_success "Скрипты управления созданы"
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
    echo "📁 Установка: $INSTALL_PATH"
    echo "👤 Пользователь: $BOT_USER"
    echo ""
    echo "Полезные команды:"
    echo "  quiz-bot-status    - проверить статус бота"
    echo "  quiz-bot-logs      - просмотреть логи"
    echo "  quiz-bot-restart   - перезапустить бота"
    echo "  quiz-bot-update    - обновить бота"
    echo ""
    echo "Не забудьте:"
    echo "  1. Указать BOT_TOKEN в файле $INSTALL_PATH/.env"
    echo "  2. Перезапустить бота: sudo systemctl restart quiz-bot"
    echo "  3. Проверить логи: sudo journalctl -u quiz-bot -f"
    echo ""
    echo "Для ручного запуска:"
    echo "  cd $INSTALL_PATH"
    echo "  source venv/bin/activate"
    echo "  python bot.py"
    echo ""
}

# Главная функция
main() {
    echo "=== Morning Quiz Bot - Улучшенный скрипт развертывания ==="
    echo ""
    
    check_sudo
    update_system
    install_dependencies
    get_install_path
    clone_repository
    setup_venv
    create_env_file
    create_systemd_service
    create_management_scripts
    final_setup
    print_instructions
}

# Запуск скрипта
main "$@" 