#!/bin/bash
# МЕНЮ УПРАВЛЕНИЯ БОТОМ

echo "МЕНЮ УПРАВЛЕНИЯ MORNING QUIZ BOT"
echo "================================="
echo ""

# Проверяем права
if [[ $EUID -eq 0 ]]; then
    echo "ВНИМАНИЕ: ВЫ ВОШЛИ С ПРАВАМИ ROOT"
    echo ""
fi

show_menu() {
    echo "Выберите действие:"
    echo "=================="
    echo "1. Показать статус системы"
    echo "2. Переключить на режим обслуживания"
    echo "3. Переключить на основной бот"
    echo "4. Запустить основной бот"
    echo "5. Остановить основной бот"
    echo "6. Запустить fallback бот"
    echo "7. Конвертировать изображения в WebP"
    echo "8. Перезапустить бота"
    echo "9. Показать быстрые команды"
    echo "10. Выход"
    echo ""
}

# Функция для безопасного выполнения команд с повторными попытками
safe_execute() {
    local command="$1"
    local description="$2"
    local max_attempts=3
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        echo "Попытка $attempt из $max_attempts: $description"
        
        if eval "$command"; then
            echo "УСПЕХ: $description выполнено успешно!"
            return 0
        else
            echo "ОШИБКА: $description"
            if [ $attempt -lt $max_attempts ]; then
                echo "Повторная попытка через 2 секунды..."
                sleep 2
            fi
        fi
        
        attempt=$((attempt + 1))
    done
    
    echo "НЕУДАЧА: Не удалось выполнить $description после $max_attempts попыток"
    return 1
}

# Функция для запроса пароля с повторными попытками
get_sudo_password() {
    local max_attempts=3
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        echo -n "Введите пароль sudo (попытка $attempt из $max_attempts): "
        read -s password
        echo ""
        
        if echo "$password" | sudo -S true 2>/dev/null; then
            echo "Пароль принят!"
            return 0
        else
            echo "Неверный пароль"
            if [ $attempt -lt $max_attempts ]; then
                echo "Попробуйте еще раз..."
            fi
        fi
        
        attempt=$((attempt + 1))
    done
    
    echo "Превышено количество попыток ввода пароля"
    return 1
}

show_quick_commands() {
    echo "БЫСТРЫЕ КОМАНДЫ:"
    echo "================"
    echo ""
    echo "# Проверка статуса"
    echo "python3 simple_switcher.py status"
    echo ""
    echo "# Переключение режимов"
    echo "python3 simple_switcher.py to-maintenance 'Причина'"
    echo "python3 simple_switcher.py to-main"
    echo ""
    echo "# Управление сервисами"
    echo "sudo systemctl start quiz-bot"
    echo "sudo systemctl stop quiz-bot"
    echo "sudo systemctl status quiz-bot"
    echo ""
    echo "# Конвертация изображений"
    echo "python3 scripts/convert_and_metadata.py"
    echo "python3 scripts/convert_and_metadata.py --metadata-only"
    echo ""
    echo "# Перезагрузка сервера"
    echo "sudo reboot"
    echo ""
    echo "# Интерактивное управление"
    echo "sudo ./bot_control.sh"
    echo ""
}

