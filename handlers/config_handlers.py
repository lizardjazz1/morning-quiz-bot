# bot/handlers/config_handlers.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler # For dailyquiz config menu
from telegram.constants import ParseMode, ChatMemberStatus


import state
from app_config import logger, QUIZ_CONFIG, DAILY_QUIZ_MAX_CUSTOM_CATEGORIES, \
                       DAILY_QUIZ_MENU_MAX_CATEGORIES_DISPLAY, DAILY_QUIZ_CATEGORIES_TO_PICK_RANDOM, \
                       CALLBACK_DATA_PREFIX_DAILY_QUIZ_CATEGORY_SHORT, CALLBACK_DATA_DAILY_QUIZ_RANDOM_CATEGORY, \
                       CALLBACK_DATA_DAILY_QUIZ_INFO_TOO_MANY_CATS
from data_manager import save_chat_settings, get_chat_settings
from utils import escape_markdown_v2, parse_time_hh_mm, pluralize
from modules import category_manager
# Import scheduler for re-scheduling daily quiz
from .daily_quiz_scheduler import schedule_or_reschedule_daily_quiz_for_chat # Relative import


async def _is_user_chat_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.effective_chat or not update.effective_user: return False
    if update.effective_chat.type == 'private': return True
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception as e:
        logger.warning(f"Error checking admin status for user {update.effective_user.id} in chat {update.effective_chat.id}: {e}")
        return False

# --- General Chat Quiz Settings ---
async def set_quiz_type_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _is_user_chat_admin(update, context):
        await update.message.reply_text("Эта команда доступна только администраторам чата.")
        return
    # TODO: Implement logic to set default quiz type for /quiz (normal/session)
    await update.message.reply_text("Функция /setquiztype в разработке.")

async def set_quiz_questions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _is_user_chat_admin(update, context):
        await update.message.reply_text("Эта команда доступна только администраторам чата.")
        return
    # TODO: Implement logic to set default number of questions for session quizzes
    await update.message.reply_text("Функция /setquizquestions в разработке.")

async def set_quiz_categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _is_user_chat_admin(update, context):
        await update.message.reply_text("Эта команда доступна только администраторам чата.")
        return
    # TODO: Implement logic to set default categories for the chat
    await update.message.reply_text("Функция /setquizcategories в разработке.")

async def exclude_quiz_categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _is_user_chat_admin(update, context):
        await update.message.reply_text("Эта команда доступна только администраторам чата.")
        return
    # TODO: Implement logic to set excluded categories for the chat
    await update.message.reply_text("Функция /excludecategories в разработке.")

async def show_chat_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # No admin check needed for showing settings
    if not update.message or not update.effective_chat: return
    chat_id_str = str(update.effective_chat.id)
    settings = get_chat_settings(chat_id_str) # Gets merged settings with defaults

    # General settings
    quiz_type = settings.get("quiz_type_on_start", "normal")
    num_q_session = settings.get("num_questions_session", QUIZ_CONFIG.get("quiz_types_config", {}).get("session",{}).get("default_num_questions",10) )
    
    allowed_cats_list = settings.get("allowed_categories")
    allowed_cats_str = f"`{escape_markdown_v2(', '.join(allowed_cats_list))}`" if allowed_cats_list else "`Все доступные`"
    
    excluded_cats_list = settings.get("excluded_categories", [])
    excluded_cats_str = f"`{escape_markdown_v2(', '.join(excluded_cats_list))}`" if excluded_cats_list else "`Нет`"

    # Daily quiz settings
    daily_settings = settings.get("daily_quiz", {})
    daily_enabled = daily_settings.get("enabled", False)
    daily_time_str = f"{daily_settings.get('hour_msk',0):02d}:{daily_settings.get('minute_msk',0):02d} МСК"
    daily_cats_list = daily_settings.get("categories")
    daily_cats_str = f"`{escape_markdown_v2(', '.join(daily_cats_list))}`" if daily_cats_list else f"`Случайные ({DAILY_QUIZ_CATEGORIES_TO_PICK_RANDOM})`"
    daily_num_q = daily_settings.get("num_questions", QUIZ_CONFIG.get("quiz_types_config", {}).get("daily",{}).get("default_num_questions",10))

    reply_text = (
        f"⚙️ *Текущие настройки викторин для этого чата*:\n\n"
        f"*Общие настройки*:\n"
        f"\\- Тип викторины по умолчанию для `/quiz`: `{quiz_type}`\n"
        f"\\- Вопросов в сессии по умолчанию: `{num_q_session}`\n"
        f"\\- Разрешенные категории по умолчанию: {allowed_cats_str}\n"
        f"\\- Исключенные категории: {excluded_cats_str}\n\n"
        f"*Настройки ежедневной викторины* (`/dailyquiz`):\n"
        f"\\- Статус: {'*Включена*' if daily_enabled else '_Выключена_'}\n"
    )
    if daily_enabled:
        reply_text += (
            f"\\- Время: `{daily_time_str}`\n"
            f"\\- Категории: {daily_cats_str}\n"
            f"\\- Количество вопросов: `{daily_num_q}`\n"
        )
    reply_text += "\nИспользуйте команды настроек для изменения\\."

    await update.message.reply_text(reply_text, parse_mode=ParseMode.MARKDOWN_V2)


