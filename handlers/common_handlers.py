#handlers/common_handlers.py
import logging
import asyncio
from typing import List, Optional, TYPE_CHECKING

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, ConversationHandler # ИСПРАВЛЕНО: Добавлен ConversationHandler
from telegram.constants import ParseMode

if TYPE_CHECKING:
    from app_config import AppConfig
    from state import BotState

from utils import escape_markdown_v2, md, bold, italic, code
from modules.category_manager import CategoryManager
import time

logger = logging.getLogger(__name__)

class CommonHandlers:
    def __init__(self, app_config: 'AppConfig', category_manager: CategoryManager, bot_state: 'BotState'):
        self.app_config = app_config
        self.category_manager = category_manager
        self.bot_state = bot_state # bot_state сохраняется, но не используется методами этого класса

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.message:
            return

        user = update.effective_user
        welcome_text = (
            f"Привет, {bold(user.first_name)}\\! Я бот для проведения викторин\\.\n\n"
            f"{md.section_header('Быстрые действия:', '🎯')}\n"
            f"• 🎮 Начать викторину\n"
            f"• 📊 Мои очки\n"
            f"• 🏆 Глобальный рейтинг\n"
            f"• ⚙️ Настройки\n"
            f"• ❓ Помощь\n\n"
            f"{md.section_header('Все команды:', '📋')}\n"
            f"{md.command_help(self.app_config.commands.quiz, 'начать викторину')}\n"
            f"{md.command_help(self.app_config.commands.mystats, 'моя статистика')}\n"
            f"{md.command_help(self.app_config.commands.top, 'рейтинг чата')}\n"
            f"{md.command_help(self.app_config.commands.global_top, 'глобальный рейтинг')}\n"
            f"{md.command_help(self.app_config.commands.categories, 'доступные категории')}\n"
            f"{md.command_help(self.app_config.commands.help, 'показать эту справку')}\n\n"
            f"{md.section_header('Для администраторов:', '💡')}\n"
            f"• ⚙️ Настройки чата: {code(f'/{self.app_config.commands.admin_settings}')}\n"
            f"• 🛑 Остановить викторину: {code(f'/{self.app_config.commands.stop_quiz}')}"
        )
        try:
            # Создаем inline клавиатуру для быстрого доступа
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton

            keyboard = [
                [
                    InlineKeyboardButton("🎮 Начать викторину", callback_data="start_quiz"),
                    InlineKeyboardButton("📊 Мои очки", callback_data="start_mystats")
                ],
                [
                    InlineKeyboardButton("🏆 Глобальный рейтинг", callback_data="start_global_top"),
                    InlineKeyboardButton("⚙️ Настройки", callback_data="start_settings")
                ],
                [
                    InlineKeyboardButton("❓ Помощь", callback_data="start_help"),
                    InlineKeyboardButton("📚 Категории", callback_data="start_categories")
                ]
            ]

            reply_markup = InlineKeyboardMarkup(keyboard)

            sent_msg = await update.message.reply_text(
                welcome_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            # Добавляем сообщение в список для удаления
            bot_state = context.bot_data.get('bot_state')
            if bot_state:
                bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
            
            # Обновляем метаданные чата (название, тип) в фоновом режиме
            data_manager = context.bot_data.get('data_manager')
            if data_manager:
                asyncio.create_task(data_manager.update_chat_metadata(update.effective_chat.id, context.bot))
        except Exception as e:
            logger.error(f"Ошибка при отправке start_command: {e}")

    async def start_menu_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Обработчик callback-запросов от inline кнопок в главном меню /start
        """
        query = update.callback_query
        if not query or not query.data:
            return

        try:
            callback_data = query.data
            logger.info(f"🔘 START MENU: Получен callback '{callback_data}' от пользователя {query.from_user.id if query.from_user else 'Unknown'}")
            
            # ВАЖНО: Отвечаем на callback СРАЗУ, до всех обработок
            try:
                await query.answer(timeout=10)  # Подтверждаем получение callback с таймаутом
            except Exception as e:
                logger.warning(f"Не удалось ответить на callback сразу: {e}")

            chat_id = query.message.chat_id
            user = query.from_user

            # Получаем обработчики заранее
            rating_handlers = context.bot_data.get('rating_handlers')

            if callback_data == "start_quiz":
                # Имитируем команду /quiz
                fake_message = type('FakeMessage', (), {
                    'chat_id': chat_id,
                    'from_user': user,
                    'text': f"/{self.app_config.commands.quiz}",
                    'message_id': query.message.message_id,
                })()

                fake_update = type('FakeUpdate', (), {
                    'message': fake_message,
                    'effective_chat': query.message.chat,
                    'effective_user': user
                })()

                # Вызываем обработчик викторины
                quiz_manager = context.bot_data.get('quiz_manager')
                if quiz_manager:
                    await quiz_manager.quiz_command_entry(fake_update, context)

            elif callback_data == "start_mystats":
                # Имитируем команду /mystats
                fake_message = type('FakeMessage', (), {
                    'chat_id': chat_id,
                    'from_user': user,
                    'text': f"/{self.app_config.commands.mystats}",
                    'message_id': query.message.message_id,
                })()

                fake_update = type('FakeUpdate', (), {
                    'message': fake_message,
                    'effective_chat': query.message.chat,
                    'effective_user': user
                })()

                # Вызываем обработчик статистики
                if rating_handlers:
                    await rating_handlers.mystats_command(fake_update, context)

            elif callback_data == "start_global_top":
                # Имитируем команду /globaltop
                fake_update = type('FakeUpdate', (), {
                    'message': type('FakeMessage', (), {
                        'chat_id': chat_id,
                        'from_user': user,
                        'text': f"/{self.app_config.commands.global_top}"
                    })(),
                    'effective_chat': query.message.chat,
                    'effective_user': user
                })()

                # Вызываем обработчик глобального рейтинга
                if rating_handlers:
                    await rating_handlers.globaltop_command(fake_update, context)

            elif callback_data == "start_settings":
                # Вызываем команду settings
                fake_update = type('FakeUpdate', (), {
                    'message': type('FakeMessage', (), {
                        'chat_id': chat_id,
                        'from_user': user,
                        'text': f"/{self.app_config.commands.mystats}"
                    })(),
                    'effective_chat': query.message.chat,
                    'effective_user': user
                })()

                await self.mystats_command(fake_update, context)

            elif callback_data == "start_help":
                # Вызываем команду help
                # Создаем более совместимый fake update
                async def fake_reply_text(*args, **kwargs):
                    # args[0] может быть 'self' если вызывается как метод, или text если как функция
                    text = args[-1] if len(args) > 0 else kwargs.get('text', '')
                    return await query.message.reply_text(text, **kwargs)

                fake_message = type('FakeMessage', (), {
                    'chat_id': chat_id,
                    'from_user': user,
                    'text': f"/{self.app_config.commands.help}",
                    'message_id': query.message.message_id,  # Используем реальный message_id
                    'reply_text': fake_reply_text
                })()

                fake_update = type('FakeUpdate', (), {
                    'message': fake_message,
                    'effective_chat': query.message.chat,
                    'effective_user': user
                })()

                await self.help_command(fake_update, context)

            elif callback_data == "start_categories":
                # Вызываем команду categories
                class FakeMessage:
                    def __init__(self, real_message, user, text):
                        self.chat_id = real_message.chat_id
                        self.from_user = user
                        self.text = text
                        self.message_id = real_message.message_id
                        self.chat = real_message.chat
                        self._real_message = real_message
                    
                    async def reply_text(self, *args, **kwargs):
                        return await self._real_message.reply_text(*args, **kwargs)

                fake_message = FakeMessage(query.message, user, f"/{self.app_config.commands.categories}")
                
                fake_update = type('FakeUpdate', (), {
                    'message': fake_message,
                    'effective_chat': query.message.chat,
                    'effective_user': user
                })()

                await self.categories_command(fake_update, context)

            # Обновляем сообщение, чтобы убрать кнопки (опционально)
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                # Игнорируем ошибку, если не удалось обновить разметку
                pass

        except Exception as e:
            logger.error(f"Ошибка при обработке callback от start меню: {e}")
            try:
                await query.answer("❌ Произошла ошибка. Попробуйте команду напрямую.")
            except Exception:
                pass

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        
        import time
        start_time = time.time()
        logger.info(f"Команда /help получена в {start_time:.3f}")

        help_full_text = (
            f"{md.section_header('Справка по командам бота:', '📖')}\n\n"
            f"{md.section_header('Викторина', '📝')}\n"
            f"{md.command_help(self.app_config.commands.quiz, 'начать викторину (можно с параметрами)')}\n"
            f"{bold('Примеры:')}\n"
            f"{code(f'/{self.app_config.commands.quiz} 5')} \\- {escape_markdown_v2('викторина из 5 вопросов')}\n"
            f"{code(f'/{self.app_config.commands.quiz} Название Категории')} \\- {escape_markdown_v2('викторина по категории')}\n"
            f"{code(f'/{self.app_config.commands.quiz} 10 Название Категории')} \\- {escape_markdown_v2('комбинированный вариант')}\n"
            f"{code(f'/{self.app_config.commands.quiz} announce')} \\- {escape_markdown_v2('викторина с анонсом')}\n"
            f"{md.command_help(self.app_config.commands.stop_quiz, 'остановить текущую викторину (админ/инициатор)')}\n\n"

            f"{md.section_header('Категории', '📚')}\n"
            f"{md.command_help(self.app_config.commands.categories, 'показать список всех категорий вопросов с статистикой использования')}\n\n"

            f"{md.section_header('Рейтинг и Статистика', '📊')}\n"
            f"{md.command_help(self.app_config.commands.top, 'показать рейтинг текущего чата')}\n"
            f"{md.command_help(self.app_config.commands.global_top, 'показать глобальный рейтинг')}\n"
            f"{md.command_help(self.app_config.commands.mystats, 'показать вашу личную статистику')}\n"
            f"{md.command_help(getattr(self.app_config.commands, 'chat_stats', 'chat_stats'), 'показать статистику викторин в чате')}\n\n"

            f"{md.section_header('Настройки (для администраторов чата)', '⚙️')}\n"
            f"{md.command_help(getattr(self.app_config.commands, 'admin_settings', 'adminsettings'), 'открыть меню настроек чата')}\n"
            f"{md.command_help(getattr(self.app_config.commands, 'view_chat_config', 'viewchatconfig'), 'посмотреть текущие настройки чата')}\n\n"

            f"{md.section_header('Общие', '❓')}\n"
            f"{md.command_help(self.app_config.commands.help, 'показать эту справку')}\n"
            f"{md.command_help(self.app_config.commands.start, 'начать работу с ботом')}\n"
            f"{md.command_help(self.app_config.commands.cancel, 'отмена текущего диалога (например, настройки)')}\n\n"
            f"{md.section_header('Поддержка', '💬')}\n"
            f"{escape_markdown_v2(f'По всем вопросам обращайтесь к {self.app_config.support_contact}').replace('@', '\\@')}"
        )
        try:
            from modules.telegram_utils import safe_send_message
            sent_msg = await safe_send_message(
                context.bot,
                update.effective_chat.id,
                help_full_text,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            # Добавляем сообщение в список для удаления
            bot_state = context.bot_data.get('bot_state')
            if bot_state:
                bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
            
            elapsed = time.time() - start_time
            logger.info(f"Команда /help обработана за {elapsed:.3f}с (подготовка текста + отправка)")
        except Exception as e:
            logger.error(f"Ошибка при отправке help_command: {e}", exc_info=True)
            elapsed = time.time() - start_time
            logger.error(f"Команда /help завершилась с ошибкой за {elapsed:.3f}с")

    async def categories_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message: return
        
        chat_id = update.effective_chat.id if update.effective_chat else None
        
        # Получаем список категорий с количеством вопросов и статистикой использования в чате
        categories_data = self.category_manager.get_all_category_names(with_question_counts=True, chat_id=chat_id)

        if not categories_data:
            try:
                from modules.telegram_utils import safe_send_message
                sent_msg = await safe_send_message(context.bot, update.effective_chat.id, escape_markdown_v2("Категории вопросов еще не загружены или отсутствуют."), parse_mode=ParseMode.MARKDOWN_V2)
                # Добавляем сообщение в список для удаления
                bot_state = context.bot_data.get('bot_state')
                if bot_state:
                    bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
            except Exception as e:
                 logger.error(f"Ошибка при отправке categories_command (нет категорий): {e}")
            return

        response_lines = [f"*{escape_markdown_v2('📚 Доступные категории вопросов:')}*"]
        for cat_info in sorted(categories_data, key=lambda x: x.get('name', '').lower()):
            cat_name_escaped = escape_markdown_v2(cat_info.get('name', 'N/A'))
            q_count = cat_info.get('count', 0)
            chat_usage = cat_info.get('chat_usage', 0)
            global_usage = cat_info.get('global_usage', 0)
            
            # Формируем строку с количеством вопросов и статистикой использования
            if chat_usage > 0:
                response_lines.append(f"{escape_markdown_v2('-')} `{cat_name_escaped}` {escape_markdown_v2(f'({q_count}) (в чате: {chat_usage}, всего: {global_usage})')}")
            else:
                response_lines.append(f"{escape_markdown_v2('-')} `{cat_name_escaped}` {escape_markdown_v2(f'({q_count}) (всего: {global_usage})')}")

        full_message = "\n".join(response_lines)

        try:
            from modules.telegram_utils import safe_send_message
            if len(full_message) > 4096:
                logger.warning("Список категорий слишком длинный, будет отправлен частями.")
                part_buffer = response_lines[0] + "\n"
                for line_idx, line_content in enumerate(response_lines[1:], 1):
                    if len(part_buffer) + len(line_content) + 1 > 4000:
                        sent_msg = await safe_send_message(context.bot, update.effective_chat.id, part_buffer.strip(), parse_mode=ParseMode.MARKDOWN_V2)
                        # Добавляем сообщение в список для удаления
                        bot_state = context.bot_data.get('bot_state')
                        if bot_state:
                            bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
                        part_buffer = line_content
                    else:
                        part_buffer += "\n" + line_content
                if part_buffer.strip():
                    sent_msg = await safe_send_message(context.bot, update.effective_chat.id, part_buffer.strip(), parse_mode=ParseMode.MARKDOWN_V2)
                    # Добавляем сообщение в список для удаления
                    bot_state = context.bot_data.get('bot_state')
                    if bot_state:
                        bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
            else:
                sent_msg = await safe_send_message(context.bot, update.effective_chat.id, full_message, parse_mode=ParseMode.MARKDOWN_V2)
                # Добавляем сообщение в список для удаления
                bot_state = context.bot_data.get('bot_state')
                if bot_state:
                    bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
        except Exception as e:
            logger.error(f"Ошибка при отправке списка категорий: {e}\nТекст сообщения (начало): {full_message[:500]}")
            try:
                sent_msg = await update.message.reply_text(
                    escape_markdown_v2("Произошла ошибка при отображении списка категорий."),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                # Добавляем сообщение в список для удаления
                bot_state = context.bot_data.get('bot_state')
                if bot_state:
                    bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
            except Exception as e_fallback:
                 logger.error(f"Ошибка при отправке fallback-сообщения для categories_command: {e_fallback}")

    async def category_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показывает детальную статистику использования категорий"""
        if not update.message: return
        
        chat_id = update.effective_chat.id if update.effective_chat else None
        
        try:
            # Получаем глобальную статистику
            global_stats = self.category_manager.get_global_category_stats()
            
            if not global_stats:
                sent_msg = await update.message.reply_text(
                    escape_markdown_v2("Статистика использования категорий пока не собрана."),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                # Добавляем сообщение в список для удаления
                bot_state = context.bot_data.get('bot_state')
                if bot_state:
                    bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
                return
            
            # Сортируем по общему количеству использований
            # Поддержка обоих форматов: global_usage (новый) и total_usage (старый)
            sorted_stats = sorted(global_stats.items(),
                                key=lambda x: x[1].get('global_usage', x[1].get('total_usage', 0)),
                                reverse=True)

            response_lines = [f"*{escape_markdown_v2('📊 Глобальная статистика использования категорий:')}*"]

            for category_name, stats in sorted_stats[:20]:  # Показываем топ-20
                cat_name_escaped = escape_markdown_v2(category_name)
                # Поддержка обоих форматов: global_usage (новый) или total_usage (старый)
                total_usage = stats.get('global_usage', stats.get('total_usage', 0))
                chat_count = len(stats.get('chats_used_in', [])) if 'chats_used_in' in stats else stats.get('chat_count', 0)
                last_used = stats.get('last_used', 0)
                
                # Форматируем время последнего использования
                if last_used > 0:
                    time_ago = int(time.time() - last_used)
                    if time_ago < 3600:  # Меньше часа
                        time_str = f"{time_ago // 60} мин назад"
                    elif time_ago < 86400:  # Меньше дня
                        time_str = f"{time_ago // 3600} ч назад"
                    else:
                        time_str = f"{time_ago // 86400} дн назад"
                else:
                    time_str = "никогда"
                
                response_lines.append(
                    f"{escape_markdown_v2('-')} `{cat_name_escaped}`: {escape_markdown_v2(f'{total_usage} использований, {chat_count} чатов, {time_str}')}"
                )
            
            if len(sorted_stats) > 20:
                response_lines.append(f"\n{escape_markdown_v2(f'... и еще {len(sorted_stats) - 20} категорий')}")
            
            # Добавляем статистику по чату, если указан
            if chat_id:
                chat_stats = self.category_manager.get_chat_category_stats(chat_id)
                if chat_stats:
                    response_lines.append(f"\n*{escape_markdown_v2(f'📱 Статистика в этом чате ({chat_id}):')}*")

                    # Функция для получения chat_usage с поддержкой обоих форматов
                    def get_chat_usage_value(stats_data, chat_id_str):
                        chat_usage_data = stats_data.get('chat_usage', 0)
                        if isinstance(chat_usage_data, dict):
                            # Глобальный формат: словарь с ID чатов
                            return chat_usage_data.get(chat_id_str, 0)
                        elif isinstance(chat_usage_data, (int, float)):
                            # Формат файла чата: просто число использований в этом чате
                            return int(chat_usage_data)
                        return 0

                    # Сортируем по использованию в чате
                    sorted_chat_stats = sorted(chat_stats.items(),
                                             key=lambda x: get_chat_usage_value(x[1], str(chat_id)),
                                             reverse=True)

                    for category_name, stats in sorted_chat_stats[:10]:  # Показываем топ-10
                        cat_name_escaped = escape_markdown_v2(category_name)
                        chat_usage = get_chat_usage_value(stats, str(chat_id))

                        # Берём глобальное использование из глобальной статистики
                        global_usage = 0
                        if category_name in global_stats:
                            global_usage = global_stats[category_name].get('global_usage', global_stats[category_name].get('total_usage', 0))

                        response_lines.append(
                            f"{escape_markdown_v2('-')} `{cat_name_escaped}`: {escape_markdown_v2(f'{chat_usage} использований (глобально: {global_usage})')}"
                        )
            
            full_message = "\n".join(response_lines)
            
            # Отправляем сообщение
            sent_msg = await update.message.reply_text(full_message, parse_mode=ParseMode.MARKDOWN_V2)
            
            # Добавляем сообщение в список для удаления
            bot_state = context.bot_data.get('bot_state')
            if bot_state:
                bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
                
        except Exception as e:
            logger.error(f"Ошибка при отправке статистики категорий: {e}")
            try:
                sent_msg = await update.message.reply_text(
                    escape_markdown_v2("Произошла ошибка при получении статистики категорий."),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                # Добавляем сообщение в список для удаления
                bot_state = context.bot_data.get('bot_state')
                if bot_state:
                    bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
            except Exception as e_fallback:
                logger.error(f"Ошибка при отправке fallback-сообщения для category_stats_command: {e_fallback}")

    async def chatcategories_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показывает очередь категорий с их весами для текущего чата"""
        if not update.message: return

        chat_id = update.effective_chat.id if update.effective_chat else None

        try:
            # Получаем веса всех категорий для этого чата
            category_weights = self.category_manager.get_category_weights_for_chat(chat_id)

            if not category_weights:
                sent_msg = await update.message.reply_text(
                    escape_markdown_v2("Категории вопросов еще не загружены или отсутствуют."),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                # Добавляем сообщение в список для удаления
                bot_state = context.bot_data.get('bot_state')
                if bot_state:
                    bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
                return

            # Формируем заголовок
            header = "🎲 Очередность выбора категорий для викторин:"
            response_lines = [f"*{escape_markdown_v2(header)}*"]
            response_lines.append("")  # Пустая строка

            # Показываем топ-20 категорий (очередность выбора)
            for i, cat_info in enumerate(category_weights[:20], 1):
                name = cat_info['name']
                weight = cat_info['weight']

                # Простая нумерация вместо эмодзи
                position = f"{i:2d}."

                # Форматируем строку
                name_escaped = escape_markdown_v2(name)
                weight_str = f"{weight:.1f}"

                # Показываем только имя и вес
                line = f"{escape_markdown_v2(position)} {escape_markdown_v2('`')}{name_escaped}{escape_markdown_v2('`')} {escape_markdown_v2('| вес:')} {escape_markdown_v2(weight_str)}"
                response_lines.append(line)

            # Добавляем краткое объяснение
            response_lines.append("")
            explanation_header = "💡 Чем выше вес - тем приоритетнее выбор категории"
            response_lines.append(f"*{escape_markdown_v2(explanation_header)}*")
            response_lines.append(escape_markdown_v2("• Вес учитывает частоту использования и давность"))
            response_lines.append(escape_markdown_v2("• Новые категории получают бонус"))
            response_lines.append(escape_markdown_v2("• Часто используемые получают штраф"))

            full_message = "\n".join(response_lines)

            # Отправляем сообщение, разбивая на части если слишком длинное
            try:
                if len(full_message) > 4096:
                    logger.warning("Список категорий с весами слишком длинный, будет отправлен частями.")
                    part_buffer = response_lines[0] + "\n" + response_lines[1] + "\n"
                    for line_idx, line_content in enumerate(response_lines[2:], 2):
                        if len(part_buffer) + len(line_content) + 1 > 4000:
                            sent_msg = await update.message.reply_text(part_buffer.strip(), parse_mode=ParseMode.MARKDOWN_V2)
                            # Добавляем сообщение в список для удаления
                            bot_state = context.bot_data.get('bot_state')
                            if bot_state:
                                bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
                            part_buffer = line_content
                        else:
                            part_buffer += "\n" + line_content
                    if part_buffer.strip():
                        sent_msg = await update.message.reply_text(part_buffer.strip(), parse_mode=ParseMode.MARKDOWN_V2)
                        # Добавляем сообщение в список для удаления
                        bot_state = context.bot_data.get('bot_state')
                        if bot_state:
                            bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
                else:
                    sent_msg = await update.message.reply_text(full_message, parse_mode=ParseMode.MARKDOWN_V2)
                    # Добавляем сообщение в список для удаления
                    bot_state = context.bot_data.get('bot_state')
                    if bot_state:
                        bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)

            except Exception as e:
                logger.error(f"Ошибка при отправке списка категорий с весами: {e}")
                try:
                    sent_msg = await update.message.reply_text(
                        escape_markdown_v2("Произошла ошибка при отображении очереди категорий."),
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
                    # Добавляем сообщение в список для удаления
                    bot_state = context.bot_data.get('bot_state')
                    if bot_state:
                        bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
                except Exception as e_fallback:
                    logger.error(f"Ошибка при отправке fallback-сообщения для chatcategories_command: {e_fallback}")

        except Exception as e:
            logger.error(f"Критическая ошибка в chatcategories_command: {e}")
            try:
                await update.message.reply_text("Произошла критическая ошибка при обработке команды.")
            except Exception:
                pass

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
        if not update.message or not update.effective_user or not update.effective_chat:
             return ConversationHandler.END # type: ignore [attr-defined]

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        cancel_message = escape_markdown_v2("Команда отмены получена. Если вы были в диалоге, он должен завершиться.")
        try:
            sent_msg = await update.message.reply_text(cancel_message, parse_mode=ParseMode.MARKDOWN_V2)
            # Добавляем сообщение в список для удаления
            bot_state = context.bot_data.get('bot_state')
            if bot_state:
                bot_state.add_message_for_deletion(update.effective_chat.id, sent_msg.message_id)
        except Exception as e:
            logger.error(f"Ошибка при отправке cancel_command сообщения: {e}")

        logger.info(f"Пользователь {user_id} в чате {chat_id} вызвал /{self.app_config.commands.cancel}.")
        return ConversationHandler.END # type: ignore [attr-defined]



    # ===== СИСТЕМА ОБРАБОТКИ РЕЖИМА ТЕХНИЧЕСКОГО ОБСЛУЖИВАНИЯ =====

    async def maintenance_command_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Обработчик для всех команд в режиме технического обслуживания.
        Отправляет уведомление о том, что бот на обслуживании.
        """
        if not update.message or not update.effective_chat:
            return

        # Получаем data_manager из контекста
        data_manager = context.bot_data.get('data_manager')
        if not data_manager:
            logger.warning("data_manager не найден в bot_data")
            return

        # Проверяем, включен ли режим обслуживания
        if not data_manager.is_maintenance_mode():
            # Если режим обслуживания не включен, пропускаем
            return

        # Исключаем команду maintenance из перехвата
        if update.message.text and update.message.text.startswith('/maintenance'):
            return

        try:
            # Получаем статус обслуживания
            maintenance_status = data_manager.get_maintenance_status()
            reason = maintenance_status.get("reason", "Техническое обслуживание")
            start_time_str = maintenance_status.get("start_time", "")

            # Формируем сообщение
            if start_time_str:
                from datetime import datetime
                try:
                    start_time = datetime.fromisoformat(start_time_str)
                    time_diff = datetime.now() - start_time
                    hours = int(time_diff.total_seconds() // 3600)
                    minutes = int((time_diff.total_seconds() % 3600) // 60)

                    duration_text = ""
                    if hours > 0:
                        duration_text = f"{hours} ч. {minutes} мин."
                    else:
                        duration_text = f"{minutes} мин."

                    message_text = f"""🔧 *БОТ НА ТЕХНИЧЕСКОМ ОБСЛУЖИВАНИИ*

⚠️ *Причина:* {escape_markdown_v2(reason)}
⏱️ *Длительность:* {duration_text}

🤖 Пожалуйста, подождите\\. Бот скоро вернется в строй\\!
📅 Ориентировочное время восстановления: 5\\-15 минут

_Приносим извинения за неудобства\\._"""

                except Exception:
                    # Если не удалось распарсить время
                    message_text = f"""🔧 *БОТ НА ТЕХНИЧЕСКОМ ОБСЛУЖИВАНИИ*

⚠️ *Причина:* {escape_markdown_v2(reason)}

🤖 Пожалуйста, подождите\\. Бот скоро вернется в строй\\!
📅 Ориентировочное время восстановления: 5\\-15 минут

_Приносим извинения за неудобства\\._"""
            else:
                message_text = f"""🔧 *БОТ НА ТЕХНИЧЕСКОМ ОБСЛУЖИВАНИИ*

⚠️ *Причина:* {escape_markdown_v2(reason)}

🤖 Пожалуйста, подождите\\. Бот скоро вернется в строй\\!
📅 Ориентировочное время восстановления: 5\\-15 минут

_Приносим извинения за неудобства\\._"""

            # Отправляем сообщение
            sent_message = await update.message.reply_text(
                message_text,
                parse_mode=ParseMode.MARKDOWN_V2
            )

            # Сохраняем информацию о уведомлении для последующей очистки
            data_manager.add_maintenance_notification(
                update.effective_chat.id,
                sent_message.message_id
            )

            logger.info(f"Отправлено уведомление об обслуживании в чат {update.effective_chat.id}")

        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления об обслуживании: {e}")

    async def cleanup_maintenance_notifications(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Очищает уведомления об обслуживании и отправляет сообщения о готовности.
        Вызывается при запуске бота.
        """
        try:
            # Получаем data_manager
            data_manager = context.bot_data.get('data_manager')
            if not data_manager:
                logger.warning("data_manager не найден при очистке уведомлений")
                return

            # Выключаем режим обслуживания и получаем данные для очистки
            maintenance_data = data_manager.disable_maintenance_mode()

            if not maintenance_data or not maintenance_data.get("chats_notified"):
                logger.info("Нет уведомлений для очистки")
                return

            chats_to_notify = maintenance_data.get("chats_notified", [])
            notification_messages = maintenance_data.get("notification_messages", [])

            logger.info(f"Очистка уведомлений в {len(chats_to_notify)} чатах")

            # Группируем сообщения по чатам для эффективного удаления
            messages_by_chat = {}
            for msg_data in notification_messages:
                chat_id = msg_data.get("chat_id")
                message_id = msg_data.get("message_id")
                if chat_id and message_id:
                    if chat_id not in messages_by_chat:
                        messages_by_chat[chat_id] = []
                    messages_by_chat[chat_id].append(message_id)

            # Удаляем уведомления и отправляем сообщения о готовности
            for chat_id in chats_to_notify:
                try:
                    # Удаляем уведомления об обслуживании
                    if chat_id in messages_by_chat:
                        for message_id in messages_by_chat[chat_id]:
                            try:
                                await context.bot.delete_message(
                                    chat_id=chat_id,
                                    message_id=message_id
                                )
                                logger.debug(f"Удалено уведомление об обслуживании: чат {chat_id}, сообщение {message_id}")
                            except Exception as e:
                                logger.debug(f"Не удалось удалить уведомление: чат {chat_id}, сообщение {message_id}: {e}")

                    # Отправляем сообщение о готовности
                    ready_message = """✅ *БОТ ГОТОВ К РАБОТЕ\\!*

🤖 Все системы функционируют нормально\\.
🎯 Можно продолжать использовать викторины\\!

_Спасибо за ожидание\\!_"""

                    sent_message = await context.bot.send_message(
                        chat_id=chat_id,
                        text=ready_message,
                        parse_mode=ParseMode.MARKDOWN_V2
                    )

                    # Добавляем сообщение о готовности в список для удаления через 5 минут
                    bot_state = context.bot_data.get('bot_state')
                    if bot_state:
                        bot_state.add_message_for_deletion(chat_id, sent_message.message_id)

                        # Планируем удаление через 5 минут
                        from datetime import timedelta
                        from telegram.ext import JobQueue
                        job_queue = context.application.job_queue if hasattr(context, 'application') else None
                        if job_queue:
                            job_name = f"delete_ready_msg_{chat_id}_{sent_message.message_id}"
                            job_queue.run_once(
                                lambda ctx: self._delete_message_job(ctx, chat_id, sent_message.message_id),
                                when=timedelta(minutes=5),
                                name=job_name
                            )

                    logger.info(f"Отправлено сообщение о готовности в чат {chat_id}")

                except Exception as e:
                    logger.error(f"Ошибка при очистке уведомлений в чате {chat_id}: {e}")

            logger.info(f"✅ Очистка уведомлений завершена. Обработано {len(chats_to_notify)} чатов")

        except Exception as e:
            logger.error(f"❌ Ошибка при очистке уведомлений об обслуживании: {e}")

    async def _delete_message_job(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int) -> None:
        """Job для удаления сообщения о готовности через 5 минут"""
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            logger.debug(f"Удалено сообщение о готовности: чат {chat_id}, сообщение {message_id}")
        except Exception as e:
            logger.debug(f"Не удалось удалить сообщение о готовности: {e}")

    def get_maintenance_handlers(self) -> List[CommandHandler]:
        """
        Возвращает обработчики для режима технического обслуживания.
        Эти обработчики имеют более высокий приоритет и перехватывают все команды.
        """
        # Создаем обработчики для всех основных команд
        maintenance_handlers = []

        # Список всех команд, которые нужно перехватывать
        commands_to_intercept = [
            self.app_config.commands.start,
            self.app_config.commands.help,
            self.app_config.commands.quiz,
            self.app_config.commands.top,
            self.app_config.commands.global_top,
            self.app_config.commands.mystats,
            self.app_config.commands.categories,
            self.app_config.commands.category_stats,
            self.app_config.commands.mystats,  # Личная статистика пользователя
            self.app_config.commands.cancel,
            "maintenance",  # Команда управления обслуживанием (исключаем из перехвата)
        ]

        # Создаем обработчики для каждой команды
        for command in commands_to_intercept:
            handler = CommandHandler(command, self.maintenance_command_handler)
            maintenance_handlers.append(handler)

        return maintenance_handlers

    async def maintenance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Команда для управления режимом технического обслуживания.
        Доступна только администраторам бота.
        Использование: /maintenance on/off [причина]
        """
        if not update.message or not update.effective_user or not update.effective_chat:
            return

        # Получаем data_manager
        data_manager = context.bot_data.get('data_manager')
        if not data_manager:
            await update.message.reply_text("❌ Система управления обслуживанием недоступна")
            return

        # КРИТИЧЕСКАЯ КОМАНДА: Только для создателя бота!
        user_id = update.effective_user.id
        developer_id = self.app_config.global_settings.get("developer_notifications", {}).get("developer_user_id")

        if user_id != developer_id:
            await update.message.reply_text(
                escape_markdown_v2("❌ У вас нет прав для выполнения этой команды. Требуются права администратора."),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        args = context.args if context.args else []

        if not args:
            # Показать текущий статус
            is_maintenance = data_manager.is_maintenance_mode()
            status_text = "ВКЛЮЧЕН" if is_maintenance else "ВЫКЛЮЧЕН"

            if is_maintenance:
                maintenance_data = data_manager.get_maintenance_status()
                reason = maintenance_data.get("reason", "Не указана")
                start_time = maintenance_data.get("start_time", "Неизвестно")
                chats_count = len(maintenance_data.get("chats_notified", []))

                response = f"""🔧 *РЕЖИМ ОБСЛУЖИВАНИЯ:* {status_text}

⚠️ *Причина:* {escape_markdown_v2(reason)}
🕒 *Начало:* {start_time}
👥 *Уведомлено чатов:* {chats_count}

*Команды:*
/maintenance off \\- выключить режим обслуживания
/maintenance on [причина] \\- включить с причиной"""
            else:
                response = f"""🔧 *РЕЖИМ ОБСЛУЖИВАНИЯ:* {status_text}

*Команды:*
/maintenance on [причина] \\- включить режим обслуживания
/maintenance off \\- выключить режим обслуживания"""

            await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN_V2)
            return

        action = args[0].lower()

        if action == "on":
            # Включаем режим обслуживания
            reason = " ".join(args[1:]) if len(args) > 1 else "Техническое обслуживание"
            data_manager.enable_maintenance_mode(reason)

            response = f"""✅ *РЕЖИМ ОБСЛУЖИВАНИЯ ВКЛЮЧЕН*

⚠️ *Причина:* {escape_markdown_v2(reason)}
🔄 Бот будет отвечать на все команды уведомлениями об обслуживании

*Выключить:* /maintenance off"""

        elif action == "off":
            # Выключаем режим обслуживания
            if data_manager.is_maintenance_mode():
                maintenance_data = data_manager.disable_maintenance_mode()
                chats_count = len(maintenance_data.get("chats_notified", []))

                response = f"""✅ *РЕЖИМ ОБСЛУЖИВАНИЯ ВЫКЛЮЧЕН*

👥 Было уведомлено чатов: {chats_count}
🔄 Бот вернулся к нормальной работе"""
            else:
                response = "❌ Режим обслуживания уже выключен"
        else:
            response = """❌ *Неверная команда*

*Использование:*
/maintenance on [причина] \\- включить режим обслуживания
/maintenance off \\- выключить режим обслуживания
/maintenance \\- показать статус"""

        await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Пользователь {user_id} выполнил команду maintenance: {action}")

    def get_handlers(self) -> List:
        """Возвращает все обработчики команд и callback-запросов"""
        from telegram.ext import CallbackQueryHandler

        handlers_list = [
            CommandHandler(self.app_config.commands.start, self.start_command),
            CommandHandler(self.app_config.commands.help, self.help_command),
            CommandHandler(self.app_config.commands.categories, self.categories_command),
            CommandHandler(self.app_config.commands.category_stats, self.category_stats_command),
            CommandHandler(self.app_config.commands.chatcategories, self.chatcategories_command),

            CommandHandler(self.app_config.commands.cancel, self.cancel_command),
            CommandHandler("maintenance", self.maintenance_command),  # Команда для управления обслуживанием
            # Обработчик callback-запросов от inline кнопок
            CallbackQueryHandler(self.start_menu_callback, pattern=r"^start_"),
        ]
        return handlers_list

    def get_command_handlers(self) -> List[CommandHandler]:
        """Возвращает только обработчики команд (для обратной совместимости)"""
        handlers_list = [
            CommandHandler(self.app_config.commands.start, self.start_command),
            CommandHandler(self.app_config.commands.help, self.help_command),
            CommandHandler(self.app_config.commands.categories, self.categories_command),
            CommandHandler(self.app_config.commands.category_stats, self.category_stats_command),
            CommandHandler(self.app_config.commands.chatcategories, self.chatcategories_command),

            CommandHandler(self.app_config.commands.cancel, self.cancel_command),
            CommandHandler("maintenance", self.maintenance_command),  # Команда для управления обслуживанием
        ]
        return handlers_list
