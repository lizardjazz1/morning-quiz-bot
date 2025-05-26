# handlers/quiz_session_handlers.py
import random
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes # JobQueue не импортируется напрямую

from config import (logger, NUMBER_OF_QUESTIONS_IN_SESSION,
                    CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT,
                    CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY,
                    QUIZ10_NOTIFY_DELAY_MINUTES)
import state
from quiz_logic import (get_random_questions, get_random_questions_from_all,
                        send_next_question_in_session,
                        show_quiz_session_results) # prepare_poll_options здесь не нужен

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
    chat_id_int = update.effective_chat.id # Для context.chat_data
    reply_text_to_send = ""

    if state.current_quiz_session.get(chat_id_str):
        reply_text_to_send = "В этом чате уже идет игра /quiz10. Дождитесь ее окончания или используйте /stopquiz."
        logger.debug(f"Attempting to send message to {chat_id_str} (quiz10_command blocked by active session). Text: '{reply_text_to_send}'")
        await update.message.reply_text(reply_text_to_send)
        return
    if state.pending_scheduled_quizzes.get(chat_id_str):
        reply_text_to_send = f"В этом чате уже запланирована игра /quiz10notify. Дождитесь ее начала или используйте /stopquiz."
        logger.debug(f"Attempting to send message to {chat_id_str} (quiz10_command blocked by pending session). Text: '{reply_text_to_send}'")
        await update.message.reply_text(reply_text_to_send)
        return

    if not state.quiz_data:
        reply_text_to_send = "Вопросы еще не загружены. Попробуйте /start позже."
        logger.debug(f"Attempting to send message to {chat_id_str} (quiz10_command, no questions loaded). Text: '{reply_text_to_send}'")
        await update.message.reply_text(reply_text_to_send)
        return

    available_categories = [cat_name for cat_name, q_list in state.quiz_data.items() if isinstance(q_list, list) and q_list]
    if not available_categories:
        reply_text_to_send = "Нет доступных категорий с вопросами для /quiz10."
        logger.debug(f"Attempting to send message to {chat_id_str} (quiz10_command, no categories with questions). Text: '{reply_text_to_send}'")
        await update.message.reply_text(reply_text_to_send)
        return

    keyboard = []
    category_map_for_callback: Dict[str, str] = {}
    for i, cat_name in enumerate(sorted(available_categories)): # Сортируем для предсказуемого порядка кнопок
        short_id = f"c{i}"
        category_map_for_callback[short_id] = cat_name
        callback_data = f"{CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT}{short_id}"
        if len(callback_data.encode('utf-8')) > 64: # Проверка длины callback_data
             logger.error(f"Сгенерированный callback_data '{callback_data}' для категории '{cat_name}' слишком длинный! Пропуск кнопки.")
             continue
        keyboard.append([InlineKeyboardButton(cat_name, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("🎲 Случайные категории", callback_data=CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY)])
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Сохраняем временное отображение в chat_data
    chat_data_key = f"quiz10_cat_map_{chat_id_str}"
    context.chat_data[chat_data_key] = category_map_for_callback
    logger.debug(f"Временная карта категорий сохранена в chat_data (ключ: {chat_data_key}) для чата {chat_id_str}.")

    reply_text_to_send = 'Выберите категорию для немедленного старта /quiz10:'
    logger.debug(f"Attempting to send category selection for /quiz10 to {chat_id_str}. Text: '{reply_text_to_send}'")
    await update.message.reply_text(reply_text_to_send, reply_markup=reply_markup)


async def handle_quiz10_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        logger.error("handle_quiz10_category_selection: query is None.")
        return

    await query.answer() # Отвечаем на callback query, чтобы убрать "часики" у пользователя

    if not query.message or not query.message.chat or not query.from_user:
        logger.warning("handle_quiz10_category_selection: message, chat or user is None in query.")
        return

    chat_id_int = query.message.chat.id
    chat_id_str = str(chat_id_int)
    user_id = query.from_user.id
    
    chat_data_key = f"quiz10_cat_map_{chat_id_str}"
    category_map_for_callback: Dict[str, str] | None = context.chat_data.pop(chat_data_key, None)

    if category_map_for_callback is None: # Проверяем строго на None, т.к. пустой словарь тоже False
        logger.warning(f"Временная карта категорий не найдена в chat_data (ключ: {chat_data_key}) для чата {chat_id_str} при обработке callback. Ответ на старую кнопку или ошибка.")
        message_text_on_error = "Ошибка: Время выбора категории истекло или произошла внутренняя ошибка. Попробуйте начать новую викторину с /quiz10."
        try:
            await query.edit_message_text(text=message_text_on_error)
        except Exception as e_edit:
            logger.info(f"Не удалось отредактировать сообщение после ошибки выбора категории (map missing): {e_edit}. Отправка нового.")
            try:
                 await context.bot.send_message(chat_id=chat_id_int, text=message_text_on_error)
            except Exception as e_send:
                 logger.error(f"Не удалось отправить новое сообщение после неудачного редактирования (map missing): {e_send}")
        return

    logger.debug(f"Временная карта категорий (ключ: {chat_data_key}) удалена из chat_data для чата {chat_id_str} после получения callback.")

    selected_category_name: str | None = None
    callback_data = query.data
    message_text_after_selection = ""

    if callback_data == CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY:
        selected_category_name = None # Сигнал для _initiate_quiz10_session
        message_text_after_selection = "Выбран случайный набор категорий. Начинаем /quiz10..."
    elif callback_data and callback_data.startswith(CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT):
        short_id = callback_data[len(CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT):]
        selected_category_name = category_map_for_callback.get(short_id)
        if selected_category_name:
             message_text_after_selection = f"Выбрана категория '{selected_category_name}'. Начинаем /quiz10..."
        else:
             logger.warning(f"Не удалось найти полное имя для короткого ID '{short_id}' в карте категорий для чата {chat_id_str}. Карта была: {category_map_for_callback}")
             message_text_after_selection = "Произошла ошибка при выборе категории (ID не найден в карте). Попробуйте снова /quiz10."
             # Не инициируем викторину, просто редактируем сообщение
             try:
                 await query.edit_message_text(text=message_text_after_selection)
             except Exception as e:
                 logger.info(f"Не удалось отредактировать сообщение после ошибки выбора категории (ID not in map): {e}")
                 await context.bot.send_message(chat_id=chat_id_int, text=message_text_after_selection)
             return # Завершаем обработку
    else:
        logger.warning(f"Неизвестные callback_data в handle_quiz10_category_selection: '{callback_data}'.")
        message_text_after_selection = "Произошла ошибка при выборе категории (неизвестный тип выбора). Попробуйте снова /quiz10."
        try:
            await query.edit_message_text(text=message_text_after_selection)
        except Exception as e:
             logger.info(f"Не удалось отредактировать сообщение после неизвестных callback_data: {e}")
             await context.bot.send_message(chat_id=chat_id_int, text=message_text_after_selection)
        return # Завершаем обработку

    # Отредактировать сообщение с кнопками
    logger.debug(f"Attempting to edit message after /quiz10 category selection in {chat_id_str}. New text: '{message_text_after_selection}'")
    try:
        await query.edit_message_text(text=message_text_after_selection)
    except Exception as e_edit_final:
        logger.info(f"Не удалось отредактировать сообщение с кнопками выбора категории (финальное): {e_edit_final}. Возможно, сообщение удалено.")
        # Если не удалось отредактировать, не страшно, главное - запустить сессию если надо

    # Запускаем сессию, если выбор был успешен (selected_category_name определено или это RANDOM)
    # Условие `message_text_after_selection.startswith("Выбрана категория")` или `message_text_after_selection.startswith("Выбран случайный")`
    # может быть использовано как прокси для успешного выбора.
    if "Начинаем /quiz10..." in message_text_after_selection:
         await _initiate_quiz10_session(context, chat_id_int, chat_id_str, user_id, selected_category_name)


async def quiz10notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user:
        logger.warning("quiz10notify_command: message, chat or user is None.")
        return

    chat_id_int = update.effective_chat.id
    chat_id_str = str(chat_id_int)
    user_id = update.effective_user.id
    reply_text_to_send = ""

    if state.current_quiz_session.get(chat_id_str):
        reply_text_to_send = "В этом чате уже идет игра /quiz10. Дождитесь ее окончания или используйте /stopquiz."
        logger.debug(f"Attempting to send message to {chat_id_str} (quiz10notify blocked by active session). Text: '{reply_text_to_send}'")
        await update.message.reply_text(reply_text_to_send)
        return
        
    if state.pending_scheduled_quizzes.get(chat_id_str):
        pending_info = state.pending_scheduled_quizzes[chat_id_str]
        scheduled_dt_utc = pending_info.get("scheduled_time")
        time_left_str = "скоро"
        if scheduled_dt_utc and isinstance(scheduled_dt_utc, datetime):
            now_utc = datetime.now(timezone.utc)
            if scheduled_dt_utc > now_utc:
                time_left = scheduled_dt_utc - now_utc
                time_left_str = f"примерно через {max(1, int(time_left.total_seconds() / 60))} мин."
            else: # Время уже прошло, но job еще не сработал/не удалил из pending
                time_left_str = "очень скоро (возможно, уже началась)"
        reply_text_to_send = f"В этом чате уже запланирована игра /quiz10notify (начнется {time_left_str}). Дождитесь ее начала или используйте /stopquiz для отмены."
        logger.debug(f"Attempting to send message to {chat_id_str} (quiz10notify blocked by existing pending). Text: '{reply_text_to_send}'")
        await update.message.reply_text(reply_text_to_send)
        return

    category_name_arg = " ".join(context.args) if context.args else None
    chosen_category_full_name: str | None = None # Будет None для случайных
    category_display_name = "случайным категориям" # Для сообщения пользователю

    if not state.quiz_data:
        reply_text_to_send = "Вопросы еще не загружены. Попробуйте /start позже."
        logger.debug(f"Attempting to send message to {chat_id_str} (quiz10notify, no questions loaded). Text: '{reply_text_to_send}'")
        await update.message.reply_text(reply_text_to_send)
        return

    if category_name_arg:
        # Ищем категорию без учета регистра для удобства пользователя
        found_cat_name = next((cat for cat in state.quiz_data if cat.lower() == category_name_arg.lower() and state.quiz_data[cat]), None)
        if found_cat_name:
            chosen_category_full_name = found_cat_name
            category_display_name = f"категории '{chosen_category_full_name}'"
        else:
            reply_text_to_send = f"Категория '{category_name_arg}' не найдена или пуста. Викторина будет запланирована по случайным категориям."
            logger.debug(f"Attempting to send message to {chat_id_str} (quiz10notify, category not found). Text: '{reply_text_to_send}'")
            await update.message.reply_text(reply_text_to_send)
            # Продолжаем со случайными категориями, chosen_category_full_name остается None

    # Если категория не была задана или не найдена, проверяем общую доступность вопросов
    if not chosen_category_full_name and category_name_arg: # Если была задана, но не найдена
        pass # Уже сообщили пользователю, chosen_category_full_name останется None -> случайные
    elif not chosen_category_full_name and not category_name_arg: # Не была задана -> случайные
         all_questions_flat = [q for q_list in state.quiz_data.values() for q in q_list]
         if not all_questions_flat:
             reply_text_to_send = "Нет доступных вопросов для викторины. Загрузите вопросы (админ)."
             logger.debug(f"Attempting to send message to {chat_id_str} (quiz10notify, no questions AT ALL). Text: '{reply_text_to_send}'")
             await update.message.reply_text(reply_text_to_send)
             return

    delay_seconds = QUIZ10_NOTIFY_DELAY_MINUTES * 60
    job_name = f"scheduled_quiz10_chat_{chat_id_str}" # Сделаем имя уникальным для чата

    job_context_data = {"chat_id_int": chat_id_int, "user_id": user_id, "category_full_name": chosen_category_full_name}

    if context.job_queue:
        # Удаляем предыдущие джобы с таким же именем для этого чата
        existing_jobs = context.job_queue.get_jobs_by_name(job_name)
        for old_job in existing_jobs:
            old_job.schedule_removal()
            logger.debug(f"Удален старый job для quiz10notify с именем '{old_job.name}' в чате {chat_id_str}.")

        context.job_queue.run_once(
            _start_scheduled_quiz10_job_callback,
            timedelta(seconds=delay_seconds),
            data=job_context_data,
            name=job_name
        )

        scheduled_time_utc = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        state.pending_scheduled_quizzes[chat_id_str] = {
            "job_name": job_name,
            "category_name": chosen_category_full_name, # Сохраняем полное имя или None
            "starter_user_id": str(user_id),
            "scheduled_time": scheduled_time_utc
        }

        reply_text_to_send = (
            f"🔔 Принято! Викторина /quiz10 по {category_display_name} начнется через {QUIZ10_NOTIFY_DELAY_MINUTES} мин.\n"
            "Чтобы отменить, используйте /stopquiz."
        )
        logger.debug(f"Attempting to send confirmation for /quiz10notify to {chat_id_str}. Text: '{reply_text_to_send}'")
        await update.message.reply_text(reply_text_to_send)
        logger.info(f"Запланирован /quiz10notify для чата {chat_id_str} по {category_display_name} через {QUIZ10_NOTIFY_DELAY_MINUTES} мин. Job: {job_name}")
    else:
        reply_text_to_send = "Ошибка: JobQueue не настроен. Уведомление не может быть установлено."
        logger.debug(f"Attempting to send error (JobQueue missing) for /quiz10notify to {chat_id_str}. Text: '{reply_text_to_send}'")
        await update.message.reply_text(reply_text_to_send)
        logger.error("JobQueue не доступен в quiz10notify_command.")


async def _start_scheduled_quiz10_job_callback(context: ContextTypes.DEFAULT_TYPE):
    if not context.job or not context.job.data:
        logger.error("_start_scheduled_quiz10_job_callback вызван без job data.")
        return

    job_data = context.job.data
    chat_id_int: int = job_data["chat_id_int"]
    chat_id_str = str(chat_id_int)
    user_id: int = job_data["user_id"]
    category_full_name: str | None = job_data.get("category_full_name") # Может быть None

    # Проверяем, не был ли этот pending quiz отменен
    pending_quiz_info = state.pending_scheduled_quizzes.get(chat_id_str)
    if not pending_quiz_info or pending_quiz_info.get("job_name") != context.job.name:
        logger.info(f"Запланированный quiz10 (job: {context.job.name}) для чата {chat_id_str} был отменен или заменен другим. Job завершен.")
        return

    # Удаляем из pending, так как сейчас будем запускать
    state.pending_scheduled_quizzes.pop(chat_id_str, None)
    logger.debug(f"Удалена запись из pending_scheduled_quizzes для чата {chat_id_str} при запуске job'а.")

    if state.current_quiz_session.get(chat_id_str):
        logger.warning(f"Попытка запустить запланированный quiz10 в чате {chat_id_str}, но там уже активна другая сессия /quiz10.")
        try:
            error_text = "Не удалось запустить запланированную викторину: в этом чате уже идет другая игра /quiz10."
            logger.debug(f"Attempting to send message to {chat_id_str} (_start_scheduled_quiz10_job_callback, session conflict). Text: '{error_text}'")
            await context.bot.send_message(chat_id=chat_id_int, text=error_text)
        except Exception as e_send:
             logger.error(f"Ошибка отправки сообщения о конфликте сессий в чат {chat_id_str}: {e_send}")
        return

    logger.info(f"Запускаем запланированный quiz10 для чата {chat_id_str}. Категория из job: {category_full_name if category_full_name else 'Случайные'}")
    await _initiate_quiz10_session(context, chat_id_int, chat_id_str, user_id, category_full_name)


async def stop_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user or not update.effective_chat:
        logger.warning("stop_quiz_command: message, user or chat is None.")
        return

    chat_id_int = update.effective_chat.id
    chat_id_str = str(chat_id_int)
    user_id_str = str(update.effective_user.id)
    reply_text_to_send = ""

    user_is_admin = False
    if update.effective_chat.type != "private":
        try:
            chat_member = await context.bot.get_chat_member(chat_id_str, user_id_str)
            if chat_member.status in [chat_member.ADMINISTRATOR, chat_member.CREATOR]:
                user_is_admin = True
        except Exception as e:
            logger.warning(f"Ошибка проверки статуса админа для {user_id_str} в {chat_id_str}: {e}")

    stopped_something = False

    # Остановка активной сессии /quiz10
    active_session = state.current_quiz_session.get(chat_id_str)
    if active_session:
        session_starter_id = active_session.get("starter_user_id")
        if user_is_admin or user_id_str == session_starter_id:
            logger.info(f"/stopquiz от {user_id_str} (admin: {user_is_admin}) в {chat_id_str}. Остановка активной сессии /quiz10, начатой {session_starter_id}.")
            
            # Пытаемся остановить текущий опрос сессии, если он есть
            current_poll_id_in_session = active_session.get("current_poll_id")
            if current_poll_id_in_session:
                poll_info = state.current_poll.get(current_poll_id_in_session)
                if poll_info and poll_info.get("message_id"):
                    try:
                        await context.bot.stop_poll(chat_id_str, poll_info["message_id"])
                        logger.debug(f"Текущий опрос {current_poll_id_in_session} активной сессии /quiz10 остановлен.")
                    except Exception as e_stop_poll:
                        logger.warning(f"Ошибка остановки опроса {current_poll_id_in_session} через /stopquiz: {e_stop_poll}")
            
            await show_quiz_session_results(context, chat_id_str, error_occurred=True) # Показываем результаты досрочно
            reply_text_to_send = "Активная викторина /quiz10 остановлена."
            logger.debug(f"Attempting to send message to {chat_id_str} (active /quiz10 stopped). Text: '{reply_text_to_send}'")
            await update.message.reply_text(reply_text_to_send)
            stopped_something = True
        else:
            reply_text_to_send = "Только админ или тот, кто начал активную /quiz10, может ее остановить."
            logger.debug(f"Attempting to send restriction message to {chat_id_str} (stop active /quiz10). Text: '{reply_text_to_send}'")
            await update.message.reply_text(reply_text_to_send)
            return # Выходим, если нет прав на остановку активной, не проверяем pending

    # Отмена запланированной /quiz10notify
    pending_quiz = state.pending_scheduled_quizzes.get(chat_id_str)
    if pending_quiz:
        pending_starter_id = pending_quiz.get("starter_user_id")
        if user_is_admin or user_id_str == pending_starter_id:
            job_name = pending_quiz.get("job_name")
            if job_name and context.job_queue:
                jobs = context.job_queue.get_jobs_by_name(job_name)
                removed_count = 0
                for job in jobs:
                    job.schedule_removal()
                    removed_count +=1
                if removed_count > 0:
                    logger.info(f"Отменен(о) {removed_count} запланированный(х) quiz10notify (job name pattern: {job_name}) в чате {chat_id_str} командой /stopquiz от {user_id_str} (admin: {user_is_admin}).")

            state.pending_scheduled_quizzes.pop(chat_id_str, None)
            reply_text_to_send = "Запланированная викторина /quiz10notify отменена."
            logger.debug(f"Attempting to send message to {chat_id_str} (pending /quiz10notify cancelled). Text: '{reply_text_to_send}'")
            await update.message.reply_text(reply_text_to_send)
            stopped_something = True
        else:
            # Это сообщение будет отправлено, только если не было активной сессии ИЛИ не было прав ее остановить,
            # И сейчас нет прав остановить запланированную.
            if not active_session: # Если не было активной сессии (или ее не смогли остановить выше)
                 reply_text_to_send = "Только админ или тот, кто запланировал /quiz10notify, может ее отменить."
                 logger.debug(f"Attempting to send restriction message to {chat_id_str} (stop pending /quiz10notify). Text: '{reply_text_to_send}'")
                 await update.message.reply_text(reply_text_to_send)
            return

    if not stopped_something:
        reply_text_to_send = "В этом чате нет активных или запланированных викторин /quiz10 для остановки/отмены."
        logger.debug(f"Attempting to send message to {chat_id_str} (nothing to stop for /quiz10). Text: '{reply_text_to_send}'")
        await update.message.reply_text(reply_text_to_send)