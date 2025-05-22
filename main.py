import logging
import os
import json
import copy # Для глубокого копирования
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

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

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
    raw_data: Dict[str, List[Dict[str, Any]]] = {}
    try:
        with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    except FileNotFoundError:
        logger.error(f"Файл вопросов {QUESTIONS_FILE} не найден.")
        quiz_data = {}; return
    except json.JSONDecodeError:
        logger.error(f"Ошибка декодирования JSON в {QUESTIONS_FILE}.")
        quiz_data = {}; return
    except Exception as e:
        logger.error(f"Неизвестная ошибка при загрузке сырых вопросов: {e}")
        quiz_data = {}; return

    processed_data: Dict[str, List[Dict[str, Any]]] = {}
    loaded_count, skipped_count = 0, 0
    for category, q_list in raw_data.items():
        if not isinstance(q_list, list):
            logger.warning(f"Категория '{category}' не содержит список. Пропуск."); continue
        
        processed_q_for_cat = []
        for idx, q_raw in enumerate(q_list):
            if not isinstance(q_raw, dict):
                logger.warning(f"Вопрос #{idx+1} в '{category}' не словарь. Пропуск."); skipped_count += 1; continue
            
            q_text, opts, correct_text = q_raw.get("question"), q_raw.get("options"), q_raw.get("correct")
            if not (isinstance(q_text, str) and q_text.strip() and \
                    isinstance(opts, list) and len(opts) >= 2 and all(isinstance(o, str) for o in opts) and \
                    isinstance(correct_text, str) and correct_text.strip()):
                logger.warning(f"Вопрос #{idx+1} в '{category}' неверный формат. Пропуск. {q_raw}"); skipped_count += 1; continue
            try:
                correct_idx = opts.index(correct_text)
            except ValueError:
                logger.warning(f"Ответ '{correct_text}' для '{q_text[:30]}...' в '{category}' не в опциях. Пропуск."); skipped_count += 1; continue
            
            processed_q_for_cat.append({"question": q_text, "options": opts, "correct_option_index": correct_idx})
            loaded_count += 1
        if processed_q_for_cat: processed_data[category] = processed_q_for_cat
    quiz_data = processed_data
    logger.info(f"Загружено {loaded_count} вопросов. Пропущено из-за ошибок: {skipped_count}.")

def load_user_data():
    global user_scores
    if not os.path.exists(USERS_FILE):
        logger.info(f"Файл {USERS_FILE} не найден, будет создан новый."); save_user_data({}); user_scores = {}; return
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f: content = f.read()
        if not content: logger.info(f"{USERS_FILE} пуст."); user_scores = {}; return
        loaded_data = json.loads(content)
        user_scores = convert_user_scores_lists_to_sets(loaded_data)
        logger.info(f"Данные пользователей загружены из {USERS_FILE}.")
    except json.JSONDecodeError:
        logger.error(f"Ошибка декодирования JSON в {USERS_FILE}. Файл будет перезаписан пустым."); save_user_data({}); user_scores = {}
    except Exception as e:
        logger.error(f"Ошибка загрузки рейтинга из {USERS_FILE}: {e}. Файл будет перезаписан."); save_user_data({}); user_scores = {}

def save_user_data(data: Dict[str, Any]):
    data_to_save_final = {}
    try:
        data_copy = copy.deepcopy(data)
        data_to_save_final = convert_sets_to_lists_recursively(data_copy)
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save_final, f, ensure_ascii=False, indent=4)
        logger.debug(f"Данные пользователей сохранены в {USERS_FILE}.")
    except Exception as e:
        problem_data_str = str(data_to_save_final if data_to_save_final else data) # Показать, что пытались сохранить
        logger.error(f"Ошибка при сохранении пользовательских данных: {e}. Данные (часть): {problem_data_str[:500]}")

# --- Инициализация ---
load_questions()
load_user_data()

# --- Вспомогательные функции ---
def get_user_mention(user_id: int, user_name: str) -> str: return f"[{user_name}](tg://user?id={user_id})"

