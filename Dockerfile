# Morning Quiz Bot - Dockerfile
FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Создание пользователя для безопасности
RUN useradd -m -s /bin/bash quizbot

# Установка рабочей директории
WORKDIR /app

# Копирование файлов зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY . .

# Создание необходимых директорий
RUN mkdir -p /app/data /app/config /var/log/quiz-bot

# Установка прав доступа
RUN chown -R quizbot:quizbot /app /var/log/quiz-bot

# Переключение на пользователя quizbot
USER quizbot

# Переменные окружения по умолчанию
ENV PYTHONPATH=/app
ENV LOG_LEVEL=INFO

# Проверка здоровья
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Команда запуска
CMD ["python", "bot.py"] 