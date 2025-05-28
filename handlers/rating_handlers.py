#handlers/rating_handlers.py
import logging
from typing import List, Dict, Any, Optional

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

from app_config import AppConfig
from modules.score_manager import ScoreManager
# from state import BotState # Не используется напрямую, можно закомментировать если нет других причин
from utils import escape_markdown_v2

logger = logging.getLogger(__name__)

class RatingHandlers:
    def __init__(self, app_config: AppConfig, score_manager: ScoreManager):
        self.app_config = app_config
        self.score_manager = score_manager

    async def rating_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE, global_rating: bool) -> None:
        if not update.message or not update.effective_chat:
            return

        chat_id = update.effective_chat.id if not global_rating else None # None for global rating

        top_users = self.score_manager.get_top_users(
            limit=self.app_config.rating_display_limit,
            chat_id=chat_id
        )

        reply_text: str
        if not top_users:
            if global_rating:
                reply_text = "Пока нет данных для глобального рейтинга\\." # ИСПРАВЛЕНО
            else:
                reply_text = "Пока нет данных для рейтинга в этом чате\\." # ИСПРАВЛЕНО
            try:
                await update.message.reply_text(reply_text, parse_mode=ParseMode.MARKDOWN_V2)
            except Exception as e:
                logger.error(f"Ошибка при отправке 'нет рейтинга': {e}. Текст: {reply_text}")
                await update.message.reply_text("Не удалось отобразить рейтинг.", parse_mode=None) # Fallback
            return

        title = "🏆 Топ игроков в этом чате:" if not global_rating else "🌍 Глобальный топ игроков:"
        
        # Предполагаем, что self.score_manager.format_scores УЖЕ возвращает MarkdownV2-совместимую строку
        reply_text = self.score_manager.format_scores(
            scores_list=top_users,
            title=title,
            is_session_score=False
        )
        
        try:
            await update.message.reply_text(reply_text, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Ошибка при отправке рейтинга: {e}. Текст: {reply_text}")
            await update.message.reply_text("Не удалось отобразить рейтинг.", parse_mode=None) # Fallback

    async def top_chat_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.rating_command(update, context, global_rating=False)

    async def top_global_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.rating_command(update, context, global_rating=True)

    async def my_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user or not update.effective_chat:
            return

        user = update.effective_user
        chat_id = update.effective_chat.id
        user_first_name_escaped = escape_markdown_v2(user.first_name)

        user_chat_stats = self.score_manager.get_user_stats(user.id, chat_id)
        user_global_stats = self.score_manager.get_user_stats(user.id, chat_id=None)

        reply_parts = [f"📊 *Ваша статистика, {user_first_name_escaped}*\n"]

        if user_chat_stats:
            answered_polls_count = user_chat_stats.get('answered_polls', 0)
            total_score = user_chat_stats.get('total_score', 0)
            avg_score_per_poll = user_chat_stats.get('average_score_per_poll', 0.0)
            
            chat_title_escaped = escape_markdown_v2(update.effective_chat.title or 'этот чат')
            reply_parts.append(f"\n*В этом чате \\({chat_title_escaped}\\):*") # ИСПРАВЛЕНО
            reply_parts.append(f"⭐ *Общий рейтинг:* `{total_score}`")
            reply_parts.append(f"🙋 *Отвечено на опросы \\(в этом чате\\):* `{answered_polls_count}`") # ИСПРАВЛЕНО
            reply_parts.append(f"🎯 *Средний балл за опрос \\(в этом чате\\):* `{avg_score_per_poll:.2f}`") # ИСПРАВЛЕНО
        else:
            reply_parts.append(f"\n{user_first_name_escaped}, у вас пока нет статистики в этом чате\\.") # ИСПРАВЛЕНО

        if user_global_stats:
            global_answered_polls = user_global_stats.get('answered_polls', 0)
            global_total_score = user_global_stats.get('total_score', 0)
            global_avg_score = user_global_stats.get('average_score_per_poll', 0.0)

            reply_parts.append(f"\n*🌍 Глобально:*")
            reply_parts.append(f"⭐ *Общий рейтинг:* `{global_total_score}`")
            reply_parts.append(f"🙋 *Всего отвечено на опросы:* `{global_answered_polls}`")
            reply_parts.append(f"🎯 *Средний балл за опрос \\(глобально\\):* `{global_avg_score:.2f}`") # ИСПРАВЛЕНО
        else:
             reply_parts.append(f"\n{user_first_name_escaped}, у вас пока нет глобальной статистики\\.") # ИСПРАВЛЕНО

        final_reply_text: str
        if len(reply_parts) == 1: # Only the initial title part (means no stats at all)
            final_reply_text = f"{user_first_name_escaped}, данных для статистики пока нет\\." # ИСПРАВЛЕНО
        else:
            final_reply_text = "\n".join(reply_parts)

        try:
            await update.message.reply_text(final_reply_text, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Ошибка при отправке my_stats: {e}. Текст:\n{final_reply_text}")
            await update.message.reply_text("Не удалось отобразить вашу статистику.", parse_mode=None)

    def get_handlers(self) -> List[CommandHandler]:
        return [
            CommandHandler(self.app_config.commands.top, self.top_chat_command),
            CommandHandler(self.app_config.commands.global_top, self.top_global_command),
            CommandHandler(self.app_config.commands.mystats, self.my_stats_command),
        ]