def prepare_poll_options(q_details: Dict[str, Any]) -> Tuple[str, List[str], int, List[str]]:
    q_text = q_details["question"]
    if not ("correct_option_index" in q_details and isinstance(q_details["options"], list) and \
            0 <= q_details["correct_option_index"] < len(q_details["options"])):
        logger.error(f"Некорректные детали вопроса: {q_details}"); return "Ошибка вопроса", ["A", "B"], 0, ["A", "B"]
    
    correct_answer = q_details["options"][q_details["correct_option_index"]]
    options = list(q_details["options"]) # Копия для перемешивания
    random.shuffle(options)
    try: new_correct_index = options.index(correct_answer)
    except ValueError:
        logger.error(f"Ответ '{correct_answer}' не найден в {options} для '{q_text}'. Исходные: {q_details['options']}. Возврат к исходному индексу.")
        new_correct_index = q_details["correct_option_index"] # Аварийный вариант
    return q_text, options, new_correct_index, q_details["options"]

def get_random_questions(category: str, count: int) -> List[Dict[str, Any]]:
    cat_q_list = quiz_data.get(category)
    if not isinstance(cat_q_list, list) or not cat_q_list: return []
    num_actual = min(count, len(cat_q_list))
    return [dict(q, original_category=category) for q in random.sample(cat_q_list, num_actual)]

def get_random_questions_from_all(count: int) -> List[Dict[str, Any]]:
    all_q_details: List[Dict[str, Any]] = [dict(q, original_category=cat) for cat, q_list in quiz_data.items() if isinstance(q_list, list) for q in q_list]
    if not all_q_details: return []
    num_actual = min(count, len(all_q_details))
    return random.sample(all_q_details, num_actual)

# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not (update.message and update.effective_user): return
    chat_id_str, user = str(update.message.chat_id), update.effective_user
    uid_str = str(user.id)

    user_scores.setdefault(chat_id_str, {})
    user_entry = user_scores[chat_id_str].get(uid_str)
    if not user_entry:
        user_scores[chat_id_str][uid_str] = {"name": user.full_name, "score": 0, "answered_polls": set()}
    else:
        user_entry["name"] = user.full_name
        if not isinstance(user_entry.get("answered_polls"), set): user_entry["answered_polls"] = set(user_entry.get("answered_polls", []))
    save_user_data(user_scores)
    await update.message.reply_text("Привет! Я бот для викторин. Команды:\n/quiz_category <категория>\n/quiz10 [категория]\n/rating, /categories, /stopquiz10")

async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    if not quiz_data: await update.message.reply_text("Категории не загружены."); return
    cat_list_str = "\n".join([f"- {cat}" for cat in quiz_data if isinstance(quiz_data.get(cat), list) and quiz_data[cat]])
    await update.message.reply_text(f"Доступные категории:\n{cat_list_str}" if cat_list_str else "Нет доступных категорий.")

async def quiz_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not (update.message and update.effective_chat and context.args):
        if update.message: await update.message.reply_text("Укажите категорию: /quiz_category <название>"); return
    
    chat_id, chat_id_str = update.effective_chat.id, str(update.effective_chat.id) # type: ignore
    category_name = " ".join(context.args) # type: ignore
    q_list = get_random_questions(category_name, 1)
    if not q_list: await update.message.reply_text(f"Нет вопросов в '{category_name}' или категория не найдена."); return # type: ignore
    
    q_details = q_list[0]
    q_text, opts, correct_idx, _ = prepare_poll_options(q_details)
    try:
        poll_msg = await context.bot.send_poll(chat_id=chat_id, question=q_text[:Poll.MAX_QUESTION_LENGTH], options=opts,
            is_anonymous=False, type=Poll.QUIZ, correct_option_id=correct_idx, open_period=DEFAULT_POLL_OPEN_PERIOD)
        current_poll[poll_msg.poll.id] = {"chat_id": chat_id_str, "message_id": poll_msg.message_id, "correct_index": correct_idx,
            "quiz_session": False, "question_details": q_details, "next_question_triggered_for_this_poll": False, "associated_quiz_session_chat_id": None}
    except Exception as e:
        logger.error(f"Ошибка отправки одиночного опроса в {chat_id}: {e}"); await update.message.reply_text("Не удалось отправить вопрос.") # type: ignore

