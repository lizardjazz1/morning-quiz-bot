# handlers/daily_quiz_handlers.py
import random
import re
from datetime import timedelta, time
from typing import Tuple, Optional, List, Dict, Any

import pytz
from telegram import Update
from telegram.ext import ContextTypes, JobQueue, Application
from telegram.constants import ChatMemberStatus, ParseMode

from config import (logger, DAILY_QUIZ_QUESTIONS_COUNT,
                    DAILY_QUIZ_CATEGORIES_TO_PICK, DAILY_QUIZ_POLL_OPEN_PERIOD_SECONDS,
                    DAILY_QUIZ_QUESTION_INTERVAL_SECONDS, DAILY_QUIZ_DEFAULT_HOUR_MSK,
                    DAILY_QUIZ_DEFAULT_MINUTE_MSK, DAILY_QUIZ_MAX_CUSTOM_CATEGORIES)
import state
from data_manager import save_daily_quiz_subscriptions
from quiz_logic import prepare_poll_options

# --- Вспомогательные функции ---

def moscow_time(hour: int, minute: int) -> time:
    """Создает объект datetime.time для указанного часа и минуты по Московскому времени."""
    moscow_tz = pytz.timezone('Europe/Moscow')
    return time(hour=hour, minute=minute, tzinfo=moscow_tz)

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

def _parse_time_hh_mm(time_str: str) -> Optional[Tuple[int, int]]:
    """Парсит время из строки формата HH, HH:MM, HH.MM."""
    match_hh_mm = re.fullmatch(r"(\d{1,2})[:.](\d{1,2})", time_str)
    if match_hh_mm:
        h_str, m_str = match_hh_mm.groups()
        try:
            h, m = int(h_str), int(m_str)
            if 0 <= h <= 23 and 0 <= m <= 59:
                return h, m
        except ValueError:
            pass # Fall through to return None
        return None # Explicitly return None if conversion or range check fails

    match_hh = re.fullmatch(r"(\d{1,2})", time_str)
    if match_hh:
        h_str = match_hh.group(1)
        try:
            h = int(h_str)
            if 0 <= h <= 23:
                return h, 0 # Минуты по умолчанию 00
        except ValueError:
            pass # Fall through to return None
    return None


async def _schedule_or_reschedule_daily_quiz_for_chat(application: Application, chat_id_str: str):
    """Планирует или перепланирует ежедневную викторину для конкретного чата."""
    job_queue: JobQueue | None = application.job_queue
    if not job_queue:
        logger.error(f"JobQueue не доступен. Не удалось (пере)запланировать ежедневную викторину для чата {chat_id_str}.")
        return

    subscription_details = state.daily_quiz_subscriptions.get(chat_id_str)
    job_name = f"daily_quiz_trigger_chat_{chat_id_str}"

    # Удаляем существующие jobs с таким именем перед (пере)планированием или если подписка неактивна
    existing_jobs = job_queue.get_jobs_by_name(job_name)
    if existing_jobs:
        for job in existing_jobs:
            job.schedule_removal()
        logger.debug(f"Удален(ы) существующий(е) job(s) '{job_name}' для чата {chat_id_str} перед (пере)планированием.")
    
    if not subscription_details:
        logger.info(f"Подписка для чата {chat_id_str} не активна. Викторина не будет запланирована (старые jobs удалены).")
        return

    hour = subscription_details.get("hour", DAILY_QUIZ_DEFAULT_HOUR_MSK)
    minute = subscription_details.get("minute", DAILY_QUIZ_DEFAULT_MINUTE_MSK)
    
    target_time_msk = moscow_time(hour, minute)
    job_queue.run_daily(
        _trigger_daily_quiz_for_chat_job,
        time=target_time_msk,
        data={"chat_id_str": chat_id_str}, 
        name=job_name
    )
    logger.info(f"Ежедневная викторина для чата {chat_id_str} запланирована на {hour:02d}:{minute:02d} МСК (job: {job_name}).")


