# handlers/daily_quiz_handlers.py
import random
import re
from datetime import timedelta, time, datetime # Added datetime
from typing import Tuple, Optional, List, Dict, Any

import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup # Added Inline...
from telegram.ext import ContextTypes, JobQueue, Application
from telegram.constants import ChatMemberStatus, ParseMode

from config import (logger, DAILY_QUIZ_QUESTIONS_COUNT,
                    DAILY_QUIZ_CATEGORIES_TO_PICK, DAILY_QUIZ_POLL_OPEN_PERIOD_SECONDS,
                    DAILY_QUIZ_QUESTION_INTERVAL_SECONDS, DAILY_QUIZ_DEFAULT_HOUR_MSK,
                    DAILY_QUIZ_DEFAULT_MINUTE_MSK, DAILY_QUIZ_MAX_CUSTOM_CATEGORIES,
                    CALLBACK_DATA_PREFIX_DAILY_QUIZ_CATEGORY_SHORT, # New import
                    CALLBACK_DATA_DAILY_QUIZ_RANDOM_CATEGORY) # New import
import state
from data_manager import save_daily_quiz_subscriptions
from quiz_logic import prepare_poll_options
from handlers.rating_handlers import get_player_display # For top-10 message
from utils import pluralize_points # For top-10 message, if get_player_display doesn't fully cover

# --- Вспомогательные функции ---

def moscow_time(hour: int, minute: int) -> time:
    """Создает объект datetime.time для указанного часа и минуты по Московскому времени."""
    moscow_tz = pytz.timezone('Europe/Moscow')
    return time(hour=hour, minute=minute, tzinfo=moscow_tz)

async def _is_user_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.effective_chat or not update.effective_user:
        return False
    if update.effective_chat.type == 'private':
        return True
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception as e:
        logger.warning(f"Ошибка проверки статуса администратора для {update.effective_user.id} в {update.effective_chat.id}: {e}")
        return False

def _parse_time_hh_mm(time_str: str) -> Optional[Tuple[int, int]]:
    match_hh_mm = re.fullmatch(r"(\d{1,2})[:.](\d{1,2})", time_str)
    if match_hh_mm:
        h_str, m_str = match_hh_mm.groups()
        try:
            h, m = int(h_str), int(m_str)
            if 0 <= h <= 23 and 0 <= m <= 59: return h, m
        except ValueError: pass
        return None
    match_hh = re.fullmatch(r"(\d{1,2})", time_str)
    if match_hh:
        h_str = match_hh.group(1)
        try:
            h = int(h_str)
            if 0 <= h <= 23: return h, 0
        except ValueError: pass
    return None

async def _schedule_or_reschedule_daily_quiz_for_chat(application: Application, chat_id_str: str):
    job_queue: JobQueue | None = application.job_queue
    if not job_queue:
        logger.error(f"JobQueue не доступен. Не удалось (пере)запланировать ежедневную викторину для чата {chat_id_str}.")
        return

    subscription_details = state.daily_quiz_subscriptions.get(chat_id_str)
    job_name = f"daily_quiz_trigger_chat_{chat_id_str}"

    existing_jobs = job_queue.get_jobs_by_name(job_name)
    if existing_jobs:
        for job in existing_jobs: job.schedule_removal()
        logger.debug(f"Удален(ы) существующий(е) job(s) '{job_name}' для чата {chat_id_str} перед (пере)планированием.")

    if not subscription_details:
        logger.info(f"Подписка для чата {chat_id_str} не активна. Викторина не будет запланирована.")
        return

    hour = subscription_details.get("hour", DAILY_QUIZ_DEFAULT_HOUR_MSK)
    minute = subscription_details.get("minute", DAILY_QUIZ_DEFAULT_MINUTE_MSK)
    target_time_msk = moscow_time(hour, minute)
    job_queue.run_daily(
        _trigger_daily_quiz_for_chat_job, time=target_time_msk,
        data={"chat_id_str": chat_id_str}, name=job_name
    )
    logger.info(f"Ежедневная викторина для чата {chat_id_str} запланирована на {hour:02d}:{minute:02d} МСК (job: {job_name}).")