# --- Daily Quiz Settings Commands (migrated from old daily_quiz_handlers) ---
# Conversation states for /dailyquiz main menu
SELECT_DAILY_ACTION, SET_DAILY_TIME, SET_DAILY_CATEGORIES_METHOD, SET_DAILY_CATEGORIES_TEXT = range(4)

async def daily_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Main entry point for /dailyquiz configuration."""
    if not update.message or not update.effective_chat: return ConversationHandler.END
    chat_id_str = str(update.effective_chat.id)
    
    if not await _is_user_chat_admin(update, context): # Admin check for config
        await update.message.reply_text("Настройка ежедневной викторины доступна только администраторам чата.")
        return ConversationHandler.END

    settings = get_chat_settings(chat_id_str)
    daily_settings = settings.get("daily_quiz", {})
    is_enabled = daily_settings.get("enabled", False)

    keyboard = [
        [InlineKeyboardButton(f"{'Выключить' if is_enabled else 'Включить'} ежедневную викторину", callback_data="toggle_daily")],
    ]
    if is_enabled:
        keyboard.extend([
            [InlineKeyboardButton("Установить время", callback_data="set_time_daily")],
            [InlineKeyboardButton("Выбрать категории", callback_data="set_cats_daily")],
            [InlineKeyboardButton("Кол-во вопросов (скоро)", callback_data="set_num_q_daily_soon")], # Placeholder
        ])
    keyboard.append([InlineKeyboardButton("Отмена", callback_data="cancel_daily_config")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    status_str = "*Включена*" if is_enabled else "_Выключена_"
    time_str = f"{daily_settings.get('hour_msk',0):02d}:{daily_settings.get('minute_msk',0):02d} МСК"
    cats = daily_settings.get('categories')
    cat_str = f"`{escape_markdown_v2(', '.join(cats))}`" if cats else f"`Случайные ({DAILY_QUIZ_CATEGORIES_TO_PICK_RANDOM})`"
    
    text = (f"🗓️ *Настройка ежедневной викторины для этого чата*:\n"
            f"Текущий статус: {status_str}\n")
    if is_enabled:
        text += (f"Время: `{time_str}`\n"
                 f"Категории: {cat_str}\n")
    text += "\nВыберите действие:"
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    return SELECT_DAILY_ACTION

async def daily_quiz_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles button presses from the main /dailyquiz menu."""
    query = update.callback_query
    await query.answer()
    action = query.data
    chat_id_str = str(query.message.chat_id)

    if action == "cancel_daily_config":
        await query.edit_message_text("Настройка отменена.", reply_markup=None)
        return ConversationHandler.END

    settings = get_chat_settings(chat_id_str)
    # Ensure 'daily_quiz' key exists and is a dict, even if loading defaults
    if "daily_quiz" not in settings or not isinstance(settings["daily_quiz"], dict):
        settings["daily_quiz"] = copy.deepcopy(QUIZ_CONFIG.get("default_chat_settings", {}).get("daily_quiz", {}))


    if action == "toggle_daily":
        current_enabled = settings.get("daily_quiz", {}).get("enabled", False)
        settings["daily_quiz"]["enabled"] = not current_enabled
        state.chat_settings[chat_id_str] = settings # Update state
        save_chat_settings()
        await schedule_or_reschedule_daily_quiz_for_chat(context.application, chat_id_str)
        status_msg = "Ежедневная викторина ВКЛЮЧЕНА." if settings["daily_quiz"]["enabled"] else "Ежедневная викторина ВЫКЛЮЧЕНА."
        await query.edit_message_text(status_msg + "\n\nИспользуйте /dailyquiz для дальнейшей настройки.", reply_markup=None)
        return ConversationHandler.END # Or back to main menu if preferred

    elif action == "set_time_daily":
        await query.edit_message_text("Введите время для ежедневной викторины в формате HH:MM (МСК):", reply_markup=None)
        return SET_DAILY_TIME
        
    elif action == "set_cats_daily":
        # Similar to old setdailyquizcategories command logic
        # For simplicity, directly ask for text input or show menu
        keyboard_cats = [
            [InlineKeyboardButton("🎲 Случайные категории", callback_data=f"dq_set_{CALLBACK_DATA_DAILY_QUIZ_RANDOM_CATEGORY}")],
            [InlineKeyboardButton("📝 Ввести названия категорий", callback_data="dq_set_text_input")],
            # TODO: Add button to show category list if many
            [InlineKeyboardButton("⬅️ Назад", callback_data="dq_back_to_main")]
        ]
        await query.edit_message_text(
            "Как вы хотите выбрать категории для ежедневной викторины?\n"
            f"(Максимум {DAILY_QUIZ_MAX_CUSTOM_CATEGORIES} категории, если вводите вручную)",
            reply_markup=InlineKeyboardMarkup(keyboard_cats)
        )
        return SET_DAILY_CATEGORIES_METHOD
    
    elif action == "set_num_q_daily_soon":
        await query.answer("Эта функция скоро появится!", show_alert=True)
        return SELECT_DAILY_ACTION # Stay in the same state

    return ConversationHandler.END # Should not happen


