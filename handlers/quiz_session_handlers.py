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

async def _start_q10_sess( # Renamed
    context: ContextTypes.DEFAULT_TYPE,
    cid_int: int, # Renamed
    cid_str: str,
    uid: int, # Renamed
    cat_name: str | None # Renamed
):
    sess_qs = [] # Renamed
    intro_part = "" # Renamed
    reply_txt = ""

    if cat_name:
        sess_qs = get_rand_qs(cat_name, QS_PER_SESSION)
        intro_part = f"из категории: {cat_name}"
    else:
        sess_qs = get_rand_qs_all(QS_PER_SESSION)
        intro_part = "из случайных категорий"

    actual_qs_num = len(sess_qs) # Renamed
    if actual_qs_num == 0:
        reply_txt = f"Не найдено вопросов для /quiz10 ({intro_part}). Викторина не начата."
        try:
            await context.bot.send_message(chat_id=cid_int, text=reply_txt)
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения о пустой категории в {cid_str}: {e}")
        return

    start_msg_txt = f"🚀 Начинаем викторину из {actual_qs_num} вопросов ({intro_part})! Приготовьтесь!"
    intro_msg = None # Renamed
    try:
        intro_msg = await context.bot.send_message(chat_id=cid_int, text=start_msg_txt)
    except Exception as e:
         logger.error(f"Ошибка отправки вводного сообщения сессии в {cid_str}: {e}", exc_info=True)
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
    cid_int = update.effective_chat.id # Renamed
    reply_txt = ""

    if state.cur_q_sessions.get(cid_str):
        reply_txt = "В этом чате уже идет игра /quiz10. Дождитесь окончания или /stopquiz."
        await update.message.reply_text(reply_txt)
        return
    if state.pend_sched_qs.get(cid_str):
        reply_txt = f"В этом чате уже запланирована игра /quiz10notify. Дождитесь или /stopquiz."
        await update.message.reply_text(reply_txt)
        return

    if not state.qs_data:
        reply_txt = "Вопросы еще не загружены. Попробуйте /start позже."
        await update.message.reply_text(reply_txt)
        return

    avail_cats = [name for name, ql in state.qs_data.items() if isinstance(ql, list) and ql] # Renamed
    if not avail_cats:
        reply_txt = "Нет доступных категорий с вопросами для /quiz10."
        await update.message.reply_text(reply_txt)
        return

    kbd = [] # Renamed
    cat_map_cb: Dict[str, str] = {} # Renamed
    for i, cat_name in enumerate(sorted(avail_cats)):
        short_id = f"c{i}"
        cat_map_cb[short_id] = cat_name
        cb_data = f"{CB_Q10_CAT_PFX}{short_id}" # Renamed const
        if len(cb_data.encode('utf-8')) > 64:
             logger.error(f"Callback data '{cb_data}' для '{cat_name}' слишком длинный! Пропуск.")
             continue
        kbd.append([InlineKeyboardButton(cat_name, callback_data=cb_data)])

    kbd.append([InlineKeyboardButton("🎲 Случайные категории", callback_data=CB_Q10_RND_CAT)]) # Renamed const
    reply_markup = InlineKeyboardMarkup(kbd)

    chat_data_key = f"q10_cat_map_{cid_str}"
    context.chat_data[chat_data_key] = cat_map_cb
    logger.debug(f"Временная карта категорий сохранена в chat_data (ключ: {chat_data_key}) для {cid_str}.")

    reply_txt = 'Выберите категорию для немедленного старта /quiz10:'
    await update.message.reply_text(reply_txt, reply_markup=reply_markup)

