# handlers/quiz_session_handlers.py
import random
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import (logger, QS_PER_SESSION, CB_Q10_CAT_PFX, # Renamed constants
                    CB_Q10_RND_CAT, Q10_NOTIFY_DELAY_M)
import state
from quiz_logic import (get_rand_qs, get_rand_qs_all, send_next_q_in_sess, # Renamed functions
                        show_q_sess_res)
from handlers.common_handlers import md_escape # For escaping category names in messages

async def _start_q10_sess( # Renamed
    context: ContextTypes.DEFAULT_TYPE,
    cid_int: int, # Renamed
    cid_str: str,
    uid: int, # Renamed user_id
    cat_name: str | None # Renamed category_name
):
    sess_qs = [] # Renamed session_questions
    intro_part = "" # Renamed intro_category_part
    reply_txt = ""

    if cat_name:
        sess_qs = get_rand_qs(cat_name, QS_PER_SESSION)
        intro_part = f"из категории: {md_escape(cat_name)}"
    else:
        sess_qs = get_rand_qs_all(QS_PER_SESSION)
        intro_part = "из случайных категорий"

    actual_qs_num = len(sess_qs) # Renamed actual_number_of_questions
    if actual_qs_num == 0:
        reply_txt = f"Не найдено вопросов для /quiz10 ({intro_part})\\. Викторина не начата\\."
        try:
            await context.bot.send_message(chat_id=cid_int, text=reply_txt, parse_mode='MarkdownV2')
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения о пустой категории в {cid_str}: {e}")
        return

    start_msg_txt = f"🚀 Начинаем викторину из {actual_qs_num} вопросов ({intro_part})\\! Приготовьтесь\\!"
    intro_msg = None # Renamed intro_message_obj
    try:
        intro_msg = await context.bot.send_message(chat_id=cid_int, text=start_msg_txt, parse_mode='MarkdownV2')
    except Exception as e:
         logger.error(f"Ошибка отправки вводного сообщения сессии в {cid_str}: {e}", exc_info=True)
         # If intro message fails, we might not want to proceed with the session
         return

    state.cur_q_sessions[cid_str] = {
        "questions": sess_qs, "session_scores": {}, "current_index": 0,
        "actual_num_questions": actual_qs_num,
        "message_id_intro": intro_msg.message_id if intro_msg else None,
        "starter_user_id": str(uid), "current_poll_id": None,
        "next_question_job": None, "category_used": cat_name
    }
    logger.info(f"/quiz10 на {actual_qs_num} вопросов ({intro_part}) запущена в {cid_str} юзером {uid}.")
    await send_next_q_in_sess(context, cid_str)


