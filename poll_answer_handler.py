# poll_answer_handler.py
from telegram import Update, PollAnswer, User as TelegramUser
from telegram.ext import ContextTypes

# Импорты из других модулей проекта
from config import logger
import state # Для доступа к current_poll, user_scores, current_quiz_session
from data_manager import save_user_data # Для сохранения очков пользователя
# send_next_question_in_session И send_solution_if_available ИЗ quiz_logic
from quiz_logic import send_next_question_in_session, send_solution_if_available, show_quiz_session_results 
from utils import pluralize_points # Обновленная функция для склонения слова "очки"

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
    question_details = poll_info_from_state.get("question_details") # Получаем детали вопроса, включая возможное решение
    # Индекс вопроса в сессии (если это сессионный вопрос)
    question_session_idx = poll_info_from_state.get("question_session_index", -1)


    # Инициализация или обновление данных пользователя в глобальном хранилище user_scores
    state.user_scores.setdefault(chat_id_str, {}).setdefault(user_id_str, {"name": user_full_name, "score": 0, "answered_polls": set(), "milestones_achieved": set()})
    global_user_data = state.user_scores[chat_id_str][user_id_str]
    global_user_data["name"] = user_full_name # Обновляем имя на случай смены

    # Убедимся, что answered_polls и milestones_achieved являются множествами
    if not isinstance(global_user_data.get("answered_polls"), set):
        current_answered = global_user_data.get("answered_polls", [])
        global_user_data["answered_polls"] = set(current_answered)
    if not isinstance(global_user_data.get("milestones_achieved"), set):
        milestones = global_user_data.get("milestones_achieved", [])
        global_user_data["milestones_achieved"] = set(milestones)

    is_answer_correct = (len(poll_answer.option_ids) == 1 and poll_answer.option_ids[0] == poll_info_from_state["correct_index"])

    score_change_message = ""
    score_updated_this_time = False
    previous_score = global_user_data["score"] # Сохраняем счет до изменения

    if answered_poll_id not in global_user_data["answered_polls"]:
        if is_answer_correct:
            global_user_data["score"] += 1
            score_change_message = "+1 очко"
        else:
            global_user_data["score"] -= 1 # Отнимаем очко за неверный ответ
            score_change_message = "-1 очко"

        global_user_data["answered_polls"].add(answered_poll_id)
        save_user_data() # Сохраняем после каждого изменения счета
        score_updated_this_time = True
        logger.info(
            f"Пользователь {user_full_name} ({user_id_str}) ответил на poll {answered_poll_id} "
            f"{'правильно' if is_answer_correct else 'неправильно'} в чате {chat_id_str}. "
            f"Изменение глобального счета: {score_change_message}. Общий счет: {global_user_data['score']}."
        )

        # --- ОБНОВЛЕННАЯ ЛОГИКА ДЛЯ МОТИВАЦИОННЫХ СООБЩЕНИЙ ---
        current_score = global_user_data["score"]
        
        # Сортируем пороги, чтобы проходить по ним в строгом порядке (от наименьшего к наибольшему)
        sorted_thresholds = sorted(MOTIVATIONAL_MESSAGES.keys())

        for threshold in sorted_thresholds:
            message = MOTIVATIONAL_MESSAGES[threshold]
            
            # Если этот порог уже был достигнут/пройден, пропускаем его, чтобы не дублировать сообщения
            if threshold in global_user_data["milestones_achieved"]:
                continue

            send_message = False

            if threshold > 0: # Положительные пороги (10, 25, 50, ...)
                if previous_score < threshold <= current_score:
                    send_message = True
            elif threshold < 0: # Отрицательные пороги (-50, -200, -500, ...)
                if previous_score > threshold >= current_score:
                    send_message = True

            if send_message:
                try:
                    await context.bot.send_message(chat_id=chat_id_str, text=f"{user.first_name}, {message}")
                    global_user_data["milestones_achieved"].add(threshold)
                    save_user_data() 
                except Exception as e:
                    logger.error(f"Не удалось отправить мотивационное сообщение для {threshold} очков пользователю {user_id_str}: {e}")
        # --- КОНЕЦ ОБНОВЛЕННОЙ ЛОГИКИ ---

    else:
        logger.debug(
            f"Пользователь {user_full_name} ({user_id_str}) уже отвечал на poll {answered_poll_id}. Глобальный счет не изменен этим ответом."
        )

    # Сообщение о результате одиночного квиза (/quiz)
    is_quiz_session_poll = poll_info_from_state.get("quiz_session", False)
    if not is_quiz_session_poll and score_updated_this_time: # Только если это одиночный квиз и счет был обновлен
        try:
            reply_text_parts = []
            user_name_display = user.first_name # Используем только имя для краткости

            if is_answer_correct:
                reply_text_parts.append(f"{user_name_display}, верно! ✅")
            else:
                # question_details уже получены выше
                correct_option_text = "неизвестен"
                if question_details and "options" in question_details and "correct_option_index" in question_details:
                     correct_original_idx = question_details["correct_option_index"]
                     if 0 <= correct_original_idx < len(question_details["options"]):
                         correct_option_text = question_details["options"][correct_original_idx]
                reply_text_parts.append(f"{user_name_display}, неверно. ❌ Правильный ответ: {correct_option_text}")

            # Добавляем пояснение, если оно есть (ДЛЯ ОДИНОЧНОГО КВИЗА)
            if question_details and question_details.get("solution"):
                reply_text_parts.append(f"💡 Пояснение: {question_details['solution']}")

            reply_text_parts.append(f"Твой текущий рейтинг в этом чате: {pluralize_points(global_user_data['score'])}.")

            # Отправляем сообщение в чат, где был опрос
            await context.bot.send_message(chat_id=chat_id_str, text="\n".join(reply_text_parts))
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение с рейтингом/пояснением пользователю {user_id_str} в чат {chat_id_str} после /quiz: {e}", exc_info=True)

    # Логика для сессий /quiz10
    if is_quiz_session_poll:
        session_chat_id = poll_info_from_state.get("associated_quiz_session_chat_id")
        if not session_chat_id: # Должен быть всегда для сессионного опроса
            logger.error(f"Poll {answered_poll_id} помечен как quiz_session, но associated_quiz_session_chat_id отсутствует.")
            return

        active_session = state.current_quiz_session.get(session_chat_id)
        if active_session:
            # Инициализация или обновление данных пользователя в сессионном хранилище
            session_user_scores_data = active_session["session_scores"].setdefault(
                user_id_str,
                {"name": user_full_name, "score": 0, "answered_this_session_polls": set()}
            )
            session_user_scores_data["name"] = user_full_name # Обновляем имя

            if not isinstance(session_user_scores_data.get("answered_this_session_polls"), set):
                 session_user_scores_data["answered_this_session_polls"] = set(session_user_scores_data.get("answered_this_session_polls", []))

            # Обновление сессионного счета, если пользователь еще не отвечал на ЭТОТ опрос в рамках ЭТОЙ сессии
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
                    f"за poll {answered_poll_id} (вопрос {question_session_idx + 1}). Сессионный счет: {session_user_scores_data['score']}."
                )

            # Логика досрочного перехода к следующему вопросу в /quiz10
            # poll_info_from_state["next_q_triggered_by_answer"] предотвращает многократный запуск следующего вопроса от нескольких быстрых ответов
            if not poll_info_from_state.get("is_last_question") and \
               not poll_info_from_state.get("next_q_triggered_by_answer"):

                # Убедимся, что ответ пришел на текущий активный опрос сессии
                if active_session.get("current_poll_id") == answered_poll_id:
                    poll_info_from_state["next_q_triggered_by_answer"] = True # Помечаем, что переход инициирован этим ответом
                    
                    logger.info(
                        f"Досрочный ответ на poll {answered_poll_id} (вопрос {question_session_idx + 1}) в сессии {session_chat_id}. Запускаем следующий вопрос."
                    )

                    # Отправляем пояснение к текущему (завершающемуся) вопросу ПЕРЕД переходом
                    # question_details из poll_info_from_state, question_session_idx тоже оттуда
                    if question_details:
                        await send_solution_if_available(context, session_chat_id, question_details, question_session_idx)

                    # Отменяем запланированный job на таймаут текущего вопроса
                    if job := active_session.get("next_question_job"):
                        try:
                            job.schedule_removal()
                            logger.debug(f"Job {job.name} отменен из-за досрочного ответа на poll {answered_poll_id}.")
                        except Exception: pass # может быть уже выполнен или удален
                        active_session["next_question_job"] = None # Очищаем ссылку на job

                    # Удаляем информацию о текущем опросе из state.current_poll, так как он обработан
                    # Это критично, чтобы handle_current_poll_end не пытался его обработать снова по таймауту.
                    state.current_poll.pop(answered_poll_id, None)
                    logger.debug(f"Poll {answered_poll_id} (вопрос {question_session_idx + 1}) удален из state.current_poll (досрочный ответ).")

                    await send_next_question_in_session(context, session_chat_id)
                else:
                    logger.debug(
                        f"Ответ на poll {answered_poll_id} в сессии {session_chat_id} получен, "
                        f"но текущий активный poll сессии уже {active_session.get('current_poll_id')} (возможно, ответ запоздал или на старый poll). "
                        "Досрочный переход не инициирован этим ответом."
                    )
            elif poll_info_from_state.get("is_last_question") and not poll_info_from_state.get("next_q_triggered_by_answer"):
                 # Если это был последний вопрос, и ответ пришел
                 if active_session.get("current_poll_id") == answered_poll_id:
                    poll_info_from_state["next_q_triggered_by_answer"] = True # Помечаем, что обработан
                    logger.info(f"Досрочный ответ на последний poll {answered_poll_id} (вопрос {question_session_idx + 1}) в сессии {session_chat_id}.")
                    if question_details:
                        await send_solution_if_available(context, session_chat_id, question_details, question_session_idx)
                    
                    if job := active_session.get("next_question_job"): # Отменяем таймаут последнего вопроса
                        try: job.schedule_removal()
                        except: pass
                        active_session["next_question_job"] = None
                    
                    state.current_poll.pop(answered_poll_id, None) # Удаляем из активных
                    logger.debug(f"Последний poll {answered_poll_id} удален из state.current_poll (досрочный ответ).")
                    
                    # Завершаем сессию и показываем результаты
                    await show_quiz_session_results(context, session_chat_id)


        else: # active_session не найдена
            logger.warning(
                f"Сессия для чата {session_chat_id} не найдена в state.current_quiz_session, "
                f"хотя poll {answered_poll_id} указывает на нее. Ответ от {user_full_name} обработан только для глобального счета."
            )
