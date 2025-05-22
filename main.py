import logging
import os
import json
from telegram import Update, Poll
from telegram.ext import ApplicationBuilder, CommandHandler, PollAnswerHandler, ContextTypes, JobQueue
# from apscheduler.schedulers.background import BackgroundScheduler # Заменяем на JobQueue от PTB
from dotenv import load_dotenv
import random
import threading
from typing import List, Tuple, Dict, Any, Optional

# --- Константы ---
QUESTIONS_FILE = 'questions.json'
USERS_FILE = 'users.json'
DEFAULT_POLL_OPEN_PERIOD = 30  # Секунд для каждого вопроса (кроме последнего в сессии)
FINAL_ANSWER_WINDOW_SECONDS = 90 # Дополнительное время на ответ на ПОСЛЕДНИЙ вопрос в /quiz10

# Загрузка токена
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# Логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные переменные для данных
quiz_data: Dict[str, Dict[str, Dict[str, Any]]] = {}
user_scores: Dict[str, Dict[str, Any]] = {}

# Хранение активных опросов
# {poll_id: {"chat_id": str, "message_id": int, "correct_index": int,
#             "quiz_session": bool, "question_details": dict,
#             "next_question_triggered_for_this_poll": bool,
#             "associated_quiz_session_chat_id": Optional[str]}} # Для связи с сессией
current_poll: Dict[str, Dict[str, Any]] = {}

# Хранение сессии квиза из 10 вопросов
# {chat_id_str: {"questions": [полные детали вопроса],
#                 "session_scores": {user_id_str: {"name": "...", "score": 0}},
#                 "current_index": 0,  # Индекс *следующего* вопроса для отправки
#                 "message_id_intro": Optional[int],
#                 "final_results_job": Optional[Any] }} # Для хранения задачи JobQueue
current_quiz_session: Dict[str, Dict[str, Any]] = {}


# --- Функции загрузки и сохранения данных ---
def load_questions():
    global quiz_data
    try:
        with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
            quiz_data = json.load(f)
            logger.info(f"Загружено {sum(len(cat) for cat in quiz_data.values())} вопросов.")
    except FileNotFoundError:
        logger.error(f"Файл вопросов {QUESTIONS_FILE} не найден.")
        quiz_data = {}
    except json.JSONDecodeError:
        logger.error(f"Ошибка декодирования JSON в файле вопросов {QUESTIONS_FILE}.")
        quiz_data = {}
    except Exception as e:
        logger.error(f"Неизвестная ошибка при загрузке вопросов: {e}")
        quiz_data = {}

def load_user_data():
    global user_scores
    if not os.path.exists(USERS_FILE):
        save_user_data({})
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content:
                user_scores = {}
                return
            user_scores = json.loads(content)
    except json.JSONDecodeError:
        logger.error(f"Ошибка декодирования JSON в файле пользователей {USERS_FILE}. Создается пустой файл.")
        save_user_data({})
        user_scores = {}
    except Exception as e:
        logger.error(f"Ошибка при загрузке рейтинга: {e}")
        save_user_data({})
        user_scores = {}

def save_user_data(data):
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка при сохранении пользовательских данных: {e}")

# Периодический вывод для Replit
def keep_alive():
    # Эта функция больше не нужна, если вы не на Replit или используете другой метод keep-alive
    # Если вы на Replit, лучше использовать веб-сервер (например, Flask/FastAPI) для keep_alive
    # logger.info("⏰ Бот всё ещё работает (keep_alive)...")
    # threading.Timer(7200, keep_alive).start() # Не рекомендуется для долгосрочных ботов
    pass

# if os.getenv("REPLIT_ENVIRONMENT") or os.getenv("REPLIT_CLUSTER"):
#     keep_alive()


# --- Инициализация данных при запуске ---
load_questions()
load_user_data()


# --- Вспомогательные функции ---
def get_user_mention(user_id: int, user_name: str) -> str:
    return f"[{user_name}](tg://user?id={user_id})"

