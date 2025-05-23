# handlers/quiz_session_handlers.py
import random
# import urllib.parse # Для кодирования категории в callback_data - не используется в текущей реализации _initiate_quiz10_session
from datetime import datetime, timedelta, timezone # Для времени уведомления
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
# ConversationHandler не используется, убираем если не планируется

# Импорты из других модулей проекта
from config import (logger, DEFAULT_POLL_OPEN_PERIOD, NUMBER_OF_QUESTIONS_IN_SESSION, # DEFAULT_POLL_OPEN_PERIOD не используется здесь напрямую
                    CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY, CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY,
                    QUIZ10_NOTIFY_DELAY_MINUTES) # CALLBACK_DATA_QUIZ10_NOTIFY_START_NOW не используется здесь напрямую
import state # Для доступа к quiz_data, user_scores, current_quiz_session, current_poll, pending_scheduled_quizzes
# from data_manager import save_user_data # save_user_data здесь не нужен
from quiz_logic import (get_random_questions, get_random_questions_from_all,
                        # prepare_poll_options, # prepare_poll_options здесь не нужен, он в quiz_logic
                        send_next_question_in_session,
                        show_quiz_session_results) # Основная логика викторины
# from utils import pluralize_points # pluralize_points здесь не нужен

# --- Вспомогательная функция для старта сессии (используется quiz10 и quiz10notify) ---
async def _initiate_quiz10_session(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    chat_id_str: str,
    user_id: int,
    category_name: str | None
):
    """Инициализирует и запускает сессию /quiz10."""
    questions_for_session = []
    intro_message_part = ""

    if category_name:
        questions_for_session = get_random_questions(category_name, NUMBER_OF_QUESTIONS_IN_SESSION)
        intro_message_part = f"из категории: {category_name}"
    else:
        questions_for_session = get_random_questions_from_all(NUMBER_OF_QUESTIONS_IN_SESSION)
        intro_message_part = "из случайных категорий"

    actual_number_of_questions = len(questions_for_session)
    if actual_number_of_questions == 0:
        await context.bot.send_message(chat_id, f"Не найдено вопросов для /quiz10 ({intro_message_part}).")
        return

    start_message_text = f"🚀 Начинаем викторину из {actual_number_of_questions} вопросов ({intro_message_part})! Приготовьтесь!"
    if actual_number_of_questions < NUMBER_OF_QUESTIONS_IN_SESSION:
        start_message_text += f" (Меньше {NUMBER_OF_QUESTIONS_IN_SESSION}, доступно {actual_number_of_questions})"

    intro_message = await context.bot.send_message(chat_id, start_message_text)

    state.current_quiz_session[chat_id_str] = {
        "questions": questions_for_session,
        "session_scores": {},
        "current_index": 0,
        "actual_num_questions": actual_number_of_questions,
        "message_id_intro": intro_message.message_id,
        "starter_user_id": str(user_id),
        "current_poll_id": None,
        "next_question_job": None,
        "category_used": category_name # Сохраняем использованную категорию
    }
    logger.info(f"/quiz10 на {actual_number_of_questions} вопросов ({intro_message_part}) запущена в чате {chat_id_str} пользователем {user_id}.")
    await send_next_question_in_session(context, chat_id_str)


