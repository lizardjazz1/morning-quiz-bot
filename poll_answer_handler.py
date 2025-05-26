# poll_answer_handler.py
from telegram import Update, PollAnswer, User as TelegramUser
from telegram.ext import ContextTypes

from config import logger
import state # Для доступа к current_poll, user_scores, current_quiz_session
from data_manager import save_user_data # Для сохранения очков пользователя
from quiz_logic import send_next_question_in_session
from utils import pluralize_points

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

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.poll_answer:
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
            f"Ответ от {user_full_name} ({user_id_str}) проигнорирован (возможно, опрос уже завершен и удален)."
        )
        return

    chat_id_str = poll_info_from_state["chat_id"]
    question_session_idx = poll_info_from_state.get("question_session_index", -1) # Индекс в /quiz10 сессии или ежедневной

    # Инициализация и обновление данных пользователя
    state.user_scores.setdefault(chat_id_str, {}).setdefault(user_id_str, {"name": user.full_name, "score": 0, "answered_polls": set(), "milestones_achieved": set()})
    global_user_data = state.user_scores[chat_id_str][user_id_str]
    global_user_data["name"] = user_full_name # Обновляем имя на случай смены
    # Убедимся, что поля являются множествами
    if not isinstance(global_user_data.get("answered_polls"), set):
        global_user_data["answered_polls"] = set(global_user_data.get("answered_polls", []))
    if not isinstance(global_user_data.get("milestones_achieved"), set):
        global_user_data["milestones_achieved"] = set(global_user_data.get("milestones_achieved", []))

    is_answer_correct = (len(poll_answer.option_ids) == 1 and poll_answer.option_ids[0] == poll_info_from_state["correct_index"])
    score_change_message = ""
    score_updated_this_time = False
    previous_score = global_user_data["score"]

    # Проверка, не истекло ли время для ежедневного опроса (если применимо)
    # Это дополнительная проверка, если PollAnswer приходит для опроса, который должен был закрыться.
    # Обычно Telegram не должен присылать ответы на уже закрытые опросы.
    is_daily_quiz_poll = poll_info_from_state.get("daily_quiz", False)
    # if is_daily_quiz_poll:
    #     open_timestamp = poll_info_from_state.get("open_timestamp")
    #     poll_duration = config.DAILY_QUIZ_POLL_OPEN_PERIOD_SECONDS # Используем константу
    #     if open_timestamp and (datetime.now(timezone.utc).timestamp() - open_timestamp > poll_duration + config.JOB_GRACE_PERIOD):
    #         logger.info(f"Ответ на ежедневный опрос {answered_poll_id} от {user_full_name} пришел слишком поздно. Очки не начисляются.")
    #         # Тут можно решить не обновлять счет вообще, или не давать очки, но фиксировать ответ
    #         # Для простоты, если ответ пришел, значит Telegram его пропустил, обработаем как обычно.
    #         # Telegram клиент обычно не дает ответить на закрытый опрос.

    if answered_poll_id not in global_user_data["answered_polls"]:
        if is_answer_correct:
            global_user_data["score"] += 1
            score_change_message = "+1 очко"
        else:
            global_user_data["score"] -= 1
            score_change_message = "-1 очко"
        global_user_data["answered_polls"].add(answered_poll_id)
        save_user_data() # Сохраняем после каждого изменения глобального счета
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
            send_motivational_message_flag = False
            if threshold > 0: # Положительные ачивки
                if previous_score < threshold <= current_score: send_motivational_message_flag = True
            elif threshold < 0: # Отрицательные "анти-ачивки"
                if previous_score > threshold >= current_score: send_motivational_message_flag = True
            
            if send_motivational_message_flag:
                motivational_text = f"{user.first_name}, {message}"
                logger.debug(f"Attempting to send motivational message to {user_id_str} in {chat_id_str}. Text: '{motivational_text}'")
                try:
                    await context.bot.send_message(chat_id=chat_id_str, text=motivational_text)
                    global_user_data["milestones_achieved"].add(threshold)
                    save_user_data() # Сохраняем после добавления ачивки
                except Exception as e:
                    logger.error(f"Не удалось отправить мотивационное сообщение для {threshold} очков пользователю {user_id_str}: {e}")
    else:
        logger.debug(
            f"Пользователь {user_full_name} ({user_id_str}) уже отвечал на poll {answered_poll_id}. Глобальный счет не изменен этим ответом."
        )

    is_quiz10_session_poll = poll_info_from_state.get("quiz_session", False)

    # Сообщение о результате одиночного квиза (/quiz)
    if not is_quiz10_session_poll and not is_daily_quiz_poll and score_updated_this_time:
        reply_text_parts = []
        user_name_display = user.first_name
        if is_answer_correct:
            reply_text_parts.append(f"{user_name_display}, верно! ✅")
        else:
            reply_text_parts.append(f"{user_name_display}, неверно. ❌")
        reply_text_parts.append(f"Твой текущий рейтинг в этом чате: {pluralize_points(global_user_data['score'])}.")
        
        single_quiz_reply_text = "\n".join(reply_text_parts)
        logger.debug(f"Attempting to send single quiz result to {user_id_str} in {chat_id_str}. Text: '{single_quiz_reply_text}'")
        try:
            await context.bot.send_message(chat_id=chat_id_str, text=single_quiz_reply_text)
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение с рейтингом для /quiz пользователю {user_id_str} в чат {chat_id_str}: {e}", exc_info=True)

    # Логика для сессий /quiz10
    if is_quiz10_session_poll:
        session_chat_id_from_poll = poll_info_from_state.get("associated_quiz_session_chat_id")
        if not session_chat_id_from_poll:
            logger.error(f"Poll {answered_poll_id} помечен как quiz_session, но associated_quiz_session_chat_id отсутствует.")
            return

        active_session = state.current_quiz_session.get(session_chat_id_from_poll)
        if active_session:
            session_user_scores_data = active_session["session_scores"].setdefault(
                user_id_str,
                {"name": user_full_name, "score": 0, "answered_this_session_polls": set()}
            )
            session_user_scores_data["name"] = user_full_name # Обновляем имя
            if not isinstance(session_user_scores_data.get("answered_this_session_polls"), set):
                 session_user_scores_data["answered_this_session_polls"] = set(session_user_scores_data.get("answered_this_session_polls", []))

            if answered_poll_id not in session_user_scores_data["answered_this_session_polls"]:
                session_score_change_log = ""
                if is_answer_correct:
                    session_user_scores_data["score"] += 1
                    session_score_change_log = "+1"
                else:
                    session_user_scores_data["score"] -= 1 # В сессии тоже отнимаем за неверный первый ответ
                    session_score_change_log = "-1"
                session_user_scores_data["answered_this_session_polls"].add(answered_poll_id)
                logger.info(
                    f"Пользователь {user_full_name} ({user_id_str}) получил "
                    f"{session_score_change_log} очко в сессии /quiz10 {session_chat_id_from_poll} "
                    f"за poll {answered_poll_id} (вопрос {question_session_idx + 1}). Сессионный счет: {session_user_scores_data['score']}."
                )

            # Логика досрочного перехода / обработки ответа на последний вопрос
            if active_session.get("current_poll_id") == answered_poll_id: # Ответ на ТЕКУЩИЙ опрос сессии
                if not poll_info_from_state.get("is_last_question") and \
                   not poll_info_from_state.get("next_q_triggered_by_answer"): # Флаг еще не установлен

                    state.current_poll[answered_poll_id]["next_q_triggered_by_answer"] = True # Ставим флаг
                    logger.info(
                        f"Досрочный ответ на НЕ последний poll {answered_poll_id} (вопрос {question_session_idx + 1}) в сессии {session_chat_id_from_poll}. "
                        "Отправка пояснения и следующего вопроса будет по таймауту текущего или этим job'ом, если он еще не был удален."
                    )
                    
                    # Отменяем job на таймаут ТЕКУЩЕГО вопроса, так как мы сейчас его обработаем
                    if job := active_session.get("next_question_job"):
                        try: job.schedule_removal()
                        except Exception: pass
                        active_session["next_question_job"] = None
                        logger.debug(f"Таймаут-job для poll {answered_poll_id} отменен из-за досрочного ответа.")

                    # Отправляем пояснение НЕМЕДЛЕННО
                    await quiz_logic.send_solution_if_available(context, session_chat_id_from_poll, poll_info_from_state["question_details"], question_session_idx)
                    
                    # Удаляем информацию о ТЕКУЩЕМ опросе из state.current_poll
                    state.current_poll.pop(answered_poll_id, None)
                    logger.debug(f"Poll {answered_poll_id} (НЕ последний) удален из state.current_poll (досрочный ответ).")

                    # Запускаем следующий вопрос
                    await send_next_question_in_session(context, session_chat_id_from_poll)

                elif poll_info_from_state.get("is_last_question") and \
                     not poll_info_from_state.get("next_q_triggered_by_answer"): # Флаг еще не установлен

                    state.current_poll[answered_poll_id]["next_q_triggered_by_answer"] = True # Ставим флаг
                    logger.info(f"Досрочный ответ на ПОСЛЕДНИЙ poll {answered_poll_id} (вопрос {question_session_idx + 1}) в сессии {session_chat_id_from_poll}. "
                                "Пояснение и результаты будут по таймауту.")
                    # НЕ отменяем job на таймаут последнего вопроса (handle_current_poll_end).
                    # Этот job теперь отвечает за показ результатов и отправку пояснения в нужное время.
                    # НЕ удаляем poll из state.current_poll здесь. Пусть handle_current_poll_end его обработает.
                    # НЕ вызываем show_quiz_session_results здесь.
            else:
                logger.debug(
                    f"Ответ на poll {answered_poll_id} в сессии {session_chat_id_from_poll} получен, "
                    f"но текущий активный poll сессии уже {active_session.get('current_poll_id')}. "
                    "Досрочный переход не инициирован этим ответом."
                )
        else:
            logger.warning(
                f"Сессия /quiz10 для чата {session_chat_id_from_poll} не найдена в state.current_quiz_session, "
                f"хотя poll {answered_poll_id} указывает на нее. Ответ от {user_full_name} обработан только для глобального счета."
            )