def _get_questions_for_daily_quiz(
    chat_id_str: str, num_questions: int = DAILY_QUIZ_QUESTIONS_COUNT,
    default_num_categories_to_pick: int = DAILY_QUIZ_CATEGORIES_TO_PICK
) -> tuple[list[dict], list[str]]:
    if not state.quiz_data: return [], []
    available_categories_with_questions = { cat_name: q_list for cat_name, q_list in state.quiz_data.items() if q_list }
    if not available_categories_with_questions: return [], []

    subscription_details = state.daily_quiz_subscriptions.get(chat_id_str, {})
    custom_categories_names: Optional[List[str]] = subscription_details.get("categories")
    chosen_categories_for_quiz: List[str] = []

    if custom_categories_names:
        valid_custom_categories = [name for name in custom_categories_names if name in available_categories_with_questions]
        if valid_custom_categories: chosen_categories_for_quiz = valid_custom_categories
        else: logger.warning(f"Указанные кастомные категории для чата {chat_id_str} недействительны/пусты. Выбор случайных.")
    
    if not chosen_categories_for_quiz:
        num_to_sample_random = min(default_num_categories_to_pick, len(available_categories_with_questions))
        if num_to_sample_random > 0:
            chosen_categories_for_quiz = random.sample(list(available_categories_with_questions.keys()), num_to_sample_random)
        else: return [], [] 
    
    picked_category_names_final = chosen_categories_for_quiz
    all_questions_from_picked: list[dict] = [q.copy() for cat_name in picked_category_names_final for q in available_categories_with_questions.get(cat_name, [])]
    if not all_questions_from_picked: return [], picked_category_names_final
    
    random.shuffle(all_questions_from_picked)
    questions_for_quiz = all_questions_from_picked[:num_questions]
    logger.info(f"Для ежедневной викторины в {chat_id_str} отобрано {len(questions_for_quiz)} вопросов из: {picked_category_names_final}.")
    return questions_for_quiz, picked_category_names_final

# --- Обработчики команд ---
async def subscribe_daily_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user: return
    chat_id_str = str(update.effective_chat.id)
    if not await _is_user_admin(update, context):
        await update.message.reply_text("Только администраторы могут подписать чат на ежедневную викторину.")
        return

    if chat_id_str in state.daily_quiz_subscriptions:
        sub_details = state.daily_quiz_subscriptions[chat_id_str]
        time_str = f"{sub_details.get('hour', DAILY_QUIZ_DEFAULT_HOUR_MSK):02d}:{sub_details.get('minute', DAILY_QUIZ_DEFAULT_MINUTE_MSK):02d} МСК"
        cats = sub_details.get("categories")
        cat_str = f"категориям: {', '.join(cats)}" if cats else "случайным категориям"
        reply_text = (f"Этот чат уже подписан\\.\nВремя: *{time_str}*\\. Категории: *{cat_str}*\\.")
    else:
        state.daily_quiz_subscriptions[chat_id_str] = {
            "hour": DAILY_QUIZ_DEFAULT_HOUR_MSK, "minute": DAILY_QUIZ_DEFAULT_MINUTE_MSK, "categories": None
        }
        save_daily_quiz_subscriptions()
        await _schedule_or_reschedule_daily_quiz_for_chat(context.application, chat_id_str)
        reply_text = (f"✅ Чат подписан на ежедневную викторину\\!\nВремя: *{DAILY_QUIZ_DEFAULT_HOUR_MSK:02d}:{DAILY_QUIZ_DEFAULT_MINUTE_MSK:02d} МСК* \\(по умолч\\.\\)\\.\n"
                      f"Категории: *{DAILY_QUIZ_CATEGORIES_TO_PICK} случайных* \\(по умолч\\.\\)\\.\n"
                      f"Используйте `/setdailyquiztime` и `/setdailyquizcategories` для настройки\\.")
        logger.info(f"Чат {chat_id_str} подписан на ежедневную викторину.")
    await update.message.reply_text(reply_text, parse_mode=ParseMode.MARKDOWN_V2)

