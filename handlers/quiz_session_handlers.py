# handlers/quiz_session_handlers.py
import random
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# Импорты из других модулей проекта
from config import (logger, DEFAULT_POLL_OPEN_PERIOD, NUMBER_OF_QUESTIONS_IN_SESSION,
                    CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT, # Используем новый короткий префикс
                    CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY, # Этот уже достаточно короткий
                    QUIZ10_NOTIFY_DELAY_MINUTES)
import state
from quiz_logic import (get_random_questions, get_random_questions_from_all,
                        send_next_question_in_session,
                        show_quiz_session_results)

# --- Вспомогательная функция для старта сессии (используется quiz10 и quiz10notify) ---
async def _initiate_quiz10_session(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    chat_id_str: str,
    user_id: int,
    category_name: str | None # Full category name is expected here
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
        # No questions found, need to send a message to the chat
        try:
            await context.bot.send_message(chat_id, f"Не найдено вопросов для /quiz10 ({intro_message_part}).")
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения о пустой категории в чат {chat_id}: {e}")
        return

    start_message_text = f"🚀 Начинаем викторину из {actual_number_of_questions} вопросов ({intro_message_part})! Приготовьтесь!"
    if actual_number_of_questions < NUMBER_OF_QUESTIONS_IN_SESSION:
        start_message_text += f" (Меньше {NUMBER_OF_QUESTIONS_IN_SESSION} запрошено, доступно {actual_number_of_questions})" # Adjusted wording

    try:
        intro_message = await context.bot.send_message(chat_id, start_message_text)
    except Exception as e:
         logger.error(f"Ошибка отправки вводного сообщения сессии в чат {chat_id}: {e}", exc_info=True)
         # If we can't send the intro message, maybe we can't run the quiz? Let's log and return.
         return


    state.current_quiz_session[chat_id_str] = {
        "questions": questions_for_session,
        "session_scores": {},
        "current_index": 0,
        "actual_num_questions": actual_number_of_questions,
        "message_id_intro": intro_message.message_id if intro_message else None, # Handle case where intro_message failed
        "starter_user_id": str(user_id),
        "current_poll_id": None,
        "next_question_job": None,
        "category_used": category_name # Сохраняем использованную категорию (полное имя)
    }
    logger.info(f"/quiz10 на {actual_number_of_questions} вопросов ({intro_message_part}) запущена в чате {chat_id_str} пользователем {user_id}.")
    await send_next_question_in_session(context, chat_id_str)


async def quiz10_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        logger.warning("quiz10_command: message or effective_chat is None.")
        return

    chat_id_str = str(update.effective_chat.id)
    chat_id = update.effective_chat.id # Need int chat_id for context.chat_data

    if state.current_quiz_session.get(chat_id_str):
        await update.message.reply_text("В этом чате уже идет игра /quiz10. Дождитесь ее окончания или используйте /stopquiz.") # type: ignore
        return
    if state.pending_scheduled_quizzes.get(chat_id_str):
        await update.message.reply_text(f"В этом чате уже запланирована игра /quiz10notify. Дождитесь ее начала или используйте /stopquiz.") # type: ignore
        return

    if not state.quiz_data:
        await update.message.reply_text("Вопросы еще не загружены. Попробуйте /start позже.") # type: ignore
        return

    # Получаем список доступных категорий, в которых есть вопросы
    available_categories = [cat_name for cat_name, q_list in state.quiz_data.items() if isinstance(q_list, list) and q_list]
    if not available_categories:
        await update.message.reply_text("Нет доступных категорий с вопросами для /quiz10.") # type: ignore
        return

    keyboard = []
    # Создаем временное отображение коротких ID на полные имена категорий
    # Используем context.chat_data для временного хранения этого для данного чата
    # Ключ map'а привяжем к chat_id.
    category_map_for_callback: Dict[str, str] = {}
    for i, cat_name in enumerate(available_categories):
        short_id = f"c{i}" # Простой числовой идентификатор с префиксом
        category_map_for_callback[short_id] = cat_name
        # Используем короткий ID в callback_data с новым префиксом
        callback_data = f"{CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT}{short_id}"
        # Проверяем, что callback_data не превышает 64 байта (хотя с коротким ID это маловероятно)
        if len(callback_data.encode('utf-8')) > 64:
             logger.error(f"Сгенерированный callback_data {callback_data} для категории {cat_name} слишком длинный!")
             # Можно пропустить кнопку или использовать более короткий ID генератор
             continue # Пропускаем эту кнопку, если она все равно слишком длинная

        keyboard.append([InlineKeyboardButton(cat_name, callback_data=callback_data)])

    # Добавляем кнопку для случайных категорий (callback_data уже короткий)
    keyboard.append([InlineKeyboardButton("🎲 Случайные категории", callback_data=CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY)])

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Сохраняем временное отображение в chat_data
    # Ключ: 'quiz10_cat_map_[chat_id_str]'
    context.chat_data[f"quiz10_cat_map_{chat_id_str}"] = category_map_for_callback
    logger.debug(f"Временная карта категорий сохранена в chat_data для чата {chat_id_str}.")

    await update.message.reply_text('Выберите категорию для немедленного старта /quiz10:', reply_markup=reply_markup) # type: ignore


async def handle_quiz10_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        logger.error("handle_quiz10_category_selection: query is None, что не должно происходить.")
        return

    await query.answer()

    if not query.message or not query.message.chat or not query.from_user:
        logger.warning("handle_quiz10_category_selection: message, chat or user is None in query.")
        return

    chat_id = query.message.chat.id
    chat_id_str = str(chat_id)
    user_id = query.from_user.id

    # Пытаемся получить временное отображение коротких ID на полные имена и сразу удаляем его
    category_map_for_callback: Dict[str, str] | None = context.chat_data.pop(f"quiz10_cat_map_{chat_id_str}", None)
    if category_map_for_callback:
        logger.debug(f"Временная карта категорий удалена из chat_data для чата {chat_id_str} после получения callback.")
    else:
        logger.warning(f"Временная карта категорий не найдена в chat_data для чата {chat_id_str} при обработке callback. Вероятно, ответ на старую кнопку или ошибка.")
        # Если map не найден, скорее всего, сообщение с кнопками устарело.
        # Просто редактируем сообщение, чтобы убрать старые кнопки и сообщаем об ошибке.
        message_text = "Ошибка: Время выбора категории истекло или произошла внутренняя ошибка. Попробуйте начать новую викторину с /quiz10."
        try:
            await query.edit_message_text(text=message_text)
        except Exception as e:
            logger.info(f"Не удалось отредактировать сообщение после ошибки выбора категории (map missing): {e}")
            # Если не удалось отредактировать, отправляем новое сообщение об ошибке
            try:
                 await context.bot.send_message(chat_id, message_text)
            except Exception as e_send:
                 logger.error(f"Не удалось отправить новое сообщение после неудачного редактирования: {e_send}")
        return # Завершаем обработку, викторина не будет начата


    selected_category_name = None
    callback_data = query.data

    if callback_data == CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY:
        selected_category_name = None # Random category will be handled by _initiate_quiz10_session
        message_text = "Выбран случайный набор категорий. Начинаем /quiz10..."
    elif callback_data and callback_data.startswith(CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT):
        # Извлекаем короткий ID из callback_data
        short_id = callback_data[len(CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT):]
        # Ищем полное имя в map
        selected_category_name = category_map_for_callback.get(short_id)
        if selected_category_name:
             message_text = f"Выбрана категория '{selected_category_name}'. Начинаем /quiz10..."
        else:
             logger.warning(f"Не удалось найти полное имя для короткого ID '{short_id}' в map для чата {chat_id_str}. Map был получен, но ID не найден.")
             message_text = "Произошла ошибка при выборе категории. Попробуйте снова."
             # Don't initiate quiz, return
             try:
                 await query.edit_message_text(text=message_text)
             except Exception as e:
                 logger.info(f"Не удалось отредактировать сообщение после ошибки выбора категории (ID not in map): {e}")
                 await context.bot.send_message(chat_id, message_text)
             return
    else:
        # Эта ветка должна быть достигнута, только если pattern в bot.py изменен некорректно
        logger.warning(f"Неизвестные callback_data в handle_quiz10_category_selection: {callback_data}. Callback data не начинается с ожидаемого префикса или не является 'случайным'.")
        message_text = "Произошла ошибка при выборе категории. Неизвестный тип выбора."
        # Don't initiate quiz, return
        try:
            await query.edit_message_text(text=message_text)
        except Exception as e:
             logger.info(f"Не удалось отредактировать сообщение после неизвестных callback_data: {e}")
             await context.bot.send_message(chat_id, message_text)
        return

    # Отредактировать сообщение с кнопками, чтобы убрать их после выбора
    try:
        # Используем message_text, определенный выше, чтобы показать, что выбрано
        await query.edit_message_text(text=message_text)
    except Exception as e:
        logger.info(f"Не удалось отредактировать сообщение с кнопками выбора категории: {e}")
        # Если не удалось отредактировать (например, сообщение слишком старое или уже удалено), отправляем новое.
        try:
            await context.bot.send_message(chat_id, message_text)
        except Exception as e_send:
            logger.error(f"Не удалось отправить новое сообщение после неудачного редактирования: {e_send}")


    # Если выбранная категория была найдена (selected_category_name не None) ИЛИ был выбран случайный набор (callback_data == CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY)
    # Проверка 'selected_category_name is not None' покрывает случаи успешного выбора категории по ID.
    # Проверка 'callback_data == CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY' покрывает случай "Случайные категории".
    # Если выбран_случайный_набор (второе условие), то selected_category_name равно None, что корректно для _initiate_quiz10_session.
    if selected_category_name is not None or callback_data == CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY:
         # Важно: передаем полное имя категории (или None для случайных) в функцию инициации сессии
         await _initiate_quiz10_session(context, chat_id, chat_id_str, user_id, selected_category_name)


async def quiz10notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (остается без изменений, так как не использует callback_data для выбора категории)
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

    if not state.quiz_data:
        await update.message.reply_text("Вопросы еще не загружены. Попробуйте /start позже.") # type: ignore
        return

    if category_name_arg:
        if category_name_arg in state.quiz_data and state.quiz_data[category_name_arg]:
            chosen_category_name = category_name_arg
            category_display_name = f"категории '{chosen_category_name}'"
        else:
            await update.message.reply_text(f"Категория '{category_name_arg}' не найдена или пуста. Викторина будет по случайным категориям.") # type: ignore

    # Если категория не была задана или не найдена, проверяем общую доступность вопросов
    if not chosen_category_name:
         all_questions_flat = [q for questions_in_category in state.quiz_data.values() if isinstance(questions_in_category, list) for q in questions_in_category]
         if not all_questions_flat:
             await update.message.reply_text("Нет доступных вопросов для викторины. Загрузите вопросы.") # type: ignore
             return


    delay_seconds = QUIZ10_NOTIFY_DELAY_MINUTES * 60
    job_name = f"scheduled_quiz10_{chat_id_str}"

    # Для job сохраняем либо полное имя категории, либо строку "RANDOM"
    category_for_job = chosen_category_name if chosen_category_name else "RANDOM"

    job_context_data = {"chat_id": chat_id, "user_id": user_id, "category_name_in_job": category_for_job} # Переименовал ключ для ясности

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
            "category_name": chosen_category_name, # Сохраняем полное имя или None
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
    # Извлекаем имя категории из данных job'а
    category_name_in_job: str | None = job_data.get("category_name_in_job")

    if chat_id_str not in state.pending_scheduled_quizzes:
        logger.info(f"Запланированный quiz10 для чата {chat_id_str} был отменен или уже запущен. Job завершен.")
        return

    if state.current_quiz_session.get(chat_id_str):
        logger.warning(f"Попытка запустить запланированный quiz10 в чате {chat_id_str}, но там уже активна другая сессия.")
        state.pending_scheduled_quizzes.pop(chat_id_str, None)
        # Можно отправить сообщение об ошибке, но это job, нет связанного message для reply
        try:
            await context.bot.send_message(chat_id, "Не удалось запустить запланированную викторину: в этом чате уже идет другая игра.")
        except Exception as e:
             logger.error(f"Ошибка отправки сообщения о конфликте сессий в чат {chat_id}: {e}")
        return

    pending_info = state.pending_scheduled_quizzes.pop(chat_id_str, None)
    if pending_info:
         logger.info(f"Запускаем запланированный quiz10 для чата {chat_id_str}. Категория из job: {category_name_in_job}")

    actual_category_name = None
    if category_name_in_job != "RANDOM":
        actual_category_name = category_name_in_job # Передаем полное имя категории из job data

    await _initiate_quiz10_session(context, chat_id, chat_id_str, user_id, actual_category_name)


async def stop_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (остается без изменений)
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
                        # Пытаемся остановить опросное сообщение
                        await context.bot.stop_poll(chat_id_str, poll_message_id) # type: ignore
                    except Exception as e:
                        logger.error(f"Ошибка остановки опроса {current_poll_id_in_session} через /stopquiz: {e}")

            # Показываем результаты досрочно и очищаем сессию
            await show_quiz_session_results(context, chat_id_str, error_occurred=True)
            await update.message.reply_text("Активная викторина /quiz10 остановлена.") # type: ignore
            stopped_something = True
        else:
            await update.message.reply_text("Только админ или тот, кто начал активную /quiz10, может ее остановить.") # type: ignore
            return # Выходим, чтобы не проверять запланированную, если нет прав на остановку активной

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
            # Если активная сессия не была остановлена (т.е. предыдущий if не сработал)
            if not active_session:
                 await update.message.reply_text("Только админ или тот, кто запланировал /quiz10notify, может ее отменить.") # type: ignore
            # Если активная сессия была, но пользователь не имел прав на ее остановку,
            # и у него тоже нет прав на отмену запланированной, сообщение уже было отправлено выше.
            return # Выходим после попытки отмены запланированной

    if not stopped_something:
        await update.message.reply_text("В этом чате нет активных или запланированных викторин /quiz10 для остановки/отмены.") # type: ignore

