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
    if update.effective_chat.type == 'private': return True
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
        try: h, m = int(h_str), int(m_str); return (h,m) if 0<=h<=23 and 0<=m<=59 else None
        except ValueError: pass
        return None
    match_h = re.fullmatch(r"(\d{1,2})", time_str) # Renamed
    if match_h:
        try: h = int(match_h.group(1)); return (h,0) if 0<=h<=23 else None
        except ValueError: pass
    return None

async def _sched_daily_q_chat(app: Application, cid_str: str): # Renamed app from application
    jq: JobQueue | None = app.job_queue # Renamed
    if not jq:
        logger.error(f"JobQueue нет. Не удалось (пере)запланировать DQ для {cid_str}.") # DQ for Daily Quiz
        return

    sub_details = state.daily_q_subs.get(cid_str) # Renamed
    job_name = f"dq_trigger_chat_{cid_str}" # Shorter

    for job in jq.get_jobs_by_name(job_name): job.schedule_removal()
    if existing_jobs := jq.get_jobs_by_name(job_name): # Check if list not empty before logging
        logger.debug(f"Удалены существующие job(s) '{job_name}' для {cid_str}.")

    if not sub_details:
        logger.info(f"Подписка для {cid_str} не активна. DQ не запланирован.")
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
    avail_cats_w_qs = { name: ql for name, ql in state.qs_data.items() if ql } # Renamed

    if not avail_cats_w_qs:
        logger.warning("Нет категорий с вопросами для DQ.")
        return [], []

    sub_details = state.daily_q_subs.get(cid_str, {})
    cust_cats_cfg: Optional[List[str]] = sub_details.get("categories") # Renamed

    chosen_cats: List[str] = [] # Renamed

    if cust_cats_cfg:
        valid_cust_cats = [name for name in cust_cats_cfg if name in avail_cats_w_qs] # Renamed
        if valid_cust_cats:
            chosen_cats = valid_cust_cats
            logger.info(f"Для {cid_str} используются кастомные категории: {chosen_cats}")
        else:
            logger.warning(f"Для {cid_str} кастомные категории {cust_cats_cfg} недействительны. Выбор случайных.")

    if not chosen_cats:
        num_sample_rnd = min(def_cats_pick, len(avail_cats_w_qs)) # Renamed
        if num_sample_rnd > 0:
            chosen_cats = random.sample(list(avail_cats_w_qs.keys()), num_sample_rnd)
        else:
            logger.warning(f"Не удалось выбрать случайные категории для {cid_str} (num_sample_rnd={num_sample_rnd}).")
            return [], []
        logger.info(f"Для {cid_str} выбраны случайные категории: {chosen_cats}")

    picked_cats_final = chosen_cats
    all_qs_picked_cats: list[dict] = [] # Renamed
    for cat_name in picked_cats_final:
        all_qs_picked_cats.extend([q.copy() for q in avail_cats_w_qs.get(cat_name, [])])

    if not all_qs_picked_cats:
        logger.warning(f"Выбранные категории {picked_cats_final} для {cid_str} не содержат вопросов.")
        return [], picked_cats_final

    random.shuffle(all_qs_picked_cats)
    qs_for_quiz = all_qs_picked_cats[:num_qs]
    logger.info(f"Для DQ в {cid_str} отобрано {len(qs_for_quiz)} вопросов из: {picked_cats_final}.")
    return qs_for_quiz, picked_cats_final

# --- Обработчики команд ---
async def subscribe_daily_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user: return
    cid_str = str(update.effective_chat.id)
    if not await _is_admin(update, context):
        await update.message.reply_text("Только администраторы могут подписать чат на DQ.")
        return

    if cid_str in state.daily_q_subs:
        sub = state.daily_q_subs[cid_str] # Renamed
        time_str = f"{sub.get('hour', DQ_DEF_H):02d}:{sub.get('minute', DQ_DEF_M):02d} МСК"
        cats = sub.get("categories")
        cat_str = f"категориям: {', '.join(map(md_escape, cats))}" if cats else "случайным категориям" # md_escape here
        reply_txt = (f"Чат уже подписан на DQ\\.\nВремя: *{md_escape(time_str)}*\\. Категории: *{cat_str}*\\.\n"
                      f"Используйте `/setdailyquiztime` и `/setdailyquizcategories`\\.")
    else:
        state.daily_q_subs[cid_str] = {"hour": DQ_DEF_H, "minute": DQ_DEF_M, "categories": None}
        save_daily_q_subs()
        await _sched_daily_q_chat(context.application, cid_str)
        reply_txt = (f"✅ Чат подписан на DQ\\!\n"
                      f"Время: *{DQ_DEF_H:02d}:{DQ_DEF_M:02d} МСК*\\. Категории: *{DQ_CATS_PICK} случайных*\\.\n"
                      f"{DQ_QS_COUNT} вопросов, по одному в минуту\\. Каждый открыт {DQ_POLL_OPEN_S // 60} мин\\.\n\n"
                      f"Настройка:\n`/setdailyquiztime HH:MM`\n`/setdailyquizcategories [категории]`\n`/showdailyquizsettings`")
        logger.info(f"Чат {cid_str} подписан на DQ юзером {update.effective_user.id}.")
    await update.message.reply_text(reply_txt, parse_mode=ParseMode.MARKDOWN_V2)

