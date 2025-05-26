# handlers/quiz_session_handlers.py
import asyncio
import random
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, JobQueue
from telegram.constants import ParseMode, ChatMemberStatus

from config import (logger, DEFAULT_POLL_OPEN_PERIOD, NUMBER_OF_QUESTIONS_IN_SESSION,
                    CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT, CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY,
                    JOB_GRACE_PERIOD, QUIZ10_NOTIFY_DELAY_MINUTES)
import state
from quiz_logic import prepare_poll_options, get_random_questions
from utils import pluralize_points

# --- Вспомогательные функции ---

async def _is_user_admin_or_creator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет, является ли пользователь администратором или создателем чата."""
    if not update.effective_chat or not update.effective_user:
        return False
    if update.effective_chat.type == 'private': # В личных сообщениях пользователь всегда "админ" своих действий
        return True
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception as e:
        logger.warning(f"Ошибка проверки статуса администратора для {update.effective_user.id} в {update.effective_chat.id}: {e}")
        return False


async def send_next_question_job(context: ContextTypes.DEFAULT_TYPE):
    """Отправляет следующий вопрос викторины или завершает ее."""
    job = context.job
    if not job or not job.data:
        logger.error("send_next_question_job: Job data is missing.")
        return

    chat_id_str = job.data.get("chat_id_str")
    session = state.current_quiz_session.get(chat_id_str)

    if not session:
        logger.info(f"Сессия викторины для чата {chat_id_str} не найдена или уже завершена. Остановка job.")
        return # Сессия могла быть завершена /stopquiz

    current_question_index = session["current_question_index"]

    if current_question_index >= len(session["questions"]):
        # Все вопросы заданы, завершаем викторину
        await context.bot.send_message(chat_id_str, "🏁 Викторина завершена! Спасибо за участие!")
        state.current_quiz_session.pop(chat_id_str, None)
        logger.info(f"Викторина /quiz10 завершена для чата {chat_id_str}.")
        return

    question_data = session["questions"][current_question_index]
    _, poll_options, poll_correct_option_id, _ = prepare_poll_options(question_data)

    question_text_for_poll = question_data['question']
    question_title = f"Вопрос {current_question_index + 1}/{len(session['questions'])}"
    if original_cat := question_data.get("original_category"):
        question_title += f" (Категория: {original_cat})"

    full_question_text = f"{question_title}\n\n{question_text_for_poll}"

    MAX_POLL_QUESTION_LENGTH = 300 # Telegram API limit
    if len(full_question_text) > MAX_POLL_QUESTION_LENGTH:
        full_question_text = full_question_text[:MAX_POLL_QUESTION_LENGTH-3] + "..."
        logger.warning(f"Текст вопроса для poll в {chat_id_str} усечен до {MAX_POLL_QUESTION_LENGTH} символов.")

    try:
        sent_poll_msg = await context.bot.send_poll(
            chat_id=chat_id_str,
            question=full_question_text,
            options=poll_options,
            type='quiz',
            correct_option_id=poll_correct_option_id,
            open_period=session["open_period"],
            is_anonymous=False, # Викторины не должны быть анонимными для подсчета очков
            explanation=question_data.get('comment', ''),
            explanation_parse_mode=ParseMode.MARKDOWN_V2 if question_data.get('comment') else None
        )
        state.current_poll[sent_poll_msg.poll.id] = {
            "chat_id": chat_id_str,
            "message_id": sent_poll_msg.message_id,
            "correct_index": poll_correct_option_id,
            "quiz_session": True, # Указываем, что это часть сессии /quiz10
            "question_session_index": current_question_index,
            "question_details": question_data,
            "open_timestamp": sent_poll_msg.date.timestamp()
        }
        logger.info(f"Отправлен вопрос {current_question_index + 1} (Poll ID: {sent_poll_msg.poll.id}) для /quiz10 в чат {chat_id_str}.")
    except Exception as e:
        logger.error(f"Ошибка отправки вопроса {current_question_index + 1} в чат {chat_id_str}: {e}", exc_info=True)
        # Попытаться отправить сообщение об ошибке в чат и остановить сессию
        try:
            await context.bot.send_message(chat_id_str, "Произошла ошибка при отправке вопроса. Викторина прервана.")
        except Exception as send_err:
            logger.error(f"Не удалось отправить сообщение об ошибке в чат {chat_id_str}: {send_err}")
        state.current_quiz_session.pop(chat_id_str, None) # Прерываем сессию
        return


    session["current_question_index"] += 1 # Переходим к следующему вопросу для следующего job

    # Планируем следующий job (отправка следующего вопроса или завершение)
    # Задержка = время на ответ + небольшой буфер
    delay_seconds = session["open_period"] + JOB_GRACE_PERIOD
    job_queue: JobQueue | None = context.application.job_queue
    if job_queue:
        # Имя джоба должно быть уникальным для каждой сессии в чате
        next_job_name = f"quiz10_nextq_{chat_id_str}"
        # Удаляем старый job с таким именем, если он вдруг остался (например, после перезапуска)
        # Это важно, чтобы не было дублирующих джобов для одного чата
        existing_jobs = job_queue.get_jobs_by_name(next_job_name)
        for old_job in existing_jobs:
            old_job.schedule_removal()
            logger.debug(f"Удален существующий job '{next_job_name}' перед планированием нового для {chat_id_str}.")

        job_queue.run_once(
            send_next_question_job,
            when=timedelta(seconds=delay_seconds),
            data={"chat_id_str": chat_id_str}, # Передаем chat_id_str
            name=next_job_name # Даем имя джобу для возможности управления
        )
        session["next_job_name"] = next_job_name # Сохраняем имя джоба в сессии
        logger.debug(f"Запланирован следующий вопрос/завершение для /quiz10 в чате {chat_id_str} (job: {next_job_name}).")
    else:
        logger.error(f"JobQueue не доступен. Не удалось запланировать следующий вопрос для {chat_id_str}.")
        # В этом случае викторина просто остановится после текущего вопроса


# --- Обработчики команд ---

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет один случайный вопрос-викторину."""
    if not update.message or not update.effective_chat: return

    chat_id = update.effective_chat.id
    chat_id_str = str(chat_id)

    if state.current_quiz_session.get(chat_id_str):
        await update.message.reply_text("В этом чате уже идет викторина /quiz10. Дождитесь ее завершения или остановите командой /stopquiz.")
        return
    if state.active_daily_quizzes.get(chat_id_str):
        await update.message.reply_text("В этом чате идет ежедневная викторина. Дождитесь ее завершения или остановите командой /stopquiz.")
        return
    if state.pending_scheduled_quizzes.get(chat_id_str):
        await update.message.reply_text("В этом чате уже запланирована викторина /quiz10notify. Дождитесь ее начала или отмените /stopquiz.")
        return


    question = get_random_questions(1)
    if not question:
        await update.message.reply_text("К сожалению, вопросы закончились или не загружены. Попробуйте позже.")
        return

    q_data = question[0]
    _, poll_options, poll_correct_option_id, _ = prepare_poll_options(q_data)

    question_text_for_poll = q_data['question']
    question_title = "Случайный вопрос!"
    if original_cat := q_data.get("original_category"):
        question_title += f" (Категория: {original_cat})"

    full_question_text = f"{question_title}\n\n{question_text_for_poll}"

    MAX_POLL_QUESTION_LENGTH = 300 # Telegram API limit
    if len(full_question_text) > MAX_POLL_QUESTION_LENGTH:
        full_question_text = full_question_text[:MAX_POLL_QUESTION_LENGTH-3] + "..."
        logger.warning(f"Текст вопроса для poll (/quiz) в {chat_id_str} усечен до {MAX_POLL_QUESTION_LENGTH} символов.")


    try:
        sent_poll_msg = await context.bot.send_poll(
            chat_id=chat_id,
            question=full_question_text,
            options=poll_options,
            type='quiz',
            correct_option_id=poll_correct_option_id,
            open_period=DEFAULT_POLL_OPEN_PERIOD,
            is_anonymous=False,
            explanation=q_data.get('comment', ''),
            explanation_parse_mode=ParseMode.MARKDOWN_V2 if q_data.get('comment') else None
        )
        state.current_poll[sent_poll_msg.poll.id] = {
            "chat_id": str(chat_id),
            "message_id": sent_poll_msg.message_id,
            "correct_index": poll_correct_option_id,
            "quiz_session": False, # Это не часть сессии /quiz10
            "daily_quiz": False,   # Это не часть ежедневной викторины
            "question_details": q_data,
            "open_timestamp": sent_poll_msg.date.timestamp()
        }
        logger.info(f"Отправлен вопрос /quiz (Poll ID: {sent_poll_msg.poll.id}) в чат {chat_id}.")
    except Exception as e:
        logger.error(f"Ошибка отправки вопроса /quiz в чат {chat_id}: {e}", exc_info=True)
        await update.message.reply_text("Произошла ошибка при отправке вопроса.")


