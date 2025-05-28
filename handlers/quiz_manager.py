#handlers/quiz_manager.py
from __future__ import annotations
import asyncio
import logging
from typing import List, Optional, Union, Dict, Any, TYPE_CHECKING
from datetime import timedelta

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, User as TelegramUser, Message, CallbackQuery
)
from telegram.ext import Application, ContextTypes, CommandHandler, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.constants import ParseMode, ChatType
from telegram.error import BadRequest

from app_config import AppConfig
from state import BotState, QuizState
from data_manager import DataManager
from modules.category_manager import CategoryManager # Убедитесь, что этот путь правильный
from modules.score_manager import ScoreManager # Убедитесь, что этот путь правильный
from modules.quiz_engine import QuizEngine # Убедитесь, что этот путь правильный
from utils import get_current_utc_time, schedule_job_unique, escape_markdown_v2, is_user_admin_in_update

if TYPE_CHECKING:
    pass # Можно добавить импорты для тайп-хинтинга, если они нужны и вызывают циклические зависимости

logger = logging.getLogger(__name__)

# Константы для состояний ConversationHandler
(CFG_QUIZ_OPTIONS, CFG_QUIZ_NUM_QS) = map(str, range(2))

# Константы для callback_data
CB_QCFG_ = "qcfg_"
CB_QCFG_NUM_MENU = f"{CB_QCFG_}num_menu"
CB_QCFG_NUM_VAL = f"{CB_QCFG_}num_val" # qcfg_num_val:1, qcfg_num_val:5, etc.
CB_QCFG_CAT_MENU = f"{CB_QCFG_}cat_menu"
CB_QCFG_CAT_VAL = f"{CB_QCFG_}cat_val" # qcfg_cat_val:CategoryName, qcfg_cat_val:random
CB_QCFG_ANNOUNCE = f"{CB_QCFG_}announce"
CB_QCFG_START = f"{CB_QCFG_}start"
CB_QCFG_CANCEL = f"{CB_QCFG_}cancel"
CB_QCFG_BACK = f"{CB_QCFG_}back_to_main_opts" # Для возврата из подменю

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
        self.quiz_engine = QuizEngine(state, app_config) # QuizEngine тоже должен быть инициализирован

    def _get_effective_quiz_params(self, chat_id: int, num_questions_override: Optional[int] = None) -> Dict[str, Any]:
        chat_s = self.data_manager.get_chat_settings(chat_id)

        num_q: int
        if num_questions_override is not None:
            num_q = num_questions_override
        else:
            num_q = chat_s.get("default_num_questions", self.app_config.default_chat_settings.get("default_num_questions", 10))

        quiz_type_for_params_lookup = "single" if num_q == 1 else chat_s.get("default_quiz_type", "session")
        type_cfg = self.app_config.quiz_types_config.get(quiz_type_for_params_lookup, {})

        default_announce_delay = self.app_config.default_chat_settings.get("default_announce_delay_seconds", 5)

        return {
            "quiz_type_key": quiz_type_for_params_lookup,
            "quiz_mode": type_cfg.get("mode", "single_question" if num_q == 1 else "serial_immediate"),
            "num_questions": num_q,
            "open_period_seconds": chat_s.get("default_open_period_seconds", type_cfg.get("default_open_period_seconds", 30)),
            "announce_quiz": chat_s.get("default_announce_quiz", type_cfg.get("announce", False)),
            "announce_delay_seconds": chat_s.get("default_announce_delay_seconds", type_cfg.get("announce_delay_seconds", default_announce_delay)),
            "interval_seconds": type_cfg.get("default_interval_seconds"), # Может быть None
            "enabled_categories_chat": chat_s.get("enabled_categories"), # Список имен или None
            "disabled_categories_chat": chat_s.get("disabled_categories", []), # Список имен
        }

    async def _initiate_quiz_session(
        self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, initiated_by_user: Optional[TelegramUser],
        quiz_type: str, quiz_mode: str, num_questions: int, open_period_seconds: int,
        announce: bool, announce_delay_seconds: int,
        category_names_for_quiz: Optional[List[str]] = None,
        is_random_categories_mode: bool = False,
        interval_seconds: Optional[int] = None,
        original_command_message_id: Optional[int] = None
    ):
        logger.info(f"Инициация викторины в чате {chat_id}. Тип: {quiz_type}, Режим: {quiz_mode}, NQ: {num_questions}, Announce: {announce} ({announce_delay_seconds}s)")

        active_quiz = self.state.get_active_quiz(chat_id)
        if active_quiz and not active_quiz.is_stopping:
            logger.warning(f"Попытка начать викторину в чате {chat_id}, где уже есть активная.")
            if initiated_by_user: # Только если команда от пользователя, а не от шедулера
                 await context.bot.send_message(chat_id, "Викторина уже идет. Остановите текущую (/stopquiz).", parse_mode=None)
            return

        # Логика подбора вопросов
        cat_mode_for_get_questions = "random_from_pool" # по умолчанию
        if category_names_for_quiz and not is_random_categories_mode: # Если указаны конкретные категории И это не режим "случайные" (случайные из всех)
            cat_mode_for_get_questions = "specific_only"
        elif is_random_categories_mode: # Если явно указан режим случайных категорий (даже если category_names_for_quiz переданы, они игнорируются)
            cat_mode_for_get_questions = "random_from_pool"
        # Если category_names_for_quiz не указаны и is_random_categories_mode=False, то это тоже random_from_pool (согласно чат-настройкам)

        questions_for_session = self.category_manager.get_questions(
            num_questions_needed=num_questions,
            chat_id=chat_id, # Для учета настроек чата (включенные/выключенные категории)
            allowed_specific_categories=category_names_for_quiz if cat_mode_for_get_questions == "specific_only" else None,
            mode=cat_mode_for_get_questions
        )

        actual_num_questions_obtained = len(questions_for_session)
        if actual_num_questions_obtained == 0:
            msg_no_q = "Не удалось подобрать вопросы для викторины. Проверьте настройки категорий или попробуйте позже."
            if initiated_by_user: await context.bot.send_message(chat_id, msg_no_q, parse_mode=None)
            else: logger.warning(f"{msg_no_q} (Чат: {chat_id})")
            return

        if actual_num_questions_obtained < num_questions:
            logger.info(f"Запрошено {num_questions}, доступно {actual_num_questions_obtained}. Викторина будет с {actual_num_questions_obtained} вопросами.")
            num_questions = actual_num_questions_obtained # Обновляем количество вопросов до фактического

        user_id_int: Optional[int] = int(initiated_by_user.id) if initiated_by_user else None

        quiz_state = QuizState(
            chat_id=chat_id, quiz_type=quiz_type, quiz_mode=quiz_mode,
            questions=questions_for_session, # Подобранные вопросы
            num_questions_to_ask=num_questions, # Фактическое количество вопросов
            open_period_seconds=open_period_seconds,
            created_by_user_id=user_id_int,
            original_command_message_id=original_command_message_id,
            interval_seconds=interval_seconds,
            quiz_start_time=get_current_utc_time() # Время фактического начала сессии
        )
        self.state.add_active_quiz(chat_id, quiz_state)

        announce_msg_id: Optional[int] = None
        if announce and announce_delay_seconds > 0:
            announce_text_parts = [f"🔔 Викторина начнется через {announce_delay_seconds} сек\\!"]
            if initiated_by_user:
                announce_text_parts.insert(0, f"{escape_markdown_v2(initiated_by_user.first_name)} запускает викторину\\!")
            try:
                msg = await context.bot.send_message(chat_id, " ".join(announce_text_parts), parse_mode=ParseMode.MARKDOWN_V2)
                announce_msg_id = msg.message_id
                quiz_state.announce_message_id = announce_msg_id
                quiz_state.message_ids_to_delete.add(announce_msg_id) # Добавляем ID анонса для последующего удаления
            except Exception as e_announce:
                logger.error(f"Ошибка отправки анонса викторины в чат {chat_id}: {e_announce}")
            
            await asyncio.sleep(announce_delay_seconds)

            # Перепроверяем состояние после задержки
            current_quiz_state_after_delay = self.state.get_active_quiz(chat_id)
            if not current_quiz_state_after_delay or current_quiz_state_after_delay.is_stopping or current_quiz_state_after_delay != quiz_state:
                logger.info(f"Викторина в чате {chat_id} остановлена/заменена во время задержки анонса.")
                # Если викторина была заменена другой, не удаляем анонс, который относится к "старой" (текущей) quiz_state
                if announce_msg_id and current_quiz_state_after_delay != quiz_state and announce_msg_id in quiz_state.message_ids_to_delete:
                     quiz_state.message_ids_to_delete.remove(announce_msg_id) # Убираем из списка на удаление для ЭТОЙ сессии
                
                # Если эта сессия (quiz_state) была удалена из BotState другой логикой, но мы еще здесь,
                # то нужно убедиться, что мы не продолжим.
                if current_quiz_state_after_delay != quiz_state and self.state.get_active_quiz(chat_id) == quiz_state:
                     self.state.remove_active_quiz(chat_id) # На всякий случай, если она как-то осталась
                return
        elif announce: # Анонс без задержки
             announce_text_parts = ["🏁 Викторина начинается\\!"]
             if initiated_by_user:
                announce_text_parts.insert(0, f"{escape_markdown_v2(initiated_by_user.first_name)} запускает викторину\\!")
             try:
                 msg = await context.bot.send_message(chat_id, " ".join(announce_text_parts), parse_mode=ParseMode.MARKDOWN_V2)
                 quiz_state.announce_message_id = msg.message_id
                 quiz_state.message_ids_to_delete.add(msg.message_id)
             except Exception as e_announce_now: logger.error(f"Ошибка немедленного анонса: {e_announce_now}")

        # Запуск отправки первого вопроса
        await self._send_next_question(context, chat_id)

    async def _send_next_question(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        quiz_state = self.state.get_active_quiz(chat_id)
        if not quiz_state or quiz_state.is_stopping:
            # Если викторина останавливается, финализация должна быть вызвана из stop_quiz или другого места
            return

        if quiz_state.current_question_index >= quiz_state.num_questions_to_ask:
            logger.info(f"Все {quiz_state.num_questions_to_ask} вопросов отправлены в {chat_id}. Ожидание завершения последнего или финализация.")
            # Финализация произойдет по таймауту последнего опроса или раннему ответу
            return

        question_data = quiz_state.get_current_question_data()
        if not question_data:
            logger.error(f"Нет данных для вопроса {quiz_state.current_question_index} в {chat_id}. Завершение викторины.")
            await self._finalize_quiz_session(context, chat_id, error_occurred=True, error_message="Ошибка получения данных вопроса.")
            return

        is_last = (quiz_state.current_question_index == quiz_state.num_questions_to_ask - 1)

        q_num_display = quiz_state.current_question_index + 1
        title_prefix = f"Вопрос {q_num_display}/{quiz_state.num_questions_to_ask}"
        if quiz_state.quiz_type == "single": title_prefix = "Вопрос"
        elif quiz_state.quiz_type == "daily": title_prefix = f"Ежедневный вопрос {q_num_display}/{quiz_state.num_questions_to_ask}"
        # Добавить другие типы по необходимости

        current_cat_name = question_data.get('current_category_name_for_quiz', question_data.get('original_category', 'Без категории'))

        poll_id_str = await self.quiz_engine.send_quiz_poll(
            context, chat_id, question_data, title_prefix, quiz_state.open_period_seconds,
            quiz_state.quiz_type, is_last, quiz_state.current_question_index, current_cat_name
        )

        if poll_id_str:
            quiz_state.current_poll_id = poll_id_str
            poll_data_from_state = self.state.get_current_poll_data(poll_id_str) # Получаем данные, которые сохранил QuizEngine
            if poll_data_from_state:
                quiz_state.current_poll_message_id = poll_data_from_state.get("message_id")
                quiz_state.question_start_time = get_current_utc_time() # Время отправки этого вопроса
                # Имя задачи для таймаута этого опроса
                poll_data_from_state["job_poll_end_name"] = f"poll_end_chat_{chat_id}_poll_{poll_id_str}"
                quiz_state.current_poll_end_job_name = poll_data_from_state["job_poll_end_name"]
            else:
                logger.error(f"Данные для poll_id {poll_id_str} не найдены в BotState сразу после создания QuizEngine'ом.")
                # Это критическая ситуация, возможно, стоит прервать викторину
                await self._finalize_quiz_session(context, chat_id, error_occurred=True, error_message="Внутренняя ошибка: потеря данных опроса.")
                return


            # Планируем задачу для обработки окончания времени опроса
            await schedule_job_unique(
                self.application.job_queue, quiz_state.current_poll_end_job_name, self._handle_poll_end_job,
                timedelta(seconds=quiz_state.open_period_seconds + self.app_config.job_grace_period_seconds), # + небольшой буфер
                data={"chat_id": chat_id, "ended_poll_id": poll_id_str}
            )
            quiz_state.current_question_index += 1 # Переходим к следующему вопросу для следующего вызова
        else:
            logger.error(f"Не удалось отправить опрос для вопроса {quiz_state.current_question_index} в {chat_id}.")
            await self._finalize_quiz_session(context, chat_id, error_occurred=True, error_message="Ошибка отправки опроса Telegram.")

    async def _handle_poll_end_job(self, context: ContextTypes.DEFAULT_TYPE):
        job_data = context.job.data # type: ignore
        chat_id: int = job_data["chat_id"]
        ended_poll_id: str = job_data["ended_poll_id"]
        logger.info(f"Сработал таймаут для poll_id {ended_poll_id} в чате {chat_id}.")

        poll_info = self.state.get_current_poll_data(ended_poll_id) # Получаем данные опроса (включая message_id)

        if not poll_info:
            logger.warning(f"_handle_poll_end_job: Информация для poll_id {ended_poll_id} не найдена в BotState. Возможно, уже обработан или удален.")
            # Проверяем, не ожидает ли активная викторина этот опрос
            active_q = self.state.get_active_quiz(chat_id)
            if active_q and active_q.current_poll_id == ended_poll_id:
                logger.error(f"Активная сессия в чате {chat_id} ожидала poll_id {ended_poll_id}, но он не найден в BotState. Завершение сессии.")
                await self._finalize_quiz_session(context, chat_id, error_occurred=True, error_message="Внутренняя ошибка: потеряны данные опроса при таймауте.")
            return

        # Если опрос уже был обработан (например, ранним ответом в serial_immediate режиме)
        if poll_info.get("processed_by_early_answer", False):
            logger.info(f"Опрос {ended_poll_id} уже был обработан (например, ранним ответом). Пропуск стандартной обработки по таймауту.")
            self.state.remove_current_poll(ended_poll_id) # Очищаем данные опроса из BotState
            return

        # Отправляем решение, если оно еще не было отправлено
        await self.quiz_engine.send_solution_if_available(context, chat_id, ended_poll_id)
        
        # Удаляем данные опроса из BotState после обработки
        self.state.remove_current_poll(ended_poll_id)

        quiz_state = self.state.get_active_quiz(chat_id)
        if not quiz_state or quiz_state.is_stopping:
            if quiz_state and quiz_state.is_stopping: # Если викторина была остановлена, финализируем
                await self._finalize_quiz_session(context, chat_id, was_stopped=True)
            # Если quiz_state нет, значит финализация уже произошла или это "блуждающий" job
            return

        # Дополнительная проверка, что это таймаут для текущего опроса этой сессии, а не старого
        # (на случай, если что-то пошло не так с отменой предыдущих jobs)
        # Однако, ended_poll_id должен быть уникальным, так что эта проверка может быть избыточной,
        # если poll_id генерируются уникально. Но poll_info.get("open_timestamp") полезен.
        if quiz_state.quiz_start_time.timestamp() > poll_info.get("open_timestamp", 0) and quiz_state.current_poll_id != ended_poll_id:
             logger.warning(f"Таймаут для старого опроса {ended_poll_id} (открыт {poll_info.get('open_timestamp')}), текущий опрос сессии: {quiz_state.current_poll_id}. Игнорируется.")
             return


        is_last_q_in_series = poll_info.get("is_last_question_in_series", False) # Флаг из QuizEngine

        if is_last_q_in_series:
            logger.info(f"Это был последний вопрос ({ended_poll_id}) в серии. Финализация викторины для чата {chat_id}.")
            await self._finalize_quiz_session(context, chat_id)
        elif quiz_state.quiz_mode == "serial_immediate":
            logger.info(f"Режим 'serial_immediate', отправка следующего вопроса в чате {chat_id} после таймаута {ended_poll_id}.")
            await self._send_next_question(context, chat_id)
        elif quiz_state.quiz_mode == "serial_interval":
            logger.info(f"Режим 'serial_interval', планирование следующего вопроса в чате {chat_id} после таймаута {ended_poll_id}.")
            if not quiz_state.next_question_job_name: # Если еще не запланировано (например, ранним ответом)
                await self._schedule_next_question_for_interval(context, chat_id)
        elif quiz_state.quiz_mode == "single_question":
            logger.info(f"Режим 'single_question', финализация викторины для чата {chat_id} после таймаута {ended_poll_id}.")
            await self._finalize_quiz_session(context, chat_id)
        # Другие режимы, если будут

    async def _schedule_next_question_for_interval(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        quiz_state = self.state.get_active_quiz(chat_id)
        if not quiz_state or quiz_state.is_stopping or quiz_state.quiz_mode != "serial_interval" or \
           quiz_state.current_question_index >= quiz_state.num_questions_to_ask or not quiz_state.interval_seconds:
            # Условия, при которых не нужно планировать следующий вопрос
            return

        job_name = f"next_q_interval_chat_{chat_id}_q_idx_{quiz_state.current_question_index}"
        quiz_state.next_question_job_name = job_name # Сохраняем имя задачи для возможной отмены

        await schedule_job_unique(
            self.application.job_queue, job_name, self._trigger_next_question_for_interval,
            timedelta(seconds=quiz_state.interval_seconds), data={"chat_id": chat_id}
        )
        logger.info(f"Запланирован следующий вопрос ({quiz_state.current_question_index + 1}/{quiz_state.num_questions_to_ask}) для режима 'serial_interval' в чате {chat_id} через {quiz_state.interval_seconds} сек. Job: {job_name}")

    async def _trigger_next_question_for_interval(self, context: ContextTypes.DEFAULT_TYPE):
        job_data = context.job.data # type: ignore
        chat_id: int = job_data["chat_id"]
        logger.info(f"Сработала задача _trigger_next_question_for_interval для чата {chat_id}. Job: {context.job.name}") # type: ignore

        quiz_state = self.state.get_active_quiz(chat_id)
        if not quiz_state or quiz_state.is_stopping or quiz_state.quiz_mode != "serial_interval":
            return

        # Сбрасываем имя задачи, так как она выполнилась
        if quiz_state.next_question_job_name == context.job.name: # type: ignore
            quiz_state.next_question_job_name = None

        await self._send_next_question(context, chat_id)


    async def _finalize_quiz_session(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int,
                                     was_stopped: bool = False, error_occurred: bool = False, error_message: Optional[str] = None):
        quiz_state = self.state.remove_active_quiz(chat_id) # Удаляем сессию из активных
        if not quiz_state:
            logger.warning(f"Попытка финализировать викторину для чата {chat_id}, но активной сессии QuizState не найдено.")
            return

        logger.info(f"Завершение викторины (тип: {quiz_state.quiz_type}, режим: {quiz_state.quiz_mode}) в чате {chat_id}. Остановлена: {was_stopped}, Ошибка: {error_occurred}, Сообщение об ошибке: {error_message}")

        # Отменяем запланированные задачи, связанные с этой сессией
        if quiz_state.next_question_job_name:
            jobs = self.application.job_queue.get_jobs_by_name(quiz_state.next_question_job_name)
            for job in jobs: job.schedule_removal()
            logger.debug(f"Отменена задача следующего вопроса (интервал): {quiz_state.next_question_job_name}")

        if quiz_state.current_poll_end_job_name: # Если был активный опрос, отменяем его таймаут
            jobs = self.application.job_queue.get_jobs_by_name(quiz_state.current_poll_end_job_name)
            for job in jobs: job.schedule_removal()
            logger.debug(f"Отменена задача таймаута текущего опроса: {quiz_state.current_poll_end_job_name}")

        # Если викторина была остановлена и есть активный опрос, пытаемся его закрыть
        if was_stopped and quiz_state.current_poll_id and quiz_state.current_poll_message_id:
            try:
                await context.bot.stop_poll(chat_id=chat_id, message_id=quiz_state.current_poll_message_id)
                self.state.remove_current_poll(quiz_state.current_poll_id) # Убираем его из BotState
                logger.info(f"Активный опрос {quiz_state.current_poll_id} (msg_id: {quiz_state.current_poll_message_id}) остановлен.")
            except BadRequest as e_stop_poll:
                if "poll_has_already_been_closed" not in str(e_stop_poll).lower():
                    logger.warning(f"Не удалось остановить опрос {quiz_state.current_poll_id} при финализации: {e_stop_poll}")
            except Exception as e_gen_stop_poll:
                 logger.error(f"Общая ошибка при остановке опроса {quiz_state.current_poll_id}: {e_gen_stop_poll}")

        # Отправка результатов или сообщения об ошибке
        if error_occurred and not quiz_state.scores: # Если ошибка и нет очков (например, ошибка до первого вопроса)
            msg_text = f"Викторина завершена с ошибкой: {error_message}" if error_message else "Викторина завершена из-за непредвиденной ошибки."
            try: await context.bot.send_message(chat_id, msg_text, parse_mode=None)
            except Exception as e_send_err: logger.error(f"Не удалось отправить сообщение об ошибке финализации: {e_send_err}")
        elif quiz_state.quiz_type != "single" or quiz_state.scores or (error_occurred and quiz_state.scores):
            # Показываем результаты для сессий (не "single"), или если есть очки, или если была ошибка, но очки уже есть
            title = "🏁 Викторина завершена!"
            if was_stopped: title = "📝 Викторина остановлена. Результаты:"
            elif error_occurred: title = "⚠️ Викторина завершена с ошибкой. Результаты (если есть):"

            scores_for_display: List[Dict[str, Any]] = []
            for user_id_str, data in quiz_state.scores.items(): # user_id_str - строка из ключей словаря
                scores_for_display.append({"user_id": int(user_id_str), "name": data["name"], "score": data["score"]})
            scores_for_display.sort(key=lambda x: -x["score"]) # Сортировка по убыванию очков

            results_text = self.score_manager.format_scores(
                scores_list=scores_for_display, title=title,
                is_session_score=True, num_questions_in_session=quiz_state.num_questions_to_ask
            )
            try: await context.bot.send_message(chat_id, results_text, parse_mode=ParseMode.MARKDOWN_V2)
            except Exception as e_send_res: logger.error(f"Не удалось отправить результаты викторины: {e_send_res}")
        
        # Удаление сообщений, помеченных для удаления (анонсы, возможно, старые меню)
        for msg_id in quiz_state.message_ids_to_delete:
            try: await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception as e_del_msg: logger.debug(f"Не удалось удалить сообщение {msg_id} при финализации: {e_del_msg}")

        logger.info(f"Викторина в чате {chat_id} полностью финализирована.")


    async def _handle_early_answer_for_session(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, answered_poll_id: str):
        logger.info(f"Обработка раннего ответа на опрос {answered_poll_id} в чате {chat_id} (режим 'serial_immediate').")
        quiz_state = self.state.get_active_quiz(chat_id)
        if not quiz_state or quiz_state.is_stopping or quiz_state.quiz_mode != "serial_immediate" or quiz_state.current_poll_id != answered_poll_id:
            logger.debug(f"Ранний ответ для опроса {answered_poll_id} проигнорирован (не та сессия / не тот режим / не тот опрос / сессия останавливается).")
            return

        # Отменяем задачу таймаута для текущего опроса, так как ответ получен
        if quiz_state.current_poll_end_job_name:
            jobs = self.application.job_queue.get_jobs_by_name(quiz_state.current_poll_end_job_name)
            for job in jobs: job.schedule_removal()
            logger.info(f"Отменена задача таймаута {quiz_state.current_poll_end_job_name} из-за раннего ответа на {answered_poll_id}.")
            quiz_state.current_poll_end_job_name = None # Сбрасываем имя задачи

        # Отправляем решение (если еще не отправлено)
        await self.quiz_engine.send_solution_if_available(context, chat_id, answered_poll_id)
        # Данные об опросе (answered_poll_id) будут удалены из BotState в send_solution_if_available или после него
        # self.state.remove_current_poll(answered_poll_id) - убедиться, что это делается в QuizEngine или здесь

        poll_info = self.state.get_current_poll_data(answered_poll_id) # Может быть уже None, если QuizEngine удалил
        
        # Проверяем, был ли это последний вопрос
        if poll_info and poll_info.get("is_last_question_in_series", False):
            logger.info(f"Ранний ответ на последний вопрос ({answered_poll_id}). Финализация викторины.")
            self.state.remove_current_poll(answered_poll_id) # Очищаем, если еще не очищено
            await self._finalize_quiz_session(context, chat_id)
        elif not poll_info and quiz_state.current_question_index >= quiz_state.num_questions_to_ask: # Если poll_info уже удален, но это был последний по индексу
             logger.info(f"Ранний ответ на последний вопрос (индекс {quiz_state.current_question_index-1}), poll_info уже удален. Финализация викторины.")
             await self._finalize_quiz_session(context, chat_id)
        else:
            if poll_info: self.state.remove_current_poll(answered_poll_id) # Очищаем, если еще не очищено
            logger.info(f"Отправка следующего вопроса после раннего ответа на {answered_poll_id} в чате {chat_id}.")
            await self._send_next_question(context, chat_id)

    # --- Методы для ConversationHandler (настройка викторины) ---
    async def quiz_command_entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        if not update.message or not update.effective_chat or not update.effective_user:
            return ConversationHandler.END

        chat_id = update.effective_chat.id
        user = update.effective_user

        active_quiz = self.state.get_active_quiz(chat_id)
        if active_quiz and not active_quiz.is_stopping:
            await update.message.reply_text("Викторина уже идет. Остановите ее: /stopquiz.", parse_mode=None)
            return ConversationHandler.END

        args = context.args if context.args else []
        parsed_num_q: Optional[int] = None
        parsed_categories: List[str] = [] # Список имен категорий из аргументов
        parsed_announce_flag: Optional[bool] = None

        # Простая логика парсинга аргументов: [число_вопросов] [категория1] [категория2] ... [announce]
        temp_args = list(args)
        if temp_args and temp_args[-1].lower() == "announce":
            parsed_announce_flag = True
            temp_args.pop()
        
        if temp_args and temp_args[0].isdigit():
            try:
                num_val = int(temp_args[0])
                if 1 <= num_val <= self.app_config.max_questions_per_session:
                    parsed_num_q = num_val
                    temp_args.pop(0) # Убираем число из аргументов
                else:
                    await update.message.reply_text(f"Количество вопросов должно быть от 1 до {self.app_config.max_questions_per_session}.", parse_mode=None)
                    return ConversationHandler.END # Завершаем, если число некорректно
            except ValueError:
                # Если первый аргумент не число, но не "announce", предполагаем, что это категория
                pass 
        
        # Оставшиеся аргументы - это категории
        if temp_args:
            # Если один аргумент и он является существующей полной категорией
            full_cat_str = " ".join(temp_args)
            if self.category_manager.is_valid_category(full_cat_str):
                parsed_categories.append(full_cat_str)
            else: # Иначе, каждый аргумент - отдельная категория (или попытка)
                parsed_categories.extend(temp_args)

        is_quick_launch = parsed_num_q is not None or bool(parsed_categories)

        if is_quick_launch:
            params = self._get_effective_quiz_params(chat_id, parsed_num_q)
            final_announce = parsed_announce_flag if parsed_announce_flag is not None else params["announce_quiz"]
            
            # Если категории указаны, используем их. Иначе - режим случайных.
            # Если категории указаны, is_random_categories_mode должно быть False.
            # Если категории НЕ указаны, is_random_categories_mode должно быть True.
            await self._initiate_quiz_session(
                context, chat_id, user,
                params["quiz_type_key"], params["quiz_mode"],
                params["num_questions"], # params уже учтет parsed_num_q
                params["open_period_seconds"],
                final_announce,
                params["announce_delay_seconds"],
                category_names_for_quiz=parsed_categories if parsed_categories else None,
                is_random_categories_mode=not bool(parsed_categories), # True, если список parsed_categories пуст
                interval_seconds=params.get("interval_seconds"),
                original_command_message_id=update.message.message_id
            )
            return ConversationHandler.END # Быстрый запуск, диалог не нужен

        # Если только /quiz announce
        if parsed_announce_flag is True and not parsed_num_q and not parsed_categories:
            params = self._get_effective_quiz_params(chat_id) # Берем дефолтные параметры чата
            await self._initiate_quiz_session(
                context, chat_id, user,
                params["quiz_type_key"], params["quiz_mode"],
                params["num_questions"], params["open_period_seconds"],
                True, # Announce = True, так как было указано
                params["announce_delay_seconds"],
                is_random_categories_mode=True, # Случайные категории по умолчанию
                interval_seconds=params.get("interval_seconds"),
                original_command_message_id=update.message.message_id
            )
            return ConversationHandler.END

        # Если нет аргументов для быстрого запуска, переходим к интерактивной настройке
        params_for_interactive = self._get_effective_quiz_params(chat_id)
        context.chat_data['quiz_cfg_progress'] = {
            'num_questions': params_for_interactive["num_questions"],
            'category_name': "random", # По умолчанию "random"
            'announce': params_for_interactive["announce_quiz"],
            # Параметры, которые не меняются в простом меню, но нужны для запуска
            'open_period_seconds': params_for_interactive["open_period_seconds"],
            'announce_delay_seconds': params_for_interactive["announce_delay_seconds"],
            'quiz_type_key': params_for_interactive["quiz_type_key"], # Для определения режима
            'quiz_mode': params_for_interactive["quiz_mode"],
            'interval_seconds': params_for_interactive.get("interval_seconds"),
            'original_command_message_id': update.message.message_id, # Сохраняем для возможного удаления
            'chat_id': chat_id # Сохраняем chat_id на случай, если update.message будет недоступен
        }
        await self._send_quiz_cfg_message(update, context)
        return CFG_QUIZ_OPTIONS

    async def _send_quiz_cfg_message(self, update_or_query: Union[Update, CallbackQuery], context: ContextTypes.DEFAULT_TYPE) -> None:
        cfg = context.chat_data.get('quiz_cfg_progress')
        if not cfg:
            logger.error("Данные 'quiz_cfg_progress' не найдены в chat_data для _send_quiz_cfg_message.")
            # Попытаться ответить пользователю, если это колбэк
            if isinstance(update_or_query, CallbackQuery):
                await update_or_query.answer("Ошибка конфигурации. Пожалуйста, начните заново.", show_alert=True)
            return

        num_q_display = cfg['num_questions']
        cat_display_text = 'Случайные' if cfg['category_name'] == 'random' else cfg['category_name']
        cat_button_text = cat_display_text[:15] + "..." if len(cat_display_text) > 18 else cat_display_text # Для кнопки

        announce_text = 'Вкл' if cfg['announce'] else 'Выкл'
        delay_text = f" (задержка {cfg['announce_delay_seconds']} сек)" if cfg['announce'] else ""

        # Используем \\ для экранирования специальных символов MarkdownV2
        text = (f"⚙️ *Настройка викторины*\n\n"
                f"🔢 Количество вопросов: `{num_q_display}`\n"
                f"📚 Категория: `{escape_markdown_v2(cat_display_text)}`\n"
                f"📢 Анонс: `{announce_text}`{escape_markdown_v2(delay_text)}\n\n"
                f"Выберите параметр или запустите\\.") # ИСПРАВЛЕНО: \\.

        kb_layout = [
            [InlineKeyboardButton(f"Вопросы: {num_q_display}", callback_data=CB_QCFG_NUM_MENU),
             InlineKeyboardButton(f"Категория: {cat_button_text}", callback_data=CB_QCFG_CAT_MENU)], # Имя категории не экранируем для кнопки, т.к. это простой текст кнопки
            [InlineKeyboardButton(f"Анонс: {announce_text}", callback_data=CB_QCFG_ANNOUNCE)],
            [InlineKeyboardButton("▶️ Запустить викторину", callback_data=CB_QCFG_START)],
            [InlineKeyboardButton("❌ Отмена", callback_data=CB_QCFG_CANCEL)]
        ]
        markup = InlineKeyboardMarkup(kb_layout)

        message_to_edit_id = context.chat_data.get('_quiz_cfg_msg_id')
        
        current_message: Optional[Message] = None
        is_callback = isinstance(update_or_query, CallbackQuery)

        if is_callback and update_or_query.message:
            current_message = update_or_query.message
        elif isinstance(update_or_query, Update) and update_or_query.message: # Если это Update от MessageHandler
            current_message = update_or_query.message

        # Пытаемся отредактировать, если ID совпадает
        if current_message and message_to_edit_id == current_message.message_id:
            try:
                await current_message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN_V2)
                if is_callback: await update_or_query.answer()
                return
            except BadRequest as e_br:
                if "Message is not modified" not in str(e_br).lower():
                    logger.error(f"Ошибка редактирования меню конфигурации викторины (BadRequest): {e_br}\nТекст: {text}")
                if is_callback: await update_or_query.answer() # Отвечаем на колбэк, даже если не изменено
                return
            except Exception as e_edit: # Другие ошибки редактирования
                logger.error(f"Не удалось обновить меню конфигурации викторины (edit): {e_edit}\nТекст: {text}")
                if is_callback: await update_or_query.answer("Произошла ошибка при обновлении меню.", show_alert=True)
                # Если редактирование не удалось, не удаляем старое и не отправляем новое, чтобы не спамить
                return

        # Если ID не совпадает или редактирование не удалось, удаляем старое (если было) и отправляем новое
        if message_to_edit_id and (not current_message or message_to_edit_id != current_message.message_id):
             target_chat_id_for_delete = (current_message.chat_id if current_message 
                                         else cfg.get('chat_id', update_or_query.effective_chat.id if update_or_query.effective_chat else None))
             if target_chat_id_for_delete:
                try: 
                    await context.bot.delete_message(target_chat_id_for_delete, message_to_edit_id)
                    logger.debug(f"Старое сообщение меню конфигурации {message_to_edit_id} удалено.")
                except Exception as e_del_old: 
                    logger.debug(f"Не удалось удалить старое сообщение меню конфигурации {message_to_edit_id}: {e_del_old}")
             context.chat_data['_quiz_cfg_msg_id'] = None # Сбрасываем ID, так как старое удалено или неактуально


        target_chat_id_for_send = (current_message.chat_id if current_message 
                                   else cfg.get('chat_id', update_or_query.effective_chat.id if update_or_query.effective_chat else None))
        if not target_chat_id_for_send:
            logger.error("Не удалось определить chat_id для отправки нового меню конфигурации.")
            if is_callback: await update_or_query.answer("Ошибка: не удалось определить чат.", show_alert=True)
            return

        try:
            sent_msg = await context.bot.send_message(target_chat_id_for_send, text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN_V2)
            context.chat_data['_quiz_cfg_msg_id'] = sent_msg.message_id # Сохраняем ID нового сообщения
            if is_callback: await update_or_query.answer()
        except Exception as e_send_new:
            logger.error(f"Не удалось отправить новое меню конфигурации викторины: {e_send_new}\nТекст: {text}")
            if is_callback: await update_or_query.answer("Произошла ошибка при отправке меню.", show_alert=True)


    async def handle_quiz_cfg_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        query = update.callback_query
        if not query or not query.data: return CFG_QUIZ_OPTIONS # На всякий случай

        action = query.data
        cfg = context.chat_data.get('quiz_cfg_progress')

        if not cfg: # Если данные сессии потеряны
            await query.answer("Сессия настройки истекла. Пожалуйста, начните заново командой /quiz.", show_alert=True)
            if query.message:
                try: await query.message.delete() # Удаляем старое сообщение меню, если оно есть
                except Exception as e_del_expired: logger.debug(f"Не удалось удалить сообщение меню (истекшая сессия): {e_del_expired}")
            return ConversationHandler.END

        # Обновляем chat_id в cfg на случай, если он был утерян или это первый колбэк
        if query.message and 'chat_id' not in cfg:
            cfg['chat_id'] = query.message.chat_id


        if action == CB_QCFG_BACK:
            await self._send_quiz_cfg_message(query, context) # query здесь используется для ответа и возможного редактирования
            return CFG_QUIZ_OPTIONS

        elif action == CB_QCFG_NUM_MENU:
            kb_num = [[InlineKeyboardButton("1", callback_data=f"{CB_QCFG_NUM_VAL}:1"),
                       InlineKeyboardButton("5", callback_data=f"{CB_QCFG_NUM_VAL}:5"),
                       InlineKeyboardButton("10", callback_data=f"{CB_QCFG_NUM_VAL}:10")],
                      [InlineKeyboardButton("Другое число...", callback_data=f"{CB_QCFG_NUM_VAL}:custom")],
                      [InlineKeyboardButton("⬅️ Назад", callback_data=CB_QCFG_BACK)]]
            try:
                await query.edit_message_text("Выберите количество вопросов:", reply_markup=InlineKeyboardMarkup(kb_num), parse_mode=None)
                await query.answer()
            except Exception as e_edit_num_menu:
                logger.error(f"Ошибка при показе меню выбора числа вопросов: {e_edit_num_menu}")
                await query.answer("Ошибка отображения меню.", show_alert=True)
            return CFG_QUIZ_OPTIONS

        elif action.startswith(CB_QCFG_NUM_VAL):
            val_str = action.split(":", 1)[1]
            if val_str == "custom":
                try:
                    # Используем \\ для экранирования MarkdownV2 символов
                    await query.edit_message_text(
                        f"Введите количество вопросов \\(от 1 до {self.app_config.max_questions_per_session}\\)\\.\n"
                        f"Или /cancel для отмены\\.", 
                        reply_markup=None, 
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
                    await query.answer()
                except Exception as e_edit_custom_num:
                    logger.error(f"Ошибка при запросе кастомного числа вопросов: {e_edit_custom_num}")
                    await query.answer("Ошибка отображения.", show_alert=True)
                return CFG_QUIZ_NUM_QS # Переходим в состояние ожидания текстового ввода
            else:
                try:
                    num = int(val_str)
                    if 1 <= num <= self.app_config.max_questions_per_session: 
                        cfg['num_questions'] = num
                    else: 
                        await query.answer(f"Некорректное число: {num}. Допустимо от 1 до {self.app_config.max_questions_per_session}.", show_alert=True)
                except ValueError: 
                    await query.answer(f"Ошибка значения числа: {val_str}.", show_alert=True)
                await self._send_quiz_cfg_message(query, context) # Возвращаемся к главному меню настроек
                return CFG_QUIZ_OPTIONS

        elif action == CB_QCFG_CAT_MENU:
            available_cats = self.category_manager.get_all_category_names() # Получаем только имена
            cat_kb_list = [[InlineKeyboardButton("🎲 Случайные", callback_data=f"{CB_QCFG_CAT_VAL}:random")]]
            for cat_name in available_cats[:self.app_config.max_interactive_categories_to_show]: # Ограничиваем для отображения
                # Текст кнопки - простой текст, не Markdown
                cat_kb_list.append([InlineKeyboardButton(cat_name, callback_data=f"{CB_QCFG_CAT_VAL}:{cat_name}")])
            if len(available_cats) > self.app_config.max_interactive_categories_to_show:
                 cat_kb_list.append([InlineKeyboardButton(f"(еще {len(available_cats) - self.app_config.max_interactive_categories_to_show}...)", callback_data="qcfg_noop")]) # noop - ничего не делать
            cat_kb_list.append([InlineKeyboardButton("⬅️ Назад", callback_data=CB_QCFG_BACK)])
            
            try:
                await query.edit_message_text("Выберите категорию:", reply_markup=InlineKeyboardMarkup(cat_kb_list), parse_mode=None)
                await query.answer()
            except Exception as e_edit_cat_menu:
                logger.error(f"Ошибка при показе меню выбора категорий: {e_edit_cat_menu}")
                await query.answer("Ошибка отображения меню.", show_alert=True)
            return CFG_QUIZ_OPTIONS

        elif action.startswith(CB_QCFG_CAT_VAL):
            cfg['category_name'] = action.split(":", 1)[1] # 'random' или имя категории
            await self._send_quiz_cfg_message(query, context)
            return CFG_QUIZ_OPTIONS
        
        elif action == "qcfg_noop": # Нажатие на кнопку "(еще ...)"
            await query.answer() # Просто подтверждаем получение колбэка
            return CFG_QUIZ_OPTIONS


        elif action == CB_QCFG_ANNOUNCE:
            cfg['announce'] = not cfg['announce']
            await self._send_quiz_cfg_message(query, context)
            return CFG_QUIZ_OPTIONS

        elif action == CB_QCFG_START:
            final_cfg = context.chat_data.pop('quiz_cfg_progress') # Удаляем данные сессии
            quiz_cfg_msg_id = context.chat_data.pop('_quiz_cfg_msg_id', None) # Удаляем ID сообщения меню
            
            start_message_text = "🚀 Запускаю викторину..."
            if query.message and quiz_cfg_msg_id == query.message.message_id :
                try: 
                    await query.edit_message_text(start_message_text, reply_markup=None, parse_mode=None)
                except Exception as e_edit_start: 
                    logger.debug(f"Не удалось отредактировать сообщение меню при запуске: {e_edit_start}. Отправлю новое.")
                    try: await context.bot.send_message(final_cfg['chat_id'], start_message_text, parse_mode=None)
                    except Exception as e_send_start: logger.error(f"Не удалось отправить сообщение о запуске: {e_send_start}")
            elif query.message: # Если ID не совпали, но есть query.message (например, юзер нажал старую кнопку)
                 try: 
                    await context.bot.send_message(final_cfg['chat_id'], start_message_text, parse_mode=None)
                    # Можно попытаться удалить query.message, если оно не то, что мы ожидали
                    if quiz_cfg_msg_id != query.message.message_id: await query.message.delete()
                 except Exception as e_fallback_start: logger.error(f"Не удалось отправить/удалить сообщение при запуске (fallback): {e_fallback_start}")
            else: # Если query.message нет (очень редкий случай для колбэка от кнопки)
                 try: await context.bot.send_message(final_cfg['chat_id'], start_message_text, parse_mode=None)
                 except Exception as e_send_start_no_q_msg: logger.error(f"Не удалось отправить сообщение о запуске (нет query.message): {e_send_start_no_q_msg}")

            await query.answer() # Отвечаем на колбэк

            # Определяем параметры для запуска викторины на основе final_cfg
            final_num_q = final_cfg['num_questions']
            # quiz_type_key и quiz_mode берутся из cfg, которые были установлены из _get_effective_quiz_params
            # и могли быть переопределены, если бы логика была сложнее (но здесь они не меняются в меню)
            final_quiz_type_key = final_cfg.get('quiz_type_key', "single" if final_num_q == 1 else "session")
            final_quiz_mode = final_cfg.get('quiz_mode', "single_question" if final_num_q == 1 else "serial_immediate")


            await self._initiate_quiz_session(
                context, final_cfg['chat_id'], query.from_user,
                final_quiz_type_key, final_quiz_mode, final_num_q,
                final_cfg['open_period_seconds'], final_cfg['announce'], final_cfg['announce_delay_seconds'],
                category_names_for_quiz=[final_cfg['category_name']] if final_cfg['category_name'] != "random" else None,
                is_random_categories_mode=(final_cfg['category_name'] == "random"),
                interval_seconds=final_cfg.get('interval_seconds'),
                original_command_message_id=final_cfg.get('original_command_message_id')
            )
            return ConversationHandler.END

        elif action == CB_QCFG_CANCEL:
            # Используем существующий метод отмены
            return await self.cancel_quiz_cfg_command(update, context)

        # Если колбэк не распознан (не должно происходить при правильной настройке)
        await query.answer("Неизвестное действие.", show_alert=True)
        return CFG_QUIZ_OPTIONS


    async def handle_typed_num_questions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        if not update.message or not update.message.text: return CFG_QUIZ_NUM_QS # Остаемся в том же состоянии
        
        cfg = context.chat_data.get('quiz_cfg_progress')
        if not cfg:
            await update.message.reply_text("Сессия настройки истекла. Пожалуйста, начните заново командой /quiz.", parse_mode=None)
            return ConversationHandler.END

        try:
            num = int(update.message.text.strip())
            if 1 <= num <= self.app_config.max_questions_per_session:
                cfg['num_questions'] = num
                try: await update.message.delete() # Удаляем сообщение пользователя с числом
                except Exception as e_del_num: logger.debug(f"Не удалось удалить сообщение с числом вопросов: {e_del_num}")
                
                await self._send_quiz_cfg_message(update, context) # Показываем обновленное главное меню настроек
                return CFG_QUIZ_OPTIONS
            else:
                await update.message.reply_text(
                    f"Число должно быть от 1 до {self.app_config.max_questions_per_session}\\. Попробуйте еще раз или /cancel для отмены\\.",
                    parse_mode=ParseMode.MARKDOWN_V2
                )
        except ValueError:
            await update.message.reply_text("Это не число\\. Пожалуйста, введите число или /cancel для отмены\\.", parse_mode=ParseMode.MARKDOWN_V2)
        
        return CFG_QUIZ_NUM_QS # Остаемся в состоянии ожидания числа, если ввод некорректен

    async def cancel_quiz_cfg_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query # Если отмена пришла от кнопки
        final_message_text = "Настройка викторины отменена."
        
        quiz_cfg_msg_id = context.chat_data.pop('_quiz_cfg_msg_id', None) # Удаляем ID из chat_data
        chat_id_for_ops = context.chat_data.get('quiz_cfg_progress', {}).get('chat_id') # Получаем chat_id из cfg

        if not chat_id_for_ops and query and query.message : chat_id_for_ops = query.message.chat_id
        if not chat_id_for_ops and update.message : chat_id_for_ops = update.message.chat_id


        if query: # Если отмена через кнопку
            await query.answer() # Отвечаем на колбэк
            if query.message and quiz_cfg_msg_id == query.message.message_id:
                # Если это то самое сообщение меню, редактируем его
                try: await query.edit_message_text(final_message_text, reply_markup=None, parse_mode=None)
                except Exception as e_edit_cancel: logger.debug(f"Не удалось отредактировать сообщение меню при отмене: {e_edit_cancel}")
            else:
                # Если это не то сообщение или редактирование не удалось, или ID нет, пытаемся удалить старое и отправить новое
                if quiz_cfg_msg_id and chat_id_for_ops:
                    try: await context.bot.delete_message(chat_id_for_ops, quiz_cfg_msg_id)
                    except Exception as e_del_old_cfg: logger.debug(f"Не удалось удалить старое сообщение конфига при отмене (кнопка): {e_del_old_cfg}")
                if chat_id_for_ops: # Отправляем новое сообщение об отмене, если есть chat_id
                    try: await context.bot.send_message(chat_id_for_ops, final_message_text, parse_mode=None)
                    except Exception as e_send_cancel_btn: logger.error(f"Не удалось отправить финальное сообщение отмены (кнопка): {e_send_cancel_btn}")

        elif update.message: # Если отмена через команду /cancel
            if chat_id_for_ops:
                 await context.bot.send_message(chat_id_for_ops, final_message_text, parse_mode=None)
            else: # Если chat_id неизвестен (маловероятно для команды)
                 await update.message.reply_text(final_message_text, parse_mode=None)

            if quiz_cfg_msg_id and chat_id_for_ops: # Пытаемся удалить сообщение меню, если оно было
                try: await context.bot.delete_message(chat_id_for_ops, quiz_cfg_msg_id)
                except Exception as e_del_cfg_cmd: logger.debug(f"Не удалось удалить сообщение конфига при отмене (команда): {e_del_cfg_cmd}")

        context.chat_data.pop('quiz_cfg_progress', None) # Очищаем данные сессии настройки
        logger.info(f"Диалог настройки викторины отменен (чат: {chat_id_for_ops if chat_id_for_ops else 'N/A'}).")
        return ConversationHandler.END

    # --- Команда для остановки активной викторины ---
    async def stop_quiz_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat or not update.effective_user or not update.message: return
        chat_id = update.effective_chat.id
        user_who_stopped = update.effective_user

        quiz_state = self.state.get_active_quiz(chat_id)
        if not quiz_state or quiz_state.is_stopping:
            await update.message.reply_text("Нет активной викторины для остановки, или она уже останавливается.", parse_mode=None)
            return

        # Проверка прав на остановку
        can_stop = await is_user_admin_in_update(update, context)
        # Инициатор может остановить любую викторину, кроме "daily" (ежедневную может только админ)
        if not can_stop and quiz_state.created_by_user_id == user_who_stopped.id:
            if quiz_state.quiz_type != "daily": 
                can_stop = True
        
        if not can_stop:
            await update.message.reply_text("Только администраторы чата или инициатор (кроме ежедневной викторины) могут остановить текущую викторину.", parse_mode=None)
            return

        logger.info(f"Пользователь {user_who_stopped.full_name} (ID: {user_who_stopped.id}) остановил викторину в чате {chat_id}.")
        quiz_state.is_stopping = True # Устанавливаем флаг, что викторина останавливается
        
        # Используем \\ для экранирования MarkdownV2 символов
        await update.message.reply_text(
            f"Викторина остановлена пользователем {escape_markdown_v2(user_who_stopped.first_name)}\\. Подведение итогов\\.\\.\\.", 
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
        # Финализация сессии (подсчет очков, отправка результатов и т.д.)
        await self._finalize_quiz_session(context, chat_id, was_stopped=True)


    def get_handlers(self) -> list:
        # Общий обработчик отмены для ConversationHandler
        # Обратите внимание, что этот cancel_quiz_cfg_command специфичен для этого диалога.
        # Если нужен более глобальный /cancel, он должен быть в common_handlers и обрабатываться иначе.
        cancel_handler_for_conv = CommandHandler(self.app_config.commands.cancel, self.cancel_quiz_cfg_command)

        conv_handler = ConversationHandler(
            entry_points=[CommandHandler(self.app_config.commands.quiz, self.quiz_command_entry)],
            states={
                CFG_QUIZ_OPTIONS: [CallbackQueryHandler(self.handle_quiz_cfg_callback, pattern=f"^{CB_QCFG_}")],
                CFG_QUIZ_NUM_QS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_typed_num_questions)],
            },
            fallbacks=[cancel_handler_for_conv], # Используем специфичный cancel для этого диалога
            per_chat=True, 
            per_user=True, # Стандартные настройки для большинства диалогов
            per_message=True, # ВАЖНО для CallbackQueryHandler, чтобы избежать PTBUserWarning и для корректной работы
            name="quiz_interactive_setup_conv", # Имя для отладки и управления
            persistent=True, # Сохранять состояние диалога между перезапусками (если PicklePersistence используется)
            allow_reentry=True # Позволяет войти в диалог снова, даже если он уже активен (например, /quiz еще раз)
        )
        return [
            conv_handler,
            CommandHandler(self.app_config.commands.stop_quiz, self.stop_quiz_command)
        ]

