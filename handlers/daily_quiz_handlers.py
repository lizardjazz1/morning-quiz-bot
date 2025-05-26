# handlers/daily_quiz_handlers.py
import random
import re
from datetime import timedelta, time
from typing import Tuple, Optional, List, Dict, Any

import pytz
from telegram import Update
from telegram.ext import ContextTypes, JobQueue, Application
from telegram.constants import ChatMemberStatus, ParseMode

from config import (logger, DQ_QS_COUNT, DQ_CATS_PICK, DQ_POLL_OPEN_S, # Renamed constants
                    DQ_Q_INTERVAL_S, DQ_DEF_H, DQ_DEF_M, DQ_MAX_CUST_CATS)
import state
from data_manager import save_daily_q_subs # Renamed function
from quiz_logic import prep_poll_opts # Renamed function
from handlers.common_handlers import md_escape # Import new md_escape

# --- Вспомогательные функции ---

def msk_time(hour: int, minute: int) -> time: # Renamed
    return time(hour=hour, minute=minute, tzinfo=pytz.timezone('Europe/Moscow'))

async def _is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool: # Renamed
    if not update.effective_chat or not update.effective_user: return False
    if update.effective_chat.type == 'private': return True # In private chat, user is effectively admin
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception as e:
        logger.warning(f"Ошибка проверки админа {update.effective_user.id} в {update.effective_chat.id}: {e}")
        return False

def _parse_hhmm(time_str: str) -> Optional[Tuple[int, int]]: # Renamed
    match_hm = re.fullmatch(r"(\d{1,2})[:.](\d{1,2})", time_str) # Renamed
    if match_hm:
        h_str, m_str = match_hm.groups()
        try: 
            h, m = int(h_str), int(m_str)
            return (h,m) if 0<=h<=23 and 0<=m<=59 else None
        except ValueError: pass # Will fall through to return None
        return None # Should be unreachable if try succeeds or fails with ValueError
    match_h = re.fullmatch(r"(\d{1,2})", time_str) # Renamed
    if match_h:
        try: 
            h = int(match_h.group(1))
            return (h,0) if 0<=h<=23 else None # Default minute to 0 if only hour is provided
        except ValueError: pass
    return None

async def _sched_daily_q_chat(app: Application, cid_str: str): # Renamed app from application
    jq: JobQueue | None = app.job_queue # Renamed
    if not jq:
        logger.error(f"JobQueue нет. Не удалось (пере)запланировать DQ для {cid_str}.") # DQ for Daily Quiz
        return

    sub_details = state.daily_q_subs.get(cid_str) # Renamed
    job_name = f"dq_trigger_chat_{cid_str}" # Shorter

    # Remove any existing jobs with this name first
    existing_jobs = jq.get_jobs_by_name(job_name)
    for job in existing_jobs: 
        job.schedule_removal()
    if existing_jobs: # Check if list not empty before logging
        logger.debug(f"Удалены существующие job(s) '{job_name}' для {cid_str} перед перепланированием.")

    if not sub_details: # If subscription was removed
        logger.info(f"Подписка для {cid_str} не активна или удалена. DQ не запланирован.")
        return

    hour = sub_details.get("hour", DQ_DEF_H)
    minute = sub_details.get("minute", DQ_DEF_M)

    target_t = msk_time(hour, minute) # Renamed
    jq.run_daily(_trigger_daily_q_job_cb, time=target_t, data={"chat_id_str": cid_str}, name=job_name) # Renamed
    logger.info(f"DQ для {cid_str} запланирован на {hour:02d}:{minute:02d} МСК (job: {job_name}).")