async def unsubscribe_daily_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user: return
    cid_str = str(update.effective_chat.id)
    if not await _is_admin(update, context):
        await update.message.reply_text("Только администраторы могут отписать чат от DQ.")
        return

    if cid_str in state.daily_q_subs:
        state.daily_q_subs.pop(cid_str, None)
        save_daily_q_subs()
        await _sched_daily_q_chat(context.application, cid_str)
        reply_txt = "Чат отписан от DQ. Задача отменена."
        logger.info(f"Чат {cid_str} отписан от DQ юзером {update.effective_user.id}.")
    else:
        reply_txt = "Чат не был подписан на DQ."
    await update.message.reply_text(reply_txt)

async def set_daily_quiz_time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user: return
    if not context.args:
        await update.message.reply_text("Использование: /setdailyquiztime HH:MM или HH (МСК).")
        return
    cid_str = str(update.effective_chat.id)
    if not await _is_admin(update, context):
        await update.message.reply_text("Только администраторы могут менять время DQ.")
        return
    if cid_str not in state.daily_q_subs:
        await update.message.reply_text("Чат не подписан на DQ. /subscribe_daily_quiz")
        return

    parsed_t = _parse_hhmm(context.args[0]) # Renamed
    if parsed_t is None:
        await update.message.reply_text("Неверный формат времени. HH:MM или HH (МСК).")
        return

    h, m = parsed_t
    state.daily_q_subs[cid_str]["hour"] = h
    state.daily_q_subs[cid_str]["minute"] = m
    save_daily_q_subs()
    await _sched_daily_q_chat(context.application, cid_str)
    await update.message.reply_text(f"Время DQ для чата: {h:02d}:{m:02d} МСК.")
    logger.info(f"Время DQ для {cid_str} изменено на {h:02d}:{m:02d} МСК юзером {update.effective_user.id}.")

async def set_daily_quiz_categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user: return
    cid_str = str(update.effective_chat.id)
    if not await _is_admin(update, context):
        await update.message.reply_text("Только администраторы могут менять категории DQ.")
        return
    if cid_str not in state.daily_q_subs:
        await update.message.reply_text("Чат не подписан на DQ. /subscribe_daily_quiz")
        return
    if not state.qs_data:
        await update.message.reply_text("Вопросы не загружены. Невозможно установить категории.")
        return

    avail_cat_map = {name.lower(): name for name, ql in state.qs_data.items() if ql} # Renamed

    if not context.args:
        state.daily_q_subs[cid_str]["categories"] = None
        save_daily_q_subs()
        await update.message.reply_text(f"Категории сброшены. Будут {DQ_CATS_PICK} случайных.")
        logger.info(f"Категории DQ для {cid_str} сброшены юзером {update.effective_user.id}.")
        return

    chosen_cats_raw = context.args
    valid_cats_canon = [] # Renamed
    invalid_cats_in = [] # Renamed

    for cat_arg in chosen_cats_raw: # Renamed
        canon_name = avail_cat_map.get(cat_arg.lower()) # Renamed
        if canon_name:
            if canon_name not in valid_cats_canon: valid_cats_canon.append(canon_name)
        else: invalid_cats_in.append(cat_arg)

    if len(valid_cats_canon) > DQ_MAX_CUST_CATS:
        await update.message.reply_text(f"Можно выбрать не более {DQ_MAX_CUST_CATS} категорий.")
        return
    if not valid_cats_canon and chosen_cats_raw:
        await update.message.reply_text(f"Категории не найдены/пусты: {', '.join(chosen_cats_raw)}. /categories для списка.")
        return

    state.daily_q_subs[cid_str]["categories"] = valid_cats_canon if valid_cats_canon else None
    save_daily_q_subs()
    reply_parts = []
    if valid_cats_canon: reply_parts.append(f"Категории DQ: {', '.join(valid_cats_canon)}.")
    else: reply_parts.append(f"Категории DQ: {DQ_CATS_PICK} случайных.")
    if invalid_cats_in: reply_parts.append(f"\nПредупреждение: категории '{', '.join(invalid_cats_in)}' не найдены/пусты/проигнорированы.")
    await update.message.reply_text(" ".join(reply_parts))
    logger.info(f"Категории DQ для {cid_str} изменены на {valid_cats_canon or 'случайные'} юзером {update.effective_user.id}.")

