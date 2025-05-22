# config.py

# BOT_NAME = "Умная Сова"
# BOT_USERNAME = "quizowlbot"

# Пути к данным
QUESTIONS_FILE = 'data/questions.json'
USERS_FILE = 'data/users.json'

# Токен из .env
from dotenv import load_dotenv
import os

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")