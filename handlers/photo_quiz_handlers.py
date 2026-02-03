"""
Обработчики команд фото-викторины
Отдельная система от обычных текстовых викторин
"""

import logging
from typing import Dict, Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from telegram.error import BadRequest
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from modules.photo_quiz_manager import PhotoQuizManager
from modules.telegram_utils import safe_send_message
from utils import escape_markdown_v2

logger = logging.getLogger(__name__)

PHOTO_CFG_OPTIONS = "photo_cfg_options"
PHOTO_CFG_QCOUNT_INPUT = "photo_cfg_qcount_input"

CB_PQCFG_PREFIX = "pqcfg_"
CB_PQCFG_TIME = f"{CB_PQCFG_PREFIX}time"
CB_PQCFG_QUESTIONS = f"{CB_PQCFG_PREFIX}qcount"
CB_PQCFG_QCOUNT_VALUE = f"{CB_PQCFG_PREFIX}qval"
CB_PQCFG_HINTS = f"{CB_PQCFG_PREFIX}hints"
CB_PQCFG_START = f"{CB_PQCFG_PREFIX}start"
CB_PQCFG_CANCEL = f"{CB_PQCFG_PREFIX}cancel"
CB_PQCFG_NOOP = f"{CB_PQCFG_PREFIX}noop"

PHOTO_CFG_STORE_KEY = "photo_quiz_cfg"
PHOTO_CFG_MENU_MSG_KEY = "_photo_quiz_cfg_msg_id"

DEFAULT_TIME_LIMIT = 60
TIME_PRESETS = [60, 90, 120, 180]
DEFAULT_QUESTION_COUNT = 3
QUESTION_COUNT_MIN = 1
QUESTION_COUNT_MAX = 10