# Основной цикл
while true; do
    show_menu
    read -p "Ваш выбор (1-10): " choice

    case $choice in
        1)
            echo ""
            echo "СТАТУС СИСТЕМЫ:"
            echo "==============="
            python3 simple_switcher.py status
            echo ""
            ;;
        2)
            echo ""
            read -p "Причина обслуживания: " reason
            if [ -z "$reason" ]; then
                reason="Ручное переключение"
            fi
            echo ""
            safe_execute "python3 simple_switcher.py to-maintenance '$reason'" "Переключение на режим обслуживания"
            echo ""
            ;;
        3)
            echo ""
            safe_execute "python3 simple_switcher.py to-main" "Переключение на основной бот"
            echo ""
            ;;
        4)
            echo ""
            echo "Запуск основного бота..."
            if get_sudo_password; then
                safe_execute "sudo systemctl start quiz-bot" "Запуск основного бота"
                sleep 2
                echo "Статус сервиса:"
                sudo systemctl status quiz-bot --no-pager -l | head -5
            fi
            echo ""
            ;;
        5)
            echo ""
            echo "Остановка основного бота..."
            if get_sudo_password; then
                safe_execute "sudo systemctl stop quiz-bot" "Остановка основного бота"
                sleep 2
                echo "Статус: $(sudo systemctl is-active quiz-bot)"
            fi
            echo ""
            ;;
        6)
            echo ""
            echo "Запуск fallback бота..."
            echo "(Убедитесь, что режим обслуживания включен!)"
            echo "Нажмите Ctrl+C для остановки"
            python3 maintenance_fallback.py
            echo ""
            ;;
        7)
            echo ""
            echo "КОНВЕРТАЦИЯ ИЗОБРАЖЕНИЙ:"
            echo "========================"
            echo ""
            echo "Выберите режим конвертации:"
            echo "1. Полная конвертация (PNG/JPG → WebP + метаданные)"
            echo "2. Только добавление метаданных для существующих WebP"
            echo "3. Назад в главное меню"
            echo ""
            read -p "Ваш выбор (1-3): " convert_choice
            
            case $convert_choice in
                1)
                    echo ""
                    echo "Запуск полной конвертации..."
                    echo "Проверяем зависимости..."
                    
                    # Проверяем наличие Pillow
                    if ! python3 -c "from PIL import Image" 2>/dev/null; then
                        echo "Pillow не установлен. Попробуем установить..."
                        echo "Попытка 1: sudo apt install python3-pil"
                        if sudo apt install -y python3-pil 2>/dev/null; then
                            echo "Pillow установлен через apt"
                        else
                            echo "Попытка 2: pip install --user Pillow"
                            if pip install --user Pillow 2>/dev/null; then
                                echo "Pillow установлен через pip --user"
                            else
                                echo "Попытка 3: pip install --break-system-packages Pillow"
                                if pip install --break-system-packages Pillow 2>/dev/null; then
                                    echo "Pillow установлен через pip --break-system-packages"
                                else
                                    echo "Не удалось установить Pillow автоматически"
                                    echo "Установите вручную: sudo apt install python3-pil"
                                    echo "Затем запустите конвертацию снова"
                                    read -p "Нажмите Enter для продолжения..."
                                    continue
                                fi
                            fi
                        fi
                    fi
                    
                    python3 scripts/convert_and_metadata.py
                    echo ""
                    ;;
                2)
                    echo ""
                    echo "Добавление метаданных для существующих WebP..."
                    echo "Проверяем зависимости..."
                    
                    # Проверяем наличие Pillow
                    if ! python3 -c "from PIL import Image" 2>/dev/null; then
                        echo "Pillow не установлен. Попробуем установить..."
                        echo "Попытка 1: sudo apt install python3-pil"
                        if sudo apt install -y python3-pil 2>/dev/null; then
                            echo "Pillow установлен через apt"
                        else
                            echo "Попытка 2: pip install --user Pillow"
                            if pip install --user Pillow 2>/dev/null; then
                                echo "Pillow установлен через pip --user"
                            else
                                echo "Попытка 3: pip install --break-system-packages Pillow"
                                if pip install --break-system-packages Pillow 2>/dev/null; then
                                    echo "Pillow установлен через pip --break-system-packages"
                                else
                                    echo "Не удалось установить Pillow автоматически"
                                    echo "Установите вручную: sudo apt install python3-pil"
                                    echo "Затем запустите конвертацию снова"
                                    read -p "Нажмите Enter для продолжения..."
                                    continue
                                fi
                            fi
                        fi
                    fi
                    
                    python3 scripts/convert_and_metadata.py --metadata-only
                    echo ""
                    ;;
                3)
                    echo ""
                    echo "Возврат в главное меню"
                    ;;
                *)
                    echo ""
                    echo "Неверный выбор"
                    ;;
            esac
            ;;
        8)
            echo ""
            echo "ПЕРЕЗАПУСК БОТА:"
            echo "================"
            echo ""
            echo "Перезапускаем бота..."
            if get_sudo_password; then
                safe_execute "sudo systemctl restart quiz-bot" "Перезапуск бота"
                sleep 2
                echo "Статус: $(sudo systemctl is-active quiz-bot)"
            fi
            echo ""
            ;;
        9)
            echo ""
            show_quick_commands
            ;;
        10)
            echo ""
            echo "До свидания!"
            exit 0
            ;;
        *)
            echo ""
            echo "Неверный выбор. Попробуйте еще раз."
            echo ""
            ;;
    esac

    if [ "$choice" != "9" ]; then
        echo ""
        read -p "Нажмите Enter для продолжения..."
        clear
    fi
done
