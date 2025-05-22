import logging
import os
import json
import copy
from datetime import timedelta # Для JobQueue
from telegram import Update, Poll
from telegram.ext import ApplicationBuilder, CommandHandler, PollAnswerHandler, ContextTypes, JobQueue
from dotenv import load_dotenv
import random
from typing import List, Tuple, Dict, Any, Optional

# --- Константы ---
QUESTIONS_FILE = 'questions.json'
USERS_FILE = 'users.json'
DEFAULT_POLL_OPEN_PERIOD = 30  # Секунд для каждого вопроса (кроме последнего в сессии)
FINAL_ANSWER_WINDOW_SECONDS = 60 # Время на ответ на ПОСЛЕДНИЙ вопрос в /quiz10. Уменьшил для теста.
NUMBER_OF_QUESTIONS_IN_SESSION = 10 # Количество вопросов в /quiz10

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

quiz_data: Dict[str, List[Dict[str, Any]]] = {}
user_scores: Dict[str, Dict[str, Any]] = {} # Глобальные очки {chat_id: {user_id: {name:..., score:..., answered_polls: set()}}}
current_poll: Dict[str, Dict[str, Any]] = {} # Активные опросы {poll_id: {details}}
current_quiz_session: Dict[str, Dict[str, Any]] = {} # Активные сессии {chat_id: {details}}

# --- Вспомогательные функции для сериализации/десериализации ---
def convert_sets_to_lists_recursively(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: convert_sets_to_lists_recursively(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_sets_to_lists_recursively(elem) for elem in obj]
    elif isinstance(obj, set):
        return list(obj)
    return obj

def convert_user_scores_lists_to_sets(scores_data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(scores_data, dict):
        return scores_data
    for chat_id, users_in_chat in scores_data.items():
        if isinstance(users_in_chat, dict):
            for user_id, user_data_val in users_in_chat.items():
                if isinstance(user_data_val, dict) and 'answered_polls' in user_data_val and isinstance(user_data_val['answered_polls'], list):
                    user_data_val['answered_polls'] = set(user_data_val['answered_polls'])
    return scores_data

# --- Функции загрузки и сохранения данных ---
def load_questions():
    global quiz_data
    processed_questions_count = 0
    valid_categories_count = 0
    try:
        with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)

        if not isinstance(raw_data, dict):
            logger.error(f"Ошибка: {QUESTIONS_FILE} должен содержать JSON объект (словарь категорий).")
            return

        temp_quiz_data = {}
        for category, questions_list in raw_data.items():
            if not isinstance(questions_list, list):
                logger.warning(f"Категория '{category}' в {QUESTIONS_FILE} не содержит список вопросов. Пропущена.")
                continue

            processed_category_questions = []
            for i, q_data in enumerate(questions_list):
                if not isinstance(q_data, dict):
                    logger.warning(f"Вопрос {i+1} в категории '{category}' не является словарем. Пропущен.")
                    continue
                if not all(k in q_data for k in ["question", "options", "correct"]):
                    logger.warning(f"Вопрос {i+1} в категории '{category}' имеет неполные данные (отсутствует question, options или correct). Пропущен.")
                    continue
                if not isinstance(q_data["options"], list) or len(q_data["options"]) < 2:
                    logger.warning(f"Вопрос {i+1} в категории '{category}' имеет некорректные 'options'. Должен быть список минимум из 2 элементов. Пропущен.")
                    continue
                if q_data["correct"] not in q_data["options"]:
                    logger.warning(f"Вопрос {i+1} в категории '{category}': правильный ответ '{q_data['correct']}' отсутствует в списке вариантов. Пропущен.")
                    continue

                correct_option_index = q_data["options"].index(q_data["correct"])
                processed_category_questions.append({
                    "question": q_data["question"],
                    "options": q_data["options"],
                    "correct_option_index": correct_option_index,
                    "original_category": category # Сохраняем исходную категорию
                })
                processed_questions_count += 1
            if processed_category_questions:
                temp_quiz_data[category] = processed_category_questions
                valid_categories_count +=1
        quiz_data = temp_quiz_data
        logger.info(f"Успешно загружено и обработано {processed_questions_count} вопросов из {valid_categories_count} категорий.")

    except FileNotFoundError:
        logger.error(f"Файл вопросов {QUESTIONS_FILE} не найден.")
    except json.JSONDecodeError:
        logger.error(f"Ошибка декодирования JSON в файле вопросов {QUESTIONS_FILE}.")
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при загрузке вопросов: {e}")


def save_user_data():
    global user_scores
    # Создаем глубокую копию, чтобы не изменять оригинальный user_scores во время сериализации
    data_to_save = copy.deepcopy(user_scores)
    # Рекурсивно преобразуем все set в list перед сохранением
    data_to_save_serializable = convert_sets_to_lists_recursively(data_to_save)
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save_serializable, f, ensure_ascii=False, indent=4)
        # logger.info("Данные пользователей сохранены.") # Можно закомментировать для уменьшения логов
    except TypeError as e:
        logger.error(f"Ошибка при сохранении пользовательских данных (TypeError): {e}. Данные: {data_to_save_serializable}")
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при сохранении пользовательских данных: {e}")


