# handlers/daily_quiz_handlers.py
import random
from datetime import timedelta
from telegram import Update
from telegram.ext import ContextTypes, JobQueue
from telegram.constants import ChatMemberStatus, ParseMode

from config import (logger, DAILY_QUIZ_SUBSCRIPTIONS_FILE, DAILY_QUIZ_QUESTIONS_COUNT,
                    DAILY_QUIZ_CATEGORIES_TO_PICK, DAILY_QUIZ_POLL_OPEN_PERIOD_SECONDS,
                    DAILY_QUIZ_QUESTION_INTERVAL_SECONDS, DAILY_QUIZ_DEFAULT_HOUR_MSK, # Добавлен импорт
                    DAILY_QUIZ_DEFAULT_MINUTE_MSK) # Добавлен импорт
import state
from data_manager import save_daily_quiz_subscriptions
from quiz_logic import prepare_poll_options # Используем существующую функцию

# --- Вспомогательные функции ---
async def _is_user_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
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

def _get_questions_for_daily_quiz(
    num_questions: int = DAILY_QUIZ_QUESTIONS_COUNT,
    num_categories_to_pick: int = DAILY_QUIZ_CATEGORIES_TO_PICK
) -> tuple[list[dict], list[str]]:
    """
    Выбирает указанное количество случайных категорий, а затем
    указанное количество вопросов из этих категорий.
    Возвращает список вопросов и список имен выбранных категорий.
    """
    questions_for_quiz: list[dict] = []
    picked_category_names: list[str] = []

    if not state.quiz_data:
        logger.warning("Нет загруженных вопросов (state.quiz_data пуст) для формирования ежедневной викторины.")
        return [], []

    # Отбираем только категории, в которых есть вопросы
    available_categories_with_questions = {
        cat_name: q_list for cat_name, q_list in state.quiz_data.items() if q_list
    }

    if not available_categories_with_questions:
        logger.warning("Нет категорий с вопросами для ежедневной викторины.")
        return [], []

    # Выбираем num_categories_to_pick случайных категорий
    num_to_sample = min(num_categories_to_pick, len(available_categories_with_questions))
    if num_to_sample == 0: # На всякий случай, хотя предыдущая проверка должна это покрыть
        return [], []

    picked_category_names = random.sample(list(available_categories_with_questions.keys()), num_to_sample)

    # Собираем все вопросы из выбранных категорий
    all_questions_from_picked_categories: list[dict] = []
    for cat_name in picked_category_names:
        all_questions_from_picked_categories.extend(
            [q.copy() for q in available_categories_with_questions.get(cat_name, [])]
        )

    if not all_questions_from_picked_categories:
        logger.warning(f"Выбранные категории {picked_category_names} не содержат вопросов.")
        return [], picked_category_names # Возвращаем имена, но пустой список вопросов

    # Перемешиваем все вопросы из отобранных категорий
    random.shuffle(all_questions_from_picked_categories)

    # Отбираем нужное количество вопросов
    questions_for_quiz = all_questions_from_picked_categories[:num_questions]

    logger.info(f"Для ежедневной викторины отобрано {len(questions_for_quiz)} вопросов из категорий: {picked_category_names}.")
    return questions_for_quiz, picked_category_names

# --- Обработчики команд ---
async def subscribe_daily_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user:
        return

    chat_id_str = str(update.effective_chat.id)

    if not await _is_user_admin(update, context):
        reply_text = "Только администраторы могут подписать этот чат на ежедневную викторину."
        logger.debug(f"Attempting to send admin restriction message to {chat_id_str}. Text: '{reply_text}'")
        await update.message.reply_text(reply_text)
        return

    if chat_id_str in state.daily_quiz_subscriptions:
        reply_text = "Этот чат уже подписан на ежедневную викторину."
    else:
        state.daily_quiz_subscriptions.add(chat_id_str)
        save_daily_quiz_subscriptions()
        reply_text = (f"✅ Этот чат подписан на ежедневную викторину! "
                      f"Она будет начинаться примерно в {DAILY_QUIZ_DEFAULT_HOUR_MSK:02d}:{DAILY_QUIZ_DEFAULT_MINUTE_MSK:02d} МСК.\n"
                      f"Будет {DAILY_QUIZ_QUESTIONS_COUNT} вопросов из {DAILY_QUIZ_CATEGORIES_TO_PICK} случайных категорий, "
                      f"по одному вопросу в минуту. Каждый вопрос будет открыт {DAILY_QUIZ_POLL_OPEN_PERIOD_SECONDS // 60} минут.")

    logger.debug(f"Attempting to send daily quiz subscription status to {chat_id_str}. Text: '{reply_text}'")
    await update.message.reply_text(reply_text)
    logger.info(f"Чат {chat_id_str} подписан на ежедневную викторину пользователем {update.effective_user.id}.")