async def unsubscribe_daily_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user: return
    chat_id_str = str(update.effective_chat.id)
    if not await _is_user_admin(update, context):
        await update.message.reply_text("Только администраторы могут отписать чат.")
        return

    if chat_id_str in state.daily_quiz_subscriptions:
        state.daily_quiz_subscriptions.pop(chat_id_str, None)
        save_daily_quiz_subscriptions()
        await _schedule_or_reschedule_daily_quiz_for_chat(context.application, chat_id_str)
        await update.message.reply_text("Чат отписан от ежедневной викторины.")
        logger.info(f"Чат {chat_id_str} отписан от ежедневной викторины.")
    else:
        await update.message.reply_text("Чат не был подписан.")

async def set_daily_quiz_time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user: return
    chat_id_str = str(update.effective_chat.id)
    if not await _is_user_admin(update, context):
        await update.message.reply_text("Только администраторы могут изменять время.")
        return
    if chat_id_str not in state.daily_quiz_subscriptions:
        await update.message.reply_text("Чат не подписан. Сначала /subdaily.")
        return
    if not context.args:
        await update.message.reply_text("Использование: /setdailyquiztime HH:MM (МСК).")
        return

    parsed_time = _parse_time_hh_mm(context.args[0])
    if parsed_time is None:
        await update.message.reply_text("Неверный формат времени. Используйте HH:MM (МСК).")
        return

    hour, minute = parsed_time
    state.daily_quiz_subscriptions[chat_id_str]["hour"] = hour
    state.daily_quiz_subscriptions[chat_id_str]["minute"] = minute
    save_daily_quiz_subscriptions()
    await _schedule_or_reschedule_daily_quiz_for_chat(context.application, chat_id_str)
    await update.message.reply_text(f"Время ежедневной викторины установлено на {hour:02d}:{minute:02d} МСК.")
    logger.info(f"Время ежедневной викторины для {chat_id_str} изменено на {hour:02d}:{minute:02d} МСК.")

