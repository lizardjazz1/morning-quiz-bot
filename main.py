import logging
import os
import json
import copy # <-- Добавлен импорт
from telegram import Update, Poll
from telegram.ext import ApplicationBuilder, CommandHandler, PollAnswerHandler, ContextTypes, JobQueue
from dotenv import load_dotenv
import random
from typing import List, Tuple, Dict, Any, Optional

# --- Константы ---
QUESTIONS_FILE = 'questions.json'
USERS_FILE = 'users.json'
DEFAULT_POLL_OPEN_PERIOD = 30
FINAL_ANSWER_WINDOW_SECONDS = 90

# Загрузка токена
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# Логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные переменные для данных
quiz_data: Dict[str, List[Dict[str, Any]]] = {}
user_scores: Dict[str, Dict[str, Any]] = {}
current_poll: Dict[str, Dict[str, Any]] = {}
current_quiz_session: Dict[str, Dict[str, Any]] = {}

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
            for user_id, user_data_dict in users_in_chat.items():
                if isinstance(user_data_dict, dict):
                    if "answered_polls" in user_data_dict and isinstance(user_data_dict["answered_polls"], list):
                        user_data_dict["answered_polls"] = set(user_data_dict["answered_polls"])
    return scores_data

# --- Функции загрузки и сохранения данных ---
def load_questions():
    global quiz_data
    raw_quiz_data_from_file: Dict[str, List[Dict[str, Any]]] = {}
    try:
        with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
            raw_quiz_data_from_file = json.load(f)
    except FileNotFoundError:
        logger.error(f"Файл вопросов {QUESTIONS_FILE} не найден.")
        quiz_data = {}
        return
    except json.JSONDecodeError:
        logger.error(f"Ошибка декодирования JSON в файле вопросов {QUESTIONS_FILE}.")
        quiz_data = {}
        return
    except Exception as e:
        logger.error(f"Неизвестная ошибка при загрузке сырых вопросов: {e}")
        quiz_data = {}
        return

    processed_quiz_data: Dict[str, List[Dict[str, Any]]] = {}
    total_questions_loaded = 0
    questions_skipped = 0
    for category, questions_list in raw_quiz_data_from_file.items():
        if not isinstance(questions_list, list):
            logger.warning(f"Категория '{category}' не содержит список. Пропускается.")
            continue
        processed_questions_for_category = []
        for idx, q_raw in enumerate(questions_list):
            if not isinstance(q_raw, dict):
                logger.warning(f"Вопрос #{idx+1} в '{category}' не словарь. Пропуск.")
                questions_skipped +=1
                continue
            q_text = q_raw.get("question")
            opts = q_raw.get("options")
            correct_text = q_raw.get("correct")
            if not all([isinstance(q_text, str) and q_text.strip(),
                        isinstance(opts, list) and len(opts) >= 2 and all(isinstance(o, str) for o in opts),
                        isinstance(correct_text, str) and correct_text.strip()]):
                logger.warning(f"Вопрос #{idx+1} в '{category}' имеет неверный формат. Пропуск. {q_raw}")
                questions_skipped +=1
                continue
            try:
                correct_idx = opts.index(correct_text)
            except ValueError:
                logger.warning(f"Ответ '{correct_text}' для '{q_text[:20]}...' в '{category}' не в опциях {opts}. Пропуск.")
                questions_skipped +=1
                continue
            processed_questions_for_category.append({"question": q_text, "options": opts, "correct_option_index": correct_idx})
            total_questions_loaded += 1
        if processed_questions_for_category:
            processed_quiz_data[category] = processed_questions_for_category
    quiz_data = processed_quiz_data
    logger.info(f"Загружено {total_questions_loaded} вопросов. Пропущено: {questions_skipped}")


def load_user_data():
    global user_scores
    if not os.path.exists(USERS_FILE):
        save_user_data({})
        user_scores = {}
        return
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content:
                user_scores = {}
                return
            loaded_data = json.loads(content)
            user_scores = convert_user_scores_lists_to_sets(loaded_data)
    except json.JSONDecodeError:
        logger.error(f"Ошибка декодирования JSON в {USERS_FILE}. Файл будет перезаписан.")
        save_user_data({})
        user_scores = {}
    except Exception as e:
        logger.error(f"Ошибка загрузки рейтинга из {USERS_FILE}: {e}. Файл будет перезаписан.")
        save_user_data({})
        user_scores = {}

