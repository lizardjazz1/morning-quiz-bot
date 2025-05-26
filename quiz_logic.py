# quiz_logic.py
import random
from typing import List, Dict, Any, Tuple, Optional
from datetime import timedelta
from telegram import Update, Poll
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from config import (logger, QS_PER_SESSION, POLL_OPEN_S, JOB_GRACE_S) # Renamed constants
import state
from utils import plural_pts # Renamed function
from handlers.rating_handlers import get_player_display # Used in show_q_sess_res

# --- Вспомогательные функции ---
def get_rand_qs(category: str, count: int = 1) -> List[Dict[str, Any]]: # Renamed
    cat_q_list = state.qs_data.get(category)
    if not isinstance(cat_q_list, list) or not cat_q_list:
        return []
    return [q.copy() for q in random.sample(cat_q_list, min(count, len(cat_q_list)))]

def get_rand_qs_all(count: int) -> List[Dict[str, Any]]: # Renamed
    all_q = [q.copy() for qs_in_cat in state.qs_data.values() if isinstance(qs_in_cat, list) for q in qs_in_cat]
    if not all_q:
        return []
    return random.sample(all_q, min(count, len(all_q)))

def prep_poll_opts(q_item: Dict[str, Any]) -> Tuple[str, List[str], int, List[str]]: # Renamed q_details to q_item
    q_text, opts_orig = q_item["question"], q_item["options"]
    correct_ans_txt = opts_orig[q_item["correct_option_index"]]
    opts_shuf = list(opts_orig) # Renamed
    random.shuffle(opts_shuf)
    try:
        new_correct_idx = opts_shuf.index(correct_ans_txt)
    except ValueError:
        logger.error(f"Не удалось найти '{correct_ans_txt}' в перемешанных опциях: {opts_shuf}. Используем оригинальный индекс.")
        return q_text, list(opts_orig), q_item["correct_option_index"], list(opts_orig)
    return q_text, opts_shuf, new_correct_idx, list(opts_orig)

async def send_sol_if_avail( # Renamed
    context: ContextTypes.DEFAULT_TYPE,
    cid_str: str, # Renamed
    q_item: Dict[str, Any], # Renamed
    q_idx_log: int = -1, # Renamed
    poll_id_lookup: Optional[str] = None # Renamed
):
    solution = q_item.get("solution")
    if not solution:
        return

    q_txt_hdr = q_item.get("question", "завершенному вопросу") # Renamed
    log_q_ref = f"«{q_txt_hdr[:30]}...»" if len(q_txt_hdr) > 30 else f"«{q_txt_hdr}»"
    log_q_ref += f" (вопрос сессии {q_idx_log + 1})" if q_idx_log != -1 else ""

    sol_msg_full = f"💡{solution}" # Renamed
    MAX_MSG_LEN = 4096
    if len(sol_msg_full) > MAX_MSG_LEN:
        sol_msg_full = sol_msg_full[:MAX_MSG_LEN - 3] + "..."
        logger.warning(f"Пояснение для вопроса {log_q_ref} в чате {cid_str} было усечено.")

    placeholder_msg_id: Optional[int] = None
    if poll_id_lookup:
        poll_info = state.cur_polls.get(poll_id_lookup)
        if poll_info:
            placeholder_msg_id = poll_info.get("solution_placeholder_message_id")

    if placeholder_msg_id:
        logger.debug(f"Editing solution placeholder {placeholder_msg_id} in {cid_str} for q {log_q_ref}.")
        try:
            await context.bot.edit_message_text(text=sol_msg_full, chat_id=cid_str, message_id=placeholder_msg_id)
            logger.info(f"Отредактирована заглушка с пояснением для {log_q_ref} в {cid_str}.")
            return
        except BadRequest as e:
            if "Message to edit not found" in str(e) or "message is not modified" in str(e).lower():
                logger.warning(f"Не удалось отредактировать заглушку ({placeholder_msg_id}) для {log_q_ref} в {cid_str}: {e}. Отправка нового.")
            else:
                logger.error(f"BadRequest при редактировании заглушки ({placeholder_msg_id}) для {log_q_ref} в {cid_str}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Ошибка при редактировании заглушки ({placeholder_msg_id}) для {log_q_ref} в {cid_str}: {e}", exc_info=True)

    logger.debug(f"Sending new solution message to {cid_str} for q {log_q_ref}.")
    try:
        await context.bot.send_message(chat_id=cid_str, text=sol_msg_full)
        logger.info(f"Отправлено (новое) пояснение для {log_q_ref} в {cid_str}.")
    except Exception as e:
        logger.error(f"Ошибка при отправке (нового) пояснения для {log_q_ref} в {cid_str}: {e}", exc_info=True)

