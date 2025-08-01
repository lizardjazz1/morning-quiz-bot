#handlers/cleanup_handler.py
import logging
from datetime import timedelta
from telegram.ext import ContextTypes, JobQueue
from telegram import Update
# from telegram.constants import ParseMode # ParseMode не используется в этом файле напрямую
# from telegram.error import TelegramError # TelegramError не используется
# from html import escape # html.escape не используется

# Чтобы избежать циклических импортов и для явности, BotState лучше получать из context.bot_data
# from state import BotState # Можно раскомментировать, если используется для тайп-хинтинга напрямую

logger = logging.getLogger(__name__)

async def cleanup_old_messages_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Запуск задачи очистки старых сообщений...")

    # Предполагаем, что экземпляр BotState хранится в context.bot_data['bot_state']
    bot_state = context.bot_data.get('bot_state')
    if not bot_state:
        logger.error("BotState не найден в context.bot_data. Задача очистки не может быть выполнена.")
        return

    # Убедимся, что атрибут существует и является словарем
    if not hasattr(bot_state, 'generic_messages_to_delete') or \
       not isinstance(bot_state.generic_messages_to_delete, dict):
        logger.warning("Атрибут generic_messages_to_delete отсутствует или имеет неверный тип в BotState. Пропуск задачи.")
        return

    # bot_state.generic_messages_to_delete: Dict[int, Set[int]]
    # где int - chat_id, Set[int] - message_ids

    chats_to_remove_entry_for = [] # Список ID чатов, для которых запись в словаре стала пустой

    # Итерируемся по копии ключей словаря, чтобы безопасно удалять элементы из него
    for chat_id, message_ids_set in list(bot_state.generic_messages_to_delete.items()):
        if not message_ids_set: # Если для чата уже пустой сет, помечаем на удаление из словаря
            chats_to_remove_entry_for.append(chat_id)
            continue

        processed_message_ids = set() # Сообщения, которые были обработаны (удалены или ошибка типа "не найдено")

        # Итерируемся по копии сета, чтобы безопасно удалять элементы из оригинального сета
        for msg_id in list(message_ids_set):
            try:
                # Здесь можно добавить логику проверки "времени жизни" сообщения, если это необходимо.
                # Например, если сообщения хранятся с временными метками и удаляются только по истечении N часов.
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                logger.debug(f"Удалено старое сообщение {msg_id} из чата {chat_id}")
                processed_message_ids.add(msg_id)
            except Exception as e:
                error_str = str(e).lower()
                # Распространенные ошибки, указывающие, что сообщение уже удалено или не может быть удалено
                if "message to delete not found" in error_str or \
                   "message can't be deleted" in error_str or \
                   "message_id_invalid" in error_str or \
                   "message not found" in error_str or \
                   "chat not found" in error_str: # Если чат удален/бот кикнут
                    logger.warning(f"Сообщение {msg_id} в чате {chat_id} не найдено/не может быть удалено (или чат не найден): {e}. Удаление из списка отслеживания.")
                    processed_message_ids.add(msg_id)
                else:
                    # Другие ошибки (например, временные проблемы с сетью) - оставляем сообщение для следующей попытки
                    logger.error(f"Не удалось удалить сообщение {msg_id} из чата {chat_id}: {e}")

        # Удаляем обработанные ID из сета в BotState
        for m_id in processed_message_ids:
            message_ids_set.discard(m_id)

        # Если после обработки сет сообщений для чата стал пустым, помечаем на удаление из словаря
        if not message_ids_set:
             chats_to_remove_entry_for.append(chat_id)

    # Удаляем записи для чатов, у которых не осталось сообщений для удаления
    for chat_id_to_remove in chats_to_remove_entry_for:
        if chat_id_to_remove in bot_state.generic_messages_to_delete:
            del bot_state.generic_messages_to_delete[chat_id_to_remove]
            logger.debug(f"Удалена запись для чата {chat_id_to_remove} из generic_messages_to_delete (список сообщений пуст).")

    logger.info("Задача очистки старых сообщений завершена.")

def schedule_cleanup_job(job_queue: JobQueue) -> None:
    """Планирует периодическую задачу очистки сообщений."""
    interval_hours = 6  # Интервал запуска задачи (например, каждые 6 часов)
    first_run_delay_seconds = 60  # Задержка перед первым запуском после старта бота (в секундах)

    job_name = "periodic_message_cleanup" # Уникальное имя для задачи

    # Удаляем старую задачу с таким же именем, если она существует (на случай перезапуска)
    current_jobs = job_queue.get_jobs_by_name(job_name)
    if current_jobs:
        for job in current_jobs:
            job.schedule_removal()
        logger.info(f"Удалена существующая задача очистки сообщений '{job_name}'.")

    job_queue.run_repeating(
        cleanup_old_messages_job,
        interval=timedelta(hours=interval_hours),
        first=timedelta(seconds=first_run_delay_seconds),
        name=job_name
    )
    logger.info(f"Задача очистки сообщений '{job_name}' запланирована с интервалом {interval_hours} часов (первый запуск через {first_run_delay_seconds} сек).")