def _get_daily_qs(cid_str: str, num_qs: int = DQ_QS_COUNT, def_cats_pick: int = DQ_CATS_PICK) -> tuple[list[dict], list[str]]: # Renamed
    qs_for_quiz: list[dict] = []
    picked_cats_final: list[str] = [] # Renamed

    if not state.qs_data:
        logger.warning("Нет загруженных вопросов (state.qs_data) для DQ.")
        return [], []
    
    # Filter out empty categories right away
    avail_cats_w_qs = { name: ql for name, ql in state.qs_data.items() if ql and isinstance(ql, list) } # Renamed

    if not avail_cats_w_qs:
        logger.warning("Нет категорий с вопросами для DQ.")
        return [], []

    sub_details = state.daily_q_subs.get(cid_str, {})
    cust_cats_cfg: Optional[List[str]] = sub_details.get("categories") # Renamed

    chosen_cats: List[str] = [] # Renamed

    if cust_cats_cfg: # User has specified custom categories
        valid_cust_cats = [name for name in cust_cats_cfg if name in avail_cats_w_qs] # Renamed
        if valid_cust_cats:
            chosen_cats = valid_cust_cats
            logger.info(f"Для DQ в {cid_str} используются кастомные категории: {chosen_cats}")
        else:
            logger.warning(f"Для DQ в {cid_str} указанные кастомные категории {cust_cats_cfg} недействительны или пусты. Выбор случайных.")
            # Fall through to random selection if custom ones are invalid

    if not chosen_cats: # No valid custom categories, or none specified, so pick randomly
        num_sample_rnd = min(def_cats_pick, len(avail_cats_w_qs)) # Renamed
        if num_sample_rnd > 0:
            chosen_cats = random.sample(list(avail_cats_w_qs.keys()), num_sample_rnd)
        else: # Should not happen if avail_cats_w_qs is not empty
            logger.warning(f"Не удалось выбрать случайные категории для DQ в {cid_str} (num_sample_rnd={num_sample_rnd}).")
            return [], [] # Return empty if no categories could be chosen
        logger.info(f"Для DQ в {cid_str} выбраны случайные категории: {chosen_cats}")

    picked_cats_final = chosen_cats
    all_qs_picked_cats: list[dict] = [] # Renamed
    for cat_name in picked_cats_final:
        # Ensure questions are copied to prevent modification of original data
        all_qs_picked_cats.extend([q.copy() for q in avail_cats_w_qs.get(cat_name, [])])


    if not all_qs_picked_cats:
        logger.warning(f"Выбранные категории {picked_cats_final} для DQ в {cid_str} не содержат вопросов (неожиданно).")
        return [], picked_cats_final # Return chosen categories even if no questions found (for logging)

    random.shuffle(all_qs_picked_cats)
    qs_for_quiz = all_qs_picked_cats[:num_qs] # Take up to num_qs questions
    logger.info(f"Для DQ в {cid_str} отобрано {len(qs_for_quiz)} вопросов из категорий: {picked_cats_final}.")
    return qs_for_quiz, picked_cats_final

# --- Обработчики команд ---
async def subscribe_daily_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user: return
    cid_str = str(update.effective_chat.id)
    if not await _is_admin(update, context):
        await update.message.reply_text("Только администраторы могут подписать чат на ежедневную викторину.")
        return

    if cid_str in state.daily_q_subs:
        sub = state.daily_q_subs[cid_str] # Renamed
        time_str = f"{sub.get('hour', DQ_DEF_H):02d}:{sub.get('minute', DQ_DEF_M):02d} МСК"
        cats_list = sub.get("categories")
        # Correctly escape category names for MarkdownV2
        cat_str = f"категориям: {', '.join([md_escape(c) for c in cats_list])}" if cats_list else "случайным категориям" # md_escape here
        
        reply_txt = (f"Чат уже подписан на ежедневную викторину\\.\n"
                      f"Время: *{md_escape(time_str)}*\\.\nКатегории: *{cat_str}*\\.\n"
                      f"Используйте `/setdailyquiztime` и `/setdailyquizcategories` для изменения\\.")
    else:
        state.daily_q_subs[cid_str] = {"hour": DQ_DEF_H, "minute": DQ_DEF_M, "categories": None}
        save_daily_q_subs()
        await _sched_daily_q_chat(context.application, cid_str) # Reschedule
        reply_txt = (f"✅ Чат подписан на ежедневную викторину\\!\n"
                      f"Время по умолчанию: *{DQ_DEF_H:02d}:{DQ_DEF_M:02d} МСК*\\.\n"
                      f"Категории по умолчанию: *{DQ_CATS_PICK} случайных*\\.\n"
                      f"Будет {DQ_QS_COUNT} вопросов, по одному примерно каждые {DQ_Q_INTERVAL_S // 60} мин\\.\n"
                      f"Каждый опрос будет открыт {DQ_POLL_OPEN_S // 60} мин\\.\n\n"
                      f"Для настройки используйте:\n`/setdailyquiztime HH:MM`\n"
                      f"`/setdailyquizcategories [названия категорий]`\n"
                      f"`/showdailyquizsettings`")
        logger.info(f"Чат {cid_str} подписан на DQ юзером {update.effective_user.id}.")
    await update.message.reply_text(reply_txt, parse_mode=ParseMode.MARKDOWN_V2)