async def start_quiz10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not (update.message and update.effective_chat): return
    chat_id, chat_id_str = update.effective_chat.id, str(update.effective_chat.id)
    if chat_id_str in current_quiz_session: await update.message.reply_text("Серия уже запущена. /stopquiz10 для остановки."); return

    questions: List[Dict[str, Any]]; cat_desc: str
    num_fetch = 10
    if not context.args:
        logger.info(f"/quiz10 без категории от {chat_id_str}."); questions = get_random_questions_from_all(num_fetch); cat_desc = "всех категорий"
    else:
        cat_name = " ".join(context.args); logger.info(f"/quiz10 с '{cat_name}' от {chat_id_str}."); questions = get_random_questions(cat_name, num_fetch); cat_desc = f"категории '{cat_name}'"

    if not questions: await update.message.reply_text(f"Не удалось найти вопросы для {cat_desc}."); return
    
    num_actual = len(questions); q_word = "вопрос"
    if not(num_actual % 10 == 1 and num_actual % 100 != 11): q_word = "вопроса" if num_actual % 10 in [2,3,4] and num_actual % 100 not in [12,13,14] else "вопросов"
    
    intro_text = f"Начинаем квиз из {cat_desc}! Подготовлено {num_actual} {q_word}"
    if num_actual < num_fetch and num_actual > 0: intro_text += f" (меньше {num_fetch})"
    intro_text += ". Приготовьтесь!"
    
    intro_msg = await update.message.reply_text(intro_text)
    current_quiz_session[chat_id_str] = {"questions": questions, "session_scores": {}, "current_index": 0,
        "message_id_intro": intro_msg.message_id if intro_msg else None, "final_results_job": None}
    await send_next_quiz_question(context, chat_id_str)

async def send_next_quiz_question(context: ContextTypes.DEFAULT_TYPE, chat_id_str: str):
    session = current_quiz_session.get(chat_id_str)
    if not session: logger.warning(f"send_next_q: Сессия {chat_id_str} не найдена."); return

    if session["current_index"] >= len(session["questions"]):
        logger.info(f"Все {len(session['questions'])} вопросов сессии {chat_id_str} отправлены. Запуск таймера результатов.")
        if sj := session.get("final_results_job"): 
            try: sj.schedule_removal()
            except Exception as e_job: logger.error(f"Ошибка удаления старого job {chat_id_str}: {e_job}")
        
        job = context.job_queue.run_once(show_quiz10_final_results_after_delay, FINAL_ANSWER_WINDOW_SECONDS, chat_id=int(chat_id_str), name=f"quiz10_res_{chat_id_str}")
        session["final_results_job"] = job
        await context.bot.send_message(int(chat_id_str), f"Последний вопрос! {FINAL_ANSWER_WINDOW_SECONDS} сек на ответ. Затем результаты.")
        return

    q_details = session["questions"][session["current_index"]]
    q_text, opts, correct_idx, _ = prepare_poll_options(q_details)
    is_last = (session["current_index"] == len(session["questions"]) - 1)
    open_period = FINAL_ANSWER_WINDOW_SECONDS if is_last else DEFAULT_POLL_OPEN_PERIOD
    
    try:
        poll_msg = await context.bot.send_poll(chat_id=int(chat_id_str), question=q_text[:Poll.MAX_QUESTION_LENGTH], options=opts,
            is_anonymous=False, type=Poll.QUIZ, correct_option_id=correct_idx, open_period=open_period)
        current_poll[poll_msg.poll.id] = {"chat_id": chat_id_str, "message_id": poll_msg.message_id, "correct_index": correct_idx, "quiz_session": True,
            "question_details": q_details, "next_question_triggered_for_this_poll": False, "associated_quiz_session_chat_id": chat_id_str}
        session["current_index"] += 1
    except Exception as e:
        logger.error(f"Ошибка отправки вопроса сессии {chat_id_str}: {e}")
        await context.bot.send_message(int(chat_id_str), "Ошибка отправки вопроса. Сессия прервана.")
        await stop_quiz10_logic(int(chat_id_str), context, "Ошибка отправки вопроса.")

