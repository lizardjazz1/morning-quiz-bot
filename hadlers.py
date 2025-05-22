# quiz_bot/handlers.py
import logging
from telegram import Update, Poll
from telegram.ext import ContextTypes
from data_manager import save_user_data
from quiz_logic import (
    broadcast_quiz_to_active_chats, 
    get_random_quiz_questions, 
    send_next_quiz10_question,
    send_single_quiz_poll # Для /quiz
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_str = str(update.message.chat_id)
    user_id_str = str(update.effective_user.id)
    user_name = update.effective_user.full_name

    user_scores = context.bot_data['user_scores']
    
    # Регистрация пользователя и чата
    if chat_id_str not in user_scores:
        user_scores[chat_id_str] = {}
    if user_id_str not in user_scores.get(chat_id_str, {}):
        user_scores[chat_id_str][user_id_str] = {"name": user_name, "score": 0}
        save_user_data(user_scores) # Сохраняем сразу после регистрации нового

    await update.message.reply_text("Привет! Я буду присылать вам утреннюю викторину в формате опроса!")
    logging.info(f"Бот добавлен в чат {chat_id_str} пользователем {user_name} ({user_id_str})")

    # Добавляем чат в список активных
    active_chats = context.bot_data.get("active_chats", set())
    active_chats.add(chat_id_str)
    context.bot_data["active_chats"] = active_chats
    # Можно добавить сохранение active_chats в файл, если нужна персистентность между перезапусками

async def manual_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_str = str(update.message.chat_id)

    if chat_id_str not in context.bot_data.get("active_chats", set()):
        await update.message.reply_text("Сначала нужно запустить бота через /start")
        return
    
    quiz_data = context.bot_data.get("quiz_data", {})
    if not quiz_data:
        await update.message.reply_text("Нет вопросов для викторины.")
        return

    import random # для выбора случайного вопроса
    categories = list(quiz_data.keys())
    if not categories:
        await update.message.reply_text("В файле вопросов нет категорий.")
        return
    category = random.choice(categories)
    if not quiz_data[category]:
        await update.message.reply_text(f"В категории {category} нет вопросов.")
        return
    question_data = random.choice(quiz_data[category])

    await update.message.reply_text("🧠 Запускаю викторину вручную...")
    await send_single_quiz_poll(context, chat_id_str, question_data, is_quiz_session=False)


async def start_quiz10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_str = str(update.message.chat_id)

    if chat_id_str not in context.bot_data.get("active_chats", set()):
        await update.message.reply_text("Сначала нужно запустить бота через /start")
        return

    quiz_data = context.bot_data.get("quiz_data", {})
    questions = get_random_quiz_questions(quiz_data, 10)
    if not questions:
        await update.message.reply_text("Не могу начать квиз — нет вопросов 😕")
        return

    # Подготавливаем сессию
    context.bot_data['current_quiz_session'][chat_id_str] = {
        "questions": questions,
        "correct_answers": {}, # {user_id: {"name": name, "count": count}}
        "current_index": 0,
        "active": True
    }

    await update.message.reply_text("📚 Серия из 10 вопросов началась! 🧠")
    await send_next_quiz10_question(chat_id_str, context)


async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = answer.poll_id
    user_id_str = str(answer.user.id)
    user_name = answer.user.full_name
    
    # Убедимся, что опции есть, прежде чем брать первую
    if not answer.option_ids:
        logging.warning(f"Получен ответ на опрос {poll_id} без выбранных опций от {user_name} ({user_id_str}).")
        return # или какая-то другая логика

    selected_option_index = answer.option_ids[0]

    poll_info = context.bot_data['current_poll'].get(poll_id)
    if not poll_info:
        logging.warning(f"Получен ответ на неизвестный или уже обработанный опрос {poll_id}.")
        return

    chat_id_str = poll_info["chat_id"]
    correct_option_index = poll_info["correct_index"]
    is_quiz_session = poll_info.get("quiz_session", False)

    # Убираем опрос из списка активных, чтобы не обрабатывать повторно
    # (хотя Telegram обычно не шлет повторные poll_answer для одного юзера на один poll)
    # Но если опрос был остановлен, он может еще быть в current_poll
    # del context.bot_data['current_poll'][poll_id] # Делать это осторожно, т.к. другие юзеры могут еще отвечать

    user_scores = context.bot_data['user_scores']
    chat_scores = user_scores.setdefault(chat_id_str, {})
    
    is_correct = (selected_option_index == correct_option_index)

    if is_correct:
        # Обновление общего рейтинга для одиночных вопросов (не сессии)
        if not is_quiz_session:
            user_data = chat_scores.setdefault(user_id_str, {"name": user_name, "score": 0})
            user_data["name"] = user_name # Обновляем имя, если изменилось
            user_data["score"] += 1
            await context.bot.send_message(chat_id=chat_id_str, text=f"{user_name}, правильно! 👏 Ваш общий счет: {user_data['score']}.")
            save_user_data(user_scores) # Сохраняем изменения
        else: # Для сессии quiz10 сообщение о правильности будет после каждого вопроса
             await context.bot.send_message(chat_id=chat_id_str, text=f"{user_name}, правильно! ✅")


    # Логика для сессии quiz10
    if is_quiz_session and chat_id_str in context.bot_data['current_quiz_session']:
        session = context.bot_data['current_quiz_session'][chat_id_str]
        
        # Записываем ответ пользователя в сессии
        session_user_answers = session["correct_answers"].setdefault(user_id_str, {"name": user_name, "count": 0})
        session_user_answers["name"] = user_name # Обновляем имя
        if is_correct:
            session_user_answers["count"] += 1
        
        # Если этот ответ был на последний ожидаемый вопрос сессии от *этого* пользователя
        # Важно: следующий вопрос для quiz10 отсылается после *первого* ответа на текущий вопрос сессии
        # Это сделано в оригинальном коде: send_next_quiz_question вызывается сразу.
        # Чтобы не отправлять следующий вопрос много раз, если несколько юзеров отвечают на текущий,
        # current_poll[poll_id] удаляется после первого ответа, и send_next_quiz10_question
        # вызывается только один раз.
        # Поэтому, удаляем poll_id из current_poll здесь, после обработки ответа первого юзера на этот poll.
        if poll_id in context.bot_data['current_poll']:
            del context.bot_data['current_poll'][poll_id]
            await send_next_quiz10_question(chat_id_str, context)
    elif not is_quiz_session: # Одиночный вопрос, не из серии
        if poll_id in context.bot_data['current_poll']:
             del context.bot_data['current_poll'][poll_id] # Удаляем, так как он обработан


async def rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_str = str(update.message.chat_id)
    scores_for_chat = context.bot_data['user_scores'].get(chat_id_str, {})

    if not scores_for_chat:
        await update.message.reply_text("Никто ещё не отвечал в этом чате.")
        return

    sorted_scores = sorted(scores_for_chat.items(), key=lambda x: x[1]['score'], reverse=True)
    rating_text = "🏆 Таблица лидеров (общий зачет):\n\n"
    for idx, (uid, data) in enumerate(sorted_scores, 1):
        rating_text += f"{idx}. {data['name']} — {data['score']} очков\n"

    await update.message.reply_text(rating_text)

