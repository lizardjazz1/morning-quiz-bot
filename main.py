import logging
import os
import json
from telegram import Update, Poll
from telegram.ext import ApplicationBuilder, CommandHandler, PollAnswerHandler, ContextTypes, JobQueue
from dotenv import load_dotenv
import random
import threading # Этот импорт больше не используется активно для keep_alive
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
current_poll: Dict[str, Dict[str, Any]] = {}

# Хранение сессии квиза
current_quiz_session: Dict[str, Dict[str, Any]] = {}


# --- Функции загрузки и сохранения данных ---
def load_questions():
    global quiz_data
    try:
        with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
            quiz_data = json.load(f)
            logger.info(f"Загружено {sum(len(cat) for cat in quiz_data.values() if isinstance(cat, dict))} вопросов.")
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
        save_user_data({}) # Создаем пустой файл, если его нет
        user_scores = {}
        return
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content: # Если файл пуст
                user_scores = {}
                return
            user_scores = json.loads(content)
    except json.JSONDecodeError:
        logger.error(f"Ошибка декодирования JSON в файле пользователей {USERS_FILE}. Создается пустой файл.")
        save_user_data({})
        user_scores = {}
    except Exception as e:
        logger.error(f"Ошибка при загрузке рейтинга: {e}")
        save_user_data({}) # На всякий случай сбросим к пустому состоянию
        user_scores = {}

def save_user_data(data):
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка при сохранении пользовательских данных: {e}")

# --- Инициализация данных при запуске ---
load_questions()
load_user_data()


# --- Вспомогательные функции ---
def get_user_mention(user_id: int, user_name: str) -> str:
    return f"[{user_name}](tg://user?id={user_id})"

def prepare_poll_options(question_details: Dict[str, Any]) -> Tuple[str, List[str], int, List[str]]:
    q_text = question_details["question"]
    correct_answer = question_details["options"][question_details["correct_option_index"]]
    options = list(question_details["options"])
    random.shuffle(options)
    new_correct_index = options.index(correct_answer)
    return q_text, options, new_correct_index, question_details["options"]

def get_random_questions(category: str, count: int) -> List[Dict[str, Any]]:
    """Получает 'count' случайных вопросов из указанной категории."""
    if category not in quiz_data or not isinstance(quiz_data.get(category), dict) or not quiz_data[category]:
        logger.warning(f"get_random_questions: Категория '{category}' не найдена, не является словарем или пуста.")
        return []
    
    category_data = quiz_data[category]
    all_question_keys = list(category_data.keys())

    if not all_question_keys:
        logger.warning(f"get_random_questions: В категории '{category}' нет ключей вопросов.")
        return []

    if len(all_question_keys) < count:
        selected_keys = all_question_keys 
        random.shuffle(selected_keys) # Shuffle if taking all available from category
    else:
        selected_keys = random.sample(all_question_keys, count)
    
    selected_questions = []
    for key in selected_keys:
        question_detail = category_data.get(key)
        if isinstance(question_detail, dict):
            question_copy = question_detail.copy() 
            question_copy["original_key_in_category"] = key 
            question_copy["original_category"] = category # Добавляем информацию о категории
            selected_questions.append(question_copy)
        else:
            logger.warning(f"get_random_questions: question_detail для ключа {key} в категории {category} не является словарем: {type(question_detail)}")
            
    return selected_questions

def get_random_questions_from_all(count: int) -> List[Dict[str, Any]]:
    """Получает 'count' случайных вопросов из всех доступных категорий."""
    all_questions_with_details: List[Dict[str, Any]] = []
    if not quiz_data:
        logger.warning("get_random_questions_from_all: quiz_data пуст.")
        return []

    for category, questions_in_cat in quiz_data.items():
        if questions_in_cat and isinstance(questions_in_cat, dict):
            for q_key, q_detail in questions_in_cat.items():
                if isinstance(q_detail, dict):
                    question_copy = q_detail.copy()
                    question_copy["original_key_in_category"] = q_key
                    question_copy["original_category"] = category
                    all_questions_with_details.append(question_copy)
                else:
                    logger.warning(f"get_random_questions_from_all: q_detail для ключа {q_key} в категории {category} не является словарем: {type(q_detail)}")
        elif not questions_in_cat:
             logger.debug(f"get_random_questions_from_all: Категория {category} пуста.")
        else: # questions_in_cat is not a dict
            logger.warning(f"get_random_questions_from_all: questions_in_cat для категории {category} не является словарем: {type(questions_in_cat)}")

    if not all_questions_with_details:
        logger.info("get_random_questions_from_all: Не найдено ни одного вопроса во всех категориях.")
        return []

    if len(all_questions_with_details) <= count:
        random.shuffle(all_questions_with_details)
        return all_questions_with_details
    else:
        return random.sample(all_questions_with_details, count)


# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_str = str(update.message.chat_id)
    user = update.effective_user
    user_id_str = str(user.id)

    if chat_id_str not in user_scores:
        user_scores[chat_id_str] = {}
    if user_id_str not in user_scores[chat_id_str]:
        user_scores[chat_id_str][user_id_str] = {"name": user.full_name, "score": 0, "answered_polls": set()}
    else:
        user_scores[chat_id_str][user_id_str]["name"] = user.full_name

    save_user_data(user_scores)
    await update.message.reply_text(
        "Привет! Я бот для викторин.\n"
        "Используйте /quiz_category <название категории> для начала одиночного вопроса по категории.\n"
        "Используйте /quiz10 [название категории] для начала серии из 10 вопросов (если категория не указана, вопросы будут из всех доступных).\n"
        "Используйте /rating для просмотра рейтинга.\n"
        "Используйте /categories для просмотра доступных категорий.\n"
        "Используйте /stopquiz10 для досрочной остановки серии из 10 вопросов."
    )

async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not quiz_data:
        await update.message.reply_text("Категории вопросов еще не загружены или отсутствуют.")
        return
    
    category_list = "\n".join([f"- {cat}" for cat in quiz_data.keys() if isinstance(quiz_data.get(cat), dict) and quiz_data[cat]])
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
        await update.message.reply_text(f"В категории '{category_name}' не нашлось вопросов.") # Сообщение изменено для краткости
        return
    
    question_details = question_list[0]
    q_text, options, correct_index, _ = prepare_poll_options(question_details)

    try:
        sent_poll_message = await context.bot.send_poll(
            chat_id=chat_id,
            question=q_text[:Poll.MAX_QUESTION_LENGTH],
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
            "quiz_session": False,
            "question_details": question_details,
            "next_question_triggered_for_this_poll": False,
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

    questions_for_session: List[Dict[str, Any]] = []
    category_source_description: str = "" 
    num_questions_to_fetch = 10

    if not context.args: # Категория не указана
        logger.info(f"Запрос /quiz10 без категории от чата {chat_id_str}.")
        questions_for_session = get_random_questions_from_all(num_questions_to_fetch)
        category_source_description = "всех доступных категорий"
        
        if not questions_for_session:
            await update.message.reply_text("Не удалось найти вопросы. Возможно, база вопросов пуста или все категории пусты.")
            return

    else: # Категория указана
        category_name = " ".join(context.args)
        logger.info(f"Запрос /quiz10 с категорией '{category_name}' от чата {chat_id_str}.")

        if category_name not in quiz_data or not isinstance(quiz_data.get(category_name), dict) or not quiz_data[category_name]:
            await update.message.reply_text(f"Категория '{category_name}' не найдена или в ней нет вопросов.")
            return

        questions_for_session = get_random_questions(category_name, num_questions_to_fetch)
        category_source_description = f"категории '{category_name}'"
        
        if not questions_for_session: 
            await update.message.reply_text(f"В категории '{category_name}' не нашлось вопросов для квиза.")
            return
            
    actual_num_questions = len(questions_for_session)
    
    intro_message_text = f"Начинаем квиз из {category_source_description}! "
    if actual_num_questions == 1:
        intro_message_text += f"Подготовлен {actual_num_questions} вопрос. Приготовьтесь!"
    elif actual_num_questions < num_questions_to_fetch : # Но больше 0
         intro_message_text += f"Подготовлено {actual_num_questions} вопросов (меньше {num_questions_to_fetch}). Приготовьтесь!"
    else: # actual_num_questions == num_questions_to_fetch (или больше, если get_random_... вернуло больше, но оно не должно)
        intro_message_text += f"Подготовлено {actual_num_questions} вопросов. Приготовьтесь!"

    intro_message = await update.message.reply_text(intro_message_text)

    current_quiz_session[chat_id_str] = {
        "questions": questions_for_session,
        "session_scores": {},
        "current_index": 0,
        "message_id_intro": intro_message.message_id if intro_message else None,
        "final_results_job": None
    }

    if chat_id_str in user_scores:
        for uid in user_scores[chat_id_str]: # uid это user_id_str
            if isinstance(user_scores[chat_id_str].get(uid), dict):
                user_scores[chat_id_str][uid]["answered_polls"] = set()
    save_user_data(user_scores)

    await send_next_quiz_question(context, chat_id_str)


async def send_next_quiz_question(context: ContextTypes.DEFAULT_TYPE, chat_id_str: str):
    session = current_quiz_session.get(chat_id_str)
    if not session:
        logger.warning(f"send_next_quiz_question: Сессия для чата {chat_id_str} не найдена.")
        return

    if session["current_index"] >= len(session["questions"]):
        logger.info(f"Все {len(session['questions'])} вопросов для сессии в чате {chat_id_str} отправлены. Запускаем таймер для результатов.")
        
        if session.get("final_results_job"):
            session["final_results_job"].schedule_removal()
            logger.info(f"Удален предыдущий job для результатов сессии в чате {chat_id_str}")

        job = context.job_queue.run_once(
            show_quiz10_final_results_after_delay,
            FINAL_ANSWER_WINDOW_SECONDS,
            chat_id=int(chat_id_str),
            name=f"quiz10_results_{chat_id_str}"
        )
        session["final_results_job"] = job
        current_quiz_session[chat_id_str] = session
        await context.bot.send_message(
            chat_id=int(chat_id_str),
            text=f"Это был последний вопрос! У вас есть {FINAL_ANSWER_WINDOW_SECONDS} секунд, чтобы ответить на него. Затем будут показаны результаты."
        )
        return

    question_details = session["questions"][session["current_index"]]
    q_text, options, correct_idx, _ = prepare_poll_options(question_details)
    
    # Определяем open_period: длиннее для последнего вопроса
    is_last_question = (session["current_index"] == len(session["questions"]) - 1)
    current_open_period = DEFAULT_POLL_OPEN_PERIOD
    if is_last_question:
        # Время на последний вопрос = стандартное время + дополнительное окно на результаты
        # Это значит, что сам опрос будет открыт дольше.
        # Или, если мы хотим чтобы опрос закрылся через DEFAULT_POLL_OPEN_PERIOD, а потом было ожидание,
        # то FINAL_ANSWER_WINDOW_SECONDS - это задержка *после* закрытия опроса.
        # Текущая логика в send_poll для последнего вопроса:
        # open_period=DEFAULT_POLL_OPEN_PERIOD + (FINAL_ANSWER_WINDOW_SECONDS if session["current_index"] == len(session["questions"]) - 1 else 0)
        # Это делает сам опрос дольше.
        # А job `show_quiz10_final_results_after_delay` запускается с задержкой FINAL_ANSWER_WINDOW_SECONDS *после* отправки последнего вопроса.
        # Это может привести к тому, что результаты покажутся раньше, чем закроется опрос, если FINAL_ANSWER_WINDOW_SECONDS < open_period последнего вопроса.

        # Исправим: Опрос всегда DEFAULT_POLL_OPEN_PERIOD. Таймер FINAL_ANSWER_WINDOW_SECONDS запускается *после* отправки последнего вопроса.
        # Сообщение "У вас есть X секунд" должно отражать время до показа результатов.
        # Это означает, что у пользователя есть DEFAULT_POLL_OPEN_PERIOD на ответ на последний вопрос,
        # и еще (FINAL_ANSWER_WINDOW_SECONDS - DEFAULT_POLL_OPEN_PERIOD) времени, если они еще не ответили, до показа результатов.
        # Либо, FINAL_ANSWER_WINDOW_SECONDS - это общее время от момента отправки последнего вопроса до результатов.
        # Текущая формулировка "У вас есть {FINAL_ANSWER_WINDOW_SECONDS} секунд, чтобы ответить на него" предполагает, что это общее время.
        # А опрос должен быть открыт как минимум это время.
        current_open_period = FINAL_ANSWER_WINDOW_SECONDS # Делаем опрос открытым на всё время ожидания результатов
    
    try:
        sent_poll_message = await context.bot.send_poll(
            chat_id=int(chat_id_str),
            question=q_text[:Poll.MAX_QUESTION_LENGTH],
            options=options,
            is_anonymous=False,
            type=Poll.QUIZ,
            correct_option_id=correct_idx,
            open_period=current_open_period
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
        current_quiz_session[chat_id_str] = session

    except Exception as e:
        logger.error(f"Ошибка отправки вопроса сессии в чат {chat_id_str}: {e}")
        await context.bot.send_message(int(chat_id_str), "Произошла ошибка при отправке следующего вопроса. Сессия может быть прервана.")
        await stop_quiz10_logic(int(chat_id_str), context, "Ошибка отправки вопроса.")


async def show_quiz10_final_results_after_delay(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    chat_id_str = str(chat_id)

    session = current_quiz_session.get(chat_id_str)
    if not session:
        logger.info(f"show_quiz10_final_results_after_delay: Сессия для чата {chat_id_str} не найдена (возможно, уже завершена).")
        return

    logger.info(f"Таймер сработал. Показываем финальные результаты для сессии в чате {chat_id_str}.")

    num_questions_in_session = len(session["questions"])
    results_text = f"🏁 **Результаты квиза ({num_questions_in_session} вопросов):** 🏁\n\n"

    sorted_session_participants = sorted(
        session["session_scores"].items(),
        key=lambda item: (-item[1]["score"], item[1]["name"].lower())
    )

    if not sorted_session_participants:
        results_text += "В этой сессии никто не участвовал или не набрал очков."
    else:
        for rank, (user_id_str, data) in enumerate(sorted_session_participants, 1):
            user_name = data["name"]
            session_score = data["score"]
            total_score = user_scores.get(chat_id_str, {}).get(user_id_str, {}).get("score", 0)
            user_mention_md = get_user_mention(int(user_id_str), user_name)
            results_text += (
                f"{rank}. {user_mention_md}: {session_score}/{num_questions_in_session} (общий рейтинг: {total_score})\n"
            )
    
    try:
        await context.bot.send_message(chat_id=chat_id, text=results_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка отправки финальных результатов в чат {chat_id}: {e}")


    cleanup_quiz_session(chat_id_str)
    logger.info(f"Сессия квиза для чата {chat_id_str} завершена и очищена.")

def cleanup_quiz_session(chat_id_str: str):
    if chat_id_str in current_quiz_session:
        session = current_quiz_session.pop(chat_id_str)
        if session.get("final_results_job"):
            session["final_results_job"].schedule_removal()
            logger.info(f"Удален job для результатов сессии в чате {chat_id_str} при очистке.")

    polls_to_delete = [
        poll_id for poll_id, poll_info in current_poll.items()
        if poll_info.get("associated_quiz_session_chat_id") == chat_id_str
    ]
    for poll_id in polls_to_delete:
        if poll_id in current_poll:
            del current_poll[poll_id]
            logger.debug(f"Удален опрос {poll_id} из current_poll при очистке сессии {chat_id_str}")


async def stop_quiz10_logic(chat_id: int, context: ContextTypes.DEFAULT_TYPE, reason: str = "остановлена пользователем"):
    chat_id_str = str(chat_id)
    if chat_id_str in current_quiz_session:
        cleanup_quiz_session(chat_id_str)
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

    if chat_id_str not in user_scores:
        user_scores[chat_id_str] = {}
    if user_id_str not in user_scores[chat_id_str]:
        user_scores[chat_id_str][user_id_str] = {"name": user_name, "score": 0, "answered_polls": set()}
    else:
        user_scores[chat_id_str][user_id_str]["name"] = user_name
    
    # answered_polls в user_scores в основном для одиночных квизов или для предотвращения двойного начисления общего рейтинга.
    # Для quiz10, answered_polls очищается перед сессией.

    is_correct = bool(selected_option_ids and selected_option_ids[0] == correct_option_index)

    if is_correct:
        # Обновляем общий счет только если пользователь еще не отвечал ПРАВИЛЬНО на этот КОНКРЕТНЫЙ опрос (poll_id)
        # This check is important for overall score, even if session scores are handled separately.
        # user_scores[chat_id_str][user_id_str]["answered_polls"] stores poll_ids for which score was already given.
        # Let's rename "answered_polls" to "rewarded_poll_ids" to be clearer for overall score.
        # For now, let's assume "answered_polls" tracks polls for which any answer was given.
        # The logic for adding to overall score needs to be precise.
        # If this poll_id is NOT in the set of polls for which the user has ALREADY received a point.
        
        # Let's refine this: add to score if correct, and this poll_id hasn't yet given this user a point.
        # We will use a different set for this in user_scores for clarity.
        # Or, for simplicity, assume one correct answer per poll ID per user adds to global score.
        # The current logic `if poll_id not in user_scores[chat_id_str][user_id_str].get("answered_polls", set()):`
        # before adding to score was fine for preventing multiple global score additions for the same poll.
        # Let's keep it.
        
        # Убедимся, что `answered_polls` существует
        if "answered_polls" not in user_scores[chat_id_str][user_id_str]:
            user_scores[chat_id_str][user_id_str]["answered_polls"] = set()

        if poll_id not in user_scores[chat_id_str][user_id_str]["answered_polls"]:
             user_scores[chat_id_str][user_id_str]["score"] = user_scores[chat_id_str][user_id_str].get("score", 0) + 1
             user_scores[chat_id_str][user_id_str]["answered_polls"].add(poll_id) # Отмечаем, что за этот опрос балл начислен


    # save_user_data() вызывается здесь, чтобы сохранить обновленное имя или новый счет, если он изменился
    # Это может быть часто, но гарантирует сохранность.
    save_user_data(user_scores)


    if is_quiz_session_poll:
        session_chat_id = poll_info.get("associated_quiz_session_chat_id")
        if session_chat_id and session_chat_id in current_quiz_session:
            session = current_quiz_session[session_chat_id]
            
            if user_id_str not in session["session_scores"]:
                session["session_scores"][user_id_str] = {"name": user_name, "score": 0, "correctly_answered_poll_ids_in_session": set()}
            elif session["session_scores"][user_id_str]["name"] != user_name:
                 session["session_scores"][user_id_str]["name"] = user_name

            # Для сессионных очков:
            if is_correct and poll_id not in session["session_scores"][user_id_str]["correctly_answered_poll_ids_in_session"]:
                session["session_scores"][user_id_str]["score"] += 1
                session["session_scores"][user_id_str]["correctly_answered_poll_ids_in_session"].add(poll_id)
                current_quiz_session[session_chat_id] = session # Сохраняем обновленную сессию

            current_question_index_in_session = session["current_index"] -1 
            is_it_last_question_of_session = (current_question_index_in_session == len(session["questions"]) - 1)

            if not poll_info.get("next_question_triggered_for_this_poll") and not is_it_last_question_of_session:
                poll_info["next_question_triggered_for_this_poll"] = True
                current_poll[poll_id] = poll_info 
                logger.info(f"Первый ответ на вопрос {current_question_index_in_session +1} сессии в чате {session_chat_id}. Отправляем следующий.")
                await send_next_quiz_question(context, session_chat_id)
            elif is_it_last_question_of_session:
                 logger.debug(f"Ответ на последний вопрос сессии от {user_name}. Ожидаем таймер.")
        else:
            logger.warning(f"Ответ на опрос {poll_id} из сессии, но сессия {poll_info.get('associated_quiz_session_chat_id')} не найдена.")


async def rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_str = str(update.effective_chat.id)
    if chat_id_str not in user_scores or not user_scores[chat_id_str]:
        await update.message.reply_text("Рейтинг для этого чата пока пуст.")
        return

    sorted_users = sorted(
        [item for item in user_scores[chat_id_str].items() if isinstance(item[1], dict)], # Фильтруем некорректные записи
        key=lambda item: (-item[1].get("score", 0), item[1].get("name", "").lower())
    )

    rating_text = "🏆 **Общий рейтинг игроков в этом чате:** 🏆\n\n"
    if not sorted_users:
        rating_text += "Пока никто не набрал очков или данные игроков некорректны."
    else:
        for rank, (user_id, data) in enumerate(sorted_users, 1):
            user_name = data.get("name", f"User_{user_id}")
            score = data.get("score", 0)
            user_mention_md = get_user_mention(int(user_id), user_name)
            rating_text += f"{rank}. {user_mention_md} - {score} очков\n"
    
    await update.message.reply_text(rating_text, parse_mode='Markdown')

# --- Точка входа ---
def main():
    if not TOKEN:
        logger.critical("Токен бота не найден. Установите переменную окружения BOT_TOKEN.")
        return

    logger.info("Бот запускается...")

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("categories", categories_command))
    application.add_handler(CommandHandler("quiz_category", quiz_category))
    application.add_handler(CommandHandler("quiz10", start_quiz10))
    application.add_handler(CommandHandler("stopquiz10", stop_quiz10))
    application.add_handler(CommandHandler("rating", rating))
    application.add_handler(PollAnswerHandler(handle_poll_answer))

    logger.info("Обработчики добавлены.")
    try:
        application.run_polling()
    except Exception as e:
        logger.critical(f"Критическая ошибка в работе polling: {e}", exc_info=True)
    finally:
        logger.info("Бот остановлен.")


if __name__ == '__main__':
    main()