async def quiz10_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat: return

    cid_str = str(update.effective_chat.id)
    cid_int = update.effective_chat.id # Renamed chat_id_int_val
    reply_txt = ""

    if state.cur_q_sessions.get(cid_str):
        reply_txt = "В этом чате уже идет игра /quiz10. Дождитесь окончания или /stopquiz."
        await update.message.reply_text(reply_txt)
        return
    if state.pend_sched_qs.get(cid_str): # Use renamed state var
        reply_txt = f"В этом чате уже запланирована игра /quiz10notify. Дождитесь или /stopquiz."
        await update.message.reply_text(reply_txt)
        return

    if not state.qs_data: # Use renamed state var
        reply_txt = "Вопросы еще не загружены. Попробуйте /start позже."
        await update.message.reply_text(reply_txt)
        return

    avail_cats = [name for name, ql in state.qs_data.items() if isinstance(ql, list) and ql] # Renamed
    if not avail_cats:
        reply_txt = "Нет доступных категорий с вопросами для /quiz10."
        await update.message.reply_text(reply_txt)
        return

    kbd = [] # Renamed keyboard_buttons
    cat_map_cb: Dict[str, str] = {} # Renamed category_map_for_callback
    
    # Sort categories for consistent display
    for i, cat_name in enumerate(sorted(avail_cats)):
        # Using a simple short ID for callback data to keep it under 64 bytes
        short_id = f"c{i}" 
        cat_map_cb[short_id] = cat_name # Store mapping from short_id to full category name
        cb_data = f"{CB_Q10_CAT_PFX}{short_id}" # Renamed const
        
        # Check callback data length (Telegram limit is 64 bytes)
        if len(cb_data.encode('utf-8')) > 64:
             logger.error(f"Callback data '{cb_data}' для '{cat_name}' слишком длинный! Пропуск.")
             continue
        kbd.append([InlineKeyboardButton(cat_name, callback_data=cb_data)])

    # Add random category button if there are categories to choose from
    if kbd: # Only add random if there are specific categories
        kbd.append([InlineKeyboardButton("🎲 Случайные категории", callback_data=CB_Q10_RND_CAT)]) # Renamed const
    
    if not kbd: # Should not happen if avail_cats was not empty, but as a safeguard
        reply_txt = "Не удалось сформировать кнопки выбора категорий."
        await update.message.reply_text(reply_txt)
        return

    reply_markup = InlineKeyboardMarkup(kbd)

    # Store the category map temporarily in chat_data, it will be cleared after selection or timeout
    chat_data_key = f"q10_cat_map_{cid_str}" 
    context.chat_data[chat_data_key] = cat_map_cb 
    logger.debug(f"Временная карта категорий сохранена в chat_data (ключ: {chat_data_key}) для {cid_str}.")

    reply_txt = 'Выберите категорию для немедленного старта /quiz10:'
    await update.message.reply_text(reply_txt, reply_markup=reply_markup)


async def on_q10_cat_select(update: Update, context: ContextTypes.DEFAULT_TYPE): # Renamed
    query = update.callback_query
    if not query: return
    await query.answer() # Acknowledge the callback query

    if not query.message or not query.message.chat or not query.from_user: return

    cid_int = query.message.chat.id
    cid_str = str(cid_int)
    uid = query.from_user.id # Renamed user_id

    # Retrieve and remove the temporary category map
    chat_data_key = f"q10_cat_map_{cid_str}"
    cat_map_cb: Dict[str, str] | None = context.chat_data.pop(chat_data_key, None)

    if cat_map_cb is None and not query.data == CB_Q10_RND_CAT: # If map is needed but not found
        logger.warning(f"Временная карта категорий не найдена в chat_data ({chat_data_key}) для {cid_str} при выборе не случайной категории.")
        err_msg = "Ошибка: Время выбора категории истекло или произошла внутренняя ошибка. Попробуйте /quiz10 снова." # Shorter
        try: await query.edit_message_text(text=err_msg)
        except Exception: # Fallback if edit fails (e.g., message too old)
            try: await context.bot.send_message(chat_id=cid_int, text=err_msg)
            except Exception as e_send: logger.error(f"Failed to send error msg on cat select: {e_send}")
        return
    
    if cat_map_cb is not None: # Log removal if it was found
        logger.debug(f"Временная карта категорий ({chat_data_key}) удалена из chat_data для {cid_str}.")


    sel_cat_name: str | None = None # Renamed selected_category_name
    cb_data = query.data # Renamed callback_data_received
    msg_after_sel = "" # Renamed message_text_after_selection

    if cb_data == CB_Q10_RND_CAT: # Renamed const
        sel_cat_name = None # None signifies random categories
        msg_after_sel = "Выбран случайный набор категорий. Начинаем /quiz10..."
    elif cb_data and cb_data.startswith(CB_Q10_CAT_PFX) and cat_map_cb: # Renamed const
        short_id = cb_data[len(CB_Q10_CAT_PFX):]
        sel_cat_name = cat_map_cb.get(short_id)
        if sel_cat_name:
             msg_after_sel = f"Выбрана категория '{md_escape(sel_cat_name)}'. Начинаем /quiz10..."
        else:
             logger.warning(f"Не найден ID '{short_id}' в карте категорий для {cid_str}. Карта: {cat_map_cb}")
             msg_after_sel = "Ошибка выбора категории (ID не найден). Попробуйте /quiz10 снова."
             # No session start if error
    else:
        logger.warning(f"Неизвестные callback_data в on_q10_cat_select: '{cb_data}'.")
        msg_after_sel = "Ошибка выбора категории (неизвестный тип). Попробуйте /quiz10 снова."
        # No session start if error

    try:
        # Use MarkdownV2 if escaping was used
        parse_mode_final = ParseMode.MARKDOWN_V2 if "Начинаем /quiz10..." in msg_after_sel and sel_cat_name else None
        await query.edit_message_text(text=msg_after_sel, parse_mode=parse_mode_final)
    except Exception as e_edit_final:
        # This can happen if the message is too old or already edited, log and continue if session is starting
        logger.info(f"Не удалось отредактировать сообщение с кнопками (финальное): {e_edit_final}. Сообщение: '{msg_after_sel}'")

    # Start session only if a valid selection leading to "Начинаем" was made
    if "Начинаем /quiz10..." in msg_after_sel and not ("Ошибка" in msg_after_sel or "ID не найден" in msg_after_sel):
         await _start_q10_sess(context, cid_int, cid_str, uid, sel_cat_name)