async def unsubscribe_daily_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user:
        return

    chat_id_str = str(update.effective_chat.id)

    if not await _is_user_admin(update, context):
        reply_text = "Только администраторы могут отписать этот чат от ежедневной викторины."
        logger.debug(f"Attempting to send admin restriction message to {chat_id_str}. Text: '{reply_text}'")
        await update.message.reply_text(reply_text)
        return

    if chat_id_str in state.daily_quiz_subscriptions:
        state.daily_quiz_subscriptions.discard(chat_id_str)
        save_daily_quiz_subscriptions()
        reply_text = "Этот чат отписан от ежедневной викторины."
        logger.info(f"Чат {chat_id_str} отписан от ежедневной викторины пользователем {update.effective_user.id}.")
    else:
        reply_text = "Этот чат не был подписан на ежедневную викторину."

    logger.debug(f"Attempting to send daily quiz unsubscription status to {chat_id_str}. Text: '{reply_text}'")
    await update.message.reply_text(reply_text)

# --- Логика запланированных задач (Jobs) ---

async def _send_one_daily_question_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    if not job or not job.data:
        logger.error("_send_one_daily_question_job: Job data is missing.")
        return

    chat_id_str: str = job.data["chat_id_str"]
    current_q_idx: int = job.data["current_question_index"]
    questions_this_session: list[dict] = job.data["questions_this_session"]

    active_quiz_state = state.active_daily_quizzes.get(chat_id_str)
    if not active_quiz_state or active_quiz_state.get("current_question_index") != current_q_idx:
        logger.warning(f"Ежедневная викторина для чата {chat_id_str} была прервана или состояние не соответствует job'у. Остановка отправки вопроса {current_q_idx + 1}.")
        # Очищаем состояние, если оно есть, чтобы предотвратить дальнейшие запуски
        state.active_daily_quizzes.pop(chat_id_str, None)
        return

    if current_q_idx >= len(questions_this_session):
        logger.info(f"Все {len(questions_this_session)} вопросов ежедневной викторины отправлены в чат {chat_id_str}.")
        state.active_daily_quizzes.pop(chat_id_str, None) # Завершаем сессию
        # Можно отправить сообщение о завершении
        try:
            final_text = "🎉 Ежедневная викторина завершена! Спасибо за участие!"
            logger.debug(f"Attempting to send daily quiz completion message to {chat_id_str}. Text: '{final_text}'")
            await context.bot.send_message(chat_id=chat_id_str, text=final_text)
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение о завершении ежедневной викторины в чат {chat_id_str}: {e}")
        return

    q_details = questions_this_session[current_q_idx]

    # Подготовка текста вопроса
    poll_question_text_for_api = q_details['question']
    full_poll_question_header = f"Ежедневная викторина! Вопрос {current_q_idx + 1}/{len(questions_this_session)}"
    if original_cat := q_details.get("original_category"):
        full_poll_question_header += f" (Кат: {original_cat})"
    full_poll_question_header += f"\n\n{poll_question_text_for_api}" # Добавил \n\n для лучшего форматирования

    MAX_POLL_QUESTION_LENGTH = 255 # Telegram API limit for poll question
    if len(full_poll_question_header) > MAX_POLL_QUESTION_LENGTH:
        truncate_at = MAX_POLL_QUESTION_LENGTH - 3 # for "..."
        full_poll_question_header = full_poll_question_header[:truncate_at] + "..."
        logger.warning(f"Текст вопроса ежедневной викторины для poll в чате {chat_id_str} был усечен.")

    _, poll_options, poll_correct_option_id, _ = prepare_poll_options(q_details)

    try:
        logger.debug(f"Отправка ежедневного вопроса {current_q_idx + 1} в чат {chat_id_str}. Текст: '{full_poll_question_header[:100]}...'")
        sent_poll_msg = await context.bot.send_poll(
            chat_id=chat_id_str,
            question=full_poll_question_header,
            options=poll_options,
            type='quiz',
            correct_option_id=poll_correct_option_id,
            open_period=DAILY_QUIZ_POLL_OPEN_PERIOD_SECONDS,
            is_anonymous=False
        )
        # Сохраняем информацию о созданном опросе для poll_answer_handler
        state.current_poll[sent_poll_msg.poll.id] = {
            "chat_id": chat_id_str,
            "message_id": sent_poll_msg.message_id,
            "correct_index": poll_correct_option_id,
            "quiz_session": False, # Это не /quiz10 сессия
            "daily_quiz": True,    # Пометка, что это опрос из ежедневной викторины
            "question_details": q_details,
            "question_session_index": current_q_idx, # Для логирования в poll_answer_handler
            "open_timestamp": sent_poll_msg.date.timestamp() # Время отправки опроса
        }
        logger.info(f"Ежедневный вопрос {current_q_idx + 1}/{len(questions_this_session)} (Poll ID: {sent_poll_msg.poll.id}) отправлен в чат {chat_id_str}.")

    except Exception as e:
        logger.error(f"Ошибка при отправке ежедневного вопроса {current_q_idx + 1} в чат {chat_id_str}: {e}", exc_info=True)
        state.active_daily_quizzes.pop(chat_id_str, None) # Прерываем сессию в случае ошибки
        return # Не планируем следующий вопрос

    # Планируем следующий вопрос
    next_q_idx = current_q_idx + 1
    active_quiz_state["current_question_index"] = next_q_idx # Обновляем состояние

    if next_q_idx < len(questions_this_session):
        job_queue: JobQueue | None = context.application.job_queue
        if job_queue:
            next_job_name = f"daily_quiz_q_{next_q_idx}_chat_{chat_id_str}"
            active_quiz_state["job_name_next_q"] = next_job_name
            job_queue.run_once(
                _send_one_daily_question_job,
                timedelta(seconds=DAILY_QUIZ_QUESTION_INTERVAL_SECONDS),
                data={
                    "chat_id_str": chat_id_str,
                    "current_question_index": next_q_idx,
                    "questions_this_session": questions_this_session
                },
                name=next_job_name
            )
            logger.debug(f"Запланирован следующий ежедневный вопрос ({next_q_idx + 1}) для чата {chat_id_str} (job: {next_job_name}).")
    else:
        # Это был последний вопрос, следующий job вызовет завершение сессии.
        # На самом деле, логика завершения уже есть в начале этой функции.
        # Можно здесь запланировать финальное сообщение, если нужно.
        job_queue: JobQueue | None = context.application.job_queue
        if job_queue:
            final_job_name = f"daily_quiz_finish_chat_{chat_id_str}"
            active_quiz_state["job_name_next_q"] = final_job_name # Хотя это джоб завершения
            job_queue.run_once(
                _send_one_daily_question_job, # Он же обработает выход за пределы индекса
                timedelta(seconds=DAILY_QUIZ_QUESTION_INTERVAL_SECONDS), # Небольшая задержка перед сообщением о завершении
                data={
                    "chat_id_str": chat_id_str,
                    "current_question_index": next_q_idx, # next_q_idx == len(questions_this_session)
                    "questions_this_session": questions_this_session
                },
                name=final_job_name
            )
            logger.debug(f"Запланирован финальный обработчик для ежедневной викторины в чате {chat_id_str} (job: {final_job_name}).")

