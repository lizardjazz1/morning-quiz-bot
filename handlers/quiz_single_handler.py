# handlers/quiz_single_handler.py
import random
from datetime import timedelta
from telegram import Update, Poll
from telegram.ext import ContextTypes

from config import logger, POLL_OPEN_S, JOB_GRACE_S # Renamed constants
import state
from quiz_logic import (get_rand_qs, prep_poll_opts, # Renamed functions
                        on_single_q_poll_end) # Renamed handler

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        logger.warning("quiz_command: message or effective_chat is None.")
        return

    cid = update.effective_chat.id # Renamed
    cid_str = str(cid)
    reply_txt = "" # Renamed

    if state.cur_q_sessions.get(cid_str):
        reply_txt = "В этом чате уже идет игра /quiz10. Дождитесь ее окончания или используйте /stopquiz."
        await update.message.reply_text(reply_txt)
        return
    if state.pend_sched_qs.get(cid_str):
        reply_txt = f"В этом чате уже запланирована игра /quiz10notify. Дождитесь ее начала или используйте /stopquiz."
        await update.message.reply_text(reply_txt)
        return

    cat_arg = " ".join(context.args) if context.args else None # Renamed
    q_item_list = [] # Renamed
    msg_pfx = "" # Renamed

    if not state.qs_data:
        reply_txt = "Вопросы еще не загружены. Попробуйте /start позже."
        await update.message.reply_text(reply_txt)
        return

    if not cat_arg:
        avail_cats = [name for name, ql in state.qs_data.items() if isinstance(ql, list) and ql] # Renamed
        if not avail_cats:
            reply_txt = "Нет доступных категорий с вопросами."
            await update.message.reply_text(reply_txt)
            return
        chosen_cat = random.choice(avail_cats) # Renamed
        q_item_list = get_rand_qs(chosen_cat, 1)
        msg_pfx = f"Случайный вопрос из категории: {chosen_cat}\n"
    else:
        q_item_list = get_rand_qs(cat_arg, 1)

    if not q_item_list:
        reply_txt = f"Не найдено вопросов в категории '{cat_arg if cat_arg else 'случайной'}'. Проверьте: /categories"
        await update.message.reply_text(reply_txt)
        return

    single_q_item = q_item_list[0] # Renamed
    poll_q_hdr = f"{msg_pfx}{single_q_item['question']}" # Renamed
    MAX_POLL_Q_LEN = 255
    if len(poll_q_hdr) > MAX_POLL_Q_LEN:
        poll_q_hdr = poll_q_hdr[:MAX_POLL_Q_LEN - 3] + "..."
        logger.warning(f"Текст вопроса для /quiz в {cid_str} был усечен.")

    _, poll_opts, poll_correct_id, _ = prep_poll_opts(single_q_item) # Renamed

    logger.debug(f"Sending /quiz poll to {cid_str}. Question header: '{poll_q_hdr[:100]}...'")
    try:
        sent_poll = await context.bot.send_poll( # Renamed
            chat_id=cid, question=poll_q_hdr, options=poll_opts, type=Poll.QUIZ,
            correct_option_id=poll_correct_id, open_period=POLL_OPEN_S, is_anonymous=False # Renamed const
        )
        poll_entry = { # Renamed
            "chat_id": cid_str, "message_id": sent_poll.message_id,
            "correct_index": poll_correct_id, "quiz_session": False, "daily_quiz": False,
            "question_details": single_q_item, "associated_quiz_session_chat_id": None,
            "next_q_triggered_by_answer": False, "solution_placeholder_message_id": None,
            "processed_by_early_answer": False, "timeout_job": None # Renamed solution_job
        }
        state.cur_polls[sent_poll.poll.id] = poll_entry

        if single_q_item.get("solution"):
            try:
                placeholder_msg = await context.bot.send_message(chat_id=cid_str, text="💡")
                state.cur_polls[sent_poll.poll.id]["solution_placeholder_message_id"] = placeholder_msg.message_id
            except Exception as e_sol_pl:
                 logger.error(f"Не удалось отправить заглушку '💡' для /quiz poll {sent_poll.poll.id} в {cid_str}: {e_sol_pl}")

        if context.job_queue:
            job_delay_s = POLL_OPEN_S + JOB_GRACE_S # Renamed consts
            job_name = f"sq_timeout_chat_{cid_str}_poll_{sent_poll.poll.id}" # Shorter

            for old_job in context.job_queue.get_jobs_by_name(job_name): old_job.schedule_removal()

            timeout_job = context.job_queue.run_once(
                on_single_q_poll_end, timedelta(seconds=job_delay_s), # Renamed handler
                data={"chat_id_str": cid_str, "poll_id": sent_poll.poll.id}, name=job_name
            )
            state.cur_polls[sent_poll.poll.id]["timeout_job"] = timeout_job
            logger.info(f"Запланирован job '{job_name}' для таймаута poll {sent_poll.poll.id} (/quiz).")
    except Exception as e:
        logger.error(f"Ошибка при создании опроса для /quiz в {cid_str}: {e}", exc_info=True)
        await update.message.reply_text("Произошла ошибка при попытке создать вопрос.")