async def unsubscribe_daily_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user: return
    cid_str = str(update.effective_chat.id)
    if not await _is_admin(update, context):
        await update.message.reply_text("Только администраторы могут отписать чат от ежедневной викторины.")
        return

    if cid_str in state.daily_q_subs:
        state.daily_q_subs.pop(cid_str, None)
        save_daily_q_subs()
        await _sched_daily_q_chat(context.application, cid_str) # This will remove the job
        reply_txt = "Чат успешно отписан от ежедневной викторины. Запланированная задача отменена."
        logger.info(f"Чат {cid_str} отписан от DQ юзером {update.effective_user.id}.")
    else:
        reply_txt = "Чат не был подписан на ежедневную викторину."
    await update.message.reply_text(reply_txt)


async def set_daily_quiz_time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user: return
    if not context.args:
        await update.message.reply_text("Пожалуйста, укажите время. Пример: /setdailyquiztime 14:30 или /setdailyquiztime 8 (для 08:00 МСК).")
        return
    
    cid_str = str(update.effective_chat.id)
    if not await _is_admin(update, context):
        await update.message.reply_text("Только администраторы могут изменять время ежедневной викторины.")
        return
    if cid_str not in state.daily_q_subs:
        await update.message.reply_text("Чат не подписан на ежедневную викторину. Сначала используйте /subscribe_daily_quiz.")
        return

    parsed_t = _parse_hhmm(context.args[0]) # Renamed
    if parsed_t is None:
        await update.message.reply_text("Неверный формат времени. Используйте HH:MM или HH (например, 08:00, 17:30, 9). Время указывается в МСК.")
        return

    h, m = parsed_t
    state.daily_q_subs[cid_str]["hour"] = h
    state.daily_q_subs[cid_str]["minute"] = m
    save_daily_q_subs()
    await _sched_daily_q_chat(context.application, cid_str) # Reschedule with new time
    await update.message.reply_text(f"Время ежедневной викторины для этого чата установлено на: {h:02d}:{m:02d} МСК.")
    logger.info(f"Время DQ для {cid_str} изменено на {h:02d}:{m:02d} МСК юзером {update.effective_user.id}.")