async def _trigger_daily_quiz_for_chat_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    if not job or not job.data:
        logger.error("_trigger_daily_quiz_for_chat_job: Job data is missing.")
        return

    chat_id_str: str = job.data["chat_id_str"]

    if chat_id_str in state.active_daily_quizzes:
        logger.warning(f"Попытка запустить ежедневную викторину для чата {chat_id_str}, но она уже активна. Пропуск.")
        return

    questions_for_quiz, picked_categories = _get_questions_for_daily_quiz(
        num_questions=DAILY_QUIZ_QUESTIONS_COUNT,
        num_categories_to_pick=DAILY_QUIZ_CATEGORIES_TO_PICK
    )

    if not questions_for_quiz:
        logger.warning(f"Не удалось получить вопросы для ежедневной викторины в чате {chat_id_str}. Викторина не будет запущена.")
        try:
            error_text = "Не удалось подготовить вопросы для сегодняшней ежедневной викторины. Попробуем завтра!"
            logger.debug(f"Attempting to send daily quiz question fetch error to {chat_id_str}. Text: '{error_text}'")
            await context.bot.send_message(chat_id=chat_id_str, text=error_text)
        except Exception as e:
            logger.error(f"Не удалось уведомить чат {chat_id_str} об ошибке подготовки ежедневной викторины: {e}")
        return

    # Сообщение о начале
    intro_message_parts = [
        f"🌞 Доброе утро! Начинаем ежедневную викторину ({len(questions_for_quiz)} вопросов)!",
        f"Сегодняшние категории: <b>{', '.join(picked_categories) if picked_categories else 'Случайные'}</b>.",
        f"Один вопрос каждую минуту. Каждый вопрос будет доступен {DAILY_QUIZ_POLL_OPEN_PERIOD_SECONDS // 60} минут."
    ]
    intro_text = "\n".join(intro_message_parts)

    try:
        logger.debug(f"Attempting to send daily quiz intro message to {chat_id_str}. Text: '{intro_text[:100]}...'")
        await context.bot.send_message(chat_id=chat_id_str, text=intro_text, parse_mode=ParseMode.HTML)
        logger.info(f"Ежедневная викторина инициирована для чата {chat_id_str} с {len(questions_for_quiz)} вопросами из категорий: {picked_categories}.")
    except Exception as e:
        logger.error(f"Не удалось отправить стартовое сообщение ежедневной викторины в чат {chat_id_str}: {e}", exc_info=True)
        return # Если не можем отправить интро, не начинаем

    # Инициализируем состояние активной викторины
    state.active_daily_quizzes[chat_id_str] = {
        "current_question_index": 0,
        "questions": questions_for_quiz,
        "picked_categories": picked_categories,
        "job_name_next_q": None
    }

    # Запускаем отправку первого вопроса (небольшая задержка после интро)
    job_queue: JobQueue | None = context.application.job_queue
    if job_queue:
        first_q_job_name = f"daily_quiz_q_0_chat_{chat_id_str}"
        state.active_daily_quizzes[chat_id_str]["job_name_next_q"] = first_q_job_name
        job_queue.run_once(
            _send_one_daily_question_job,
            timedelta(seconds=5), # Короткая задержка после интро-сообщения
            data={
                "chat_id_str": chat_id_str,
                "current_question_index": 0,
                "questions_this_session": questions_for_quiz
            },
            name=first_q_job_name
        )
        logger.debug(f"Запланирован первый вопрос ежедневной викторины для чата {chat_id_str} (job: {first_q_job_name}).")