async def send_next_q_in_sess(context: ContextTypes.DEFAULT_TYPE, cid_str: str): # Renamed
    session = state.cur_q_sessions.get(cid_str)
    if not session:
        logger.warning(f"send_next_q_in_sess: Сессия для {cid_str} не найдена.")
        return

    cur_q_idx = session["current_index"] # Renamed
    actual_q_num = session["actual_num_questions"] # Renamed

    if cur_q_idx >= actual_q_num:
        logger.info(f"Все {actual_q_num} вопросов сессии {cid_str} отправлены. Завершение управляется on_sess_poll_end.")
        return

    q_item = session["questions"][cur_q_idx] # Renamed
    is_last_q = (cur_q_idx == actual_q_num - 1)
    poll_open_duration = POLL_OPEN_S # Renamed constant

    poll_q_txt_api = q_item['question'] # Renamed
    full_poll_q_hdr = f"Вопрос {cur_q_idx + 1}/{actual_q_num}" # Renamed
    if orig_cat := q_item.get("original_category"): # Renamed
        full_poll_q_hdr += f" (Кат: {orig_cat})"
    full_poll_q_hdr += f"\n{poll_q_txt_api}"

    MAX_POLL_Q_LEN = 255 # Renamed
    if len(full_poll_q_hdr) > MAX_POLL_Q_LEN:
        full_poll_q_hdr = full_poll_q_hdr[:MAX_POLL_Q_LEN - 3] + "..."
        logger.warning(f"Текст вопроса для poll в {cid_str} усечен (вопрос сессии {cur_q_idx + 1}).")

    _, poll_opts, poll_correct_id, _ = prep_poll_opts(q_item) # Renamed vars

    logger.debug(f"Sending /quiz10 question {cur_q_idx + 1} to {cid_str}. Header: '{full_poll_q_hdr[:100]}...'")
    try:
        sent_poll = await context.bot.send_poll( # Renamed
            chat_id=cid_str, question=full_poll_q_hdr, options=poll_opts,
            type=Poll.QUIZ, correct_option_id=poll_correct_id,
            open_period=poll_open_duration, is_anonymous=False
        )
        session["current_poll_id"] = sent_poll.poll.id
        session["current_index"] += 1

        cur_poll_entry = { # Renamed
            "chat_id": cid_str, "message_id": sent_poll.message_id,
            "correct_index": poll_correct_id, "quiz_session": True,
            "question_details": q_item, "associated_quiz_session_chat_id": cid_str,
            "is_last_question": is_last_q,
            "next_q_triggered_by_answer": False,
            "question_session_index": cur_q_idx,
            "solution_placeholder_message_id": None,
            "processed_by_early_answer": False
        }
        state.cur_polls[sent_poll.poll.id] = cur_poll_entry
        logger.info(f"Отправлен вопрос {cur_q_idx + 1}/{actual_q_num} сессии {cid_str}. Poll ID: {sent_poll.poll.id}. Last: {is_last_q}")

        if q_item.get("solution"):
            try:
                placeholder_msg = await context.bot.send_message(chat_id=cid_str, text="💡")
                state.cur_polls[sent_poll.poll.id]["solution_placeholder_message_id"] = placeholder_msg.message_id
            except Exception as e_sol_pl:
                logger.error(f"Не удалось отправить заглушку '💡' для poll {sent_poll.poll.id} в {cid_str}: {e_sol_pl}")

        job_delay_s = poll_open_duration + JOB_GRACE_S # Renamed
        job_name = f"poll_end_chat_{cid_str}_poll_{sent_poll.poll.id}" # Shorter
        if context.job_queue:
            for old_job in context.job_queue.get_jobs_by_name(job_name): old_job.schedule_removal()

            poll_end_job = context.job_queue.run_once( # Renamed
                on_sess_poll_end, timedelta(seconds=job_delay_s), # Renamed handler
                data={"chat_id_str": cid_str, "ended_poll_id": sent_poll.poll.id}, name=job_name
            )
            session["next_question_job"] = poll_end_job
    except Exception as e:
        logger.error(f"Ошибка при отправке вопроса сессии ({cur_q_idx + 1}) в {cid_str}: {e}", exc_info=True)
        await show_q_sess_res(context, cid_str, error_occurred=True) # Renamed