async def show_daily_quiz_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat: return
    cid_str = str(update.effective_chat.id)
    if cid_str not in state.daily_q_subs:
        await update.message.reply_text("Чат не подписан на DQ. /subscribe_daily_quiz")
        return

    settings = state.daily_q_subs[cid_str]
    h, m = settings.get("hour", DQ_DEF_H), settings.get("minute", DQ_DEF_M) # Renamed
    cust_cats = settings.get("categories") # Renamed
    time_str = f"{h:02d}:{m:02d} МСК"
    cats_str = f"Выбранные: {md_escape(', '.join(cust_cats))}" if cust_cats else f"Случайные ({DQ_CATS_PICK} категории)" # md_escape

    reply_txt = (f"⚙️ Настройки DQ для чата:\n"
                  f"\\- Время: *{md_escape(time_str)}*\n"
                  f"\\- Категории: *{cats_str}*\n"
                  f"\\- Кол-во вопросов: {DQ_QS_COUNT}\n"
                  f"\\- Длительность опроса: {DQ_POLL_OPEN_S // 60} мин\n"
                  f"\\- Интервал: {DQ_Q_INTERVAL_S // 60} мин\n\n"
                  f"Изменить: `/setdailyquiztime` и `/setdailyquizcategories`\\.")
    await update.message.reply_text(reply_txt, parse_mode=ParseMode.MARKDOWN_V2)

# --- Логика запланированных задач (Jobs) ---
async def _send_daily_q_job_cb(context: ContextTypes.DEFAULT_TYPE): # Renamed
    job = context.job
    if not job or not job.data: logger.error("_send_daily_q_job_cb: Job data missing."); return

    cid_str: str = job.data["chat_id_str"]
    cur_q_idx: int = job.data["current_question_index"] # Renamed
    qs_this_sess: list[dict] = job.data["questions_this_session"] # Renamed

    active_q_state = state.active_daily_qs.get(cid_str) # Renamed
    if not active_q_state or active_q_state.get("current_question_index") != cur_q_idx:
        logger.warning(f"DQ для {cid_str} прервана или состояние не совпадает. Остановка вопроса {cur_q_idx + 1}.")
        state.active_daily_qs.pop(cid_str, None)
        return

    if cur_q_idx >= len(qs_this_sess):
        logger.info(f"Все {len(qs_this_sess)} вопросов DQ отправлены в {cid_str}.")
        state.active_daily_qs.pop(cid_str, None)
        try: await context.bot.send_message(chat_id=cid_str, text="🎉 DQ завершена! Спасибо!")
        except Exception as e: logger.error(f"Не удалось отправить сообщение о завершении DQ в {cid_str}: {e}")
        return

    q_item = qs_this_sess[cur_q_idx] # Renamed
    poll_q_txt_api = q_item['question'] # Renamed
    full_poll_q_hdr = f"Ежедневная викторина! Вопрос {cur_q_idx + 1}/{len(qs_this_sess)}" # Renamed
    if orig_cat := q_item.get("original_category"): full_poll_q_hdr += f" (Кат: {orig_cat})"
    full_poll_q_hdr += f"\n\n{poll_q_txt_api}"

    MAX_POLL_Q_LEN = 300
    if len(full_poll_q_hdr) > MAX_POLL_Q_LEN:
        full_poll_q_hdr = full_poll_q_hdr[:MAX_POLL_Q_LEN - 3] + "..."
        logger.warning(f"Текст вопроса DQ для poll в {cid_str} был усечен.")

    _, poll_opts, poll_correct_id, _ = prep_poll_opts(q_item) # Renamed

    try:
        sent_poll = await context.bot.send_poll( # Renamed
            chat_id=cid_str, question=full_poll_q_hdr, options=poll_opts, type='quiz',
            correct_option_id=poll_correct_id, open_period=DQ_POLL_OPEN_S, is_anonymous=False
        )
        state.cur_polls[sent_poll.poll.id] = {
            "chat_id": cid_str, "message_id": sent_poll.message_id,
            "correct_index": poll_correct_id, "quiz_session": False, "daily_quiz": True,
            "question_details": q_item, "question_session_index": cur_q_idx,
            "open_timestamp": sent_poll.date.timestamp()
        }
        logger.info(f"DQ вопрос {cur_q_idx + 1}/{len(qs_this_sess)} (Poll ID: {sent_poll.poll.id}) отправлен в {cid_str}.")
    except Exception as e:
        logger.error(f"Ошибка отправки DQ вопроса {cur_q_idx + 1} в {cid_str}: {e}", exc_info=True)
        state.active_daily_qs.pop(cid_str, None)
        return

    next_q_idx = cur_q_idx + 1 # Renamed
    active_q_state["current_question_index"] = next_q_idx
    jq: JobQueue | None = context.application.job_queue # Renamed
    if not jq:
        logger.error(f"JobQueue нет в _send_daily_q_job_cb для {cid_str}. Следующий вопрос не запланирован.")
        state.active_daily_qs.pop(cid_str, None)
        return

    job_data_next = { "chat_id_str": cid_str, "current_question_index": next_q_idx, "questions_this_session": qs_this_sess } # Renamed
    next_job_name_base = f"dq_q_{next_q_idx}_chat_{cid_str}" if next_q_idx < len(qs_this_sess) else f"dq_finish_chat_{cid_str}" # Renamed

    active_q_state["job_name_next_q"] = next_job_name_base
    jq.run_once(_send_daily_q_job_cb, timedelta(seconds=DQ_Q_INTERVAL_S), data=job_data_next, name=next_job_name_base)
    log_msg_next_q = f"Запланирован {'следующий DQ вопрос ' if next_q_idx < len(qs_this_sess) else 'финальный обработчик DQ для '}"
    logger.debug(f"{log_msg_next_q}({next_q_idx + 1 if next_q_idx < len(qs_this_sess) else ''}) для {cid_str} (job: {next_job_name_base}).")