# Функция cleanup_command была здесь, но она не интегрирована в классовую структуру обработчиков
# и не зарегистрирована в bot.py. Для ее использования необходимо:
# 1. Переместить ее в соответствующий класс обработчиков (например, CommonHandlers или новый AdminHandlers).
# 2. Добавить команду "cleanup" (или как она будет называться) в AppConfig и quiz_config.json.
# 3. Зарегистрировать CommandHandler для этой команды в bot.py.
# 4. Добавить описание команды в set_my_commands в bot.py.
# Поскольку текущая задача - исправить существующий код с минимальными изменениями структуры,
# я оставляю эту функцию здесь с комментарием. Если она вам нужна, потребуется ее интеграция.
# async def cleanup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
#     if not update.effective_chat or not update.effective_user:
#         return
#
#     chat_id = update.effective_chat.id
#     user_id = update.effective_user.id
#
#     # Проверяем права администратора
#     # Для этого utils.is_user_admin_in_update(update, context) можно использовать
#     # или context.bot.get_chat_member(...) как здесь
#     chat_member = await context.bot.get_chat_member(chat_id, user_id)
#     if chat_member.status not in ['creator', 'administrator']:
#         await update.message.reply_text(
#             escape_markdown_v2("У вас нет прав для выполнения этой команды. Требуются права администратора."),
#             parse_mode=ParseMode.MARKDOWN_V2 # ParseMode должен быть импортирован
#         )
#         return
#
#     # Получаем количество сообщений для удаления
#     args = context.args
#     if not args:
#         await update.message.reply_text(
#             escape_markdown_v2("Укажите количество сообщений для удаления. Например: `/cleanup 10`"),
#             parse_mode=ParseMode.MARKDOWN_V2 # ParseMode должен быть импортирован
#         )
#         return
#
#     try:
#         count = int(args[0])
#         if count <= 0 or count > 100: # Добавим ограничение на максимальное количество
#             raise ValueError("Count must be positive and not too large")
#     except ValueError:
#         await update.message.reply_text(
#             escape_markdown_v2("Пожалуйста, укажите корректное положительное число сообщений (1-100) для удаления."),
#             parse_mode=ParseMode.MARKDOWN_V2 # ParseMode должен быть импортирован
#         )
#         return
#
#     # Удаляем сообщения (get_chat_history более не рекомендуется для этого, используйте get_messages)
#     # Однако, для простоты оставим get_chat_history, но он может быть медленным.
#     # Telegram Bot API не предоставляет прямого способа массового удаления сообщений ботом,
#     # кроме как удаление по одному.
#     # Также, бот может удалять только свои сообщения или сообщения админов (если у бота есть права админа).
#     # И сообщения не старше 48 часов (кроме своих).
#
#     deleted_count = 0
#     # ВНИМАНИЕ: get_chat_history может быть неэффективным.
#     # Вместо него можно использовать context.bot.get_messages, но это требует знания message_ids.
#     # Либо, если нужно удалить последние N сообщений, get_chat_history - один из путей,
#     # но с ограничениями API по удалению.
#     message_ids_to_delete = []
#     async for message in context.bot.get_chat_history(chat_id, limit=count + 1): # +1 чтобы пропустить команду /cleanup
#         if message.message_id == update.message.message_id: # Пропускаем само сообщение с командой
#             continue
#         message_ids_to_delete.append(message.message_id)
#         if len(message_ids_to_delete) >= count:
#             break
#
#     for msg_id_to_del in message_ids_to_delete:
#         try:
#             await context.bot.delete_message(chat_id, msg_id_to_del)
#             deleted_count += 1
#         except Exception as e:
#             logger.error(f"Error deleting message {msg_id_to_del}: {e}")
#
#     # Отправляем отчет
#     # utils.escape_markdown_v2 должен быть импортирован, если используется
#     from utils import escape_markdown_v2 # Предполагая, что этот файл находится в той же директории или utils в sys.path
#     await update.message.reply_text(
#         f"Удалено {escape_markdown_v2(str(deleted_count))} сообщений.",
#         parse_mode=ParseMode.MARKDOWN_V2 # ParseMode должен быть импортирован
#     )
