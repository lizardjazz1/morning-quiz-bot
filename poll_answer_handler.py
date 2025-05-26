# poll_answer_handler.py
from typing import Dict, Any
from telegram import Update, PollAnswer, User as TelegramUser
from telegram.ext import ContextTypes

from config import logger
import state
from data_manager import save_user_data
from quiz_logic import send_next_question_in_session
# quiz_logic.send_solution_if_available будет вызываться из обработчиков таймаутов
from utils import pluralize # MODIFIED: pluralize_points -> pluralize

# Мотивационные сообщения
MOTIVATIONAL_MESSAGES = {
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

async def _ensure_user_initialized(chat_id_str: str, user: TelegramUser) -> Dict[str, Any]:
    user_id_str = str(user.id)
    state.user_scores.setdefault(chat_id_str, {})
    user_data = state.user_scores[chat_id_str].setdefault(user_id_str, {
        "name": user.full_name, "score": 0,
        "answered_polls": set(), "milestones_achieved": set()
    })
    user_data["name"] = user.full_name # Always update name, in case it changed
    if not isinstance(user_data.get("answered_polls"), set): # Ensure sets for older data
        user_data["answered_polls"] = set(user_data.get("answered_polls", []))
    if not isinstance(user_data.get("milestones_achieved"), set):
        user_data["milestones_achieved"] = set(user_data.get("milestones_achieved", []))
    return user_data

async def _process_global_score_and_motivation(
    global_user_data: Dict[str, Any],
    user: TelegramUser,
    chat_id_str: str,
    answered_poll_id: str,
    is_answer_correct: bool,
    context: ContextTypes.DEFAULT_TYPE
) -> bool:
    score_updated_this_time = False
    user_id_str = str(user.id)
    previous_score = global_user_data["score"]

    if answered_poll_id not in global_user_data["answered_polls"]:
        score_change = 1 if is_answer_correct else -1
        global_user_data["score"] += score_change
        global_user_data["answered_polls"].add(answered_poll_id)
        save_user_data() # Save after any change to global score or milestones
        score_updated_this_time = True

        logger.info(
            f"Пользователь {user.full_name} ({user_id_str}) ответил на poll {answered_poll_id} "
            f"{'правильно' if is_answer_correct else 'неправильно'} в чате {chat_id_str}. "
            f"Изменение глобального счета: {('+1' if score_change > 0 else '-1')} очко. "
            f"Общий счет: {global_user_data['score']}."
        )

        current_score = global_user_data["score"]
        milestones_achieved_set = global_user_data["milestones_achieved"]

        for threshold in sorted(MOTIVATIONAL_MESSAGES.keys()):
            if threshold in milestones_achieved_set:
                continue # Already achieved this milestone
            
            send_motivational_message = False
            # Check for positive thresholds: crossed from below
            if threshold > 0 and previous_score < threshold <= current_score:
                send_motivational_message = True
            # Check for negative thresholds: crossed from above (e.g. score went from -10 to -55, previous_score > threshold >= current_score)
            elif threshold < 0 and previous_score > threshold >= current_score:
                 send_motivational_message = True

            if send_motivational_message:
                motivational_text = f"{user.first_name}, {MOTIVATIONAL_MESSAGES[threshold]}"
                logger.debug(f"Attempting to send motivational message to {user_id_str} in {chat_id_str}. Text: '{motivational_text}'")
                try:
                    await context.bot.send_message(chat_id=chat_id_str, text=motivational_text)
                    milestones_achieved_set.add(threshold)
                    save_user_data() # Save after adding a milestone
                except Exception as e:
                    logger.error(f"Не удалось отправить мотивационное сообщение для {threshold} очков пользователю {user_id_str}: {e}")
    else:
        logger.debug(
            f"Пользователь {user.full_name} ({user_id_str}) уже отвечал на poll {answered_poll_id}. "
            "Глобальный счет не изменен этим ответом."
        )
    return score_updated_this_time

async def _send_single_quiz_feedback(
    user: TelegramUser,
    chat_id_str: str,
    is_answer_correct: bool,
    global_user_score: int,
    context: ContextTypes.DEFAULT_TYPE
):
    result_text = "верно! ✅" if is_answer_correct else "неверно. ❌"
    # MODIFIED: pluralize_points -> pluralize, providing specific forms for "очко"
    score_text = pluralize(global_user_score, "очко", "очка", "очков")
    reply_text = (
        f"{user.first_name}, {result_text}\n"
        f"Твой текущий рейтинг в этом чате: {score_text}."
    )
    logger.debug(f"Attempting to send single quiz result to {str(user.id)} in {chat_id_str}. Text: '{reply_text}'")
    try:
        await context.bot.send_message(chat_id=chat_id_str, text=reply_text)
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение с рейтингом для /quiz пользователю {str(user.id)} в чат {chat_id_str}: {e}", exc_info=True)

async def _handle_quiz10_session_poll_answer(
    user: TelegramUser,
    answered_poll_id: str,
    poll_info_from_state: Dict[str, Any],
    is_answer_correct: bool,
    question_session_idx: int,
    context: ContextTypes.DEFAULT_TYPE
):
    user_id_str = str(user.id)
    # This is the chat_id where the /quiz10 session is running, usually same as poll_info_from_state["chat_id"]
    session_chat_id_from_poll = poll_info_from_state.get("associated_quiz_session_chat_id") 

    if not session_chat_id_from_poll:
        logger.error(f"Poll {answered_poll_id} marked as quiz_session, but associated_quiz_session_chat_id is missing.")
        return

    active_session = state.current_quiz_session.get(session_chat_id_from_poll)
    if not active_session:
        logger.warning(
            f"Сессия /quiz10 для чата {session_chat_id_from_poll} не найдена, "
            f"хотя poll {answered_poll_id} указывает на нее. Ответ от {user.full_name} обработан только для глобального счета."
        )
        return

    # Initialize or get session-specific scores for the user
    session_scores_root = active_session.setdefault("session_scores", {})
    session_user_data = session_scores_root.setdefault(
        user_id_str, 
        {"name": user.full_name, "score": 0, "answered_this_session_polls": set()}
    )
    session_user_data["name"] = user.full_name # Update name
    if not isinstance(session_user_data.get("answered_this_session_polls"), set): # Ensure set
         session_user_data["answered_this_session_polls"] = set(session_user_data.get("answered_this_session_polls", []))


    # Update session score only if this is the first time user answers THIS poll in THIS session
    if answered_poll_id not in session_user_data["answered_this_session_polls"]:
        session_score_change = 1 if is_answer_correct else -1
        session_user_data["score"] += session_score_change
        session_user_data["answered_this_session_polls"].add(answered_poll_id)
        logger.info(
            f"Пользователь {user.full_name} ({user_id_str}) получил "
            f"{('+1' if session_score_change > 0 else '-1')} очко в сессии /quiz10 {session_chat_id_from_poll} "
            f"за poll {answered_poll_id} (вопрос {question_session_idx + 1}). " # +1 for 1-based indexing for logs
            f"Сессионный счет: {session_user_data['score']}."
        )
    # else: user already answered this poll in this session, session score not changed again

    # Logic for early transition to next question / handling last question
    # This should only happen if the answered poll is the *current* one for the session
    if active_session.get("current_poll_id") == answered_poll_id:
        is_last_q = poll_info_from_state.get("is_last_question", False)
        
        # next_q_triggered_by_answer: флаг, чтобы только первый ответивший инициировал переход/логику
        if not poll_info_from_state.get("next_q_triggered_by_answer", False):
            poll_info_from_state["next_q_triggered_by_answer"] = True # Помечаем, что этот ответ инициировал логику
            
            if not is_last_q:
                logger.info(
                    f"Досрочный ответ на НЕ последний poll {answered_poll_id} (вопрос {question_session_idx + 1}) "
                    f"в сессии {session_chat_id_from_poll}. Следующий вопрос будет отправлен НЕМЕДЛЕННО. "
                    f"Текущий poll {answered_poll_id} останется открытым до своего таймаута, пояснение по нему будет тогда же."
                )
                # Помечаем, что этот poll был обработан досрочно,
                # чтобы handle_current_poll_end не запускал следующий вопрос повторно
                poll_info_from_state["processed_by_early_answer"] = True 
                
                # НЕ удаляем poll_info_from_state из state.current_poll здесь.
                # НЕ вызываем send_solution_if_available здесь.
                # handle_current_poll_end позаботится о пояснении и удалении poll_info.
                await send_next_question_in_session(context, session_chat_id_from_poll)
            else: # This is the last question
                logger.info(
                    f"Досрочный ответ на ПОСЛЕДНИЙ poll {answered_poll_id} (вопрос {question_session_idx + 1}) "
                    f"в сессии {session_chat_id_from_poll}. Этот poll {answered_poll_id} останется открытым до своего таймаута. "
                    f"Пояснение и результаты будут по таймауту этого вопроса."
                )
                # Также помечаем, чтобы handle_current_poll_end знал (хотя для последнего это менее критично)
                poll_info_from_state["processed_by_early_answer"] = True
                # Таймаут-job (handle_current_poll_end) сам обработает пояснение и вызовет show_quiz_session_results.
    else:
        logger.debug(
            f"Ответ на poll {answered_poll_id} в сессии {session_chat_id_from_poll} получен, "
            f"но текущий активный poll сессии уже {active_session.get('current_poll_id')}. "
            "Досрочный переход не инициирован этим ответом."
        )

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.poll_answer:
        logger.debug("handle_poll_answer: update.poll_answer is None, проигнорировано.")
        return

    poll_answer: PollAnswer = update.poll_answer
    user: TelegramUser = poll_answer.user
    answered_poll_id: str = poll_answer.poll_id

    poll_info_from_state = state.current_poll.get(answered_poll_id)
    if not poll_info_from_state:
        logger.debug(
            f"Информация для poll_id {answered_poll_id} не найдена в state.current_poll. "
            f"Ответ от {user.full_name} ({user.id}) проигнорирован (опрос мог быть завершен/удален)."
        )
        return

    chat_id_str = poll_info_from_state["chat_id"]
    question_session_idx = poll_info_from_state.get("question_session_index", -1)

    global_user_data = await _ensure_user_initialized(chat_id_str, user)
    
    is_answer_correct = (len(poll_answer.option_ids) == 1 and 
                         poll_answer.option_ids[0] == poll_info_from_state["correct_index"])


    score_updated_this_time = await _process_global_score_and_motivation(
        global_user_data, user, chat_id_str, answered_poll_id, is_answer_correct, context
    )

    is_quiz10_session_poll = poll_info_from_state.get("quiz_session", False)
    is_daily_quiz_poll = poll_info_from_state.get("daily_quiz", False)

    if not is_quiz10_session_poll and not is_daily_quiz_poll and score_updated_this_time:
        await _send_single_quiz_feedback(
            user, chat_id_str, is_answer_correct, global_user_data["score"], context
        )
    
    if is_quiz10_session_poll:
        await _handle_quiz10_session_poll_answer(
            user, answered_poll_id, poll_info_from_state, is_answer_correct, question_session_idx, context
        )