async def set_daily_quiz_categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user: return
    cid_str = str(update.effective_chat.id)
    if not await _is_admin(update, context):
        await update.message.reply_text("Только администраторы могут изменять категории для ежедневной викторины.")
        return
    if cid_str not in state.daily_q_subs:
        await update.message.reply_text("Чат не подписан на ежедневную викторину. Сначала используйте /subscribe_daily_quiz.")
        return
    if not state.qs_data:
        await update.message.reply_text("Вопросы еще не загружены. Невозможно установить категории в данный момент.")
        return

    # Create a map of lowercase category name to its canonical (original case) name for existing, non-empty categories
    avail_cat_map = {name.lower(): name for name, ql in state.qs_data.items() if ql and isinstance(ql, list)} # Renamed

    if not context.args: # If no arguments, reset to random categories
        state.daily_q_subs[cid_str]["categories"] = None # None means random
        save_daily_q_subs()
        await update.message.reply_text(f"Категории для ежедневной викторины сброшены. Будут выбираться {DQ_CATS_PICK} случайных категории.")
        logger.info(f"Категории DQ для {cid_str} сброшены на случайные юзером {update.effective_user.id}.")
        return

    chosen_cats_raw = context.args # User input category names
    valid_cats_canon = [] # Stores canonical names of valid chosen categories
    invalid_cats_in = [] # Stores user inputs that were not valid category names

    for cat_arg in chosen_cats_raw: # Renamed
        canon_name = avail_cat_map.get(cat_arg.lower()) # Find canonical name case-insensitively
        if canon_name:
            if canon_name not in valid_cats_canon: # Avoid duplicates if user entered same cat differently
                valid_cats_canon.append(canon_name)
        else: 
            invalid_cats_in.append(cat_arg)

    if len(valid_cats_canon) > DQ_MAX_CUST_CATS:
        await update.message.reply_text(f"Можно выбрать не более {DQ_MAX_CUST_CATS} категорий. Вы указали {len(valid_cats_canon)}.")
        return
    
    # If user provided arguments but none were valid categories
    if not valid_cats_canon and chosen_cats_raw: 
        # This implies all chosen_cats_raw went into invalid_cats_in
        escaped_invalid_cats = [md_escape(c) for c in invalid_cats_in]
        await update.message.reply_text(f"Указанные категории не найдены или пусты: {', '.join(escaped_invalid_cats)}\\. "
                                        f"Используйте /categories для просмотра доступных\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return

    state.daily_q_subs[cid_str]["categories"] = valid_cats_canon if valid_cats_canon else None # Store list or None for random
    save_daily_q_subs()
    
    reply_parts = []
    if valid_cats_canon:
        escaped_valid_cats = [md_escape(c) for c in valid_cats_canon]
        reply_parts.append(f"Установлены следующие категории для ежедневной викторины: {', '.join(escaped_valid_cats)}\\.")
    else: # This case should ideally be caught by "reset to random" if no args, or error if args but no valid
        reply_parts.append(f"Категории сброшены на случайные (будут выбираться {DQ_CATS_PICK} категории)\\.")

    if invalid_cats_in:
        escaped_invalid_cats_warn = [md_escape(c) for c in invalid_cats_in]
        reply_parts.append(f"\nПредупреждение: следующие указанные категории не найдены, пусты или уже были учтены: '{', '.join(escaped_invalid_cats_warn)}'\\.")
    
    await update.message.reply_text(" ".join(reply_parts), parse_mode=ParseMode.MARKDOWN_V2)
    logger.info(f"Категории DQ для {cid_str} изменены на {valid_cats_canon or 'случайные'} юзером {update.effective_user.id}.")


async def show_daily_quiz_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat: return
    cid_str = str(update.effective_chat.id)
    if cid_str not in state.daily_q_subs:
        await update.message.reply_text("Чат не подписан на ежедневную викторину. Используйте /subscribe_daily_quiz для подписки.")
        return

    settings = state.daily_q_subs[cid_str]
    h, m = settings.get("hour", DQ_DEF_H), settings.get("minute", DQ_DEF_M) # Renamed
    cust_cats_list = settings.get("categories") # Renamed
    
    time_str = f"{h:02d}:{m:02d} МСК"
    
    cats_str_display = ""
    if cust_cats_list:
        escaped_cats = [md_escape(c) for c in cust_cats_list]
        cats_str_display = f"Выбранные: {', '.join(escaped_cats)}"
    else:
        cats_str_display = f"Случайные ({DQ_CATS_PICK} категории из доступных)"

    reply_txt = (f"⚙️ Текущие настройки ежедневной викторины для этого чата:\n"
                  f"\\- Время запуска: *{md_escape(time_str)}*\n"
                  f"\\- Категории: *{cats_str_display}*\n"
                  f"\\- Количество вопросов в сессии: *{DQ_QS_COUNT}*\n"
                  f"\\- Длительность каждого опроса: *{DQ_POLL_OPEN_S // 60} мин\\.*\n"
                  f"\\- Интервал между вопросами: *{DQ_Q_INTERVAL_S // 60} мин\\.*\n\n"
                  f"Для изменения используйте `/setdailyquiztime` и `/setdailyquizcategories`\\.")
    await update.message.reply_text(reply_txt, parse_mode=ParseMode.MARKDOWN_V2)

# --- Логика запланированных задач (Jobs) ---
async def _send_daily_q_job_cb(context: ContextTypes.DEFAULT_TYPE): # Renamed
    job = context.job
    if not job or not job.data: 
        logger.error("_send_daily_q_job_cb: Job data missing.")
        return

    cid_str: str = job.data["chat_id_str"]
    cur_q_idx: int = job.data["current_question_index"] # Renamed
    qs_this_sess: list[dict] = job.data["questions_this_session"] # Renamed

    active_q_state = state.active_daily_qs.get(cid_str) # Renamed
    # Check if the quiz is still active and the current index matches the job's expectation
    if not active_q_state or active_q_state.get("current_question_index") != cur_q_idx:
        logger.warning(f"DQ для {cid_str} (ожидался вопрос {cur_q_idx + 1}) прервана или состояние не совпадает. Остановка задачи.")
        # Ensure it's cleaned up if this job is somehow orphaned
        if active_q_state and active_q_state.get("job_name_next_q") == job.name:
            state.active_daily_qs.pop(cid_str, None)
        return

    if cur_q_idx >= len(qs_this_sess): # All questions sent
        logger.info(f"Все {len(qs_this_sess)} вопросов DQ отправлены в {cid_str}. Завершение сессии DQ.")
        state.active_daily_qs.pop(cid_str, None) # Clean up active session state
        try: 
            await context.bot.send_message(chat_id=cid_str, text="🎉 Ежедневная викторина завершена! Спасибо за участие!")
        except Exception as e: 
            logger.error(f"Не удалось отправить сообщение о завершении DQ в {cid_str}: {e}")
        return

    q_item = qs_this_sess[cur_q_idx] # Renamed
    poll_q_txt_api = q_item['question'] # Renamed
    
    # Header for the poll question
    full_poll_q_hdr = f"Ежедневная викторина! Вопрос {cur_q_idx + 1}/{len(qs_this_sess)}" # Renamed
    if orig_cat := q_item.get("original_category"): 
        full_poll_q_hdr += f" (Категория: {orig_cat})" # Using "Категория" for clarity
    full_poll_q_hdr += f"\n\n{poll_q_txt_api}" # Add question text after header

    # Telegram Poll question length limit is 300 chars.
    MAX_POLL_Q_LEN = 300 
    if len(full_poll_q_hdr) > MAX_POLL_Q_LEN:
        full_poll_q_hdr = full_poll_q_hdr[:MAX_POLL_Q_LEN - 3] + "..."
        logger.warning(f"Текст вопроса DQ ({cur_q_idx+1}) для poll в {cid_str} был усечен до {MAX_POLL_Q_LEN} символов.")

    _, poll_opts, poll_correct_id, _ = prep_poll_opts(q_item) # Renamed

    try:
        sent_poll = await context.bot.send_poll( # Renamed
            chat_id=cid_str, question=full_poll_q_hdr, options=poll_opts, type='quiz',
            correct_option_id=poll_correct_id, open_period=DQ_POLL_OPEN_S, is_anonymous=False
        )
        # Store info about the sent poll
        state.cur_polls[sent_poll.poll.id] = {
            "chat_id": cid_str, "message_id": sent_poll.message_id,
            "correct_index": poll_correct_id, "quiz_session": False, "daily_quiz": True,
            "question_details": q_item, "question_session_index": cur_q_idx,
            "open_timestamp": sent_poll.date.timestamp() # Useful for potential cleanup later
        }
        logger.info(f"DQ вопрос {cur_q_idx + 1}/{len(qs_this_sess)} (Poll ID: {sent_poll.poll.id}) отправлен в {cid_str}.")
    except Exception as e:
        logger.error(f"Ошибка отправки DQ вопроса {cur_q_idx + 1} в {cid_str}: {e}", exc_info=True)
        state.active_daily_qs.pop(cid_str, None) # Stop this DQ session if a question fails to send
        # Optionally notify chat about failure
        try: await context.bot.send_message(chat_id=cid_str, text="⚠️ Произошла ошибка при отправке вопроса ежедневной викторины. Викторина прервана.")
        except: pass
        return

    # Prepare for the next question
    next_q_idx = cur_q_idx + 1 # Renamed
    active_q_state["current_question_index"] = next_q_idx # Update state for the next iteration
    
    jq: JobQueue | None = context.application.job_queue # Renamed
    if not jq:
        logger.error(f"JobQueue нет в _send_daily_q_job_cb для {cid_str} после вопроса {next_q_idx-1}. Следующий вопрос не запланирован.")
        state.active_daily_qs.pop(cid_str, None) # Critical failure, stop quiz
        return

    # Schedule the next call to this function (or the end-of-quiz handler)
    job_data_next = { "chat_id_str": cid_str, "current_question_index": next_q_idx, "questions_this_session": qs_this_sess } # Renamed
    
    # Determine job name for logging/management; if it's the last question, it's a "finish" job
    next_job_name_base = f"dq_q_{next_q_idx}_chat_{cid_str}" if next_q_idx < len(qs_this_sess) else f"dq_finish_chat_{cid_str}" # Renamed

    active_q_state["job_name_next_q"] = next_job_name_base # Store next job name in state
    jq.run_once(_send_daily_q_job_cb, timedelta(seconds=DQ_Q_INTERVAL_S), data=job_data_next, name=next_job_name_base)
    
    log_msg_next_q = f"Запланирован {'следующий DQ вопрос ' if next_q_idx < len(qs_this_sess) else 'финальный обработчик DQ для '}"
    logger.debug(f"{log_msg_next_q}({next_q_idx + 1 if next_q_idx < len(qs_this_sess) else 'завершение'}) для {cid_str} через {DQ_Q_INTERVAL_S}s (job: {next_job_name_base}).")


async def _trigger_daily_q_job_cb(context: ContextTypes.DEFAULT_TYPE): # Renamed
    job = context.job
    if not job or not job.data: 
        logger.error("_trigger_daily_q_job_cb: Job data missing.")
        return
    cid_str: str = job.data["chat_id_str"]

    if cid_str not in state.daily_q_subs: # Check if chat unsubscribed before job trigger
        logger.info(f"DQ для {cid_str} не запущен (job: {job.name}), т.к. чат отписался.")
        return
    if cid_str in state.active_daily_qs: # Prevent multiple concurrent DQ sessions in the same chat
        logger.warning(f"Попытка запуска DQ для {cid_str} (job: {job.name}), но сессия DQ уже активна. Пропуск.")
        return

    # Get questions for this daily quiz session
    qs_for_quiz, picked_cats = _get_daily_qs(cid_str=cid_str, num_qs=DQ_QS_COUNT, def_cats_pick=DQ_CATS_PICK) # Renamed

    if not qs_for_quiz:
        logger.warning(f"Не удалось получить вопросы для DQ в {cid_str} (job: {job.name}). Викторина не запущена.")
        try: 
            await context.bot.send_message(chat_id=cid_str, text="Не удалось подготовить вопросы для сегодняшней ежедневной викторины. Попробуем снова завтра!")
        except Exception as e: 
            logger.error(f"Не удалось уведомить {cid_str} об ошибке подготовки DQ: {e}")
        return

    # Send introductory message
    intro_parts = [ # Renamed
        f"🌞 Начинается ежедневная викторина ({len(qs_for_quiz)} вопросов)!",
        f"Категории сегодня: <b>{', '.join(picked_cats) if picked_cats else 'Случайные'}</b>.",
        f"Один вопрос примерно каждые {DQ_Q_INTERVAL_S // 60} мин. Каждый опрос будет доступен {DQ_POLL_OPEN_S // 60} мин."
    ]
    intro_txt = "\n".join(intro_parts) # Renamed

    try:
        await context.bot.send_message(chat_id=cid_str, text=intro_txt, parse_mode=ParseMode.HTML)
        logger.info(f"DQ инициирован для {cid_str} с {len(qs_for_quiz)} вопросами из категорий: {picked_cats}.")
    except Exception as e:
        logger.error(f"Не удалось отправить стартовое сообщение DQ в {cid_str}: {e}", exc_info=True)
        return # Don't proceed if intro message fails

    # Initialize active daily quiz state for this chat
    state.active_daily_qs[cid_str] = {
        "current_question_index": 0, "questions": qs_for_quiz,
        "picked_categories": picked_cats, "job_name_next_q": None # Will be set by the first _send_daily_q_job_cb
    }

    jq: JobQueue | None = context.application.job_queue # Renamed
    if jq:
        # Schedule the first question with a small delay (e.g., 5 seconds after intro)
        first_q_job_name = f"dq_q_0_chat_{cid_str}" # Explicit name for first question job
        state.active_daily_qs[cid_str]["job_name_next_q"] = first_q_job_name # Store its name
        
        jq.run_once(
            _send_daily_q_job_cb, timedelta(seconds=5), # Small delay after intro
            data={"chat_id_str": cid_str, "current_question_index": 0, "questions_this_session": qs_for_quiz},
            name=first_q_job_name
        )
        logger.debug(f"Запланирован первый вопрос DQ для {cid_str} через 5s (job: {first_q_job_name}).")
    else:
        logger.error(f"JobQueue нет в _trigger_daily_q_job_cb для {cid_str}. DQ не начнется.")
        state.active_daily_qs.pop(cid_str, None) # Clean up if jobqueue is missing