def _get_questions_for_daily_quiz(
    chat_id_str: str, 
    num_questions: int = DAILY_QUIZ_QUESTIONS_COUNT,
    default_num_categories_to_pick: int = DAILY_QUIZ_CATEGORIES_TO_PICK
) -> tuple[list[dict], list[str]]:
    """
    Выбирает вопросы для ежедневной викторины.
    Использует пользовательские категории, если они настроены для чата, иначе выбирает случайные.
    Возвращает список вопросов и список имен выбранных категорий.
    """
    questions_for_quiz: list[dict] = []
    picked_category_names_final: list[str] = []

    if not state.quiz_data:
        logger.warning("Нет загруженных вопросов (state.quiz_data пуст) для формирования ежедневной викторины.")
        return [], []

    available_categories_with_questions = {
        cat_name: q_list for cat_name, q_list in state.quiz_data.items() if q_list
    }

    if not available_categories_with_questions:
        logger.warning("Нет категорий с вопросами для ежедневной викторины.")
        return [], []

    subscription_details = state.daily_quiz_subscriptions.get(chat_id_str, {})
    custom_categories_names_from_settings: Optional[List[str]] = subscription_details.get("categories")

    chosen_categories_for_quiz: List[str] = []

    if custom_categories_names_from_settings: # Пользователь указал категории
        valid_custom_categories = [
            name for name in custom_categories_names_from_settings if name in available_categories_with_questions
        ]
        if valid_custom_categories:
            chosen_categories_for_quiz = valid_custom_categories
            logger.info(f"Для чата {chat_id_str} используются кастомные категории: {chosen_categories_for_quiz}")
        else:
            logger.warning(f"Для чата {chat_id_str} указанные кастомные категории {custom_categories_names_from_settings} все недействительны или пусты. Будут выбраны случайные.")
            # Фолбэк на случайные категории (произойдет ниже)

    if not chosen_categories_for_quiz: # Случайный выбор категорий (если кастомных нет или все невалидны)
        num_to_sample_random = min(default_num_categories_to_pick, len(available_categories_with_questions))
        if num_to_sample_random > 0:
            chosen_categories_for_quiz = random.sample(list(available_categories_with_questions.keys()), num_to_sample_random)
        else: 
            logger.warning(f"Не удалось выбрать случайные категории для чата {chat_id_str} (num_to_sample_random={num_to_sample_random}).")
            return [], [] # Не из чего выбирать
        logger.info(f"Для чата {chat_id_str} выбраны случайные категории: {chosen_categories_for_quiz}")
    
    picked_category_names_final = chosen_categories_for_quiz # Сохраняем имена для возврата

    all_questions_from_picked_categories: list[dict] = []
    for cat_name in picked_category_names_final:
        all_questions_from_picked_categories.extend(
            [q.copy() for q in available_categories_with_questions.get(cat_name, [])]
        )

    if not all_questions_from_picked_categories:
        logger.warning(f"Выбранные категории {picked_category_names_final} для чата {chat_id_str} не содержат вопросов.")
        return [], picked_category_names_final 

    random.shuffle(all_questions_from_picked_categories)
    questions_for_quiz = all_questions_from_picked_categories[:num_questions]

    logger.info(f"Для ежедневной викторины в чате {chat_id_str} отобрано {len(questions_for_quiz)} вопросов из категорий: {picked_category_names_final}.")
    return questions_for_quiz, picked_category_names_final