def prepare_poll_options(question_details: Dict[str, Any]) -> Tuple[str, List[str], int, List[str]]:
    """
    Готовит и перемешивает варианты ответов для опроса.
    Возвращает: (текст вопроса, перемешанные варианты, правильный индекс после перемешивания, оригинальные варианты)
    """
    q_text = question_details["question"]
    correct_answer = question_details["options"][question_details["correct_option_index"]]
    options = list(question_details["options"]) # Копируем, чтобы не изменять оригинал
    random.shuffle(options)
    new_correct_index = options.index(correct_answer)
    return q_text, options, new_correct_index, question_details["options"]

def get_random_questions(category: str, count: int) -> List[Dict[str, Any]]:
    """Получает 'count' случайных вопросов из указанной категории."""
    if category not in quiz_data or not quiz_data[category]:
        return []
    
    all_question_keys = list(quiz_data[category].keys())
    if len(all_question_keys) < count:
        selected_keys = all_question_keys # Берем все, если их меньше, чем запрошено
    else:
        selected_keys = random.sample(all_question_keys, count)
    
    selected_questions = []
    for key in selected_keys:
        question_detail = quiz_data[category][key].copy() # Копируем, чтобы не изменять оригинал
        question_detail["original_key"] = key # Сохраняем ключ для возможной отладки или статистики
        selected_questions.append(question_detail)
    return selected_questions


# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_str = str(update.message.chat_id)
    user = update.effective_user
    user_id_str = str(user.id)

    if chat_id_str not in user_scores:
        user_scores[chat_id_str] = {}
    if user_id_str not in user_scores[chat_id_str]:
        user_scores[chat_id_str][user_id_str] = {"name": user.full_name, "score": 0, "answered_polls": set()}
    else: # Обновить имя, если изменилось
        user_scores[chat_id_str][user_id_str]["name"] = user.full_name

    save_user_data(user_scores)
    await update.message.reply_text(
        "Привет! Я бот для викторин.\n"
        "Используйте /quiz_category <название категории> для начала одиночного вопроса по категории.\n"
        "Используйте /quiz10 <название категории> для начала серии из 10 вопросов.\n"
        "Используйте /rating для просмотра рейтинга.\n"
        "Используйте /categories для просмотра доступных категорий.\n"
        "Используйте /stopquiz10 для досрочной остановки серии из 10 вопросов."
    )

async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not quiz_data:
        await update.message.reply_text("Категории вопросов еще не загружены или отсутствуют.")
        return
    
    category_list = "\n".join([f"- {cat}" for cat in quiz_data.keys() if quiz_data[cat]]) # Показываем только непустые
    if not category_list:
        await update.message.reply_text("Доступных категорий с вопросами нет.")
    else:
        await update.message.reply_text(f"Доступные категории:\n{category_list}")

async def quiz_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_id_str = str(chat_id)

    if not context.args:
        await update.message.reply_text("Пожалуйста, укажите категорию. Пример: /quiz_category ОбщиеЗнания")
        return
    category_name = " ".join(context.args)

    if category_name not in quiz_data or not quiz_data[category_name]:
        await update.message.reply_text(f"Категория '{category_name}' не найдена или в ней нет вопросов.")
        return

    question_list = get_random_questions(category_name, 1)
    if not question_list:
        await update.message.reply_text(f"В категории '{category_name}' закончились вопросы или их нет.")
        return
    
    question_details = question_list[0]
    q_text, options, correct_index, _ = prepare_poll_options(question_details)

    try:
        sent_poll_message = await context.bot.send_poll(
            chat_id=chat_id,
            question=q_text[:Poll.MAX_QUESTION_LENGTH], # Обрезка, если вопрос слишком длинный
            options=options,
            is_anonymous=False,
            type=Poll.QUIZ,
            correct_option_id=correct_index,
            open_period=DEFAULT_POLL_OPEN_PERIOD
        )
        current_poll[sent_poll_message.poll.id] = {
            "chat_id": chat_id_str,
            "message_id": sent_poll_message.message_id,
            "correct_index": correct_index,
            "quiz_session": False, # Это одиночный вопрос
            "question_details": question_details,
            "next_question_triggered_for_this_poll": False, # Не используется для одиночных
            "associated_quiz_session_chat_id": None
        }
    except Exception as e:
        logger.error(f"Ошибка отправки одиночного опроса в чат {chat_id}: {e}")
        await update.message.reply_text("Не удалось отправить вопрос. Попробуйте позже.")