async def _trigger_daily_q_job_cb(context: ContextTypes.DEFAULT_TYPE): # Renamed
    job = context.job
    if not job or not job.data: logger.error("_trigger_daily_q_job_cb: Job data missing."); return
    cid_str: str = job.data["chat_id_str"]

    if cid_str not in state.daily_q_subs:
        logger.info(f"DQ для {cid_str} не запущен, т.к. чат отписан.")
        return
    if cid_str in state.active_daily_qs:
        logger.warning(f"Попытка запуска DQ для {cid_str}, но он уже активен. Пропуск.")
        return

    qs_for_quiz, picked_cats = _get_daily_qs(cid_str=cid_str, num_qs=DQ_QS_COUNT, def_cats_pick=DQ_CATS_PICK) # Renamed

    if not qs_for_quiz:
        logger.warning(f"Не удалось получить вопросы для DQ в {cid_str}. Викторина не запущена.")
        try: await context.bot.send_message(chat_id=cid_str, text="Не удалось подготовить вопросы для DQ. Попробуем завтра!")
        except Exception as e: logger.error(f"Не удалось уведомить {cid_str} об ошибке подготовки DQ: {e}")
        return

    intro_parts = [ # Renamed
        f"🌞 Начинаем DQ ({len(qs_for_quiz)} вопросов)!",
        f"Категории: <b>{', '.join(picked_cats) if picked_cats else 'Случайные'}</b>.",
        f"1 вопрос/мин. Доступен {DQ_POLL_OPEN_S // 60} мин."
    ]
    intro_txt = "\n".join(intro_parts) # Renamed

    try:
        await context.bot.send_message(chat_id=cid_str, text=intro_txt, parse_mode=ParseMode.HTML)
        logger.info(f"DQ инициирован для {cid_str} с {len(qs_for_quiz)} вопросами из: {picked_cats}.")
    except Exception as e:
        logger.error(f"Не удалось отправить стартовое сообщение DQ в {cid_str}: {e}", exc_info=True)
        return

    state.active_daily_qs[cid_str] = {
        "current_question_index": 0, "questions": qs_for_quiz,
        "picked_categories": picked_cats, "job_name_next_q": None
    }

    jq: JobQueue | None = context.application.job_queue # Renamed
    if jq:
        first_q_job_name = f"dq_q_0_chat_{cid_str}"
        state.active_daily_qs[cid_str]["job_name_next_q"] = first_q_job_name
        jq.run_once(
            _send_daily_q_job_cb, timedelta(seconds=5),
            data={"chat_id_str": cid_str, "current_question_index": 0, "questions_this_session": qs_for_quiz},
            name=first_q_job_name
        )
        logger.debug(f"Запланирован первый вопрос DQ для {cid_str} (job: {first_q_job_name}).")
    else:
        logger.error(f"JobQueue нет в _trigger_daily_q_job_cb для {cid_str}. DQ не начнется.")
        state.active_daily_qs.pop(cid_str, None)