def save_user_data(data: Dict[str, Any]):
    try:
        # 1. Создаем глубокую копию данных
        data_copy = copy.deepcopy(data)
        # 2. Рекурсивно преобразуем все set в list в этой копии.
        data_to_save = convert_sets_to_lists_recursively(data_copy)
        # 3. Сохраняем преобразованные данные в JSON.
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка при сохранении пользовательских данных: {e}")
        if isinstance(e, TypeError): # Дополнительное логирование для TypeError
             logger.error(f"Данные, вызвавшие TypeError при сохранении: {data_to_save if 'data_to_save' in locals() else 'data_to_save не определена'}")


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
    if category not in quiz_data or not isinstance(quiz_data.get(category), list) or not quiz_data[category]:
        return []
    category_questions_list = quiz_data[category]
    num_available = len(category_questions_list)
    actual_count = min(count, num_available)
    selected_raw = random.sample(category_questions_list, actual_count)
    return [dict(q, original_category=category) for q in selected_raw] # Добавляем original_category

def get_random_questions_from_all(count: int) -> List[Dict[str, Any]]:
    all_questions_with_details: List[Dict[str, Any]] = []
    if not quiz_data: return []
    for category, questions_list in quiz_data.items():
        if questions_list and isinstance(questions_list, list):
            for q_detail in questions_list:
                all_questions_with_details.append(dict(q_detail, original_category=category)) # Добавляем original_category
    if not all_questions_with_details: return []
    num_available = len(all_questions_with_details)
    actual_count = min(count, num_available)
    return random.sample(all_questions_with_details, actual_count)

# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_str = str(update.message.chat_id)
    user = update.effective_user
    user_id_str = str(user.id) # type: ignore

    if chat_id_str not in user_scores: user_scores[chat_id_str] = {}
    if user_id_str not in user_scores[chat_id_str]:
        user_scores[chat_id_str][user_id_str] = {"name": user.full_name, "score": 0, "answered_polls": set()}
    else:
        user_scores[chat_id_str][user_id_str]["name"] = user.full_name
        if not isinstance(user_scores[chat_id_str][user_id_str].get("answered_polls"), set):
            user_scores[chat_id_str][user_id_str]["answered_polls"] = set(user_scores[chat_id_str][user_id_str].get("answered_polls", []))
    save_user_data(user_scores)
    await update.message.reply_text( # type: ignore
        "Привет! Я бот для викторин.\n"
        "Используйте /quiz <категория> для одиночного вопроса.\n"
        "Используйте /quiz10 [категория] для серии из 10 вопросов (без категории - из всех).\n"
        "/rating - рейтинг, /categories - категории, /stopquiz10 - остановить серию."
    )

async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not quiz_data: await update.message.reply_text("Категории не загружены."); return # type: ignore
    cats = "\n".join([f"- {c}" for c in quiz_data if isinstance(quiz_data.get(c), list) and quiz_data[c]])
    await update.message.reply_text(f"Категории:\n{cats}" if cats else "Нет доступных категорий.") # type: ignore

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("Укажите категорию: /quiz <название>"); return # type: ignore
    category_name = " ".join(context.args)
    q_list = get_random_questions(category_name, 1)
    if not q_list: await update.message.reply_text(f"Нет вопросов в '{category_name}' или категория не найдена."); return # type: ignore
    
    q_details = q_list[0]
    q_text, opts, correct_idx, _ = prepare_poll_options(q_details)
    try:
        poll_msg = await context.bot.send_poll(
            chat_id=update.effective_chat.id, # type: ignore
            question=q_text[:Poll.MAX_QUESTION_LENGTH], options=opts,
            is_anonymous=False, type=Poll.QUIZ, correct_option_id=correct_idx,
            open_period=DEFAULT_POLL_OPEN_PERIOD
        )
        current_poll[poll_msg.poll.id] = {
            "chat_id": str(update.effective_chat.id), "message_id": poll_msg.message_id, # type: ignore
            "correct_index": correct_idx, "quiz_session": False,
            "question_details": q_details, "next_question_triggered_for_this_poll": False,
            "associated_quiz_session_chat_id": None
        }
    except Exception as e:
        logger.error(f"Ошибка отправки одиночного опроса: {e}")
        await update.message.reply_text("Не удалось отправить вопрос.") # type: ignore

