# bot/poll_answer_handler.py
import logging
from typing import Optional

from telegram import Update, PollAnswer, User as TelegramUser
from telegram.ext import ContextTypes, PollAnswerHandler as PTBPollAnswerHandler

# from ..app_config import AppConfig # Через конструктор
# from ..state import BotState # Через конструктор
# from ..modules.score_manager import ScoreManager # Через конструктор
# QuizManager может понадобиться для триггера следующего вопроса в сессии
# from ..handlers.quiz_manager import QuizManager # Осторожно с циклическими импортами

logger = logging.getLogger(__name__)

class CustomPollAnswerHandler:
    def __init__(
        self,
        state: 'BotState',
        score_manager: 'ScoreManager',
        app_config: 'AppConfig'
        # quiz_manager: Optional['QuizManager'] = None # Передаем опционально, если нужен
    ):
        self.state = state
        self.score_manager = score_manager
        self.app_config = app_config
        # self.quiz_manager = quiz_manager # Сохраняем, если передан

    async def handle_poll_answer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.poll_answer:
            logger.debug("handle_poll_answer: update.poll_answer is None, игнорируется.")
            return

        poll_answer: PollAnswer = update.poll_answer
        user: TelegramUser = poll_answer.user
        answered_poll_id: str = poll_answer.poll_id

        poll_info_from_state = self.state.current_polls.get(answered_poll_id)
        if not poll_info_from_state:
            logger.debug(
                f"Информация для poll_id {answered_poll_id} не найдена в state.current_polls. "
                f"Ответ от {user.full_name} ({user.id}) проигнорирован (опрос может быть старым/закрытым)."
            )
            return

        chat_id_int: int = poll_info_from_state["chat_id"] # ID чата, где был отправлен опрос
        quiz_type_of_poll: str = poll_info_from_state.get("quiz_type", "unknown")
        
        is_answer_correct = (
            len(poll_answer.option_ids) == 1 and
            poll_answer.option_ids[0] == poll_info_from_state["correct_option_index"]
        )

        # Обновляем счет и получаем текст для мотивационного сообщения
        score_was_updated, motivational_msg_text = await self.score_manager.update_score_and_get_motivation(
            chat_id=chat_id_int,
            user=user,
            poll_id=answered_poll_id,
            is_correct=is_answer_correct,
            quiz_type_of_poll=quiz_type_of_poll
        )

        # Отправляем мотивационное сообщение, если оно есть
        if motivational_msg_text:
            try:
                await context.bot.send_message(chat_id=chat_id_int, text=motivational_msg_text)
            except Exception as e:
                logger.error(f"Не удалось отправить мотивационное сообщение пользователю {user.id} в чат {chat_id_int}: {e}")
        
        # Обратная связь для одиночных викторин (если обновлен счет)
        if quiz_type_of_poll == "single" and score_was_updated:
            # from ..utils import pluralize # Локальный импорт, чтобы не было на уровне модуля
            # user_stats = self.score_manager.get_user_stats_in_chat(chat_id_int, str(user.id))
            # current_score = user_stats["score"] if user_stats else 0
            # result_text = "верно! ✅" if is_answer_correct else "неверно. ❌"
            # score_text_display = pluralize(current_score, "очко", "очка", "очков")
            # reply_text = (
            #     f"{user.first_name}, ваш ответ {result_text}\n"
            #     f"Ваш текущий рейтинг в этом чате: {score_text_display}."
            # )
            # Пока не будем отправлять это сообщение, чтобы не спамить.
            # Решение будет показано по таймауту.
            pass


        # Логика для немедленного перехода к следующему вопросу в сессии (serial_immediate)
        active_quiz_session = self.state.active_quizzes.get(chat_id_int)
        if active_quiz_session and \
           active_quiz_session.get("quiz_mode") == "serial_immediate" and \
           active_quiz_session.get("current_poll_id") == answered_poll_id:
            
            # Отмечаем, что этот опрос обработан ранним ответом
            # Это поможет _handle_poll_end_job не пытаться запустить следующий вопрос еще раз
            poll_info_from_state["processed_by_early_answer"] = True
            
            is_last_q_in_poll = poll_info_from_state.get("is_last_question_in_series", False)
            
            if not is_last_q_in_poll:
                # Чтобы вызвать метод из QuizManager, нужен его экземпляр.
                # Если передавать QuizManager в CustomPollAnswerHandler, это создаст цикл импорта.
                # Лучше, если QuizManager сам подписывается на какое-то событие или
                # CustomPollAnswerHandler просто выставляет флаг, а QuizManager его проверяет.
                # В данном случае, poll_info_from_state["processed_by_early_answer"] = True
                # уже выставлен. _handle_poll_end_job увидит это.
                #
                # Для немедленного перехода можно запланировать _send_next_question_in_session
                # с нулевой задержкой, если QuizManager недоступен напрямую.
                # Но это усложнит логику отмены и синхронизации.
                #
                # Пока что оставим так: _handle_poll_end_job среагирует на таймаут,
                # увидит processed_by_early_answer и не будет дублировать отправку следующего вопроса,
                # если следующий вопрос был уже отправлен каким-то другим механизмом (например, QuizManager слушает ответы).
                #
                # Если мы хотим РЕАЛЬНО немедленный переход, то QuizManager должен иметь метод,
                # который PollAnswerHandler может вызвать.
                # Это сложный вопрос дизайна из-за зависимостей.
                #
                # Вариант: PollAnswerHandler ставит флаг и тут же (если это не последний вопрос)
                # отменяет текущий job таймаута (_handle_poll_end_job) и немедленно запускает
                # _handle_poll_end_job с флагом "early_trigger".
                # Либо QuizManager должен иметь метод типа `quiz_manager.on_answer_received_for_session(chat_id, poll_id)`

                logger.info(
                    f"Ранний ответ на опрос {answered_poll_id} в сессии (serial_immediate) в чате {chat_id_int}. "
                    f"Следующий вопрос будет отправлен по таймауту текущего (если не последний)."
                )
                # Если хотим действительно немедленный переход, нужно будет пересмотреть взаимодействие
                # с QuizManager._send_next_question_in_session или его аналогом.
                # Например, можно было бы здесь запланировать задачу QuizManager._send_next_question_in_session
                # с очень маленькой задержкой или без нее, но это потребует передачи QuizManager.
                #
                # Простейший вариант немедленного эффекта, если таймауты большие:
                # 1. Помечаем processed_by_early_answer = True
                # 2. Отменяем существующий _handle_poll_end_job для этого опроса.
                # 3. Немедленно вызываем _handle_poll_end_job (или его часть, отвечающую за переход).
                # Это нужно делать очень осторожно, чтобы не нарушить состояние.
                #
                # Пока оставляем стандартный поток через таймаут, который учтет флаг.
                # Если open_period маленький, разница будет незаметна.

            else: # Это был последний вопрос в сессии
                logger.info(
                    f"Ранний ответ на ПОСЛЕДНИЙ опрос {answered_poll_id} в сессии (serial_immediate) в чате {chat_id_int}. "
                    f"Результаты будут показаны по таймауту."
                )
        
    def get_handler(self) -> PTBPollAnswerHandler:
        return PTBPollAnswerHandler(self.handle_poll_answer)

