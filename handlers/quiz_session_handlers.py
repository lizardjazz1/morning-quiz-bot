# handlers/quiz_session_handlers.py
import random
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatMemberStatus

from config import (logger, NUMBER_OF_QUESTIONS_IN_SESSION,
                    CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT,
                    CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY,
                    QUIZ10_NOTIFY_DELAY_MINUTES)
import state
from quiz_logic import (get_random_questions, get_random_questions_from_all,
                        send_next_question_in_session,
                        show_quiz_session_results)
# Импорт _is_user_admin из daily_quiz_handlers, если он там останется единственным таким
# Но лучше его перенести в utils.py или держать копию, если он специфичен.
# Для простоты предположим, что он доступен или будет перенесен.
# from .daily_quiz_handlers import _is_user_admin # Если daily_quiz_handlers в том же пакете

# Вспомогательная функция для проверки прав администратора (может быть вынесена в utils.py)
async def _is_user_chat_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.effective_chat or not update.effective_user:
        return False
    if update.effective_chat.type == 'private':
        return True # В личных сообщениях пользователь всегда "админ" для своего бота
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception as e:
        logger.warning(f"Ошибка проверки статуса администратора для пользователя {update.effective_user.id} в чате {update.effective_chat.id}: {e}")
        return False

# --- Вспомогательная функция для старта сессии (используется quiz10 и quiz10notify) ---
async def _initiate_quiz10_session(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int, # Используем int для совместимости с context.bot.send_message
    chat_id_str: str, # Строка для ключей в state
    user_id: int,
    category_name: str | None # Полное имя категории или None для случайных
):
    """Инициализирует и запускает сессию /quiz10."""
    questions_for_session = []
    intro_message_part = ""
    reply_text_to_send = "" # Для сообщений об ошибках

    if category_name:
        questions_for_session = get_random_questions(category_name, NUMBER_OF_QUESTIONS_IN_SESSION)
        intro_message_part = f"из категории: {category_name}"
    else:
        questions_for_session = get_random_questions_from_all(NUMBER_OF_QUESTIONS_IN_SESSION)
        intro_message_part = "из случайных категорий"

    actual_number_of_questions = len(questions_for_session)
    if actual_number_of_questions == 0:
        reply_text_to_send = f"Не найдено вопросов для /quiz10 ({intro_message_part}). Викторина не будет начата."
        logger.debug(f"Attempting to send message to {chat_id_str} (_initiate_quiz10_session, no questions). Text: '{reply_text_to_send}'")
        try:
            await context.bot.send_message(chat_id=chat_id, text=reply_text_to_send)
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения о пустой категории в чат {chat_id_str} (initiate_quiz10): {e}")
        return

    start_message_text = f"🚀 Начинаем викторину из {actual_number_of_questions} вопросов ({intro_message_part})! Приготовьтесь!"
    if actual_number_of_questions < NUMBER_OF_QUESTIONS_IN_SESSION:
        # Сообщение уже достаточно информативно из-за actual_number_of_questions
        pass

    intro_message = None
    logger.debug(f"Attempting to send intro message for /quiz10 to {chat_id_str}. Text: '{start_message_text}'")
    try:
        intro_message = await context.bot.send_message(chat_id=chat_id, text=start_message_text)
    except Exception as e:
         logger.error(f"Ошибка отправки вводного сообщения сессии в чат {chat_id_str}: {e}", exc_info=True)
         # Если не можем отправить интро, вероятно, не стоит продолжать
         return

    state.current_quiz_session[chat_id_str] = {
        "questions": questions_for_session,
        "session_scores": {},
        "current_index": 0, # Индекс следующего вопроса к отправке
        "actual_num_questions": actual_number_of_questions,
        "message_id_intro": intro_message.message_id if intro_message else None,
        "starter_user_id": str(user_id), # Сохраняем как строку для консистентности
        "current_poll_id": None, # ID последнего отправленного опроса в этой сессии
        "next_question_job": None, # Job для таймаута текущего вопроса / запуска следующего
        "category_used": category_name
    }
    logger.info(f"/quiz10 на {actual_number_of_questions} вопросов ({intro_message_part}) запущена в чате {chat_id_str} пользователем {user_id}.")
    await send_next_question_in_session(context, chat_id_str) # Отправляем первый вопрос