async def quiz10_command(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str | None = None, initiated_by_notify: bool = False):
    """Начинает сессию викторины из 10 вопросов."""
    if not update.message and not initiated_by_notify: # Если не от команды и не от notify
        logger.warning("quiz10_command вызван без update.message и не из notify_job")
        return
    
    # Определяем chat_id и сообщение для ответа
    # Если команда вызвана из notify_job, update.message может не быть, используем chat_id из job.data
    chat_id = None
    reply_to_message = update.message if update.message else None

    if initiated_by_notify and context.job and context.job.data:
        chat_id = context.job.data.get("chat_id")
        # Для сообщений от notify не нужен reply_to_message, т.к. они сами по себе
    elif update.effective_chat:
        chat_id = update.effective_chat.id
    
    if not chat_id:
        logger.error("Не удалось определить chat_id для quiz10_command")
        if reply_to_message: await reply_to_message.reply_text("Не удалось начать викторину: ошибка с ID чата.")
        return

    chat_id_str = str(chat_id)

    # Проверка на существующую сессию /quiz10 или /quiz10notify
    if state.current_quiz_session.get(chat_id_str) and not initiated_by_notify: # Если сессия уже есть и это не запуск от notify
        await reply_to_message.reply_text("Викторина /quiz10 уже идет в этом чате. Дождитесь ее завершения или остановите командой /stopquiz.")
        return
    if state.pending_scheduled_quizzes.get(chat_id_str) and not initiated_by_notify: # Если запланирована и это не запуск от notify
        pending_details = state.pending_scheduled_quizzes[chat_id_str]
        start_dt = datetime.fromtimestamp(pending_details['start_timestamp'])
        start_time_str = start_dt.strftime("%H:%M:%S")
        await reply_to_message.reply_text(f"Викторина /quiz10 уже запланирована на {start_time_str} МСК. "
                                          "Дождитесь ее начала или отмените уведомление командой /stopquiz.")
        return
    if state.active_daily_quizzes.get(chat_id_str):
        msg = "В этом чате идет ежедневная викторина. Дождитесь ее завершения или остановите командой /stopquiz."
        if reply_to_message: await reply_to_message.reply_text(msg)
        else: await context.bot.send_message(chat_id, msg)
        return

    # Если это запуск от notify, удаляем из pending
    if initiated_by_notify:
        state.pending_scheduled_quizzes.pop(chat_id_str, None)
        # Удаляем job самого уведомления, он уже выполнился
        if context.job and context.job.name:
            job_queue: JobQueue | None = context.application.job_queue
            if job_queue:
                current_jobs = job_queue.get_jobs_by_name(context.job.name)
                for j in current_jobs: j.schedule_removal()
        logger.info(f"Запускается запланированная викторина /quiz10notify для чата {chat_id_str}.")


    open_period_args = [arg for arg in (context.args or []) if arg.isdigit()]
    open_period = int(open_period_args[0]) if open_period_args else DEFAULT_POLL_OPEN_PERIOD
    if not (10 <= open_period <= 600): # Ограничение Telegram
        open_period = DEFAULT_POLL_OPEN_PERIOD
        msg = f"Время на ответ должно быть от 10 до 600 секунд. Установлено значение по умолчанию: {DEFAULT_POLL_OPEN_PERIOD} сек."
        if reply_to_message: await reply_to_message.reply_text(msg)
        # Если это от notify, такое сообщение не нужно, т.к. время устанавливается при /quiz10notify

    category_to_use = category # Если категория передана из callback_handler
    if not category_to_use and context.args:
        # Ищем текстовый аргумент, который не является числом (временем ответа)
        category_args = [arg for arg in context.args if not arg.isdigit()]
        if category_args:
            category_to_use = " ".join(category_args) # Объединяем, если название категории из нескольких слов

    questions = get_random_questions(NUMBER_OF_QUESTIONS_IN_SESSION, category_name=category_to_use)

    if not questions:
        msg = f"Не найдено достаточного количества вопросов ({NUMBER_OF_QUESTIONS_IN_SESSION}) "
        if category_to_use and category_to_use != "Случайная":
            msg += f"в категории '{category_to_use}'."
        else:
            msg += "по случайным категориям."
        msg += " Викторина не будет начата."

        if reply_to_message: await reply_to_message.reply_text(msg)
        else: await context.bot.send_message(chat_id, msg)
        return

    # Сохраняем состояние сессии
    state.current_quiz_session[chat_id_str] = {
        "questions": questions,
        "current_question_index": 0,
        "open_period": open_period,
        "category_name": category_to_use or "Случайная",
        "next_job_name": None # Будет установлено при планировании первого send_next_question_job
    }

    category_name_display = category_to_use if category_to_use and category_to_use != "Случайная" else "случайным категориям"
    start_message_text = (
        f"🚀 Начинаем викторину из {NUMBER_OF_QUESTIONS_IN_SESSION} вопросов по {category_name_display}! \n"
        f"Время на ответ: {open_period} секунд."
    )
    if reply_to_message: await reply_to_message.reply_text(start_message_text)
    else: await context.bot.send_message(chat_id, start_message_text)

    logger.info(f"Начата викторина /quiz10 для чата {chat_id_str}. Категория: {category_name_display}, время: {open_period} сек.")

    # Запускаем отправку первого вопроса немедленно (или с очень малой задержкой)
    job_queue: JobQueue | None = context.application.job_queue
    if job_queue:
        first_job_name = f"quiz10_nextq_{chat_id_str}" # Такое же имя, как для последующих
        # Удаляем предыдущий job с таким именем, если он есть (на всякий случай)
        existing_jobs = job_queue.get_jobs_by_name(first_job_name)
        for old_job in existing_jobs: old_job.schedule_removal()

        job_queue.run_once(
            send_next_question_job,
            when=timedelta(seconds=1), # Небольшая задержка, чтобы сообщение о старте успело отправиться
            data={"chat_id_str": chat_id_str},
            name=first_job_name
        )
        state.current_quiz_session[chat_id_str]["next_job_name"] = first_job_name
        logger.debug(f"Запланирован первый вопрос для /quiz10 в чате {chat_id_str} (job: {first_job_name}).")

    else:
        logger.error(f"JobQueue не доступен. Не удалось запланировать первый вопрос для {chat_id_str}.")
        await context.bot.send_message(chat_id_str, "Ошибка: не удалось запустить очередь вопросов. Викторина прервана.")
        state.current_quiz_session.pop(chat_id_str, None)