class PhotoQuizHandlers:
    """Обработчики команд фото-викторины"""

    def __init__(self, photo_quiz_manager: PhotoQuizManager):
        self.photo_quiz_manager = photo_quiz_manager

    async def photo_quiz_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Точка входа команды /photo_quiz -> показывает меню настроек"""
        if not update.message or not update.effective_chat or not update.effective_user:
            return ConversationHandler.END

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        # Проверяем, не идет ли уже фото-викторина
        active_quiz = self.photo_quiz_manager.get_active_photo_quiz(chat_id)
        if active_quiz and active_quiz.is_active:
            await update.message.reply_text(
                escape_markdown_v2("🖼️ Фото-викторина уже идет. Остановите текущую: `/stop_photo_quiz`."),
                parse_mode="MarkdownV2",
            )
            return ConversationHandler.END

        cfg = context.chat_data.get(PHOTO_CFG_STORE_KEY, {})
        if "time_limit" not in cfg:
            cfg["time_limit"] = self.photo_quiz_manager.get_default_time_limit() or DEFAULT_TIME_LIMIT
        if "question_count" not in cfg:
            cfg["question_count"] = DEFAULT_QUESTION_COUNT
        if "hints_enabled" not in cfg:
            cfg["hints_enabled"] = True

        cfg.update(
            {
                "chat_id": chat_id,
                "user_id": user_id,
                "original_command_message_id": update.message.message_id,
            }
        )
        context.chat_data[PHOTO_CFG_STORE_KEY] = cfg

        await self._send_photo_quiz_cfg_message(update, context)
        return PHOTO_CFG_OPTIONS

    async def stop_photo_quiz_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /stop_photo_quiz"""
        try:
            await self.photo_quiz_manager.stop_photo_quiz(update, context)
        except Exception as e:
            logger.error(f"Ошибка в команде /stop_photo_quiz: {e}")
            if update.message:
                await update.message.reply_text(
                    escape_markdown_v2("❌ Ошибка остановки фото-викторины."),
                    parse_mode="MarkdownV2",
                )

    async def photo_quiz_help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /photo_quiz_help"""
        if not update.message:
            return
        
        try:
            # Формируем текст справки с правильным экранированием для MarkdownV2
            help_text = (
                f"🖼️ {escape_markdown_v2('Фото-викторина - Помощь')}\n\n"
                f"{escape_markdown_v2('Команды:')}\n"
                f"• {escape_markdown_v2('/photo_quiz')} \\- {escape_markdown_v2('Настроить и запустить фото-викторину')}\n"
                f"• {escape_markdown_v2('/stop_photo_quiz')} \\- {escape_markdown_v2('Остановить активную фото-викторину')}\n"
                f"• {escape_markdown_v2('/photo_quiz_help')} \\- {escape_markdown_v2('Эта справка')}\n\n"
                f"{escape_markdown_v2('Как играть:')}\n"
                f"1\\. {escape_markdown_v2('Запустите')} {escape_markdown_v2('/photo_quiz')}\n"
                f"2\\. {escape_markdown_v2('Выберите время ответа и нажмите «Запустить фото-викторину»')}\n"
                f"3\\. {escape_markdown_v2('Угадайте слово по изображению до окончания таймера')}\n"
                f"4\\. {escape_markdown_v2('Подсказки появятся автоматически, если это потребуется')}\n\n"
                f"{escape_markdown_v2('Очки:')}\n"
                f"• {escape_markdown_v2('Правильный ответ: 5 очков')}\n"
                f"• {escape_markdown_v2('Быстрый ответ (до первой подсказки): +1 очко')}\n"
                f"• {escape_markdown_v2('Каждая ошибка: -0.5 очка (но минимум 1 очко за победу)')}\n\n"
                f"{escape_markdown_v2('Удачи!')} 🎯"
            )

            await safe_send_message(
                bot=context.bot,
                chat_id=update.message.chat_id,
                text=help_text,
                reply_to_message_id=update.message.message_id,
                parse_mode="MarkdownV2",
            )

        except Exception as e:
            logger.error(f"Ошибка в команде /photo_quiz_help: {e}", exc_info=True)
            try:
                await safe_send_message(
                    bot=context.bot,
                    chat_id=update.message.chat_id,
                    text=escape_markdown_v2("❌ Ошибка отображения справки."),
                    reply_to_message_id=update.message.message_id,
                    parse_mode="MarkdownV2",
                )
            except Exception as e2:
                logger.error(f"Не удалось отправить сообщение об ошибке: {e2}")

    async def handle_photo_quiz_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик сообщений в фото-викторине"""
        try:
            chat_id = update.effective_chat.id
            active_quiz = self.photo_quiz_manager.get_active_photo_quiz(chat_id)

            if active_quiz and active_quiz.is_active:
                await self.photo_quiz_manager.check_answer(update, context)
            else:
                return False

        except Exception as e:
            logger.error(f"Ошибка обработки сообщения в фото-викторине: {e}")
            return False

        return True

    async def handle_photo_quiz_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback-данных фото-викторины"""
        query = update.callback_query
        if not query:
            return ConversationHandler.END

        await query.answer()
        data = query.data or ""
        cfg: Dict[str, Optional[int]] = context.chat_data.get(PHOTO_CFG_STORE_KEY, {})

        if not cfg:
            await query.answer("Настройка устарела. Попробуйте снова.", show_alert=True)
            await self._cleanup_cfg_message(context, query.message)
            return ConversationHandler.END

        if data == CB_PQCFG_NOOP:
            cfg.pop("awaiting_qcount_input", None)
            await self._send_photo_quiz_cfg_message(query, context)
            return PHOTO_CFG_OPTIONS

        if data.startswith(CB_PQCFG_QCOUNT_VALUE):
            value = data.replace(f"{CB_PQCFG_QCOUNT_VALUE}:", "", 1)
            if value == "manual":
                cfg["awaiting_qcount_input"] = True
                context.chat_data[PHOTO_CFG_STORE_KEY] = cfg
                await self._prompt_manual_question_count(query, context)
                return PHOTO_CFG_QCOUNT_INPUT

            try:
                new_count = int(value)
            except ValueError:
                await query.answer("Некорректное число вопросов.", show_alert=True)
                return PHOTO_CFG_OPTIONS

            if not (QUESTION_COUNT_MIN <= new_count <= QUESTION_COUNT_MAX):
                await query.answer(
                    f"Допустимо от {QUESTION_COUNT_MIN} до {QUESTION_COUNT_MAX} вопросов.",
                    show_alert=True,
                )
                return PHOTO_CFG_OPTIONS

            cfg["question_count"] = new_count
            cfg.pop("awaiting_qcount_input", None)
            context.chat_data[PHOTO_CFG_STORE_KEY] = cfg
            await self._send_photo_quiz_cfg_message(query, context)
            return PHOTO_CFG_OPTIONS

        if data == CB_PQCFG_TIME:
            current = cfg.get("time_limit") or DEFAULT_TIME_LIMIT
            try:
                idx = TIME_PRESETS.index(current)
                next_idx = (idx + 1) % len(TIME_PRESETS)
            except ValueError:
                next_idx = 0

            cfg["time_limit"] = TIME_PRESETS[next_idx]
            context.chat_data[PHOTO_CFG_STORE_KEY] = cfg
            await self._send_photo_quiz_cfg_message(query, context)
            return PHOTO_CFG_OPTIONS

        if data == CB_PQCFG_QUESTIONS:
            await self._show_question_count_menu(query, context)
            return PHOTO_CFG_OPTIONS

        if data == CB_PQCFG_HINTS:
            hints_enabled = cfg.get("hints_enabled", True)
            cfg["hints_enabled"] = not hints_enabled
            context.chat_data[PHOTO_CFG_STORE_KEY] = cfg
            await self._send_photo_quiz_cfg_message(query, context)
            return PHOTO_CFG_OPTIONS

        if data == CB_PQCFG_START:
            chat_id = cfg.get("chat_id")
            user_id = cfg.get("user_id")
            time_limit = cfg.get("time_limit") or DEFAULT_TIME_LIMIT
            question_count = cfg.get("question_count") or DEFAULT_QUESTION_COUNT
            hints_enabled = cfg.get("hints_enabled", True)

            if chat_id is None or user_id is None:
                await query.answer("Не удалось определить параметры запуска.", show_alert=True)
                return PHOTO_CFG_OPTIONS

            active_quiz = self.photo_quiz_manager.get_active_photo_quiz(chat_id)
            if active_quiz and active_quiz.is_active:
                await query.answer("Фото-викторина уже идет в этом чате.", show_alert=True)
                await self._send_photo_quiz_cfg_message(query, context)
                return PHOTO_CFG_OPTIONS

            await self.photo_quiz_manager.start_photo_quiz_series(
                context=context,
                chat_id=chat_id,
                user_id=user_id,
                time_limit=time_limit,
                question_count=question_count,
                hints_enabled=hints_enabled,
            )

            await self._cleanup_cfg_message(context, query.message)
            context.chat_data.pop(PHOTO_CFG_STORE_KEY, None)
            return ConversationHandler.END

        if data == CB_PQCFG_CANCEL:
            await self._cleanup_cfg_message(context, query.message)
            context.chat_data.pop(PHOTO_CFG_STORE_KEY, None)
            return ConversationHandler.END

        # NO-OP or неизвестное действие
        return PHOTO_CFG_OPTIONS

    async def cancel_photo_quiz_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /cancel внутри диалога фото-викторины"""
        await self._cleanup_cfg_message(context)
        context.chat_data.pop(PHOTO_CFG_STORE_KEY, None)
        if update.message:
            await update.message.reply_text(escape_markdown_v2("Фото-викторина отменена."))
        return ConversationHandler.END

    async def _send_photo_quiz_cfg_message(self, update_or_query, context: ContextTypes.DEFAULT_TYPE):
        cfg = context.chat_data.get(PHOTO_CFG_STORE_KEY)
        if not cfg:
            logger.error("_send_photo_quiz_cfg_message: конфигурация отсутствует")
            return

        time_limit = cfg.get("time_limit") or DEFAULT_TIME_LIMIT
        question_count = cfg.get("question_count") or DEFAULT_QUESTION_COUNT
        hints_enabled = cfg.get("hints_enabled", True)
        title_text = escape_markdown_v2("Настройка фото-викторины")
        hints_status = "Вкл" if hints_enabled else "Выкл"
        status_text = (
            f"⚙️ *{title_text}*\n\n"
            f"🔢 {escape_markdown_v2('Количество вопросов:')} `{escape_markdown_v2(str(question_count))}`\n"
            f"⏰ {escape_markdown_v2('Время ответа:')} `{escape_markdown_v2(str(time_limit))} сек`\n"
            f"💡 {escape_markdown_v2('Подсказки:')} `{escape_markdown_v2(hints_status)}`\n\n"
            f"{escape_markdown_v2('Выберите параметр или запустите.')}"
        )

        markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔢 Количество вопросов",
                        callback_data=CB_PQCFG_QUESTIONS,
                    ),
                    InlineKeyboardButton(
                        f"⏰ Время ответа: {time_limit} сек",
                        callback_data=CB_PQCFG_TIME,
                    ),
                ],
                [
                    InlineKeyboardButton(
                        f"💡 Подсказки: {'Вкл' if hints_enabled else 'Выкл'}",
                        callback_data=CB_PQCFG_HINTS,
                    )
                ],
                [
                    InlineKeyboardButton(
                        "▶️ Запустить фото-викторину",
                        callback_data=CB_PQCFG_START,
                    )
                ],
                [
                    InlineKeyboardButton(
                        "❌ Отмена",
                        callback_data=CB_PQCFG_CANCEL,
                    )
                ],
            ]
        )

        if await self._edit_cfg_view(context, status_text, markup):
            return

        existing_message_id = context.chat_data.get(PHOTO_CFG_MENU_MSG_KEY)
        cfg_chat_id = cfg.get("chat_id")
        if existing_message_id and cfg_chat_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=cfg_chat_id,
                    message_id=existing_message_id,
                    text=status_text,
                    reply_markup=markup,
                    parse_mode="MarkdownV2",
                )
                return
            except BadRequest as e_br:
                # Если сообщение не изменилось - это нормальная ситуация
                if "Message is not modified" not in str(e_br).lower():
                    logger.debug(f"Ошибка BadRequest при редактировании сообщения фото-викторины: {e_br}")
                return
            except Exception:
                pass

        target_message: Optional[Message] = None
        if isinstance(update_or_query, CallbackQuery) and update_or_query.message:
            target_message = update_or_query.message
        elif isinstance(update_or_query, Update) and update_or_query.message:
            target_message = update_or_query.message

        if target_message:
            try:
                sent = await safe_send_message(
                    bot=context.bot,
                    chat_id=target_message.chat_id,
                    text=status_text,
                    reply_markup=markup,
                    reply_to_message_id=target_message.message_id,
                    parse_mode="MarkdownV2",
                )
                context.chat_data[PHOTO_CFG_MENU_MSG_KEY] = sent.message_id
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения конфигурации фото-квиза: {e}", exc_info=True)
        else:
            chat_id = cfg_chat_id
            if chat_id:
                try:
                    sent = await safe_send_message(
                        bot=context.bot,
                        chat_id=chat_id,
                        text=status_text,
                        reply_markup=markup,
                        parse_mode="MarkdownV2",
                    )
                    context.chat_data[PHOTO_CFG_MENU_MSG_KEY] = sent.message_id
                except Exception as e:
                    logger.error(f"Ошибка отправки сообщения конфигурации фото-квиза: {e}", exc_info=True)

    async def _cleanup_cfg_message(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        message: Optional[Message] = None,
    ):
        cfg = context.chat_data.get(PHOTO_CFG_STORE_KEY, {})
        chat_id = cfg.get("chat_id")
        message_id = context.chat_data.get(PHOTO_CFG_MENU_MSG_KEY)

        if message and not message_id:
            message_id = message.message_id
            chat_id = message.chat_id

        if chat_id and message_id:
            try:
                await context.bot.delete_message(chat_id, message_id)
            except Exception as e:
                logger.debug(f"Не удалось удалить сообщение меню фото-викторины: {e}")

        context.chat_data.pop(PHOTO_CFG_MENU_MSG_KEY, None)

    async def _show_question_count_menu(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
        cfg = context.chat_data.get(PHOTO_CFG_STORE_KEY)
        if not cfg:
            await query.answer("Настройка устарела.", show_alert=True)
            return

        current_count = cfg.get("question_count") or DEFAULT_QUESTION_COUNT
        step_options = [1, 3, 5, 7, 10]
        buttons = []
        for val in step_options:
            if QUESTION_COUNT_MIN <= val <= QUESTION_COUNT_MAX:
                marker = "✅" if val == current_count else "☑️"
                buttons.append(
                    [
                        InlineKeyboardButton(
                            f"{marker} {val}",
                            callback_data=f"{CB_PQCFG_QCOUNT_VALUE}:{val}",
                        )
                    ]
                )

        buttons.append(
            [
                InlineKeyboardButton(
                    "✏️ Ввести число",
                    callback_data=f"{CB_PQCFG_QCOUNT_VALUE}:manual",
                )
            ]
        )
        buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data=CB_PQCFG_NOOP)])

        text = escape_markdown_v2(
            f"🔢 Выберите количество вопросов (от {QUESTION_COUNT_MIN} до {QUESTION_COUNT_MAX}):"
        )
        markup = InlineKeyboardMarkup(buttons)

        if not await self._edit_cfg_view(context, text, markup):
            if query.message:
                sent = await query.message.reply_text(
                    text=text,
                    reply_markup=markup,
                    parse_mode="MarkdownV2",
                )
                context.chat_data[PHOTO_CFG_MENU_MSG_KEY] = sent.message_id
        await query.answer()

    async def _prompt_manual_question_count(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
        cfg = context.chat_data.get(PHOTO_CFG_STORE_KEY)
        if not cfg:
            await query.answer("Настройка устарела.", show_alert=True)
            return

        prompt_text = escape_markdown_v2(
            f"Введите количество вопросов (от {QUESTION_COUNT_MIN} до {QUESTION_COUNT_MAX}):"
        )
        back_markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Назад", callback_data=CB_PQCFG_QUESTIONS)]]
        )

        if not await self._edit_cfg_view(context, prompt_text, back_markup):
            if query.message:
                sent = await query.message.reply_text(
                    text=prompt_text,
                    reply_markup=back_markup,
                    parse_mode="MarkdownV2",
                )
                context.chat_data[PHOTO_CFG_MENU_MSG_KEY] = sent.message_id
        await query.answer()

    async def _handle_manual_question_count_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        cfg = context.chat_data.get(PHOTO_CFG_STORE_KEY)
        if not cfg:
            await update.message.reply_text(escape_markdown_v2("⚠️ Настройка устарела. Начните заново командой /photo_quiz."))
            return ConversationHandler.END

        text = (update.message.text or "").strip()
        if not text.isdigit():
            await update.message.reply_text(
                escape_markdown_v2(f"Пожалуйста, введите число от {QUESTION_COUNT_MIN} до {QUESTION_COUNT_MAX}.")
            )
            return PHOTO_CFG_QCOUNT_INPUT

        value = int(text)
        if not (QUESTION_COUNT_MIN <= value <= QUESTION_COUNT_MAX):
            await update.message.reply_text(
                escape_markdown_v2(f"Значение должно быть от {QUESTION_COUNT_MIN} до {QUESTION_COUNT_MAX}. Попробуйте еще раз.")
            )
            return PHOTO_CFG_QCOUNT_INPUT

        cfg["question_count"] = value
        cfg.pop("awaiting_qcount_input", None)
        context.chat_data[PHOTO_CFG_STORE_KEY] = cfg

        await self._send_photo_quiz_cfg_message(None, context)
        return PHOTO_CFG_OPTIONS

    async def _edit_cfg_view(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        parse_mode: str = "MarkdownV2",
    ) -> bool:
        cfg = context.chat_data.get(PHOTO_CFG_STORE_KEY)
        if not cfg:
            return False

        chat_id = cfg.get("chat_id")
        message_id = context.chat_data.get(PHOTO_CFG_MENU_MSG_KEY)

        if chat_id and message_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                )
                return True
            except BadRequest as e_br:
                # Если сообщение не изменилось - это нормальная ситуация (например, двойной клик)
                if "Message is not modified" not in str(e_br).lower():
                    logger.debug(f"Ошибка BadRequest при редактировании меню фото-викторины: {e_br}")
                return True  # Считаем успешным, так как сообщение уже имеет нужное содержимое
            except Exception as e:
                logger.debug(f"Не удалось отредактировать сообщение меню фото-викторины: {e}")
        return False

    def get_handlers(self) -> list:
        cancel_handler = CommandHandler("cancel", self.cancel_photo_quiz_command)
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("photo_quiz", self.photo_quiz_command)],
            states={
                PHOTO_CFG_OPTIONS: [
                    CallbackQueryHandler(
                        self.handle_photo_quiz_callback, pattern=f"^{CB_PQCFG_PREFIX}"
                    ),
                ],
                PHOTO_CFG_QCOUNT_INPUT: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND, self._handle_manual_question_count_input
                    ),
                    CallbackQueryHandler(
                        self.handle_photo_quiz_callback, pattern=f"^{CB_PQCFG_PREFIX}"
                    ),
                ],
            },
            fallbacks=[cancel_handler],
            per_chat=True,
            per_user=True,
            name="photo_quiz_setup_conv",
            persistent=True,
            allow_reentry=True,
        )

        return [
            conv_handler,
            CommandHandler("stop_photo_quiz", self.stop_photo_quiz_command),
            CommandHandler("photo_quiz_help", self.photo_quiz_help_command),
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_photo_quiz_message),
        ]