async def on_sess_poll_end(context: ContextTypes.DEFAULT_TYPE): # Renamed from handle_current_poll_end
    if not context.job or not context.job.data:
        logger.error("on_sess_poll_end вызван без job data.")
        return

    job_data = context.job.data
    cid_str: str = job_data["chat_id_str"]
    ended_poll_id: str = job_data["ended_poll_id"]

    poll_info = state.cur_polls.get(ended_poll_id)
    session = state.cur_q_sessions.get(cid_str)

    if not poll_info:
        logger.warning(f"Job 'on_sess_poll_end' для poll {ended_poll_id} в {cid_str}: poll_info не найден.")
        if session:
            logger.error(f"Нештатно: poll_info для {ended_poll_id} нет, но сессия {cid_str} активна. Завершение.")
            await show_q_sess_res(context, cid_str, error_occurred=True)
        return

    q_idx_poll = poll_info.get("question_session_index", -1) # Renamed
    logger.info(f"Job 'on_sess_poll_end' сработал для {cid_str}, poll {ended_poll_id} (вопрос ~{q_idx_poll + 1}).")

    await send_sol_if_avail(context, cid_str, poll_info["question_details"], q_idx_poll, ended_poll_id)

    is_last_q_poll = poll_info.get("is_last_question", False) # Renamed
    proc_early = poll_info.get("processed_by_early_answer", False) # Renamed

    state.cur_polls.pop(ended_poll_id, None)
    logger.debug(f"Poll {ended_poll_id} удален из state.cur_polls после таймаута.")

    if not session:
        logger.info(f"Сессия {cid_str} не активна при таймауте poll {ended_poll_id}.")
        return

    if is_last_q_poll:
        logger.info(f"Время для ПОСЛЕДНЕГО вопроса (индекс {q_idx_poll}, poll {ended_poll_id}) сессии {cid_str} истекло.")
        await show_q_sess_res(context, cid_str)
    else:
        if not proc_early:
            logger.info(f"Тайм-аут для НЕ последнего вопроса (индекс {q_idx_poll}, poll {ended_poll_id}) в сессии {cid_str}. Отправляем следующий.")
            await send_next_q_in_sess(context, cid_str)
        else:
            logger.info(f"Таймаут для poll {ended_poll_id} (вопрос {q_idx_poll + 1}), но следующий уже отправлен.")

async def on_single_q_poll_end(context: ContextTypes.DEFAULT_TYPE): # Renamed from handle_single_quiz_poll_end
    if not context.job or not context.job.data:
        logger.error("on_single_q_poll_end: Job data missing.")
        return

    job_data = context.job.data
    cid_str: str = job_data["chat_id_str"]
    poll_id: str = job_data["poll_id"]
    logger.info(f"Job 'on_single_q_poll_end' сработал для poll {poll_id} в {cid_str}.")

    poll_info = state.cur_polls.get(poll_id)

    if poll_info:
        q_item = poll_info.get("question_details") # Renamed
        if not poll_info.get("quiz_session", False) and \
           not poll_info.get("daily_quiz", False) and q_item:
            await send_sol_if_avail(context, cid_str, q_item, poll_id_lookup=poll_id)
        state.cur_polls.pop(poll_id, None)
        logger.info(f"Одиночный квиз (poll {poll_id}) обработан и удален из state.cur_polls.")
    else:
        logger.warning(f"on_single_q_poll_end: Информация для poll {poll_id} ({cid_str}) не найдена.")

