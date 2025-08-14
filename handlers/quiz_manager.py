#handlers/quiz_manager.py
from __future__ import annotations
import asyncio
import logging
from typing import List, Optional, Union, Dict, Any
from datetime import timedelta
import datetime as dt 
import pytz 

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, User as TelegramUser, Message, CallbackQuery
)
from telegram.ext import Application, ContextTypes, CommandHandler, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.constants import ParseMode
from telegram.error import BadRequest

from app_config import AppConfig
from state import BotState, QuizState 
from data_manager import DataManager
from modules.category_manager import CategoryManager
from modules.score_manager import ScoreManager
from modules.quiz_engine import QuizEngine
from utils import get_current_utc_time, schedule_job_unique, escape_markdown_v2, is_user_admin_in_update

logger = logging.getLogger(__name__)

(CFG_QUIZ_OPTIONS, CFG_QUIZ_NUM_QS) = map(str, range(2))

CB_QCFG_ = "qcfg_"
CB_QCFG_NUM_MENU = f"{CB_QCFG_}num_menu"
CB_QCFG_NUM_VAL = f"{CB_QCFG_}num_val"
CB_QCFG_CAT_MENU = f"{CB_QCFG_}cat_menu"
CB_QCFG_CAT_VAL = f"{CB_QCFG_}cat_val"
CB_QCFG_ANNOUNCE = f"{CB_QCFG_}announce"
CB_QCFG_START = f"{CB_QCFG_}start"
CB_QCFG_CANCEL = f"{CB_QCFG_}cancel"
CB_QCFG_BACK = f"{CB_QCFG_}back_to_main_opts"
CB_QCFG_NOOP = f"{CB_QCFG_}noop"

DELAY_BEFORE_SESSION_MESSAGES_DELETION_SECONDS = 300  
DELAY_BEFORE_POLL_SOLUTION_DELETION_SECONDS = 120 