async def daily_quiz_set_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id_str = str(update.message.chat_id)
    time_input = update.message.text
    parsed_time = parse_time_hh_mm(time_input)

    if parsed_time is None:
        await update.message.reply_text("Неверный формат времени. Пожалуйста, введите в формате HH:MM (например, 08:30 или 19:00).")
        return SET_DAILY_TIME # Stay in this state

    hour, minute = parsed_time
    settings = get_chat_settings(chat_id_str)
    if "daily_quiz" not in settings or not isinstance(settings["daily_quiz"], dict): # Ensure structure
        settings["daily_quiz"] = copy.deepcopy(QUIZ_CONFIG.get("default_chat_settings", {}).get("daily_quiz", {}))

    settings["daily_quiz"]["hour_msk"] = hour
    settings["daily_quiz"]["minute_msk"] = minute
    state.chat_settings[chat_id_str] = settings
    save_chat_settings()
    await schedule_or_reschedule_daily_quiz_for_chat(context.application, chat_id_str)
    await update.message.reply_text(f"Время ежедневной викторины установлено на {hour:02d}:{minute:02d} МСК.\nИспользуйте /dailyquiz для других настроек.")
    return ConversationHandler.END

async def daily_quiz_set_categories_method_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data
    chat_id_str = str(query.message.chat_id)

    if action == "dq_back_to_main":
        # Re-show main menu (call daily_quiz_command logic, simplified here)
        # For a real ConvoHandler, you'd transition back. Here, just end and tell user to re-run.
        await query.edit_message_text("Возврат в главное меню настроек. Используйте /dailyquiz.", reply_markup=None)
        return ConversationHandler.END


    if action == f"dq_set_{CALLBACK_DATA_DAILY_QUIZ_RANDOM_CATEGORY}":
        settings = get_chat_settings(chat_id_str)
        if "daily_quiz" not in settings or not isinstance(settings["daily_quiz"], dict):
             settings["daily_quiz"] = copy.deepcopy(QUIZ_CONFIG.get("default_chat_settings", {}).get("daily_quiz", {}))
        settings["daily_quiz"]["categories"] = None # None for random
        state.chat_settings[chat_id_str] = settings
        save_chat_settings()
        await query.edit_message_text(f"Категории для ежедневной викторины установлены на: *случайные* ({DAILY_QUIZ_CATEGORIES_TO_PICK_RANDOM} шт\\.)\nИспользуйте /dailyquiz для других настроек\\.", reply_markup=None, parse_mode=ParseMode.MARKDOWN_V2)
        return ConversationHandler.END
    
    elif action == "dq_set_text_input":
        await query.edit_message_text(
            f"Введите названия категорий через запятую (например: `История, Наука, География`)\\.\n"
            f"Максимум {DAILY_QUIZ_MAX_CUSTOM_CATEGORIES} категории\\. "
            f"Чтобы выбрать случайные, напишите `случайные` или `random`\\.",
            reply_markup=None, parse_mode=ParseMode.MARKDOWN_V2
        )
        return SET_DAILY_CATEGORIES_TEXT
    
    # TODO: Add logic for showing full category list with pagination if needed

    return SET_DAILY_CATEGORIES_METHOD # Stay if unhandled