async def start_quiz10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id # type: ignore
    chat_id_str = str(chat_id)
    if chat_id_str in current_quiz_session:
        await update.message.reply_text("Серия уже запущена. /stopquiz10 для остановки."); return # type: ignore

    questions_for_session: List[Dict[str, Any]]
    cat_desc: str
    num_to_fetch = 10

    if not context.args:
        logger.info(f"/quiz10 без категории от {chat_id_str}.")
        questions_for_session = get_random_questions_from_all(num_to_fetch)
        cat_desc = "всех доступных категорий"
        if not questions_for_session: await update.message.reply_text("Не найдено вопросов."); return # type: ignore
    else:
        category_name = " ".join(context.args)
        logger.info(f"/quiz10 с категорией '{category_name}' от {chat_id_str}.")
        questions_for_session = get_random_questions(category_name, num_to_fetch)
        cat_desc = f"категории '{category_name}'"
        if not questions_for_session: await update.message.reply_text(f"Нет вопросов в '{category_name}'."); return # type: ignore
    
    num_actual = len(questions_for_session)
    intro_text = f"Начинаем квиз из {cat_desc}! Подготовлено {num_actual} вопрос{'ов' if num_actual != 1 and (num_actual % 10 < 1 or num_actual % 10 > 4 or (num_actual > 10 and num_actual < 15)) else ('а' if num_actual % 10 > 1 and num_actual % 10 < 5 else '')}. Приготовьтесь!"
    if num_actual < num_to_fetch and num_actual > 0:
        intro_text = f"Начинаем квиз из {cat_desc}! Нашлось {num_actual} вопрос{'ов' if num_actual != 1 and (num_actual % 10 < 1 or num_actual % 10 > 4 or (num_actual > 10 and num_actual < 15)) else ('а' if num_actual % 10 > 1 and num_actual % 10 < 5 else '')} (меньше {num_to_fetch}). Приготовьтесь!"
    
    intro_msg = await update.message.reply_text(intro_text) # type: ignore
    current_quiz_session[chat_id_str] = {
        "questions": questions_for_session, "session_scores": {}, "current_index": 0,
        "message_id_intro": intro_msg.message_id if intro_msg else None, "final_results_job": None
    }
    await send_next_quiz_question(context, chat_id_str)

async def send_next_quiz_question(context: ContextTypes.DEFAULT_TYPE, chat_id_str: str):
    session = current_quiz_session.get(chat_id_str)
    if not session: logger.warning(f"send_next_quiz_question: Сессия {chat_id_str} не найдена."); return

    if session["current_index"] >= len(session["questions"]):
        logger.info(f"Все {len(session['questions'])} вопросов сессии {chat_id_str} отправлены. Таймер результатов.")
        if session.get("final_results_job"): session["final_results_job"].schedule_removal()
        job = context.job_queue.run_once(
            show_quiz10_final_results_after_delay, FINAL_ANSWER_WINDOW_SECONDS,
            chat_id=int(chat_id_str), name=f"quiz10_results_{chat_id_str}"
        )
        session["final_results_job"] = job
        await context.bot.send_message(chat_id=int(chat_id_str),
            text=f"Последний вопрос! {FINAL_ANSWER_WINDOW_SECONDS} сек на ответ. Затем результаты.")
        return

    q_details = session["questions"][session["current_index"]]
    q_text, opts, correct_idx, _ = prepare_poll_options(q_details)
    is_last = (session["current_index"] == len(session["questions"]) - 1)
    open_period = FINAL_ANSWER_WINDOW_SECONDS if is_last else DEFAULT_POLL_OPEN_PERIOD
    
    try:
        poll_msg = await context.bot.send_poll(
            chat_id=int(chat_id_str), question=q_text[:Poll.MAX_QUESTION_LENGTH], options=opts,
            is_anonymous=False, type=Poll.QUIZ, correct_option_id=correct_idx, open_period=open_period
        )
        current_poll[poll_msg.poll.id] = {
            "chat_id": chat_id_str, "message_id": poll_msg.message_id,
            "correct_index": correct_idx, "quiz_session": True,
            "question_details": q_details, "next_question_triggered_for_this_poll": False,
            "associated_quiz_session_chat_id": chat_id_str
        }
        session["current_index"] += 1
    except Exception as e:
        logger.error(f"Ошибка отправки вопроса сессии в {chat_id_str}: {e}")
        await context.bot.send_message(int(chat_id_str), "Ошибка отправки вопроса. Сессия прервана.")
        await stop_quiz10_logic(int(chat_id_str), context, "Ошибка отправки вопроса.")