# --- Обработчики команд ---
async def subscribe_daily_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user:
        return

    chat_id_str = str(update.effective_chat.id)

    if not await _is_user_admin(update, context):
        await update.message.reply_text("Только администраторы могут подписать этот чат на ежедневную викторину.")
        return

    if chat_id_str in state.daily_quiz_subscriptions:
        sub_details = state.daily_quiz_subscriptions[chat_id_str]
        time_str = f"{sub_details.get('hour', DAILY_QUIZ_DEFAULT_HOUR_MSK):02d}:{sub_details.get('minute', DAILY_QUIZ_DEFAULT_MINUTE_MSK):02d} МСК"
        cats = sub_details.get("categories")
        cat_str = f"категориям: {', '.join(cats)}" if cats else "случайным категориям"
        reply_text = (f"Этот чат уже подписан на ежедневную викторину\\.\n"
                      f"Время: *{time_str}*\\. Категории: *{cat_str}*\\.\n"
                      f"Используйте `/setdailyquiztime` и `/setdailyquizcategories` для настройки\\.")
    else:
        state.daily_quiz_subscriptions[chat_id_str] = {
            "hour": DAILY_QUIZ_DEFAULT_HOUR_MSK,
            "minute": DAILY_QUIZ_DEFAULT_MINUTE_MSK,
            "categories": None 
        }
        save_daily_quiz_subscriptions()
        await _schedule_or_reschedule_daily_quiz_for_chat(context.application, chat_id_str)
        
        reply_text = (f"✅ Этот чат подписан на ежедневную викторину\\!\n"
                      f"Время по умолчанию: *{DAILY_QUIZ_DEFAULT_HOUR_MSK:02d}:{DAILY_QUIZ_DEFAULT_MINUTE_MSK:02d} МСК*\\.\n"
                      f"Категории по умолчанию: *{DAILY_QUIZ_CATEGORIES_TO_PICK} случайных*\\.\n"
                      f"Будет {DAILY_QUIZ_QUESTIONS_COUNT} вопросов, по одному в минуту\\.\n"
                      f"Каждый вопрос будет открыт {DAILY_QUIZ_POLL_OPEN_PERIOD_SECONDS // 60} минут\\.\n\n"
                      f"Для настройки используйте:\n"
                      f"`/setdailyquiztime HH:MM` \\(например, `/setdailyquiztime 08:30`\\)\n"
                      f"`/setdailyquizcategories [названия категорий]` \\(до {DAILY_QUIZ_MAX_CUSTOM_CATEGORIES}, без аргументов \\- случайные\\)\n"
                      f"`/showdailyquizsettings` \\- показать текущие настройки\\.")
        logger.info(f"Чат {chat_id_str} подписан на ежедневную викторину пользователем {update.effective_user.id}.")

    await update.message.reply_text(reply_text, parse_mode=ParseMode.MARKDOWN_V2)


async def unsubscribe_daily_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user:
        return

    chat_id_str = str(update.effective_chat.id)

    if not await _is_user_admin(update, context):
        await update.message.reply_text("Только администраторы могут отписать этот чат от ежедневной викторины.")
        return

    if chat_id_str in state.daily_quiz_subscriptions:
        state.daily_quiz_subscriptions.pop(chat_id_str, None)
        save_daily_quiz_subscriptions()
        await _schedule_or_reschedule_daily_quiz_for_chat(context.application, chat_id_str) # This will remove the job

        reply_text = "Этот чат отписан от ежедневной викторины. Запланированная задача отменена."
        logger.info(f"Чат {chat_id_str} отписан от ежедневной викторины пользователем {update.effective_user.id}.")
    else:
        reply_text = "Этот чат не был подписан на ежедневную викторину."

    await update.message.reply_text(reply_text)

async def set_daily_quiz_time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user:
        await update.message.reply_text("Произошла ошибка с данными чата или пользователя.")
        return
    if not context.args:
        await update.message.reply_text("Использование: /setdailyquiztime HH:MM (например, 08:30) или HH (например, 9). Время указывается по МСК.")
        return

    chat_id_str = str(update.effective_chat.id)

    if not await _is_user_admin(update, context):
        await update.message.reply_text("Только администраторы могут изменять время ежедневной викторины.")
        return

    if chat_id_str not in state.daily_quiz_subscriptions:
        await update.message.reply_text("Этот чат не подписан на ежедневную викторину. Сначала используйте /subscribe_daily_quiz.")
        return

    time_str = context.args[0]
    parsed_time = _parse_time_hh_mm(time_str)

    if parsed_time is None:
        await update.message.reply_text("Неверный формат времени. Используйте HH:MM (например, 08:30) или HH (например, 9). Время указывается по МСК.")
        return

    hour, minute = parsed_time
    state.daily_quiz_subscriptions[chat_id_str]["hour"] = hour
    state.daily_quiz_subscriptions[chat_id_str]["minute"] = minute
    save_daily_quiz_subscriptions()
    await _schedule_or_reschedule_daily_quiz_for_chat(context.application, chat_id_str)

    await update.message.reply_text(f"Время ежедневной викторины для этого чата установлено на {hour:02d}:{minute:02d} МСК.")
    logger.info(f"Время ежедневной викторины для чата {chat_id_str} изменено на {hour:02d}:{minute:02d} МСК пользователем {update.effective_user.id}.")

