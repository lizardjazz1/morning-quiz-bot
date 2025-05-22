import logging
import os
import json
import copy
from datetime import timedelta
from telegram import Update, Poll
from telegram.ext import ApplicationBuilder, CommandHandler, PollAnswerHandler, ContextTypes, JobQueue
from dotenv import load_dotenv
import random
from typing import List, Tuple, Dict, Any, Optional

# --- Константы ---
QUESTIONS_FILE = 'questions.json'
USERS_FILE = 'users.json'
DEFAULT_POLL_OPEN_PERIOD = 25  # Секунд на ответ (уменьшено для динамики)
FINAL_ANSWER_WINDOW_SECONDS = 45 # Время на последний вопрос (уменьшено)
NUMBER_OF_QUESTIONS_IN_SESSION = 10
JOB_GRACE_PERIOD = 1 # Секунды запаса для задач JobQueue после закрытия опроса

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

quiz_data: Dict[str, List[Dict[str, Any]]] = {}
user_scores: Dict[str, Dict[str, Any]] = {}  # Исправлено
current_poll: Dict[str, Dict[str, Any]] = {} # Исправлено
current_quiz_session: Dict[str, Dict[str, Any]] = {} # Исправлено

# --- Вспомогательные функции для сериализации/десериализации (без изменений) ---
def convert_sets_to_lists_recursively(obj: Any) -> Any:
    if isinstance(obj, dict): return {k: convert_sets_to_lists_recursively(v) for k, v in obj.items()}
    if isinstance(obj, list): return [convert_sets_to_lists_recursively(elem) for elem in obj]
    if isinstance(obj, set): return list(obj)
    return obj

def convert_user_scores_lists_to_sets(scores_data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(scores_data, dict): return scores_data
    for chat_id, users_in_chat in scores_data.items():
        if isinstance(users_in_chat, dict):
            for user_id, user_data_val in users_in_chat.items():
                if isinstance(user_data_val, dict) and 'answered_polls' in user_data_val and isinstance(user_data_val['answered_polls'], list):
                    user_data_val['answered_polls'] = set(user_data_val['answered_polls'])
    return scores_data

# --- Функции загрузки и сохранения данных (небольшие улучшения в логах) ---
def load_questions():
    global quiz_data
    processed_questions_count, valid_categories_count = 0, 0
    try:
        with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f: raw_data = json.load(f)
        if not isinstance(raw_data, dict):
            logger.error(f"{QUESTIONS_FILE} должен содержать JSON объект."); return
        temp_quiz_data = {}
        for category, questions_list in raw_data.items():
            if not isinstance(questions_list, list):
                logger.warning(f"Категория '{category}' не список. Пропущена."); continue
            processed_category_questions = []
            for i, q_data in enumerate(questions_list):
                if not (isinstance(q_data, dict) and all(k in q_data for k in ["question", "options", "correct"]) and
                        isinstance(q_data["options"], list) and len(q_data["options"]) >= 2 and
                        q_data["correct"] in q_data["options"])):
                    logger.warning(f"Вопрос {i+1} в '{category}' некорректен. Пропущен. Данные: {q_data}"); continue
                correct_option_index = q_data["options"].index(q_data["correct"])
                processed_category_questions.append({"question": q_data["question"], "options": q_data["options"],
                                                     "correct_option_index": correct_option_index, "original_category": category})
                processed_questions_count += 1
            if processed_category_questions: temp_quiz_data[category] = processed_category_questions; valid_categories_count +=1
        quiz_data = temp_quiz_data
        logger.info(f"Загружено {processed_questions_count} вопросов из {valid_categories_count} категорий.")
    except FileNotFoundError: logger.error(f"{QUESTIONS_FILE} не найден.")
    except json.JSONDecodeError: logger.error(f"Ошибка декодирования JSON в {QUESTIONS_FILE}.")
    except Exception as e: logger.error(f"Ошибка загрузки вопросов: {e}", exc_info=True)

def save_user_data():
    global user_scores
    data_to_save = copy.deepcopy(user_scores)
    data_to_save_serializable = convert_sets_to_lists_recursively(data_to_save)
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f: json.dump(data_to_save_serializable, f, ensure_ascii=False, indent=4)
    except Exception as e: logger.error(f"Ошибка сохранения данных: {e}", exc_info=True)

