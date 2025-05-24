# poll_answer_handler.py
from telegram import Update, PollAnswer, User as TelegramUser
from telegram.ext import ContextTypes

# Импорты из других модулей проекта
from config import logger
import state # Для доступа к current_poll, user_scores, current_quiz_session
from data_manager import save_user_data # Для сохранения очков пользователя
from quiz_logic import send_next_question_in_session, show_quiz_session_results
# Removed: send_solution_if_available (solutions are now only sent on timeout by quiz_logic handlers)
from utils import pluralize_points

# Мотивационные сообщения ( остаются без изменений )
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

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.poll_answer:
        logger.debug("handle_poll_answer: update.poll_answer is None, проигнорировано.")
        return

    poll_answer: PollAnswer = update.poll_answer
    user: TelegramUser = poll_answer.user
    answered_poll_id: str = poll_answer.poll_id
    user_id_str = str(user.id)
    user_full_name = user.full_name

    # Получаем информацию об опросе из state.current_poll
    # Важно: poll_info_from_state здесь является ссылкой на объект в словаре state.current_poll.
    # Изменения в poll_info_from_state (например, установка флага) отразятся на оригинальном объекте.
    poll_info_from_state = state.current_poll.get(answered_poll_id)

    if not poll_info_from_state:
        logger.debug(
            f"Информация для poll_id {answered_poll_id} не найдена в state.current_poll. "
            f"Ответ от {user_full_name} ({user_id_str}) проигнорирован."
        )
        return

    chat_id_str = poll_info_from_state["chat_id"]
    # question_details = poll_info_from_state.get("question_details") # Не используется для отправки solution здесь
    question_session_idx = poll_info_from_state.get("question_session_index", -1)

    # ... (логика обновления глобального счета и мотивационных сообщений остается без изменений) ...
    state.user_scores.setdefault(chat_id_str, {}).setdefault(user_id_str, {"name": user.full_name, "score": 0, "answered_polls": set(), "milestones_achieved": set()})
    global_user_data = state.user_scores[chat_id_str][user_id_str]
    global_user_data["name"] = user_full_name
    if not isinstance(global_user_data.get("answered_polls"), set):
        current_answered = global_user_data.get("answered_polls", [])
        global_user_data["answered_polls"] = set(current_answered)
    if not isinstance(global_user_data.get("milestones_achieved"), set):
        milestones = global_user_data.get("milestones_achieved", [])
        global_user_data["milestones_achieved"] = set(milestones)

    is_answer_correct = (len(poll_answer.option_ids) == 1 and poll_answer.option_ids[0] == poll_info_from_state["correct_index"])
    score_change_message = ""
    score_updated_this_time = False
    previous_score = global_user_data["score"]

    if answered_poll_id not in global_user_data["answered_polls"]:
        if is_answer_correct:
            global_user_data["score"] += 1
            score_change_message = "+1 очко"
        else:
            global_user_data["score"] -= 1
            score_change_message = "-1 очко"
        global_user_data["answered_polls"].add(answered_poll_id)
        save_user_data()
        score_updated_this_time = True
        logger.info(
            f"Пользователь {user_full_name} ({user_id_str}) ответил на poll {answered_poll_id} "
            f"{'правильно' if is_answer_correct else 'неправильно'} в чате {chat_id_str}. "
            f"Изменение глобального счета: {score_change_message}. Общий счет: {global_user_data['score']}."
        )
        current_score = global_user_data["score"]
        sorted_thresholds = sorted(MOTIVATIONAL_MESSAGES.keys())
        for threshold in sorted_thresholds:
            message = MOTIVATIONAL_MESSAGES[threshold]
            if threshold in global_user_data["milestones_achieved"]:
                continue
            send_message_flag = False
            if threshold > 0:
                if previous_score < threshold <= current_score: send_message_flag = True
            elif threshold < 0:
                if previous_score > threshold >= current_score: send_message_flag = True
            if send_message_flag:
                try:
                    await context.bot.send_message(chat_id=chat_id_str, text=f"{user.first_name}, {message}")
                    global_user_data["milestones_achieved"].add(threshold)
                    save_user_data()
                except Exception as e:
                    logger.error(f"Не удалось отправить мотивационное сообщение для {threshold} очков пользователю {user_id_str}: {e}")
    else:
        logger.debug(
            f"Пользователь {user_full_name} ({user_id_str}) уже отвечал на poll {answered_poll_id}. Глобальный счет не изменен этим ответом."
        )


    is_quiz_session_poll = poll_info_from_state.get("quiz_session", False)

    # Сообщение о результате одиночного квиза (/quiz) - без изменений, т.к. solution и так был по таймауту
    if not is_quiz_session_poll and score_updated_this_time:
        try:
            reply_text_parts = []
            user_name_display = user.first_name
            if is_answer_correct:
                reply_text_parts.append(f"{user_name_display}, верно! ✅")
            else:
                reply_text_parts.append(f"{user_name_display}, неверно. ❌")
            reply_text_parts.append(f"Твой текущий рейтинг в этом чате: {pluralize_points(global_user_data['score'])}.")
            await context.bot.send_message(chat_id=chat_id_str, text="\n".join(reply_text_parts))
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение с рейтингом/пояснением пользователю {user_id_str} в чат {chat_id_str} после /quiz: {e}", exc_info=True)

    # Логика для сессий /quiz10
    if is_quiz_session_poll:
        session_chat_id = poll_info_from_state.get("associated_quiz_session_chat_id")
        if not session_chat_id:
            logger.error(f"Poll {answered_poll_id} помечен как quiz_session, но associated_quiz_session_chat_id отсутствует.")
            return

        active_session = state.current_quiz_session.get(session_chat_id)
        if active_session:
            # ... (обновление сессионного счета остается без изменений) ...
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
                    session_user_scores_data["score"] -= 1
                    session_score_change_log = "-1"
                session_user_scores_data["answered_this_session_polls"].add(answered_poll_id)
                logger.info(
                    f"Пользователь {user_full_name} ({user_id_str}) получил "
                    f"{session_score_change_log} очко в сессии {session_chat_id} "
                    f"за poll {answered_poll_id} (вопрос {question_session_idx + 1}). Сессионный счет: {session_user_scores_data['score']}."
                )

            # ИЗМЕНЕННАЯ Логика досрочного перехода / обработки ответа на последний вопрос
            # Убедимся, что ответ пришел на текущий активный опрос сессии
            if active_session.get("current_poll_id") == answered_poll_id:
                # Если это НЕ последний вопрос и переход еще не был инициирован для этого опроса
                if not poll_info_from_state.get("is_last_question") and \
                   not poll_info_from_state.get("next_q_triggered_by_answer"): # Флаг на poll_info в state

                    # Помечаем, что переход инициирован этим ответом, чтобы другие ответы на этот же опрос не дублировали действие
                    state.current_poll[answered_poll_id]["next_q_triggered_by_answer"] = True
                    logger.info(
                        f"Досрочный ответ на НЕ последний poll {answered_poll_id} (вопрос {question_session_idx + 1}) в сессии {session_chat_id}. Запускаем следующий вопрос."
                    )
                    # ИЗМЕНЕНИЕ: Не отправляем пояснение здесь. Оно будет по таймауту.

                    # Отменяем запланированный job на таймаут ТЕКУЩЕГО вопроса
                    if job := active_session.get("next_question_job"):
                        try: job.schedule_removal()
                        except Exception: pass
                        active_session["next_question_job"] = None

                    # Удаляем информацию о ТЕКУЩЕМ опросе из state.current_poll, так как он обработан досрочно
                    state.current_poll.pop(answered_poll_id, None)
                    logger.debug(f"Poll {answered_poll_id} (НЕ последний) удален из state.current_poll (досрочный ответ).")

                    await send_next_question_in_session(context, session_chat_id)

                # Если это ПОСЛЕДНИЙ вопрос и его обработка (установка флага) еще не была инициирована
                elif poll_info_from_state.get("is_last_question") and \
                     not poll_info_from_state.get("next_q_triggered_by_answer"):

                    # Помечаем, что ответ на последний вопрос получен и флаг установлен
                    state.current_poll[answered_poll_id]["next_q_triggered_by_answer"] = True
                    logger.info(f"Досрочный ответ на ПОСЛЕДНИЙ poll {answered_poll_id} (вопрос {question_session_idx + 1}) в сессии {session_chat_id}.")

                    # ИЗМЕНЕНИЕ: НЕ отправляем пояснение здесь.
                    # ИЗМЕНЕНИЕ: НЕ отменяем job на таймаут последнего вопроса (next_question_job).
                    #            Этот job (handle_current_poll_end) теперь отвечает за показ результатов в нужное время.
                    # ИЗМЕНЕНИЕ: НЕ удаляем poll из state.current_poll здесь. Пусть handle_current_poll_end его обработает.
                    # ИЗМЕНЕНИЕ: НЕ вызываем show_quiz_session_results здесь.

            else: # Ответ пришел не на текущий активный опрос сессии
                logger.debug(
                    f"Ответ на poll {answered_poll_id} в сессии {session_chat_id} получен, "
                    f"но текущий активный poll сессии уже {active_session.get('current_poll_id')} "
                    "(возможно, ответ запоздал или на старый poll). "
                    "Досрочный переход/обработка не инициированы этим ответом."
                )
        else: # active_session не найдена
            logger.warning(
                f"Сессия для чата {session_chat_id} не найдена в state.current_quiz_session, "
                f"хотя poll {answered_poll_id} указывает на нее. Ответ от {user_full_name} обработан только для глобального счета."
            )