async def set_daily_quiz_categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user: return
    chat_id_str = str(update.effective_chat.id)

    if not await _is_user_admin(update, context):
        await update.message.reply_text("Только администраторы могут изменять категории.")
        return
    if chat_id_str not in state.daily_quiz_subscriptions:
        await update.message.reply_text("Чат не подписан. Сначала /subdaily.")
        return
    if not state.quiz_data:
        await update.message.reply_text("Вопросы не загружены. Невозможно установить категории.")
        return

    # Если переданы аргументы, обрабатываем их как раньше
    if context.args:
        available_cat_names_map = {name.lower(): name for name, q_list in state.quiz_data.items() if q_list}
        chosen_categories_raw = context.args
        valid_chosen_categories_canonical = []
        invalid_or_empty_categories_input = []

        for cat_name_arg in chosen_categories_raw:
            canonical_name = available_cat_names_map.get(cat_name_arg.lower())
            if canonical_name and canonical_name not in valid_chosen_categories_canonical:
                valid_chosen_categories_canonical.append(canonical_name)
            else:
                invalid_or_empty_categories_input.append(cat_name_arg)
        
        if len(valid_chosen_categories_canonical) > DAILY_QUIZ_MAX_CUSTOM_CATEGORIES:
            await update.message.reply_text(f"Можно выбрать до {DAILY_QUIZ_MAX_CUSTOM_CATEGORIES} категорий.")
            return
        
        state.daily_quiz_subscriptions[chat_id_str]["categories"] = valid_chosen_categories_canonical or None
        save_daily_quiz_subscriptions()
        
        reply_parts = []
        if valid_chosen_categories_canonical:
            reply_parts.append(f"Категории установлены: {', '.join(valid_chosen_categories_canonical)}.")
        else: # Если все введенные были невалидны, но args были
            reply_parts.append(f"Указанные категории не найдены. Будут использованы случайные.")
        if invalid_or_empty_categories_input:
            reply_parts.append(f"\nПредупреждение: категории '{', '.join(invalid_or_empty_categories_input)}' не найдены/пусты.")
        await update.message.reply_text(" ".join(reply_parts))
        logger.info(f"Категории для {chat_id_str} изменены на {valid_chosen_categories_canonical or 'случайные'} через аргументы.")
    
    # Если аргументов нет, показываем меню выбора одной категории или случайных
    else:
        available_categories = [cat_name for cat_name, q_list in state.quiz_data.items() if isinstance(q_list, list) and q_list]
        if not available_categories:
            await update.message.reply_text("Нет доступных категорий для выбора.")
            return

        keyboard = []
        category_map_for_callback: Dict[str, str] = {}
        # Ограничим количество кнопок, чтобы сообщение не стало слишком большим
        MAX_CATEGORIES_IN_MENU = 20 
        sorted_cats = sorted(available_categories)
        
        for i, cat_name in enumerate(sorted_cats[:MAX_CATEGORIES_IN_MENU]):
            short_id = f"dqc{i}" # Daily Quiz Category
            category_map_for_callback[short_id] = cat_name
            callback_data = f"{CALLBACK_DATA_PREFIX_DAILY_QUIZ_CATEGORY_SHORT}{short_id}"
            if len(callback_data.encode('utf-8')) > 64:
                 logger.error(f"Сгенерированный callback_data '{callback_data}' для категории '{cat_name}' (ежедн.) слишком длинный!")
                 continue
            keyboard.append([InlineKeyboardButton(cat_name, callback_data=callback_data)])
        
        if len(sorted_cats) > MAX_CATEGORIES_IN_MENU:
             keyboard.append([InlineKeyboardButton(f"Еще {len(sorted_cats) - MAX_CATEGORIES_IN_MENU} категорий (используйте ввод)", callback_data="dq_info_too_many_cats")])


        keyboard.append([InlineKeyboardButton("🎲 Случайные категории", callback_data=CALLBACK_DATA_DAILY_QUIZ_RANDOM_CATEGORY)])
        reply_markup = InlineKeyboardMarkup(keyboard)

        chat_data_key = f"daily_quiz_cat_map_{chat_id_str}"
        context.chat_data[chat_data_key] = category_map_for_callback
        
        current_selection = state.daily_quiz_subscriptions[chat_id_str].get("categories")
        current_selection_str = ""
        if current_selection:
            current_selection_str = f"\nТекущий выбор: *{', '.join(current_selection)}*\\."
        else:
            current_selection_str = "\nТекущий выбор: *случайные категории*\\."

        msg_text = (f"Выберите *одну* категорию для ежедневной викторины, или случайный набор{current_selection_str}\n"
                    f"Для выбора *нескольких* категорий \\(до {DAILY_QUIZ_MAX_CUSTOM_CATEGORIES}\\), используйте команду с названиями через пробел, например:\n"
                    f"`/setdailyquizcategories Категория1 Категория2`")
        
        await update.message.reply_text(msg_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)

