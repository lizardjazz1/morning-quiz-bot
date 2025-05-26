# poll_answer_handler.py
from typing import Dict, Any
from telegram import Update, PollAnswer, User as TelegramUser
from telegram.ext import ContextTypes

from config import logger # No specific constants needed here directly that were renamed
import state
from data_manager import save_usr_data # Renamed
from quiz_logic import send_next_q_in_sess # Renamed
from utils import plural_pts # Renamed

MOTIV_MSGS = { # Renamed from MOTIVATIONAL_MESSAGES
    -1000: "💀 Да ты блин издеваешься, такое не возможно вообще! Попробуй не вытворять больше!",
    -500: "😵 Ну и нуб, прям с порога падает... Поправься уже!",
    -200: "🤦‍♂️ Опять промах? Кажется, тебе пора на тренировку.",
    -50: "🙃 Ну ничего, даже у профессионалов бывают плохие дни... правда?",
    10: "🎉 Поздравляю с первыми 10 очками! Так держать!",
    25: "🌟 25 очков! Ты уже опытный игрок!",
    50: "🔥 50 очков! Ты просто огонь! 🔥",
    100: "👑 100 очков! Моя ты лапочка, умненькость - это про тебя!",
    200: "🚀 200 очков! Ты взлетаешь к вершинам знаний!",
    300: "💎 300 очков! Ты настоящий алмаз в нашем сообществе!",
    500: "🏆 500 очков! Настоящий чемпион!",
    750: "🌈 750 очков! Дал дал ушёл!",
    1000: "✨ 1000 очков! Ты легенда!",
    1500: "🔥 1500 очков! Огонь неистощимой энергии!",
    2000: "🚀 2000 очков! Сверхзвездный уровень!",
    3000: "👑 3000 очков! Царь и бог знаний!",
    5000: "💥 5000 очков! Э-э-это ты создатель вселенной?!",
}

async def _init_usr_score(cid_str: str, user: TelegramUser) -> Dict[str, Any]: # Renamed
    uid_str = str(user.id)
    state.usr_scores.setdefault(cid_str, {})
    usr_data = state.usr_scores[cid_str].setdefault(uid_str, { # Renamed
        "name": user.full_name, "score": 0,
        "answered_polls": set(), "milestones_achieved": set()
    })
    usr_data["name"] = user.full_name
    if not isinstance(usr_data.get("answered_polls"), set):
        usr_data["answered_polls"] = set(usr_data.get("answered_polls", []))
    if not isinstance(usr_data.get("milestones_achieved"), set):
        usr_data["milestones_achieved"] = set(usr_data.get("milestones_achieved", []))
    return usr_data

async def _proc_global_score_motiv( # Renamed
    g_usr_data: Dict[str, Any], # Renamed
    user: TelegramUser,
    cid_str: str,
    ans_poll_id: str, # Renamed
    is_correct: bool, # Renamed
    context: ContextTypes.DEFAULT_TYPE
) -> bool:
    score_updated = False # Renamed
    uid_str = str(user.id)
    prev_score = g_usr_data["score"] # Renamed

    if ans_poll_id not in g_usr_data["answered_polls"]:
        score_chg = 1 if is_correct else -1 # Renamed
        g_usr_data["score"] += score_chg
        g_usr_data["answered_polls"].add(ans_poll_id)
        save_usr_data()
        score_updated = True

        logger.info(
            f"User {user.full_name} ({uid_str}) answered poll {ans_poll_id} "
            f"{'correctly' if is_correct else 'incorrectly'} in chat {cid_str}. " # Shorter
            f"Global score change: {'+1' if score_chg > 0 else '-1'}. "
            f"Total score: {g_usr_data['score']}."
        )

        cur_score = g_usr_data["score"] # Renamed
        milestones_set = g_usr_data["milestones_achieved"] # Renamed

        for threshold in sorted(MOTIV_MSGS.keys()):
            if threshold in milestones_set:
                continue
            send_motiv = False # Renamed
            if threshold > 0 and prev_score < threshold <= cur_score:
                send_motiv = True
            elif threshold < 0 and prev_score > threshold >= cur_score:
                 send_motiv = True

            if send_motiv:
                motiv_txt = f"{user.first_name}, {MOTIV_MSGS[threshold]}" # Renamed
                logger.debug(f"Sending motiv msg to {uid_str} in {cid_str}. Text: '{motiv_txt}'")
                try:
                    await context.bot.send_message(chat_id=cid_str, text=motiv_txt)
                    milestones_set.add(threshold)
                    save_usr_data()
                except Exception as e:
                    logger.error(f"Failed to send motiv msg for {threshold} pts to {uid_str}: {e}")
    else:
        logger.debug(
            f"User {user.full_name} ({uid_str}) already answered poll {ans_poll_id}. "
            "Global score not changed."
        )
    return score_updated