def load_user_data():
    global user_scores
    try:
        if os.path.exists(USERS_FILE) and os.path.getsize(USERS_FILE) > 0:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
                user_scores = convert_user_scores_lists_to_sets(loaded_data)
                logger.info("Данные пользователей загружены.")
        else:
            logger.info(f"{USERS_FILE} не найден или пуст. Начинаем с пустыми данными пользователей.")
            user_scores = {}
    except json.JSONDecodeError:
        logger.error(f"Ошибка декодирования JSON в файле пользователей {USERS_FILE}. Создается пустой файл или используются пустые данные.")
        user_scores = {}
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при загрузке данных пользователей: {e}")
        user_scores = {}


# --- Вспомогательные функции для викторины ---
def get_random_questions(category: str, count: int = 1) -> List[Dict[str, Any]]:
    if category not in quiz_data or not isinstance(quiz_data[category], list):
        return []
    
    available_questions = quiz_data[category]
    if not available_questions:
        return []
        
    num_to_select = min(count, len(available_questions))
    selected_questions = random.sample(available_questions, num_to_select)
    
    # Добавляем 'original_category' если его нет (хотя load_questions должен это делать)
    return [
        {**q, 'original_category': category} if 'original_category' not in q else q
        for q in selected_questions
    ]

def get_random_questions_from_all(count: int) -> List[Dict[str, Any]]:
    all_questions = []
    for category_name, questions_list in quiz_data.items():
        if isinstance(questions_list, list):
            for q in questions_list:
                 # Убедимся, что original_category есть, load_questions должен это обеспечивать
                all_questions.append(q.copy()) # Копируем, чтобы избежать модификации оригинала

    if not all_questions:
        return []
    
    num_to_select = min(count, len(all_questions))
    return random.sample(all_questions, num_to_select)

# --- Обработчики команд ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id_str = str(update.effective_chat.id)
    user_id_str = str(user.id)

    if chat_id_str not in user_scores:
        user_scores[chat_id_str] = {}
    if user_id_str not in user_scores[chat_id_str]:
        user_scores[chat_id_str][user_id_str] = {"name": user.full_name, "score": 0, "answered_polls": set()}
        save_user_data()

    await update.message.reply_text(
        f"Привет, {user.first_name}! Я бот для викторин.\n"
        "Доступные команды:\n"
        "/quiz [категория] - начать викторину из одного вопроса по категории.\n"
        "/quiz10 [категория] - начать викторину из 10 вопросов по категории (категория опциональна, если не указана - вопросы из всех категорий).\n"
        "/categories - показать список доступных категорий.\n"
        "/top - показать топ игроков в этом чате.\n"
        "/stopquiz - остановить текущую активную сессию викторины из 10 вопросов в этом чате (только для администраторов или того, кто запустил)."
    )