async def start_quiz10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_id_str = str(chat_id)

    if chat_id_str in current_quiz_session:
        await update.message.reply_text("Серия из 10 вопросов уже запущена в этом чате. Используйте /stopquiz10 для остановки.")
        return

    if not context.args:
        await update.message.reply_text("Пожалуйста, укажите категорию. Пример: /quiz10 ОбщиеЗнания")
        return
    category_name = " ".join(context.args)

    if category_name not in quiz_data or not quiz_data[category_name]:
        await update.message.reply_text(f"Категория '{category_name}' не найдена или в ней нет вопросов.")
        return

    questions_for_session = get_random_questions(category_name, 10)
    if len(questions_for_session) < 1: # Проверяем, есть ли хоть какие-то вопросы
        await update.message.reply_text(f"В категории '{category_name}' недостаточно вопросов для начала серии (нужно хотя бы 1).")
        return
    if len(questions_for_session) < 10:
         await update.message.reply_text(f"Внимание: в категории '{category_name}' найдено только {len(questions_for_session)} вопросов. Серия будет короче.")


    intro_message = await update.message.reply_text(f"Начинаем квиз из {len(questions_for_session)} вопросов по категории '{category_name}'! Приготовьтесь.")

    current_quiz_session[chat_id_str] = {
        "questions": questions_for_session,
        "session_scores": {},  # {user_id_str: {"name": "...", "score": 0}}
        "current_index": 0,    # Индекс *следующего* вопроса для отправки
        "message_id_intro": intro_message.message_id if intro_message else None,
        "final_results_job": None # Для отложенного показа результатов
    }
    # Обнуляем answered_polls для всех пользователей этого чата перед началом новой сессии /quiz10
    if chat_id_str in user_scores:
        for uid in user_scores[chat_id_str]:
            user_scores[chat_id_str][uid]["answered_polls"] = set() # Очищаем для новой серии
    save_user_data(user_scores)

    await send_next_quiz_question(context, chat_id_str)