async def show_q_sess_res(context: ContextTypes.DEFAULT_TYPE, cid_str: str, error_occurred: bool = False): # Renamed
    session = state.cur_q_sessions.get(cid_str)

    if not session:
        logger.warning(f"show_q_sess_res: Сессия для {cid_str} не найдена.")
        state.cur_q_sessions.pop(cid_str, None)
        return

    if job := session.get("next_question_job"):
        try:
            job.schedule_removal()
            session["next_question_job"] = None
            logger.debug(f"Job {job.name} удален при показе результатов сессии {cid_str}.")
        except Exception: pass

    num_q_sess = session.get("actual_num_questions", QS_PER_SESSION) # Renamed
    res_hdr = "🏁 Викторина завершена! 🏁\n\nРезультаты:\n" if not error_occurred \
              else "Викторина прервана.\n\nПромежуточные результаты:\n" # Shorter
    res_body = "" # Renamed

    sess_scores_data = session.get("session_scores") # Renamed
    if not sess_scores_data:
        res_body = "Никто не участвовал или не набрал очков."
    else:
        sorted_parts = sorted( # Renamed
            sess_scores_data.items(),
            key=lambda item: (-item[1].get("score", 0), item[1].get("name", "").lower())
        )
        for rank, (uid, data) in enumerate(sorted_parts): # Renamed user_id to uid
            usr_name = data.get("name", f"User {uid}") # Renamed
            sess_score = data.get("score", 0) # Renamed
            g_score_data = state.usr_scores.get(cid_str, {}).get(uid, {}) # Renamed
            g_score = g_score_data.get("score", 0) # Renamed
            rank_pfx = f"{rank + 1}." # Renamed

            if rank == 0 and sess_score > 0 : rank_pfx = "🥇"
            elif rank == 1 and sess_score > 0 : rank_pfx = "🥈"
            elif rank == 2 and sess_score > 0 : rank_pfx = "🥉"

            sess_display = get_player_display(usr_name, sess_score, separator=":")
            res_body += (f"{rank_pfx} {sess_display} (из {num_q_sess} вопр.)\n"
                         f"    Общий счёт: {plural_pts(g_score)}\n") # Renamed
        if len(sorted_parts) > 3:
             res_body += "\nОтличная игра, остальные!" # Shorter

    full_res_txt = res_hdr + res_body # Renamed
    logger.debug(f"Sending /quiz10 session results to {cid_str}. Text: '{full_res_txt[:100]}...'")
    try:
        await context.bot.send_message(chat_id=cid_str, text=full_res_txt)
    except Exception as e:
        logger.error(f"Ошибка при отправке результатов сессии в {cid_str}: {e}", exc_info=True)

    cur_poll_id_sess = session.get("current_poll_id") # Renamed
    if cur_poll_id_sess:
        poll_info_rm = state.cur_polls.get(cur_poll_id_sess) # Renamed
        if poll_info_rm and \
           poll_info_rm.get("quiz_session") and \
           str(poll_info_rm.get("associated_quiz_session_chat_id")) == str(cid_str):
            state.cur_polls.pop(cur_poll_id_sess, None)
            logger.debug(f"Poll {cur_poll_id_sess} (сессия) удален из state.cur_polls при завершении сессии {cid_str}.")

    state.cur_q_sessions.pop(cid_str, None)
    logger.info(f"Сессия /quiz10 для {cid_str} очищена (show_q_sess_res).")