async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not quiz_data:
        await update.message.reply_text("Извините, список категорий пуст или еще не загружен.")
        return
    
    category_names = [f"- {name} ({len(questions)} в.)" for name, questions in quiz_data.items() if isinstance(questions, list) and questions]
    if category_names:
        await update.message.reply_text("Доступные категории:\n" + "\n".join(category_names))
    else:
        await update.message.reply_text("Нет доступных категорий с вопросами.")


async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_id_str = str(chat_id)

    if chat_id_str in current_quiz_session and current_quiz_session[chat_id_str].get("current_index", -1) < NUMBER_OF_QUESTIONS_IN_SESSION :
        await update.message.reply_text("В этом чате уже идет викторина из 10 вопросов. Дождитесь ее окончания или остановите командой /stopquiz.")
        return

    category_name = " ".join(context.args) if context.args else None

    if not category_name:
        categories = list(quiz_data.keys())
        if not categories:
            await update.message.reply_text("Нет доступных категорий для выбора случайного вопроса.")
            return
        category_name = random.choice(categories)
        question_details_list = get_random_questions(category_name, 1)
        await update.message.reply_text(f"Категория не указана. Выбрана случайная категория: {category_name}")
    else:
        question_details_list = get_random_questions(category_name, 1)

    if not question_details_list:
        await update.message.reply_text(f"Не удалось найти вопросы в категории '{category_name}' или такой категории нет.")
        return
    
    question_details = question_details_list[0]

    try:
        sent_poll = await context.bot.send_poll(
            chat_id=chat_id,
            question=f"Категория: {question_details.get('original_category', category_name)}\n{question_details['question']}",
            options=question_details['options'],
            type=Poll.QUIZ,
            correct_option_id=question_details['correct_option_index'],
            open_period=DEFAULT_POLL_OPEN_PERIOD,
            is_anonymous=False
        )
        current_poll[sent_poll.poll.id] = {
            "chat_id": str(chat_id),
            "message_id": sent_poll.message_id,
            "correct_index": question_details['correct_option_index'],
            "quiz_session": False, # Одиночный вопрос
            "question_details": question_details,
            "associated_quiz_session_chat_id": None
        }
    except Exception as e:
        logger.error(f"Ошибка при отправке одиночного опроса: {e}")
        await update.message.reply_text("Произошла ошибка при создании вопроса. Попробуйте позже.")


async def start_quiz10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_id_str = str(chat_id)

    if chat_id_str in current_quiz_session and current_quiz_session[chat_id_str].get("current_index", -1) < NUMBER_OF_QUESTIONS_IN_SESSION:
        await update.message.reply_text("В этом чате уже идет викторина. Дождитесь ее окончания или остановите командой /stopquiz.")
        return

    category_name_arg = " ".join(context.args) if context.args else None
    questions_for_session = []

    if category_name_arg:
        questions_for_session = get_random_questions(category_name_arg, NUMBER_OF_QUESTIONS_IN_SESSION)
        if len(questions_for_session) < NUMBER_OF_QUESTIONS_IN_SESSION:
            await update.message.reply_text(f"В категории '{category_name_arg}' недостаточно вопросов для полной викторины из {NUMBER_OF_QUESTIONS_IN_SESSION}. Найдено: {len(questions_for_session)}.")
            if not questions_for_session: return # Если совсем нет вопросов
        intro_message_text = f"Начинаем викторину из {len(questions_for_session)} вопросов по категории: {category_name_arg}!"
    else:
        questions_for_session = get_random_questions_from_all(NUMBER_OF_QUESTIONS_IN_SESSION)
        if len(questions_for_session) < NUMBER_OF_QUESTIONS_IN_SESSION:
            await update.message.reply_text(f"Недостаточно вопросов во всех категориях для полной викторины из {NUMBER_OF_QUESTIONS_IN_SESSION}. Найдено: {len(questions_for_session)}.")
            if not questions_for_session: return
        intro_message_text = f"Начинаем викторину из {len(questions_for_session)} вопросов из случайных категорий!"

    if not questions_for_session:
        # Это сообщение дублируется, но оставим на всякий случай
        await update.message.reply_text("Не удалось подобрать вопросы для викторины.")
        return
    
    actual_num_questions = len(questions_for_session)

    intro_message = await update.message.reply_text(intro_message_text + f"\nВсего вопросов: {actual_num_questions}. Приготовьтесь!")

    current_quiz_session[chat_id_str] = {
        "questions": questions_for_session,
        "session_scores": {}, # {user_id_str: {"name": "...", "score": 0}}
        "current_index": 0,
        "message_id_intro": intro_message.message_id,
        "starter_user_id": str(update.effective_user.id), # Кто запустил
        "current_poll_id": None,
        "next_question_job": None,
        "actual_num_questions": actual_num_questions # Сохраняем фактическое количество вопросов
    }
    logger.info(f"Сессия викторины на {actual_num_questions} вопросов запущена в чате {chat_id_str} пользователем {update.effective_user.id}.")
    
    # Запускаем первый вопрос сессии
    await send_next_question_in_session(context, chat_id_str)