async def daily_quiz_set_categories_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id_str = str(update.message.chat_id)
    text_input = update.message.text.strip()

    settings = get_chat_settings(chat_id_str)
    if "daily_quiz" not in settings or not isinstance(settings["daily_quiz"], dict):
        settings["daily_quiz"] = copy.deepcopy(QUIZ_CONFIG.get("default_chat_settings", {}).get("daily_quiz", {}))

    if text_input.lower() in ["случайные", "random"]:
        settings["daily_quiz"]["categories"] = None
        state.chat_settings[chat_id_str] = settings
        save_chat_settings()
        await update.message.reply_text(f"Категории установлены на: *случайные* ({DAILY_QUIZ_CATEGORIES_TO_PICK_RANDOM} шт\\.)", parse_mode=ParseMode.MARKDOWN_V2)
        return ConversationHandler.END

    raw_category_names = [name.strip() for name in text_input.split(',') if name.strip()]
    if not raw_category_names:
        await update.message.reply_text("Вы не указали категории. Напишите названия через запятую или `случайные`.")
        return SET_DAILY_CATEGORIES_TEXT

    available_cat_names_map = {
        name.lower(): name for name in category_manager.get_available_categories()
    }
    
    valid_chosen_categories = []
    invalid_categories_input = []

    for cat_arg in raw_category_names:
        canonical_name = available_cat_names_map.get(cat_arg.lower())
        if canonical_name and canonical_name not in valid_chosen_categories:
            valid_chosen_categories.append(canonical_name)
        else:
            invalid_categories_input.append(cat_arg)

    if len(valid_chosen_categories) > DAILY_QUIZ_MAX_CUSTOM_CATEGORIES:
        await update.message.reply_text(
            f"Слишком много категорий\\! Можно выбрать до {DAILY_QUIZ_MAX_CUSTOM_CATEGORIES}\\. "
            f"Вы указали {len(valid_chosen_categories)} валидных: `{escape_markdown_v2(', '.join(valid_chosen_categories))}`\\. Пожалуйста, сократите список\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return SET_DAILY_CATEGORIES_TEXT

    if not valid_chosen_categories:
        await update.message.reply_text(
            f"Указанные категории ({escape_markdown_v2(', '.join(invalid_categories_input))}) не найдены или пусты\\. "
            f"Попробуйте еще раз или напишите `случайные`\\.", parse_mode=ParseMode.MARKDOWN_V2
        )
        return SET_DAILY_CATEGORIES_TEXT
    
    settings["daily_quiz"]["categories"] = valid_chosen_categories
    state.chat_settings[chat_id_str] = settings
    save_chat_settings()

    reply_msg = f"Категории для ежедневной викторины установлены: *{escape_markdown_v2(', '.join(valid_chosen_categories))}*\\."
    if invalid_categories_input:
        reply_msg += f"\n*Предупреждение*: категории `{escape_markdown_v2(', '.join(invalid_categories_input))}` не найдены/пусты и были проигнорированы\\."
    
    await update.message.reply_text(reply_msg, parse_mode=ParseMode.MARKDOWN_V2)
    return ConversationHandler.END

async def daily_quiz_cancel_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Generic cancel for any state in the conversation."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Настройка ежедневной викторины отменена.", reply_markup=None)
    elif update.message:
        await update.message.reply_text("Настройка ежедневной викторины отменена.")
    return ConversationHandler.END