def load_user_data():
    global user_scores
    try:
        if os.path.exists(USERS_FILE) and os.path.getsize(USERS_FILE) > 0:
            with open(USERS_FILE, 'r', encoding='utf-8') as f: loaded_data = json.load(f)
            user_scores = convert_user_scores_lists_to_sets(loaded_data); logger.info("Данные пользователей загружены.")
        else: logger.info(f"{USERS_FILE} не найден/пуст. Старт с пустыми данными."); user_scores = {}
    except json.JSONDecodeError: logger.error(f"Ошибка декодирования {USERS_FILE}. Использование пустых данных."); user_scores = {}
    except Exception as e: logger.error(f"Ошибка загрузки данных: {e}", exc_info=True); user_scores = {}

# --- Вспомогательные функции для викторины (без изменений) ---
def get_random_questions(category: str, count: int = 1) -> List[Dict[str, Any]]:
    cat_q_list = quiz_data.get(category);
    if not isinstance(cat_q_list, list) or not cat_q_list: return []
    return [q.copy() for q in random.sample(cat_q_list, min(count, len(cat_q_list)))]

def get_random_questions_from_all(count: int) -> List[Dict[str, Any]]:
    all_q = [q.copy() for q_list in quiz_data.values() if isinstance(q_list, list) for q in q_list]
    if not all_q: return []
    return random.sample(all_q, min(count, len(all_q)))

# --- Обработчики команд (start, categories, quiz - без существенных изменений) ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, chat_id_str = update.effective_user, str(update.effective_chat.id) # type: ignore
    user_id_str = str(user.id) # type: ignore
    user_scores.setdefault(chat_id_str, {}).setdefault(user_id_str, {"name": user.full_name, "score": 0, "answered_polls": set()}) # type: ignore
    user_scores[chat_id_str][user_id_str]["name"] = user.full_name # type: ignore
    if not isinstance(user_scores[chat_id_str][user_id_str].get("answered_polls"), set): # type: ignore
        user_scores[chat_id_str][user_id_str]["answered_polls"] = set(user_scores[chat_id_str][user_id_str].get("answered_polls", [])) # type: ignore
    save_user_data()
    await update.message.reply_text( # type: ignore
        f"Привет, {user.first_name}! Команды:\n"
        "/quiz [категория] - 1 вопрос.\n/quiz10 [категория] - 10 вопросов.\n"
        "/categories - список категорий.\n/top - топ игроков.\n/stopquiz - остановить /quiz10."
    )

async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not quiz_data: await update.message.reply_text("Категории не загружены."); return # type: ignore
    cat_names = [f"- {name} ({len(q_list)} в.)" for name, q_list in quiz_data.items() if isinstance(q_list, list) and q_list]
    await update.message.reply_text("Доступные категории:\n" + "\n".join(cat_names) if cat_names else "Нет категорий.") # type: ignore

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, chat_id_str = update.effective_chat.id, str(update.effective_chat.id) # type: ignore
    if chat_id_str in current_quiz_session and current_quiz_session[chat_id_str].get("current_index", -1) < current_quiz_session[chat_id_str].get("actual_num_questions", NUMBER_OF_QUESTIONS_IN_SESSION) :
        await update.message.reply_text("Идет /quiz10. Дождитесь или /stopquiz."); return # type: ignore

    category_name = " ".join(context.args) if context.args else None # type: ignore
    q_details_list: List[Dict]
    msg_prefix = ""

    if not category_name:
        categories = [k for k, v in quiz_data.items() if isinstance(v, list) and v]
        if not categories: await update.message.reply_text("Нет категорий для случайного вопроса."); return # type: ignore
        category_name = random.choice(categories)
        q_details_list = get_random_questions(category_name, 1)
        msg_prefix = f"Случайная категория: {category_name}\n"
    else:
        q_details_list = get_random_questions(category_name, 1)

    if not q_details_list: await update.message.reply_text(f"Нет вопросов в '{category_name}'."); return # type: ignore
    q_details = q_details_list[0]

    try:
        q_text, opts, correct_idx, _ = prepare_poll_options(q_details)
        sent_poll = await context.bot.send_poll(chat_id=chat_id, question=f"{msg_prefix}{q_text}", options=opts,
            type=Poll.QUIZ, correct_option_id=correct_idx, open_period=DEFAULT_POLL_OPEN_PERIOD, is_anonymous=False)
        current_poll[sent_poll.poll.id] = {"chat_id": chat_id_str, "message_id": sent_poll.message_id, "correct_index": correct_idx,
            "quiz_session": False, "question_details": q_details, "associated_quiz_session_chat_id": None, "next_q_triggered_by_answer": False}
    except Exception as e: logger.error(f"Ошибка /quiz: {e}", exc_info=True); await update.message.reply_text("Ошибка создания вопроса.") # type: ignore