async def stop_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Останавливает текущую викторину /quiz10 или отменяет запланированную /quiz10notify."""
    if not update.message or not update.effective_chat: return
    chat_id_str = str(update.effective_chat.id)

    # Проверка прав администратора, если это не личный чат
    if update.effective_chat.type != 'private':
        is_admin = await _is_user_admin_or_creator(update, context)
        if not is_admin:
            await update.message.reply_text("Только администраторы могут останавливать викторины в этом чате.")
            return

    stopped_something = False
    job_queue: JobQueue | None = context.application.job_queue

    # 1. Остановка активной сессии /quiz10
    active_session = state.current_quiz_session.get(chat_id_str)
    if active_session:
        next_job_name = active_session.get("next_job_name")
        if next_job_name and job_queue:
            jobs_to_remove = job_queue.get_jobs_by_name(next_job_name)
            for job in jobs_to_remove:
                job.schedule_removal()
            logger.info(f"Удален job '{next_job_name}' для остановки /quiz10 в чате {chat_id_str}.")
        state.current_quiz_session.pop(chat_id_str, None)
        await update.message.reply_text("Викторина /quiz10 остановлена.")
        logger.info(f"Викторина /quiz10 остановлена в чате {chat_id_str} по команде /stopquiz.")
        stopped_something = True

    # 2. Отмена запланированной /quiz10notify
    pending_quiz = state.pending_scheduled_quizzes.get(chat_id_str)
    if pending_quiz:
        notify_job_name = pending_quiz.get("notify_job_name")
        quiz_start_job_name = pending_quiz.get("quiz_start_job_name")

        if notify_job_name and job_queue:
            jobs_to_remove = job_queue.get_jobs_by_name(notify_job_name)
            for job in jobs_to_remove: job.schedule_removal()
            logger.info(f"Удален notify_job '{notify_job_name}' для отмены /quiz10notify в чате {chat_id_str}.")

        if quiz_start_job_name and job_queue:
            jobs_to_remove = job_queue.get_jobs_by_name(quiz_start_job_name)
            for job in jobs_to_remove: job.schedule_removal()
            logger.info(f"Удален quiz_start_job '{quiz_start_job_name}' для отмены /quiz10notify в чате {chat_id_str}.")

        state.pending_scheduled_quizzes.pop(chat_id_str, None)
        await update.message.reply_text("Запланированная викторина (/quiz10notify) отменена.")
        logger.info(f"Запланированная викторина /quiz10notify отменена в чате {chat_id_str} по команде /stopquiz.")
        stopped_something = True
        
    # 3. Остановка активной ежедневной викторины
    active_daily_quiz = state.active_daily_quizzes.get(chat_id_str)
    if active_daily_quiz:
        next_q_job_name = active_daily_quiz.get("job_name_next_q")
        if next_q_job_name and job_queue:
            jobs_to_remove = job_queue.get_jobs_by_name(next_q_job_name)
            for job in jobs_to_remove:
                job.schedule_removal()
            logger.info(f"Удален job '{next_q_job_name}' для остановки ежедневной викторины в чате {chat_id_str}.")
        
        # Также нужно остановить текущий опрос, если он есть и относится к этой викторине
        # Это более сложная часть, т.к. опросы останавливаются по таймауту, а не командой боту напрямую (без удаления сообщения)
        # Мы можем пометить, что викторина остановлена, и poll_handler не будет засчитывать очки
        state.active_daily_quizzes.pop(chat_id_str, None) # Удаляем из активных
        
        await update.message.reply_text("Ежедневная викторина остановлена. Следующие вопросы не будут отправлены.")
        logger.info(f"Ежедневная викторина остановлена в чате {chat_id_str} по команде /stopquiz.")
        stopped_something = True

    if not stopped_something:
        await update.message.reply_text("Нет активных или запланированных викторин для остановки в этом чате.")


async def show_quiz_categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает доступные категории вопросов в виде кнопок для /quiz10."""
    if not update.message or not update.effective_chat: return

    chat_id = update.effective_chat.id
    chat_id_str = str(chat_id)

    # Проверки на активные/запланированные викторины
    if state.current_quiz_session.get(chat_id_str):
        await update.message.reply_text("Викторина /quiz10 уже идет. Командуйте /stopquiz для остановки или дождитесь завершения.")
        return
    if state.pending_scheduled_quizzes.get(chat_id_str):
        await update.message.reply_text("Викторина /quiz10notify уже запланирована. Командуйте /stopquiz для отмены.")
        return
    if state.active_daily_quizzes.get(chat_id_str):
        await update.message.reply_text("В этом чате идет ежедневная викторина. /stopquiz для остановки.")
        return


    if not state.quiz_data:
        await update.message.reply_text("Категории вопросов не загружены.")
        return

    available_categories = sorted([cat for cat, questions in state.quiz_data.items() if questions])
    if not available_categories:
        await update.message.reply_text("Нет доступных категорий с вопросами.")
        return

    keyboard = []
    # Сохраняем полное имя категории в chat_data под коротким ID для callback'а
    # Это нужно, т.к. callback_data имеет ограничение по длине
    category_map_for_callback = {} # short_id -> full_category_name

    MAX_CATEGORIES_IN_MENU_Q10 = 25 # Лимит кнопок, чтобы сообщение не было слишком большим

    for i, cat_name in enumerate(available_categories[:MAX_CATEGORIES_IN_MENU_Q10]):
        short_id = f"c{i}" # Простой короткий ID
        category_map_for_callback[short_id] = cat_name
        # Убедимся, что callback_data не превышает лимит Telegram (64 байта)
        callback_data = f"{CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT}{short_id}"
        if len(callback_data.encode('utf-8')) > 64:
            logger.error(f"Сгенерированный callback_data '{callback_data}' для категории '{cat_name}' (/quiz10) слишком длинный! Пропуск кнопки.")
            continue
        keyboard.append([InlineKeyboardButton(cat_name, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("🎲 Случайная категория", callback_data=CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY)])
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Сохраняем карту в chat_data, чтобы потом получить полное имя категории в callback_handler
    # Ключ должен быть уникальным для чата
    context.chat_data[f"quiz10_category_map_{chat_id_str}"] = category_map_for_callback

    text = "Выберите категорию для викторины /quiz10:"
    if len(available_categories) > MAX_CATEGORIES_IN_MENU_Q10:
        text += f"\n(Показаны первые {MAX_CATEGORIES_IN_MENU_Q10} из {len(available_categories)}. Для выбора других категорий используйте команду `/quiz10 Название категории`)"
    
    await update.message.reply_text(text, reply_markup=reply_markup)


async def handle_quiz10_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает выбор категории из InlineKeyboard для /quiz10."""
    query = update.callback_query
    await query.answer() # Отвечаем на callback, чтобы убрать "часики" на кнопке

    if not query.message or not query.message.chat: return

    chat_id_str = str(query.message.chat.id)
    category_map_key = f"quiz10_category_map_{chat_id_str}"
    category_map = context.chat_data.pop(category_map_key, None) # Удаляем карту после использования

    selected_category_name: str | None = None

    if query.data == CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY:
        selected_category_name = "Случайная" # Специальное значение для случайного выбора
    elif query.data and query.data.startswith(CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT):
        if category_map:
            short_id = query.data[len(CALLBACK_DATA_PREFIX_QUIZ10_CATEGORY_SHORT):]
            selected_category_name = category_map.get(short_id)
        else:
            await query.edit_message_text(text="Ошибка: данные для выбора категории устарели. Попробуйте снова /quiz10.", reply_markup=None)
            logger.warning(f"Карта категорий quiz10_category_map_{chat_id_str} не найдена в chat_data.")
            return

    if selected_category_name:
        # Удаляем клавиатуру из предыдущего сообщения
        try:
            await query.edit_message_text(text=f"Выбрана категория: {selected_category_name}. Начинаем /quiz10...", reply_markup=None)
        except Exception as e: # Может быть ошибка, если сообщение слишком старое
            logger.warning(f"Не удалось отредактировать сообщение выбора категории для /quiz10 в {chat_id_str}: {e}")
            # Отправим новое сообщение, если редактирование не удалось
            await context.bot.send_message(chat_id_str, f"Выбрана категория: {selected_category_name}. Начинаем /quiz10...")


        # Имитируем вызов quiz10_command с выбранной категорией
        # Создаем "фиктивный" Update объект для передачи в quiz10_command, если это необходимо
        # В данном случае, quiz10_command уже умеет принимать category напрямую
        class MockMessage:
            async def reply_text(self, text, **kwargs): # Мок для reply_text
                return await context.bot.send_message(chat_id_str, text, **kwargs)
        
        mock_update = Update(update_id=query.update_id, message=MockMessage()) # type: ignore
        # Передаем chat.id и user.id из query
        if query.message and query.message.chat: mock_update.effective_chat = query.message.chat
        if query.from_user: mock_update.effective_user = query.from_user
        
        # Передаем аргументы, если они были (например, время на ответ), но категория будет переопределена
        # context.args может быть None, если команда была вызвана без них
        original_args = context.args if isinstance(context.args, list) else []

        # Передаем управление в quiz10_command, передавая выбранную категорию
        # quiz10_command сама разберется с остальными аргументами (временем и т.д.)
        await quiz10_command(mock_update, context, category=selected_category_name)

    else:
        error_text = "Ошибка выбора категории. Попробуйте снова."
        if query.data != CALLBACK_DATA_QUIZ10_RANDOM_CATEGORY and not category_map:
             error_text = "Данные для выбора категории устарели. Пожалуйста, вызовите /quiz10 еще раз."
        try:
            await query.edit_message_text(text=error_text, reply_markup=None)
        except Exception: pass # Если не удалось отредактировать, ничего страшного


async def _quiz10_notify_job(context: ContextTypes.DEFAULT_TYPE):
    """Job, который отправляет уведомление и планирует старт викторины."""
    job = context.job
    if not job or not job.data:
        logger.error("_quiz10_notify_job: Job data is missing.")
        return

    chat_id = job.data.get("chat_id")
    category_name = job.data.get("category_name")
    open_period = job.data.get("open_period")
    delay_minutes = job.data.get("delay_minutes")
    
    if not chat_id:
        logger.error("_quiz10_notify_job: chat_id отсутствует в job.data.")
        return

    chat_id_str = str(chat_id)
    pending_quiz_details = state.pending_scheduled_quizzes.get(chat_id_str)

    if not pending_quiz_details or pending_quiz_details.get("notify_job_name") != job.name:
        logger.info(f"Уведомление для {chat_id_str} (job: {job.name}) отменено или перезаписано. Job не будет выполнен.")
        return # Уведомление было отменено или перезаписано другим /quiz10notify
    
    category_display = f"категории '{category_name}'" if category_name and category_name != "Случайная" else "случайным категориям"
    time_word = pluralize_points(delay_minutes, "минуту", "минуты", "минут")
    
    notify_message = (f"🔔 Внимание! Викторина /quiz10 по {category_display} начнется через {delay_minutes} {time_word}.\n"
                      f"Время на ответ: {open_period} секунд. Приготовьтесь!")
    try:
        await context.bot.send_message(chat_id, notify_message)
        logger.info(f"Отправлено уведомление /quiz10notify в чат {chat_id_str}.")
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление /quiz10notify в чат {chat_id_str}: {e}")
        # Удаляем из pending, т.к. уведомление не доставлено
        state.pending_scheduled_quizzes.pop(chat_id_str, None)
        # Job старта викторины также не должен запускаться, его имя хранится в pending_quiz_details
        if pending_quiz_details and (start_job_name := pending_quiz_details.get("quiz_start_job_name")):
            job_queue: JobQueue | None = context.application.job_queue
            if job_queue:
                for j in job_queue.get_jobs_by_name(start_job_name): j.schedule_removal()
        return

    # Job уведомления выполнился, теперь он не нужен
    # Job старта самой викторины уже был запланирован при вызове /quiz10notify

async def quiz10_notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Планирует викторину /quiz10 с уведомлением за N минут."""
    if not update.message or not update.effective_chat: return
    
    chat_id = update.effective_chat.id
    chat_id_str = str(chat_id)

    if not await _is_user_admin_or_creator(update, context):
        await update.message.reply_text("Только администраторы могут планировать викторины с уведомлением.")
        return

    if state.current_quiz_session.get(chat_id_str):
        await update.message.reply_text("Викторина /quiz10 уже идет. Дождитесь ее завершения или остановите (/stopquiz).")
        return
    if state.active_daily_quizzes.get(chat_id_str):
        await update.message.reply_text("В этом чате идет ежедневная викторина. /stopquiz для остановки.")
        return

    args = list(context.args or []) # Копируем, чтобы можно было изменять

    # 1. Извлечение времени задержки уведомления (первое число, если есть)
    delay_minutes_actual = QUIZ10_NOTIFY_DELAY_MINUTES # Значение по умолчанию
    if args and args[0].isdigit():
        try:
            val = int(args.pop(0))
            if 1 <= val <= 1440: # От 1 минуты до 24 часов
                delay_minutes_actual = val
            else:
                await update.message.reply_text("Время уведомления должно быть от 1 до 1440 минут.")
                return
        except ValueError: pass # Не число, значит это часть названия категории

    # 2. Извлечение времени на ответ (второе число, если есть)
    open_period_actual = DEFAULT_POLL_OPEN_PERIOD
    if args and args[0].isdigit():
        try:
            val = int(args.pop(0))
            if 10 <= val <= 600: # Ограничение Telegram
                open_period_actual = val
            else:
                await update.message.reply_text(f"Время на ответ должно быть от 10 до 600 секунд. Будет использовано: {open_period_actual} сек.")
        except ValueError: pass

    # 3. Все остальное - название категории
    category_name_actual = " ".join(args) if args else None # None означает случайную
    if category_name_actual and category_name_actual.lower() in ["random", "случайная"]:
        category_name_actual = None


    # Проверка, есть ли вопросы для такой категории (если она указана)
    if category_name_actual:
        if not state.quiz_data or category_name_actual not in state.quiz_data or not state.quiz_data[category_name_actual]:
            await update.message.reply_text(f"Категория '{category_name_actual}' не найдена или не содержит вопросов. Викторина не будет запланирована.")
            return
        # Проверим, достаточно ли вопросов в категории
        if len(state.quiz_data[category_name_actual]) < NUMBER_OF_QUESTIONS_IN_SESSION:
             await update.message.reply_text(f"В категории '{category_name_actual}' менее {NUMBER_OF_QUESTIONS_IN_SESSION} вопросов. Викторина не будет запланирована.")
             return
    else: # Если категория случайная, проверяем общее кол-во вопросов
        if not get_random_questions(NUMBER_OF_QUESTIONS_IN_SESSION, None): # Пробный вызов
            await update.message.reply_text(f"Недостаточно вопросов для начала викторины ({NUMBER_OF_QUESTIONS_IN_SESSION} шт.) по случайным категориям.")
            return

    job_queue: JobQueue | None = context.application.job_queue
    if not job_queue:
        logger.error("JobQueue не доступен для quiz10_notify_command.")
        await update.message.reply_text("Ошибка: сервис планировщика недоступен.")
        return

    # Отменяем предыдущее запланированное уведомление и викторину для этого чата, если есть
    if existing_pending := state.pending_scheduled_quizzes.pop(chat_id_str, None):
        if notify_job_name := existing_pending.get("notify_job_name"):
            for j in job_queue.get_jobs_by_name(notify_job_name): j.schedule_removal()
        if quiz_start_job_name := existing_pending.get("quiz_start_job_name"):
            for j in job_queue.get_jobs_by_name(quiz_start_job_name): j.schedule_removal()
        logger.info(f"Отменена предыдущая запланированная викторина /quiz10notify для чата {chat_id_str}.")


    # Уникальные имена для jobs
    timestamp_now_for_job_name = int(datetime.now().timestamp())
    base_job_name = f"quiz10notify_{chat_id_str}_{timestamp_now_for_job_name}"
    notify_job_name = f"{base_job_name}_notification"
    quiz_start_job_name = f"{base_job_name}_start"

    # Время старта самой викторины
    quiz_start_time = datetime.now() + timedelta(minutes=delay_minutes_actual)

    # Данные для job'а, который будет запускать quiz10_command
    quiz_start_job_data = {
        "chat_id": chat_id,
        # "category_name": category_name_actual, # quiz10_command ожидает категорию в args или через параметр
        # "open_period": open_period_actual, # quiz10_command ожидает это в args
        # Передаем в context.args для quiz10_command
        "args": [str(open_period_actual)] + ([category_name_actual] if category_name_actual else [])
    }


    # Планируем job, который запустит саму викторину quiz10_command
    # Передаем параметры через `job.data['args']` которые потом будут в `context.args`
    # Либо нужно модифицировать quiz10_command, чтобы она могла принимать эти данные из job.data напрямую.
    # Проще передать через 'args' в job.data, а в quiz10_command доставать context.job.data['args'] если context.args пуст
    # Это будет выглядеть так:
    # if context.job and context.job.data and 'args' in context.job.data:
    #    context.args = context.job.data['args']
    # quiz10_command(update, context, initiated_by_notify=True)
    # ---
    # НО! quiz10_command уже умеет принимать категорию как параметр. Время ответа - через args.
    # Мы можем передать в data для quiz10_command все что нужно, и она разберется.
    # Для этого quiz10_command должна будет проверять context.job.data
    
    # Создаем фиктивный update для quiz10_command, т.к. она его ожидает
    # Это нужно, чтобы quiz10_command могла использовать context.bot.send_message и т.п.
    # Важно: chat_id будет взят из job.data в quiz10_command, если update.effective_chat нет
    class MockUser: id = 0; name = "ScheduledTask" # фиктивный пользователь
    class MockChat: id = chat_id; type = update.effective_chat.type # Используем реальный chat_id
    class MockMessage: chat = MockChat(); from_user = MockUser() # фиктивное сообщение
        # async def reply_text(self, text, **kwargs): await context.bot.send_message(self.chat.id, text, **kwargs)

    # Запускаем quiz10_command через job_queue.run_once
    # Ей нужно передать category и open_period. Она сама создаст сессию.
    # Мы передаем chat_id, category, open_period в quiz_start_job_data
    # А в quiz10_command мы будем их извлекать из context.job.data
    # quiz10_command будет вызвана с initiated_by_notify=True
    
    # Обновленная логика для quiz10_command:
    # def quiz10_command(update, context, category=None, initiated_by_notify=False, open_period_override=None)
    # if initiated_by_notify and context.job and context.job.data:
    #    chat_id = context.job.data.get("chat_id")
    #    category_from_job = context.job.data.get("category_name_for_start")
    #    open_period_from_job = context.job.data.get("open_period_for_start")
    #    # Используем их
    # Иначе, как обычно из update.message и context.args
    
    # Для _quiz10_notify_job (который отправляет УВЕДОМЛЕНИЕ):
    notify_job_data = {
        "chat_id": chat_id,
        "category_name": category_name_actual or "Случайная",
        "open_period": open_period_actual,
        "delay_minutes": delay_minutes_actual
    }
    
    # Сохраняем информацию о запланированной викторине
    state.pending_scheduled_quizzes[chat_id_str] = {
        "notify_job_name": notify_job_name,
        "quiz_start_job_name": quiz_start_job_name,
        "start_timestamp": quiz_start_time.timestamp(),
        "category_name": category_name_actual or "Случайная",
        "open_period": open_period_actual,
        "delay_minutes": delay_minutes_actual
    }

    # Планируем уведомление (если delay > 0)
    # Уведомление отправится, а через delay_minutes_actual запустится quiz10_command
    if delay_minutes_actual > 0:
        job_queue.run_once(
            _quiz10_notify_job,
            when=timedelta(minutes=0.01), # Отправляем уведомление почти сразу после команды
            data=notify_job_data,
            name=notify_job_name
        )
        # Планируем саму викторину через delay_minutes_actual
        job_queue.run_once(
            lambda ctx: asyncio.create_task(quiz10_command(
                update=Update(0, message=None), # Пустой update, т.к. chat_id будет из job.data
                context=ctx,
                category=ctx.job.data.get("category_name_for_start"), # type: ignore
                initiated_by_notify=True
                # open_period будет взят из ctx.args, которые мы формируем ниже
            )),
            when=quiz_start_time, # Точное время старта
            data={ # Эти данные будут доступны в context.job.data внутри лямбды и quiz10_command
                "chat_id": chat_id,
                "category_name_for_start": category_name_actual, # Может быть None
                "open_period_for_start": open_period_actual,
                 # Для quiz10_command, чтобы она взяла open_period
                "args": [str(open_period_actual)] # Категорию передаем явно
            },
            name=quiz_start_job_name
        )
        start_time_user_friendly = quiz_start_time.strftime("%H:%M:%S")
        category_display_user = f"категории '{category_name_actual}'" if category_name_actual else "случайным категориям"
        time_word_user = pluralize_points(delay_minutes_actual, "минуту", "минуты", "минут")

        await update.message.reply_text(
            f"✅ Викторина /quiz10 по {category_display_user} запланирована!\n"
            f"Уведомление будет отправлено сейчас, а сама викторина начнется через {delay_minutes_actual} {time_word_user} (примерно в {start_time_user_friendly} МСК).\n"
            f"Время на ответ: {open_period_actual} секунд.\n"
            f"Для отмены используйте /stopquiz."
        )
        logger.info(f"Запланирована викторина /quiz10notify для {chat_id_str} на {start_time_user_friendly} МСК. Уведомление через ~0 мин, старт через {delay_minutes_actual} мин. Кат: {category_name_actual or 'Случ.'}, время: {open_period_actual}с.")

    else: # Если delay_minutes_actual == 0 (не должно быть по логике проверки val >=1, но на всякий случай)
          # или если мы решим запускать немедленно без уведомления
        state.pending_scheduled_quizzes.pop(chat_id_str, None) # Убираем из pending, т.к. стартует сразу
        await update.message.reply_text("Задержка должна быть > 0. Используйте /quiz10 для немедленного старта.")
        # await quiz10_command(update, context, category=category_name_actual) # Запускаем сразу, если нужно
        return