async def on_q10_cat_select(update: Update, context: ContextTypes.DEFAULT_TYPE): # Renamed
    query = update.callback_query
    if not query: return
    await query.answer()

    if not query.message or not query.message.chat or not query.from_user: return

    cid_int = query.message.chat.id
    cid_str = str(cid_int)
    uid = query.from_user.id # Renamed

    chat_data_key = f"q10_cat_map_{cid_str}"
    cat_map_cb: Dict[str, str] | None = context.chat_data.pop(chat_data_key, None)

    if cat_map_cb is None:
        logger.warning(f"Временная карта категорий не найдена в chat_data ({chat_data_key}) для {cid_str}.")
        err_msg = "Ошибка: Время выбора категории истекло. Попробуйте /quiz10 снова." # Shorter
        try: await query.edit_message_text(text=err_msg)
        except Exception: await context.bot.send_message(chat_id=cid_int, text=err_msg)
        return

    logger.debug(f"Временная карта категорий ({chat_data_key}) удалена из chat_data для {cid_str}.")

    sel_cat_name: str | None = None # Renamed
    cb_data = query.data # Renamed
    msg_after_sel = "" # Renamed

    if cb_data == CB_Q10_RND_CAT: # Renamed const
        sel_cat_name = None
        msg_after_sel = "Выбран случайный набор категорий. Начинаем /quiz10..."
    elif cb_data and cb_data.startswith(CB_Q10_CAT_PFX): # Renamed const
        short_id = cb_data[len(CB_Q10_CAT_PFX):]
        sel_cat_name = cat_map_cb.get(short_id)
        if sel_cat_name:
             msg_after_sel = f"Выбрана категория '{sel_cat_name}'. Начинаем /quiz10..."
        else:
             logger.warning(f"Не найден ID '{short_id}' в карте категорий для {cid_str}. Карта: {cat_map_cb}")
             msg_after_sel = "Ошибка выбора категории (ID не найден). Попробуйте /quiz10 снова."
             try: await query.edit_message_text(text=msg_after_sel)
             except Exception: await context.bot.send_message(chat_id=cid_int, text=msg_after_sel)
             return
    else:
        logger.warning(f"Неизвестные callback_data в on_q10_cat_select: '{cb_data}'.")
        msg_after_sel = "Ошибка выбора категории (неизвестный тип). Попробуйте /quiz10 снова."
        try: await query.edit_message_text(text=msg_after_sel)
        except Exception: await context.bot.send_message(chat_id=cid_int, text=msg_after_sel)
        return

    try:
        await query.edit_message_text(text=msg_after_sel)
    except Exception as e_edit_final:
        logger.info(f"Не удалось отредактировать сообщение с кнопками (финальное): {e_edit_final}.")

    if "Начинаем /quiz10..." in msg_after_sel:
         await _start_q10_sess(context, cid_int, cid_str, uid, sel_cat_name)

async def quiz10notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user: return

    cid_int = update.effective_chat.id
    cid_str = str(cid_int)
    uid = update.effective_user.id # Renamed
    reply_txt = ""

    if state.cur_q_sessions.get(cid_str):
        reply_txt = "В этом чате уже идет игра /quiz10. Дождитесь или /stopquiz."
        await update.message.reply_text(reply_txt)
        return
    if state.pend_sched_qs.get(cid_str):
        pending_info = state.pend_sched_qs[cid_str]
        sched_dt_utc = pending_info.get("scheduled_time") # Renamed
        time_left = "скоро" # Renamed
        if sched_dt_utc and isinstance(sched_dt_utc, datetime):
            now_utc = datetime.now(timezone.utc)
            if sched_dt_utc > now_utc:
                diff = sched_dt_utc - now_utc # Renamed
                time_left = f"примерно через {max(1, int(diff.total_seconds() / 60))} мин."
            else:
                time_left = "очень скоро"
        reply_txt = f"В этом чате уже запланирована игра /quiz10notify (начнется {time_left}). /stopquiz для отмены."
        await update.message.reply_text(reply_txt)
        return

    cat_name_arg = " ".join(context.args) if context.args else None
    chosen_cat_full: str | None = None # Renamed
    cat_disp_name = "случайным категориям" # Renamed

    if not state.qs_data:
        reply_txt = "Вопросы еще не загружены. Попробуйте /start позже."
        await update.message.reply_text(reply_txt)
        return

    if cat_name_arg:
        found_cat = next((cat for cat in state.qs_data if cat.lower() == cat_name_arg.lower() and state.qs_data[cat]), None) # Renamed
        if found_cat:
            chosen_cat_full = found_cat
            cat_disp_name = f"категории '{chosen_cat_full}'"
        else:
            reply_txt = f"Категория '{cat_name_arg}' не найдена/пуста. Викторина по случайным категориям."
            await update.message.reply_text(reply_txt)

    if not chosen_cat_full and not cat_name_arg:
         all_qs_flat = [q for q_list in state.qs_data.values() for q in q_list] # Renamed
         if not all_qs_flat:
             reply_txt = "Нет доступных вопросов для викторины."
             await update.message.reply_text(reply_txt)
             return

    delay_s = Q10_NOTIFY_DELAY_M * 60 # Renamed
    job_name = f"sched_q10_chat_{cid_str}"

    job_ctx_data = {"chat_id_int": cid_int, "user_id": uid, "category_full_name": chosen_cat_full} # Renamed

    if context.job_queue:
        for old_job in context.job_queue.get_jobs_by_name(job_name): old_job.schedule_removal()

        context.job_queue.run_once(
            _exec_sched_q10_cb, timedelta(seconds=delay_s), # Renamed handler
            data=job_ctx_data, name=job_name
        )
        sched_time_utc = datetime.now(timezone.utc) + timedelta(seconds=delay_s) # Renamed
        state.pend_sched_qs[cid_str] = {
            "job_name": job_name, "category_name": chosen_cat_full,
            "starter_user_id": str(uid), "scheduled_time": sched_time_utc
        }
        reply_txt = (f"🔔 Принято! /quiz10 по {cat_disp_name} через {Q10_NOTIFY_DELAY_M} мин.\n/stopquiz для отмены.")
        await update.message.reply_text(reply_txt)
        logger.info(f"Запланирован /quiz10notify для {cid_str} по {cat_disp_name} через {Q10_NOTIFY_DELAY_M} мин. Job: {job_name}")
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
    cat_full_name: str | None = job_data.get("category_full_name") # Renamed

    pending_q_info = state.pend_sched_qs.get(cid_str) # Renamed
    if not pending_q_info or pending_q_info.get("job_name") != context.job.name:
        logger.info(f"Запланированный quiz10 (job: {context.job.name}) для {cid_str} отменен/заменен.")
        return

    state.pend_sched_qs.pop(cid_str, None)
    logger.debug(f"Удалена запись из pend_sched_qs для {cid_str} при запуске job'а.")

    if state.cur_q_sessions.get(cid_str):
        logger.warning(f"Попытка запуска запланированного quiz10 в {cid_str}, но там уже активна сессия.")
        try:
            await context.bot.send_message(chat_id=cid_int, text="Не удалось запустить запланированную викторину: идет другая игра /quiz10.")
        except Exception as e_send: logger.error(f"Ошибка отправки о конфликте сессий в {cid_str}: {e_send}")
        return

    logger.info(f"Запускаем запланированный quiz10 для {cid_str}. Категория: {cat_full_name or 'Случайные'}")
    await _start_q10_sess(context, cid_int, cid_str, uid, cat_full_name)