def prepare_poll_options(q_details: Dict[str, Any]) -> Tuple[str, List[str], int, List[str]]: # Без изменений
    q_text, opts_orig = q_details["question"], q_details["options"]
    correct_answer = opts_orig[q_details["correct_option_index"]]
    opts_shuffled = list(opts_orig); random.shuffle(opts_shuffled)
    try: new_correct_idx = opts_shuffled.index(correct_answer)
    except ValueError: new_correct_idx = q_details["correct_option_index"]; opts_shuffled = list(opts_orig) # Fallback
    return q_text, opts_shuffled, new_correct_idx, opts_orig

# --- Логика /quiz10 (существенные изменения) ---
async def start_quiz10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, chat_id_str = update.effective_chat.id, str(update.effective_chat.id) # type: ignore
    if chat_id_str in current_quiz_session and current_quiz_session[chat_id_str].get("current_index", -1) < current_quiz_session[chat_id_str].get("actual_num_questions", NUMBER_OF_QUESTIONS_IN_SESSION) :
        await update.message.reply_text("Идет /quiz10. Дождитесь или /stopquiz."); return # type: ignore

    category_name_arg = " ".join(context.args) if context.args else None # type: ignore
    questions: List[Dict[str, Any]]
    intro_text: str

    if category_name_arg:
        questions = get_random_questions(category_name_arg, NUMBER_OF_QUESTIONS_IN_SESSION)
        cat_desc = f"категории: {category_name_arg}"
    else:
        questions = get_random_questions_from_all(NUMBER_OF_QUESTIONS_IN_SESSION)
        cat_desc = "случайных категорий"

    actual_num_q = len(questions)
    if actual_num_q == 0: await update.message.reply_text(f"Не найдено вопросов для {cat_desc}."); return # type: ignore

    intro_text = f"Начинаем викторину из {actual_num_q} вопросов ({cat_desc})! Приготовьтесь!"
    if actual_num_q < NUMBER_OF_QUESTIONS_IN_SESSION: intro_text += f" (Меньше {NUMBER_OF_QUESTIONS_IN_SESSION}, т.к. не хватило)"

    intro_msg = await update.message.reply_text(intro_text) # type: ignore
    current_quiz_session[chat_id_str] = {
        "questions": questions, "session_scores": {}, "current_index": 0, "actual_num_questions": actual_num_q,
        "message_id_intro": intro_msg.message_id, "starter_user_id": str(update.effective_user.id), # type: ignore
        "current_poll_id": None, "next_question_job": None
    }
    logger.info(f"/quiz10 на {actual_num_q} в. запущена в {chat_id_str} пользователем {update.effective_user.id}.") # type: ignore
    await send_next_question_in_session(context, chat_id_str)