async def send_next_quiz_question(context: ContextTypes.DEFAULT_TYPE, chat_id_str: str):
    session = current_quiz_session.get(chat_id_str)
    if not session:
        logger.warning(f"send_next_quiz_question: Сессия для чата {chat_id_str} не найдена.")
        return

    if session["current_index"] >= len(session["questions"]):
        # Все вопросы отправлены, теперь ждем FINAL_ANSWER_WINDOW_SECONDS
        logger.info(f"Все {len(session['questions'])} вопросов для сессии в чате {chat_id_str} отправлены. Запускаем таймер для результатов.")
        
        # Удаляем предыдущий job, если он был (на всякий случай, хотя логика не должна этого допускать)
        if session.get("final_results_job"):
            session["final_results_job"].schedule_removal()
            logger.info(f"Удален предыдущий job для результатов сессии в чате {chat_id_str}")

        job = context.job_queue.run_once(
            show_quiz10_final_results_after_delay,
            FINAL_ANSWER_WINDOW_SECONDS,
            chat_id=int(chat_id_str), # job_queue требует int для chat_id
            name=f"quiz10_results_{chat_id_str}"
        )
        session["final_results_job"] = job
        current_quiz_session[chat_id_str] = session # Сохраняем job в сессии
        await context.bot.send_message(
            chat_id=int(chat_id_str),
            text=f"Это был последний вопрос! У вас есть {FINAL_ANSWER_WINDOW_SECONDS} секунд, чтобы ответить на него. Затем будут показаны результаты."
        )
        return

    question_details = session["questions"][session["current_index"]]
    q_text, options, correct_idx, _ = prepare_poll_options(question_details)

    try:
        sent_poll_message = await context.bot.send_poll(
            chat_id=int(chat_id_str),
            question=q_text[:Poll.MAX_QUESTION_LENGTH],
            options=options,
            is_anonymous=False,
            type=Poll.QUIZ,
            correct_option_id=correct_idx,
            open_period=DEFAULT_POLL_OPEN_PERIOD + (FINAL_ANSWER_WINDOW_SECONDS if session["current_index"] == len(session["questions"]) - 1 else 0) # Длиннее для последнего
        )
        current_poll[sent_poll_message.poll.id] = {
            "chat_id": chat_id_str,
            "message_id": sent_poll_message.message_id,
            "correct_index": correct_idx,
            "quiz_session": True,
            "question_details": question_details,
            "next_question_triggered_for_this_poll": False,
            "associated_quiz_session_chat_id": chat_id_str
        }
        session["current_index"] += 1
        current_quiz_session[chat_id_str] = session # Обновляем сессию с новым current_index

    except Exception as e:
        logger.error(f"Ошибка отправки вопроса сессии в чат {chat_id_str}: {e}")
        # Попытаться завершить сессию, если отправка не удалась? Или пропустить вопрос?
        # Пока просто логируем. Можно добавить более сложную обработку.
        # Если это был критический сбой, можно вызвать stop_quiz10_logic
        await context.bot.send_message(int(chat_id_str), "Произошла ошибка при отправке следующего вопроса. Сессия может быть прервана.")
        await stop_quiz10_logic(int(chat_id_str), context, "Ошибка отправки вопроса.")