async def show_quiz10_final_results_after_delay(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id # type: ignore
    chat_id_str = str(chat_id)
    session = current_quiz_session.get(chat_id_str)
    if not session: logger.info(f"show_quiz10_final_results: Сессия {chat_id_str} не найдена."); return

    logger.info(f"Таймер сработал. Финальные результаты для сессии {chat_id_str}.")
    num_q = len(session["questions"])
    results_text = f"🏁 **Результаты квиза ({num_q} вопросов):** 🏁\n\n"
    sorted_participants = sorted(session["session_scores"].items(), key=lambda item: (-item[1]["score"], item[1]["name"].lower()))

    if not sorted_participants: results_text += "Никто не участвовал или не набрал очков."
    else:
        for rank, (uid_str, data) in enumerate(sorted_participants, 1):
            total_score = user_scores.get(chat_id_str, {}).get(uid_str, {}).get("score", 0)
            mention = get_user_mention(int(uid_str), data["name"])
            results_text += f"{rank}. {mention}: {data['score']}/{num_q} (общий рейтинг: {total_score})\n"
    try:
        await context.bot.send_message(chat_id=chat_id, text=results_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка отправки финальных результатов в {chat_id}: {e}")
    cleanup_quiz_session(chat_id_str)
    logger.info(f"Сессия квиза для {chat_id_str} завершена и очищена.")

def cleanup_quiz_session(chat_id_str: str):
    if chat_id_str in current_quiz_session:
        session = current_quiz_session.pop(chat_id_str)
        if session.get("final_results_job"):
            session["final_results_job"].schedule_removal()
            logger.info(f"Удален job результатов сессии {chat_id_str} при очистке.")
    
    polls_to_del = [pid for pid, p_info in current_poll.items() if p_info.get("associated_quiz_session_chat_id") == chat_id_str]
    for pid in polls_to_del:
        if pid in current_poll: del current_poll[pid]

async def stop_quiz10_logic(chat_id: int, context: ContextTypes.DEFAULT_TYPE, reason: str = "остановлена пользователем"):
    chat_id_str = str(chat_id)
    if chat_id_str in current_quiz_session:
        cleanup_quiz_session(chat_id_str)
        await context.bot.send_message(chat_id=chat_id, text=f"Серия из 10 вопросов {reason}.")
        logger.info(f"Серия квиза для {chat_id_str} остановлена: {reason}.")
    else:
        await context.bot.send_message(chat_id=chat_id, text="Нет активной серии для остановки.")

async def stop_quiz10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stop_quiz10_logic(update.effective_chat.id, context) # type: ignore

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    poll_id = answer.poll_id
    user = answer.user
    user_id_str = str(user.id)
    user_name = user.full_name

    poll_info = current_poll.get(poll_id)
    if not poll_info: logger.debug(f"Ответ на неизвестный/старый опрос: {poll_id}"); return

    chat_id_str = poll_info["chat_id"]
    is_session_poll = poll_info["quiz_session"]
    correct_idx = poll_info["correct_index"]
    selected_ids = answer.option_ids

    if chat_id_str not in user_scores: user_scores[chat_id_str] = {}
    if user_id_str not in user_scores[chat_id_str]:
        user_scores[chat_id_str][user_id_str] = {"name": user_name, "score": 0, "answered_polls": set()}
    else:
        user_scores[chat_id_str][user_id_str]["name"] = user_name
        if not isinstance(user_scores[chat_id_str][user_id_str].get("answered_polls"), set):
            user_scores[chat_id_str][user_id_str]["answered_polls"] = set(user_scores[chat_id_str][user_id_str].get("answered_polls", []))
    
    is_correct = bool(selected_ids and selected_ids[0] == correct_idx)

    if is_correct:
        if poll_id not in user_scores[chat_id_str][user_id_str]["answered_polls"]:
            user_scores[chat_id_str][user_id_str]["score"] = user_scores[chat_id_str][user_id_str].get("score", 0) + 1
            user_scores[chat_id_str][user_id_str]["answered_polls"].add(poll_id)
    save_user_data(user_scores)

    if is_session_poll:
        session_chat_id = poll_info.get("associated_quiz_session_chat_id")
        if session_chat_id and session_chat_id in current_quiz_session:
            session = current_quiz_session[session_chat_id]
            if user_id_str not in session["session_scores"]:
                session["session_scores"][user_id_str] = {"name": user_name, "score": 0, "correctly_answered_poll_ids_in_session": set()}
            else: # Обновить имя, если изменилось, и убедиться, что set существует
                session["session_scores"][user_id_str]["name"] = user_name
                if not isinstance(session["session_scores"][user_id_str].get("correctly_answered_poll_ids_in_session"), set):
                     session["session_scores"][user_id_str]["correctly_answered_poll_ids_in_session"] = set(session["session_scores"][user_id_str].get("correctly_answered_poll_ids_in_session",[]))


            if is_correct and poll_id not in session["session_scores"][user_id_str]["correctly_answered_poll_ids_in_session"]:
                session["session_scores"][user_id_str]["score"] += 1
                session["session_scores"][user_id_str]["correctly_answered_poll_ids_in_session"].add(poll_id)

            curr_q_idx = session["current_index"] - 1
            is_last_q = (curr_q_idx == len(session["questions"]) - 1)

            if not poll_info.get("next_question_triggered_for_this_poll") and not is_last_q:
                poll_info["next_question_triggered_for_this_poll"] = True
                logger.info(f"Первый ответ на вопрос {curr_q_idx +1} сессии {session_chat_id}. Следующий.")
                await send_next_quiz_question(context, session_chat_id)
            elif is_last_q:
                logger.debug(f"Ответ на последний вопрос сессии от {user_name}. Ожидаем таймер.")
        else:
            logger.warning(f"Ответ на опрос {poll_id} из сессии, но сессия {poll_info.get('associated_quiz_session_chat_id')} не найдена.")

async def rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_str = str(update.effective_chat.id) # type: ignore
    if chat_id_str not in user_scores or not user_scores[chat_id_str]:
        await update.message.reply_text("Рейтинг для этого чата пока пуст."); return # type: ignore

    sorted_users = sorted(
        [item for item in user_scores[chat_id_str].items() if isinstance(item[1], dict)],
        key=lambda item: (-item[1].get("score", 0), item[1].get("name", "").lower())
    )
    rating_text = "🏆 **Общий рейтинг игроков в этом чате:** 🏆\n\n"
    if not sorted_users: rating_text += "Пока никто не набрал очков."
    else:
        for rank, (uid, data) in enumerate(sorted_users, 1):
            mention = get_user_mention(int(uid), data.get("name", f"User_{uid}"))
            rating_text += f"{rank}. {mention} - {data.get('score', 0)} очков\n"
    await update.message.reply_text(rating_text, parse_mode='Markdown') # type: ignore

# --- Точка входа ---
def main():
    if not TOKEN: logger.critical("Токен бота не найден. Установите BOT_TOKEN."); return
    logger.info("Бот запускается...")
    
    # Перед первым запуском с исправлением, удалите users.json, если он поврежден.
    # if os.path.exists(USERS_FILE):
    #     try:
    #         with open(USERS_FILE, 'r') as f_test:
    #             json.load(f_test)
    #     except json.JSONDecodeError:
    #         logger.warning(f"{USERS_FILE} поврежден. Удаление перед запуском рекомендуется.")
    #         # os.remove(USERS_FILE) # Раскомментируйте для автоматического удаления, если уверены.

    application = ApplicationBuilder().token(TOKEN).build() # type: ignore
    handlers = [
        CommandHandler("start", start), CommandHandler("categories", categories_command),
        CommandHandler("quiz", quiz), CommandHandler("quiz10", start_quiz10),
        CommandHandler("stopquiz10", stop_quiz10), CommandHandler("rating", rating),
        PollAnswerHandler(handle_poll_answer)
    ]
    for handler in handlers: application.add_handler(handler)
    logger.info("Обработчики добавлены.")
    try:
        application.run_polling()
    except Exception as e:
        logger.critical(f"Критическая ошибка polling: {e}", exc_info=True)
    finally:
        logger.info("Бот остановлен.")

if __name__ == '__main__':
    main()