async def quiz10_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        logger.warning("quiz10_command: message or effective_chat is None.")
        return

    chat_id_str = str(update.effective_chat.id)
    # chat_id_int = update.effective_chat.id # Для context.chat_data, не используется здесь напрямую

    if state.current_quiz_session.get(chat_id_str):
        await update.message.reply_text("В этом чате уже идет игра /quiz10. Дождитесь ее окончания или используйте /stopquiz.")
        return
    if state.pending_scheduled_quizzes.get(chat_id_str):
        await update.message.reply_text(f"В этом чате уже запланирована игра /quiz10notify. Дождитесь ее начала или используйте /stopquiz.")
        return
    if state.active_daily_quizzes.get(chat_id_str):
        await update.message.reply_text("В этом чате идет ежедневная викторина. Команда /quiz10 временно недоступна. Вы можете остановить ежедневную викторину с помощью /stopquiz (только админ).")
        return

    if not state.quiz_data:
        await update.message.reply_text("Вопросы еще не загружены. Попробуйте /start позже.")
        return

    available_categories = [cat_name for cat_name, q_list in state.quiz_data.items() if isinstance(q_list, list) and q_list]
    if not available_categories:
        await update.message.reply_text("Нет доступных категорий с вопросами для /quiz10.")
        return

    keyboard = []
    category_map_for_callback: Dict[str, str] = {}
    for i, cat_name in enumerate(sorted(available_categories)):
        short_id = f"c{i}"
        category_map_for_callback[short_id] = cat_name
        callback_data = f"{CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT}{short_id}"
        if len(callback_data.encode('utf-8')) > 64:
             logger.error(f"Сгенерированный callback_data '{callback_data}' для категории '{cat_name}' слишком длинный! Пропуск кнопки.")
             continue
        keyboard.append([InlineKeyboardButton(cat_name, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("🎲 Случайные категории", callback_data=CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY)])
    reply_markup = InlineKeyboardMarkup(keyboard)

    chat_data_key = f"quiz10_cat_map_{chat_id_str}"
    context.chat_data[chat_data_key] = category_map_for_callback
    logger.debug(f"Временная карта категорий сохранена в chat_data (ключ: {chat_data_key}) для чата {chat_id_str}.")

    await update.message.reply_text('Выберите категорию для немедленного старта /quiz10:', reply_markup=reply_markup)

async def handle_quiz10_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        logger.error("handle_quiz10_category_selection: query is None.")
        return
    await query.answer()

    if not query.message or not query.message.chat or not query.from_user:
        logger.warning("handle_quiz10_category_selection: message, chat or user is None in query.")
        return

    chat_id_int = query.message.chat.id
    chat_id_str = str(chat_id_int)
    user_id = query.from_user.id

    chat_data_key = f"quiz10_cat_map_{chat_id_str}"
    category_map_for_callback: Dict[str, str] | None = context.chat_data.pop(chat_data_key, None)

    if category_map_for_callback is None:
        logger.warning(f"Временная карта категорий не найдена в chat_data (ключ: {chat_data_key}) для чата {chat_id_str}. Ответ на старую кнопку или ошибка.")
        message_text_on_error = "Ошибка: Время выбора категории истекло или произошла внутренняя ошибка. Попробуйте начать новую викторину с /quiz10."
        try: await query.edit_message_text(text=message_text_on_error)
        except Exception: pass # Ignore if fails, e.g. message too old
        return

    selected_category_name: str | None = None
    callback_data = query.data
    message_text_after_selection = ""

    if callback_data == CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY:
        selected_category_name = None
        message_text_after_selection = "Выбран случайный набор категорий. Начинаем /quiz10..."
    elif callback_data and callback_data.startswith(CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT):
        short_id = callback_data[len(CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT):]
        selected_category_name = category_map_for_callback.get(short_id)
        if selected_category_name:
             message_text_after_selection = f"Выбрана категория '{selected_category_name}'. Начинаем /quiz10..."
        else:
             message_text_after_selection = "Произошла ошибка при выборе категории (ID не найден). Попробуйте /quiz10."
             # Fall through to edit message and return
    else:
        message_text_after_selection = "Произошла ошибка (неизвестный тип выбора). Попробуйте /quiz10."

    try: await query.edit_message_text(text=message_text_after_selection)
    except Exception: pass # Ignore if fails

    if "Начинаем /quiz10..." in message_text_after_selection:
         await _initiate_quiz10_session(context, chat_id_int, chat_id_str, user_id, selected_category_name)

async def quiz10notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user:
        return

    chat_id_int = update.effective_chat.id
    chat_id_str = str(chat_id_int)
    user_id = update.effective_user.id

    if state.current_quiz_session.get(chat_id_str):
        await update.message.reply_text("В этом чате уже идет игра /quiz10. Дождитесь ее окончания или используйте /stopquiz.")
        return
    if state.pending_scheduled_quizzes.get(chat_id_str):
        await update.message.reply_text(f"В этом чате уже запланирована игра /quiz10notify. Дождитесь ее начала или используйте /stopquiz.")
        return
    if state.active_daily_quizzes.get(chat_id_str):
        await update.message.reply_text("В этом чате идет ежедневная викторина. Команда /quiz10notify временно недоступна. Вы можете остановить ежедневную викторину с помощью /stopquiz (только админ).")
        return

    category_name_arg = " ".join(context.args) if context.args else None
    chosen_category_full_name: str | None = None
    category_display_name = "случайным категориям"

    if not state.quiz_data:
        await update.message.reply_text("Вопросы еще не загружены. Попробуйте /start позже.")
        return

    if category_name_arg:
        found_cat_name = next((cat for cat in state.quiz_data if cat.lower() == category_name_arg.lower() and state.quiz_data[cat]), None)
        if found_cat_name:
            chosen_category_full_name = found_cat_name
            category_display_name = f"категории '{chosen_category_full_name}'"
        else:
            await update.message.reply_text(f"Категория '{category_name_arg}' не найдена или пуста. Викторина будет запланирована по случайным категориям.")
            # chosen_category_full_name remains None

    if not chosen_category_full_name and not category_name_arg: # No specific category, check general availability
         all_questions_flat = [q for q_list in state.quiz_data.values() for q in q_list]
         if not all_questions_flat:
             await update.message.reply_text("Нет доступных вопросов для викторины.")
             return

    delay_seconds = QUIZ10_NOTIFY_DELAY_MINUTES * 60
    job_name = f"scheduled_quiz10_chat_{chat_id_str}"
    job_context_data = {"chat_id_int": chat_id_int, "user_id": user_id, "category_full_name": chosen_category_full_name}

    if context.job_queue:
        existing_jobs = context.job_queue.get_jobs_by_name(job_name)
        for old_job in existing_jobs: old_job.schedule_removal()

        context.job_queue.run_once(
            _start_scheduled_quiz10_job_callback,
            timedelta(seconds=delay_seconds),
            data=job_context_data,
            name=job_name
        )
        scheduled_time_utc = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        state.pending_scheduled_quizzes[chat_id_str] = {
            "job_name": job_name, "category_name": chosen_category_full_name,
            "starter_user_id": str(user_id), "scheduled_time": scheduled_time_utc
        }
        await update.message.reply_text(
            f"🔔 Принято! Викторина /quiz10 по {category_display_name} начнется через {QUIZ10_NOTIFY_DELAY_MINUTES} мин.\n"
            "Чтобы отменить, используйте /stopquiz."
        )
        logger.info(f"Запланирован /quiz10notify для чата {chat_id_str} по {category_display_name} через {QUIZ10_NOTIFY_DELAY_MINUTES} мин. Job: {job_name}")
    else:
        await update.message.reply_text("Ошибка: JobQueue не настроен.")
        logger.error("JobQueue не доступен в quiz10notify_command.")

async def _start_scheduled_quiz10_job_callback(context: ContextTypes.DEFAULT_TYPE):
    if not context.job or not context.job.data:
        logger.error("_start_scheduled_quiz10_job_callback вызван без job data.")
        return

    job_data = context.job.data
    chat_id_int: int = job_data["chat_id_int"]
    chat_id_str = str(chat_id_int)
    user_id: int = job_data["user_id"]
    category_full_name: str | None = job_data.get("category_full_name")

    pending_quiz_info = state.pending_scheduled_quizzes.get(chat_id_str)
    if not pending_quiz_info or pending_quiz_info.get("job_name") != context.job.name:
        logger.info(f"Запланированный quiz10 (job: {context.job.name}) для чата {chat_id_str} был отменен/заменен. Job завершен.")
        return
    state.pending_scheduled_quizzes.pop(chat_id_str, None)

    if state.current_quiz_session.get(chat_id_str) or state.active_daily_quizzes.get(chat_id_str):
        logger.warning(f"Попытка запустить запланированный quiz10 в чате {chat_id_str}, но там уже активна другая викторина (/quiz10 или ежедневная).")
        try:
            await context.bot.send_message(chat_id=chat_id_int, text="Не удалось запустить запланированную викторину /quiz10: в этом чате уже идет другая игра.")
        except Exception: pass
        return

    logger.info(f"Запускаем запланированный quiz10 для чата {chat_id_str}. Категория: {category_full_name if category_full_name else 'Случайные'}")
    await _initiate_quiz10_session(context, chat_id_int, chat_id_str, user_id, category_full_name)

async def stop_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user or not update.effective_chat:
        logger.warning("stop_quiz_command: message, user or chat is None.")
        return

    chat_id_int = update.effective_chat.id
    chat_id_str = str(chat_id_int)
    user_id_str = str(update.effective_user.id)
    
    stopped_messages = []
    user_is_chat_admin = await _is_user_chat_admin(update, context) # Use the local/imported helper

    # 1. Остановка активной сессии /quiz10
    active_session = state.current_quiz_session.get(chat_id_str)
    if active_session:
        session_starter_id = active_session.get("starter_user_id")
        can_stop_quiz10 = user_is_chat_admin or (user_id_str == session_starter_id)
        
        if can_stop_quiz10:
            logger.info(f"/stopquiz от {user_id_str} (admin: {user_is_chat_admin}) в {chat_id_str}. Остановка активной сессии /quiz10, начатой {session_starter_id}.")
            current_poll_id_in_session = active_session.get("current_poll_id")
            if current_poll_id_in_session:
                poll_info = state.current_poll.get(current_poll_id_in_session)
                if poll_info and poll_info.get("message_id"):
                    try:
                        await context.bot.stop_poll(chat_id_str, poll_info["message_id"])
                        logger.debug(f"Текущий опрос {current_poll_id_in_session} активной сессии /quiz10 остановлен.")
                    except Exception as e_stop_poll:
                        logger.warning(f"Ошибка остановки опроса {current_poll_id_in_session} через /stopquiz: {e_stop_poll}")
            await show_quiz_session_results(context, chat_id_str, error_occurred=True)
            stopped_messages.append("✅ Активная викторина /quiz10 остановлена.")
        else:
            stopped_messages.append("❌ Не удалось остановить активную /quiz10: только админ чата или инициатор викторины может это сделать.")

    # 2. Отмена запланированной /quiz10notify
    pending_quiz = state.pending_scheduled_quizzes.get(chat_id_str)
    if pending_quiz:
        pending_starter_id = pending_quiz.get("starter_user_id")
        can_cancel_pending_quiz10 = user_is_chat_admin or (user_id_str == pending_starter_id)

        if can_cancel_pending_quiz10:
            job_name = pending_quiz.get("job_name")
            if job_name and context.job_queue:
                jobs = context.job_queue.get_jobs_by_name(job_name)
                removed_count = 0
                for job in jobs:
                    job.schedule_removal()
                    removed_count +=1
                if removed_count > 0:
                    logger.info(f"Отменен(о) {removed_count} запланированный(х) quiz10notify (job: {job_name}) в {chat_id_str} от {user_id_str}.")
            state.pending_scheduled_quizzes.pop(chat_id_str, None)
            stopped_messages.append("✅ Запланированная викторина /quiz10notify отменена.")
        else:
            stopped_messages.append("❌ Не удалось отменить запланированную /quiz10notify: только админ чата или инициатор может это сделать.")

    # 3. Остановка активной ежедневной викторины
    active_daily_quiz_info = state.active_daily_quizzes.get(chat_id_str)
    if active_daily_quiz_info:
        can_stop_daily = user_is_chat_admin # Включает приватный чат, где user_is_chat_admin = True

        if can_stop_daily:
            logger.info(f"/stopquiz от {user_id_str} (admin: {user_is_chat_admin}) в {chat_id_str}. Остановка активной ежедневной викторины.")
            job_name_next_daily_q = active_daily_quiz_info.get("job_name_next_q")
            if job_name_next_daily_q and context.job_queue:
                jobs = context.job_queue.get_jobs_by_name(job_name_next_daily_q)
                removed_count = 0
                for job in jobs:
                    job.schedule_removal()
                    removed_count +=1
                if removed_count > 0:
                    logger.info(f"Отменен(о) {removed_count} следующий(х) вопрос(ов) ежедневной викторины (job: {job_name_next_daily_q}) в {chat_id_str}.")
            
            state.active_daily_quizzes.pop(chat_id_str, None)
            stopped_messages.append("✅ Активная ежедневная викторина остановлена. Следующие вопросы не будут отправлены.")
        else: # Групповой чат, пользователь не админ
            stopped_messages.append("❌ Не удалось остановить ежедневную викторину: только админ чата может это сделать.")
            
    # Отправка итогового сообщения
    if not stopped_messages:
        await update.message.reply_text("В этом чате нет активных или запланированных викторин (/quiz10, /quiz10notify, ежедневная) для остановки/отмены.")
    else:
        # Фильтруем сообщения об успешной остановке, если таковые были.
        # Если были только сообщения об ошибках прав, то добавим общее "нечего остановить или нет прав".
        success_stops = [msg for msg in stopped_messages if "✅" in msg]
        permission_errors = [msg for msg in stopped_messages if "❌" in msg]

        final_reply = ""
        if success_stops:
            final_reply += "\n".join(success_stops)
        
        if permission_errors:
            if final_reply: final_reply += "\n\n" # Добавляем разделитель, если были успешные остановки
            final_reply += "\n".join(permission_errors)
        
        if not final_reply: # Теоретически не должно случиться, если stopped_messages не пуст
             final_reply = "Не удалось выполнить команду /stopquiz."

        await update.message.reply_text(final_reply)