async def quiz10notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user: return

    cid_int = update.effective_chat.id
    cid_str = str(cid_int)
    uid = update.effective_user.id # Renamed user_id
    reply_txt = ""

    if state.cur_q_sessions.get(cid_str):
        reply_txt = "В этом чате уже идет игра /quiz10. Дождитесь или /stopquiz."
        await update.message.reply_text(reply_txt)
        return
    if state.pend_sched_qs.get(cid_str): # Use renamed state var
        pending_info = state.pend_sched_qs[cid_str]
        sched_dt_utc = pending_info.get("scheduled_time") # Renamed
        time_left = "скоро" # Renamed time_left_str
        if sched_dt_utc and isinstance(sched_dt_utc, datetime):
            now_utc = datetime.now(timezone.utc)
            if sched_dt_utc > now_utc:
                diff = sched_dt_utc - now_utc # Renamed time_difference
                # Show in minutes, at least 1 min if it's very soon
                time_left = f"примерно через {max(1, int(diff.total_seconds() / 60))} мин."
            else: # Should ideally not happen if job hasn't run, but handle it
                time_left = "очень скоро (возможно, уже началась)"
        reply_txt = f"В этом чате уже запланирована игра /quiz10notify (начнется {time_left}). /stopquiz для отмены."
        await update.message.reply_text(reply_txt)
        return

    cat_name_arg = " ".join(context.args) if context.args else None
    chosen_cat_full: str | None = None # Renamed chosen_category_full_name
    cat_disp_name = "случайным категориям" # Renamed category_display_name

    if not state.qs_data: # Use renamed state var
        reply_txt = "Вопросы еще не загружены. Попробуйте /start позже."
        await update.message.reply_text(reply_txt)
        return

    if cat_name_arg:
        # Find case-insensitive match for category name
        found_cat = next((cat for cat in state.qs_data if cat.lower() == cat_name_arg.lower() and state.qs_data[cat]), None) # Renamed
        if found_cat:
            chosen_cat_full = found_cat
            cat_disp_name = f"категории '{md_escape(chosen_cat_full)}'"
        else:
            # If category specified but not found/empty, inform user and default to random.
            # The behavior in prompt was "Викторина по случайным категориям."
            # No specific reply for this in prompt, but it's good UX.
            await update.message.reply_text(
                f"Категория '{md_escape(cat_name_arg)}' не найдена или пуста. "
                f"Викторина будет запланирована по случайным категориям.",
                 parse_mode=ParseMode.MARKDOWN_V2
            )
            # chosen_cat_full remains None, cat_disp_name remains "случайным категориям"

    # Ensure there are any questions at all if going for random
    if not chosen_cat_full and not cat_name_arg: # i.e., random categories by default or due to bad arg
         all_qs_flat = [q for q_list in state.qs_data.values() for q in q_list] # Renamed
         if not all_qs_flat:
             reply_txt = "Нет доступных вопросов для викторины в принципе."
             await update.message.reply_text(reply_txt)
             return

    delay_s = Q10_NOTIFY_DELAY_M * 60 # Renamed delay_seconds
    job_name = f"sched_q10_chat_{cid_str}" # Shorter job name

    job_ctx_data = {"chat_id_int": cid_int, "user_id": uid, "category_full_name": chosen_cat_full} # Renamed

    if context.job_queue:
        # Remove any existing job with the same name before scheduling a new one
        for old_job in context.job_queue.get_jobs_by_name(job_name): old_job.schedule_removal()

        context.job_queue.run_once(
            _exec_sched_q10_cb, timedelta(seconds=delay_s), # Renamed handler
            data=job_ctx_data, name=job_name
        )
        sched_time_utc = datetime.now(timezone.utc) + timedelta(seconds=delay_s) # Renamed
        state.pend_sched_qs[cid_str] = { # Use renamed state var
            "job_name": job_name, "category_name": chosen_cat_full,
            "starter_user_id": str(uid), "scheduled_time": sched_time_utc
        }
        reply_txt = (f"🔔 Принято! /quiz10 по {cat_disp_name} через {Q10_NOTIFY_DELAY_M} мин\\.\n"
                      f"/stopquiz для отмены\\.")
        await update.message.reply_text(reply_txt, parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Запланирован /quiz10notify для {cid_str} по {cat_disp_name if chosen_cat_full else 'случайным категориям'} через {Q10_NOTIFY_DELAY_M} мин. Job: {job_name}")
    else:
        reply_txt = "Ошибка: JobQueue не настроен. Уведомление не установлено."
        await update.message.reply_text(reply_txt)
        logger.error("JobQueue не доступен в quiz10notify_command.")


async def _exec_sched_q10_cb(context: ContextTypes.DEFAULT_TYPE): # Renamed
    if not context.job or not context.job.data:
        logger.error("_exec_sched_q10_cb вызван без job data.")
        return

    job_data = context.job.data
    cid_int: int = job_data["chat_id_int"]
    cid_str = str(cid_int)
    uid: int = job_data["user_id"]
    cat_full_name: str | None = job_data.get("category_full_name") # Renamed category_full_name_from_job

    # Verify if this job is still the one pending for this chat
    pending_q_info = state.pend_sched_qs.get(cid_str) # Renamed, use renamed state var
    if not pending_q_info or pending_q_info.get("job_name") != context.job.name:
        logger.info(f"Запланированный quiz10 (job: {context.job.name}) для {cid_str} был отменен/заменен до запуска. Пропуск.")
        # Clean up just in case, though it should be cleaned by stopquiz or a new notify
        if pending_q_info and pending_q_info.get("job_name") == context.job.name:
             state.pend_sched_qs.pop(cid_str, None)
        return

    # This job is now running, remove it from pending list
    state.pend_sched_qs.pop(cid_str, None) # Use renamed state var
    logger.debug(f"Удалена запись из pend_sched_qs для {cid_str} при запуске job'а '{context.job.name}'.")

    if state.cur_q_sessions.get(cid_str): # Use renamed state var
        logger.warning(f"Попытка запуска запланированного quiz10 в {cid_str}, но там уже активна сессия.")
        try:
            await context.bot.send_message(chat_id=cid_int, text="Не удалось запустить запланированную викторину: в чате уже идет другая игра /quiz10.")
        except Exception as e_send: logger.error(f"Ошибка отправки сообщения о конфликте сессий в {cid_str}: {e_send}")
        return

    logger.info(f"Запускаем запланированный quiz10 для {cid_str}. Категория: {cat_full_name or 'Случайные'}")
    await _start_q10_sess(context, cid_int, cid_str, uid, cat_full_name)


async def stop_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user or not update.effective_chat: return

    cid_int = update.effective_chat.id
    cid_str = str(cid_int)
    uid_str = str(update.effective_user.id) # Renamed
    reply_txt = ""

    is_admin = False # Renamed is_user_admin
    if update.effective_chat.type != "private": # Admin check only relevant in groups/supergroups
        try:
            member = await context.bot.get_chat_member(cid_str, uid_str) # Renamed chat_member_obj
            if member.status in [member.ADMINISTRATOR, member.CREATOR]: is_admin = True
        except Exception as e: logger.warning(f"Ошибка проверки админа для {uid_str} в {cid_str}: {e}")
    elif update.effective_chat.type == "private": # In private chat, user is always "admin" of their own session
        is_admin = True


    stopped_any = False # Renamed stopped_anything

    # Stop active quiz session (/quiz10)
    active_sess = state.cur_q_sessions.get(cid_str) # Renamed, use renamed state var
    if active_sess:
        sess_starter_id = active_sess.get("starter_user_id") # Renamed
        if is_admin or uid_str == sess_starter_id:
            logger.info(f"/stopquiz от {uid_str} (admin: {is_admin}) в {cid_str}. Остановка активной /quiz10 (стартер {sess_starter_id}).")
            
            # Attempt to stop the current poll if one exists
            cur_poll_id = active_sess.get("current_poll_id") # Renamed
            if cur_poll_id:
                poll_info = state.cur_polls.get(cur_poll_id) # Use renamed state var
                if poll_info and poll_info.get("message_id"):
                    try: 
                        await context.bot.stop_poll(chat_id=cid_str, message_id=poll_info["message_id"])
                        logger.info(f"Остановлен poll {cur_poll_id} для сессии {cid_str}.")
                    except Exception as e_stop: 
                        logger.warning(f"Ошибка остановки опроса {cur_poll_id} при /stopquiz: {e_stop}")
            
            # Show results (marked as error/interrupted) and clean up session
            await show_q_sess_res(context, cid_str, error_occurred=True) 
            reply_txt = "Активная викторина /quiz10 остановлена."
            await update.message.reply_text(reply_txt)
            stopped_any = True
        else:
            reply_txt = "Только администратор чата или пользователь, начавший викторину /quiz10, может ее остановить."
            await update.message.reply_text(reply_txt)
            return # Don't proceed to check pending if permission denied for active

    # Cancel pending scheduled quiz (/quiz10notify)
    pending_q = state.pend_sched_qs.get(cid_str) # Renamed, use renamed state var
    if pending_q:
        pending_starter_id = pending_q.get("starter_user_id") # Renamed
        if is_admin or uid_str == pending_starter_id:
            job_name = pending_q.get("job_name")
            if job_name and context.job_queue:
                removed_cnt = 0 # Renamed removed_jobs_count
                for job in context.job_queue.get_jobs_by_name(job_name):
                    job.schedule_removal()
                    removed_cnt +=1
                if removed_cnt > 0: 
                    logger.info(f"Отменен(о) {removed_cnt} запланированных заданий /quiz10notify (job: {job_name}) в {cid_str} по команде /stopquiz от {uid_str}.")
            
            state.pend_sched_qs.pop(cid_str, None) # Remove from pending list
            reply_txt = "Запланированная викторина /quiz10notify отменена."
            await update.message.reply_text(reply_txt)
            stopped_any = True
        else:
            # If an active session was already handled, this message might be redundant or confusing.
            # Only send if no active session was stopped (or attempted to be stopped).
            if not active_sess: 
                 reply_txt = "Только администратор чата или пользователь, запланировавший /quiz10notify, может ее отменить."
                 await update.message.reply_text(reply_txt)
            return # Stop further processing

    if not stopped_any:
        reply_txt = "В этом чате нет активных или запланированных викторин (/quiz10, /quiz10notify) для остановки/отмены."
        await update.message.reply_text(reply_txt)
