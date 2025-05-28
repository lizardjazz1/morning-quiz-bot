# bot/handlers/quiz_manager.py
import asyncio
import logging
from typing import List, Optional, Union, Dict, Any, Tuple
from datetime import timedelta, datetime, timezone

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    User as TelegramUser,
    Message
)
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    CommandHandler,
    Application # Для доступа к job_queue
)
from telegram.constants import ParseMode, ChatType
from telegram.error import BadRequest

# from ..app_config import AppConfig # Через конструктор
# from ..state import BotState # Через конструктор
# from ..data_manager import DataManager # Через конструктор
# from ..modules.category_manager import CategoryManager # Через конструктор
# from ..modules.score_manager import ScoreManager # Через конструктор
from ..modules.quiz_engine import QuizEngine # Используется этим менеджером

logger = logging.getLogger(__name__)

# Состояния для ConversationHandler при интерактивной настройке /quiz
(
    QUIZ_CFG_SELECTING_OPTIONS,
    QUIZ_CFG_TYPING_NUM_QUESTIONS,
    QUIZ_CFG_SELECTING_CATEGORY, # Можно расширить для мульти-выбора или постраничного
    # ... другие состояния по необходимости
) = map(str, range(3)) # Используем строки для имен состояний

# Префиксы и действия для callback_data в интерактивной настройке
CB_QUIZ_CFG_PREFIX = "qcfg_"
ACTION_SET_NUM_Q_MENU = f"{CB_QUIZ_CFG_PREFIX}num_menu"
ACTION_TYPE_NUM_Q_VALUE = f"{CB_QUIZ_CFG_PREFIX}num_val" # qcfg_num_val:X или qcfg_num_val:custom
ACTION_SET_CATEGORY_MENU = f"{CB_QUIZ_CFG_PREFIX}cat_menu"
ACTION_SELECT_CATEGORY_VALUE = f"{CB_QUIZ_CFG_PREFIX}cat_val" # qcfg_cat_val:category_name или qcfg_cat_val:random
ACTION_TOGGLE_ANNOUNCE = f"{CB_QUIZ_CFG_PREFIX}announce"
ACTION_START_CONFIGURED_QUIZ = f"{CB_QUIZ_CFG_PREFIX}start"
ACTION_CANCEL_CONFIG_QUIZ = f"{CB_QUIZ_CFG_PREFIX}cancel"
ACTION_BACK_TO_MAIN_CONFIG = f"{CB_QUIZ_CFG_PREFIX}main_menu"