async def _send_single_q_feedback( # Renamed
    user: TelegramUser,
    cid_str: str,
    is_correct: bool,
    g_usr_score: int, # Renamed
    context: ContextTypes.DEFAULT_TYPE
):
    res_txt = "верно! ✅" if is_correct else "неверно. ❌" # Renamed
    reply_txt = ( # Renamed
        f"{user.first_name}, {res_txt}\n"
        f"Твой рейтинг в чате: {plural_pts(g_usr_score)}." # Renamed
    )
    logger.debug(f"Sending single quiz result to {str(user.id)} in {cid_str}. Text: '{reply_txt}'")
    try:
        await context.bot.send_message(chat_id=cid_str, text=reply_txt)
    except Exception as e:
        logger.error(f"Failed to send rating msg for /quiz to {user.id} in {cid_str}: {e}", exc_info=True)

async def _proc_q10_poll_answer( # Renamed
    user: TelegramUser,
    ans_poll_id: str,
    poll_info: Dict[str, Any], # Renamed
    is_correct: bool,
    q_sess_idx: int, # Renamed
    context: ContextTypes.DEFAULT_TYPE
):
    uid_str = str(user.id)
    sess_cid_from_poll = poll_info.get("associated_quiz_session_chat_id") # Renamed

    if not sess_cid_from_poll:
        logger.error(f"Poll {ans_poll_id} quiz_session, but associated_quiz_session_chat_id missing.")
        return

    active_sess = state.cur_q_sessions.get(sess_cid_from_poll) # Renamed
    if not active_sess:
        logger.warning(
            f"/quiz10 session for {sess_cid_from_poll} not found (poll {ans_poll_id}). "
            f"Answer from {user.full_name} processed only for global score."
        )
        return

    sess_scores_root = active_sess.setdefault("session_scores", {})
    sess_usr_data = sess_scores_root.setdefault( # Renamed
        uid_str,
        {"name": user.full_name, "score": 0, "answered_this_session_polls": set()}
    )
    sess_usr_data["name"] = user.full_name
    if not isinstance(sess_usr_data.get("answered_this_session_polls"), set):
         sess_usr_data["answered_this_session_polls"] = set(sess_usr_data.get("answered_this_session_polls", []))

    if ans_poll_id not in sess_usr_data["answered_this_session_polls"]:
        sess_score_chg = 1 if is_correct else -1 # Renamed
        sess_usr_data["score"] += sess_score_chg
        sess_usr_data["answered_this_session_polls"].add(ans_poll_id)
        logger.info(
            f"User {user.full_name} ({uid_str}) got {('+1' if sess_score_chg > 0 else '-1')} pt in session {sess_cid_from_poll} "
            f"for poll {ans_poll_id} (q {q_sess_idx + 1}). Session score: {sess_usr_data['score']}."
        )

    if active_sess.get("current_poll_id") == ans_poll_id:
        is_last_q = poll_info.get("is_last_question", False)

        if not poll_info.get("next_q_triggered_by_answer", False):
            poll_info["next_q_triggered_by_answer"] = True

            if not is_last_q:
                logger.info(
                    f"Early answer on NOT last poll {ans_poll_id} (q {q_sess_idx + 1}) "
                    f"in session {sess_cid_from_poll}. Next Q sent IMMEDIATELY. "
                    f"Poll {ans_poll_id} remains open; solution at its timeout."
                )
                poll_info["processed_by_early_answer"] = True
                await send_next_q_in_sess(context, sess_cid_from_poll) # Renamed
            else:
                logger.info(
                    f"Early answer on LAST poll {ans_poll_id} (q {q_sess_idx + 1}) "
                    f"in session {sess_cid_from_poll}. Poll {ans_poll_id} remains open. "
                    f"Solution and results at its timeout."
                )
                poll_info["processed_by_early_answer"] = True
    else:
        logger.debug(
            f"Answer to poll {ans_poll_id} in session {sess_cid_from_poll} received, "
            f"but current active poll is {active_sess.get('current_poll_id')}. "
            "Early transition not triggered."
        )

async def on_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE): # Renamed
    if not update.poll_answer:
        logger.debug("on_poll_answer: update.poll_answer is None, ignored.")
        return

    poll_ans: PollAnswer = update.poll_answer # Renamed
    user: TelegramUser = poll_ans.user
    ans_poll_id: str = poll_ans.poll_id # Renamed

    poll_info = state.cur_polls.get(ans_poll_id) # Renamed
    if not poll_info:
        logger.debug(
            f"Info for poll_id {ans_poll_id} not found in state.cur_polls. "
            f"Answer from {user.full_name} ({user.id}) ignored."
        )
        return

    cid_str = poll_info["chat_id"]
    q_sess_idx = poll_info.get("question_session_index", -1) # Renamed

    g_usr_data = await _init_usr_score(cid_str, user) # Renamed

    is_correct = (len(poll_ans.option_ids) == 1 and
                  poll_ans.option_ids[0] == poll_info["correct_index"]) # Renamed

    score_updated = await _proc_global_score_motiv( # Renamed
        g_usr_data, user, cid_str, ans_poll_id, is_correct, context
    )

    is_q10_poll = poll_info.get("quiz_session", False) # Renamed
    is_daily_q_poll = poll_info.get("daily_quiz", False) # Renamed

    if not is_q10_poll and not is_daily_q_poll and score_updated:
        await _send_single_q_feedback( # Renamed
            user, cid_str, is_correct, g_usr_data["score"], context
        )

    if is_q10_poll:
        await _proc_q10_poll_answer( # Renamed
            user, ans_poll_id, poll_info, is_correct, q_sess_idx, context
        )