async def stop_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user or not update.effective_chat: return

    cid_int = update.effective_chat.id
    cid_str = str(cid_int)
    uid_str = str(update.effective_user.id) # Renamed
    reply_txt = ""

    is_admin = False # Renamed
    if update.effective_chat.type != "private":
        try:
            member = await context.bot.get_chat_member(cid_str, uid_str) # Renamed
            if member.status in [member.ADMINISTRATOR, member.CREATOR]: is_admin = True
        except Exception as e: logger.warning(f"Ошибка проверки админа для {uid_str} в {cid_str}: {e}")

    stopped_any = False # Renamed

    active_sess = state.cur_q_sessions.get(cid_str) # Renamed
    if active_sess:
        sess_starter_id = active_sess.get("starter_user_id") # Renamed
        if is_admin or uid_str == sess_starter_id:
            logger.info(f"/stopquiz от {uid_str} (admin: {is_admin}) в {cid_str}. Остановка /quiz10 (стартер {sess_starter_id}).")
            cur_poll_id = active_sess.get("current_poll_id") # Renamed
            if cur_poll_id:
                poll_info = state.cur_polls.get(cur_poll_id)
                if poll_info and poll_info.get("message_id"):
                    try: await context.bot.stop_poll(cid_str, poll_info["message_id"])
                    except Exception as e_stop: logger.warning(f"Ошибка остановки опроса {cur_poll_id}: {e_stop}")
            await show_q_sess_res(context, cid_str, error_occurred=True)
            reply_txt = "Активная викторина /quiz10 остановлена."
            await update.message.reply_text(reply_txt)
            stopped_any = True
        else:
            reply_txt = "Только админ или стартер /quiz10 может ее остановить."
            await update.message.reply_text(reply_txt)
            return

    pending_q = state.pend_sched_qs.get(cid_str) # Renamed
    if pending_q:
        pending_starter_id = pending_q.get("starter_user_id") # Renamed
        if is_admin or uid_str == pending_starter_id:
            job_name = pending_q.get("job_name")
            if job_name and context.job_queue:
                removed_cnt = 0 # Renamed
                for job in context.job_queue.get_jobs_by_name(job_name):
                    job.schedule_removal()
                    removed_cnt +=1
                if removed_cnt > 0: logger.info(f"Отменен(о) {removed_cnt} quiz10notify ({job_name}) в {cid_str} /stopquiz от {uid_str}.")
            state.pend_sched_qs.pop(cid_str, None)
            reply_txt = "Запланированная викторина /quiz10notify отменена."
            await update.message.reply_text(reply_txt)
            stopped_any = True
        else:
            if not active_sess:
                 reply_txt = "Только админ или тот, кто запланировал /quiz10notify, может ее отменить."
                 await update.message.reply_text(reply_txt)
            return

    if not stopped_any:
        reply_txt = "В этом чате нет активных или запланированных /quiz10 для остановки/отмены."
        await update.message.reply_text(reply_txt)
