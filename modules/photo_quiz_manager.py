"""
Модуль управления фото-викториной
Отдельная система от обычных текстовых викторин
"""

import asyncio
import json
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from utils import escape_markdown_v2, schedule_job_unique

logger = logging.getLogger(__name__)

# Константы для удаления сообщений
DELAY_BEFORE_PHOTO_QUIZ_DELETION_SECONDS = 180  # 3 минуты (как в обычных викторинах)

@dataclass
class PhotoQuizState:
    """Состояние активной серии фото-викторины"""
    chat_id: int
    user_id: int
    questions: List[Dict[str, str]]
    current_question_index: int = 0
    start_time: datetime = None
    time_limit: int = 30
    hint_schedule: List[int] = None
    hints_enabled: bool = True
    hints_given: List[str] = None
    current_hint_level: int = 0
    is_active: bool = True
    attempts: int = 0
    message_ids_to_delete: Set[int] = None
    timer_task: Optional[asyncio.Task] = None
    masks: Dict[str, str] = None
    total_correct_answers: int = 0
    total_score: float = 0.0

    def __post_init__(self):
        if self.hints_given is None:
            self.hints_given = []
        if self.message_ids_to_delete is None:
            self.message_ids_to_delete = set()

class PhotoQuizManager:
    """Менеджер фото-викторины"""
    
    def __init__(self, data_manager, score_manager):
        self.data_manager = data_manager
        self.score_manager = score_manager
        self.active_photo_quizzes: Dict[int, PhotoQuizState] = {}  # chat_id -> PhotoQuizState
        self.images_metadata: Dict[str, Dict] = {}
        self.images_dir = Path("data/images")
        self.metadata_file = Path("data/photo_quiz_metadata.json")
        
        # Настройки фото-викторины по умолчанию
        self._default_time_limit = 45  # секунд
        
        # Загружаем метаданные изображений
        self._load_images_metadata()
    
    def _load_images_metadata(self):
        """Загружает метаданные изображений из JSON файла"""
        try:
            if self.metadata_file.exists():
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    self.images_metadata = json.load(f)
                logger.info(f"Загружено {len(self.images_metadata)} метаданных изображений")
            else:
                logger.warning("Файл метаданных не найден, создаем пустой")
                self.images_metadata = {}
        except Exception as e:
            logger.error(f"Ошибка загрузки метаданных: {e}")
            self.images_metadata = {}
    
    def _save_images_metadata(self):
        """Сохраняет метаданные изображений в JSON файл"""
        try:
            self.metadata_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.images_metadata, f, ensure_ascii=False, indent=2)
            logger.info("Метаданные изображений сохранены")
        except Exception as e:
            logger.error(f"Ошибка сохранения метаданных: {e}")
    
    def _normalize_name(self, name: str) -> str:
        """Нормализует имя, убирая номера в конце (например, 'Лиса2' -> 'Лиса')"""
        import re
        # Убираем номера в конце имени (например, "Лиса2" -> "Лиса")
        normalized = re.sub(r'\d+$', '', name)
        return normalized.strip()
    
    def _get_image_groups(self) -> Dict[str, List[str]]:
        """Группирует изображения по нормализованному имени"""
        groups = {}
        webp_files = list(self.images_dir.glob("*.webp"))
        
        for image_path in webp_files:
            image_name = image_path.stem
            normalized_name = self._normalize_name(image_name)
            
            if normalized_name not in groups:
                groups[normalized_name] = []
            groups[normalized_name].append(image_name)
        
        return groups
    
    def get_default_time_limit(self) -> int:
        return self._default_time_limit

    def _get_random_image(self) -> Tuple[str, Dict]:
        """Получает случайное изображение и его метаданные"""
        try:
            # Получаем группы изображений
            image_groups = self._get_image_groups()
            if not image_groups:
                raise ValueError("Нет WebP изображений в папке data/images")
            
            # Выбираем случайную группу
            normalized_name = random.choice(list(image_groups.keys()))
            group_images = image_groups[normalized_name]
            
            # Выбираем случайное изображение из группы
            image_name = random.choice(group_images)
            image_path = self.images_dir / f"{image_name}.webp"
            
            # Получаем метаданные для нормализованного имени
            metadata = self.images_metadata.get(normalized_name, {})
            if not metadata:
                # Если метаданных нет, создаем базовые для нормализованного имени
                metadata = {
                    "correct_answer": normalized_name,
                    "display_answer": normalized_name,
                }
                self.images_metadata[normalized_name] = metadata
                self._save_images_metadata()
            
            return str(image_path), metadata
            
        except Exception as e:
            logger.error(f"Ошибка получения случайного изображения: {e}")
            raise
    
    def _generate_mask(self, answer: str, reveal_level: str) -> str:
        """Генерирует маску для подсказки"""
        result_chars: List[str] = []
        reveal_positions: Set[int] = set()

        if reveal_level == "first_letters":
            new_segment = True
            for idx, ch in enumerate(answer):
                if ch in {" ", "-", "_"}:
                    new_segment = True
                    continue
                if new_segment:
                    reveal_positions.add(idx)
                new_segment = False
        elif reveal_level == "partial":
            letters_indexes = [idx for idx, ch in enumerate(answer) if ch not in {" ", "-", "_"}]
            if letters_indexes:
                reveal_count = max(1, len(letters_indexes) // 2)
                rng = random.Random(answer)
                reveal_positions.update(rng.sample(letters_indexes, reveal_count))
            new_segment = True
            for idx, ch in enumerate(answer):
                if ch in {" ", "-", "_"}:
                    new_segment = True
                    continue
                if new_segment:
                    reveal_positions.add(idx)
                new_segment = False

        for idx, ch in enumerate(answer):
            if ch in {" ", "-"}:
                result_chars.append(ch)
            elif ch == "_":
                result_chars.append("_")
            elif idx in reveal_positions or reveal_level == "answer":
                result_chars.append(ch)
            else:
                result_chars.append("⬜")

        return "".join(result_chars)

    def _prepare_masks(self, answer: str) -> Dict[str, str]:
        """Возвращает набор масок для разных уровней подсказок"""
        return {
            "initial": self._generate_mask(answer, "initial"),
            "first_letters": self._generate_mask(answer, "first_letters"),
            "partial": self._generate_mask(answer, "partial"),
            "answer": answer,
        }
    
    def _prepare_question(self) -> Optional[Dict[str, str]]:
        """Подготавливает данные одного фото-вопроса."""
        try:
            image_path, metadata = self._get_random_image()
            display_answer = metadata.get("display_answer") or metadata.get("correct_answer", "")
            display_answer = display_answer.strip()
            if not display_answer:
                return None

            normalized_answer = self._normalize_name(display_answer).lower()
            masks = self._prepare_masks(display_answer)

            return {
                "image_path": image_path,
                "display_answer": display_answer,
                "normalized_answer": normalized_answer,
                "correct_answer": metadata.get("correct_answer", display_answer),
                "masks": masks,
            }
        except Exception as e:
            logger.error(f"Ошибка подготовки фото-вопроса: {e}")
            return None

    async def _send_current_question(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            state = self.active_photo_quizzes.get(chat_id)
            if not state:
                return

            if state.current_question_index >= len(state.questions):
                self.active_photo_quizzes.pop(chat_id, None)
                return

            question_index = state.current_question_index
            current_question = state.questions[question_index]

            state.start_time = datetime.now()
            state.current_hint_level = 0
            state.hints_given = []
            state.attempts = 0
            state.is_active = True
            state.masks = current_question["masks"]

            caption_lines = [
                f"⏰ Время: {state.time_limit} сек",
            ]
            if state.hints_enabled:
                caption_lines.append("💡 Подсказки появятся автоматически")
                caption_lines.append(f"📝 Слово: {state.masks['initial']}")
            caption_lines.append("")
            caption_lines.append("Отправьте ответ в чат сообщением.")

            caption = escape_markdown_v2("\n".join(caption_lines))

            image_path = current_question["image_path"]

            if not Path(image_path).exists():
                logger.error(f"[PhotoQuiz] Файл изображения не найден: {image_path}")
                await self._force_finish(chat_id, context)
                return

            with open(image_path, "rb") as photo:
                message = await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )

            state.message_ids_to_delete.add(message.message_id)

            logger.debug(
                f"Отправлено изображение: {Path(image_path).name}, правильный ответ: {current_question['display_answer']}"
            )

            state.current_question_index += 1

            if state.hints_enabled:
                state.timer_task = asyncio.create_task(self._photo_quiz_timer(chat_id, context))
            else:
                state.timer_task = asyncio.create_task(self._photo_quiz_timer_without_hints(chat_id, context))

        except Exception as e:
            logger.error(f"Ошибка отправки фото-вопроса: {e}", exc_info=True)
            if chat_id in self.active_photo_quizzes:
                await self._force_finish(chat_id, context)

    def _check_almost_correct(self, user_answer: str, correct_answer: str) -> bool:
        """Проверяет, является ли ответ 'почти правильным'"""
        try:
            # Проверяем только правильный ответ
            all_correct_answers = [correct_answer]
            
            for correct in all_correct_answers:
                # 1. Проверяем, содержит ли правильный ответ пользовательский ответ
                if user_answer in correct and len(user_answer) >= 3:
                    return True
                
                # 2. Проверяем, содержит ли пользовательский ответ правильный ответ
                if correct in user_answer and len(correct) >= 3:
                    return True
                
                # 3. Проверяем схожесть по символам (80% совпадение)
                if self._calculate_similarity(user_answer, correct) >= 0.8:
                    return True
                
                # 4. Проверяем, если пользователь добавил лишние символы
                if self._is_extra_characters(user_answer, correct):
                    return True
                
                # 5. Проверяем, если пользователь пропустил символы
                if self._is_missing_characters(user_answer, correct):
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка проверки почти правильного ответа: {e}")
            return False
    
    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Вычисляет схожесть двух строк (0.0 - 1.0)"""
        if not str1 or not str2:
            return 0.0
        
        # Простой алгоритм схожести на основе общих символов
        set1 = set(str1.lower())
        set2 = set(str2.lower())
        
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        
        if union == 0:
            return 0.0
        
        return intersection / union
    
    def _is_extra_characters(self, user_answer: str, correct_answer: str) -> bool:
        """Проверяет, добавил ли пользователь лишние символы"""
        if len(user_answer) <= len(correct_answer) + 2:
            return False
        
        # Проверяем, содержит ли пользовательский ответ правильный ответ
        return correct_answer in user_answer
    
    def _is_missing_characters(self, user_answer: str, correct_answer: str) -> bool:
        """Проверяет, пропустил ли пользователь символы"""
        if len(user_answer) >= len(correct_answer) - 2:
            return False
        
        # Проверяем, содержит ли правильный ответ пользовательский ответ
        return user_answer in correct_answer
    
    def _build_hint_schedule(self, time_limit: int) -> List[int]:
        first_hint = max(5, int(time_limit * 0.4))
        second_hint = max(first_hint + 5, int(time_limit * 0.7))
        return [min(first_hint, time_limit - 5), min(second_hint, time_limit - 2)]

    async def start_photo_quiz(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        user_id: int,
        time_limit: int,
    ) -> bool:
        """Совместимость: запускает одиночный вопрос фото-викторины."""
        return await self.start_photo_quiz_series(
            context=context,
            chat_id=chat_id,
            user_id=user_id,
            time_limit=time_limit,
            question_count=1,
            hints_enabled=True,
        )

    async def start_photo_quiz_series(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        user_id: int,
        time_limit: int,
        question_count: int,
        hints_enabled: bool,
    ) -> bool:
        """Запускает серию фото-вопросов для пользователя."""
        try:
            if chat_id in self.active_photo_quizzes:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=escape_markdown_v2(
                        "🖼️ Фото-викторина уже идет!\n"
                        "Дождитесь завершения или используйте /stop_photo_quiz."
                    ),
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                return False

            questions: List[Dict[str, str]] = []
            for _ in range(max(1, question_count)):
                question = self._prepare_question()
                if question:
                    questions.append(question)

            if not questions:
                raise ValueError("Не удалось подобрать изображения для фото-викторины")

            hint_schedule = self._build_hint_schedule(time_limit)

            logger.debug(
                "[PhotoQuiz] Подготовлено %s вопросов для чата %s: %s",
                len(questions),
                chat_id,
                [Path(q.get("image_path", "")).name for q in questions],
            )

            state = PhotoQuizState(
                chat_id=chat_id,
                user_id=user_id,
                questions=questions,
                current_question_index=0,
                time_limit=time_limit,
                hint_schedule=hint_schedule,
                hints_enabled=hints_enabled,
            )

            self.active_photo_quizzes[chat_id] = state
            await self._send_current_question(chat_id, context)

            logger.info(
                f"Запущена фото-викторина в чате {chat_id} для пользователя {user_id}. Вопросов: {len(questions)}"
            )
            return True

        except Exception as e:
            logger.error(f"Ошибка запуска фото-викторины: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=escape_markdown_v2("❌ Ошибка запуска фото-викторины. Попробуйте позже."),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return False
    
    async def _photo_quiz_timer(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Таймер фото-викторины с подсказками"""
        try:
            state = self.active_photo_quizzes.get(chat_id)
            if not state or not state.hints_enabled:
                return

            start_time = state.start_time
            for idx, hint_time in enumerate(state.hint_schedule, start=1):
                wait_seconds = hint_time - (datetime.now() - start_time).total_seconds()
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)

                current_state = self.active_photo_quizzes.get(chat_id)
                if not current_state or not current_state.is_active or not current_state.hints_enabled:
                    return

                hint_key = "first_letters" if idx == 1 else "partial"
                hint_mask = current_state.masks.get(hint_key, current_state.masks["initial"])
                message = await context.bot.send_message(
                    chat_id=chat_id,
                    text=escape_markdown_v2(f"💡 Подсказка {idx}: {hint_mask}"),
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                current_state.hints_given.append(hint_mask)
                current_state.current_hint_level = idx
                current_state.message_ids_to_delete.add(message.message_id)

            remaining = state.time_limit - (datetime.now() - start_time).total_seconds()
            if remaining > 0:
                await asyncio.sleep(remaining)

            current_state = self.active_photo_quizzes.get(chat_id)
            if current_state and current_state.is_active:
                await self._end_photo_quiz(chat_id, context, timeout=True)

        except Exception as e:
            logger.error(f"Ошибка в таймере фото-викторины: {e}")
            await self._force_finish(chat_id, context)

    async def _photo_quiz_timer_without_hints(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Таймер фото-викторины без подсказок"""
        try:
            state = self.active_photo_quizzes.get(chat_id)
            if not state:
                return

            await asyncio.sleep(state.time_limit)

            current_state = self.active_photo_quizzes.get(chat_id)
            if current_state and current_state.is_active:
                await self._end_photo_quiz(chat_id, context, timeout=True)

        except Exception as e:
            logger.error(f"Ошибка таймера фото-викторины без подсказок: {e}")
            await self._force_finish(chat_id, context)
    
    async def check_answer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Проверяет ответ пользователя в фото-викторине"""
        try:
            chat_id = update.effective_chat.id
            user_answer = update.message.text.strip().lower()

            if chat_id not in self.active_photo_quizzes:
                return False

            quiz_state = self.active_photo_quizzes[chat_id]
            # Текущий вопрос - это current_question_index - 1
            question_index = quiz_state.current_question_index - 1
            if question_index < 0 or question_index >= len(quiz_state.questions):
                return False

            current_question = quiz_state.questions[question_index]
            normalized_correct = current_question["normalized_answer"]

            is_correct = (user_answer == normalized_correct)

            # Проверяем на "почти правильный" ответ
            is_almost_correct = False
            if not is_correct:
                is_almost_correct = self._check_almost_correct(user_answer, normalized_correct)

            logger.debug(
                f"Проверка ответа в фото-викторине: '{user_answer}' vs '{normalized_correct}' -> {is_correct} (почти: {is_almost_correct})"
            )

            if is_correct:
                await self._end_photo_quiz(chat_id, context, correct=True, user_answer=user_answer, is_exact_match=True)
            elif is_almost_correct:
                await update.message.reply_text(
                    escape_markdown_v2("🔥 Вы на верном пути! Но ответ неполный. Попробуйте еще раз."),
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                quiz_state.attempts = getattr(quiz_state, "attempts", 0) + 1
            else:
                await update.message.reply_text(
                    escape_markdown_v2("❌ Неправильно! Попробуйте еще раз."),
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                quiz_state.attempts = getattr(quiz_state, "attempts", 0) + 1

            return True

        except Exception as e:
            logger.error(f"Ошибка проверки ответа: {e}")
            return False
    
    async def _end_photo_quiz(
        self,
        chat_id: int,
        context: ContextTypes.DEFAULT_TYPE,
        correct: bool = False,
        timeout: bool = False,
        user_answer: str = "",
        is_exact_match: bool = True,
    ):
        """Завершает текущий вопрос фото-викторины"""
        try:
            logger.debug(f"Завершение фото-викторины в чате {chat_id}, correct: {correct}, timeout: {timeout}")

            if chat_id not in self.active_photo_quizzes:
                logger.warning(f"Фото-викторина в чате {chat_id} не найдена при завершении")
                return

            quiz_state = self.active_photo_quizzes[chat_id]
            question_index = quiz_state.current_question_index - 1
            if question_index < 0 or question_index >= len(quiz_state.questions):
                return

            quiz_state.is_active = False
            current_question = quiz_state.questions[question_index]

            current_task = asyncio.current_task()
            timer_task = quiz_state.timer_task
            if (
                timer_task
                and not timer_task.done()
                and timer_task is not current_task
            ):
                timer_task.cancel()

            logger.debug(f"Состояние фото-викторины: {len(quiz_state.message_ids_to_delete)} сообщений для удаления")

            points = 0.0
            if correct:
                base_points = 5.0
                if quiz_state.hints_enabled and quiz_state.hint_schedule:
                    first_hint_time = quiz_state.hint_schedule[0]
                    elapsed = (datetime.now() - quiz_state.start_time).total_seconds()
                    if elapsed < first_hint_time:
                        base_points += 1.0

                attempts = getattr(quiz_state, "attempts", 0)
                penalty = attempts * 0.5
                points = max(1.0, base_points - penalty)

                # Обновляем общую статистику
                quiz_state.total_correct_answers += 1
                quiz_state.total_score += points

                chat_id_str = str(quiz_state.chat_id)
                user_id_str = str(quiz_state.user_id)

                if quiz_state.chat_id not in self.data_manager.state.user_scores:
                    self.data_manager.state.user_scores[quiz_state.chat_id] = {}

                if user_id_str not in self.data_manager.state.user_scores[quiz_state.chat_id]:
                    self.data_manager.state.user_scores[quiz_state.chat_id][user_id_str] = {
                        "name": f"User {user_id_str}",
                        "score": 0,
                        "answered_polls": set(),
                        "correct_answers_count": 0,
                        "daily_answered_polls": set(),
                        "first_answer_time": None,
                        "last_answer_time": None,
                        "milestones_achieved": set(),
                    }

                self.data_manager.state.user_scores[quiz_state.chat_id][user_id_str]["score"] += points
                self.data_manager.state.user_scores[quiz_state.chat_id][user_id_str]["correct_answers_count"] += 1

                logger.debug(
                    f"Начислено {points} очков пользователю {user_id_str} в чате {quiz_state.chat_id} за фото-викторину"
                )

                self.data_manager.save_user_data(quiz_state.chat_id)

            attempts = getattr(quiz_state, "attempts", 0)
            penalty_value = attempts * 0.5
            points_display = f"{points:.1f}" if points % 1 else f"{int(points)}"
            penalty_display = f"{penalty_value:.1f}" if penalty_value % 1 else f"{int(penalty_value)}"

            escape = escape_markdown_v2

            base_text_lines = []
            if correct:
                header = escape("🎉 Правильно! 🟢")
                base_text_lines.append(f"*{header}*")
                base_text_lines.append("")
                base_text_lines.append(f"✅ Ответ: {escape(current_question['display_answer'])}")
                if attempts > 0:
                    base_text_lines.append(
                        f"🏆 Очки: {escape('+')}{escape(points_display)} (штраф {escape('-')}{escape(penalty_display)})"
                    )
                else:
                    base_text_lines.append(f"🏆 Очки: {escape('+')}{escape(points_display)}")
                base_text_lines.append(
                    f"⏱️ Время: {escape(str(int((datetime.now() - quiz_state.start_time).total_seconds())))} сек"
                )
            elif timeout:
                header = escape("⏰ Время истекло! 🕒")
                base_text_lines.append(f"*{header}*")
                base_text_lines.append("")
                base_text_lines.append(escape("😊 Ничего страшного! Попробуйте снова позже."))
            else:
                header = escape("❌ Неправильно! 🔴")
                base_text_lines.append(f"*{header}*")
                base_text_lines.append("")
                base_text_lines.append(
                    f"✅ Правильный ответ: {escape(current_question['display_answer'])}"
                )

            result_text = "\n".join(base_text_lines)
            logger.debug(
                "[PhotoQuiz] Итоговое сообщение (chat=%s, question_index=%s, timeout=%s, correct=%s): %s",
                chat_id,
                question_index,
                timeout,
                correct,
                result_text,
            )

            try:
                result_message_obj = await context.bot.send_message(
                    chat_id=chat_id,
                    text=result_text,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                logger.info(
                    "[PhotoQuiz] Сообщение о результате отправлено (chat=%s, message_id=%s)",
                    chat_id,
                    result_message_obj.message_id,
                )
                quiz_state.message_ids_to_delete.add(result_message_obj.message_id)
            except Exception as send_error:
                logger.error(
                    "[PhotoQuiz] Ошибка отправки сообщения о результате (chat=%s): %s | text=%s",
                    chat_id,
                    send_error,
                    result_text,
                    exc_info=True,
                )

            if quiz_state.current_question_index < len(quiz_state.questions):
                logger.info(
                    "[PhotoQuiz] Переход к следующему вопросу (chat=%s, next_index=%s)",
                    chat_id,
                    quiz_state.current_question_index,
                )
                await asyncio.sleep(1)
                await self._send_current_question(chat_id, context)
                return

            # Серия завершена - отправляем итоговое сообщение
            logger.info("[PhotoQuiz] Все вопросы пройдены, отправляем итоговое сообщение")
            await self._send_final_results(chat_id, context)

            logger.info(
                "[PhotoQuiz] Планируем очистку сообщений (chat=%s, total_messages=%s)",
                chat_id,
                len(quiz_state.message_ids_to_delete),
            )
            if quiz_state.message_ids_to_delete:
                await self._schedule_photo_quiz_cleanup(
                    chat_id, list(quiz_state.message_ids_to_delete), context
                )

            del self.active_photo_quizzes[chat_id]
            logger.info("Фото-викторина завершена в чате %s (серия завершена)", chat_id)

        except Exception as e:
            logger.error(f"Ошибка завершения фото-викторины: {e}")

    async def _send_final_results(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Отправляет итоговое сообщение по завершению серии фото-вопросов"""
        try:
            state = self.active_photo_quizzes.get(chat_id)
            if not state:
                return

            total_questions = len(state.questions)
            correct_answers = state.total_correct_answers
            total_score = state.total_score

            accuracy = (correct_answers / total_questions * 100) if total_questions > 0 else 0

            result_lines = [
                escape_markdown_v2("🏁 Фото-викторина завершена!"),
                "",
                escape_markdown_v2(f"📊 Всего вопросов: {total_questions}"),
                escape_markdown_v2(f"✅ Правильных ответов: {correct_answers}"),
                escape_markdown_v2(f"📈 Точность: {accuracy:.1f}%"),
                escape_markdown_v2(f"🏆 Общие очки: {total_score:.1f}"),
                "",
                escape_markdown_v2("Спасибо за участие! 🎉")
            ]

            result_text = "\n".join(result_lines)

            message = await context.bot.send_message(
                chat_id=chat_id,
                text=result_text,
                parse_mode=ParseMode.MARKDOWN_V2,
            )

            state.message_ids_to_delete.add(message.message_id)

            logger.info(f"[PhotoQuiz] Отправлено итоговое сообщение серии в чате {chat_id}")

        except Exception as e:
            logger.error(f"Ошибка отправки итогового сообщения фото-викторины в чате {chat_id}: {e}")

    async def _force_finish(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Принудительно завершает зависшую викторину"""
        quiz_state = self.active_photo_quizzes.pop(chat_id, None)
        if not quiz_state:
            return
        try:
            quiz_state.is_active = False
            if quiz_state.timer_task and not quiz_state.timer_task.done():
                quiz_state.timer_task.cancel()
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=chat_id,
            text=escape_markdown_v2("❌ Фото-викторина остановлена из-за ошибки."),
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def _schedule_photo_quiz_cleanup(self, chat_id: int, message_ids: List[int], context: ContextTypes.DEFAULT_TYPE):
        """Планирует отложенное удаление сообщений фото-викторины"""
        try:
            logger.info(f"Начинаем планирование удаления {len(message_ids)} сообщений фото-викторины для чата {chat_id}")
            
            job_queue = context.job_queue
            if not job_queue:
                logger.error("Job queue не доступен в context!")
                return
                
            job_name = f"delayed_photo_quiz_cleanup_chat_{chat_id}_{int(datetime.now().timestamp())}"
            
            logger.info(f"Создаем задачу {job_name} с задержкой {DELAY_BEFORE_PHOTO_QUIZ_DELETION_SECONDS} секунд")
            
            schedule_job_unique(
                job_queue,
                job_name=job_name,
                callback=self._delayed_delete_photo_quiz_messages_job,
                when=timedelta(seconds=DELAY_BEFORE_PHOTO_QUIZ_DELETION_SECONDS),
                data={"chat_id": chat_id, "message_ids": message_ids}
            )
            
            logger.info(f"✅ Запланировано отложенное удаление {len(message_ids)} сообщений фото-викторины для чата {chat_id} (job: {job_name}, delay: {DELAY_BEFORE_PHOTO_QUIZ_DELETION_SECONDS}s)")
            
        except Exception as e:
            logger.error(f"❌ Ошибка планирования удаления сообщений фото-викторины: {e}")
    
    async def _delayed_delete_photo_quiz_messages_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Отложенное удаление сообщений фото-викторины"""
        try:
            chat_id = context.job.data["chat_id"]
            message_ids = context.job.data["message_ids"]
            
            logger.info(f"Начинаем отложенное удаление {len(message_ids)} сообщений фото-викторины в чате {chat_id}")
            
            deleted_count = 0
            for msg_id in message_ids:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                    deleted_count += 1
                    logger.debug(f"Сообщение фото-викторины {msg_id} удалено из чата {chat_id}")
                except Exception as e:
                    logger.warning(f"Не удалось удалить сообщение фото-викторины {msg_id} из чата {chat_id}: {e}")
            
            logger.info(f"Отложенное удаление сообщений фото-викторины в чате {chat_id} завершено. Удалено: {deleted_count}/{len(message_ids)}")
            
        except Exception as e:
            logger.error(f"Ошибка отложенного удаления сообщений фото-викторины: {e}")
    
    async def stop_photo_quiz(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Останавливает активную фото-викторину"""
        try:
            chat_id = update.effective_chat.id

            if chat_id not in self.active_photo_quizzes:
                await update.message.reply_text("❌ В этом чате нет активной фото-викторины.")
                return

            quiz_state = self.active_photo_quizzes[chat_id]
            quiz_state.is_active = False
            if quiz_state.timer_task and not quiz_state.timer_task.done():
                quiz_state.timer_task.cancel()

            answer = "—"
            question_index = quiz_state.current_question_index - 1
            if question_index >= 0 and question_index < len(quiz_state.questions):
                answer = quiz_state.questions[question_index]["display_answer"]

            message_text = escape_markdown_v2(
                f"🛑 Фото-викторина остановлена!\n\n✅ Правильный ответ: {answer}"
            )

            await update.message.reply_text(
                message_text,
                parse_mode=ParseMode.MARKDOWN_V2,
            )

            if quiz_state.message_ids_to_delete:
                await self._schedule_photo_quiz_cleanup(
                    chat_id, list(quiz_state.message_ids_to_delete), context
                )

            del self.active_photo_quizzes[chat_id]

        except Exception as e:
            logger.error(f"Ошибка остановки фото-викторины: {e}")
    
    def get_active_photo_quiz(self, chat_id: int) -> Optional[PhotoQuizState]:
        """Получает активную фото-викторину для чата"""
        return self.active_photo_quizzes.get(chat_id)