# --- Standalone subscribe/unsubscribe for convenience ---
async def subscribe_daily_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user: return
    chat_id_str = str(update.effective_chat.id)

    if not await _is_user_chat_admin(update, context):
        await update.message.reply_text("Эта команда доступна только администраторам чата.")
        return

    settings = get_chat_settings(chat_id_str)
    if "daily_quiz" not in settings or not isinstance(settings["daily_quiz"], dict):
        settings["daily_quiz"] = copy.deepcopy(QUIZ_CONFIG.get("default_chat_settings", {}).get("daily_quiz", {}))

    if settings["daily_quiz"].get("enabled", False):
        await update.message.reply_text("Ежедневная викторина уже включена. Используйте /dailyquiz для настройки.")
    else:
        settings["daily_quiz"]["enabled"] = True
        # Use existing defaults or load them if not present
        settings["daily_quiz"].setdefault("hour_msk", QUIZ_CONFIG.get("default_chat_settings", {}).get("daily_quiz", {}).get("hour_msk",7) )
        settings["daily_quiz"].setdefault("minute_msk", QUIZ_CONFIG.get("default_chat_settings", {}).get("daily_quiz", {}).get("minute_msk",0) )
        settings["daily_quiz"].setdefault("categories", None) # Random
        settings["daily_quiz"].setdefault("num_questions", QUIZ_CONFIG.get("default_chat_settings", {}).get("daily_quiz", {}).get("num_questions",10) )


        state.chat_settings[chat_id_str] = settings
        save_chat_settings()
        await schedule_or_reschedule_daily_quiz_for_chat(context.application, chat_id_str)
        await update.message.reply_text("✅ Ежедневная викторина включена! Используйте /dailyquiz для подробной настройки (время, категории).")
        logger.info(f"Daily quiz enabled for chat {chat_id_str} by user {update.effective_user.id} via /subdaily.")

async def unsubscribe_daily_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat or not update.effective_user: return
    chat_id_str = str(update.effective_chat.id)

    if not await _is_user_chat_admin(update, context):
        await update.message.reply_text("Эта команда доступна только администраторам чата.")
        return

    settings = get_chat_settings(chat_id_str)
    if not settings.get("daily_quiz", {}).get("enabled", False):
        await update.message.reply_text("Ежедневная викторина не была включена.")
    else:
        if "daily_quiz" not in settings or not isinstance(settings["daily_quiz"], dict):
             settings["daily_quiz"] = copy.deepcopy(QUIZ_CONFIG.get("default_chat_settings", {}).get("daily_quiz", {}))
        settings["daily_quiz"]["enabled"] = False
        state.chat_settings[chat_id_str] = settings
        save_chat_settings()
        await schedule_or_reschedule_daily_quiz_for_chat(context.application, chat_id_str) # This will remove the job
        await update.message.reply_text("Ежедневная викторина отключена.")
        logger.info(f"Daily quiz disabled for chat {chat_id_str} by user {update.effective_user.id} via /unsubdaily.")