async def send_next_question_in_session(context: ContextTypes.DEFAULT_TYPE, chat_id_str: str):
    session = current_quiz_session.get(chat_id_str)
    if not session: logger.warning(f"send_next_q: Сессия {chat_id_str} удалена/не найдена."); return

    # Отменяем предыдущую задачу на переход, если она была (например, если вызвали досрочно из handle_poll_answer)
    if job := session.get("next_question_job"):
        try: job.schedule_removal(); logger.debug(f"Job {job.name} отменен для {chat_id_str}.")
        except Exception: pass # Может быть уже выполнена или удалена
        session["next_question_job"] = None

    current_q_idx, actual_num_q = session["current_index"], session["actual_num_questions"]
    if current_q_idx >= actual_num_q:
        logger.info(f"Все {actual_num_q} вопросов сессии {chat_id_str} отправлены. Завершение.");
        await show_quiz_session_results(context, chat_id_str); return

    q_details = session["questions"][current_q_idx]
    is_last = (current_q_idx == actual_num_q - 1)
    open_period = FINAL_ANSWER_WINDOW_SECONDS if is_last else DEFAULT_POLL_OPEN_PERIOD

    q_text_display = f"Вопрос {current_q_idx + 1}/{actual_num_q}\n"
    if cat := q_details.get("original_category"): q_text_display += f"Категория: {cat}\n"
    q_text_display += q_details['question']

    q_text_poll, opts_poll, correct_idx_poll, _ = prepare_poll_options(q_details) # q_text_poll не используется здесь, берем q_text_display

    try:
        sent_poll = await context.bot.send_poll(chat_id=chat_id_str, question=q_text_display, options=opts_poll,
            type=Poll.QUIZ, correct_option_id=correct_idx_poll, open_period=open_period, is_anonymous=False)

        session["current_poll_id"] = sent_poll.poll.id
        session["current_index"] += 1

        current_poll[sent_poll.poll.id] = {
            "chat_id": chat_id_str, "message_id": sent_poll.message_id, "correct_index": correct_idx_poll,
            "quiz_session": True, "question_details": q_details, "associated_quiz_session_chat_id": chat_id_str,
            "is_last_question": is_last, "next_q_triggered_by_answer": False # Новый флаг
        }
        logger.info(f"Отправлен вопрос {current_q_idx + 1}/{actual_num_q} сессии {chat_id_str}. Poll ID: {sent_poll.poll.id}")

        job_delay_secs = open_period + JOB_GRACE_PERIOD
        job_name = f"poll_end_{chat_id_str}_{sent_poll.poll.id}"

        # Удаляем старую задачу с таким именем, если она есть
        for old_job in context.job_queue.get_jobs_by_name(job_name): old_job.schedule_removal() # type: ignore

        next_job = context.job_queue.run_once(handle_current_poll_end, timedelta(seconds=job_delay_secs), # type: ignore
            data={"chat_id": chat_id_str, "ended_poll_id": sent_poll.poll.id, "ended_poll_q_idx": current_q_idx}, name=job_name)
        session["next_question_job"] = next_job
    except Exception as e:
        logger.error(f"Ошибка отправки вопроса сессии {chat_id_str}: {e}", exc_info=True)
        await show_quiz_session_results(context, chat_id_str, error_occurred=True)


async def handle_current_poll_end(context: ContextTypes.DEFAULT_TYPE): # Job callback
    job_data = context.job.data # type: ignore
    chat_id_str, ended_poll_id, ended_poll_q_idx = job_data["chat_id"], job_data["ended_poll_id"], job_data["ended_poll_q_idx"]
    logger.info(f"Job 'handle_current_poll_end' сработал для {chat_id_str}, poll {ended_poll_id} (вопрос {ended_poll_q_idx + 1}).")

    session = current_quiz_session.get(chat_id_str)
    if not session: logger.warning(f"Сессия {chat_id_str} не найдена при обработке job для poll {ended_poll_id}."); return

    # Очищаем информацию о завершенном опросе
    poll_info_ended = current_poll.pop(ended_poll_id, None)
    if poll_info_ended: logger.debug(f"Poll {ended_poll_id} удален из current_poll для {chat_id_str}.")
    else: logger.warning(f"Poll {ended_poll_id} не найден в current_poll при обработке job (возможно, уже удален).")

    # Если это была задача для последнего вопроса, или сессия уже должна была завершиться
    if ended_poll_q_idx >= session["actual_num_questions"] - 1:
        # Убедимся, что все вопросы действительно были "отправлены" (current_index дошел до конца)
        if session["current_index"] >= session["actual_num_questions"]:
            logger.info(f"Время для последнего вопроса (индекс {ended_poll_q_idx}) сессии {chat_id_str} истекло. Показ результатов.")
            await show_quiz_session_results(context, chat_id_str)
        else: # Сессия почему-то не дошла до конца, но job для последнего вопроса сработал. Странно.
            logger.warning(f"Job для последнего вопроса {ended_poll_q_idx} сработал, но current_index={session['current_index']}. Показываем результаты.")
            await show_quiz_session_results(context, chat_id_str)
        return

    # Если следующий вопрос ЕЩЕ НЕ БЫЛ отправлен (т.е. никто не ответил на ended_poll_id, или ответ не вызвал переход)
    # `current_index` указывает на индекс *следующего* вопроса. Если он равен `ended_poll_q_idx + 1`, значит,
    # `send_next_question_in_session` для вопроса `ended_poll_q_idx + 1` еще не вызывался.
    if session["current_index"] == ended_poll_q_idx + 1:
        logger.info(f"Тайм-аут для вопроса {ended_poll_q_idx + 1} в {chat_id_str} (poll {ended_poll_id}). Отправляем следующий.")
        await send_next_question_in_session(context, chat_id_str)
    else:
        logger.debug(f"Job для poll {ended_poll_id} в {chat_id_str} завершен. Следующий вопрос (индекс {session['current_index']}) уже был инициирован.")