async def show_quiz10_final_results_after_delay(context: ContextTypes.DEFAULT_TYPE):
    if not (job := context.job): return
    chat_id, chat_id_str = job.chat_id, str(job.chat_id)
    session = current_quiz_session.get(chat_id_str)
    if not session: logger.info(f"show_results_delay: Сессия {chat_id_str} не найдена."); return

    logger.info(f"Таймер сработал. Финальные результаты для сессии {chat_id_str}.")
    num_q = len(session["questions"])
    results_text = f"🏁 **Результаты квиза ({num_q} {'вопрос' if num_q % 10 == 1 and num_q % 100 != 11 else ('вопроса' if num_q % 10 in [2,3,4] and num_q % 100 not in [12,13,14] else 'вопросов')}):** 🏁\n\n"
    
    sorted_participants = sorted(session["session_scores"].items(), key=lambda item: (-item[1]["score"], item[1]["name"].lower()))
    if not sorted_participants: results_text += "Никто не участвовал или не набрал очков."
    else:
        for rank, (uid_str, data) in enumerate(sorted_participants, 1):
            total_score = user_scores.get(chat_id_str, {}).get(uid_str, {}).get("score", 0)
            mention = get_user_mention(int(uid_str), data["name"])
            results_text += f"{rank}. {mention}: {data['score']}/{num_q} (общий рейтинг: {total_score})\n"
    try:
        await context.bot.send_message(chat_id, text=results_text, parse_mode='Markdown')
    except Exception as e: logger.error(f"Ошибка отправки финальных результатов в {chat_id}: {e}")
    cleanup_quiz_session(chat_id_str)
    logger.info(f"Сессия квиза {chat_id_str} завершена и очищена.")

def cleanup_quiz_session(chat_id_str: str):
    if session_data := current_quiz_session.pop(chat_id_str, None):
        if job := session_data.get("final_results_job"):
            try: job.schedule_removal()
            except Exception as e: logger.error(f"Ошибка удаления job {chat_id_str}: {e}")
    
    for poll_id in [pid for pid, p_info in current_poll.items() if p_info.get("associated_quiz_session_chat_id") == chat_id_str]:
        if poll_id in current_poll: del current_poll[poll_id]

async def stop_quiz10_logic(chat_id: int, context: ContextTypes.DEFAULT_TYPE, reason: str = "остановлена пользователем"):
    chat_id_str = str(chat_id)
    if chat_id_str in current_quiz_session:
        # Если останавливаем досрочно, мы не хотим показывать результаты по таймеру,
        # поэтому удаляем job, если он есть, и немедленно показываем текущие результаты.
        session = current_quiz_session.get(chat_id_str)
        if session and (job := session.get("final_results_job")):
            try: job.schedule_removal(); logger.info(f"Job результатов для {chat_id_str} отменен из-за /stopquiz10.")
            except Exception as e: logger.error(f"Ошибка отмены job {chat_id_str} при /stopquiz10: {e}")
            session["final_results_job"] = None # Убираем ссылку на job

        # Показать текущие накопленные результаты сессии немедленно (опционально, но может быть полезно)
        # await show_quiz10_final_results_now(context, chat_id_str) # Нужна новая функция
        # Или просто очищаем без показа промежуточных результатов
        cleanup_quiz_session(chat_id_str)
        await context.bot.send_message(chat_id, text=f"Серия из 10 вопросов {reason}.")
        logger.info(f"Серия квиза {chat_id_str} остановлена: {reason}.")
    else:
        await context.bot.send_message(chat_id, text="Нет активной серии для остановки.")