async def set_daily_quiz_categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user:
        await update.message.reply_text("Произошла ошибка с данными чата или пользователя.")
        return

    chat_id_str = str(update.effective_chat.id)

    if not await _is_user_admin(update, context):
        await update.message.reply_text("Только администраторы могут изменять категории ежедневной викторины.")
        return

    if chat_id_str not in state.daily_quiz_subscriptions:
        await update.message.reply_text("Этот чат не подписан на ежедневную викторину. Сначала используйте /subscribe_daily_quiz.")
        return

    if not state.quiz_data:
        await update.message.reply_text("Вопросы еще не загружены. Невозможно установить категории.")
        return
    
    available_cat_names_map = {name.lower(): name for name, q_list in state.quiz_data.items() if q_list} # map lower_name -> original_name

    if not context.args: # Сброс на случайные категории
        state.daily_quiz_subscriptions[chat_id_str]["categories"] = None
        save_daily_quiz_subscriptions()
        await update.message.reply_text(f"Настройки категорий сброшены. Будут использоваться {DAILY_QUIZ_CATEGORIES_TO_PICK} случайных категорий.")
        logger.info(f"Категории ежедневной викторины для чата {chat_id_str} сброшены на случайные пользователем {update.effective_user.id}.")
        return

    chosen_categories_raw = context.args
    valid_chosen_categories_canonical = [] # Будем хранить канонические имена
    invalid_or_empty_categories_input = []

    for cat_name_arg in chosen_categories_raw:
        canonical_name = available_cat_names_map.get(cat_name_arg.lower())
        if canonical_name:
            if canonical_name not in valid_chosen_categories_canonical: 
                 valid_chosen_categories_canonical.append(canonical_name)
        else:
            invalid_or_empty_categories_input.append(cat_name_arg)

    if len(valid_chosen_categories_canonical) > DAILY_QUIZ_MAX_CUSTOM_CATEGORIES:
        await update.message.reply_text(f"Можно выбрать не более {DAILY_QUIZ_MAX_CUSTOM_CATEGORIES} категорий. Пожалуйста, сократите список.")
        return

    if not valid_chosen_categories_canonical and chosen_categories_raw: 
        await update.message.reply_text(f"Указанные категории не найдены или пусты: {', '.join(chosen_categories_raw)}. Используйте /categories для списка доступных. Настройки не изменены.")
        return

    state.daily_quiz_subscriptions[chat_id_str]["categories"] = valid_chosen_categories_canonical if valid_chosen_categories_canonical else None
    save_daily_quiz_subscriptions()

    reply_parts = []
    if valid_chosen_categories_canonical:
        reply_parts.append(f"Категории для ежедневной викторины установлены: {', '.join(valid_chosen_categories_canonical)}.")
    else: 
        reply_parts.append(f"Настройки категорий обновлены. Будут использоваться {DAILY_QUIZ_CATEGORIES_TO_PICK} случайных категорий (т.к. валидных пользовательских не указано или не выбрано).")

    if invalid_or_empty_categories_input:
        reply_parts.append(f"\nПредупреждение: категории '{', '.join(invalid_or_empty_categories_input)}' не найдены, пусты или уже были добавлены и проигнорированы.")
    
    await update.message.reply_text(" ".join(reply_parts))
    logger.info(f"Категории ежедневной викторины для чата {chat_id_str} изменены на {valid_chosen_categories_canonical or 'случайные'} пользователем {update.effective_user.id}.")