async def master_daily_quiz_scheduler_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Запущен мастер-планировщик ежедневных викторин.")
    if not state.daily_quiz_subscriptions:
        logger.info("Нет чатов, подписанных на ежедневную викторину.")
        return

    job_queue: JobQueue | None = context.application.job_queue
    if not job_queue:
        logger.error("JobQueue не доступен в master_daily_quiz_scheduler_job. Викторины не будут запущены.")
        return

    active_subscriptions = list(state.daily_quiz_subscriptions) # Копируем, чтобы избежать проблем с изменением во время итерации
    logger.info(f"Обнаружено {len(active_subscriptions)} подписок. Запуск индивидуальных планировщиков.")

    for i, chat_id_str in enumerate(active_subscriptions):
        # Небольшая задержка между запусками для разных чатов, чтобы распределить нагрузку
        delay_seconds = i * 2 # Например, 2 секунды на чат

        # Удаляем старые незавершенные джобы для этого чата, если есть
        for prefix in ["daily_quiz_trigger_chat_", "daily_quiz_q_", "daily_quiz_finish_chat_"]:
            # Это может быть неэффективно, если джобов много.
            # Более правильным было бы хранить имена активных джобов для каждого чата.
            # Но для простоты пока так, предполагая, что имена уникальны.
            # Лучше при старте каждой сессии удалять предыдущие джобы для *этого* чата.
            # Это делается в _trigger_daily_quiz_for_chat_job и _send_one_daily_question_job (косвенно, через state.active_daily_quizzes)
            pass

        trigger_job_name = f"daily_quiz_trigger_chat_{chat_id_str}"
        job_queue.run_once(
            _trigger_daily_quiz_for_chat_job,
            timedelta(seconds=delay_seconds),
            data={"chat_id_str": chat_id_str},
            name=trigger_job_name
        )
        logger.debug(f"Запланирован запуск ежедневной викторины для чата {chat_id_str} (job: {trigger_job_name}) через {delay_seconds} сек.")
