import logging
import os
import json
from telegram import Update, Poll
from telegram.ext import ApplicationBuilder, CommandHandler, PollAnswerHandler, ContextTypes, JobQueue
from dotenv import load_dotenv
import random
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
quiz_data: Dict[str, List[Dict[str, Any]]] = {}
user_scores: Dict[str, Dict[str, Any]] = {}

# Хранение активных опросов
current_poll: Dict[str, Dict[str, Any]] = {}

# Хранение сессии квиза
current_quiz_session: Dict[str, Dict[str, Any]] = {}


# --- Вспомогательные функции для сериализации/десериализации ---
def convert_sets_to_lists_recursively(obj: Any) -> Any:
    """Рекурсивно преобразует все вхождения set в list."""
    if isinstance(obj, dict):
        return {k: convert_sets_to_lists_recursively(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_sets_to_lists_recursively(elem) for elem in obj]
    elif isinstance(obj, set):
        return list(obj)
    return obj

def convert_user_scores_lists_to_sets(scores_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Преобразует特定ключи ('answered_polls') из list обратно в set
    внутри загруженной структуры user_scores.
    """
    if not isinstance(scores_data, dict):
        return scores_data
    
    for chat_id, users_in_chat in scores_data.items():
        if isinstance(users_in_chat, dict):
            for user_id, user_data_dict in users_in_chat.items():
                if isinstance(user_data_dict, dict):
                    # Преобразуем 'answered_polls' обратно в set
                    if "answered_polls" in user_data_dict and isinstance(user_data_dict["answered_polls"], list):
                        user_data_dict["answered_polls"] = set(user_data_dict["answered_polls"])
                    # "correctly_answered_poll_ids_in_session" не хранится в user_scores, а в current_quiz_session (в памяти)
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
    questions_skipped_due_to_format_error = 0

    for category, questions_list in raw_quiz_data_from_file.items():
        if not isinstance(questions_list, list):
            logger.warning(f"Категория '{category}' в файле вопросов не содержит список. Пропускается.")
            continue
        
        processed_questions_for_category = []
        for idx, q_raw in enumerate(questions_list):
            if not isinstance(q_raw, dict):
                logger.warning(f"Вопрос #{idx+1} в категории '{category}' не является словарем. Пропускается.")
                questions_skipped_due_to_format_error += 1
                continue

            question_text = q_raw.get("question")
            options = q_raw.get("options")
            correct_answer_text = q_raw.get("correct")

            if not all([
                isinstance(question_text, str) and question_text.strip(),
                isinstance(options, list) and len(options) >= 2 and all(isinstance(opt, str) for opt in options),
                isinstance(correct_answer_text, str) and correct_answer_text.strip()
            ]):
                logger.warning(
                    f"Вопрос #{idx+1} в категории '{category}' имеет неверный формат или пустые значения. Пропускается. Детали: {q_raw}"
                )
                questions_skipped_due_to_format_error += 1
                continue
            
            try:
                correct_option_index = options.index(correct_answer_text)
            except ValueError:
                logger.warning(
                    f"Правильный ответ '{correct_answer_text}' для вопроса '{question_text[:50]}...' "
                    f"в категории '{category}' не найден в списке вариантов {options}. Пропускается."
                )
                questions_skipped_due_to_format_error += 1
                continue
            
            processed_question = {
                "question": question_text,
                "options": options,
                "correct_option_index": correct_option_index
            }
            processed_questions_for_category.append(processed_question)
            total_questions_loaded += 1
        
        if processed_questions_for_category:
            processed_quiz_data[category] = processed_questions_for_category
        else:
            logger.info(f"Категория '{category}' не содержит валидных вопросов после обработки или была изначально пустой.")

    quiz_data = processed_quiz_data
    if total_questions_loaded > 0:
        logger.info(f"Успешно загружено и обработано {total_questions_loaded} вопросов.")
    else:
        logger.warning("Не было загружено ни одного валидного вопроса.")
    if questions_skipped_due_to_format_error > 0:
        logger.warning(f"{questions_skipped_due_to_format_error} вопросов было пропущено из-за ошибок формата или несоответствия данных.")


def load_user_data():
    global user_scores
    if not os.path.exists(USERS_FILE):
        save_user_data({})  # Создаем пустой, валидный файл, если его нет
        user_scores = {}
        return
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content:  # Если файл пуст
                user_scores = {}
                return
            loaded_data = json.loads(content)
            user_scores = convert_user_scores_lists_to_sets(loaded_data) # Преобразуем list в set где нужно
    except json.JSONDecodeError:
        logger.error(f"Ошибка декодирования JSON в файле пользователей {USERS_FILE}. Файл будет перезаписан пустым.")
        save_user_data({})  # Перезаписываем файл валидной пустой структурой
        user_scores = {}
    except Exception as e:
        logger.error(f"Ошибка при загрузке рейтинга: {e}. Файл будет перезаписан пустым.")
        save_user_data({})
        user_scores = {}

def save_user_data(data: Dict[str, Any]):
    try:
        # Глубокое копирование перед модификацией, чтобы не изменять оригинальный user_scores в памяти
        data_to_save = json.loads(json.dumps(data)) # Простой способ сделать глубокую копию простых структур
        data_to_save = convert_sets_to_lists_recursively(data_to_save) # Преобразуем все set в list
        
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка при сохранении пользовательских данных: {e}")

# --- Инициализация данных при запуске ---
load_questions()
load_user_data() # Загружаем данные пользователей (с преобразованием list -> set)


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
        logger.warning(f"get_random_questions: Категория '{category}' не найдена, не является списком или пуста.")
        return []
    
    category_questions_list = quiz_data[category]
    if not category_questions_list:
        logger.warning(f"get_random_questions: В категории '{category}' нет вопросов (список пуст).")
        return []

    num_available = len(category_questions_list)
    actual_count = min(count, num_available)
    
    selected_questions_raw = random.sample(category_questions_list, actual_count)
    
    selected_questions_processed = []
    for q_detail in selected_questions_raw:
        question_copy = q_detail.copy() 
        question_copy["original_category"] = category
        selected_questions_processed.append(question_copy)
            
    return selected_questions_processed

def get_random_questions_from_all(count: int) -> List[Dict[str, Any]]:
    all_questions_with_details: List[Dict[str, Any]] = []
    if not quiz_data:
        logger.warning("get_random_questions_from_all: quiz_data пуст.")
        return []

    for category, questions_list_in_cat in quiz_data.items():
        if questions_list_in_cat and isinstance(questions_list_in_cat, list):
            for q_detail in questions_list_in_cat:
                question_copy = q_detail.copy()
                question_copy["original_category"] = category
                all_questions_with_details.append(question_copy)
        elif not questions_list_in_cat:
             logger.debug(f"get_random_questions_from_all: Категория {category} пуста (список пуст).")
        else: 
            logger.warning(f"get_random_questions_from_all: Данные для категории {category} не являются списком: {type(questions_list_in_cat)}")

    if not all_questions_with_details:
        logger.info("get_random_questions_from_all: Не найдено ни одного вопроса во всех категориях.")
        return []

    num_available = len(all_questions_with_details)
    actual_count = min(count, num_available)
    
    return random.sample(all_questions_with_details, actual_count)


# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id_str = str(update.message.chat_id)
    user = update.effective_user
    user_id_str = str(user.id)

    if chat_id_str not in user_scores:
        user_scores[chat_id_str] = {}
    if user_id_str not in user_scores[chat_id_str]:
        # Инициализируем 'answered_polls' как set
        user_scores[chat_id_str][user_id_str] = {"name": user.full_name, "score": 0, "answered_polls": set()}
    else:
        user_scores[chat_id_str][user_id_str]["name"] = user.full_name
        # Убедимся, что answered_polls - это set, если пользователь уже существует
        if not isinstance(user_scores[chat_id_str][user_id_str].get("answered_polls"), set):
            user_scores[chat_id_str][user_id_str]["answered_polls"] = set(user_scores[chat_id_str][user_id_str].get("answered_polls", []))


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
    
    category_list = "\n".join([f"- {cat}" for cat in quiz_data.keys() if isinstance(quiz_data.get(cat), list) and quiz_data[cat]])
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

    question_list = get_random_questions(category_name, 1)
    if not question_list:
        await update.message.reply_text(f"В категории '{category_name}' не нашлось вопросов или категория не существует.")
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

    if not context.args: 
        logger.info(f"Запрос /quiz10 без категории от чата {chat_id_str}.")
        questions_for_session = get_random_questions_from_all(num_questions_to_fetch)
        category_source_description = "всех доступных категорий"
        
        if not questions_for_session:
            await update.message.reply_text("Не удалось найти вопросы. Возможно, база вопросов пуста или все категории пусты.")
            return
    else: 
        category_name = " ".join(context.args)
        logger.info(f"Запрос /quiz10 с категорией '{category_name}' от чата {chat_id_str}.")
        questions_for_session = get_random_questions(category_name, num_questions_to_fetch)
        category_source_description = f"категории '{category_name}'"
        
        if not questions_for_session: 
            await update.message.reply_text(f"В категории '{category_name}' не нашлось вопросов для квиза или категория не существует.")
            return
            
    actual_num_questions = len(questions_for_session)
    
    intro_message_text = f"Начинаем квиз из {category_source_description}! "
    if actual_num_questions == 1:
        intro_message_text += f"Подготовлен {actual_num_questions} вопрос. Приготовьтесь!"
    elif actual_num_questions < num_questions_to_fetch :
         intro_message_text += f"Подготовлено {actual_num_questions} вопросов (меньше {num_questions_to_fetch}). Приготовьтесь!"
    else:
        intro_message_text += f"Подготовлено {actual_num_questions} вопросов. Приготовьтесь!"

    intro_message = await update.message.reply_text(intro_message_text)

    current_quiz_session[chat_id_str] = {
        "questions": questions_for_session,
        "session_scores": {}, # Инициализируется при первом ответе пользователя в сессии
        "current_index": 0,
        "message_id_intro": intro_message.message_id if intro_message else None,
        "final_results_job": None
    }

    # Очищаем 'answered_polls' для текущей сессии quiz10, чтобы очки за общие вопросы
    # не начислялись повторно, если вопрос попадется снова в другой сессии.
    # Сессионные очки ('correctly_answered_poll_ids_in_session') управляются отдельно.
    if chat_id_str in user_scores:
        for uid in user_scores[chat_id_str]: 
            if isinstance(user_scores[chat_id_str].get(uid), dict):
                # Мы не очищаем user_scores[...]["answered_polls"] здесь,
                # так как это глобальный счетчик правильно отвеченных опросов для общего рейтинга.
                # Очистка этого сета приведет к тому, что пользователь сможет получать очки за один и тот же poll_id многократно.
                # Логика начисления очков в handle_poll_answer должна предотвращать повторное начисление за тот же poll_id.
                pass # user_scores[chat_id_str][uid]["answered_polls"] = set() # ЭТО БЫЛО БЫ НЕВЕРНО
    # save_user_data(user_scores) # Нет необходимости сохранять здесь, т.к. данные не изменились

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
        # current_quiz_session[chat_id_str] = session # Не обязательно сохранять здесь, т.к. session - ссылка
        await context.bot.send_message(
            chat_id=int(chat_id_str),
            text=f"Это был последний вопрос! У вас есть {FINAL_ANSWER_WINDOW_SECONDS} секунд, чтобы ответить на него. Затем будут показаны результаты."
        )
        return

    question_details = session["questions"][session["current_index"]]
    q_text, options, correct_idx, _ = prepare_poll_options(question_details)
    
    is_last_question = (session["current_index"] == len(session["questions"]) - 1)
    current_open_period = DEFAULT_POLL_OPEN_PERIOD
    if is_last_question:
        current_open_period = FINAL_ANSWER_WINDOW_SECONDS 
    
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
        # current_quiz_session[chat_id_str] = session # Не обязательно

    except Exception as e:
        logger.error(f"Ошибка отправки вопроса сессии в чат {chat_id_str}: {e}")
        await context.bot.send_message(int(chat_id_str), "Произошла ошибка при отправке следующего вопроса. Сессия может быть прервана.")
        await stop_quiz10_logic(int(chat_id_str), context, "Ошибка отправки вопроса.")


async def show_quiz10_final_results_after_delay(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id # type: ignore
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
        for rank, (user_id_str_val, data) in enumerate(sorted_session_participants, 1):
            user_name = data["name"]
            session_score = data["score"]
            # user_scores уже должен быть актуальным и содержать set где надо
            total_score = user_scores.get(chat_id_str, {}).get(user_id_str_val, {}).get("score", 0)
            user_mention_md = get_user_mention(int(user_id_str_val), user_name)
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
            session["final_results_job"].schedule_removal() # type: ignore
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

    # Гарантируем корректную структуру user_scores для пользователя
    if chat_id_str not in user_scores:
        user_scores[chat_id_str] = {}
    if user_id_str not in user_scores[chat_id_str]:
        user_scores[chat_id_str][user_id_str] = {"name": user_name, "score": 0, "answered_polls": set()}
    else:
        if user_scores[chat_id_str][user_id_str]["name"] != user_name:
            user_scores[chat_id_str][user_id_str]["name"] = user_name
        # Убедимся, что answered_polls - это set
        if not isinstance(user_scores[chat_id_str][user_id_str].get("answered_polls"), set):
             user_scores[chat_id_str][user_id_str]["answered_polls"] = set(user_scores[chat_id_str][user_id_str].get("answered_polls", []))


    is_correct = bool(selected_option_ids and selected_option_ids[0] == correct_option_index)

    # Обновление общего рейтинга
    if is_correct:
        # Начисляем балл в общий рейтинг только если за этот poll_id пользователь еще не получал балл
        if poll_id not in user_scores[chat_id_str][user_id_str]["answered_polls"]:
             user_scores[chat_id_str][user_id_str]["score"] = user_scores[chat_id_str][user_id_str].get("score", 0) + 1
             user_scores[chat_id_str][user_id_str]["answered_polls"].add(poll_id)
    
    save_user_data(user_scores) # Сохраняем изменения в общем рейтинге (с преобразованием set -> list)

    # Логика для сессии /quiz10
    if is_quiz_session_poll:
        session_chat_id = poll_info.get("associated_quiz_session_chat_id")
        if session_chat_id and session_chat_id in current_quiz_session:
            session = current_quiz_session[session_chat_id]
            
            # Инициализация или обновление имени в сессионных очках
            if user_id_str not in session["session_scores"]:
                session["session_scores"][user_id_str] = {"name": user_name, "score": 0, "correctly_answered_poll_ids_in_session": set()}
            elif session["session_scores"][user_id_str]["name"] != user_name:
                 session["session_scores"][user_id_str]["name"] = user_name
            # Убедимся, что correctly_answered_poll_ids_in_session является set
            if not isinstance(session["session_scores"][user_id_str].get("correctly_answered_poll_ids_in_session"), set):
                session["session_scores"][user_id_str]["correctly_answered_poll_ids_in_session"] = set(session["session_scores"][user_id_str].get("correctly_answered_poll_ids_in_session", []))


            # Начисление очков за сессию
            if is_correct and poll_id not in session["session_scores"][user_id_str]["correctly_answered_poll_ids_in_session"]:
                session["session_scores"][user_id_str]["score"] += 1
                session["session_scores"][user_id_str]["correctly_answered_poll_ids_in_session"].add(poll_id)
                # current_quiz_session[session_chat_id] = session # Не обязательно, т.к. session - ссылка

            # Переход к следующему вопросу
            current_question_index_in_session = session["current_index"] -1 
            is_it_last_question_of_session = (current_question_index_in_session == len(session["questions"]) - 1)

            if not poll_info.get("next_question_triggered_for_this_poll") and not is_it_last_question_of_session:
                poll_info["next_question_triggered_for_this_poll"] = True
                # current_poll[poll_id] = poll_info # Не обязательно
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

    # user_scores уже должен быть корректно загружен (с list -> set преобразованием)
    sorted_users = sorted(
        [item for item in user_scores[chat_id_str].items() if isinstance(item[1], dict)], 
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

    # Важно: Перед первым запуском с этими изменениями, если файл users.json существует
    # и мог быть поврежден предыдущими запусками (из-за ошибки сериализации set),
    # его лучше удалить или переименовать, чтобы бот создал новый, чистый файл.
    # Либо убедиться, что load_user_data корректно обработает ошибку декодирования и перезапишет его.
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