async def send_next_question_in_session(context: ContextTypes.DEFAULT_TYPE, chat_id_str: str, from_job: bool = False):
    session = current_quiz_session.get(chat_id_str)
    if not session:
        logger.warning(f"send_next_question_in_session вызван для несуществующей сессии в чате {chat_id_str}")
        return

    # Если предыдущая задача по отправке следующего вопроса еще существует, отменяем ее
    if session.get("next_question_job"):
        try:
            session["next_question_job"].schedule_removal()
            logger.debug(f"Предыдущая задача next_question_job для чата {chat_id_str} отменена.")
        except Exception as e:
            logger.error(f"Ошибка при отмене next_question_job для чата {chat_id_str}: {e}")
        session["next_question_job"] = None


    current_q_index = session["current_index"]
    actual_num_questions = session["actual_num_questions"]

    if current_q_index >= actual_num_questions:
        logger.info(f"Попытка отправить вопрос {current_q_index + 1}, но в сессии всего {actual_num_questions} вопросов. Завершаем сессию для чата {chat_id_str}.")
        await show_quiz_session_results(context, chat_id_str)
        return

    question_details = session["questions"][current_q_index]
    
    is_last_question = (current_q_index == actual_num_questions - 1)
    open_period_for_this_q = FINAL_ANSWER_WINDOW_SECONDS if is_last_question else DEFAULT_POLL_OPEN_PERIOD

    try:
        question_text = f"Вопрос {current_q_index + 1}/{actual_num_questions}\n"
        if question_details.get("original_category"):
             question_text += f"Категория: {question_details['original_category']}\n"
        question_text += question_details['question']

        sent_poll = await context.bot.send_poll(
            chat_id=chat_id_str,
            question=question_text,
            options=question_details['options'],
            type=Poll.QUIZ,
            correct_option_id=question_details['correct_option_index'],
            open_period=open_period_for_this_q,
            is_anonymous=False
        )
        
        session["current_poll_id"] = sent_poll.poll.id
        session["current_index"] += 1 # Сразу увеличиваем индекс для следующего вызова

        current_poll[sent_poll.poll.id] = {
            "chat_id": chat_id_str,
            "message_id": sent_poll.message_id,
            "correct_index": question_details['correct_option_index'],
            "quiz_session": True,
            "question_details": question_details,
            "associated_quiz_session_chat_id": chat_id_str,
            "is_last_question": is_last_question
        }
        logger.info(f"Отправлен вопрос {current_q_index + 1}/{actual_num_questions} сессии в чате {chat_id_str}. Poll ID: {sent_poll.poll.id}")

        # Планируем задачу для обработки окончания этого вопроса
        job_delay = open_period_for_this_q + 2 # Даем 2 секунды запаса Telegram на закрытие опроса
        
        # Уникальное имя для задачи, чтобы избежать дублирования при быстром рестарте/вызовах
        job_name = f"handle_poll_end_{chat_id_str}_{sent_poll.poll.id}"

        # Удаляем старую задачу с таким же именем, если она есть (на всякий случай)
        existing_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in existing_jobs:
            job.schedule_removal()
            logger.debug(f"Удалена существующая задача {job_name} перед созданием новой.")

        next_job = context.job_queue.run_once(
            handle_current_poll_end_and_proceed,
            when=timedelta(seconds=job_delay),
            data={"chat_id": chat_id_str, "poll_id": sent_poll.poll.id, "expected_q_index": current_q_index}, # передаем индекс отправленного вопроса
            name=job_name
        )
        session["next_question_job"] = next_job # Сохраняем ссылку на новую задачу

    except Exception as e:
        logger.error(f"Ошибка при отправке вопроса сессии в чате {chat_id_str}: {e}")
        # Попытаться завершить сессию, если не удалось отправить вопрос
        await show_quiz_session_results(context, chat_id_str, error_occurred=True)