class QuizManager:
    def __init__(
        self, app_config: AppConfig, state: BotState, category_manager: CategoryManager,
        score_manager: ScoreManager, data_manager: DataManager, application: Application
    ):
        self.app_config = app_config
        self.state = state
        self.category_manager = category_manager
        self.score_manager = score_manager
        self.data_manager = data_manager
        self.application = application
        self.quiz_engine = QuizEngine(state=self.state, app_config=self.app_config, data_manager=self.data_manager)
        self.moscow_tz = pytz.timezone('Europe/Moscow')
        logger.debug(f"QuizManager initialized. Command for quiz: '/{self.app_config.commands.quiz}'")

    def _get_effective_quiz_params(self, chat_id: int, num_questions_override: Optional[int] = None) -> Dict[str, Any]:
        chat_s = self.data_manager.get_chat_settings(chat_id)
        default_chat_settings_global = self.app_config.default_chat_settings
        num_q: int
        if num_questions_override is not None:
            num_q = max(1, min(num_questions_override, self.app_config.max_questions_per_session))
        else:
            num_q = chat_s.get("default_num_questions", default_chat_settings_global.get("default_num_questions", 10))

        if num_q == 1:
            quiz_type_key_for_params_lookup = "single"
        else:
            quiz_type_key_for_params_lookup = chat_s.get("default_quiz_type")
            if not quiz_type_key_for_params_lookup:
                 quiz_type_key_for_params_lookup = default_chat_settings_global.get("default_quiz_type", "session")

        type_cfg_for_params = self.app_config.quiz_types_config.get(quiz_type_key_for_params_lookup, {})

        return {
            "quiz_type_key": quiz_type_key_for_params_lookup,
            "quiz_mode": type_cfg_for_params.get("mode", "single_question" if num_q == 1 else "serial_immediate"),
            "num_questions": num_q,
            "open_period_seconds": chat_s.get("default_open_period_seconds", type_cfg_for_params.get("default_open_period_seconds", default_chat_settings_global.get("default_open_period_seconds",30))),
            "announce_quiz": chat_s.get("default_announce_quiz", type_cfg_for_params.get("announce", default_chat_settings_global.get("default_announce_quiz", False))),
            "announce_delay_seconds": chat_s.get("default_announce_delay_seconds", type_cfg_for_params.get("announce_delay_seconds", default_chat_settings_global.get("default_announce_delay_seconds", 5))),
            "interval_seconds": type_cfg_for_params.get("default_interval_seconds"),
            "enabled_categories_chat": chat_s.get("enabled_categories"),
            "disabled_categories_chat": chat_s.get("disabled_categories", []),
        }

    async def _initiate_quiz_session(
        self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, initiated_by_user: Optional[TelegramUser],
        quiz_type: str, quiz_mode: str, num_questions: int, open_period_seconds: int,
        announce: bool, announce_delay_seconds: int,
        category_names_for_quiz: Optional[List[str]] = None,
        is_random_categories_mode: bool = False,
        interval_seconds: Optional[int] = None,
        original_command_message_id: Optional[int] = None,
        interactive_start_message_id: Optional[int] = None
    ):
        logger.info(f"НАЧАЛО _initiate_quiz_session: Чат {chat_id}, Тип: {quiz_type}, Режим: {quiz_mode}, NQ: {num_questions}")

        active_quiz = self.state.get_active_quiz(chat_id)
        if active_quiz and not active_quiz.is_stopping:
            logger.warning(f"_initiate_quiz_session: Викторина уже активна в чате {chat_id}.")
            if initiated_by_user:
                 await context.bot.send_message(chat_id, escape_markdown_v2(f"Викторина уже идет. Остановите текущую (`/{self.app_config.commands.stop_quiz}`)."), parse_mode=ParseMode.MARKDOWN_V2)
            return

        cat_mode_for_get_questions: str
        if is_random_categories_mode:
            cat_mode_for_get_questions = "random_from_pool"
        elif category_names_for_quiz:
            cat_mode_for_get_questions = "specific_only"
        else:
            cat_mode_for_get_questions = "random_from_pool"

        logger.debug(f"_initiate_quiz_session: Получение вопросов. Режим для get_questions: {cat_mode_for_get_questions}, Исходные запрашиваемые категории: {category_names_for_quiz}")
        questions_for_session = self.category_manager.get_questions(
            num_questions_needed=num_questions,
            chat_id=chat_id,
            allowed_specific_categories=category_names_for_quiz if cat_mode_for_get_questions == "specific_only" else None,
            mode=cat_mode_for_get_questions
        )
        logger.debug(f"_initiate_quiz_session: Получено {len(questions_for_session)} вопросов.")

        actual_num_questions_obtained = len(questions_for_session)
        if actual_num_questions_obtained == 0:
            msg_no_q = "Не удалось подобрать вопросы для викторины. Проверьте настройки категорий или попробуйте позже."
            logger.warning(f"_initiate_quiz_session: {msg_no_q} (Чат: {chat_id}, NQ: {num_questions}, Режим кат: {cat_mode_for_get_questions}, Список кат: {category_names_for_quiz})")
            if initiated_by_user:
                await context.bot.send_message(chat_id, escape_markdown_v2(msg_no_q), parse_mode=ParseMode.MARKDOWN_V2)
            if interactive_start_message_id:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=interactive_start_message_id)
                    logger.debug(f"Сообщение о запуске ({interactive_start_message_id}) удалено, т.к. викторина не стартовала.")
                except Exception as e_del_launch_msg_fail:
                    logger.warning(f"Не удалось удалить сообщение о запуске ({interactive_start_message_id}) при неудачном старте викторины: {e_del_launch_msg_fail}")
            return

        if actual_num_questions_obtained < num_questions:
            logger.info(f"_initiate_quiz_session: Запрошено {num_questions}, доступно {actual_num_questions_obtained}. Викторина будет с {actual_num_questions_obtained} вопросами. Чат: {chat_id}")
            num_questions = actual_num_questions_obtained

        user_id_int_for_state: Optional[int] = int(initiated_by_user.id) if initiated_by_user else None
        current_quiz_state_instance = QuizState(
            chat_id=chat_id, quiz_type=quiz_type, quiz_mode=quiz_mode,
            questions=questions_for_session, num_questions_to_ask=num_questions,
            open_period_seconds=open_period_seconds, created_by_user_id=user_id_int_for_state,
            original_command_message_id=original_command_message_id,
            interval_seconds=interval_seconds, quiz_start_time=get_current_utc_time()
        )

        if interactive_start_message_id:
            current_quiz_state_instance.message_ids_to_delete.add(interactive_start_message_id)
            logger.debug(f"Сообщение о запуске из интерактива ({interactive_start_message_id}) добавлено в список на удаление (служебные).")

        if announce:
            announce_text_parts = []
            if quiz_type == "daily":
                greeting = ""
                try:
                    current_time_msk = dt.datetime.now(self.moscow_tz)
                    current_hour_msk = current_time_msk.hour

                    if 5 <= current_hour_msk <= 11: greeting = "Доброе утро☀️"
                    elif 12 <= current_hour_msk <= 16: greeting = "Добрый день🌞"
                    elif 17 <= current_hour_msk <= 22: greeting = "Добрый вечер🌙"
                    else: greeting = "Доброй ночи✨"
                    announce_text_parts.append(escape_markdown_v2(f"{greeting}!"))
                except Exception as e_greeting:
                    logger.warning(f"Не удалось определить приветствие по времени для ежедневной викторины: {e_greeting}")
                    announce_text_parts.append(escape_markdown_v2("Привет!"))

                announce_text_parts.append(escape_markdown_v2("Начинается ежедневная викторина."))
                used_categories_set = {q_data.get('current_category_name_for_quiz', q_data.get('original_category')) for q_data in questions_for_session if q_data.get('current_category_name_for_quiz') or q_data.get('original_category')}
                if used_categories_set:
                    announce_text_parts.append(escape_markdown_v2(f"Темы сегодня: {', '.join(sorted(list(used_categories_set)))}."))
                else:
                    announce_text_parts.append(escape_markdown_v2("Темы будут сюрпризом!"))
                if announce_delay_seconds > 0:
                    announce_text_parts.append(f"Старт через {escape_markdown_v2(str(announce_delay_seconds))} сек\\!")
            else:
                if initiated_by_user:
                    announce_text_parts.append(f"{escape_markdown_v2(initiated_by_user.first_name)} запускает викторину\\!")
                if announce_delay_seconds > 0:
                    announce_text_parts.append(f"🔔 Викторина начнется через {escape_markdown_v2(str(announce_delay_seconds))} сек\\!")
                elif not interactive_start_message_id and not initiated_by_user : # Для не-daily, не-интерактивного, немедленного старта без user_id (не должно быть)
                    announce_text_parts.append(escape_markdown_v2("🏁 Викторина начинается!"))

            full_announce_text = " ".join(announce_text_parts)
            if full_announce_text.strip():
                try:
                    msg = await context.bot.send_message(chat_id, full_announce_text, parse_mode=ParseMode.MARKDOWN_V2)
                    current_quiz_state_instance.announce_message_id = msg.message_id
                    current_quiz_state_instance.message_ids_to_delete.add(msg.message_id)
                    # Добавляем в глобальный список для периодической очистки
                    self.state.add_message_for_deletion(chat_id, msg.message_id)
                except Exception as e_announce:
                    logger.error(f"Ошибка отправки анонса (delay: {announce_delay_seconds > 0}) в чат {chat_id}: {e_announce}")
            else:
                logger.debug(f"Текст анонса пуст для чата {chat_id}, отправка пропущена.")

            if announce_delay_seconds > 0:
                self.state.add_active_quiz(chat_id, current_quiz_state_instance)
                logger.info(f"_initiate_quiz_session: QuizState создан и добавлен для чата {chat_id}. Тип: {quiz_type}. Ожидание {announce_delay_seconds} сек...")
                await asyncio.sleep(announce_delay_seconds)
                logger.debug(f"Ожидание завершено для чата {chat_id}.")
                quiz_state_after_delay_check = self.state.get_active_quiz(chat_id)
                if not quiz_state_after_delay_check or quiz_state_after_delay_check.is_stopping or quiz_state_after_delay_check != current_quiz_state_instance:
                    logger.info(f"Викторина в чате {chat_id} была остановлена/заменена во время задержки анонса. Запуск отменен.")
                    if self.state.get_active_quiz(chat_id) == current_quiz_state_instance:
                        self.state.remove_active_quiz(chat_id) 
                    return
            else: 
                self.state.add_active_quiz(chat_id, current_quiz_state_instance)
                logger.info(f"_initiate_quiz_session: QuizState (немедленный анонс или без анонса если текст пуст) создан и добавлен для чата {chat_id}. Тип: {quiz_type}")
        else: 
            self.state.add_active_quiz(chat_id, current_quiz_state_instance)
            logger.info(f"_initiate_quiz_session: QuizState (без анонса) создан и добавлен для чата {chat_id}. Тип: {quiz_type}")

        logger.info(f"_initiate_quiz_session: Переход к отправке первого вопроса для чата {chat_id}.")
        await self._send_next_question(context, chat_id)

    async def _send_next_question(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        logger.debug(f"НАЧАЛО _send_next_question для чата {chat_id}.")
        quiz_state = self.state.get_active_quiz(chat_id)

        if not quiz_state or quiz_state.is_stopping:
            logger.warning(f"_send_next_question: Викторина неактивна или останавливается для чата {chat_id}.")
            return

        if quiz_state.current_question_index >= quiz_state.num_questions_to_ask:
            logger.info(f"_send_next_question: Все {quiz_state.num_questions_to_ask} вопросов для чата {chat_id} уже отправлены.")
            return

        question_data = quiz_state.get_current_question_data()
        if not question_data:
            error_msg_text = "Ошибка получения данных вопроса."
            logger.error(f"_send_next_question: {error_msg_text} Индекс: {quiz_state.current_question_index}, чат: {chat_id}. Завершение.")
            await self._finalize_quiz_session(context, chat_id, error_occurred=True, error_message=error_msg_text)
            return

        logger.info(f"_send_next_question: Отправка вопроса {quiz_state.current_question_index + 1}/{quiz_state.num_questions_to_ask} в чате {chat_id}.")

        is_last_q_in_this_session = (quiz_state.current_question_index == quiz_state.num_questions_to_ask - 1)
        q_num_display = quiz_state.current_question_index + 1
        title_prefix_for_poll_unescaped: str
        if quiz_state.quiz_type == "single": title_prefix_for_poll_unescaped = "Вопрос"
        elif quiz_state.quiz_type == "daily": title_prefix_for_poll_unescaped = f"Ежедневный вопрос {q_num_display}/{quiz_state.num_questions_to_ask}"
        else: title_prefix_for_poll_unescaped = f"Вопрос {q_num_display}/{quiz_state.num_questions_to_ask}"

        current_category_name_display_unescaped = question_data.get('current_category_name_for_quiz', question_data.get('original_category'))

        sent_poll_id = await self.quiz_engine.send_quiz_poll(
            context, chat_id, question_data,
            poll_title_prefix=title_prefix_for_poll_unescaped,
            open_period_seconds=quiz_state.open_period_seconds,
            quiz_type=quiz_state.quiz_type,
            is_last_question=is_last_q_in_this_session,
            question_session_index=quiz_state.current_question_index,
            current_category_name=current_category_name_display_unescaped if current_category_name_display_unescaped else None
        )

        if sent_poll_id:
            quiz_state_after_poll_send = self.state.get_active_quiz(chat_id)
            if not quiz_state_after_poll_send or quiz_state_after_poll_send.is_stopping or quiz_state_after_poll_send != quiz_state:
                logger.warning(f"_send_next_question: Викторина для чата {chat_id} изменилась/остановилась во время отправки опроса. Отмена дальнейших действий для этого вызова.")
                return

            quiz_state.active_poll_ids_in_session.add(sent_poll_id)
            quiz_state.latest_poll_id_sent = sent_poll_id
            quiz_state.progression_triggered_for_poll[sent_poll_id] = False

            poll_data_from_bot_state = self.state.get_current_poll_data(sent_poll_id)
            if not poll_data_from_bot_state:
                error_msg_poll_data = "Внутренняя ошибка: потеряны данные опроса при создании (сразу после send_quiz_poll)."
                logger.error(f"_send_next_question: {error_msg_poll_data} Poll ID: {sent_poll_id}, чат: {chat_id}.")
                await self._finalize_quiz_session(context, chat_id, error_occurred=True, error_message=error_msg_poll_data)
                return

            job_name_for_this_poll_end = f"poll_end_chat_{chat_id}_poll_{sent_poll_id}"
            poll_data_from_bot_state["job_poll_end_name"] = job_name_for_this_poll_end

            schedule_job_unique(
                self.application.job_queue,
                job_name=job_name_for_this_poll_end,
                callback=self._handle_poll_end_job,
                when=timedelta(seconds=quiz_state.open_period_seconds + self.app_config.job_grace_period_seconds),
                data={"chat_id": chat_id, "ended_poll_id": sent_poll_id}
            )

            quiz_state.current_question_index += 1
            logger.debug(f"_send_next_question: Индекс вопроса в чате {chat_id} увеличен до {quiz_state.current_question_index}.")
        else:
            error_msg_text_send_poll = "Ошибка отправки опроса через Telegram API (QuizEngine.send_quiz_poll вернул None)."
            logger.error(f"_send_next_question: {error_msg_text_send_poll} Вопрос: {quiz_state.current_question_index}, чат: {chat_id}.")
            await self._finalize_quiz_session(context, chat_id, error_occurred=True, error_message=error_msg_text_send_poll)

        logger.debug(f"ЗАВЕРШЕНИЕ _send_next_question для чата {chat_id} (вопрос {quiz_state.current_question_index-1 if quiz_state else 'N/A'} отправлен).")

    async def _handle_early_answer_for_session(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, answered_poll_id: str):
        logger.info(f"Обработка ответа на опрос {answered_poll_id} в чате {chat_id}.")
        quiz_state = self.state.get_active_quiz(chat_id)

        if not quiz_state or quiz_state.is_stopping:
            logger.debug(f"Ответ на опрос {answered_poll_id} проигнорирован: викторина неактивна или останавливается.")
            return

        if quiz_state.progression_triggered_for_poll.get(answered_poll_id, False):
            logger.debug(f"Ответ на опрос {answered_poll_id}: переход к следующему вопросу уже был инициирован ранее для этого опроса.")
            return

        quiz_state.progression_triggered_for_poll[answered_poll_id] = True

        poll_data_in_state = self.state.get_current_poll_data(answered_poll_id)
        if poll_data_in_state:
            poll_data_in_state["next_q_triggered_by_answer"] = True
            logger.debug(f"Флаг next_q_triggered_by_answer установлен в True для poll_id {answered_poll_id}")
        else:
            logger.warning(f"Не найдены данные для poll_id {answered_poll_id} в self.state.current_polls при попытке установить флаг next_q_triggered_by_answer.")

        logger.info(f"Первый значащий ответ на опрос {answered_poll_id} (чат {chat_id}). Инициируется отправка следующего вопроса / планирование.")

        if quiz_state.current_question_index < quiz_state.num_questions_to_ask:
            if quiz_state.next_question_job_name: 
                jobs = self.application.job_queue.get_jobs_by_name(quiz_state.next_question_job_name)
                for job in jobs: job.schedule_removal()
                logger.debug(f"Отменена предыдущая задача отложенной отправки {quiz_state.next_question_job_name}.")
                quiz_state.next_question_job_name = None

            if quiz_state.quiz_mode == "serial_interval" and quiz_state.interval_seconds is not None and quiz_state.interval_seconds > 0:
                delay_seconds = quiz_state.interval_seconds
                job_name = f"delayed_next_q_after_answer_chat_{chat_id}_qidx_{quiz_state.current_question_index}"
                quiz_state.next_question_job_name = job_name
                schedule_job_unique(
                    self.application.job_queue,
                    job_name=job_name,
                    callback=self._trigger_next_question_job_after_interval,
                    when=timedelta(seconds=delay_seconds),
                    data={"chat_id": chat_id, "expected_q_index_at_trigger": quiz_state.current_question_index}
                )
                logger.info(f"Следующий вопрос (индекс {quiz_state.current_question_index}) будет отправлен через {delay_seconds} сек (режим serial_interval).")
            else: 
                logger.info(f"Режим '{quiz_state.quiz_mode}', немедленная отправка следующего вопроса (индекс {quiz_state.current_question_index}).")
                await self._send_next_question(context, chat_id)
        else:
            logger.info(f"Все вопросы ({quiz_state.num_questions_to_ask}) уже были отправлены. Ответ на {answered_poll_id} не триггерит новые вопросы.")

    async def _trigger_next_question_job_after_interval(self, context: ContextTypes.DEFAULT_TYPE):
        if not context.job or not isinstance(context.job.data, dict): return

        chat_id: Optional[int] = context.job.data.get("chat_id")
        expected_q_idx: Optional[int] = context.job.data.get("expected_q_index_at_trigger")

        if chat_id is None:
            logger.error(f"_trigger_next_question_job_after_interval: chat_id отсутствует. Job: {context.job.name if context.job else 'N/A'}")
            return

        quiz_state = self.state.get_active_quiz(chat_id)
        if not quiz_state or quiz_state.is_stopping:
            logger.info(f"_trigger_next_question_job_after_interval: Викторина для чата {chat_id} неактивна или останавливается. Пропуск.")
            return

        if expected_q_idx is not None and quiz_state.current_question_index != expected_q_idx:
            logger.warning(f"_trigger_next_question_job_after_interval (чат {chat_id}): Ожидаемый индекс вопроса {expected_q_idx} не совпадает с текущим {quiz_state.current_question_index}. Пропуск отправки.")
            return

        if quiz_state.next_question_job_name == (context.job.name if context.job else None):
            quiz_state.next_question_job_name = None 

        logger.info(f"Сработала задача отложенной отправки следующего вопроса для чата {chat_id}. Job: {context.job.name if context.job else 'N/A'}.")
        await self._send_next_question(context, chat_id)

    async def _handle_poll_end_job(self, context: ContextTypes.DEFAULT_TYPE):
        if not context.job or not isinstance(context.job.data, dict):
            logger.error("_handle_poll_end_job: context.job или context.job.data некорректны.")
            return

        job_data: Dict[str, Any] = context.job.data
        chat_id: Optional[int] = job_data.get("chat_id")
        ended_poll_id: Optional[str] = job_data.get("ended_poll_id")

        if chat_id is None or ended_poll_id is None:
            logger.error(f"_handle_poll_end_job: chat_id или ended_poll_id отсутствуют. Data: {job_data}")
            return

        logger.info(f"Сработал таймаут для poll_id {ended_poll_id} в чате {chat_id}. Job: {context.job.name}")

        poll_info_before_removal = self.state.get_current_poll_data(ended_poll_id)
        sent_solution_msg_id = await self.quiz_engine.send_solution_if_available(context, chat_id, ended_poll_id)
        quiz_state = self.state.get_active_quiz(chat_id) 

        if poll_info_before_removal and quiz_state:
            ended_poll_message_id = poll_info_before_removal.get("message_id")
            if ended_poll_message_id:
                quiz_state.poll_and_solution_message_ids.append({
                    "poll_msg_id": ended_poll_message_id,
                    "solution_msg_id": sent_solution_msg_id
                })
                logger.debug(f"Poll msg {ended_poll_message_id} and solution msg {sent_solution_msg_id} for poll {ended_poll_id} added to delayed delete list for chat {chat_id}.")
            else:
                logger.warning(f"_handle_poll_end_job: message_id не найден в poll_info_before_removal для poll_id {ended_poll_id}, чат {chat_id}. Не добавлено в список на удаление.")
        elif not poll_info_before_removal:
             logger.warning(f"_handle_poll_end_job: poll_info_before_removal is None для poll_id {ended_poll_id}, чат {chat_id}. Не добавлено в список на удаление.")
        
        self.state.remove_current_poll(ended_poll_id)

        if not quiz_state: 
            logger.info(f"_handle_poll_end_job: Викторина для чата {chat_id} не найдена (возможно, уже завершена).")
            return

        next_q_was_triggered_by_answer = False
        if poll_info_before_removal:
            next_q_was_triggered_by_answer = poll_info_before_removal.get("next_q_triggered_by_answer", False)
        else:
            logger.warning(f"_handle_poll_end_job: Не удалось получить poll_info_before_removal (повторно) для poll_id {ended_poll_id} в чате {chat_id}.")

        if quiz_state.is_stopping:
            logger.info(f"_handle_poll_end_job: Викторина для чата {chat_id} в процессе остановки.")
            quiz_state.active_poll_ids_in_session.discard(ended_poll_id)
            quiz_state.progression_triggered_for_poll.pop(ended_poll_id, None)
            if not quiz_state.active_poll_ids_in_session and quiz_state.is_stopping:
                 logger.info(f"Это был последний активный опрос ({ended_poll_id}) в останавливаемой викторине. Финализация инициируется.")
                 await self._finalize_quiz_session(context, chat_id, was_stopped=True)
            return

        quiz_state.active_poll_ids_in_session.discard(ended_poll_id)
        quiz_state.progression_triggered_for_poll.pop(ended_poll_id, None)

        if quiz_state.current_question_index < quiz_state.num_questions_to_ask:
            if not next_q_was_triggered_by_answer:
                logger.info(f"Таймаут для опроса {ended_poll_id} (чат {chat_id}). Досрочный ответ НЕ инициировал переход. Запуск следующего вопроса.")
                if quiz_state.next_question_job_name: 
                    jobs = self.application.job_queue.get_jobs_by_name(quiz_state.next_question_job_name)
                    for job in jobs: job.schedule_removal()
                    quiz_state.next_question_job_name = None
                await self._send_next_question(context, chat_id)
            else:
                logger.info(f"Таймаут для опроса {ended_poll_id} (чат {chat_id}). Переход к следующему вопросу уже был инициирован досрочным ответом. Дополнительная отправка из _handle_poll_end_job не требуется.")
        elif not quiz_state.active_poll_ids_in_session: 
            logger.info(f"Все вопросы отправлены ({quiz_state.current_question_index}/{quiz_state.num_questions_to_ask}) и все опросы ({ended_poll_id} был последним активным) завершены. Финализация для чата {chat_id}.")
            await self._finalize_quiz_session(context, chat_id)
        else:
            logger.info(f"Опрос {ended_poll_id} завершен. В сессии для чата {chat_id} еще есть активные опросы ({len(quiz_state.active_poll_ids_in_session)}) или не все вопросы отправлены. Ожидание.")

    async def _delayed_delete_messages_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Job-функция для отложенного удаления СЛУЖЕБНЫХ сообщений викторины."""
        if not context.job or not isinstance(context.job.data, dict):
            logger.error("_delayed_delete_messages_job: context.job или context.job.data некорректны.")
            return

        chat_id: Optional[int] = context.job.data.get("chat_id")
        message_ids_to_delete_list: Optional[List[int]] = context.job.data.get("message_ids")

        if chat_id is None or message_ids_to_delete_list is None:
            logger.error(f"_delayed_delete_messages_job: chat_id или message_ids отсутствуют. Data: {context.job.data}")
            return

        # ИЗМЕНЕНИЕ: Проверка настройки автоудаления
        chat_settings = self.data_manager.get_chat_settings(chat_id)
        default_auto_delete_from_config = self.app_config.default_chat_settings.get("auto_delete_bot_messages", True)
        auto_delete_enabled = chat_settings.get("auto_delete_bot_messages", default_auto_delete_from_config)

        if not auto_delete_enabled:
            logger.info(f"Автоудаление СЛУЖЕБНЫХ сообщений отключено для чата {chat_id}. Пропуск удаления {len(message_ids_to_delete_list)} сообщений. Job: {context.job.name if context.job else 'N/A'}")
            return
        # КОНЕЦ ИЗМЕНЕНИЯ

        logger.info(f"Запуск отложенного удаления {len(message_ids_to_delete_list)} СЛУЖЕБНЫХ сообщений в чате {chat_id}. Job: {context.job.name if context.job else 'N/A'}")
        for msg_id in message_ids_to_delete_list:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                logger.info(f"Сообщение {msg_id} (служебное) удалено отложенно из чата {chat_id}.")
            except BadRequest as e_br_del:
                 if "message to delete not found" in str(e_br_del).lower() or \
                    "message can't be deleted" in str(e_br_del).lower():
                     logger.debug(f"Сообщение {msg_id} (служебное) уже удалено или не может быть удалено (отложенно): {e_br_del}")
                 else:
                     logger.warning(f"Ошибка BadRequest при отложенном удалении сообщения {msg_id} (служебное) из чата {chat_id}: {e_br_del}")
            except Exception as e_del_delayed:
                logger.warning(f"Не удалось отложенно удалить сообщение {msg_id} (служебное) из чата {chat_id}: {e_del_delayed}")
        logger.info(f"Отложенное удаление СЛУЖЕБНЫХ сообщений в чате {chat_id} завершено.")

    async def _delayed_delete_poll_solution_messages_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Job-функция для отложенного удаления сообщений ОПРОСОВ и ПОЯСНЕНИЙ."""
        if not context.job or not isinstance(context.job.data, dict):
            logger.error("_delayed_delete_poll_solution_messages_job: context.job или context.job.data некорректны.")
            return

        chat_id: Optional[int] = context.job.data.get("chat_id")
        message_ids_to_delete_list: Optional[List[int]] = context.job.data.get("message_ids")

        if chat_id is None or message_ids_to_delete_list is None:
            logger.error(f"_delayed_delete_poll_solution_messages_job: chat_id или message_ids отсутствуют. Data: {context.job.data}")
            return
        
        # ИЗМЕНЕНИЕ: Проверка настройки автоудаления
        chat_settings = self.data_manager.get_chat_settings(chat_id)
        default_auto_delete_from_config = self.app_config.default_chat_settings.get("auto_delete_bot_messages", True)
        auto_delete_enabled = chat_settings.get("auto_delete_bot_messages", default_auto_delete_from_config)

        if not auto_delete_enabled:
            logger.info(f"Автоудаление сообщений ОПРОСОВ/ПОЯСНЕНИЙ отключено для чата {chat_id}. Пропуск удаления {len(message_ids_to_delete_list)} сообщений. Job: {context.job.name if context.job else 'N/A'}")
            return
        # КОНЕЦ ИЗМЕНЕНИЯ

        logger.info(f"Запуск отложенного удаления {len(message_ids_to_delete_list)} сообщений ОПРОСОВ/ПОЯСНЕНИЙ в чате {chat_id}. Job: {context.job.name if context.job else 'N/A'}")
        for msg_id in message_ids_to_delete_list:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                logger.info(f"Сообщение {msg_id} (опрос/пояснение) удалено отложенно из чата {chat_id}.")
            except BadRequest as e_br_del:
                 if "message to delete not found" in str(e_br_del).lower() or \
                    "message can't be deleted" in str(e_br_del).lower():
                     logger.debug(f"Сообщение {msg_id} (опрос/пояснение) уже удалено или не может быть удалено (отложенно): {e_br_del}")
                 else:
                     logger.warning(f"Ошибка BadRequest при отложенном удалении сообщения {msg_id} (опрос/пояснение) из чата {chat_id}: {e_br_del}")
            except Exception as e_del_delayed:
                logger.warning(f"Не удалось отложенно удалить сообщение {msg_id} (опрос/пояснение) из чата {chat_id}: {e_del_delayed}")
        logger.info(f"Отложенное удаление сообщений ОПРОСОВ/ПОЯСНЕНИЙ в чате {chat_id} завершено.")

    async def _finalize_quiz_session(
        self, context: ContextTypes.DEFAULT_TYPE, chat_id: int,
        was_stopped: bool = False, error_occurred: bool = False, error_message: Optional[str] = None
    ):
        quiz_state = self.state.remove_active_quiz(chat_id)
        if not quiz_state:
            logger.warning(f"Попытка финализировать викторину для чата {chat_id}, но активной сессии QuizState не найдено.")
            return

        escaped_error_message = escape_markdown_v2(error_message) if error_message else None
        logger.info(f"Завершение викторины (тип: {quiz_state.quiz_type}, режим: {quiz_state.quiz_mode}) в чате {chat_id}. Остановлена: {was_stopped}, Ошибка: {error_occurred}, Сообщение: {error_message}")

        job_queue = self.application.job_queue

        if quiz_state.next_question_job_name and job_queue:
            jobs = job_queue.get_jobs_by_name(quiz_state.next_question_job_name)
            for job in jobs: job.schedule_removal()
            quiz_state.next_question_job_name = None

        active_poll_ids_copy = list(quiz_state.active_poll_ids_in_session)
        for poll_id_to_stop in active_poll_ids_copy:
            poll_data = self.state.get_current_poll_data(poll_id_to_stop) 
            if poll_data:
                job_name_to_cancel = poll_data.get("job_poll_end_name")
                if job_name_to_cancel and job_queue:
                    jobs = job_queue.get_jobs_by_name(job_name_to_cancel)
                    for job in jobs: job.schedule_removal()

                message_id_of_poll = poll_data.get("message_id")
                if message_id_of_poll and was_stopped: 
                    try:
                        await context.bot.stop_poll(chat_id=chat_id, message_id=message_id_of_poll)
                        logger.info(f"Активный опрос {poll_id_to_stop} (msg_id: {message_id_of_poll}) остановлен из-за принудительной остановки викторины.")
                    except BadRequest as e_stop_poll:
                        if "poll has already been closed" not in str(e_stop_poll).lower():
                            logger.warning(f"Не удалось остановить опрос {poll_id_to_stop} при финализации (was_stopped): {e_stop_poll}")
                    except Exception as e_gen_stop_poll:
                        logger.error(f"Общая ошибка при остановке опроса {poll_id_to_stop} (was_stopped): {e_gen_stop_poll}")
                    
                    quiz_state.poll_and_solution_message_ids.append({
                        "poll_msg_id": message_id_of_poll,
                        "solution_msg_id": None 
                    })
                    logger.debug(f"Остановленный poll msg {message_id_of_poll} (poll_id: {poll_id_to_stop}) добавлен в список на отложенное удаление.")

                self.state.remove_current_poll(poll_id_to_stop)
            quiz_state.active_poll_ids_in_session.discard(poll_id_to_stop)

        if error_occurred and not quiz_state.scores:
            msg_text_to_send = f"Викторина завершена с ошибкой: {escaped_error_message}" if escaped_error_message else escape_markdown_v2("Викторина завершена из-за непредвиденной ошибки.")
            try: 
                error_msg = await context.bot.send_message(chat_id, msg_text_to_send, parse_mode=ParseMode.MARKDOWN_V2)
                # Добавляем сообщение об ошибке в глобальный список для периодической очистки
                self.state.add_message_for_deletion(chat_id, error_msg.message_id)
            except Exception as e_send_err: logger.error(f"Не удалось отправить сообщение об ошибке финализации: {e_send_err}")
        elif quiz_state.quiz_type != "single" or quiz_state.scores or (error_occurred and quiz_state.scores): 
            title_unescaped_for_formatter = "🏁 Викторина завершена!"
            if was_stopped: title_unescaped_for_formatter = "📝 Викторина остановлена. Результаты:"
            elif error_occurred: title_unescaped_for_formatter = f"⚠️ Викторина завершена с ошибкой{(': ' + error_message) if error_message else ''}. Результаты (если есть):"

            # Собираем данные результатов сессии, включая глобальный счет и иконку ачивки
            scores_for_display: List[Dict[str, Any]] = []
            for uid, data in quiz_state.scores.items():
                # Глобальная статистика пользователя (по всем чатам)
                global_stats = self.score_manager.get_global_user_stats(uid)
                global_total_score_val = global_stats.get('total_score', 0) if global_stats else 0
                achievement_icon_val = self.score_manager.get_rating_icon(global_total_score_val)

                try:
                    user_id_int = int(uid)
                except ValueError:
                    user_id_int = 0

                scores_for_display.append({
                    "user_id": user_id_int,
                    "name": data["name"],
                    "score": data["score"],
                    "correct_count": data.get("correct_count", 0),
                    "global_total_score": global_total_score_val,
                    "achievement_icon": achievement_icon_val,
                })

            scores_for_display.sort(key=lambda x: -x["score"]) 

            results_text_md = self.score_manager.format_scores(
                scores_list=scores_for_display,
                title=title_unescaped_for_formatter,
                is_session_score=True,
                num_questions_in_session=quiz_state.num_questions_to_ask
            )
            try: 
                result_msg = await context.bot.send_message(chat_id, results_text_md, parse_mode=ParseMode.MARKDOWN_V2)
                # Добавляем результаты в глобальный список для периодической очистки
                self.state.add_message_for_deletion(chat_id, result_msg.message_id)
            except Exception as e_send_res: logger.error(f"Не удалось отправить результаты викторины: {e_send_res}")

        if quiz_state.message_ids_to_delete:
            job_name_service = f"delayed_quiz_msg_cleanup_chat_{chat_id}_qs_{int(quiz_state.quiz_start_time.timestamp())}"
            schedule_job_unique(
                job_queue,
                job_name=job_name_service,
                callback=self._delayed_delete_messages_job,
                when=timedelta(seconds=DELAY_BEFORE_SESSION_MESSAGES_DELETION_SECONDS),
                data={"chat_id": chat_id, "message_ids": list(quiz_state.message_ids_to_delete)}
            )
            logger.info(f"Запланировано отложенное удаление {len(quiz_state.message_ids_to_delete)} СЛУЖЕБНЫХ сообщений для чата {chat_id} (job: {job_name_service}, delay: {DELAY_BEFORE_SESSION_MESSAGES_DELETION_SECONDS}s).")
        else:
            logger.debug(f"Нет служебных сообщений для отложенного удаления в чате {chat_id}.")

        if quiz_state.poll_and_solution_message_ids:
            all_poll_solution_msg_ids_flat: List[int] = []
            for pair in quiz_state.poll_and_solution_message_ids:
                if pair.get("poll_msg_id"):
                    all_poll_solution_msg_ids_flat.append(pair["poll_msg_id"])
                if pair.get("solution_msg_id"):
                    all_poll_solution_msg_ids_flat.append(pair["solution_msg_id"])

            if all_poll_solution_msg_ids_flat:
                job_name_poll_sol = f"delayed_poll_sol_cleanup_chat_{chat_id}_qs_{int(quiz_state.quiz_start_time.timestamp())}"
                schedule_job_unique(
                    job_queue,
                    job_name=job_name_poll_sol,
                    callback=self._delayed_delete_poll_solution_messages_job,
                    when=timedelta(seconds=DELAY_BEFORE_POLL_SOLUTION_DELETION_SECONDS),
                    data={"chat_id": chat_id, "message_ids": all_poll_solution_msg_ids_flat}
                )
                logger.info(f"Запланировано отложенное удаление {len(all_poll_solution_msg_ids_flat)} сообщений ОПРОСОВ/ПОЯСНЕНИЙ для чата {chat_id} (job: {job_name_poll_sol}, delay: {DELAY_BEFORE_POLL_SOLUTION_DELETION_SECONDS}s).")
        else:
            logger.debug(f"Нет сообщений опросов/пояснений для отложенного удаления в чате {chat_id}.")

        logger.info(f"Викторина в чате {chat_id} полностью финализирована (основная часть). Отложенные задачи могут выполняться.")

    async def quiz_command_entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        logger.debug(f"quiz_command_entry: ПОЛУЧЕНА КОМАНДА /quiz. Update ID: {update.update_id}")
        if not update.message or not update.effective_chat or not update.effective_user:
            logger.debug("quiz_command_entry: update.message, effective_chat или effective_user отсутствуют.")
            return ConversationHandler.END

        chat_id = update.effective_chat.id
        user = update.effective_user
        logger.info(f"Команда /quiz ({self.app_config.commands.quiz}) вызвана пользователем {user.id} ({user.full_name}) в чате {chat_id}. Аргументы: {context.args}")

        active_quiz = self.state.get_active_quiz(chat_id)
        if active_quiz and not active_quiz.is_stopping:
            logger.info(f"quiz_command_entry: Викторина уже активна в чате {chat_id}. Отправка сообщения.")
            await update.message.reply_text(escape_markdown_v2(f"Викторина уже идет. Остановите ее: `/{self.app_config.commands.stop_quiz}`."), parse_mode=ParseMode.MARKDOWN_V2)
            return ConversationHandler.END

        args = context.args if context.args else []
        parsed_num_q: Optional[int] = None
        parsed_categories_names: List[str] = []
        parsed_announce_flag: Optional[bool] = None
        temp_args_for_parsing = list(args)

        if temp_args_for_parsing and temp_args_for_parsing[-1].lower() == "announce":
            parsed_announce_flag = True
            temp_args_for_parsing.pop()
            logger.debug("quiz_command_entry: Аргумент 'announce' обнаружен.")

        if temp_args_for_parsing and temp_args_for_parsing[0].isdigit():
            try:
                num_val = int(temp_args_for_parsing[0])
                if 1 <= num_val <= self.app_config.max_questions_per_session:
                    parsed_num_q = num_val
                    temp_args_for_parsing.pop(0)
                    logger.debug(f"quiz_command_entry: Количество вопросов из аргументов: {parsed_num_q}")
                else:
                    logger.info(f"quiz_command_entry: Некорректное количество вопросов в аргументах: {num_val}. Чат: {chat_id}")
                    await update.message.reply_text(f"Количество вопросов должно быть от 1 до {escape_markdown_v2(str(self.app_config.max_questions_per_session))}\\.", parse_mode=ParseMode.MARKDOWN_V2)
                    return ConversationHandler.END
            except ValueError:
                logger.debug(f"quiz_command_entry: Первый аргумент '{temp_args_for_parsing[0]}' не является числом (если остался после announce).")

        if temp_args_for_parsing:
            potential_category_name = " ".join(temp_args_for_parsing)
            if self.category_manager.is_valid_category(potential_category_name):
                parsed_categories_names.append(potential_category_name)
                logger.debug(f"quiz_command_entry: Категория из аргументов: '{potential_category_name}'")
            else:
                logger.debug(f"quiz_command_entry: Строка '{potential_category_name}' из аргументов не является валидной категорией.")

        is_quick_launch = parsed_num_q is not None or bool(parsed_categories_names)
        logger.debug(f"quiz_command_entry: Быстрый запуск: {is_quick_launch}. NQ: {parsed_num_q}, Cats: {parsed_categories_names}, AnnounceFlag: {parsed_announce_flag}")

        if is_quick_launch:
            logger.info(f"quiz_command_entry: Быстрый запуск викторины для чата {chat_id}.")
            params_for_quick_launch = self._get_effective_quiz_params(chat_id, parsed_num_q)
            final_announce_for_quick = parsed_announce_flag if parsed_announce_flag is not None else params_for_quick_launch["announce_quiz"]
            final_is_random_cats_for_quick = not bool(parsed_categories_names)
            await self._initiate_quiz_session(
                context, chat_id, user,
                params_for_quick_launch["quiz_type_key"], params_for_quick_launch["quiz_mode"],
                params_for_quick_launch["num_questions"], params_for_quick_launch["open_period_seconds"],
                final_announce_for_quick, params_for_quick_launch["announce_delay_seconds"],
                category_names_for_quiz=parsed_categories_names if parsed_categories_names else None,
                is_random_categories_mode=final_is_random_cats_for_quick,
                interval_seconds=params_for_quick_launch.get("interval_seconds"),
                original_command_message_id=update.message.message_id,
                interactive_start_message_id=None
            )
            return ConversationHandler.END
        elif parsed_announce_flag is True:
            logger.info(f"quiz_command_entry: Быстрый запуск викторины (только флаг announce) для чата {chat_id}.")
            params_for_announce_only = self._get_effective_quiz_params(chat_id)
            await self._initiate_quiz_session(
                context, chat_id, user,
                params_for_announce_only["quiz_type_key"], params_for_announce_only["quiz_mode"],
                params_for_announce_only["num_questions"], params_for_announce_only["open_period_seconds"],
                True, params_for_announce_only["announce_delay_seconds"],
                is_random_categories_mode=True,
                interval_seconds=params_for_announce_only.get("interval_seconds"),
                original_command_message_id=update.message.message_id,
                interactive_start_message_id=None
            )
            return ConversationHandler.END
        else:
            logger.info(f"quiz_command_entry: Переход к интерактивной настройке викторины для чата {chat_id}.")
            params_for_interactive = self._get_effective_quiz_params(chat_id)
            context.chat_data['quiz_cfg_progress'] = {
                'num_questions': params_for_interactive["num_questions"], 'category_name': "random",
                'announce': params_for_interactive["announce_quiz"], 'open_period_seconds': params_for_interactive["open_period_seconds"],
                'announce_delay_seconds': params_for_interactive["announce_delay_seconds"], 'quiz_type_key': params_for_interactive["quiz_type_key"],
                'quiz_mode': params_for_interactive["quiz_mode"], 'interval_seconds': params_for_interactive.get("interval_seconds"),
                'original_command_message_id': update.message.message_id, 'chat_id': chat_id, 'user_id': user.id
            }
            await self._send_quiz_cfg_message(update, context)
            return CFG_QUIZ_OPTIONS

    async def _send_quiz_cfg_message(self, update_or_query: Union[Update, CallbackQuery], context: ContextTypes.DEFAULT_TYPE) -> None:
        cfg = context.chat_data.get('quiz_cfg_progress')
        if not cfg:
            logger.error("_send_quiz_cfg_message: Данные 'quiz_cfg_progress' не найдены.")
            if isinstance(update_or_query, CallbackQuery):
                await update_or_query.answer("Ошибка конфигурации. Пожалуйста, начните заново.", show_alert=True)
                if update_or_query.message:
                    try: await update_or_query.message.delete()
                    except Exception: pass
            return

        num_q_display = cfg['num_questions']
        cat_name_raw = cfg['category_name']
        cat_display_text_escaped = escape_markdown_v2('Случайные' if cat_name_raw == 'random' else cat_name_raw)
        announce_text_raw_escaped = escape_markdown_v2('Вкл' if cfg['announce'] else 'Выкл')
        delay_text_md_escaped = f" \\(задержка {escape_markdown_v2(str(cfg['announce_delay_seconds']))} сек\\)" if cfg['announce'] else ""
        text = (
            f"⚙️ *{escape_markdown_v2('Настройка викторины')}*\n\n"
            f"🔢 {escape_markdown_v2('Количество вопросов:')} `{escape_markdown_v2(str(num_q_display))}`\n"
            f"📚 {escape_markdown_v2('Категория:')} `{cat_display_text_escaped}`\n"
            f"📢 {escape_markdown_v2('Анонс:')} `{announce_text_raw_escaped}`{delay_text_md_escaped}\n\n"
            f"{escape_markdown_v2('Выберите параметр или запустите.')}"
        )
        cat_button_text_plain = ('Случайные' if cat_name_raw == 'random' else cat_name_raw)
        if len(cat_button_text_plain) > 18 : cat_button_text_plain = cat_button_text_plain[:15] + "..."
        announce_button_text_plain = 'Вкл' if cfg['announce'] else 'Выкл'
        kb_layout = [
            [InlineKeyboardButton(f"Вопросы: {num_q_display}", callback_data=CB_QCFG_NUM_MENU), InlineKeyboardButton(f"Категория: {cat_button_text_plain}", callback_data=CB_QCFG_CAT_MENU)],
            [InlineKeyboardButton(f"Анонс: {announce_button_text_plain}", callback_data=CB_QCFG_ANNOUNCE)],
            [InlineKeyboardButton("▶️ Запустить викторину", callback_data=CB_QCFG_START)], [InlineKeyboardButton("❌ Отмена", callback_data=CB_QCFG_CANCEL)]
        ]
        markup = InlineKeyboardMarkup(kb_layout)
        message_to_edit_id = context.chat_data.get('_quiz_cfg_msg_id')
        current_message: Optional[Message] = None
        is_callback = isinstance(update_or_query, CallbackQuery)
        if is_callback and update_or_query.message: current_message = update_or_query.message
        elif isinstance(update_or_query, Update) and update_or_query.message:
            current_message = update_or_query.message
            context.chat_data['_quiz_cmd_msg_id'] = current_message.message_id

        if current_message and message_to_edit_id == current_message.message_id and \
           message_to_edit_id != context.chat_data.get('_quiz_cmd_msg_id'):
            try:
                await current_message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN_V2)
                if is_callback: await update_or_query.answer()
                return
            except BadRequest as e_br:
                if "Message is not modified" not in str(e_br).lower(): logger.warning(f"Ошибка BadRequest при редактировании меню: {e_br}.")
                if is_callback: await update_or_query.answer()
                return
            except Exception as e_edit: logger.error(f"Не удалось обновить меню (edit): {e_edit}")

        if message_to_edit_id and message_to_edit_id != context.chat_data.get('_quiz_cmd_msg_id'):
            target_chat_id_for_delete = cfg.get('chat_id', update_or_query.effective_chat.id if update_or_query.effective_chat else None)
            if target_chat_id_for_delete:
                try:
                    await context.bot.delete_message(target_chat_id_for_delete, message_to_edit_id)
                except Exception: pass
            context.chat_data['_quiz_cfg_msg_id'] = None

        target_chat_id_for_send = cfg.get('chat_id', update_or_query.effective_chat.id if update_or_query.effective_chat else None)
        if not target_chat_id_for_send:
            logger.error("Не удалось определить chat_id для отправки нового меню конфигурации.")
            if is_callback: await update_or_query.answer("Ошибка: не удалось определить чат.", show_alert=True)
            return

        try:
            sent_msg = await context.bot.send_message(target_chat_id_for_send, text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN_V2)
            context.chat_data['_quiz_cfg_msg_id'] = sent_msg.message_id
            if is_callback: await update_or_query.answer()
        except Exception as e_send_new: logger.error(f"Не удалось отправить новое меню конфигурации: {e_send_new}")

    async def handle_quiz_cfg_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        query = update.callback_query
        if not query or not query.data:
            if query: await query.answer("Ошибка: нет данных в колбэке.", show_alert=True)
            return CFG_QUIZ_OPTIONS

        action = query.data
        cfg = context.chat_data.get('quiz_cfg_progress')
        if not cfg:
            await query.answer("Сессия настройки истекла или повреждена. Пожалуйста, начните заново.", show_alert=True)
            if query.message:
                try: await query.message.delete()
                except Exception: pass
            return ConversationHandler.END
        if query.from_user.id != cfg.get('user_id'):
            await query.answer("Вы не можете изменять настройки этой викторины.", show_alert=True)
            return CFG_QUIZ_OPTIONS

        if action == CB_QCFG_START:
            logger.info(f"Запуск викторины из интерактивной настройки для чата {cfg.get('chat_id')}. Пользователь: {query.from_user.id}")
            final_cfg = context.chat_data.pop('quiz_cfg_progress')
            quiz_cfg_msg_id = context.chat_data.pop('_quiz_cfg_msg_id', None)
            context.chat_data.pop('_quiz_cmd_msg_id', None)

            start_message_text_escaped = escape_markdown_v2("🚀 Запускаю викторину...")
            interactive_start_message_id_to_pass: Optional[int] = None

            if quiz_cfg_msg_id and final_cfg.get('chat_id'):
                try:
                    if quiz_cfg_msg_id != final_cfg.get('original_command_message_id'): 
                        await context.bot.delete_message(chat_id=final_cfg['chat_id'], message_id=quiz_cfg_msg_id)
                except Exception as e_del_menu:
                    logger.warning(f"Не удалось удалить сообщение меню конфигурации {quiz_cfg_msg_id}: {e_del_menu}")

            if final_cfg.get('chat_id'):
                try:
                    sent_launch_msg = await context.bot.send_message(final_cfg['chat_id'], start_message_text_escaped, parse_mode=ParseMode.MARKDOWN_V2)
                    interactive_start_message_id_to_pass = sent_launch_msg.message_id
                except Exception as e_send_launch:
                    logger.error(f"Не удалось отправить сообщение 'Запускаю викторину...': {e_send_launch}")

            await query.answer()

            await self._initiate_quiz_session(
                context, final_cfg['chat_id'], query.from_user, final_cfg['quiz_type_key'], final_cfg['quiz_mode'],
                final_cfg['num_questions'], final_cfg['open_period_seconds'], final_cfg['announce'], final_cfg['announce_delay_seconds'],
                category_names_for_quiz=[final_cfg['category_name']] if final_cfg['category_name'] != "random" else None,
                is_random_categories_mode=(final_cfg['category_name'] == "random"),
                interval_seconds=final_cfg.get('interval_seconds'),
                original_command_message_id=final_cfg.get('original_command_message_id'),
                interactive_start_message_id=interactive_start_message_id_to_pass
            )
            return ConversationHandler.END
        
        if action == CB_QCFG_BACK:
            await self._send_quiz_cfg_message(query, context) 
            return CFG_QUIZ_OPTIONS
        elif action == CB_QCFG_NUM_MENU:
            kb_num_options = [[InlineKeyboardButton("1", callback_data=f"{CB_QCFG_NUM_VAL}:1"), InlineKeyboardButton("5", callback_data=f"{CB_QCFG_NUM_VAL}:5"), InlineKeyboardButton("10", callback_data=f"{CB_QCFG_NUM_VAL}:10")],
                              [InlineKeyboardButton("Другое число...", callback_data=f"{CB_QCFG_NUM_VAL}:custom")], [InlineKeyboardButton("⬅️ Назад", callback_data=CB_QCFG_BACK)]]
            if query.message:
                await query.message.edit_text(escape_markdown_v2("Выберите количество вопросов:"), reply_markup=InlineKeyboardMarkup(kb_num_options), parse_mode=ParseMode.MARKDOWN_V2)
            await query.answer()
            return CFG_QUIZ_OPTIONS
        elif action.startswith(CB_QCFG_NUM_VAL):
            val_str = action.split(":", 1)[1]
            if val_str == "custom":
                custom_prompt_text = (f"Введите количество вопросов \\(от 1 до {escape_markdown_v2(str(self.app_config.max_questions_per_session))}\\)\\.\n"
                                      f"Или `/{escape_markdown_v2(self.app_config.commands.cancel)}` для отмены\\.")
                if query.message:
                    await query.message.edit_text(custom_prompt_text, reply_markup=None, parse_mode=ParseMode.MARKDOWN_V2)
                await query.answer()
                return CFG_QUIZ_NUM_QS
            else:
                try:
                    num = int(val_str)
                    if 1 <= num <= self.app_config.max_questions_per_session:
                        cfg['num_questions'] = num
                        effective_params_after_num_change = self._get_effective_quiz_params(cfg['chat_id'], num)
                        cfg['quiz_type_key'] = effective_params_after_num_change['quiz_type_key']
                        cfg['quiz_mode'] = effective_params_after_num_change['quiz_mode']
                    else: await query.answer(f"Некорректное число: {num}. Допустимо от 1 до {self.app_config.max_questions_per_session}.", show_alert=True)
                except ValueError: await query.answer(f"Ошибка значения числа: {val_str}.", show_alert=True)
                await self._send_quiz_cfg_message(query, context) 
                return CFG_QUIZ_OPTIONS
        elif action == CB_QCFG_CAT_MENU:
            available_cats_data = self.category_manager.get_all_category_names(with_question_counts=False)
            available_cats = [cat_info.get('name') for cat_info in available_cats_data if isinstance(cat_info.get('name'), str)]
            cat_kb_list = [[InlineKeyboardButton("🎲 Случайные (из доступных)", callback_data=f"{CB_QCFG_CAT_VAL}:random")]]
            for cat_name in available_cats[:self.app_config.max_interactive_categories_to_show]:
                cat_kb_list.append([InlineKeyboardButton(cat_name, callback_data=f"{CB_QCFG_CAT_VAL}:{cat_name}")])
            if len(available_cats) > self.app_config.max_interactive_categories_to_show:
                cat_kb_list.append([InlineKeyboardButton(f"(еще {len(available_cats) - self.app_config.max_interactive_categories_to_show}...)", callback_data=CB_QCFG_NOOP)])
            cat_kb_list.append([InlineKeyboardButton("⬅️ Назад", callback_data=CB_QCFG_BACK)])
            if query.message:
                await query.edit_message_text(escape_markdown_v2("Выберите категорию:"), reply_markup=InlineKeyboardMarkup(cat_kb_list), parse_mode=ParseMode.MARKDOWN_V2)
            await query.answer()
            return CFG_QUIZ_OPTIONS
        elif action.startswith(CB_QCFG_CAT_VAL):
            selected_category_name = action.split(":", 1)[1]
            cfg['category_name'] = selected_category_name
            await self._send_quiz_cfg_message(query, context) 
            return CFG_QUIZ_OPTIONS
        elif action == CB_QCFG_NOOP:
            await query.answer("Для выбора других категорий, пожалуйста, используйте команду /quiz с указанием имени категории.", show_alert=True)
            return CFG_QUIZ_OPTIONS
        elif action == CB_QCFG_ANNOUNCE:
            cfg['announce'] = not cfg['announce']
            await self._send_quiz_cfg_message(query, context) 
            return CFG_QUIZ_OPTIONS
        elif action == CB_QCFG_CANCEL:
            return await self.cancel_quiz_cfg_command(update, context)

        logger.warning(f"Неизвестное действие в handle_quiz_cfg_callback: {action}")
        await query.answer("Неизвестное действие.", show_alert=True)
        return CFG_QUIZ_OPTIONS

    async def handle_typed_num_questions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        if not update.message or not update.message.text:
            return CFG_QUIZ_NUM_QS
        cfg = context.chat_data.get('quiz_cfg_progress')
        if not cfg:
            await update.message.reply_text(escape_markdown_v2("Сессия настройки истекла. Пожалуйста, начните заново командой /quiz."), parse_mode=ParseMode.MARKDOWN_V2)
            return ConversationHandler.END
        try:
            num = int(update.message.text.strip())
            if 1 <= num <= self.app_config.max_questions_per_session:
                cfg['num_questions'] = num
                effective_params_after_num_change = self._get_effective_quiz_params(cfg['chat_id'], num)
                cfg['quiz_type_key'] = effective_params_after_num_change['quiz_type_key']
                cfg['quiz_mode'] = effective_params_after_num_change['quiz_mode']
                try: await update.message.delete()
                except Exception: pass
                await self._send_quiz_cfg_message(update, context)
                return CFG_QUIZ_OPTIONS
            else:
                await update.message.reply_text(f"Число должно быть от 1 до {escape_markdown_v2(str(self.app_config.max_questions_per_session))}\\. Попробуйте еще раз или `/{escape_markdown_v2(self.app_config.commands.cancel)}` для отмены\\.", parse_mode=ParseMode.MARKDOWN_V2, reply_to_message_id=update.message.message_id)
        except ValueError:
            await update.message.reply_text(f"Это не число\\. Пожалуйста, введите число или `/{escape_markdown_v2(self.app_config.commands.cancel)}` для отмены\\.", parse_mode=ParseMode.MARKDOWN_V2, reply_to_message_id=update.message.message_id)
        return CFG_QUIZ_NUM_QS

    async def cancel_quiz_cfg_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        final_message_text = escape_markdown_v2("Настройка викторины отменена.")
        quiz_cfg_msg_id = context.chat_data.pop('_quiz_cfg_msg_id', None)
        original_cmd_msg_id = context.chat_data.get('_quiz_cmd_msg_id')
        cfg_progress_data = context.chat_data.pop('quiz_cfg_progress', None)

        chat_id_for_ops: Optional[int] = None
        if cfg_progress_data and 'chat_id' in cfg_progress_data: chat_id_for_ops = cfg_progress_data['chat_id']
        elif query and query.message: chat_id_for_ops = query.message.chat_id
        elif update.message and update.message.chat: chat_id_for_ops = update.message.chat.id
        elif update.effective_chat: chat_id_for_ops = update.effective_chat.id

        if query:
            await query.answer()
            if query.message and quiz_cfg_msg_id == query.message.message_id and quiz_cfg_msg_id != original_cmd_msg_id:
                try: await query.edit_message_text(final_message_text, reply_markup=None, parse_mode=ParseMode.MARKDOWN_V2)
                except Exception: pass
            elif chat_id_for_ops :
                 if quiz_cfg_msg_id and quiz_cfg_msg_id != original_cmd_msg_id:
                     try: await context.bot.delete_message(chat_id_for_ops, quiz_cfg_msg_id)
                     except Exception: pass
                 try: await context.bot.send_message(chat_id_for_ops, final_message_text, parse_mode=ParseMode.MARKDOWN_V2)
                 except Exception: pass
        elif update.message: 
            if chat_id_for_ops:
                if quiz_cfg_msg_id and quiz_cfg_msg_id != original_cmd_msg_id: 
                    try: await context.bot.delete_message(chat_id_for_ops, quiz_cfg_msg_id)
                    except Exception: pass
                try: await context.bot.send_message(chat_id_for_ops, final_message_text, parse_mode=ParseMode.MARKDOWN_V2, reply_to_message_id=update.message.message_id)
                except Exception: pass
            elif update.effective_chat:
                try: await update.effective_chat.send_message(final_message_text, parse_mode=ParseMode.MARKDOWN_V2)
                except Exception: pass

        context.chat_data.clear()
        return ConversationHandler.END

    async def stop_quiz_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat or not update.effective_user or not update.message:
            return
        chat_id = update.effective_chat.id
        user_who_stopped = update.effective_user
        logger.info(f"Команда /{self.app_config.commands.stop_quiz} вызвана пользователем {user_who_stopped.id} ({user_who_stopped.full_name}) в чате {chat_id}.")
        quiz_state = self.state.get_active_quiz(chat_id)
        if not quiz_state:
            await update.message.reply_text(escape_markdown_v2("Нет активной викторины для остановки."), parse_mode=ParseMode.MARKDOWN_V2)
            return
        if quiz_state.is_stopping:
            await update.message.reply_text(escape_markdown_v2("Викторина уже в процессе остановки."), parse_mode=ParseMode.MARKDOWN_V2)
            return
        can_stop = await is_user_admin_in_update(update, context)
        if not can_stop and quiz_state.created_by_user_id == user_who_stopped.id and quiz_state.quiz_type != "daily":
            can_stop = True
        if not can_stop:
            await update.message.reply_text(escape_markdown_v2("Только администраторы чата или инициатор (кроме ежедневной викторины) могут остановить текущую викторину."), parse_mode=ParseMode.MARKDOWN_V2)
            return

        quiz_state.is_stopping = True
        stop_confirm_msg = await update.message.reply_text(f"Викторина остановлена пользователем {escape_markdown_v2(user_who_stopped.first_name)}\\. Подведение итогов\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)
        quiz_state.message_ids_to_delete.add(stop_confirm_msg.message_id) 

        await self._finalize_quiz_session(context, chat_id, was_stopped=True)

    def get_handlers(self) -> list:
        cancel_handler_for_conv = CommandHandler(self.app_config.commands.cancel, self.cancel_quiz_cfg_command)
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler(self.app_config.commands.quiz, self.quiz_command_entry)],
            states={
                CFG_QUIZ_OPTIONS: [CallbackQueryHandler(self.handle_quiz_cfg_callback, pattern=f"^{CB_QCFG_}")],
                CFG_QUIZ_NUM_QS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_typed_num_questions)],
            },
            fallbacks=[cancel_handler_for_conv],
            per_chat=True, per_user=True, name="quiz_interactive_setup_conv", persistent=True, allow_reentry=True
        )
        return [conv_handler, CommandHandler(self.app_config.commands.stop_quiz, self.stop_quiz_command)]