async def handle_daily_quiz_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query: return
    await query.answer()

    if not query.message or not query.message.chat or not query.from_user: return

    chat_id_str = str(query.message.chat.id)
    # user_id = query.from_user.id # Не используется здесь, но может быть полезно для логов

    if query.data == "dq_info_too_many_cats": # Просто информационная кнопка
        await query.edit_message_text(text=query.message.text + "\n\n(Для выбора категорий не из списка, введите их названия с командой).", reply_markup=None)
        return

    chat_data_key = f"daily_quiz_cat_map_{chat_id_str}"
    category_map_for_callback: Dict[str, str] | None = context.chat_data.pop(chat_data_key, None)

    if category_map_for_callback is None and query.data != CALLBACK_DATA_DAILY_QUIZ_RANDOM_CATEGORY:
        # Если карта не найдена, но это не "случайные", то это, вероятно, старая кнопка
        await query.edit_message_text("Ошибка: время выбора категории истекло. Попробуйте снова /setdailyquizcategories.", reply_markup=None)
        return

    new_categories_selection: Optional[List[str]] = None
    message_text_after_selection = ""

    if query.data == CALLBACK_DATA_DAILY_QUIZ_RANDOM_CATEGORY:
        new_categories_selection = None
        message_text_after_selection = "Для ежедневной викторины будут использоваться случайные категории."
    elif query.data and query.data.startswith(CALLBACK_DATA_PREFIX_DAILY_QUIZ_CATEGORY_SHORT):
        short_id = query.data[len(CALLBACK_DATA_PREFIX_DAILY_QUIZ_CATEGORY_SHORT):]
        if category_map_for_callback: # Убедимся, что карта есть
            selected_category_name = category_map_for_callback.get(short_id)
            if selected_category_name:
                new_categories_selection = [selected_category_name]
                message_text_after_selection = f"Для ежедневной викторины выбрана категория: {selected_category_name}."
            else:
                message_text_after_selection = "Ошибка при выборе категории (ID не найден). Настройки не изменены."
        else: # Карта должна была быть, если это не random
             message_text_after_selection = "Ошибка: карта категорий не найдена. Попробуйте снова."
    else:
        message_text_after_selection = "Произошла неизвестная ошибка выбора. Настройки не изменены."

    if chat_id_str in state.daily_quiz_subscriptions:
        # Только обновляем, если selection действительно изменился или был установлен
        if message_text_after_selection.startswith("Для ежедневной викторины выбрана") or \
           message_text_after_selection.startswith("Для ежедневной викторины будут использоваться случайные"):
            state.daily_quiz_subscriptions[chat_id_str]["categories"] = new_categories_selection
            save_daily_quiz_subscriptions()
            logger.info(f"Категории для ежедневной викторины в чате {chat_id_str} изменены на {new_categories_selection or 'случайные'} через меню.")
    else:
        message_text_after_selection = "Ошибка: чат не подписан на ежедневную викторину. Настройки не сохранены."


    try: await query.edit_message_text(text=message_text_after_selection, reply_markup=None)
    except Exception: pass # Ignore if message too old or not modified

async def show_daily_quiz_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat: return
    chat_id_str = str(update.effective_chat.id)

    if chat_id_str not in state.daily_quiz_subscriptions:
        await update.message.reply_text("Чат не подписан. /subdaily для подписки.")
        return

    settings = state.daily_quiz_subscriptions[chat_id_str]
    hour = settings.get("hour", DAILY_QUIZ_DEFAULT_HOUR_MSK)
    minute = settings.get("minute", DAILY_QUIZ_DEFAULT_MINUTE_MSK)
    custom_categories: Optional[List[str]] = settings.get("categories")
    time_str = f"{hour:02d}:{minute:02d} МСК"
    categories_str = f"Выбранные: {', '.join(custom_categories)}" if custom_categories else f"Случайные ({DAILY_QUIZ_CATEGORIES_TO_PICK} категории)"

    reply_text = (f"⚙️ Настройки ежедневной викторины:\n"
                  f"\\- Время: *{time_str}*\n"
                  f"\\- Категории: *{categories_str}*\n"
                  f"\\- Вопросов: {DAILY_QUIZ_QUESTIONS_COUNT}\n"
                  f"Используйте `/setdailyquiztime` и `/setdailyquizcategories` для изменения\\.")
    await update.message.reply_text(reply_text, parse_mode=ParseMode.MARKDOWN_V2)

# --- Логика запланированных задач (Jobs) ---