async def show_quiz10_final_results_after_delay(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id # Получаем chat_id из job'а
    chat_id_str = str(chat_id)

    session = current_quiz_session.get(chat_id_str)
    if not session:
        logger.info(f"show_quiz10_final_results_after_delay: Сессия для чата {chat_id_str} не найдена (возможно, уже завершена).")
        return

    logger.info(f"Таймер сработал. Показываем финальные результаты для сессии в чате {chat_id_str}.")

    num_questions_in_session = len(session["questions"])
    results_text = f"🏁 **Результаты квиза ({num_questions_in_session} вопросов):** 🏁\n\n"

    # Сортировка по очкам в сессии (убывание), затем по имени
    sorted_session_participants = sorted(
        session["session_scores"].items(),
        key=lambda item: (-item[1]["score"], item[1]["name"].lower())
    )

    if not sorted_session_participants:
        results_text += "В этой сессии никто не участвовал или не ответил правильно."
    else:
        for rank, (user_id_str, data) in enumerate(sorted_session_participants, 1):
            user_name = data["name"]
            session_score = data["score"]
            # Получаем общий рейтинг пользователя из user_scores
            total_score = user_scores.get(chat_id_str, {}).get(user_id_str, {}).get("score", 0)
            user_mention_md = get_user_mention(int(user_id_str), user_name)
            results_text += (
                f"{rank}. {user_mention_md}: {session_score}/{num_questions_in_session} (общий рейтинг: {total_score})\n"
            )
    
    await context.bot.send_message(chat_id=chat_id, text=results_text, parse_mode='Markdown')

    # Очистка сессии и связанных опросов
    cleanup_quiz_session(chat_id_str)
    logger.info(f"Сессия квиза для чата {chat_id_str} завершена и очищена.")

def cleanup_quiz_session(chat_id_str: str):
    """Очищает данные завершенной или остановленной сессии /quiz10."""
    if chat_id_str in current_quiz_session:
        session = current_quiz_session.pop(chat_id_str)
        if session.get("final_results_job"):
            session["final_results_job"].schedule_removal()
            logger.info(f"Удален job для результатов сессии в чате {chat_id_str} при очистке.")

    # Удаляем все активные опросы, связанные с этой сессией
    polls_to_delete = [
        poll_id for poll_id, poll_info in current_poll.items()
        if poll_info.get("associated_quiz_session_chat_id") == chat_id_str
    ]
    for poll_id in polls_to_delete:
        if poll_id in current_poll:
            del current_poll[poll_id]
            logger.debug(f"Удален опрос {poll_id} из current_poll при очистке сессии {chat_id_str}")


async def stop_quiz10_logic(chat_id: int, context: ContextTypes.DEFAULT_TYPE, reason: str = "остановлена пользователем"):
    """Логика остановки сессии квиза."""
    chat_id_str = str(chat_id)
    if chat_id_str in current_quiz_session:
        cleanup_quiz_session(chat_id_str) # Используем новую функцию очистки
        await context.bot.send_message(chat_id=chat_id, text=f"Серия из 10 вопросов {reason}.")
        logger.info(f"Серия квиза для чата {chat_id_str} остановлена: {reason}.")
    else:
        await context.bot.send_message(chat_id=chat_id, text="Нет активной серии из 10 вопросов для остановки.")

async def stop_quiz10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stop_quiz10_logic(update.effective_chat.id, context)


async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = answer.poll_id
    user = answer.user
    user_id_str = str(user.id)
    user_name = user.full_name

    poll_info = current_poll.get(poll_id)
    if not poll_info:
        logger.debug(f"Получен ответ на неизвестный или старый опрос: {poll_id}")
        return

    chat_id_str = poll_info["chat_id"]
    is_quiz_session_poll = poll_info["quiz_session"]
    correct_option_index = poll_info["correct_index"]
    selected_option_ids = answer.option_ids

    # Убедимся, что пользователь существует в user_scores для данного чата
    if chat_id_str not in user_scores:
        user_scores[chat_id_str] = {}
    if user_id_str not in user_scores[chat_id_str]:
        user_scores[chat_id_str][user_id_str] = {"name": user_name, "score": 0, "answered_polls": set()}
    else: # Обновить имя, если изменилось
        user_scores[chat_id_str][user_id_str]["name"] = user_name


    # Проверка на повторное голосование (если open_period большой, пользователь мог переголосовать)
    # Для викторин типа QUIZ, Telegram обычно не позволяет переголосовать, но для REGULAR позволяет.
    # Для QUIZ type, option_ids будет содержать 0 или 1 элемент.
    if poll_id in user_scores[chat_id_str][user_id_str].get("answered_polls", set()):
        # logger.info(f"Пользователь {user_name} ({user_id_str}) уже отвечал на опрос {poll_id}.")
        # Если нужно запретить изменение ответа, можно просто return
        # Однако, если опрос еще открыт, ТГ сам обработает изменение ответа. Нам важно зафиксировать первое правильное.
        # Для QUIZ, это условие обычно не должно срабатывать так как ТГ сам контролирует один ответ.
        pass # Продолжаем обработку, так как ТГ мог позволить изменить ответ, и мы его просто перезапишем.

    is_correct = bool(selected_option_ids and selected_option_ids[0] == correct_option_index)

    if is_correct:
        # Обновляем общий счет только если это ПЕРВЫЙ ПРАВИЛЬНЫЙ ответ на этот вопрос от этого пользователя
        # Для простоты сейчас: если ответил правильно - всегда +1 к общему.
        # Если нужно учитывать только первый ответ на данный poll_id, нужна другая логика.
        # Текущая логика: если пользователь изменил ответ на правильный, он получит балл.
        # Если ответ был правильный, потом изменен на неправильный - балл не снимается (нужна доп. логика).
        # Для quiz-опросов ТГ обычно не дает менять ответ после первого.
        
        # Только если пользователь ЕЩЕ НЕ отвечал правильно на этот опрос
        # Это предотвращает начисление очков, если пользователь как-то умудрился ответить несколько раз
        # (маловероятно для QUIZ type, но для безопасности)
        # Мы убрали answered_polls из user_scores для QUIZ10 перед стартом сессии.
        if poll_id not in user_scores[chat_id_str][user_id_str].get("answered_polls", set()):
             user_scores[chat_id_str][user_id_str]["score"] = user_scores[chat_id_str][user_id_str].get("score", 0) + 1

    # Запоминаем, что пользователь ответил на этот опрос (любым образом)
    # Эта структура answered_polls в user_scores больше для одиночных опросов или если нужна сложная логика
    # Для quiz10 мы ее очищаем перед началом.
    if "answered_polls" not in user_scores[chat_id_str][user_id_str]: # на случай если структура неполная
        user_scores[chat_id_str][user_id_str]["answered_polls"] = set()
    user_scores[chat_id_str][user_id_str]["answered_polls"].add(poll_id)
    save_user_data(user_scores)

    # Логика для сессии /quiz10
    if is_quiz_session_poll:
        session_chat_id = poll_info.get("associated_quiz_session_chat_id")
        if session_chat_id and session_chat_id in current_quiz_session:
            session = current_quiz_session[session_chat_id]
            
            # Обновляем сессионные очки
            if user_id_str not in session["session_scores"]:
                session["session_scores"][user_id_str] = {"name": user_name, "score": 0}
            elif session["session_scores"][user_id_str]["name"] != user_name: # Обновить имя если изменилось
                 session["session_scores"][user_id_str]["name"] = user_name

            # Начисляем балл за сессию только если это первый правильный ответ на этот вопрос в рамках сессии
            # Используем уникальность poll_id. Если пользователь ответил правильно на poll_id, он получает +1 к session_score
            # Если нужно учитывать только первый ответ на этот вопрос *в этой сессии*, то нужна проверка
            # что этот poll_id еще не принес ему очков в ЭТОЙ сессии.
            # Но так как poll_id уникален для каждого вопроса сессии, простого добавления достаточно, если нет бага с многократным ответом.
            if is_correct:
                # Чтобы не начислять дважды за один и тот же вопрос сессии, если бы ТГ позволил два ответа
                # мы можем хранить poll_id отвеченных в сессии для пользователя.
                # Однако, для QUIZ type это избыточно. Достаточно просто добавить.
                # Упрощаем: если ответил правильно - добавляем в сессионный счет.
                # Если пользователь ответил -> передумал -> ответил правильно, он получит балл.
                # Важно, чтобы это был первый *засчитанный* правильный ответ.
                # Проблема: если пользователь ответил правильно, потом неправильно, потом опять правильно.
                # Решение: хранить set отвеченных poll_id в session_scores[user_id_str]["answered_in_session_polls"]
                
                # Простая логика: если правильно, увеличиваем счет сессии.
                # Если нужно предотвратить повторное начисление за тот же вопрос,
                # нужно будет добавить в session["session_scores"][user_id_str] поле типа answered_poll_ids_in_session = set()
                # и проверять, был ли poll_id уже там. Для QUIZ type это избыточно.
                
                # Предполагаем, что на один poll от одного юзера приходит один PollAnswer
                # Если он был правильный, то увеличиваем счет.
                # Если он изменил ответ (ТГ позволяет для НЕ quiz-type), то этот handler вызовется снова.
                # Для QUIZ type - один ответ.
                
                # Чтобы не дублировать очки, если пользователь меняет ответ с правильного на правильный (невозможно)
                # или если somehow PollAnswer приходит дважды
                # мы должны убедиться, что мы добавляем очки только один раз за этот poll_id для этого пользователя в этой сессии.
                # Самый простой способ - это хранить список poll_id, на которые пользователь уже ответил правильно в этой сессии.

                # Давайте заведем такой список в session_scores пользователя
                if "correctly_answered_poll_ids_in_session" not in session["session_scores"][user_id_str]:
                    session["session_scores"][user_id_str]["correctly_answered_poll_ids_in_session"] = set()

                if is_correct and poll_id not in session["session_scores"][user_id_str]["correctly_answered_poll_ids_in_session"]:
                    session["session_scores"][user_id_str]["score"] += 1
                    session["session_scores"][user_id_str]["correctly_answered_poll_ids_in_session"].add(poll_id)
                    current_quiz_session[session_chat_id] = session # Сохраняем обновленную сессию


            # Переход к следующему вопросу (кроме последнего)
            # Следующий вопрос отправляется по ПЕРВОМУ ответу на ТЕКУЩИЙ вопрос
            # И если это не последний вопрос (т.к. для последнего включается таймер)
            current_question_index_in_session = session["current_index"] -1 # т.к. current_index указывает на СЛЕДУЮЩИЙ
            is_it_last_question_of_session = (current_question_index_in_session == len(session["questions"]) - 1)

            if not poll_info.get("next_question_triggered_for_this_poll") and not is_it_last_question_of_session:
                # Если еще не последний вопрос И следующий вопрос еще не был запущен для ЭТОГО опроса
                poll_info["next_question_triggered_for_this_poll"] = True
                current_poll[poll_id] = poll_info # Сохраняем изменение флага
                logger.info(f"Первый ответ на вопрос {current_question_index_in_session +1} сессии в чате {session_chat_id}. Отправляем следующий.")
                await send_next_quiz_question(context, session_chat_id)
            elif is_it_last_question_of_session:
                 logger.debug(f"Ответ на последний вопрос сессии от {user_name}. Ожидаем таймер.")
            # Если next_question_triggered_for_this_poll уже True, ничего не делаем (следующий вопрос уже отправлен или отправляется)

        else:
            logger.warning(f"Ответ на опрос {poll_id} из сессии, но сессия {poll_info.get('associated_quiz_session_chat_id')} не найдена в current_quiz_session.")
    # else:
        # Это ответ на одиночный опрос /quiz_category, здесь ничего дополнительно делать не нужно после обновления очков.
        # logger.debug(f"Обработан ответ на одиночный опрос {poll_id} от {user_name}")


async def rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_str = str(update.effective_chat.id)
    if chat_id_str not in user_scores or not user_scores[chat_id_str]:
        await update.message.reply_text("Рейтинг для этого чата пока пуст.")
        return

    # Сортировка пользователей по убыванию очков, затем по имени
    sorted_users = sorted(
        user_scores[chat_id_str].items(),
        key=lambda item: (-item[1].get("score", 0), item[1].get("name", "").lower())
    )

    rating_text = "🏆 **Общий рейтинг игроков в этом чате:** 🏆\n\n"
    for rank, (user_id, data) in enumerate(sorted_users, 1):
        user_name = data.get("name", f"User_{user_id}")
        score = data.get("score", 0)
        user_mention_md = get_user_mention(int(user_id), user_name)
        rating_text += f"{rank}. {user_mention_md} - {score} очков\n"
    
    if len(sorted_users) == 0:
        rating_text += "Пока никто не набрал очков."

    await update.message.reply_text(rating_text, parse_mode='Markdown')

# --- Точка входа ---
def main():
    if not TOKEN:
        logger.critical("Токен бота не найден. Установите переменную окружения BOT_TOKEN.")
        return

    logger.info("Бот запускается...")

    application = ApplicationBuilder().token(TOKEN).build()

    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("categories", categories_command))
    application.add_handler(CommandHandler("quiz_category", quiz_category))
    application.add_handler(CommandHandler("quiz10", start_quiz10))
    application.add_handler(CommandHandler("stopquiz10", stop_quiz10))
    application.add_handler(CommandHandler("rating", rating))
    application.add_handler(PollAnswerHandler(handle_poll_answer))

    logger.info("Обработчики добавлены.")
    application.run_polling()
    logger.info("Бот остановлен.")


if __name__ == '__main__':
    main()
