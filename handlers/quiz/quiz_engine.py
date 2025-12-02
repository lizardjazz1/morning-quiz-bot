"""
Движок викторин для Morning Quiz Bot
Отвечает за создание, управление и выполнение викторин
"""

from __future__ import annotations
import logging
import asyncio
from typing import List, Optional, Dict, Any, Union, Tuple
from datetime import datetime, timedelta

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, User as TelegramUser
from telegram.ext import ContextTypes

from .quiz_types import (
    QuizConfig, QuizSession, QuizQuestion, QuizAnswer,
    QuizMode, QuizState, QuizResult
)
from .quiz_validator import QuizValidator
from modules.category_manager import CategoryManager
from modules.score_manager import ScoreManager
from utils import escape_markdown_v2
from modules.telegram_utils import safe_send_message

logger = logging.getLogger(__name__)


class QuizEngine:
    """Движок викторин - основной компонент для работы с викторинами"""

    def __init__(self, category_manager: CategoryManager, score_manager: ScoreManager):
        self.category_manager = category_manager
        self.score_manager = score_manager
        self.active_sessions: Dict[str, QuizSession] = {}
        self.session_results: Dict[str, List[QuizResult]] = {}

    async def create_quiz_session(
        self,
        chat_id: int,
        config: QuizConfig,
        context: ContextTypes.DEFAULT_TYPE
    ) -> Tuple[bool, str, Optional[QuizSession]]:
        """Создать новую сессию викторины"""
        try:
            # Валидируем конфигурацию
            errors = QuizValidator.validate_quiz_config(config)
            if errors:
                return False, f"Ошибки в конфигурации: {'; '.join(errors)}", None

            # Генерируем ID сессии
            session_id = f"quiz_{chat_id}_{int(datetime.now().timestamp())}"

            # Получаем вопросы из категорий
            questions = await self._get_questions_for_config(config)

            if not questions:
                return False, "Не удалось получить вопросы для выбранных категорий", None

            # Создаем сессию
            session = QuizSession(
                session_id=session_id,
                chat_id=chat_id,
                config=config,
                questions=questions
            )

            # Сохраняем сессию
            self.active_sessions[session_id] = session

            logger.info(f"✅ Создана викторина {session_id} с {len(questions)} вопросами")
            return True, "", session

        except Exception as e:
            logger.error(f"❌ Ошибка при создании викторины: {e}")
            return False, f"Ошибка при создании викторины: {str(e)}", None

    async def start_quiz_session(self, session: QuizSession, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Запустить викторину"""
        try:
            if session.state != QuizState.CREATED:
                logger.warning(f"Попытка запустить викторину в состоянии {session.state}")
                return False

            session.state = QuizState.STARTED
            session.started_at = datetime.now()

            # Отправляем первое сообщение
            success = await self._send_quiz_start_message(session, context)
            if not success:
                session.state = QuizState.CANCELLED
                return False

            # Запускаем первый вопрос
            await self._send_next_question(session, context)

            logger.info(f"🚀 Запущена викторина {session.session_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка при запуске викторины {session.session_id}: {e}")
            session.state = QuizState.CANCELLED
            return False

    async def process_answer(
        self,
        session_id: str,
        user: TelegramUser,
        selected_option: int,
        context: ContextTypes.DEFAULT_TYPE
    ) -> Tuple[bool, str]:
        """Обработать ответ пользователя"""
        try:
            session = self.active_sessions.get(session_id)
            if not session:
                return False, "Викторина не найдена"

            if not session.is_active:
                return False, "Викторина не активна"

            current_question = session.current_question
            if not current_question:
                return False, "Вопрос не найден"

            # Проверяем, отвечал ли уже пользователь
            question_answers = session.answers.get(current_question.question_id, [])
            user_answer = next((a for a in question_answers if a.user_id == user.id), None)

            if user_answer:
                return False, "Вы уже отвечали на этот вопрос"

            # Создаем новый ответ
            is_correct = selected_option == current_question.correct_option
            response_time = None  # Можно добавить расчет времени ответа

            answer = QuizAnswer(
                user_id=user.id,
                question_id=current_question.question_id,
                selected_option=selected_option,
                timestamp=datetime.now(),
                is_correct=is_correct,
                response_time=response_time
            )

            # Сохраняем ответ
            if current_question.question_id not in session.answers:
                session.answers[current_question.question_id] = []
            session.answers[current_question.question_id].append(answer)

            # Обновляем статистику пользователя
            await self.score_manager.update_user_score(
                user.id, session.chat_id, is_correct, current_question.category
            )

            logger.info(f"✅ Ответ пользователя {user.first_name}: {'✓' if is_correct else '✗'}")

            return True, ""

        except Exception as e:
            logger.error(f"❌ Ошибка при обработке ответа: {e}")
            return False, f"Ошибка при обработке ответа: {str(e)}"

    async def finish_quiz_session(
        self,
        session: QuizSession,
        context: ContextTypes.DEFAULT_TYPE,
        reason: str = "normal"
    ) -> bool:
        """Завершить викторину"""
        try:
            if not session.is_active:
                logger.warning(f"Попытка завершить неактивную викторину {session.session_id}")
                return False

            session.state = QuizState.COMPLETED if reason == "normal" else QuizState.CANCELLED
            session.completed_at = datetime.now()

            # Генерируем результаты
            results = await self._generate_quiz_results(session)

            # Отправляем финальное сообщение
            await self._send_quiz_results(session, results, context)

            # Очищаем сессию
            if session.session_id in self.active_sessions:
                del self.active_sessions[session.session_id]

            logger.info(f"🏁 Завершена викторина {session.session_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка при завершении викторины {session.session_id}: {e}")
            return False

    async def _get_questions_for_config(self, config: QuizConfig) -> List[QuizQuestion]:
        """Получить вопросы для конфигурации викторины"""
        questions = []

        if config.category_pool_mode:
            # Режим общего пула - берем вопросы из всех категорий
            all_categories = self.category_manager.get_all_categories()
            for category in config.categories:
                if category in all_categories:
                    category_questions = await self.category_manager.get_questions_for_category(
                        category, config.num_questions // len(config.categories) + 1
                    )
                    questions.extend(category_questions)
        else:
            # Обычный режим - равномерно распределяем по категориям
            questions_per_category = config.num_questions // len(config.categories)
            remainder = config.num_questions % len(config.categories)

            for i, category in enumerate(config.categories):
                num_questions = questions_per_category + (1 if i < remainder else 0)
                category_questions = await self.category_manager.get_questions_for_category(
                    category, num_questions
                )
                questions.extend(category_questions)

        # Перемешиваем и ограничиваем количество
        import random
        random.shuffle(questions)
        return questions[:config.num_questions]

    async def _send_quiz_start_message(self, session: QuizSession, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Отправить сообщение о начале викторины"""
        try:
            message_text = f"""🎯 **Викторина начинается!**

📊 **Всего вопросов:** {session.config.num_questions}
📚 **Категории:** {', '.join(session.config.categories)}
⏱️ **Режим:** {session.config.mode.value.title()}

Удачи! 🚀"""

            keyboard = [[InlineKeyboardButton("🚀 Начать!", callback_data=f"start_{session.session_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                chat_id=session.chat_id,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode='MarkdownV2'
            )

            return True

        except Exception as e:
            logger.error(f"❌ Ошибка при отправке сообщения о начале викторины: {e}")
            return False

    async def _send_next_question(self, session: QuizSession, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Отправить следующий вопрос"""
        try:
            if session.current_question_index >= len(session.questions):
                # Викторина завершена
                await self.finish_quiz_session(session, context)
                return True

            question = session.questions[session.current_question_index]

            # Создаем клавиатуру с вариантами ответов
            keyboard = []
            for i, option in enumerate(question.options):
                keyboard.append([InlineKeyboardButton(
                    f"{chr(65 + i)}. {option}",
                    callback_data=f"answer_{session.session_id}_{question.question_id}_{i}"
                )])

            reply_markup = InlineKeyboardMarkup(keyboard)

            # Формируем текст вопроса
            progress = session.progress
            question_text = f"""❓ **Вопрос {progress[0]} из {progress[1]}**

{question.text}

📚 *Категория: {question.category}*"""

            if question.explanation:
                question_text += f"\n\n💡 {question.explanation}"

            await context.bot.send_message(
                chat_id=session.chat_id,
                text=question_text,
                reply_markup=reply_markup,
                parse_mode='MarkdownV2'
            )

            # Увеличиваем счетчик вопросов
            session.current_question_index += 1

            return True

        except Exception as e:
            logger.error(f"❌ Ошибка при отправке вопроса: {e}")
            return False

    async def _generate_quiz_results(self, session: QuizSession) -> List[QuizResult]:
        """Сгенерировать результаты викторины"""
        results = []

        # Группируем ответы по пользователям
        user_answers = {}
        for question_answers in session.answers.values():
            for answer in question_answers:
                if answer.user_id not in user_answers:
                    user_answers[answer.user_id] = []
                user_answers[answer.user_id].append(answer)

        # Создаем результаты для каждого пользователя
        for user_id, answers in user_answers.items():
            correct_answers = sum(1 for a in answers if a.is_correct)

            result = QuizResult(
                user_id=user_id,
                session_id=session.session_id,
                chat_id=session.chat_id,
                total_questions=len(answers),
                correct_answers=correct_answers,
                answers=answers
            )

            results.append(result)

        # Сортируем по количеству правильных ответов
        results.sort(key=lambda r: (-r.correct_answers, r.total_questions))

        return results

    async def _send_quiz_results(
        self,
        session: QuizSession,
        results: List[QuizResult],
        context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        """Отправить результаты викторины"""
        try:
            message_text = f"""🏆 **Викторина завершена!**

📊 **Статистика:**
• Всего вопросов: {session.config.num_questions}
• Участников: {len(results)}
• Категории: {', '.join(session.config.categories)}

🎖️ **Результаты:**"""

            # Добавляем топ-участников
            for i, result in enumerate(results[:10], 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                accuracy = result.accuracy

                message_text += f"\n{medal} {accuracy:.1f}% - {result.correct_answers}/{result.total_questions}"

            await context.bot.send_message(
                chat_id=session.chat_id,
                text=message_text,
                parse_mode='MarkdownV2'
            )

            return True

        except Exception as e:
            logger.error(f"❌ Ошибка при отправке результатов: {e}")
            return False

    def get_active_session(self, session_id: str) -> Optional[QuizSession]:
        """Получить активную сессию по ID"""
        return self.active_sessions.get(session_id)

    def get_chat_sessions(self, chat_id: int) -> List[QuizSession]:
        """Получить все активные сессии для чата"""
        return [
            session for session in self.active_sessions.values()
            if session.chat_id == chat_id
        ]

    def get_session_stats(self) -> Dict[str, Any]:
        """Получить статистику сессий"""
        return {
            'active_sessions': len(self.active_sessions),
            'total_sessions_today': len([
                s for s in self.active_sessions.values()
                if s.created_at.date() == datetime.now().date()
            ])
        }