async def show_daily_quiz_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        return
    
    chat_id_str = str(update.effective_chat.id)

    if chat_id_str not in state.daily_quiz_subscriptions:
        await update.message.reply_text("Этот чат не подписан на ежедневную викторину. Используйте /subscribe_daily_quiz.")
        return
        
    settings = state.daily_quiz_subscriptions[chat_id_str]
    hour = settings.get("hour", DAILY_QUIZ_DEFAULT_HOUR_MSK)
    minute = settings.get("minute", DAILY_QUIZ_DEFAULT_MINUTE_MSK)
    custom_categories: Optional[List[str]] = settings.get("categories")

    time_str = f"{hour:02d}:{minute:02d} МСК"
    
    if custom_categories:
        categories_str = f"Выбранные: {', '.join(custom_categories)}"
    else:
        categories_str = f"Случайные ({DAILY_QUIZ_CATEGORIES_TO_PICK} категории)"
        
    reply_text = (f"⚙️ Текущие настройки ежедневной викторины для этого чата:\n"
                  f"\\- Время начала: *{time_str}*\n"
                  f"\\- Категории: *{categories_str}*\n"
                  f"\\- Количество вопросов: {DAILY_QUIZ_QUESTIONS_COUNT}\n"
                  f"\\- Длительность опроса: {DAILY_QUIZ_POLL_OPEN_PERIOD_SECONDS // 60} минут\n"
                  f"\\- Интервал между вопросами: {DAILY_QUIZ_QUESTION_INTERVAL_SECONDS // 60} минута\n\n"
                  f"Для изменения используйте `/setdailyquiztime` и `/setdailyquizcategories`\\.")
    await update.message.reply_text(reply_text, parse_mode=ParseMode.MARKDOWN_V2)

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
        state.active_daily_quizzes.pop(chat_id_str, None)
        return

    if current_q_idx >= len(questions_this_session):
        logger.info(f"Все {len(questions_this_session)} вопросов ежедневной викторины отправлены в чат {chat_id_str}.")
        state.active_daily_quizzes.pop(chat_id_str, None) 
        try:
            final_text = "🎉 Ежедневная викторина завершена! Спасибо за участие!"
            await context.bot.send_message(chat_id=chat_id_str, text=final_text)
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение о завершении ежедневной викторины в чат {chat_id_str}: {e}")
        return

    q_details = questions_this_session[current_q_idx]
    poll_question_text_for_api = q_details['question']
    full_poll_question_header = f"Ежедневная викторина! Вопрос {current_q_idx + 1}/{len(questions_this_session)}"
    if original_cat := q_details.get("original_category"):
        full_poll_question_header += f" (Кат: {original_cat})"
    full_poll_question_header += f"\n\n{poll_question_text_for_api}"

    MAX_POLL_QUESTION_LENGTH = 300 # Telegram API limit for poll question is actually 300
    if len(full_poll_question_header) > MAX_POLL_QUESTION_LENGTH:
        truncate_at = MAX_POLL_QUESTION_LENGTH - 3 
        full_poll_question_header = full_poll_question_header[:truncate_at] + "..."
        logger.warning(f"Текст вопроса ежедневной викторины для poll в чате {chat_id_str} был усечен.")

    _, poll_options, poll_correct_option_id, _ = prepare_poll_options(q_details)

    try:
        sent_poll_msg = await context.bot.send_poll(
            chat_id=chat_id_str, question=full_poll_question_header, options=poll_options,
            type='quiz', correct_option_id=poll_correct_option_id,
            open_period=DAILY_QUIZ_POLL_OPEN_PERIOD_SECONDS, is_anonymous=False
        )
        state.current_poll[sent_poll_msg.poll.id] = {
            "chat_id": chat_id_str, "message_id": sent_poll_msg.message_id,
            "correct_index": poll_correct_option_id, "quiz_session": False, 
            "daily_quiz": True, "question_details": q_details,
            "question_session_index": current_q_idx, 
            "open_timestamp": sent_poll_msg.date.timestamp()
        }
        logger.info(f"Ежедневный вопрос {current_q_idx + 1}/{len(questions_this_session)} (Poll ID: {sent_poll_msg.poll.id}) отправлен в чат {chat_id_str}.")
    except Exception as e:
        logger.error(f"Ошибка при отправке ежедневного вопроса {current_q_idx + 1} в чат {chat_id_str}: {e}", exc_info=True)
        state.active_daily_quizzes.pop(chat_id_str, None) 
        return 

    next_q_idx = current_q_idx + 1
    active_quiz_state["current_question_index"] = next_q_idx 

    job_queue: JobQueue | None = context.application.job_queue
    if not job_queue:
        logger.error(f"JobQueue не доступен в _send_one_daily_question_job для чата {chat_id_str}. Следующий вопрос не запланирован.")
        state.active_daily_quizzes.pop(chat_id_str, None)
        return

    job_data_for_next = {
        "chat_id_str": chat_id_str,
        "current_question_index": next_q_idx,
        "questions_this_session": questions_this_session,
    }

    if next_q_idx < len(questions_this_session):
        next_job_name = f"daily_quiz_q_{next_q_idx}_chat_{chat_id_str}"
        active_quiz_state["job_name_next_q"] = next_job_name
        job_queue.run_once(
            _send_one_daily_question_job,
            timedelta(seconds=DAILY_QUIZ_QUESTION_INTERVAL_SECONDS),
            data=job_data_for_next, name=next_job_name
        )
        logger.debug(f"Запланирован следующий ежедневный вопрос ({next_q_idx + 1}) для чата {chat_id_str} (job: {next_job_name}).")
    else:
        final_job_name = f"daily_quiz_finish_chat_{chat_id_str}"
        active_quiz_state["job_name_next_q"] = final_job_name 
        job_queue.run_once(
            _send_one_daily_question_job, 
            timedelta(seconds=DAILY_QUIZ_QUESTION_INTERVAL_SECONDS), 
            data=job_data_for_next, name=final_job_name
        )
        logger.debug(f"Запланирован финальный обработчик для ежедневной викторины в чате {chat_id_str} (job: {final_job_name}).")