async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer, user = update.poll_answer, update.poll_answer.user # type: ignore
    poll_id, uid_str, user_name = answer.poll_id, str(user.id), user.full_name # type: ignore

    poll_info = current_poll.get(poll_id)
    if not poll_info: return # Ответ на старый/неизвестный опрос

    chat_id_str = poll_info["chat_id"]
    # Обновление глобальной статистики
    user_scores.setdefault(chat_id_str, {}).setdefault(uid_str, {"name": user_name, "score": 0, "answered_polls": set()})
    user_global_data = user_scores[chat_id_str][uid_str]
    user_global_data["name"] = user_name
    if not isinstance(user_global_data.get("answered_polls"), set): user_global_data["answered_polls"] = set(user_global_data.get("answered_polls", []))

    is_correct = (len(answer.option_ids) == 1 and answer.option_ids[0] == poll_info["correct_index"]) # type: ignore

    # Только один раз начисляем очки за конкретный опрос в глобальный рейтинг
    if poll_id not in user_global_data["answered_polls"]:
        if is_correct: user_global_data["score"] += 1
        user_global_data["answered_polls"].add(poll_id)
        save_user_data() # Сохраняем после изменения глобальных очков
        logger.info(f"{user_name} ({uid_str}) ответил {'правильно' if is_correct else 'неправильно'} на poll {poll_id}. Глобальный счет: {user_global_data['score']}")

    # Если это опрос из сессии /quiz10
    if poll_info["quiz_session"]:
        session_chat_id = poll_info["associated_quiz_session_chat_id"]
        session = current_quiz_session.get(session_chat_id) # type: ignore
        if session:
            session_user_scores = session["session_scores"].setdefault(uid_str, {"name": user_name, "score": 0, "answered_this_session_polls": set()})
            session_user_scores["name"] = user_name # Обновить имя, если изменилось
            if not isinstance(session_user_scores.get("answered_this_session_polls"), set): session_user_scores["answered_this_session_polls"] = set(session_user_scores.get("answered_this_session_polls",[]))

            # Начисляем очки за сессию только один раз за данный poll_id
            if poll_id not in session_user_scores["answered_this_session_polls"]:
                if is_correct: session_user_scores["score"] += 1
                session_user_scores["answered_this_session_polls"].add(poll_id)
                logger.info(f"{user_name} ({uid_str}) +{1 if is_correct else 0} в сессии {session_chat_id}. Счет сессии: {session_user_scores['score']}")

            # Если это первый ответ на ДАННЫЙ опрос И это НЕ последний вопрос сессии
            if not poll_info.get("next_q_triggered_by_answer") and not poll_info.get("is_last_question"):
                poll_info["next_q_triggered_by_answer"] = True # Помечаем, что для этого poll_id переход уже инициирован
                logger.info(f"Первый ответ на poll {poll_id} в сессии {session_chat_id}. Отправляем следующий вопрос досрочно.")
                await send_next_question_in_session(context, session_chat_id) # type: ignore


