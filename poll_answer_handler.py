# poll_answer_handler.py
from telegram import Update, PollAnswer, User as TelegramUser
from telegram.ext import ContextTypes

# Импорты из других модулей проекта
from config import logger
import state # Для доступа к current_poll, user_scores, current_quiz_session
from data_manager import save_user_data # Для сохранения очков пользователя
from quiz_logic import send_next_question_in_session # Для запуска следующего вопроса в /quiz10
from utils import pluralize_points # Новая функция для склонения слова "очки"

# --- Обработчик ответов на опросы ---
# Эта функция обрабатывает ответы пользователей на опросы (Poll).
# Регистрируется в bot.py.

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.poll_answer: # type: ignore
        logger.debug("handle_poll_answer: update.poll_answer is None, проигнорировано.")
        return

    poll_answer: PollAnswer = update.poll_answer
    user: TelegramUser = poll_answer.user

    answered_poll_id: str = poll_answer.poll_id
    user_id_str = str(user.id)
    user_full_name = user.full_name

    poll_info_from_state = state.current_poll.get(answered_poll_id)

    if not poll_info_from_state:
        logger.debug(
            f"Информация для poll_id {answered_poll_id} не найдена в state.current_poll. "
            f"Ответ от {user_full_name} ({user_id_str}) проигнорирован."
        )
        return

    chat_id_str = poll_info_from_state["chat_id"]

    state.user_scores.setdefault(chat_id_str, {}).setdefault(user_id_str, {"name": user_full_name, "score": 0, "answered_polls": set()})
    global_user_data = state.user_scores[chat_id_str][user_id_str]
    global_user_data["name"] = user_full_name

    if not isinstance(global_user_data.get("answered_polls"), set):
        current_answered = global_user_data.get("answered_polls", [])
        global_user_data["answered_polls"] = set(current_answered)

    is_answer_correct = (len(poll_answer.option_ids) == 1 and poll_answer.option_ids[0] == poll_info_from_state["correct_index"])

    score_change_message = ""
    score_updated_this_time = False
    if answered_poll_id not in global_user_data["answered_polls"]:
        if is_answer_correct:
            global_user_data["score"] += 1
            score_change_message = "+1 очко"
        else:
            global_user_data["score"] -= 1 # Отнимаем очко за неверный ответ
            score_change_message = "-1 очко"

        global_user_data["answered_polls"].add(answered_poll_id)
        save_user_data()
        score_updated_this_time = True
        logger.info(
            f"Пользователь {user_full_name} ({user_id_str}) ответил на poll {answered_poll_id} "
            f"{'правильно' if is_answer_correct else 'неправильно'} в чате {chat_id_str}. "
            f"Изменение глобального счета: {score_change_message}. Общий счет: {global_user_data['score']}."
        )
    else:
        logger.debug(
            f"Пользователь {user_full_name} ({user_id_str}) уже отвечал на poll {answered_poll_id}. Глобальный счет не изменен этим ответом."
        )

    is_quiz_session_poll = poll_info_from_state.get("quiz_session", False)

    if not is_quiz_session_poll and score_updated_this_time:
        try:
            reply_text_parts = []
            user_name_display = user_full_name.split(" ")[0] # Берем первое имя для краткости

            if is_answer_correct:
                reply_text_parts.append(f"{user_name_display}, верно! ✅")
            else:
                q_details = poll_info_from_state.get("question_details")
                correct_option_text = "неизвестен"
                if q_details and "options" in q_details and "correct_option_index" in q_details:
                     correct_original_idx = q_details["correct_option_index"]
                     if 0 <= correct_original_idx < len(q_details["options"]):
                         correct_option_text = q_details["options"][correct_original_idx]
                reply_text_parts.append(f"{user_name_display}, неверно. ❌ Правильный ответ: {correct_option_text}")

            reply_text_parts.append(f"Ваш текущий рейтинг в этом чате: {pluralize_points(global_user_data['score'])}.")
            
            await context.bot.send_message(chat_id=chat_id_str, text="\n".join(reply_text_parts))
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение с рейтингом пользователю {user_id_str} в чат {chat_id_str} после /quiz: {e}", exc_info=True)

    if is_quiz_session_poll:
        session_chat_id = poll_info_from_state.get("associated_quiz_session_chat_id")
        if not session_chat_id:
            logger.error(f"Poll {answered_poll_id} помечен как quiz_session, но associated_quiz_session_chat_id отсутствует.")
            return
            
        active_session = state.current_quiz_session.get(session_chat_id)
        if active_session:
            session_user_scores_data = active_session["session_scores"].setdefault(
                user_id_str, 
                {"name": user_full_name, "score": 0, "answered_this_session_polls": set()}
            )
            session_user_scores_data["name"] = user_full_name
            
            if not isinstance(session_user_scores_data.get("answered_this_session_polls"), set):
                session_user_scores_data["answered_this_session_polls"] = set(session_user_scores_data.get("answered_this_session_polls", []))

            if answered_poll_id not in session_user_scores_data["answered_this_session_polls"]:
                session_score_change_log = ""
                if is_answer_correct:
                    session_user_scores_data["score"] += 1
                    session_score_change_log = "+1"
                else:
                    session_user_scores_data["score"] -= 1 # Также -1 в сессии
                    session_score_change_log = "-1"
                session_user_scores_data["answered_this_session_polls"].add(answered_poll_id)
                logger.info(
                    f"Пользователь {user_full_name} ({user_id_str}) получил "
                    f"{session_score_change_log} очко в сессии {session_chat_id} "
                    f"за poll {answered_poll_id}. Сессионный счет: {session_user_scores_data['score']}."
                )
            
            if not poll_info_from_state.get("is_last_question") and \
               not poll_info_from_state.get("next_q_triggered_by_answer"):
                
                if active_session.get("current_poll_id") == answered_poll_id:
                    poll_info_from_state["next_q_triggered_by_answer"] = True
                    logger.info(
                        f"Досрочный ответ на poll {answered_poll_id} в сессии {session_chat_id}. Запускаем следующий вопрос."
                    )
                    
                    if job := active_session.get("next_question_job"):
                        try: 
                            job.schedule_removal()
                        except Exception: pass 
                        active_session["next_question_job"] = None
                        
                    await send_next_question_in_session(context, session_chat_id)
                else:
                    logger.debug(
                        f"Ответ на poll {answered_poll_id} в сессии {session_chat_id} получен, "
                        f"но текущий активный poll сессии уже {active_session.get('current_poll_id')}. "
                        "Досрочный переход не инициирован."
                    )
        else:
            logger.warning(
                f"Сессия для чата {session_chat_id} не найдена в state.current_quiz_session, "
                f"хотя poll {answered_poll_id} указывает на нее. Ответ от {user_full_name} обработан только для глобального счета."
            )