async def stop_quiz10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat: return
    await stop_quiz10_logic(update.effective_chat.id, context)

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not (pa := update.poll_answer) or not (user := pa.user): return
    poll_id, uid_str, user_name = pa.poll_id, str(user.id), user.full_name

    poll_info = current_poll.get(poll_id)
    if not poll_info: logger.debug(f"Ответ на старый/неизвестный опрос {poll_id}"); return

    chat_id_str, is_session_poll, correct_idx = poll_info["chat_id"], poll_info["quiz_session"], poll_info["correct_index"]
    selected_ids = pa.option_ids

    user_scores.setdefault(chat_id_str, {})
    user_global_data = user_scores[chat_id_str].setdefault(uid_str, {"name": user_name, "score": 0, "answered_polls": set()})
    user_global_data["name"] = user_name # Обновляем имя
    if not isinstance(user_global_data.get("answered_polls"), set): user_global_data["answered_polls"] = set(user_global_data.get("answered_polls", []))

    is_correct = bool(selected_ids and selected_ids[0] == correct_idx)
    if is_correct and poll_id not in user_global_data["answered_polls"]:
        user_global_data["score"] += 1
        user_global_data["answered_polls"].add(poll_id)
    save_user_data(user_scores)

    if is_session_poll and (session_cid_str := poll_info.get("associated_quiz_session_chat_id")) and (session := current_quiz_session.get(session_cid_str)):
        session_user_data = session["session_scores"].setdefault(uid_str, {"name": user_name, "score": 0, "correctly_answered_poll_ids_in_session": set()})
        session_user_data["name"] = user_name # Обновляем имя в сессии
        if not isinstance(session_user_data.get("correctly_answered_poll_ids_in_session"), set): session_user_data["correctly_answered_poll_ids_in_session"] = set(session_user_data.get("correctly_answered_poll_ids_in_session",[]))

        if is_correct and poll_id not in session_user_data["correctly_answered_poll_ids_in_session"]:
            session_user_data["score"] += 1
            session_user_data["correctly_answered_poll_ids_in_session"].add(poll_id)

        curr_q_idx_answered = session["current_index"] - 1
        is_last_q = (curr_q_idx_answered == len(session["questions"]) - 1)
        if not poll_info.get("next_question_triggered_for_this_poll") and not is_last_q:
            poll_info["next_question_triggered_for_this_poll"] = True
            logger.info(f"Первый ответ на вопрос {curr_q_idx_answered + 1} сессии {session_cid_str}. Следующий.")
            await send_next_quiz_question(context, session_cid_str)
        elif is_last_q: logger.debug(f"Ответ на последний вопрос сессии от {user_name}. Ожидание таймера.")
    elif is_session_poll: logger.warning(f"Ответ на опрос {poll_id} из сессии, но сессия {poll_info.get('associated_quiz_session_chat_id')} не найдена.")

async def rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not (update.message and update.effective_chat): return
    chat_id_str = str(update.effective_chat.id)
    if chat_id_str not in user_scores or not user_scores[chat_id_str]: await update.message.reply_text("Рейтинг пуст."); return

    sorted_users = sorted([item for item in user_scores[chat_id_str].items() if isinstance(item[1], dict)],
        key=lambda item: (-item[1].get("score", 0), item[1].get("name", "").lower()))
    
    text = "🏆 **Общий рейтинг:** 🏆\n\n" + ("Пока нет очков." if not sorted_users else 
        "\n".join([f"{r}. {get_user_mention(int(uid), d['name'])} - {d['score']} очков" for r, (uid, d) in enumerate(sorted_users, 1)]))
    await update.message.reply_text(text, parse_mode='Markdown')

# --- Точка входа ---
def main():
    if not TOKEN: logger.critical("Токен BOT_TOKEN не найден!"); return
    logger.info("Бот запускается...")

    # Рекомендация: удалить users.json перед первым запуском с этими изменениями, если он мог быть поврежден.
    # if os.path.exists(USERS_FILE):
    #     try:
    #         with open(USERS_FILE, 'r', encoding='utf-8') as f: json.load(f)
    #     except json.JSONDecodeError:
    #         logger.warning(f"{USERS_FILE} поврежден. Рекомендуется удалить для чистого старта.")
    #         # try: os.remove(USERS_FILE)
    #         # except OSError as e: logger.error(f"Не удалось удалить {USERS_FILE}: {e}")

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handlers([
        CommandHandler("start", start), CommandHandler("categories", categories_command),
        CommandHandler("quiz_category", quiz_category), CommandHandler("quiz10", start_quiz10),
        CommandHandler("stopquiz10", stop_quiz10), CommandHandler("rating", rating),
        PollAnswerHandler(handle_poll_answer)
    ])
    logger.info("Обработчики добавлены.")
    try: app.run_polling()
    except Exception as e: logger.critical(f"Критическая ошибка polling: {e}", exc_info=True)
    finally: logger.info("Бот остановлен.")

if __name__ == '__main__':
    main()