async def show_quiz_session_results(context: ContextTypes.DEFAULT_TYPE, chat_id_str: str, error_occurred: bool = False):
    session = current_quiz_session.get(chat_id_str)
    if not session: logger.warning(f"show_results: Сессия {chat_id_str} не найдена."); return

    if job := session.get("next_question_job"):
        try: job.schedule_removal(); logger.info(f"Job {job.name} отменен для {chat_id_str} при показе результатов.")
        except Exception: pass # Может быть уже выполнен или удален

    num_q_in_session = session.get("actual_num_questions", NUMBER_OF_QUESTIONS_IN_SESSION)
    results_header = "🏁 Викторина завершена! 🏁\n\n" if not error_occurred else "Викторина прервана.\n\nПромежуточные результаты:\n"
    results_body = ""

    if not session["session_scores"]:
        results_body = "В этой сессии никто не участвовал или не набрал очков."
    else:
        # Сортируем по очкам в сессии (убывание), затем по имени (возрастание)
        sorted_session_participants = sorted(
            session["session_scores"].items(),
            key=lambda item: (-item[1]["score"], item[1]["name"].lower())
        )

        medals = ["🥇", "🥈", "🥉"]
        for rank, (user_id_str, data) in enumerate(sorted_session_participants):
            user_name = data["name"]
            session_score = data["score"]
            global_score = user_scores.get(chat_id_str, {}).get(user_id_str, {}).get("score", 0)

            rank_display = medals[rank] if rank < len(medals) else f"{rank + 1}."
            results_body += f"{rank_display} {user_name}: {session_score}/{num_q_in_session} (общий счёт: {global_score})\n"

        if len(sorted_session_participants) > 3:
            results_body += "\nОтличная игра, остальные участники!"

    try: await context.bot.send_message(chat_id=chat_id_str, text=results_header + results_body)
    except Exception as e: logger.error(f"Ошибка отправки результатов сессии в {chat_id_str}: {e}", exc_info=True)

    # Очистка сессии
    current_poll_id_of_session = session.get("current_poll_id") # Poll_id последнего отправленного вопроса
    if current_poll_id_of_session and current_poll_id_of_session in current_poll:
        del current_poll[current_poll_id_of_session]

    current_quiz_session.pop(chat_id_str, None) # Удаляем сессию
    logger.info(f"Сессия для чата {chat_id_str} очищена.")
    # Глобальные очки уже должны быть сохранены в handle_poll_answer

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_str = str(update.effective_chat.id) # type: ignore
    if chat_id_str not in user_scores or not user_scores[chat_id_str]:
        await update.message.reply_text("Статистики нет."); return # type: ignore

    sorted_scores = sorted(user_scores[chat_id_str].items(), key=lambda item: item[1].get("score", 0), reverse=True)
    if not sorted_scores: await update.message.reply_text("Пока нет игроков с очками."); return # type: ignore

    top_text = "🏆 Топ игроков в этом чате:\n"
    for i, (uid, data) in enumerate(sorted_scores[:10]): # Топ-10
        top_text += f"{i+1}. {data.get('name', f'User {uid}')} - {data.get('score', 0)} очков\n"
    await update.message.reply_text(top_text) # type: ignore

async def stop_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_str, user_id_str = str(update.effective_chat.id), str(update.effective_user.id) # type: ignore
    session = current_quiz_session.get(chat_id_str)
    if not session: await update.message.reply_text("Нет активной викторины."); return # type: ignore

    is_admin = False
    if update.effective_chat.type != "private": # type: ignore
        try:
            member = await context.bot.get_chat_member(chat_id_str, user_id_str)
            if member.status in [member.ADMINISTRATOR, member.OWNER]: is_admin = True
        except Exception as e: logger.warning(f"Ошибка проверки админа {user_id_str} в {chat_id_str}: {e}")

    if not is_admin and user_id_str != session.get("starter_user_id"):
        await update.message.reply_text("Только админ или запустивший может остановить."); return # type: ignore

    logger.info(f"/stopquiz от {user_id_str} в {chat_id_str}. Остановка сессии.")
    current_poll_id = session.get("current_poll_id")
    if current_poll_id and current_poll_id in current_poll:
        try: await context.bot.stop_poll(chat_id_str, current_poll[current_poll_id]["message_id"])
        except Exception as e: logger.error(f"Ошибка stop_poll {current_poll_id} в {chat_id_str}: {e}")

    await show_quiz_session_results(context, chat_id_str, error_occurred=True) # Показываем как прерванную
    await update.message.reply_text("Викторина остановлена.") # type: ignore

# --- Точка входа ---
def main():
    if not TOKEN: logger.critical("Токен BOT_TOKEN не найден!"); return
    load_questions(); load_user_data()
    app = ApplicationBuilder().token(TOKEN).build() # type: ignore
    app.add_handlers([CommandHandler("start", start_command), CommandHandler("quiz", quiz_command),
        CommandHandler("quiz10", start_quiz10), CommandHandler("categories", categories_command),
        CommandHandler("top", top_command), CommandHandler("stopquiz", stop_quiz_command),
        PollAnswerHandler(handle_poll_answer)])

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error("Exception while handling an update:", exc_info=context.error)
    app.add_error_handler(error_handler)

    logger.info("Бот запускается..."); app.run_polling(); logger.info("Бот остановлен.")

if __name__ == '__main__':
    main()