async def handle_current_poll_end_and_proceed(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id_str = job_data["chat_id"]
    poll_id = job_data["poll_id"]
    # expected_q_index = job_data["expected_q_index"] # Индекс вопроса, для которого эта задача была создана

    logger.info(f"Job 'handle_current_poll_end_and_proceed' сработал для чата {chat_id_str}, poll_id {poll_id}.")

    session = current_quiz_session.get(chat_id_str)
    if not session:
        logger.warning(f"Сессия для чата {chat_id_str} не найдена при обработке окончания опроса {poll_id}.")
        if poll_id in current_poll: del current_poll[poll_id] # Очистка
        return

    # Проверка, что это работа для актуального опроса сессии.
    # Может быть ситуация, когда сессия была остановлена, а задача еще висит.
    if session.get("current_poll_id") != poll_id and not session.get("questions")[job_data.get("expected_q_index",-1)]: # Доп. проверка
         logger.info(f"Задача для poll_id {poll_id} в чате {chat_id_str} больше не актуальна (текущий poll_id сессии: {session.get('current_poll_id')}). Пропускаем.")
         # Не удаляем сессию здесь, т.к. могла начаться новая обработка
         return


    # Удаляем информацию о текущем опросе из current_poll, т.к. он завершен
    if poll_id in current_poll:
        is_last_question = current_poll[poll_id].get("is_last_question", False)
        del current_poll[poll_id]
        logger.debug(f"Poll {poll_id} удален из current_poll для чата {chat_id_str}.")
    else: # Если poll_id уже нет, возможно, сессия была завершена досрочно
        logger.warning(f"Poll {poll_id} не найден в current_poll при обработке handle_current_poll_end_and_proceed для чата {chat_id_str}")
        is_last_question = (session["current_index"] >= session["actual_num_questions"])


    if session["current_index"] < session["actual_num_questions"]:
        logger.info(f"Время для вопроса (poll {poll_id}) в чате {chat_id_str} истекло. Отправляем следующий вопрос.")
        await send_next_question_in_session(context, chat_id_str, from_job=True)
    else: # Это был последний вопрос
        logger.info(f"Время для последнего вопроса (poll {poll_id}) в чате {chat_id_str} истекло. Показываем результаты.")
        await show_quiz_session_results(context, chat_id_str)


async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = answer.poll_id
    user = answer.user

    user_id_str = str(user.id)
    poll_info = current_poll.get(poll_id)

    if not poll_info:
        # logger.info(f"Получен ответ на неизвестный или уже закрытый опрос {poll_id}")
        return

    chat_id_str = poll_info["chat_id"]

    # Инициализация пользователя в глобальной статистике, если его нет
    if chat_id_str not in user_scores:
        user_scores[chat_id_str] = {}
    if user_id_str not in user_scores[chat_id_str]:
        user_scores[chat_id_str][user_id_str] = {"name": user.full_name, "score": 0, "answered_polls": set()}
    
    # Предотвращение повторного начисления очков за один и тот же опрос
    if poll_id in user_scores[chat_id_str][user_id_str]["answered_polls"]:
        logger.debug(f"Пользователь {user_id_str} уже отвечал на опрос {poll_id}. Ответ не засчитан повторно.")
        return
    
    user_scores[chat_id_str][user_id_str]["answered_polls"].add(poll_id)
    
    is_correct = (len(answer.option_ids) == 1 and answer.option_ids[0] == poll_info["correct_index"])

    if is_correct:
        user_scores[chat_id_str][user_id_str]["score"] += 1
        logger.info(f"Пользователь {user.full_name} ({user_id_str}) ответил правильно на опрос {poll_id} в чате {chat_id_str}. Глобальный счет: {user_scores[chat_id_str][user_id_str]['score']}")
    else:
        logger.info(f"Пользователь {user.full_name} ({user_id_str}) ответил неправильно на опрос {poll_id} в чате {chat_id_str}.")

    save_user_data() # Сохраняем глобальные очки

    # Если это опрос из сессии /quiz10
    if poll_info["quiz_session"]:
        session_chat_id = poll_info["associated_quiz_session_chat_id"]
        if session_chat_id and session_chat_id in current_quiz_session:
            session = current_quiz_session[session_chat_id]
            
            # Инициализация пользователя в очках сессии, если его нет
            if user_id_str not in session["session_scores"]:
                session["session_scores"][user_id_str] = {"name": user.full_name, "score": 0}
            
            if is_correct:
                session["session_scores"][user_id_str]["score"] += 1
                logger.info(f"Пользователь {user.full_name} ({user_id_str}) +1 балл в текущей сессии {session_chat_id}. Счет сессии: {session['session_scores'][user_id_str]['score']}")
            # Не отправляем следующий вопрос отсюда. Это делает Job.

async def show_quiz_session_results(context: ContextTypes.DEFAULT_TYPE, chat_id_str: str, error_occurred: bool = False):
    session = current_quiz_session.get(chat_id_str)
    if not session:
        logger.warning(f"Попытка показать результаты для несуществующей сессии в чате {chat_id_str}")
        return

    # Отменяем задачу на следующий вопрос, если она есть
    if session.get("next_question_job"):
        try:
            session["next_question_job"].schedule_removal()
            logger.info(f"Задача next_question_job для чата {chat_id_str} отменена при показе результатов.")
        except Exception as e:
            logger.error(f"Ошибка при отмене next_question_job во время show_quiz_session_results для чата {chat_id_str}: {e}")
    
    results_text = "Викторина завершена!\n\nРезультаты этой сессии:\n"
    if error_occurred:
        results_text = "Викторина была прервана из-за ошибки.\n\nПромежуточные результаты:\n"

    if not session["session_scores"]:
        results_text += "Никто не набрал очков в этой сессии."
    else:
        sorted_session_scores = sorted(
            session["session_scores"].items(), 
            key=lambda item: item[1]["score"], 
            reverse=True
        )
        for user_id, data in sorted_session_scores:
            results_text += f"{data['name']}: {data['score']} из {session.get('actual_num_questions', NUMBER_OF_QUESTIONS_IN_SESSION)}\n"
            # Обновляем глобальную статистику (или подтверждаем, если она уже обновлялась в handle_poll_answer)
            # Это может быть избыточным, если handle_poll_answer уже корректно обновляет глобальные очки,
            # но тут мы синхронизируем сессионные очки с глобальными на всякий случай.
            # Однако, handle_poll_answer уже пишет в user_scores, так что этот блок не обязателен.
            # Если логика в handle_poll_answer безупречна, это можно убрать.
            # Для безопасности оставим, но учтем, что handle_poll_answer должен быть основным местом обновления global_scores.

    try:
        await context.bot.send_message(chat_id=chat_id_str, text=results_text)
        logger.info(f"Результаты сессии отправлены в чат {chat_id_str}")
    except Exception as e:
        logger.error(f"Ошибка при отправке результатов сессии в чат {chat_id_str}: {e}")

    # Очистка сессии
    if chat_id_str in current_quiz_session:
        # Удаляем poll_id завершенной сессии из current_poll, если он там остался
        current_poll_id_of_session = current_quiz_session[chat_id_str].get("current_poll_id")
        if current_poll_id_of_session and current_poll_id_of_session in current_poll:
            del current_poll[current_poll_id_of_session]
            logger.debug(f"Poll {current_poll_id_of_session} завершенной сессии удален из current_poll для чата {chat_id_str}.")

        del current_quiz_session[chat_id_str]
        logger.info(f"Сессия для чата {chat_id_str} очищена.")
    
    save_user_data() # Сохраняем данные после возможного обновления глобальных очков


async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_str = str(update.effective_chat.id)
    if chat_id_str not in user_scores or not user_scores[chat_id_str]:
        await update.message.reply_text("В этом чате еще нет статистики игроков.")
        return

    chat_user_scores = user_scores[chat_id_str]
    
    # Фильтруем пользователей без имени или с нулевым счетом, если нужно
    # valid_scores = {uid: data for uid, data in chat_user_scores.items() if data.get("name") and data.get("score", 0) > 0}
    # if not valid_scores:
    #     await update.message.reply_text("Пока нет игроков с очками в этом чате.")
    #     return
    
    # Сортировка пользователей по очкам
    sorted_scores = sorted(chat_user_scores.items(), key=lambda item: item[1].get("score", 0), reverse=True)
    
    top_text = "Топ игроков в этом чате:\n"
    for i, (user_id, data) in enumerate(sorted_scores[:10]): # Показываем топ-10
        user_name = data.get("name", f"User {user_id}")
        score = data.get("score", 0)
        top_text += f"{i+1}. {user_name} - {score} очков\n"
        
    await update.message.reply_text(top_text)

async def stop_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_str = str(update.effective_chat.id)
    user_id_str = str(update.effective_user.id)

    session = current_quiz_session.get(chat_id_str)
    if not session:
        await update.message.reply_text("В этом чате нет активной викторины для остановки.")
        return

    # Проверка прав на остановку (администратор чата или запустивший викторину)
    is_admin = False
    if update.effective_chat.type != "private":
        try:
            chat_member = await context.bot.get_chat_member(chat_id_str, user_id_str)
            if chat_member.status in [chat_member.ADMINISTRATOR, chat_member.OWNER]:
                is_admin = True
        except Exception as e:
            logger.warning(f"Не удалось проверить статус администратора для {user_id_str} в чате {chat_id_str}: {e}")
    
    is_starter = (user_id_str == session.get("starter_user_id"))

    if not is_admin and not is_starter:
        await update.message.reply_text("Только администратор чата или тот, кто запустил викторину, может ее остановить.")
        return

    logger.info(f"Команда /stopquiz вызвана пользователем {user_id_str} в чате {chat_id_str}. Останавливаем сессию.")
    
    # Останавливаем текущий опрос сессии, если он есть
    current_poll_id_of_session = session.get("current_poll_id")
    if current_poll_id_of_session:
        try:
            await context.bot.stop_poll(chat_id_str, current_poll[current_poll_id_of_session]["message_id"])
            logger.info(f"Опрос {current_poll_id_of_session} сессии в чате {chat_id_str} остановлен.")
        except Exception as e:
            logger.error(f"Ошибка при остановке опроса {current_poll_id_of_session} в чате {chat_id_str}: {e}")
    
    # Показываем промежуточные результаты и очищаем сессию
    await show_quiz_session_results(context, chat_id_str, error_occurred=True) # error_occurred=True для сообщения о прерывании
    await update.message.reply_text("Викторина остановлена.")


def main():
    if not TOKEN:
        logger.critical("Токен бота не найден. Убедитесь, что BOT_TOKEN установлен в .env или переменных окружения.")
        return

    load_questions()
    load_user_data()

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("quiz10", start_quiz10))
    application.add_handler(CommandHandler("categories", categories_command))
    application.add_handler(CommandHandler("top", top_command))
    application.add_handler(CommandHandler("stopquiz", stop_quiz_command))
    application.add_handler(PollAnswerHandler(handle_poll_answer))
    
    # error_handler для логирования непредвиденных ошибок PTB
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error(msg="Exception while handling an update:", exc_info=context.error)

    application.add_error_handler(error_handler)

    logger.info("Бот запускается...")
    application.run_polling()
    logger.info("Бот остановлен.")

if __name__ == '__main__':
    main()