async def _send_one_daily_question_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    if not job or not job.data: logger.error("_send_one_daily_question_job: Job data missing."); return

    chat_id_str: str = job.data["chat_id_str"]
    current_q_idx: int = job.data["current_question_index"]
    questions_this_session: list[dict] = job.data["questions_this_session"]

    active_quiz_state = state.active_daily_quizzes.get(chat_id_str)
    if not active_quiz_state or active_quiz_state.get("current_question_index") != current_q_idx:
        logger.warning(f"Ежедневная викторина для {chat_id_str} прервана/состояние не совпадает. Остановка отправки вопроса {current_q_idx + 1}.")
        state.active_daily_quizzes.pop(chat_id_str, None)
        return

    if current_q_idx >= len(questions_this_session):
        logger.info(f"Все {len(questions_this_session)} вопросов ежедневной викторины отправлены в {chat_id_str}.")
        state.active_daily_quizzes.pop(chat_id_str, None)
        
        final_text_parts = ["🎉 Ежедневная викторина завершена! Спасибо за участие!"]
        
        # Формирование топ-10 для чата
        if chat_id_str in state.user_scores and state.user_scores[chat_id_str]:
            sorted_scores_list = sorted(
                state.user_scores[chat_id_str].items(),
                key=lambda item: (-item[1].get("score", 0), item[1].get("name", "").lower())
            )
            if sorted_scores_list:
                final_text_parts.append("\n\n🏆 Топ-10 игроков этого чата на данный момент:")
                for i, (user_id, data) in enumerate(sorted_scores_list[:10]):
                    player_name = data.get('name', f'Игрок {user_id}')
                    player_score = data.get('score', 0)
                    rank_prefix = f"{i+1}."
                    if player_score > 0: # Медальки только за положительный счет
                        if i == 0: rank_prefix = "🥇"
                        elif i == 1: rank_prefix = "🥈"
                        elif i == 2: rank_prefix = "🥉"
                    final_text_parts.append(f"{rank_prefix} {get_player_display(player_name, player_score)}") # Используем get_player_display
            else:
                final_text_parts.append("\n\nВ этом чате пока нет игроков с очками.")
        else:
            final_text_parts.append("\n\nВ этом чате пока нет статистики игроков.")

        try:
            await context.bot.send_message(chat_id=chat_id_str, text="\n".join(final_text_parts))
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение о завершении ежедневной викторины в {chat_id_str}: {e}")
        return

    q_details = questions_this_session[current_q_idx]
    poll_question_text_for_api = q_details['question']
    full_poll_question_header = f"Ежедневная викторина! Вопрос {current_q_idx + 1}/{len(questions_this_session)}"
    if original_cat := q_details.get("original_category"): full_poll_question_header += f" (Кат: {original_cat})"
    full_poll_question_header += f"\n\n{poll_question_text_for_api}"

    MAX_POLL_QUESTION_LENGTH = 300
    if len(full_poll_question_header) > MAX_POLL_QUESTION_LENGTH:
        full_poll_question_header = full_poll_question_header[:(MAX_POLL_QUESTION_LENGTH - 3)] + "..."
        logger.warning(f"Текст вопроса ежедневной викторины для poll в {chat_id_str} усечен.")

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
        logger.info(f"Ежедневный вопрос {current_q_idx + 1}/{len(questions_this_session)} (Poll ID: {sent_poll_msg.poll.id}) отправлен в {chat_id_str}.")
    except Exception as e:
        logger.error(f"Ошибка отправки ежедневного вопроса {current_q_idx + 1} в {chat_id_str}: {e}", exc_info=True)
        state.active_daily_quizzes.pop(chat_id_str, None)
        return

    next_q_idx = current_q_idx + 1
    active_quiz_state["current_question_index"] = next_q_idx
    job_queue: JobQueue | None = context.application.job_queue
    if not job_queue: logger.error(f"JobQueue не доступен в _send_one_daily_question_job для {chat_id_str}."); state.active_daily_quizzes.pop(chat_id_str, None); return

    job_data_for_next = { "chat_id_str": chat_id_str, "current_question_index": next_q_idx, "questions_this_session": questions_this_session }
    
    next_job_base_name = f"daily_quiz_q_{next_q_idx}" if next_q_idx < len(questions_this_session) else "daily_quiz_finish"
    next_job_name = f"{next_job_base_name}_chat_{chat_id_str}"
    
    active_quiz_state["job_name_next_q"] = next_job_name
    job_queue.run_once(
        _send_one_daily_question_job, timedelta(seconds=DAILY_QUIZ_QUESTION_INTERVAL_SECONDS),
        data=job_data_for_next, name=next_job_name
    )
    logger.debug(f"Запланирован следующий этап ежедневной викторины для {chat_id_str} (job: {next_job_name}).")