class QuizManager:
    def __init__(
        self,
        app_config: 'AppConfig',
        state: 'BotState',
        category_manager: 'CategoryManager',
        score_manager: 'ScoreManager',
        data_manager: 'DataManager',
        application: Application # Для доступа к job_queue
    ):
        self.app_config = app_config
        self.state = state
        self.category_manager = category_manager
        self.score_manager = score_manager
        self.data_manager = data_manager
        self.application = application # Сохраняем application
        self.quiz_engine = QuizEngine(state, app_config) # QuizEngine не нужен DataManager напрямую

    async def _get_effective_quiz_params_for_chat(self, chat_id: int) -> Dict[str, Any]:
        """Возвращает объединенные настройки викторины для чата (чат-специфичные + дефолты)."""
        chat_settings = self.data_manager.get_chat_settings(chat_id) # Уже объединенные с глобальными дефолтами
        
        # Параметры для стандартного запуска викторины (/quiz без аргументов или для сессии)
        # default_quiz_type определяет, будет ли это 'single' или 'session'
        quiz_type_for_defaults = chat_settings.get("default_quiz_type", "session") # 'single' или 'session'
        
        # Берем настройки для этого типа из quiz_types_config
        type_specific_config = self.app_config.quiz_types_config.get(quiz_type_for_defaults, {})

        return {
            "num_questions": chat_settings.get("default_num_questions", type_specific_config.get("default_num_questions", 10)),
            "open_period_seconds": chat_settings.get("default_open_period_seconds", type_specific_config.get("default_open_period_seconds", 60)),
            "quiz_mode": type_specific_config.get("mode", "serial_immediate"), # Из quiz_types_config
            "announce_quiz": chat_settings.get("default_announce_quiz", False),
            "announce_delay_seconds": chat_settings.get("default_announce_delay", self.app_config.default_announce_delay_seconds),
            "enabled_categories": chat_settings.get("enabled_categories"), # Может быть None
            "disabled_categories": chat_settings.get("disabled_categories", []),
            # interval_seconds для сессии обычно не используется, но может быть в type_specific_config
            "interval_seconds": type_specific_config.get("default_interval_seconds")
        }

    async def _initiate_quiz_session(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int, # int
        initiated_by_user: Optional[TelegramUser], # Кто запустил (может быть None для daily)
        quiz_type: str, # "single", "session", "daily" - общий тип викторины
        num_questions: int,
        open_period_seconds: int,
        interval_seconds: Optional[int] = None, # Только для "serial_interval" (daily)
        category_names_for_quiz: Optional[List[str]] = None, # Явно выбранные категории
        is_random_categories_mode: bool = False, # Если true, category_names_for_quiz игнорируются
        announce: bool = False,
        announce_delay_seconds: int = 0
    ) -> None:
        logger.info(
            f"Инициализация викторины в чате {chat_id}. Тип: {quiz_type}, Кол-во: {num_questions}, "
            f"Категории: {category_names_for_quiz if not is_random_categories_mode else 'СЛУЧАЙНЫЕ'}, "
            f"Анонс: {announce} (задержка {announce_delay_seconds}s)"
        )

        if chat_id in self.state.active_quizzes and not self.state.active_quizzes[chat_id].get("is_stopped"):
            # Это должно проверяться до вызова _initiate_quiz_session в командах
            logger.warning(f"Попытка запустить викторину в чате {chat_id}, где уже идет активная.")
            # await context.bot.send_message(chat_id, "Викторина уже идет в этом чате.") # Не отправляем здесь, команда должна это сделать
            return

        chat_config = self.data_manager.get_chat_settings(chat_id)
        chat_enabled_cats = chat_config.get("enabled_categories") # Может быть None
        chat_disabled_cats = chat_config.get("disabled_categories", [])

        questions_for_session: List[Dict[str, Any]]
        category_description_log: str

        if is_random_categories_mode:
            questions_for_session = self.category_manager.get_questions(
                num_questions_needed=num_questions,
                chat_enabled_categories=chat_enabled_cats,
                chat_disabled_categories=chat_disabled_cats,
                mode="random_from_pool"
            )
            category_description_log = "случайные категории (с учетом настроек чата)"
        elif category_names_for_quiz:
            questions_for_session = self.category_manager.get_questions(
                num_questions_needed=num_questions,
                allowed_specific_categories=category_names_for_quiz,
                chat_enabled_categories=chat_enabled_cats, # Учитываем общие разрешения чата
                chat_disabled_categories=chat_disabled_cats,
                mode="specific_only" # или "random_from_pool" если хотим случайные из указанного списка
            )
            category_description_log = f"категории: {', '.join(category_names_for_quiz)}"
        else: # Нет явных категорий и не случайный режим (например, из настроек чата по умолчанию)
            questions_for_session = self.category_manager.get_questions(
                num_questions_needed=num_questions,
                chat_enabled_categories=chat_enabled_cats,
                chat_disabled_categories=chat_disabled_cats,
                mode="random_from_pool" # По умолчанию случайные из доступных чату
            )
            category_description_log = "категории по умолчанию для чата (или все доступные)"


        actual_num_questions = len(questions_for_session)
        if actual_num_questions == 0:
            err_msg = f"Не найдено вопросов для викторины ({category_description_log}). Викторина не будет начата."
            try: await context.bot.send_message(chat_id=chat_id, text=err_msg)
            except Exception as e: logger.error(f"Ошибка отправки сообщения об отсутствии вопросов в чат {chat_id}: {e}")
            return
        
        if actual_num_questions < num_questions:
             logger.warning(f"Найдено только {actual_num_questions} из {num_questions} запрошенных. Викторина будет с этим количеством.")
             num_questions = actual_num_questions


        # Определяем quiz_mode из quiz_types_config
        quiz_type_config = self.app_config.quiz_types_config.get(quiz_type, {})
        quiz_mode = quiz_type_config.get("mode", "single_question" if num_questions == 1 else "serial_immediate")


        intro_message_id: Optional[int] = None
        if announce and announce_delay_seconds > 0:
            announce_text_parts = ["🔔 Викторина начнется"]
            if initiated_by_user:
                announce_text_parts.insert(0, f"{initiated_by_user.first_name} запускает викторину!")
            announce_text_parts.append(f"через {announce_delay_seconds} секунд.")
            announce_text_parts.append(f"Тема: {category_description_log}, вопросов: {num_questions}.")
            try:
                msg = await context.bot.send_message(chat_id, text=" ".join(announce_text_parts))
                intro_message_id = msg.message_id # Это сообщение анонса
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения об анонсе в чат {chat_id}: {e}")
            
            await asyncio.sleep(announce_delay_seconds)
            
            # Проверяем, не была ли викторина остановлена во время ожидания анонса
            if chat_id in self.state.active_quizzes and self.state.active_quizzes[chat_id].get("is_stopped"):
                logger.info(f"Викторина в чате {chat_id} была остановлена во время анонса.")
                if intro_message_id: # Удаляем сообщение об анонсе, если оно было
                    try: await context.bot.delete_message(chat_id, intro_message_id)
                    except: pass
                # Важно! Если викторина остановлена, не нужно регистрировать ее в self.state.active_quizzes снова
                # или нужно очистить предыдущую запись. Лучше, если stop_quiz удаляет из active_quizzes.
                # Текущая логика /stopquiz уже удаляет, так что здесь просто выходим.
                return
            if chat_id not in self.state.active_quizzes: # Если ее остановили и удалили запись
                logger.info(f"Викторина в чате {chat_id} была отменена (запись удалена) во время анонса.")
                return

        # Отправка основного интро-сообщения (если не было анонса или анонс не считается интро)
        # Пока считаем, что анонс заменяет интро, если был. Если нужен отдельный интро после анонса,
        # нужно будет добавить логику.

        # Регистрация активной викторины
        self.state.active_quizzes[chat_id] = {
            "quiz_type": quiz_type,
            "quiz_mode": quiz_mode,
            "questions_data": questions_for_session,
            "current_question_index": 0,
            "num_questions_total": num_questions,
            "open_period_seconds": open_period_seconds,
            "interval_seconds": interval_seconds,
            "session_scores": {},
            "message_id_intro": intro_message_id, # ID сообщения анонса или основного интро
            "initiated_by_user_id": str(initiated_by_user.id) if initiated_by_user else None,
            "current_poll_id": None,
            "next_question_job_name": None,
            "category_description_for_log": category_description_log,
            "is_stopped": False,
            "message_ids_to_delete": [intro_message_id] if intro_message_id else []
        }
        logger.info(f"Запись о викторине '{quiz_type}' создана для чата {chat_id}.")
        
        await self._send_next_question_in_session(context, chat_id)


    async def _send_next_question_in_session(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        active_quiz = self.state.active_quizzes.get(chat_id)
        if not active_quiz or active_quiz.get("is_stopped"):
            logger.info(f"_send_next_question: Нет активной или остановлена викторина для чата {chat_id}.")
            if active_quiz and active_quiz.get("is_stopped"): # Если была остановлена, зачищаем окончательно
                 await self._finalize_quiz_session(context, chat_id, was_stopped=True)
            return

        current_q_idx = active_quiz["current_question_index"]
        total_q = active_quiz["num_questions_total"]

        if current_q_idx >= total_q:
            logger.info(f"Все {total_q} вопросов для викторины в чате {chat_id} отправлены. Ожидание завершения последнего опроса.")
            # Завершение сессии и показ результатов произойдут в _handle_poll_end_job
            # когда последний опрос завершится.
            return

        question_data = active_quiz["questions_data"][current_q_idx]
        is_last_q_in_series = (current_q_idx == total_q - 1)
        
        title_prefix_map = {
            "single": "Вопрос",
            "session": f"Вопрос {current_q_idx + 1}/{total_q}",
            "daily": f"Ежедневный вопрос {current_q_idx + 1}/{total_q}"
        }
        poll_title_prefix = title_prefix_map.get(active_quiz["quiz_type"], "Вопрос")

        # current_category_name извлекается из question_data, если CategoryManager его туда добавил
        current_category = question_data.get('current_category_name', question_data.get('original_category'))

        poll_id_str = await self.quiz_engine.send_quiz_poll(
            context=context,
            chat_id=chat_id,
            question_data=question_data,
            poll_title_prefix=poll_title_prefix,
            open_period_seconds=active_quiz["open_period_seconds"],
            quiz_type=active_quiz["quiz_type"],
            is_last_question=is_last_q_in_series,
            question_session_index=current_q_idx,
            current_category_name=current_category
        )

        if poll_id_str:
            active_quiz["current_poll_id"] = poll_id_str
            active_quiz["current_question_index"] += 1 # Готовимся к следующему вопросу

            # Планируем задачу для обработки конца этого опроса (решение + следующий шаг)
            job_delay_seconds = active_quiz["open_period_seconds"] + self.app_config.job_grace_period_seconds
            job_name = f"poll_end_chat_{chat_id}_poll_{poll_id_str}"
            
            if chat_id in self.state.current_polls and poll_id_str in self.state.current_polls : # Проверка, что опрос был успешно зарегистрирован
                 self.state.current_polls[poll_id_str]["job_poll_end_name"] = job_name
            else: # Опрос не зарегистрирован в current_polls, это проблема
                 logger.error(f"Опрос {poll_id_str} не найден в current_polls после отправки! Невозможно запланировать job для его окончания.")
                 # Можно попытаться остановить сессию здесь, если это критично
                 await self._finalize_quiz_session(context, chat_id, error_occurred=True,
                                                   error_message="Ошибка регистрации опроса.")
                 return


            self.application.job_queue.run_once(
                self._handle_poll_end_job,
                timedelta(seconds=job_delay_seconds),
                data={"chat_id": chat_id, "ended_poll_id": poll_id_str}, # chat_id int
                name=job_name
            )
        else: # Ошибка отправки опроса
            logger.error(f"Не удалось отправить опрос для вопроса {current_q_idx} в чате {chat_id}. Завершение викторины.")
            await self._finalize_quiz_session(context, chat_id, error_occurred=True,
                                               error_message="Ошибка при отправке вопроса.")

    async def _handle_poll_end_job(self, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик завершения опроса (по таймауту). Отправляет решение и решает, что делать дальше."""
        job = context.job
        if not job or not job.data:
            logger.error("_handle_poll_end_job: Данные задачи отсутствуют.")
            return

        chat_id: int = job.data["chat_id"]
        ended_poll_id: str = job.data["ended_poll_id"]

        logger.info(f"Таймаут для poll_id {ended_poll_id} в чате {chat_id}.")

        poll_info = self.state.current_polls.pop(ended_poll_id, None) # Получаем и удаляем
        
        if not poll_info:
            logger.warning(f"_handle_poll_end_job: Информация для poll_id {ended_poll_id} не найдена (возможно, уже обработан или отменен).")
            # Если это была часть активной сессии, нужно проверить состояние сессии.
            # Возможно, сессия была остановлена (/stopquiz), и poll_info уже удален.
            active_quiz_check = self.state.active_quizzes.get(chat_id)
            if active_quiz_check and active_quiz_check.get("current_poll_id") == ended_poll_id:
                # Попытка восстановить логику, если poll_info пропал, но сессия еще ждет этот poll
                logger.warning(f"Сессия в чате {chat_id} все еще ожидала poll {ended_poll_id}, но он не найден в current_polls. Попытка завершить сессию.")
                await self._finalize_quiz_session(context, chat_id, error_occurred=True, error_message="Потерян poll_info.")
            return

        # Отправляем решение, если есть
        await self.quiz_engine.send_solution_if_available(context, chat_id, ended_poll_id)
        
        # Логика для продолжения или завершения сессии
        active_quiz = self.state.active_quizzes.get(chat_id)
        if not active_quiz or active_quiz.get("is_stopped"):
            logger.info(f"Сессия в чате {chat_id} не активна или остановлена после завершения poll {ended_poll_id}.")
            if active_quiz and active_quiz.get("is_stopped"): # Если остановлена, но poll job сработал
                await self._finalize_quiz_session(context, chat_id, was_stopped=True)
            return

        # Если этот опрос не текущий для сессии (например, ответ пришел очень поздно или был /stopquiz)
        if active_quiz.get("current_poll_id") != ended_poll_id and not poll_info.get("processed_by_early_answer"):
             logger.warning(f"Таймаут для старого опроса {ended_poll_id} в чате {chat_id}. Текущий опрос сессии: {active_quiz.get('current_poll_id')}. Ничего не делаем.")
             return


        is_last_q = poll_info.get("is_last_question_in_series", False)
        processed_early = poll_info.get("processed_by_early_answer", False)

        if is_last_q:
            logger.info(f"Последний вопрос ({ended_poll_id}) викторины в чате {chat_id} завершен. Финализация.")
            await self._finalize_quiz_session(context, chat_id)
        elif active_quiz["quiz_mode"] == "serial_immediate":
            if not processed_early: # Если ответ не пришел раньше и не запустил следующий вопрос
                logger.info(f"Опрос {ended_poll_id} (serial_immediate) в чате {chat_id} завершен. Отправка следующего вопроса.")
                await self._send_next_question_in_session(context, chat_id)
            else:
                logger.info(f"Опрос {ended_poll_id} (serial_immediate) в чате {chat_id} уже был обработан ранним ответом. Следующий вопрос (если есть) активен.")
        elif active_quiz["quiz_mode"] == "serial_interval":
            # Для "serial_interval" (например, daily), следующий вопрос запускается по своему таймеру
            # Эта job (_handle_poll_end_job) отвечает только за показ решения.
            # Если это был последний вопрос, то is_last_q обработает завершение.
            # Если не последний, то _trigger_next_question_for_interval_quiz позаботится о следующем.
            logger.info(f"Опрос {ended_poll_id} (serial_interval) в чате {chat_id} завершен. Следующий вопрос по расписанию (если есть).")
            if not is_last_q: # Если не последний, планируем следующий (если еще не запланирован)
                 if not active_quiz.get("next_question_job_name"): # Дополнительная проверка
                      await self._schedule_next_question_for_interval_quiz(context, chat_id)
                 else:
                      logger.debug(f"Следующий вопрос для serial_interval в {chat_id} уже запланирован: {active_quiz.get('next_question_job_name')}")

        elif active_quiz["quiz_mode"] == "single_question": # Одиночный вопрос
            logger.info(f"Одиночный вопрос ({ended_poll_id}) в чате {chat_id} завершен. Финализация.")
            await self._finalize_quiz_session(context, chat_id) # Одиночный вопрос тоже "сессия" из одного


    async def _schedule_next_question_for_interval_quiz(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        active_quiz = self.state.active_quizzes.get(chat_id)
        if not active_quiz or active_quiz.get("is_stopped") or active_quiz["quiz_mode"] != "serial_interval":
            return
        
        if active_quiz["current_question_index"] >= active_quiz["num_questions_total"]:
            # Все вопросы уже отправлены или в процессе, нечего планировать
            return

        interval_seconds = active_quiz.get("interval_seconds")
        if interval_seconds is None or interval_seconds <= 0:
            logger.error(f"Некорректный interval_seconds ({interval_seconds}) для serial_interval викторины в чате {chat_id}.")
            await self._finalize_quiz_session(context, chat_id, error_occurred=True, error_message="Ошибка интервала.")
            return
        
        job_name = f"next_q_interval_chat_{chat_id}_idx_{active_quiz['current_question_index']}"
        
        # Удаляем старую задачу с таким именем, если она есть (маловероятно, но для чистоты)
        current_jobs = self.application.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()
            logger.debug(f"Удалена предыдущая задача {job_name} перед планированием новой.")

        self.application.job_queue.run_once(
            self._trigger_next_question_for_interval_quiz,
            timedelta(seconds=interval_seconds),
            data={"chat_id": chat_id},
            name=job_name
        )
        active_quiz["next_question_job_name"] = job_name
        logger.info(f"Запланирован следующий вопрос ({active_quiz['current_question_index']}) для serial_interval викторины в чате {chat_id} через {interval_seconds} сек. Задача: {job_name}")

    async def _trigger_next_question_for_interval_quiz(self, context: ContextTypes.DEFAULT_TYPE):
        """Вызывается по таймеру для отправки следующего вопроса в serial_interval викторине."""
        job = context.job
        if not job or not job.data:
            logger.error("_trigger_next_question_for_interval_quiz: Данные задачи отсутствуют.")
            return
        chat_id: int = job.data["chat_id"]
        
        active_quiz = self.state.active_quizzes.get(chat_id)
        if not active_quiz or active_quiz.get("is_stopped"):
            logger.info(f"_trigger_next_question_for_interval_quiz: Викторина в чате {chat_id} не активна или остановлена.")
            return
        if active_quiz["quiz_mode"] != "serial_interval":
            logger.warning(f"_trigger_next_question_for_interval_quiz: Викторина в чате {chat_id} не является serial_interval. Имя задачи: {job.name}")
            return
        
        # Сбрасываем имя задачи, так как она выполнилась
        if active_quiz.get("next_question_job_name") == job.name:
            active_quiz["next_question_job_name"] = None

        logger.info(f"Запуск следующего вопроса для serial_interval викторины в чате {chat_id} по задаче {job.name}.")
        await self._send_next_question_in_session(context, chat_id)


    async def _finalize_quiz_session(
            self, context: ContextTypes.DEFAULT_TYPE, chat_id: int,
            was_stopped: bool = False, error_occurred: bool = False, error_message: Optional[str] = None):
        
        active_quiz = self.state.active_quizzes.pop(chat_id, None) # Удаляем из активных
        if not active_quiz:
            logger.warning(f"_finalize_quiz_session: Нет активной викторины для чата {chat_id} для завершения.")
            return

        logger.info(f"Завершение викторины (тип: {active_quiz['quiz_type']}) в чате {chat_id}. Остановлена: {was_stopped}, Ошибка: {error_occurred}")

        # Отмена связанных задач JobQueue
        if job_name := active_quiz.get("next_question_job_name"):
            jobs = self.application.job_queue.get_jobs_by_name(job_name)
            for job in jobs: job.schedule_removal()
            logger.debug(f"Отменена задача {job_name} для чата {chat_id} при завершении викторины.")
        
        # Если был текущий опрос, его job_poll_end_name также нужно отменить,
        # если финализация происходит до его естественного завершения (например, /stopquiz).
        # Однако, если _handle_poll_end_job вызвал финализацию, то poll уже удален из current_polls.
        current_poll_id = active_quiz.get("current_poll_id")
        if current_poll_id:
            # Пытаемся удалить из current_polls, если он там еще есть
            poll_info_at_stop = self.state.current_polls.pop(current_poll_id, None)
            if poll_info_at_stop:
                if job_poll_end_name := poll_info_at_stop.get("job_poll_end_name"):
                    jobs_poll_end = self.application.job_queue.get_jobs_by_name(job_poll_end_name)
                    for job_pe in jobs_poll_end: job_pe.schedule_removal()
                    logger.debug(f"Отменена задача {job_poll_end_name} (таймаут опроса) для чата {chat_id}.")
                # Если опрос был активен, пытаемся его закрыть (особенно при /stopquiz)
                try:
                    await context.bot.stop_poll(chat_id, poll_info_at_stop["message_id"])
                    logger.info(f"Опрос {current_poll_id} принудительно закрыт в чате {chat_id}.")
                except Exception as e:
                    logger.debug(f"Не удалось принудительно закрыть опрос {current_poll_id} в чате {chat_id}: {e}")


        # Сообщение о результатах (кроме одиночных вопросов без очков или при ошибке без очков)
        if active_quiz["quiz_type"] != "single" or active_quiz.get("session_scores"):
            if error_occurred and not active_quiz.get("session_scores"):
                if error_message:
                    await context.bot.send_message(chat_id, f"Викторина завершена с ошибкой: {error_message}")
                else:
                    await context.bot.send_message(chat_id, "Викторина завершена из-<y_bin_319>ошибки.")
            else:
                title = "🏁 Викторина завершена!"
                if was_stopped: title = "📝 Викторина остановлена. Результаты:"
                elif error_occurred: title = "⚠️ Викторина завершена с ошибкой. Промежуточные результаты:"
                
                results_text = self.score_manager.format_scores(
                    scores_list=sorted(
                        [{"name": v["name"], "score": v["score"]} for v in active_quiz.get("session_scores", {}).values()],
                        key=lambda x: -x["score"]
                    ),
                    title=title,
                    is_session_score=True,
                    num_questions_in_session=active_quiz["num_questions_total"]
                )
                try:
                    await context.bot.send_message(chat_id, text=results_text, parse_mode=ParseMode.MARKDOWN_V2)
                except Exception as e:
                    logger.error(f"Ошибка при отправке результатов викторины в чат {chat_id}: {e}", exc_info=True)
        
        # Удаление временных сообщений (например, анонс)
        for msg_id_to_del in active_quiz.get("message_ids_to_delete", []):
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id_to_del)
            except Exception:
                pass # Игнорируем ошибки удаления (сообщение могло быть уже удалено)
        
        logger.info(f"Викторина в чате {chat_id} полностью завершена и очищена.")

    # --- Обработчики команд ---
    async def unified_quiz_command_entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        """Точка входа для команды /quiz (или аналога)."""
        chat_id = update.effective_chat.id
        user = update.effective_user
        
        if chat_id in self.state.active_quizzes and not self.state.active_quizzes[chat_id].get("is_stopped"):
            await update.message.reply_text("Викторина уже идет в этом чате. Остановите ее командой /stopquiz.")
            return ConversationHandler.END # Завершаем ConversationHandler, если он был активен

        args = context.args if context.args is not None else []
        
        # Попытка парсинга аргументов для быстрого запуска
        if args:
            # (Логика парсинга аргументов: [количество] [категория...] [announce])
            # Примерная логика (можно усложнить):
            parsed_num_q: Optional[int] = None
            parsed_categories: List[str] = []
            parsed_announce = False
            
            temp_args = list(args)
            if temp_args and temp_args[-1].lower() == "announce":
                parsed_announce = True
                temp_args.pop()
            
            if temp_args and temp_args[0].isdigit():
                try:
                    num_val = int(temp_args[0])
                    if 1 <= num_val <= self.app_config.max_questions_per_session:
                        parsed_num_q = num_val
                        temp_args.pop(0)
                    else:
                        await update.message.reply_text(f"Количество вопросов должно быть от 1 до {self.app_config.max_questions_per_session}.")
                        return ConversationHandler.END
                except ValueError:
                    pass # Первый аргумент не число, значит категория

            if temp_args: # Оставшиеся - категории
                parsed_categories.extend(temp_args)
                # TODO: Валидация категорий

            # Если удалось распарсить хотя бы количество или категорию
            if parsed_num_q is not None or parsed_categories:
                chat_defaults = await self._get_effective_quiz_params_for_chat(chat_id)
                
                final_num_q = parsed_num_q if parsed_num_q is not None else chat_defaults["num_questions"]
                final_categories = parsed_categories if parsed_categories else None # None для случайных или из настроек чата
                is_random_mode = not bool(final_categories)

                quiz_type_session = "single" if final_num_q == 1 else "session"

                await self._initiate_quiz_session(
                    context=context, chat_id=chat_id, initiated_by_user=user,
                    quiz_type=quiz_type_session,
                    num_questions=final_num_q,
                    open_period_seconds=chat_defaults["open_period_seconds"],
                    category_names_for_quiz=final_categories,
                    is_random_categories_mode=is_random_mode,
                    announce=parsed_announce,
                    announce_delay_seconds=chat_defaults["announce_delay_seconds"] if parsed_announce else 0
                )
                return ConversationHandler.END
            elif parsed_announce and not parsed_num_q and not parsed_categories: # /quiz announce
                 # Запускаем с настройками по умолчанию, но с анонсом
                chat_defaults = await self._get_effective_quiz_params_for_chat(chat_id)
                quiz_type_session = "single" if chat_defaults["num_questions"] == 1 else "session"
                await self._initiate_quiz_session(
                    context=context, chat_id=chat_id, initiated_by_user=user,
                    quiz_type=quiz_type_session,
                    num_questions=chat_defaults["num_questions"],
                    open_period_seconds=chat_defaults["open_period_seconds"],
                    category_names_for_quiz=None, # Использует настройки чата или все доступные
                    is_random_categories_mode=not bool(chat_defaults["enabled_categories"]), # Пример
                    announce=True,
                    announce_delay_seconds=chat_defaults["announce_delay_seconds"]
                )
                return ConversationHandler.END


        # Интерактивная настройка, если нет валидных аргументов
        chat_defaults = await self._get_effective_quiz_params_for_chat(chat_id)
        context.chat_data['quiz_config_progress'] = {
            'num_questions': chat_defaults["num_questions"],
            'category_name': "random", # По умолчанию случайные
            'announce': chat_defaults["announce_quiz"],
            'open_period_seconds': chat_defaults["open_period_seconds"], # Сохраняем из настроек чата
            'announce_delay_seconds': chat_defaults["announce_delay_seconds"],
            'quiz_mode': chat_defaults["quiz_mode"], # Для определения типа сессии
            'interval_seconds': chat_defaults.get("interval_seconds") # Для будущего использования
        }
        await self._send_config_message(update, context)
        return QUIZ_CFG_SELECTING_OPTIONS

    async def _send_config_message(self, update_or_query: Union[Update, CallbackQueryHandler], context: ContextTypes.DEFAULT_TYPE):
        """Отправляет или редактирует сообщение с меню конфигурации викторины."""
        config_data = context.chat_data.get('quiz_config_progress')
        if not config_data:
            logger.warning("_send_config_message: quiz_config_progress не найден в chat_data.")
            # Можно отправить сообщение об ошибке или просто завершить
            if isinstance(update_or_query, Update) and update_or_query.message:
                 await update_or_query.message.reply_text("Ошибка конфигурации. Попробуйте /quiz снова.")
            elif hasattr(update_or_query, 'callback_query') and update_or_query.callback_query:
                 await update_or_query.callback_query.answer("Ошибка конфигурации", show_alert=True)
            return

        num_q = config_data['num_questions']
        cat_name = config_data['category_name']
        announce_on = config_data['announce']

        text = (
            f"⚙️ *Настройка викторины*\n\n"
            f"🔢 Вопросы: `{num_q}`\n"
            f"📚 Категория: `{'Случайные' if cat_name == 'random' else cat_name}`\n"
            f"📢 Анонс: `{'Вкл' if announce_on else 'Выкл'}`"
            f"{f' (задержка {config_data["announce_delay_seconds"]} сек)' if announce_on else ''}\n\n"
            f"Выберите параметр для изменения или запустите викторину."
        )
        keyboard = [
            [
                InlineKeyboardButton(f"Вопросы: {num_q}", callback_data=ACTION_SET_NUM_Q_MENU),
                InlineKeyboardButton(f"Категория: {'Случ.' if cat_name == 'random' else cat_name[:7]+'..' if len(cat_name)>7 else cat_name}", callback_data=ACTION_SET_CATEGORY_MENU)
            ],
            [InlineKeyboardButton(f"Анонс: {'Вкл' if announce_on else 'Выкл'}", callback_data=ACTION_TOGGLE_ANNOUNCE)],
            [InlineKeyboardButton("▶️ Запустить", callback_data=ACTION_START_CONFIGURED_QUIZ)],
            [InlineKeyboardButton("❌ Отмена", callback_data=ACTION_CANCEL_CONFIG_QUIZ)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if isinstance(update_or_query, Update): # Первый вызов
            msg = await update_or_query.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
            context.chat_data['_quiz_cfg_message_id'] = msg.message_id
        elif hasattr(update_or_query, 'callback_query') and update_or_query.callback_query: # Редактирование
            query = update_or_query.callback_query
            try:
                await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
            except BadRequest as e:
                if "Message is not modified" not in str(e).lower(): # Игнорируем, если сообщение не изменилось
                    logger.error(f"Ошибка редактирования сообщения конфигурации: {e}")
                    await query.answer("Произошла ошибка при обновлении меню.", show_alert=True)
                else:
                    await query.answer() # Просто подтверждаем получение колбэка

    async def handle_quiz_config_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        query = update.callback_query
        await query.answer()
        
        action_full = query.data
        if not action_full or not action_full.startswith(CB_QUIZ_CFG_PREFIX):
            logger.warning(f"Неизвестный callback в handle_quiz_config_callback: {action_full}")
            return None # Остаемся в текущем состоянии или завершаем, если это мусор

        action = action_full # Для удобства, если не используем часть после префикса напрямую
        
        config_data = context.chat_data.get('quiz_config_progress')
        if not config_data:
            await query.edit_message_text("Сессия настройки истекла. Пожалуйста, начните заново с /quiz.")
            return ConversationHandler.END
        
        # Основное меню конфигурации
        if action == ACTION_BACK_TO_MAIN_CONFIG:
            await self._send_config_message(query, context)
            return QUIZ_CFG_SELECTING_OPTIONS

        # --- Обработка выбора количества вопросов ---
        if action == ACTION_SET_NUM_Q_MENU:
            buttons_num_q = [
                [
                    InlineKeyboardButton("1", callback_data=f"{ACTION_TYPE_NUM_Q_VALUE}:1"),
                    InlineKeyboardButton("5", callback_data=f"{ACTION_TYPE_NUM_Q_VALUE}:5"),
                    InlineKeyboardButton("10", callback_data=f"{ACTION_TYPE_NUM_Q_VALUE}:10")
                ],
                [InlineKeyboardButton("Свое число...", callback_data=f"{ACTION_TYPE_NUM_Q_VALUE}:custom")],
                [InlineKeyboardButton("⬅️ Назад", callback_data=ACTION_BACK_TO_MAIN_CONFIG)]
            ]
            await query.edit_message_text("Выберите количество вопросов:", reply_markup=InlineKeyboardMarkup(buttons_num_q))
            return QUIZ_CFG_SELECTING_OPTIONS # Остаемся в этом же состоянии, просто меняем сообщение

        if action.startswith(ACTION_TYPE_NUM_Q_VALUE):
            value_str = action.split(":", 1)[1]
            if value_str == "custom":
                await query.edit_message_text("Введите желаемое количество вопросов (числом):")
                return QUIZ_CFG_TYPING_NUM_QUESTIONS
            else:
                try:
                    num = int(value_str)
                    if 1 <= num <= self.app_config.max_questions_per_session:
                        config_data['num_questions'] = num
                        await self._send_config_message(query, context)
                        return QUIZ_CFG_SELECTING_OPTIONS
                    else:
                        await query.answer(f"Число от 1 до {self.app_config.max_questions_per_session}!", show_alert=True)
                        return QUIZ_CFG_SELECTING_OPTIONS # Остаемся для исправления
                except ValueError:
                    await query.answer("Это не число!", show_alert=True)
                    return QUIZ_CFG_SELECTING_OPTIONS

        # --- Обработка выбора категории ---
        if action == ACTION_SET_CATEGORY_MENU:
            chat_id = query.message.chat_id
            chat_settings = self.data_manager.get_chat_settings(chat_id)
            # Получаем доступные категории с учетом настроек чата (enabled/disabled)
            available_categories = self.category_manager.get_all_category_names() # Пока все, фильтрация при запуске
            
            cat_buttons = [[InlineKeyboardButton("🎲 Случайные", callback_data=f"{ACTION_SELECT_CATEGORY_VALUE}:random")]]
            if available_categories:
                for cat_name_loop in available_categories[:self.app_config.max_interactive_categories_to_show]:
                    cat_buttons.append([InlineKeyboardButton(cat_name_loop, callback_data=f"{ACTION_SELECT_CATEGORY_VALUE}:{cat_name_loop}")])
                if len(available_categories) > self.app_config.max_interactive_categories_to_show:
                     cat_buttons.append([InlineKeyboardButton("...", callback_data="dummy_more_cats")]) # Заглушка

            cat_buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data=ACTION_BACK_TO_MAIN_CONFIG)])
            await query.edit_message_text("Выберите категорию:", reply_markup=InlineKeyboardMarkup(cat_buttons))
            return QUIZ_CFG_SELECTING_OPTIONS # Остаемся здесь

        if action.startswith(ACTION_SELECT_CATEGORY_VALUE):
            cat_selection = action.split(":", 1)[1]
            config_data['category_name'] = cat_selection # "random" или имя категории
            await self._send_config_message(query, context)
            return QUIZ_CFG_SELECTING_OPTIONS

        # --- Переключение анонса ---
        if action == ACTION_TOGGLE_ANNOUNCE:
            config_data['announce'] = not config_data['announce']
            await self._send_config_message(query, context)
            return QUIZ_CFG_SELECTING_OPTIONS

        # --- Запуск викторины ---
        if action == ACTION_START_CONFIGURED_QUIZ:
            final_cfg = context.chat_data.pop('quiz_config_progress')
            context.chat_data.pop('_quiz_cfg_message_id', None) # Удаляем ID сообщения меню
            
            user = query.from_user
            chat_id_for_quiz = query.message.chat_id

            num_q_final = final_cfg['num_questions']
            cat_name_final = final_cfg['category_name']
            announce_final = final_cfg['announce']
            
            is_random_final = (cat_name_final == "random")
            category_list_for_init = [cat_name_final] if not is_random_final else None
            
            quiz_type_final = "single" if num_q_final == 1 else "session" # Определяем тип по кол-ву вопросов

            await query.edit_message_text(f"🚀 Запускаю викторину с {num_q_final} вопросами...", reply_markup=None)
            
            await self._initiate_quiz_session(
                context=context, chat_id=chat_id_for_quiz, initiated_by_user=user,
                quiz_type=quiz_type_final,
                num_questions=num_q_final,
                open_period_seconds=final_cfg['open_period_seconds'], # Берем из сохраненной конфигурации
                interval_seconds=final_cfg.get('interval_seconds'), # Для будущих серийных с интервалом
                category_names_for_quiz=category_list_for_init,
                is_random_categories_mode=is_random_final,
                announce=announce_final,
                announce_delay_seconds=final_cfg['announce_delay_seconds'] if announce_final else 0
            )
            return ConversationHandler.END

        # --- Отмена конфигурации ---
        if action == ACTION_CANCEL_CONFIG_QUIZ:
            context.chat_data.pop('quiz_config_progress', None)
            context.chat_data.pop('_quiz_cfg_message_id', None)
            await query.edit_message_text("Настройка викторины отменена.")
            return ConversationHandler.END
            
        return QUIZ_CFG_SELECTING_OPTIONS # По умолчанию остаемся в главном меню выбора

    async def handle_typed_num_questions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        """Обрабатывает введенное пользователем количество вопросов."""
        if not update.message or not update.message.text:
            # Это не должно произойти, если фильтры ConversationHandler настроены правильно
            return QUIZ_CFG_TYPING_NUM_QUESTIONS 

        config_data = context.chat_data.get('quiz_config_progress')
        if not config_data:
            await update.message.reply_text("Сессия настройки истекла. Пожалуйста, начните заново с /quiz.")
            return ConversationHandler.END
        
        try:
            num = int(update.message.text)
            if 1 <= num <= self.app_config.max_questions_per_session:
                config_data['num_questions'] = num
                # Удаляем сообщение пользователя и предыдущее сообщение бота с просьбой ввести число
                try:
                    await update.message.delete()
                    if msg_id_to_del := context.chat_data.get('_quiz_cfg_message_id'):
                         # Здесь _quiz_cfg_message_id - это ID сообщения "Введите желаемое количество..."
                         # которое мы отправили перед переходом в состояние TYPING_NUM_QUESTIONS.
                         # Его нужно было бы сохранить перед query.edit_message_text("Введите...")
                         # Сейчас это не реализовано корректно, проще не удалять или переотправить _send_config_message
                         pass # Пока не удаляем сообщение бота, чтобы не усложнять
                except Exception as e_del:
                    logger.debug(f"Не удалось удалить сообщение при вводе числа вопросов: {e_del}")

                await self._send_config_message(update, context) # Отправляем основное меню конфигурации заново
                return QUIZ_CFG_SELECTING_OPTIONS
            else:
                await update.message.reply_text(f"Пожалуйста, введите число от 1 до {self.app_config.max_questions_per_session}.")
                return QUIZ_CFG_TYPING_NUM_QUESTIONS
        except ValueError:
            await update.message.reply_text("Это не похоже на число. Пожалуйста, введите корректное количество вопросов.")
            return QUIZ_CFG_TYPING_NUM_QUESTIONS

    async def cancel_quiz_config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Отмена конфигурации командой /cancel."""
        context.chat_data.pop('quiz_config_progress', None)
        context.chat_data.pop('_quiz_cfg_message_id', None)
        if update.message: # Если это команда
            await update.message.reply_text("Настройка викторины отменена.")
        # Если это был callback, он обработается в handle_quiz_config_callback
        return ConversationHandler.END


    async def stop_quiz_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        user = update.effective_user

        active_quiz = self.state.active_quizzes.get(chat_id)
        if not active_quiz or active_quiz.get("is_stopped"):
            await update.message.reply_text("В этом чате нет активной викторины для остановки.")
            return

        # Проверка прав на остановку (админ или инициатор, кроме daily)
        initiated_by_id = active_quiz.get("initiated_by_user_id")
        can_stop = False
        if update.effective_chat.type == ChatType.PRIVATE:
            can_stop = True
        else:
            try:
                member = await context.bot.get_chat_member(chat_id, user.id)
                if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
                    can_stop = True
            except Exception as e:
                logger.warning(f"Ошибка проверки статуса администратора для {user.id} в чате {chat_id}: {e}")

        if not can_stop and initiated_by_id == str(user.id) and active_quiz.get("quiz_type") != "daily":
            can_stop = True
        
        # Для daily quiz - только админ
        if not can_stop and active_quiz.get("quiz_type") == "daily":
             # Повторная проверка на админа, если не прошли первые условия
             if not (update.effective_chat.type == ChatType.PRIVATE):
                 try:
                     member = await context.bot.get_chat_member(chat_id, user.id)
                     if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
                         can_stop = True
                 except: pass


        if not can_stop:
            await update.message.reply_text("Только администраторы или инициатор викторины (кроме ежедневной) могут ее остановить.")
            return

        logger.info(f"Пользователь {user.id} остановил викторину в чате {chat_id}.")
        active_quiz["is_stopped"] = True # Устанавливаем флаг
        # Финализация произойдет либо при следующем вызове _send_next_question_in_session,
        # либо при срабатывании _handle_poll_end_job для текущего опроса,
        # либо можно вызвать принудительно, если нужно немедленное отображение результатов.
        # Для более быстрой реакции:
        await self._finalize_quiz_session(context, chat_id, was_stopped=True)
        # Сообщение об остановке будет отправлено из _finalize_quiz_session


    def get_handlers(self) -> list:
        quiz_conv_handler = ConversationHandler(
            entry_points=[CommandHandler(self.app_config.commands.quiz, self.unified_quiz_command_entry)],
            states={
                QUIZ_CFG_SELECTING_OPTIONS: [
                    CallbackQueryHandler(self.handle_quiz_config_callback, pattern=f"^{CB_QUIZ_CFG_PREFIX}")
                ],
                QUIZ_CFG_TYPING_NUM_QUESTIONS: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_typed_num_questions)
                ],
                # QUIZ_CFG_SELECTING_CATEGORY: [] # Если будет отдельное состояние для выбора категорий
            },
            fallbacks=[
                CommandHandler(self.app_config.commands.cancel, self.cancel_quiz_config_command),
                CallbackQueryHandler(self.handle_quiz_config_callback, pattern=f"^{ACTION_CANCEL_CONFIG_QUIZ}$") # Обработка кнопки Отмена
            ],
            per_chat=True,
            per_user=True, # Конфигурация уникальна для пользователя, который ее начал
            name="quiz_configuration_conversation", # Имя для отладки и персистентности
            persistent=True # Используем PicklePersistence, настроенный в bot.py
        )
        return [
            quiz_conv_handler,
            CommandHandler(self.app_config.commands.stop_quiz, self.stop_quiz_command),
        ]
