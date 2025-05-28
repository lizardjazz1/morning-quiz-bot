#handlers/cleanup_handler.py
import logging
from datetime import timedelta
from telegram.ext import ContextTypes, JobQueue

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