async def _trigger_daily_quiz_for_chat_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    if not job or not job.data: logger.error("_trigger_daily_quiz_for_chat_job: Job data missing."); return
    chat_id_str: str = job.data["chat_id_str"]

    if chat_id_str not in state.daily_quiz_subscriptions:
        logger.info(f"Ежедневная викторина для {chat_id_str} не запущена (чат отписан).")
        return
    if chat_id_str in state.active_daily_quizzes:
        logger.warning(f"Попытка запустить ежедневную викторину для {chat_id_str}, но она уже активна.")
        return
    if state.current_quiz_session.get(chat_id_str) or state.pending_scheduled_quizzes.get(chat_id_str):
        logger.warning(f"Попытка запустить ежедневную викторину для {chat_id_str}, но активна/запланирована /quiz10 сессия.")
        try:
            await context.bot.send_message(chat_id=chat_id_str, text="Не удалось начать ежедневную викторину: сейчас активна или запланирована другая викторина (/quiz10).")
        except Exception: pass
        return


    questions_for_quiz, picked_categories = _get_questions_for_daily_quiz(
        chat_id_str=chat_id_str, num_questions=DAILY_QUIZ_QUESTIONS_COUNT,
        default_num_categories_to_pick=DAILY_QUIZ_CATEGORIES_TO_PICK
    )
    if not questions_for_quiz:
        logger.warning(f"Не удалось получить вопросы для ежедневной викторины в {chat_id_str}.")
        try: await context.bot.send_message(chat_id=chat_id_str, text="Не удалось подготовить вопросы для ежедневной викторины. Попробуем завтра!")
        except Exception: pass
        return

    # Determine greeting based on Moscow time
    now_moscow = datetime.now(pytz.timezone('Europe/Moscow'))
    current_hour_moscow = now_moscow.hour
    greeting = ""
    if 0 <= current_hour_moscow <= 5: greeting = "🌙 Доброй ночи!"
    elif 6 <= current_hour_moscow <= 11: greeting = "☀️ Доброе утро!"
    elif 12 <= current_hour_moscow <= 17: greeting = "🌞 Добрый день!"
    else: greeting = "🌆 Добрый вечер!"

    intro_message_parts = [
        f"{greeting} Начинаем ежедневную викторину ({len(questions_for_quiz)} вопросов)!",
        f"Сегодняшние категории: <b>{', '.join(picked_categories) if picked_categories else 'Случайные'}</b>.",
        f"Один вопрос каждую минуту. Каждый вопрос будет доступен {DAILY_QUIZ_POLL_OPEN_PERIOD_SECONDS // 60} минут."
    ]
    intro_text = "\n".join(intro_message_parts)

    try:
        await context.bot.send_message(chat_id=chat_id_str, text=intro_text, parse_mode=ParseMode.HTML)
        logger.info(f"Ежедневная викторина инициирована для {chat_id_str} ({len(questions_for_quiz)} вопр. из: {picked_categories}).")
    except Exception as e:
        logger.error(f"Не удалось отправить стартовое сообщение ежедневной викторины в {chat_id_str}: {e}", exc_info=True)
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
            _send_one_daily_question_job, timedelta(seconds=5), # Short delay before first question
            data={ "chat_id_str": chat_id_str, "current_question_index": 0, "questions_this_session": questions_for_quiz, },
            name=first_q_job_name
        )
        logger.debug(f"Запланирован первый вопрос ежедневной викторины для {chat_id_str} (job: {first_q_job_name}).")
    else:
        logger.error(f"JobQueue не доступен в _trigger_daily_quiz_for_chat_job для {chat_id_str}. Викторина не начнется.")
        state.active_daily_quizzes.pop(chat_id_str, None)
