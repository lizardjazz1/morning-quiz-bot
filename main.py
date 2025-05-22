import logging
import os
import json
from telegram import Update, Poll
from telegram.ext import ApplicationBuilder, CommandHandler, PollAnswerHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
import random
import threading

# Загрузка токена
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# Логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Загрузка вопросов
def load_questions():
    try:
        with open('questions.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Ошибка при загрузке вопросов: {e}")
        return {}

# Загрузка пользовательских данных
def load_user_data():
    if not os.path.exists('users.json'):
        save_user_data({}) # Create users.json if it doesn't exist
    try:
        with open('users.json', 'r', encoding='utf-8') as f:
            # Handle empty file case
            content = f.read()
            if not content:
                return {}
            return json.loads(content)
    except (json.JSONDecodeError, Exception) as e:
        logging.error(f"Ошибка при загрузке рейтинга: {e}")
        # If error, try to save an empty dict and return it
        save_user_data({})
        return {}

# Сохранение пользовательских данных
def save_user_data(data):
    with open('users.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Периодический вывод для Replit
def keep_alive():
    print("⏰ Бот всё ещё работает...")
    # Use a daemon thread for keep_alive so it doesn't block shutdown
    timer = threading.Timer(7200, keep_alive)
    timer.daemon = True # Allow main program to exit even if timer is running
    timer.start()

if os.getenv("REPLIT_ENVIRONMENT") or os.getenv("REPLIT_CLUSTER"): # Check common Replit env vars
    keep_alive()

# Загружаем данные
quiz_data = load_questions()
user_scores = load_user_data()

# Хранение активных опросов
current_poll = {}  # {poll_id: {"chat_id": ..., "correct_index": ..., "message_id": ..., "quiz_session": True/False}}

# Хранение сессии квиза из 10 вопросов
current_quiz_session = {}
# Structure for current_quiz_session[chat_id_str]:
# {
#     "questions": [...],            # List of questions for this session
#     "session_scores": {            # Scores for THIS specific 10-question quiz
#         # user_id_str: {"name": "User Name", "score": 0}
#     },
#     "current_index": 0,            # Index of the next question to be sent
# }

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_str = str(update.message.chat_id)
    user_id_str = str(update.effective_user.id) # Ensure user_id is string for consistency
    user_name = update.effective_user.full_name

    if chat_id_str not in user_scores:
        user_scores[chat_id_str] = {}
    if user_id_str not in user_scores[chat_id_str]:
        user_scores[chat_id_str][user_id_str] = {"name": user_name, "score": 0}
        save_user_data(user_scores)
        await update.message.reply_text(f"Привет, {user_name}! Я буду присылать вам утреннюю викторину. Вы зарегистрированы!")
    else:
        # Update name if it changed, preserve score
        user_scores[chat_id_str][user_id_str]["name"] = user_name
        save_user_data(user_scores)
        await update.message.reply_text(f"С возвращением, {user_name}! Я буду присылать вам утреннюю викторину.")

    logging.info(f"Бот добавлен/запущен в чате {chat_id_str} пользователем {user_name} ({user_id_str})")

    active_chats = context.bot_data.get("active_chats", set())
    active_chats.add(chat_id_str) # chat_id_str is already a string
    context.bot_data["active_chats"] = active_chats

# Отправка случайного вопроса (один вопрос для всех активных чатов)
async def send_daily_quiz(context: ContextTypes.DEFAULT_TYPE): # Renamed for clarity
    active_chats = context.bot_data.get("active_chats", set())
    if not active_chats:
        logging.warning("Нет активных чатов для ежедневной рассылки")
        return
    if not quiz_data:
        logging.warning("Нет вопросов для ежедневной рассылки")
        for cid_str in active_chats:
            try:
                await context.bot.send_message(chat_id=int(cid_str), text="К сожалению, сегодня нет вопросов для ежедневной викторины.")
            except Exception as e:
                logging.error(f"Ошибка при отправке сообщения об отсутствии вопросов в чат {cid_str}: {e}")
        return

    categories = list(quiz_data.keys())
    if not categories:
        logging.warning("Категории вопросов пусты.")
        return
    category = random.choice(categories)
    if not quiz_data[category]:
        logging.warning(f"Категория {category} пуста.")
        return

    question_data = random.choice(quiz_data[category])
    options = question_data["options"]
    correct_answer = question_data["correct"]

    for cid_str in active_chats:
        try:
            cid = int(cid_str) # API expects integer chat_id
            message = await context.bot.send_poll(
                chat_id=cid,
                question=f"☀️ Ежедневный вопрос:\n{question_data['question']}",
                options=options,
                type=Poll.QUIZ,
                correct_option_id=options.index(correct_answer),
                is_anonymous=False,
                explanation=f"Правильный ответ: {correct_answer}"
            )
            poll_id = message.poll.id
            correct_index = options.index(correct_answer)
            current_poll[poll_id] = {
                "chat_id": str(cid), # Store as string for consistency with other IDs
                "correct_index": correct_index,
                "message_id": message.message_id,
                "quiz_session": False # This is a single daily quiz, not part of /quiz10
            }
        except Exception as e:
            logging.error(f"Ошибка при отправке ежедневного опроса в чат {cid_str}: {e}")
            if "chat not found" in str(e).lower() or "bot was blocked by the user" in str(e).lower():
                logging.info(f"Удаляю неактивный чат {cid_str} из рассылки.")
                active_chats.discard(cid_str)
                context.bot_data["active_chats"] = active_chats


# Получить случайные вопросы для квиза
def get_quiz_questions(count=10):
    all_questions = []
    for category_questions in quiz_data.values(): # Iterate through lists of questions
        all_questions.extend(category_questions)
    if not all_questions:
        return []
    # Ensure we don't try to sample more questions than available
    return random.sample(all_questions, min(count, len(all_questions)))

# Команда /quiz — вручную запускает ОДИН случайный вопрос ТОЛЬКО в текущем чате
async def manual_single_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_str = str(update.message.chat_id)

    if not quiz_data:
        await update.message.reply_text("Нет вопросов для викторины 😕")
        return

    categories = list(quiz_data.keys())
    if not categories:
        await update.message.reply_text("Категории вопросов пусты.")
        return
    category = random.choice(categories)
    if not quiz_data[category]: # Check if the chosen category has questions
        await update.message.reply_text(f"В категории '{category}' пока нет вопросов. Попробуйте позже или другую команду.")
        return


    question_data = random.choice(quiz_data[category])
    options = question_data["options"]
    correct_answer = question_data["correct"]

    await update.message.reply_text("🧠 Запускаю один случайный вопрос...")
    try:
        message = await context.bot.send_poll(
            chat_id=int(chat_id_str),
            question=question_data["question"],
            options=options,
            type=Poll.QUIZ,
            correct_option_id=options.index(correct_answer),
            is_anonymous=False,
            explanation=f"Правильный ответ: {correct_answer}"
        )
        poll_id = message.poll.id
        correct_index = options.index(correct_answer)
        current_poll[poll_id] = {
            "chat_id": chat_id_str,
            "correct_index": correct_index,
            "message_id": message.message_id,
            "quiz_session": False # Not part of /quiz10
        }
    except Exception as e:
        logging.error(f"Ошибка при отправке ручного опроса в чат {chat_id_str}: {e}")
        await update.message.reply_text("Произошла ошибка при отправке вопроса.")

# Команда /quiz10 — серия из 10 вопросов подряд
async def start_quiz10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_str = str(update.message.chat_id)

    if chat_id_str in current_quiz_session:
        await update.message.reply_text("Серия из 10 вопросов уже идет в этом чате! Дождитесь её окончания или используйте /stopquiz10 для отмены (если будет добавлена).")
        return

    questions_needed = 10
    questions = get_quiz_questions(questions_needed)
    if not questions or len(questions) < questions_needed :
        await update.message.reply_text(f"Не могу начать квиз — недостаточно вопросов (нужно минимум {questions_needed}, найдено {len(questions)}) 😕")
        return

    current_quiz_session[chat_id_str] = {
        "questions": questions,
        "session_scores": {}, # Stores {user_id_str: {"name": name, "score": 0}} for this session
        "current_index": 0
    }
    await update.message.reply_text(f"📚 Серия из {questions_needed} вопросов началась! 🧠\nОтвечайте на каждый вопрос. Результаты будут в конце.")
    await send_next_quiz10_question(chat_id_str, context)

# Отправка следующего вопроса серии /quiz10
async def send_next_quiz10_question(chat_id_str: str, context: ContextTypes.DEFAULT_TYPE):
    session = current_quiz_session.get(chat_id_str)

    if not session: # Session might have been cleaned up or never existed
        logging.warning(f"send_next_quiz10_question: Сессия для чата {chat_id_str} не найдена.")
        return

    if session["current_index"] >= len(session["questions"]):
        # All questions sent, show final group results
        await show_quiz10_final_group_results(chat_id_str, context)
        if chat_id_str in current_quiz_session: # Clean up session
             del current_quiz_session[chat_id_str]
             logging.info(f"Сессия /quiz10 для чата {chat_id_str} завершена и удалена.")
        return

    question_data = session["questions"][session["current_index"]]
    options = question_data["options"]
    correct_answer = question_data["correct"]

    try:
        message = await context.bot.send_poll(
            chat_id=int(chat_id_str), # API expects int
            question=f"📌 Вопрос {session['current_index'] + 1}/{len(session['questions'])}:\n{question_data['question']}",
            options=options,
            type=Poll.QUIZ,
            correct_option_id=options.index(correct_answer),
            is_anonymous=False,
            explanation=f"Правильный ответ: {correct_answer}" # Show correct answer after voting
        )
        poll_id = message.poll.id
        correct_index = options.index(correct_answer)
        current_poll[poll_id] = {
            "chat_id": chat_id_str,
            "correct_index": correct_index,
            "message_id": message.message_id,
            "quiz_session": True  # This is part of a /quiz10 series
        }
        session["current_index"] += 1
        # Do NOT save current_quiz_session here, it's stateful in memory during the quiz
    except Exception as e:
        logging.error(f"Ошибка при отправке опроса серии /quiz10 в чат {chat_id_str}: {e}")
        await context.bot.send_message(chat_id=int(chat_id_str), text="❌ Не могу продолжить серию — ошибка отправки вопроса.")
        if chat_id_str in current_quiz_session: # Clean up session on error
             del current_quiz_session[chat_id_str]
             logging.info(f"Сессия /quiz10 для чата {chat_id_str} прервана из-за ошибки и удалена.")


# Обработка ответов на опрос
async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = answer.poll_id
    user_id_str = str(answer.user.id)
    user_name = answer.user.full_name # Or use answer.user.first_name etc.

    poll_info = current_poll.get(poll_id)
    if not poll_info:
        # This can happen if the poll is old, or bot restarted and lost current_poll state
        # or if it's an answer to a poll not managed by this logic (e.g. manually created by user)
        logging.info(f"Получен ответ на неизвестный, старый или не отслеживаемый опрос {poll_id} от пользователя {user_name} ({user_id_str}). Игнорируется.")
        return

    chat_id_str = poll_info["chat_id"]
    correct_index = poll_info["correct_index"]
    is_quiz_session = poll_info.get("quiz_session", False)

    selected_option_id = answer.option_ids[0] if answer.option_ids else -1 # Handle no option selected

    # Ensure user is in global scores (should be by /start, but as a fallback)
    if chat_id_str not in user_scores:
        user_scores[chat_id_str] = {}
    if user_id_str not in user_scores[chat_id_str]:
        user_scores[chat_id_str][user_id_str] = {"name": user_name, "score": 0}
    else: # Ensure name is up-to-date
        user_scores[chat_id_str][user_id_str]["name"] = user_name


    is_correct = (selected_option_id == correct_index)

    if is_correct:
        user_scores[chat_id_str][user_id_str]["score"] += 1
        # Telegram's Poll.QUIZ type automatically shows correctness to the user who voted.
        # No need for an extra "Правильно!" message from the bot here.
    # else:
        # Telegram also shows incorrectness.

    save_user_data(user_scores) # Save global score update

    if is_quiz_session and chat_id_str in current_quiz_session:
        session = current_quiz_session[chat_id_str]

        # Update session_scores for the /quiz10
        if user_id_str not in session["session_scores"]:
            session["session_scores"][user_id_str] = {"name": user_name, "score": 0}
        else: # Update name in case it changed
             session["session_scores"][user_id_str]["name"] = user_name

        if is_correct:
            session["session_scores"][user_id_str]["score"] += 1

        # The "first answerer advances the quiz" logic:
        # If this poll_id is still in current_poll, it means this is the first answer
        # (or first processed answer) for THIS poll message.
        if poll_id in current_poll:
            del current_poll[poll_id] # Mark this poll message as "handled" for advancing.
            # Only the first answer to a specific poll message triggers the next question.
            await send_next_quiz10_question(chat_id_str, context)
        # If poll_id was already deleted, it means another user's answer to the *same poll message*
        # (or a concurrent processing of another answer) already triggered the next question.
        # This user's score is recorded, but they don't advance the quiz further from this specific answer.

# Показ финальных результатов для СЕРИИ /quiz10
async def show_quiz10_final_group_results(chat_id_str: str, context: ContextTypes.DEFAULT_TYPE):
    session = current_quiz_session.get(chat_id_str) # This should be called *before* session is deleted
    if not session:
        logging.warning(f"show_quiz10_final_group_results: Попытка показать результаты для несуществующей или уже удаленной сессии в чате {chat_id_str}")
        # Optionally send a message if this state is reached unexpectedly
        # await context.bot.send_message(chat_id=int(chat_id_str), text="Не удалось найти данные завершенной сессии для отображения результатов.")
        return

    session_scores_data = session.get("session_scores", {})
    num_questions_in_session = len(session.get("questions", [])) # Get actual number of questions in session

    if num_questions_in_session == 0: # Should not happen if quiz started correctly
        logging.error(f"show_quiz10_final_group_results: В сессии для чата {chat_id_str} 0 вопросов.")
        await context.bot.send_message(chat_id=int(chat_id_str), text="Произошла ошибка: не найдено вопросов в завершенной сессии.")
        return

    if not session_scores_data:
        await context.bot.send_message(chat_id=int(chat_id_str), text=f"🏁 Серия из {num_questions_in_session} вопросов завершена! Никто не участвовал. Результатов нет.")
        return

    results_list = []
    for user_id, data in session_scores_data.items():
        user_name = data.get("name", "Неизвестный игрок")
        session_score = data.get("score", 0)
        # Fetch the latest global score
        global_score_entry = user_scores.get(chat_id_str, {}).get(user_id, {"score": 0, "name": user_name})
        global_score = global_score_entry["score"]
        results_list.append({"name": user_name, "session_score": session_score, "global_score": global_score})

    # Sort by session_score (descending), then by global_score (descending as tie-breaker), then name
    results_list.sort(key=lambda x: (-x["session_score"], -x["global_score"], x["name"]))

    result_text = f"🏁 Результаты серии из {num_questions_in_session} вопросов: 🏁\n\n"
    for idx, res_data in enumerate(results_list, 1):
        s_score = res_data['session_score']
        g_score = res_data['global_score']
        name = res_data['name']

        emoji = ""
        if idx == 1 and s_score > 0: emoji = "🏆 "
        elif idx == 2 and s_score > 0: emoji = "🥈 "
        elif idx == 3 and s_score > 0: emoji = "🥉 "
        elif s_score == num_questions_in_session: emoji = "🎉 " # Perfect score
        elif s_score >= num_questions_in_session * 0.7: emoji = "✨ "
        elif s_score >= num_questions_in_session * 0.5: emoji = "👏 "
        else: emoji = "👍 "


        result_text += f"{idx}. {emoji}{name} — {s_score}/{num_questions_in_session}\n"
        result_text += f"   (Общий рейтинг: {g_score} очков)\n"

    result_text += "\n🔥 Молодцы! Теперь вы знаете ещё больше!"

    await context.bot.send_message(chat_id=int(chat_id_str), text=result_text)
    logging.info(f"Показаны финальные результаты для /quiz10 в чате {chat_id_str}")

# Команда /rating — показывает таблицу лидеров
async def rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_str = str(update.message.chat_id)
    scores_in_chat = user_scores.get(chat_id_str, {})

    if not scores_in_chat:
        await update.message.reply_text("Никто ещё не отвечал в этом чате. Рейтинг пуст.")
        return

    # Create a list of tuples (user_id, name, score) for sorting
    # Ensure names are up-to-date from the primary user_scores storage
    sorted_participants = []
    for user_id, data in scores_in_chat.items():
        sorted_participants.append({
            "id": user_id,
            "name": data.get("name", f"Игрок {user_id[:4]}..."), # Fallback name
            "score": data.get("score", 0)
        })

    # Sort by score descending, then by name alphabetically as a tie-breaker
    sorted_participants.sort(key=lambda item: (-item['score'], item['name']))

    rating_text = "🏆 Таблица лидеров (общий рейтинг):\n"
    if not sorted_participants: # Should be caught by `if not scores_in_chat` but as a safeguard
        await update.message.reply_text("Рейтинг пока пуст.")
        return

    for idx, data in enumerate(sorted_participants, 1):
        medal = ""
        if idx == 1: medal = "🥇 "
        elif idx == 2: medal = "🥈 "
        elif idx == 3: medal = "🥉 "
        rating_text += f"{idx}. {medal}{data['name']} — {data['score']} очков\n"

    await update.message.reply_text(rating_text)

# Основная функция
if __name__ == '__main__':
    print("🔧 Запуск бота...")
    if not TOKEN:
        logging.error("❌ Токен BOT_TOKEN не найден. Убедитесь, что он указан в файле .env или в переменных окружения.")
        raise ValueError("Токен BOT_TOKEN не найден.")
    if not quiz_data:
        logging.warning("⚠️ Файл questions.json не загружен или пуст. Викторины могут не работать корректно.")
        # You might want to exit or prevent quiz commands if questions are essential and missing.
        # For now, it will just log a warning.

    print(f"✅ Токен загружен: {TOKEN[:5]}...{TOKEN[-5:]}")
    application = ApplicationBuilder().token(TOKEN).build()

    # Сохраняем user_scores и active_chats в bot_data для персистентности между перезапусками (если PTB это поддерживает)
    # Однако, для JSON файлов, лучше при запуске загружать, а при изменении сохранять.
    # `bot_data` полезен для временных данных сессии, но для `user_scores` у нас есть `users.json`.
    # `active_chats` можно загружать при старте, если хранить их в файле.
    # For now, active_chats will reset on bot restart unless explicitly saved/loaded.

    # Регистрация команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("quiz", manual_single_quiz)) # For one random question
    application.add_handler(CommandHandler("quiz10", start_quiz10))
    application.add_handler(CommandHandler("rating", rating))
    application.add_handler(PollAnswerHandler(handle_poll_answer))

    # Планировщик для ежедневной викторины
    # Убедитесь, что часовой пояс соответствует вашим ожиданиям.
    # Например, 'Europe/Moscow', 'UTC', 'Asia/Yekaterinburg'
    # Если не указать timezone, APScheduler может использовать системный часовой пояс,
    # что может быть нежелательно на серверах с другим TZ.
    try:
        scheduler = BackgroundScheduler(timezone="Europe/Moscow") # Пример: Московское время
        scheduler.add_job(send_daily_quiz, 'cron', hour=8, minute=0, args=[application])
        scheduler.start()
        print("⏰ Ежедневная викторина запланирована на 08:00 (по указанному часовому поясу).")
    except Exception as e:
        logging.error(f"Ошибка при настройке планировщика: {e}")
        print("⚠️ Не удалось запустить планировщик для ежедневной викторины.")


    print("✅ Бот запущен. Ожидание команд и сообщений...")
    application.run_polling()
