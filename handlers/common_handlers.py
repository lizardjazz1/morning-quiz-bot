# handlers/common_handlers.py
import re # For Markdown escaping
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import logger, Q10_NOTIFY_DELAY_M, DQ_DEF_H, DQ_DEF_M # Renamed constants
import state
from data_manager import save_usr_data # Renamed function

# Helper for MarkdownV2 escaping
_MD_SPECIAL_CHARS = r"_*[]()~`>#+-=|{}.!" # All MarkdownV2 special characters
_MD_ESCAPE_RE = re.compile(f"([{re.escape(_MD_SPECIAL_CHARS)}])")

def md_escape(text: str) -> str:
    return _MD_ESCAPE_RE.sub(r"\\\1", text)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user:
        logger.warning("start_command: message, chat or user is None.")
        return

    user = update.effective_user
    cid_str = str(update.effective_chat.id) # Renamed chat_id_str
    uid_str = str(user.id) # Renamed user_id_str

    state.usr_scores.setdefault(cid_str, {}).setdefault(uid_str, {"name": user.full_name, "score": 0, "answered_polls": set(), "milestones_achieved": set()})
    state.usr_scores[cid_str][uid_str]["name"] = user.full_name
    if not isinstance(state.usr_scores[cid_str][uid_str].get("answered_polls"), set):
        state.usr_scores[cid_str][uid_str]["answered_polls"] = set(state.usr_scores[cid_str][uid_str].get("answered_polls", []))
    if not isinstance(state.usr_scores[cid_str][uid_str].get("milestones_achieved"), set):
        state.usr_scores[cid_str][uid_str]["milestones_achieved"] = set(state.usr_scores[cid_str][uid_str].get("milestones_achieved", []))

    save_usr_data()

    start_msg_txt = ( # Renamed start_message_text
        f"Привет, {md_escape(user.first_name)}\\! Я бот для викторин\\.\n\n"
        "Доступные команды:\n"
        "/quiz [категория] \\- 1 случайный вопрос \\(можно без категории\\)\\.\n"
        "/quiz10 \\- Сессия из 10 вопросов с выбором категории\\.\n"
        f"/quiz10notify [категория] \\- Анонс /quiz10 через {Q10_NOTIFY_DELAY_M} мин\\.\n" # Use renamed const
        "/categories \\- Список всех доступных категорий\\.\n"
        "/rating \\- Топ\\-10 игроков в этом чате\\.\n"
        "/globaltop \\- Топ\\-10 игроков по всем чатам\\.\n"
        "/stopquiz \\- Остановить текущую или запланированную /quiz10\\.\n\n"
        "*Ежедневная викторина*:\n"
        "/subscribe_daily_quiz \\- Подписаться/показать статус подписки\\.\n"
        "/unsubscribe_daily_quiz \\- Отписаться от ежедневной викторины\\.\n"
        "/setdailyquiztime HH:MM \\- Установить время рассылки \\(МСК\\)\\.\n"
        "/setdailyquizcategories [кат1] [кат2] \\.\\.\\. \\- Выбрать до 3 категорий \\(без аргументов \\- случайные\\)\\.\n"
        "/showdailyquizsettings \\- Показать текущие настройки ежедневной викторины\\."
    )
    logger.debug(f"Attempting to send start message to {cid_str}. Text: '{start_msg_txt[:100]}...'")
    await update.message.reply_text(start_msg_txt, parse_mode=ParseMode.MARKDOWN_V2)

async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        return

    cid_str = str(update.effective_chat.id) # Renamed
    reply_txt = "" # Renamed text_to_send

    if not state.qs_data: # Use renamed state var
        reply_txt = "Категории вопросов еще не загружены. Попробуйте позже."
    else:
        cat_names_formatted = [] # Renamed category_names
        for name, q_list in state.qs_data.items(): # Use renamed state var
            if isinstance(q_list, list) and q_list:
                escaped_name = md_escape(name) # **FIXED escaping here**
                # Note: The initial '\-' for bullet points needs careful handling if this line is part of a list itself.
                # The prompt showed f"\\- *{escaped_name}* ..."
                # For MarkdownV2, list items are typically like: \- List item
                cat_names_formatted.append(f"\\- *{escaped_name}* \\(вопросов: {len(q_list)}\\)")


        if cat_names_formatted:
            reply_txt = "Доступные категории:\n" + "\n".join(sorted(cat_names_formatted))
        else:
            reply_txt = "На данный момент нет доступных категорий с вопросами."

    logger.debug(f"Attempting to send categories list to {cid_str}. Text: '{reply_txt[:100]}...'")
    await update.message.reply_text(reply_txt, parse_mode=ParseMode.MARKDOWN_V2 if cat_names_formatted else None)