async def _trigger_daily_quiz_for_chat_job(context: ContextTypes.DEFAULT_TYPE):
    """Запускает сессию ежедневной викторины для конкретного чата."""
    job = context.job
    if not job or not job.data:
        logger.error("_trigger_daily_quiz_for_chat_job: Job data is missing.")
        return

    chat_id_str: str = job.data["chat_id_str"]

    if chat_id_str not in state.daily_quiz_subscriptions:
        logger.info(f"Ежедневная викторина для чата {chat_id_str} не будет запущена, т.к. чат отписан (job сработал после отписки).")
        return

    if chat_id_str in state.active_daily_quizzes:
        logger.warning(f"Попытка запустить ежедневную викторину для чата {chat_id_str}, но она уже активна. Пропуск.")
        return

    questions_for_quiz, picked_categories = _get_questions_for_daily_quiz(
        chat_id_str=chat_id_str,
        num_questions=DAILY_QUIZ_QUESTIONS_COUNT,
        default_num_categories_to_pick=DAILY_QUIZ_CATEGORIES_TO_PICK
    )

    if not questions_for_quiz:
        logger.warning(f"Не удалось получить вопросы для ежедневной викторины в чате {chat_id_str}. Викторина не будет запущена.")
        try:
            error_text = "Не удалось подготовить вопросы для сегодняшней ежедневной викторины (возможно, выбранные категории пусты или не существуют). Попробуем завтра!"
            await context.bot.send_message(chat_id=chat_id_str, text=error_text)
        except Exception as e:
            logger.error(f"Не удалось уведомить чат {chat_id_str} об ошибке подготовки ежедневной викторины: {e}")
        return

    intro_message_parts = [
        f"🌞 Доброе утро! Начинаем ежедневную викторину ({len(questions_for_quiz)} вопросов)!",
        f"Сегодняшние категории: <b>{', '.join(picked_categories) if picked_categories else 'Случайные'}</b>.",
        f"Один вопрос каждую минуту. Каждый вопрос будет доступен {DAILY_QUIZ_POLL_OPEN_PERIOD_SECONDS // 60} минут."
    ]
    intro_text = "\n".join(intro_message_parts)

    try:
        await context.bot.send_message(chat_id=chat_id_str, text=intro_text, parse_mode=ParseMode.HTML)
        logger.info(f"Ежедневная викторина инициирована для чата {chat_id_str} с {len(questions_for_quiz)} вопросами из категорий: {picked_categories}.")
    except Exception as e:
        logger.error(f"Не удалось отправить стартовое сообщение ежедневной викторины в чат {chat_id_str}: {e}", exc_info=True)
        return 

    state.active_daily_quizzes[chat_id_str] = {
        "current_question_index": 0, "questions": questions_for_quiz,
        "picked_categories": picked_categories, "job_name_next_q": None
    }

    job_queue: JobQueue | None = context.application.job_queue
    if job_queue:
        first_q_job_name = f"daily_quiz_q_0_chat_{chat_id_str}"
        state.active_daily_quizzes[chat_id_str]["job_name_next_q"] = first_q_job_name
        job_queue.run_once(
            _send_one_daily_question_job,
            timedelta(seconds=5), 
            data={
                "chat_id_str": chat_id_str, "current_question_index": 0,
                "questions_this_session": questions_for_quiz,
            },
            name=first_q_job_name
        )
        logger.debug(f"Запланирован первый вопрос ежедневной викторины для чата {chat_id_str} (job: {first_q_job_name}).")
    else:
        logger.error(f"JobQueue не доступен в _trigger_daily_quiz_for_chat_job для чата {chat_id_str}. Викторина не начнется.")
        state.active_daily_quizzes.pop(chat_id_str, None)