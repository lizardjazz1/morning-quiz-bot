# quiz_bot/quiz_logic.py
import random
import logging
from telegram import Poll
from data_manager import save_user_data # Для сохранения очков в сессии quiz10

# Эти переменные теперь будут управляться через context.bot_data в main.py
# quiz_data = load_questions()
# current_poll = {}
# current_quiz_session = {}

async def send_single_quiz_poll(context, chat_id, question_data, is_quiz_session=False, question_num=None):
    """Отправляет один опрос в указанный чат."""
    options = question_data["options"]
    correct_answer = question_data["correct"]
    
    question_text = question_data["question"]
    if is_quiz_session and question_num is not None:
        question_text = f"📌 Вопрос {question_num}:\n{question_text}"

    try:
        message = await context.bot.send_poll(
            chat_id=chat_id,
            question=question_text,
            options=options,
            type=Poll.QUIZ,
            correct_option_id=options.index(correct_answer),
            is_anonymous=False
        )
        poll_id = message.poll.id
        correct_index = options.index(correct_answer)

        context.bot_data['current_poll'][poll_id] = {
            "chat_id": str(chat_id),
            "correct_index": correct_index,
            "message_id": message.message_id,
            "quiz_session": is_quiz_session
        }
        logging.info(f"Опрос {poll_id} отправлен в чат {chat_id}.")
        return True
    except Exception as e:
        logging.error(f"Ошибка при отправке опроса в чат {chat_id}: {e}")
        return False

async def broadcast_quiz_to_active_chats(context):
    """Отправляет случайный вопрос всем активным чатам."""
    active_chats = context.bot_data.get("active_chats", set())
    quiz_data = context.bot_data.get("quiz_data", {})

    if not active_chats:
        logging.warning("Нет активных чатов для рассылки")
        return
    if not quiz_data:
        logging.warning("Нет вопросов для рассылки")
        return

    categories = list(quiz_data.keys())
    if not categories:
        logging.warning("В файле вопросов нет категорий.")
        return
        
    category = random.choice(categories)
    if not quiz_data[category]:
        logging.warning(f"В категории {category} нет вопросов.")
        return

    question_data = random.choice(quiz_data[category])

    for cid in active_chats:
        await send_single_quiz_poll(context, cid, question_data, is_quiz_session=False)

def get_random_quiz_questions(quiz_data, count=10):
    """Получает список случайных вопросов для серии."""
    all_questions = []
    if not quiz_data:
        return []
    for category_questions in quiz_data.values():
        all_questions.extend(category_questions)
    
    if not all_questions:
        return []
    return random.sample(all_questions, min(count, len(all_questions)))


async def send_next_quiz10_question(chat_id_str, context):
    """Отправляет следующий вопрос из серии quiz10."""
    session = context.bot_data['current_quiz_session'].get(chat_id_str)
    
    if not session or not session["active"] or session["current_index"] >= len(session["questions"]):
        await show_quiz10_final_results(chat_id_str, context)
        return

    question_data = session["questions"][session["current_index"]]
    q_num = session['current_index'] + 1
    
    success = await send_single_quiz_poll(context, chat_id_str, question_data, is_quiz_session=True, question_num=q_num)
    if success:
        session["current_index"] += 1
    else:
        await context.bot.send_message(chat_id=chat_id_str, text="❌ Не могу продолжить — ошибка отправки вопроса.")
        # Возможно, стоит завершить сессию здесь
        if chat_id_str in context.bot_data['current_quiz_session']:
            del context.bot_data['current_quiz_session'][chat_id_str]


async def show_quiz10_final_results(chat_id_str, context):
    """Показывает финальные результаты для сессии quiz10."""
    session = context.bot_data['current_quiz_session'].pop(chat_id_str, None)
    if not session:
        return

    correct_answers_map = session["correct_answers"] # {user_id: {"name": name, "count": count}}
    
    # Обновляем общий рейтинг user_scores на основе результатов сессии
    # Этого не было в оригинальном коде, но логично добавить, если quiz10 тоже влияет на общий рейтинг.
    # Если нет, эту часть можно убрать.
    user_scores_chat = context.bot_data['user_scores'].setdefault(chat_id_str, {})
    for user_id, data in correct_answers_map.items():
        user_scores_chat.setdefault(user_id, {"name": data["name"], "score": 0})
        # user_scores_chat[user_id]["score"] += data["count"] # Раскомментировать, если очки из quiz10 суммируются с общими
    # save_user_data(context.bot_data['user_scores']) # Сохраняем обновленные общие очки

    # Формируем текст результатов quiz10
    results_list = sorted(correct_answers_map.items(), key=lambda x: x[1]['count'], reverse=True)

    result_text = "🏁 Вот как вы прошли квиз из 10 вопросов:\n\n"
    if not results_list:
        result_text += "Никто не ответил на вопросы в этой сессии. 🤷‍♂️\n"
    else:
        for idx, (uid, data) in enumerate(results_list, 1):
            total = data["count"]
            emoji = "✨" if total == 10 else "👏" if total >= 7 else "👍" if total >= 5 else "🙂"
            result_text += f"{idx}. {data['name']} — {total}/10 {emoji}\n"

    result_text += "\n🔥 Молодцы! Теперь вы знаете ещё больше!"
    await context.bot.send_message(chat_id=chat_id_str, text=result_text)