async def quiz10_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        logger.warning("quiz10_command: message or effective_chat is None.")
        return

    chat_id_str = str(update.effective_chat.id)

    if state.current_quiz_session.get(chat_id_str):
        await update.message.reply_text("В этом чате уже идет игра /quiz10. Дождитесь ее окончания или используйте /stopquiz.") # type: ignore
        return
    if state.pending_scheduled_quizzes.get(chat_id_str):
        await update.message.reply_text(f"В этом чате уже запланирована игра /quiz10notify. Дождитесь ее начала или используйте /stopquiz.") # type: ignore
        return

    if not state.quiz_data:
        await update.message.reply_text("Вопросы еще не загружены. Попробуйте /start позже.") # type: ignore
        return

    available_categories = [cat_name for cat_name, q_list in state.quiz_data.items() if isinstance(q_list, list) and q_list]
    if not available_categories:
        await update.message.reply_text("Нет доступных категорий с вопросами для /quiz10.") # type: ignore
        return

    keyboard = []
    for cat_name in available_categories:
        keyboard.append([InlineKeyboardButton(cat_name, callback_data=f"{CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY}{cat_name}")])
    keyboard.append([InlineKeyboardButton("🎲 Случайные категории", callback_data=CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Выберите категорию для немедленного старта /quiz10:', reply_markup=reply_markup) # type: ignore

async def handle_quiz10_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query: # query не может быть None для CallbackQueryHandler
        logger.error("handle_quiz10_category_selection: query is None, что не должно происходить.")
        return
        
    await query.answer()

    if not query.message or not query.message.chat or not query.from_user:
        logger.warning("handle_quiz10_category_selection: message, chat or user is None in query.")
        return

    chat_id = query.message.chat.id
    chat_id_str = str(chat_id)
    user_id = query.from_user.id

    try:
        await query.edit_message_text(text=f"Выбор сделан. Начинаем /quiz10...")
    except Exception as e:
        logger.info(f"Не удалось отредактировать сообщение с кнопками выбора категории: {e}")
        # Если не удалось отредактировать (например, сообщение слишком старое), отправляем новое.
        await context.bot.send_message(chat_id, "Выбор сделан. Начинаем /quiz10...")


    category_name = None
    if query.data == CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY:
        category_name = None
    elif query.data and query.data.startswith(CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY):
        category_name = query.data[len(CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY):]
    else:
        logger.warning(f"Неизвестные callback_data в handle_quiz10_category_selection: {query.data}")
        await context.bot.send_message(chat_id, "Произошла ошибка при выборе категории. Попробуйте снова.")
        return

    await _initiate_quiz10_session(context, chat_id, chat_id_str, user_id, category_name)

async def quiz10notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user:
        logger.warning("quiz10notify_command: message, chat or user is None.")
        return

    chat_id = update.effective_chat.id
    chat_id_str = str(chat_id)
    user_id = update.effective_user.id

    if state.current_quiz_session.get(chat_id_str):
        await update.message.reply_text("В этом чате уже идет игра /quiz10. Дождитесь ее окончания или используйте /stopquiz.") # type: ignore
        return
    if state.pending_scheduled_quizzes.get(chat_id_str):
        pending_info = state.pending_scheduled_quizzes[chat_id_str]
        scheduled_dt = pending_info.get("scheduled_time")
        time_left_str = "скоро"
        if scheduled_dt and isinstance(scheduled_dt, datetime):
            now_utc = datetime.now(timezone.utc) 
            if scheduled_dt > now_utc: 
                time_left = scheduled_dt - now_utc
                time_left_str = f"примерно через {max(1, int(time_left.total_seconds() / 60))} мин."
            else:
                time_left_str = "очень скоро (возможно, уже началась)"

        await update.message.reply_text(f"В этом чате уже запланирована игра /quiz10notify (начнется {time_left_str}). Дождитесь ее начала или используйте /stopquiz для отмены.") # type: ignore
        return

    category_name_arg = " ".join(context.args) if context.args else None # type: ignore
    chosen_category_name = None 
    category_display_name = "случайным категориям"

    if category_name_arg:
        if category_name_arg in state.quiz_data and state.quiz_data[category_name_arg]:
            chosen_category_name = category_name_arg
            category_display_name = f"категории '{chosen_category_name}'"
        else:
            await update.message.reply_text(f"Категория '{category_name_arg}' не найдена или пуста. Викторина будет по случайным категориям.") # type: ignore
            
    if not chosen_category_name and not any(state.quiz_data.values()): # Проверка если нет ни одной категории с вопросами
        all_questions_flat = [q for cat_list in state.quiz_data.values() for q_list in cat_list for q in q_list]
        if not all_questions_flat:
            await update.message.reply_text("Нет доступных вопросов для викторины. Загрузите вопросы.") # type: ignore
            return

    delay_seconds = QUIZ10_NOTIFY_DELAY_MINUTES * 60
    job_name = f"scheduled_quiz10_{chat_id_str}"
    
    category_for_job = chosen_category_name if chosen_category_name else "RANDOM" 

    job_context_data = {"chat_id": chat_id, "user_id": user_id, "category_name_encoded": category_for_job}

    if context.job_queue:
        existing_jobs = context.job_queue.get_jobs_by_name(job_name)
        for old_job in existing_jobs:
            old_job.schedule_removal()
            logger.debug(f"Удален дублирующийся/старый job для quiz10notify: {old_job.name}")

        context.job_queue.run_once(
            _start_scheduled_quiz10_job_callback,
            timedelta(seconds=delay_seconds),
            data=job_context_data,
            name=job_name
        )

        scheduled_time_utc = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        state.pending_scheduled_quizzes[chat_id_str] = {
            "job_name": job_name,
            "category_name": chosen_category_name, 
            "starter_user_id": str(user_id),
            "scheduled_time": scheduled_time_utc 
        }

        await update.message.reply_text( # type: ignore
            f"🔔 Принято! Викторина /quiz10 по {category_display_name} начнется через {QUIZ10_NOTIFY_DELAY_MINUTES} мин.\n"
            "Чтобы отменить, используйте /stopquiz."
        )
        logger.info(f"Запланирован /quiz10notify для чата {chat_id_str} по {category_display_name} через {QUIZ10_NOTIFY_DELAY_MINUTES} мин. Job: {job_name}")
    else:
        await update.message.reply_text("Ошибка: JobQueue не настроен. Уведомление не может быть установлено.") # type: ignore
        logger.error("JobQueue не доступен в quiz10notify_command.")

async def _start_scheduled_quiz10_job_callback(context: ContextTypes.DEFAULT_TYPE):
    """Callback-функция, вызываемая JobQueue для старта запланированной викторины."""
    if not context.job or not context.job.data:
        logger.error("_start_scheduled_quiz10_job_callback вызван без job data.")
        return

    job_data = context.job.data
    chat_id: int = job_data["chat_id"]
    chat_id_str = str(chat_id)
    user_id: int = job_data["user_id"] 
    category_name_encoded: str = job_data["category_name_encoded"]

    if chat_id_str not in state.pending_scheduled_quizzes:
        logger.info(f"Запланированный quiz10 для чата {chat_id_str} был отменен или уже запущен. Job завершен.")
        return
    
    if state.current_quiz_session.get(chat_id_str):
        logger.warning(f"Попытка запустить запланированный quiz10 в чате {chat_id_str}, но там уже активна другая сессия.")
        state.pending_scheduled_quizzes.pop(chat_id_str, None) 
        return

    pending_info = state.pending_scheduled_quizzes.pop(chat_id_str, None)
    if pending_info: # Дополнительная проверка, что действительно было что удалять
         logger.info(f"Запускаем запланированный quiz10 для чата {chat_id_str}. Категория из job: {category_name_encoded}")

    actual_category_name = None
    if category_name_encoded != "RANDOM":
        actual_category_name = category_name_encoded 

    await _initiate_quiz10_session(context, chat_id, chat_id_str, user_id, actual_category_name)

async def stop_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user or not update.effective_chat:
        logger.warning("stop_quiz_command: message, user or chat is None.")
        return

    chat_id = update.effective_chat.id
    chat_id_str = str(chat_id)
    user_id_str = str(update.effective_user.id)

    user_is_admin = False
    if update.effective_chat.type != "private":
        try:
            chat_member = await context.bot.get_chat_member(chat_id_str, user_id_str)
            if chat_member.status in [chat_member.ADMINISTRATOR, chat_member.OWNER]: # type: ignore
                user_is_admin = True
        except Exception as e:
            logger.warning(f"Ошибка проверки статуса админа для {user_id_str} в {chat_id_str}: {e}")

    stopped_something = False

    active_session = state.current_quiz_session.get(chat_id_str)
    if active_session:
        if user_is_admin or user_id_str == active_session.get("starter_user_id"):
            logger.info(f"/stopquiz от {user_id_str} в {chat_id_str}. Остановка активной сессии /quiz10.")
            current_poll_id_in_session = active_session.get("current_poll_id")
            if current_poll_id_in_session and current_poll_id_in_session in state.current_poll:
                poll_message_id = state.current_poll[current_poll_id_in_session].get("message_id")
                if poll_message_id:
                    try:
                        await context.bot.stop_poll(chat_id_str, poll_message_id) # type: ignore
                    except Exception as e:
                        logger.error(f"Ошибка остановки опроса {current_poll_id_in_session} через /stopquiz: {e}")

            await show_quiz_session_results(context, chat_id_str, error_occurred=True) 
            await update.message.reply_text("Активная викторина /quiz10 остановлена.") # type: ignore
            stopped_something = True
        else:
            await update.message.reply_text("Только админ или тот, кто начал активную /quiz10, может ее остановить.") # type: ignore
            return 
    
    pending_quiz = state.pending_scheduled_quizzes.get(chat_id_str)
    if pending_quiz:
        if user_is_admin or user_id_str == pending_quiz.get("starter_user_id"):
            job_name = pending_quiz.get("job_name")
            if job_name and context.job_queue:
                jobs = context.job_queue.get_jobs_by_name(job_name)
                for job in jobs:
                    job.schedule_removal()
                    logger.info(f"Отменен запланированный quiz (job: {job_name}) в чате {chat_id_str} командой /stopquiz от {user_id_str}.")

            state.pending_scheduled_quizzes.pop(chat_id_str, None)
            await update.message.reply_text("Запланированная викторина /quiz10notify отменена.") # type: ignore
            stopped_something = True
        else:
            if not active_session: 
                 await update.message.reply_text("Только админ или тот, кто запланировал /quiz10notify, может ее отменить.") # type: ignore
            return

    if not stopped_something:
        await update.message.reply_text("В этом чате нет активных или запланированных викторин /quiz10 для остановки/отмены.") # type: ignore

