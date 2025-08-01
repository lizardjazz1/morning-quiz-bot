#handlers/config_handlers.py
from __future__ import annotations
import logging
import asyncio
from typing import TYPE_CHECKING, List, Any, Optional, Dict, Union

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ConversationHandler, Application
)
from telegram.constants import ParseMode
from telegram.error import BadRequest

from app_config import AppConfig
from data_manager import DataManager
from modules.category_manager import CategoryManager
from utils import is_user_admin_in_update, escape_markdown_v2, pluralize, format_seconds_to_human_readable_time

if TYPE_CHECKING:
    from .daily_quiz_scheduler import DailyQuizScheduler

logger = logging.getLogger(__name__)

(
    CFG_MAIN_MENU, CFG_INPUT_VALUE,
    CFG_SELECT_GENERAL_CATEGORIES,
    CFG_DAILY_MENU,
    CFG_CONFIRM_RESET,
    CFG_DAILY_TIMES_MENU,
    CFG_DAILY_ADD_TIME
) = map(str, range(7))

CB_ADM_ = "admcfg_"
CB_ADM_BACK_TO_MAIN = f"{CB_ADM_}main_menu_back"
CB_ADM_FINISH_CONFIG = f"{CB_ADM_}finish"
CB_ADM_CONFIRM_RESET_SETTINGS = f"{CB_ADM_}confirm_reset"
CB_ADM_EXECUTE_RESET_SETTINGS = f"{CB_ADM_}execute_reset"
CB_ADM_SET_DEFAULT_QUIZ_TYPE = f"{CB_ADM_}set_def_q_type"
CB_ADM_SET_DEFAULT_QUIZ_TYPE_OPT = f"{CB_ADM_}set_def_q_type_opt"
CB_ADM_SET_DEFAULT_NUM_QUESTIONS = f"{CB_ADM_}set_def_num_q"
CB_ADM_SET_DEFAULT_OPEN_PERIOD = f"{CB_ADM_}set_def_open_p"
CB_ADM_SET_DEFAULT_ANNOUNCE_QUIZ = f"{CB_ADM_}set_def_ann_q"
CB_ADM_SET_DEFAULT_ANNOUNCE_QUIZ_OPT = f"{CB_ADM_}set_def_ann_q_opt"
CB_ADM_SET_DEFAULT_ANNOUNCE_DELAY = f"{CB_ADM_}set_def_ann_d"
CB_ADM_MANAGE_ENABLED_CATEGORIES = f"{CB_ADM_}manage_en_cats"
CB_ADM_MANAGE_DISABLED_CATEGORIES = f"{CB_ADM_}manage_dis_cats"
CB_ADM_CAT_SEL_ = f"{CB_ADM_}g_cat_sel_"
CB_ADM_CAT_TOGGLE = f"{CB_ADM_CAT_SEL_}toggle"
CB_ADM_CAT_SAVE_SELECTION = f"{CB_ADM_CAT_SEL_}save"
CB_ADM_CAT_CLEAR_SELECTION = f"{CB_ADM_CAT_SEL_}clear"
CB_ADM_GOTO_DAILY_MENU = f"{CB_ADM_}goto_daily"
CB_ADM_BACK_TO_DAILY_MENU = f"{CB_ADM_}daily_menu_back"
CB_ADM_DAILY_TOGGLE_ENABLED = f"{CB_ADM_}daily_toggle_en"
CB_ADM_DAILY_MANAGE_TIMES = f"{CB_ADM_}daily_manage_times"
CB_ADM_DAILY_SET_CATEGORIES_MODE = f"{CB_ADM_}daily_set_cat_mode"
CB_ADM_DAILY_SET_CATEGORIES_MODE_OPT = f"{CB_ADM_}daily_set_cat_mode_opt"
CB_ADM_DAILY_SET_NUM_RANDOM_CATEGORIES = f"{CB_ADM_}daily_set_num_rand_cat"
CB_ADM_DAILY_MANAGE_SPECIFIC_CATEGORIES = f"{CB_ADM_}daily_manage_spec_cat"
CB_ADM_DAILY_SET_NUM_QUESTIONS = f"{CB_ADM_}daily_set_num_q"
CB_ADM_DAILY_SET_INTERVAL_SECONDS = f"{CB_ADM_}daily_set_interval"
CB_ADM_DAILY_SET_POLL_OPEN_SECONDS = f"{CB_ADM_}daily_set_poll_open"
CB_ADM_DAILY_TIME_ = f"{CB_ADM_}daily_time_"
CB_ADM_DAILY_TIME_ADD = f"{CB_ADM_DAILY_TIME_}add"
CB_ADM_DAILY_TIME_REMOVE = f"{CB_ADM_DAILY_TIME_}remove"
CB_ADM_DAILY_TIME_BACK_TO_LIST = f"{CB_ADM_DAILY_TIME_}back_to_times_list"

# ИЗМЕНЕНИЕ: Новые константы для управления автоудалением
CB_ADM_TOGGLE_AUTO_DELETE_BOT_MESSAGES = f"{CB_ADM_}toggle_auto_del_msg"
CB_ADM_TOGGLE_AUTO_DELETE_BOT_MESSAGES_OPT = f"{CB_ADM_}toggle_auto_del_msg_opt"


CTX_ADMIN_CFG_CHAT_ID = 'admin_cfg_chat_id'
CTX_ADMIN_CFG_MSG_ID = 'admin_cfg_msg_id'
CTX_INPUT_TARGET_KEY_PATH = 'input_target_key_path'
CTX_INPUT_PROMPT = 'input_prompt_text'
CTX_INPUT_CONSTRAINTS = 'input_constraints_dict'
CTX_CURRENT_MENU_SENDER_CB_NAME = 'current_menu_sender_callback_name'
CTX_INPUT_CANCEL_CB_DATA = '_input_cancel_cb_data'
CTX_TEMP_CATEGORY_SELECTION = 'temp_category_selection_set'
CTX_CATEGORY_SELECTION_MODE = 'category_selection_mode_str'
CTX_CATEGORY_SELECTION_TITLE = 'category_selection_title_str'

class ConfigHandlers:
    def __init__(self, app_config: AppConfig, data_manager: DataManager,
                 category_manager: CategoryManager, application: Application):
        self.app_config = app_config
        self.data_manager = data_manager
        self.category_manager = category_manager
        self.application = application
        self.daily_quiz_scheduler_ref: Optional[DailyQuizScheduler] = None

    def set_daily_quiz_scheduler(self, scheduler: DailyQuizScheduler) -> None:
        self.daily_quiz_scheduler_ref = scheduler

    async def _is_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        return await is_user_admin_in_update(update, context)

    async def _update_config_message(self,
                                     query_or_update: Optional[Union[Update, CallbackQuery]],
                                     context: ContextTypes.DEFAULT_TYPE,
                                     new_text: str,
                                     new_markup: Optional[InlineKeyboardMarkup]):
        target_msg_id = context.chat_data.get(CTX_ADMIN_CFG_MSG_ID)
        chat_id = context.chat_data.get(CTX_ADMIN_CFG_CHAT_ID)

        if not chat_id:
            logger.error("_update_config_message: chat_id не найден в context.chat_data.")
            if isinstance(query_or_update, CallbackQuery):
                try: await query_or_update.answer("Ошибка: сессия настроек повреждена.", show_alert=True)
                except Exception: pass
            return

        current_message: Optional[Message] = None
        is_callback_query = isinstance(query_or_update, CallbackQuery)

        if is_callback_query and query_or_update.message:
            current_message = query_or_update.message
        elif isinstance(query_or_update, Update) and query_or_update.message:
            current_message = query_or_update.message

        if current_message and target_msg_id == current_message.message_id:
            try:
                await current_message.edit_text(text=new_text, reply_markup=new_markup, parse_mode=ParseMode.MARKDOWN_V2)
                if is_callback_query:
                    try: await query_or_update.answer()
                    except Exception: pass
                return
            except BadRequest as e:
                if "Message is not modified" in str(e).lower():
                    if is_callback_query:
                        try: await query_or_update.answer()
                        except Exception: pass
                    return
                logger.warning(f"Не удалось отредактировать сообщение меню {target_msg_id} в чате {chat_id}: {e}. Попытка отправить новое.")
            except Exception as e_edit:
                logger.error(f"Непредвиденная ошибка при редактировании сообщения меню {target_msg_id}: {e_edit}. Попытка отправить новое.")

        if target_msg_id and (not current_message or target_msg_id != current_message.message_id):
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=target_msg_id)
                logger.debug(f"Старое сообщение меню {target_msg_id} удалено.")
            except Exception as e_del:
                logger.debug(f"Не удалось удалить старое сообщение меню {target_msg_id}: {e_del}")
        context.chat_data[CTX_ADMIN_CFG_MSG_ID] = None

        try:
            sent_msg = await context.bot.send_message(chat_id=chat_id, text=new_text, reply_markup=new_markup, parse_mode=ParseMode.MARKDOWN_V2)
            context.chat_data[CTX_ADMIN_CFG_MSG_ID] = sent_msg.message_id
            if is_callback_query:
                try: await query_or_update.answer()
                except Exception: pass
        except Exception as e_send:
            logger.error(f"Не удалось отправить новое сообщение меню в чат {chat_id}: {e_send}")
            if is_callback_query:
                try: await query_or_update.answer("Ошибка отправки меню.", show_alert=True)
                except Exception: pass

    async def admin_settings_entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        if not update.message or not update.effective_chat or not update.effective_user:
            return ConversationHandler.END
        if not await self._is_admin(update, context):
            await update.message.reply_text(escape_markdown_v2("Эта команда доступна только администраторам чата."), parse_mode=ParseMode.MARKDOWN_V2)
            return ConversationHandler.END

        context.chat_data.clear()
        context.chat_data[CTX_ADMIN_CFG_CHAT_ID] = update.effective_chat.id
        await self._send_main_cfg_menu(update, context)
        return CFG_MAIN_MENU

    async def _send_main_cfg_menu(self, query_or_update: Optional[Union[Update, CallbackQuery]], context: ContextTypes.DEFAULT_TYPE):
        chat_id = context.chat_data.get(CTX_ADMIN_CFG_CHAT_ID)
        if not chat_id:
             logger.error("_send_main_cfg_menu: CTX_ADMIN_CFG_CHAT_ID не найден.")
             return
        settings = self.data_manager.get_chat_settings(chat_id)
        display_text = self._format_settings_display(settings, part="main")
        daily_brief = self._format_settings_display(settings, part="daily_brief")
        header_text = f"*{escape_markdown_v2('🛠️ Админ. настройки чата')}*"
        prompt_text = escape_markdown_v2("Выберите параметр для изменения:")
        text = f"{header_text}\n\n{display_text}\n\n{daily_brief}\n\n{prompt_text}"
        kb_buttons = [
            [InlineKeyboardButton("Тип /quiz", callback_data=CB_ADM_SET_DEFAULT_QUIZ_TYPE),
             InlineKeyboardButton("Кол-во /quiz", callback_data=CB_ADM_SET_DEFAULT_NUM_QUESTIONS)],
            [InlineKeyboardButton("Время ответа /quiz", callback_data=CB_ADM_SET_DEFAULT_OPEN_PERIOD)],
            [InlineKeyboardButton("Анонс /quiz", callback_data=CB_ADM_SET_DEFAULT_ANNOUNCE_QUIZ),
             InlineKeyboardButton("Задержка анонса", callback_data=CB_ADM_SET_DEFAULT_ANNOUNCE_DELAY)],
            [InlineKeyboardButton("Разрешенные категории", callback_data=CB_ADM_MANAGE_ENABLED_CATEGORIES)],
            [InlineKeyboardButton("Запрещенные категории", callback_data=CB_ADM_MANAGE_DISABLED_CATEGORIES)],
            [InlineKeyboardButton("Автоудаление сообщений", callback_data=CB_ADM_TOGGLE_AUTO_DELETE_BOT_MESSAGES)], # ИЗМЕНЕНИЕ
            [InlineKeyboardButton("Ежедневная Викторина ➡️", callback_data=CB_ADM_GOTO_DAILY_MENU)],
            [InlineKeyboardButton("Сбросить всё к по умолчанию", callback_data=CB_ADM_CONFIRM_RESET_SETTINGS)],
            [InlineKeyboardButton("✅ Завершить настройку", callback_data=CB_ADM_FINISH_CONFIG)],
        ]
        context.chat_data[CTX_CURRENT_MENU_SENDER_CB_NAME] = "_send_main_cfg_menu"
        context.chat_data[CTX_INPUT_CANCEL_CB_DATA] = CB_ADM_BACK_TO_MAIN
        await self._update_config_message(query_or_update, context, text, InlineKeyboardMarkup(kb_buttons))

    def _format_settings_display(self, settings: Dict[str, Any], part: str = "main") -> str:
        lines = []
        def_chat_s = self.app_config.default_chat_settings

        time_setting_key_paths = [
            ["default_open_period_seconds"],
            ["default_announce_delay_seconds"],
            ["daily_quiz", "interval_seconds"],
            ["daily_quiz", "poll_open_seconds"]
        ]

        def get_and_format_value(setting_key_path: List[str], default_value_override: Any = None) -> str:
            current_value_in_settings = settings
            for key in setting_key_path:
                if isinstance(current_value_in_settings, dict):
                    current_value_in_settings = current_value_in_settings.get(key)
                else:
                    current_value_in_settings = None
                    break

            default_value_from_config_structure = def_chat_s
            for key in setting_key_path:
                if isinstance(default_value_from_config_structure, dict):
                    default_value_from_config_structure = default_value_from_config_structure.get(key)
                else:
                    default_value_from_config_structure = default_value_override
                    break
            
            # ИЗМЕНЕНИЕ: Убедимся, что default_value_from_config_structure не None перед использованием
            # Это особенно важно для новых настроек, которые могут отсутствовать в старых quiz_config.json
            if default_value_from_config_structure is None and default_value_override is not None:
                final_value_to_display = current_value_in_settings if current_value_in_settings is not None else default_value_override
            else:
                final_value_to_display = current_value_in_settings if current_value_in_settings is not None else default_value_from_config_structure


            if setting_key_path in time_setting_key_paths and isinstance(final_value_to_display, (int, float)):
                return escape_markdown_v2(format_seconds_to_human_readable_time(int(final_value_to_display)))

            if isinstance(final_value_to_display, list) and setting_key_path != ["daily_quiz", "times_msk"]:
                 if not final_value_to_display: return "_Нет_"
                 return escape_markdown_v2(", ".join(sorted(str(item) for item in final_value_to_display)))

            if setting_key_path == ["daily_quiz", "times_msk"]:
                times_list_val = final_value_to_display
                if not isinstance(times_list_val, list) or not times_list_val:
                    return "_Не задано_"
                formatted_times_str_list = []
                for t_entry in times_list_val:
                    if isinstance(t_entry, dict) and "hour" in t_entry and "minute" in t_entry:
                        try:
                           h, m = int(t_entry["hour"]), int(t_entry["minute"])
                           formatted_times_str_list.append(f"{h:02d}:{m:02d}")
                        except (ValueError, TypeError):
                           formatted_times_str_list.append("??:??")
                    else:
                        formatted_times_str_list.append("Некорр.запись")
                return escape_markdown_v2(", ".join(sorted(formatted_times_str_list))) + " MSK"

            if setting_key_path[-1] == "categories_mode":
                 mode_map = {"random": "🎲 Случайные", "specific": "🗂️ Выбранные", "all_enabled": "✅ Все разрешенные"}
                 return escape_markdown_v2(mode_map.get(str(final_value_to_display), "Неизвестно"))
            if isinstance(final_value_to_display, bool):
                 return escape_markdown_v2("Вкл" if final_value_to_display else "Выкл")
            if setting_key_path == ["enabled_categories"] and final_value_to_display is None:
                return "_Все системные_"
            return escape_markdown_v2(str(final_value_to_display)) if final_value_to_display is not None else "_Не задано_"

        if part == "main" or part == "all":
            lines.append(f"*{escape_markdown_v2('Тип /quiz по умолчанию:')}* `{get_and_format_value(['default_quiz_type'])}`")
            lines.append(f"*{escape_markdown_v2('Кол-во вопросов /quiz:')}* `{get_and_format_value(['default_num_questions'])}`")
            lines.append(f"*{escape_markdown_v2('Время на ответ /quiz:')}* `{get_and_format_value(['default_open_period_seconds'])}`")
            lines.append(f"*{escape_markdown_v2('Анонс /quiz:')}* `{get_and_format_value(['default_announce_quiz'])}`")
            if settings.get('default_announce_quiz', def_chat_s.get('default_announce_quiz')):
                 lines.append(f"*{escape_markdown_v2('Задержка анонса:')}* `{get_and_format_value(['default_announce_delay_seconds'])}`")
            lines.append(f"*{escape_markdown_v2('Разрешенные категории для чата:')}* {get_and_format_value(['enabled_categories'])}")
            lines.append(f"*{escape_markdown_v2('Запрещенные категории для чата:')}* {get_and_format_value(['disabled_categories'])}")
            # ИЗМЕНЕНИЕ: Отображение новой настройки
            lines.append(f"*{escape_markdown_v2('Автоудаление сообщений бота:')}* `{get_and_format_value(['auto_delete_bot_messages'], default_value_override=True)}`")


        if part == "daily_brief" or part == "daily" or part == "all":
            lines.append(f"*{escape_markdown_v2('Ежедневная викторина:')}* `{get_and_format_value(['daily_quiz', 'enabled'])}`")
            daily_enabled_val = settings.get('daily_quiz', {}).get('enabled', def_chat_s.get('daily_quiz', {}).get('enabled',False))
            if daily_enabled_val or part == "daily":
                 lines.append(f"*{escape_markdown_v2('Время запуска:')}* {get_and_format_value(['daily_quiz', 'times_msk'])}")
                 lines.append(f"*{escape_markdown_v2('Категории ежедневной викторины:')}* {get_and_format_value(['daily_quiz', 'categories_mode'])}")
                 daily_cat_mode_val = settings.get('daily_quiz', {}).get('categories_mode', def_chat_s.get('daily_quiz', {}).get('categories_mode'))
                 if daily_cat_mode_val == 'random':
                      lines.append(f"*{escape_markdown_v2('Количество случайных категорий:')}* `{get_and_format_value(['daily_quiz', 'num_random_categories'])}`")
                 elif daily_cat_mode_val == 'specific':
                      lines.append(f"*{escape_markdown_v2('Выбранные категории:')}* {get_and_format_value(['daily_quiz', 'specific_categories'])}")
                 lines.append(f"*{escape_markdown_v2('Количество вопросов:')}* `{get_and_format_value(['daily_quiz', 'num_questions'])}`")
                 lines.append(f"*{escape_markdown_v2('Интервал между вопросами:')}* `{get_and_format_value(['daily_quiz', 'interval_seconds'])}`")
                 lines.append(f"*{escape_markdown_v2('Время на ответ:')}* `{get_and_format_value(['daily_quiz', 'poll_open_seconds'])}`")
        return "\n".join(lines)

    async def handle_main_menu_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        query = update.callback_query
        await query.answer()
        action = query.data
        chat_id = context.chat_data.get(CTX_ADMIN_CFG_CHAT_ID)
        if not chat_id: return ConversationHandler.END
        settings = self.data_manager.get_chat_settings(chat_id)
        def_s = self.app_config.default_chat_settings
        context.chat_data[CTX_CURRENT_MENU_SENDER_CB_NAME] = "_send_main_cfg_menu"
        context.chat_data[CTX_INPUT_CANCEL_CB_DATA] = CB_ADM_BACK_TO_MAIN

        if action == CB_ADM_FINISH_CONFIG:
            await self._update_config_message(query, context, escape_markdown_v2("Настройки сохранены. Завершение."), None)
            context.chat_data.clear()
            return ConversationHandler.END
        elif action == CB_ADM_BACK_TO_MAIN:
            await self._send_main_cfg_menu(query, context)
            return CFG_MAIN_MENU
        elif action == CB_ADM_SET_DEFAULT_QUIZ_TYPE:
            current_val = settings.get('default_quiz_type', def_s['default_quiz_type'])
            kb = []
            for q_type_key in ["session", "single"]:
                q_type_config = self.app_config.quiz_types_config.get(q_type_key, {})
                q_type_name = q_type_config.get("type", q_type_key)
                prefix = "✅ " if q_type_name == current_val else "☑️ "
                kb.append([InlineKeyboardButton(f"{prefix}{q_type_name.capitalize()}", callback_data=f"{CB_ADM_SET_DEFAULT_QUIZ_TYPE_OPT}:{q_type_name}")])
            kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADM_BACK_TO_MAIN)])
            await self._update_config_message(query, context, escape_markdown_v2("Выберите тип /quiz по умолчанию:"), InlineKeyboardMarkup(kb))
            return CFG_MAIN_MENU
        elif action.startswith(CB_ADM_SET_DEFAULT_QUIZ_TYPE_OPT):
            val = action.split(":", 1)[1]
            self.data_manager.update_chat_setting(chat_id, ["default_quiz_type"], val)
            await self._send_main_cfg_menu(query, context)
            return CFG_MAIN_MENU
        elif action == CB_ADM_SET_DEFAULT_ANNOUNCE_QUIZ:
            current_val = settings.get('default_announce_quiz', def_s['default_announce_quiz'])
            kb = [
                [InlineKeyboardButton(f"{'✅ ' if current_val else '☑️ '}Включить анонс", callback_data=f"{CB_ADM_SET_DEFAULT_ANNOUNCE_QUIZ_OPT}:true")],
                [InlineKeyboardButton(f"{'✅ ' if not current_val else '☑️ '}Выключить анонс", callback_data=f"{CB_ADM_SET_DEFAULT_ANNOUNCE_QUIZ_OPT}:false")],
                [InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADM_BACK_TO_MAIN)]
            ]
            await self._update_config_message(query, context, escape_markdown_v2("Включить анонс для /quiz по умолчанию?"), InlineKeyboardMarkup(kb))
            return CFG_MAIN_MENU
        elif action.startswith(CB_ADM_SET_DEFAULT_ANNOUNCE_QUIZ_OPT):
            val = action.split(":", 1)[1] == "true"
            self.data_manager.update_chat_setting(chat_id, ["default_announce_quiz"], val)
            await self._send_main_cfg_menu(query, context)
            return CFG_MAIN_MENU
        # ИЗМЕНЕНИЕ: Добавлен обработчик для новой кнопки
        elif action == CB_ADM_TOGGLE_AUTO_DELETE_BOT_MESSAGES:
            current_val = settings.get('auto_delete_bot_messages', def_s.get('auto_delete_bot_messages', True))
            kb = [
                [InlineKeyboardButton(f"{'✅ ' if current_val else '☑️ '}Включить автоудаление", callback_data=f"{CB_ADM_TOGGLE_AUTO_DELETE_BOT_MESSAGES_OPT}:true")],
                [InlineKeyboardButton(f"{'✅ ' if not current_val else '☑️ '}Выключить автоудаление", callback_data=f"{CB_ADM_TOGGLE_AUTO_DELETE_BOT_MESSAGES_OPT}:false")],
                [InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADM_BACK_TO_MAIN)]
            ]
            prompt_text_escaped = escape_markdown_v2("Включить автоматическое удаление сообщений бота (опросы, пояснения, анонсы и т.д.) после их завершения/истечения времени?")
            await self._update_config_message(query, context, prompt_text_escaped, InlineKeyboardMarkup(kb))
            return CFG_MAIN_MENU
        elif action.startswith(CB_ADM_TOGGLE_AUTO_DELETE_BOT_MESSAGES_OPT):
            val_str = action.split(":", 1)[1]
            new_value = val_str == "true"
            self.data_manager.update_chat_setting(chat_id, ["auto_delete_bot_messages"], new_value)
            await self._send_main_cfg_menu(query, context)
            return CFG_MAIN_MENU
        elif action in [CB_ADM_SET_DEFAULT_NUM_QUESTIONS, CB_ADM_SET_DEFAULT_OPEN_PERIOD, CB_ADM_SET_DEFAULT_ANNOUNCE_DELAY]:
            key_map = {
                CB_ADM_SET_DEFAULT_NUM_QUESTIONS: (["default_num_questions"], def_s.get('default_num_questions', 10), "Кол-во вопросов в /quiz", (1, self.app_config.max_questions_per_session), 'int'),
                CB_ADM_SET_DEFAULT_OPEN_PERIOD: (["default_open_period_seconds"], def_s.get('default_open_period_seconds', 30), "Время на ответ в /quiz (сек)", (10, 600), 'int'),
                CB_ADM_SET_DEFAULT_ANNOUNCE_DELAY: (["default_announce_delay_seconds"], def_s.get('default_announce_delay_seconds', 30), "Задержка перед анонсом /quiz (сек)", (0, 300), 'int'),
            }
            key_path, default_val_from_def_s, prompt_text_base, (min_val, max_val), val_type = key_map[action]
            current_val_resolved = settings
            for k_part in key_path: current_val_resolved = current_val_resolved.get(k_part, {}) if isinstance(current_val_resolved, dict) else None # type: ignore
            if current_val_resolved is None or not isinstance(current_val_resolved, (int, float, str, bool)): current_val_resolved = default_val_from_def_s

            current_display_val_str = str(current_val_resolved)
            if key_path in [["default_open_period_seconds"], ["default_announce_delay_seconds"]] and isinstance(current_val_resolved, int):
                current_display_val_str = format_seconds_to_human_readable_time(current_val_resolved)

            escaped_prompt_base = escape_markdown_v2(prompt_text_base)
            escaped_current_val_display = escape_markdown_v2(current_display_val_str)
            escaped_range = escape_markdown_v2(f"{min_val}–{max_val}")
            prompt_to_show = (f"Введите новое значение для `{escaped_prompt_base}`\\.\nТекущее: `{escaped_current_val_display}`\\.\nДопустимый диапазон: `{escaped_range}` сек\\.")
            if key_path == ["default_num_questions"]:
                 prompt_to_show = (f"Введите новое значение для `{escaped_prompt_base}`\\.\nТекущее: `{escaped_current_val_display}`\\.\nДопустимый диапазон: `{escaped_range}`\\.")

            context.chat_data[CTX_INPUT_TARGET_KEY_PATH] = key_path
            context.chat_data[CTX_INPUT_PROMPT] = prompt_to_show
            context.chat_data[CTX_INPUT_CONSTRAINTS] = {'min': min_val, 'max': max_val, 'type': val_type}
            await self._update_config_message(query, context, prompt_to_show, InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data=CB_ADM_BACK_TO_MAIN)]]))
            return CFG_INPUT_VALUE
        elif action == CB_ADM_MANAGE_ENABLED_CATEGORIES:
            context.chat_data[CTX_CATEGORY_SELECTION_MODE] = 'enabled_categories'
            context.chat_data[CTX_CATEGORY_SELECTION_TITLE] = escape_markdown_v2('разрешенных категорий для /quiz')
            current_selection = settings.get('enabled_categories')
            context.chat_data[CTX_TEMP_CATEGORY_SELECTION] = set(current_selection) if isinstance(current_selection, list) else (None if current_selection is None else set())
            await self._send_category_selection_menu(query, context)
            return CFG_SELECT_GENERAL_CATEGORIES
        elif action == CB_ADM_MANAGE_DISABLED_CATEGORIES:
            context.chat_data[CTX_CATEGORY_SELECTION_MODE] = 'disabled_categories'
            context.chat_data[CTX_CATEGORY_SELECTION_TITLE] = escape_markdown_v2('запрещенных категорий (для этого чата)')
            context.chat_data[CTX_TEMP_CATEGORY_SELECTION] = set(settings.get('disabled_categories', []))
            await self._send_category_selection_menu(query, context)
            return CFG_SELECT_GENERAL_CATEGORIES
        elif action == CB_ADM_GOTO_DAILY_MENU:
            await self._send_daily_cfg_menu(query, context)
            return CFG_DAILY_MENU
        elif action == CB_ADM_CONFIRM_RESET_SETTINGS:
            kb = [[InlineKeyboardButton("‼️ ДА, СБРОСИТЬ ВСЕ НАСТРОЙКИ ‼️", callback_data=CB_ADM_EXECUTE_RESET_SETTINGS)],
                  [InlineKeyboardButton("⬅️ Нет, отмена", callback_data=CB_ADM_BACK_TO_MAIN)]]
            reset_confirm_text = escape_markdown_v2("Вы уверены, что хотите сбросить ВСЕ настройки этого чата к значениям по умолчанию?")
            await self._update_config_message(query, context, reset_confirm_text, InlineKeyboardMarkup(kb))
            return CFG_CONFIRM_RESET
        return CFG_MAIN_MENU

    async def handle_input_value(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        cancel_cb_data_for_current_input = context.chat_data.get(CTX_INPUT_CANCEL_CB_DATA, CB_ADM_BACK_TO_MAIN)

        if not update.message or not update.message.text:
            prompt_text = context.chat_data.get(CTX_INPUT_PROMPT, escape_markdown_v2("Пожалуйста, введите корректное значение текстом или отмените."))
            await self._update_config_message(update, context, prompt_text, InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data=cancel_cb_data_for_current_input)]]))
            return CFG_INPUT_VALUE

        chat_id = context.chat_data.get(CTX_ADMIN_CFG_CHAT_ID)
        key_path: Optional[List[str]] = context.chat_data.get(CTX_INPUT_TARGET_KEY_PATH)
        constraints: Optional[Dict[str, Any]] = context.chat_data.get(CTX_INPUT_CONSTRAINTS)
        menu_sender_method_name = context.chat_data.get(CTX_CURRENT_MENU_SENDER_CB_NAME, "_send_main_cfg_menu")
        fallback_menu_sender_method = getattr(self, menu_sender_method_name, self._send_main_cfg_menu)

        fallback_state_after_input: str
        if menu_sender_method_name == "_send_daily_cfg_menu": fallback_state_after_input = CFG_DAILY_MENU
        elif menu_sender_method_name == "_send_daily_times_menu": fallback_state_after_input = CFG_DAILY_TIMES_MENU
        else: fallback_state_after_input = CFG_MAIN_MENU

        if not chat_id or not key_path or not constraints:
            await update.message.reply_text(escape_markdown_v2("Ошибка сессии настроек. Пожалуйста, начните заново."), parse_mode=ParseMode.MARKDOWN_V2)
            context.chat_data.clear()
            return ConversationHandler.END

        raw_value = update.message.text.strip()
        parsed_value: Any = None
        error_msg_unescaped: Optional[str] = None
        val_type = constraints.get('type', 'int')

        if val_type == 'int':
            try:
                val = int(raw_value)
                min_val, max_val = constraints.get('min'), constraints.get('max')
                if (min_val is not None and val < min_val) or \
                   (max_val is not None and val > max_val):
                    unit_for_error = "сек" if key_path in [["default_open_period_seconds"], ["default_announce_delay_seconds"], ["daily_quiz", "interval_seconds"], ["daily_quiz", "poll_open_seconds"]] else ""
                    error_msg_unescaped = f"Значение должно быть в диапазоне от {min_val} до {max_val} {unit_for_error.strip()}."
                else: parsed_value = val
            except ValueError: error_msg_unescaped = "Некорректное число. Пожалуйста, введите целое число."
        elif val_type == 'time':
            if constraints.get('action') == 'add_to_list':
                try:
                    h_str, m_str = raw_value.split(':')
                    h, m = int(h_str), int(m_str)
                    if not (0 <= h <= 23 and 0 <= m <= 59):
                        error_msg_unescaped = "Некорректное время. Часы 0-23, минуты 0-59."
                    else:
                        chat_settings_current = self.data_manager.get_chat_settings(chat_id)
                        daily_settings_current = chat_settings_current.setdefault("daily_quiz", {})
                        times_list_current: List[Dict[str,int]] = daily_settings_current.setdefault("times_msk", [])
                        new_time_entry = {"hour": h, "minute": m}

                        max_times = self.app_config.max_daily_quiz_times_per_chat
                        if len(times_list_current) >= max_times:
                            error_msg_unescaped = f"Достигнут лимит в {max_times} {pluralize(max_times, 'настройку', 'настройки', 'настроек')} времени."
                        elif new_time_entry in times_list_current:
                            error_msg_unescaped = "Такое время уже существует в списке."
                        else:
                            times_list_current.append(new_time_entry)
                            times_list_current.sort(key=lambda t: (t.get("hour",0), t.get("minute",0)))
                            self.data_manager.update_chat_setting(chat_id, ["daily_quiz", "times_msk"], times_list_current)
                            parsed_value = f"{h:02d}:{m:02d}" 
                except ValueError: error_msg_unescaped = "Неверный формат времени. Ожидается ЧЧ:ММ (например, 07:30)."
                except Exception as e_time_parse:
                    logger.error(f"Непредвиденная ошибка парсинга времени '{raw_value}': {e_time_parse}")
                    error_msg_unescaped = "Произошла ошибка при обработке введенного времени."
            else: error_msg_unescaped = "Неизвестное действие для типа 'time'."

        try: await update.message.delete()
        except Exception as e_del_input: logger.debug(f"Не удалось удалить сообщение с вводом: {e_del_input}")

        if error_msg_unescaped:
            original_prompt_text = context.chat_data.get(CTX_INPUT_PROMPT, escape_markdown_v2("Пожалуйста, введите корректное значение."))
            error_plus_prompt_text = f"{escape_markdown_v2(error_msg_unescaped)}\n\n{original_prompt_text}"
            await self._update_config_message(update, context, error_plus_prompt_text, InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data=cancel_cb_data_for_current_input)]]))
            return CFG_INPUT_VALUE

        if parsed_value is not None and val_type != 'time': 
            self.data_manager.update_chat_setting(chat_id, key_path, parsed_value)

        if key_path and key_path[0].startswith("daily_quiz") and self.daily_quiz_scheduler_ref:
            asyncio.create_task(self.daily_quiz_scheduler_ref.reschedule_job_for_chat(chat_id))

        await fallback_menu_sender_method(update, context)
        return fallback_state_after_input

    async def _send_category_selection_menu(self, query: Optional[CallbackQuery], context: ContextTypes.DEFAULT_TYPE):
        selection_mode: str = context.chat_data.get(CTX_CATEGORY_SELECTION_MODE, 'unknown')
        title_part_md_escaped: str = context.chat_data.get(CTX_CATEGORY_SELECTION_TITLE, escape_markdown_v2('категорий'))
        temp_selection: Optional[Set[str]] = context.chat_data.get(CTX_TEMP_CATEGORY_SELECTION)
        category_id_map: Dict[str, str] = {}
        context.chat_data['_category_id_map'] = category_id_map
        all_sys_categories_names = sorted(self.category_manager.get_all_category_names())

        back_cb_target = CB_ADM_BACK_TO_MAIN
        if selection_mode == 'daily_specific_categories':
            back_cb_target = CB_ADM_BACK_TO_DAILY_MENU
        context.chat_data[CTX_INPUT_CANCEL_CB_DATA] = back_cb_target

        if not all_sys_categories_names:
             no_cats_text = escape_markdown_v2(f"Нет доступных категорий для выбора {title_part_md_escaped}.")
             await self._update_config_message(query, context, no_cats_text, InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=back_cb_target)]]))
             return
        kb = []
        text_lines = [f"*{escape_markdown_v2('Выбор')} {title_part_md_escaped}:*"]
        if selection_mode == 'enabled_categories':
            text_lines.append(escape_markdown_v2("Если ни одна категория не выбрана, то для /quiz будут разрешены все системные категории (кроме глобально 'Запрещенных')."))
            is_all_enabled_mode = temp_selection is None
            prefix_for_all_mode = "✅ " if is_all_enabled_mode else "☑️ "
            kb.append([InlineKeyboardButton(f"{prefix_for_all_mode}Разрешить все системные категории", callback_data=f"{CB_ADM_CAT_CLEAR_SELECTION}:all_mode")])

        for i, cat_name_unescaped in enumerate(all_sys_categories_names):
            short_cat_id = f"c{i}"
            category_id_map[short_cat_id] = cat_name_unescaped
            is_selected_flag = temp_selection is not None and cat_name_unescaped in temp_selection
            prefix_for_category = "✅ " if is_selected_flag else "☑️ "
            button_text = cat_name_unescaped
            if len(button_text) > 30: button_text = button_text[:27] + "..."
            kb.append([InlineKeyboardButton(f"{prefix_for_category}{button_text}", callback_data=f"{CB_ADM_CAT_TOGGLE}:{short_cat_id}")])

        kb.append([InlineKeyboardButton("💾 Сохранить", callback_data=CB_ADM_CAT_SAVE_SELECTION),
                   InlineKeyboardButton("⬅️ Назад", callback_data=back_cb_target)])
        if selection_mode != 'enabled_categories' or (selection_mode == 'enabled_categories' and temp_selection is not None):
             kb.append([InlineKeyboardButton("🧹 Сбросить текущий выбор", callback_data=f"{CB_ADM_CAT_CLEAR_SELECTION}:clear_list")])
        final_text_for_menu = "\n".join(text_lines)
        await self._update_config_message(query, context, final_text_for_menu, InlineKeyboardMarkup(kb))

    async def handle_category_selection_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        query = update.callback_query
        await query.answer()
        action = query.data
        if not action: return CFG_SELECT_GENERAL_CATEGORIES
        chat_id = context.chat_data.get(CTX_ADMIN_CFG_CHAT_ID)
        selection_mode: Optional[str] = context.chat_data.get(CTX_CATEGORY_SELECTION_MODE)
        temp_selection: Optional[Set[str]] = context.chat_data.get(CTX_TEMP_CATEGORY_SELECTION)
        category_id_map: Optional[Dict[str, str]] = context.chat_data.get('_category_id_map')

        if not chat_id or not selection_mode or (not category_id_map and action.startswith(CB_ADM_CAT_TOGGLE)):
            await query.message.reply_text(escape_markdown_v2("Ошибка сессии выбора категорий. Пожалуйста, начните настройку заново."), parse_mode=ParseMode.MARKDOWN_V2)
            context.chat_data.clear()
            return ConversationHandler.END

        if action.startswith(CB_ADM_CAT_TOGGLE):
            short_cat_id_from_cb = action.split(":", 1)[1]
            cat_name_to_toggle = category_id_map.get(short_cat_id_from_cb) if category_id_map else None
            if not cat_name_to_toggle: return CFG_SELECT_GENERAL_CATEGORIES

            if selection_mode == 'enabled_categories':
                if temp_selection is None:
                    temp_selection = {cat_name_to_toggle}
                elif cat_name_to_toggle in temp_selection:
                    temp_selection.remove(cat_name_to_toggle)
                    if not temp_selection: temp_selection = None
                else: temp_selection.add(cat_name_to_toggle)
            else: 
                if temp_selection is None: temp_selection = set() 
                if cat_name_to_toggle in temp_selection: temp_selection.remove(cat_name_to_toggle)
                else: temp_selection.add(cat_name_to_toggle)
            context.chat_data[CTX_TEMP_CATEGORY_SELECTION] = temp_selection
            await self._send_category_selection_menu(query, context)
            return CFG_SELECT_GENERAL_CATEGORIES
        elif action.startswith(CB_ADM_CAT_CLEAR_SELECTION):
            clear_action_type = action.split(":",1)[1]
            if selection_mode == 'enabled_categories' and clear_action_type == 'all_mode':
                context.chat_data[CTX_TEMP_CATEGORY_SELECTION] = None
            elif clear_action_type == 'clear_list': 
                context.chat_data[CTX_TEMP_CATEGORY_SELECTION] = set()
            await self._send_category_selection_menu(query, context)
            return CFG_SELECT_GENERAL_CATEGORIES
        elif action == CB_ADM_CAT_SAVE_SELECTION:
            final_selection_to_save_in_db: Optional[List[str]]
            if temp_selection is None and selection_mode == 'enabled_categories':
                final_selection_to_save_in_db = None
            else: 
                final_selection_to_save_in_db = sorted(list(temp_selection)) if temp_selection is not None else []

            key_path_map_for_saving = {
                'enabled_categories': ["enabled_categories"],
                'disabled_categories': ["disabled_categories"],
                'daily_specific_categories': ["daily_quiz", "specific_categories"]
            }
            key_path_to_save_in_db = key_path_map_for_saving.get(selection_mode)
            if not key_path_to_save_in_db: return CFG_SELECT_GENERAL_CATEGORIES

            self.data_manager.update_chat_setting(chat_id, key_path_to_save_in_db, final_selection_to_save_in_db)
            if selection_mode == 'daily_specific_categories' and self.daily_quiz_scheduler_ref:
                 asyncio.create_task(self.daily_quiz_scheduler_ref.reschedule_job_for_chat(chat_id))

            if selection_mode == 'daily_specific_categories':
                await self._send_daily_cfg_menu(query, context)
                return CFG_DAILY_MENU
            else:
                await self._send_main_cfg_menu(query, context)
                return CFG_MAIN_MENU
        return CFG_SELECT_GENERAL_CATEGORIES

    async def _send_daily_cfg_menu(self, query_or_update: Optional[Union[Update, CallbackQuery]], context: ContextTypes.DEFAULT_TYPE):
        chat_id = context.chat_data.get(CTX_ADMIN_CFG_CHAT_ID)
        if not chat_id: return

        settings = self.data_manager.get_chat_settings(chat_id)
        display_text = self._format_settings_display(settings, part="daily")
        header_text = f"*{escape_markdown_v2('📅 Настройки Ежедневной Викторины')}*"
        prompt_text = escape_markdown_v2("Выберите параметр для изменения:")
        text_for_menu = f"{header_text}\n\n{display_text}\n\n{prompt_text}"

        daily_s_chat_current = settings.get("daily_quiz", {})
        def_daily_s_from_appconfig = self.app_config.daily_quiz_defaults
        is_daily_enabled_currently = daily_s_chat_current.get("enabled", def_daily_s_from_appconfig.get("enabled", False))

        kb = [[InlineKeyboardButton(f"{'Выключить' if is_daily_enabled_currently else 'Включить'} ежедневную викторину",
                                   callback_data=f"{CB_ADM_DAILY_TOGGLE_ENABLED}:{str(not is_daily_enabled_currently).lower()}")]]
        if is_daily_enabled_currently:
            kb.extend([
                [InlineKeyboardButton("⏰ Управление временами запуска", callback_data=CB_ADM_DAILY_MANAGE_TIMES)],
                [InlineKeyboardButton("Режим выбора категорий", callback_data=CB_ADM_DAILY_SET_CATEGORIES_MODE)],
                [InlineKeyboardButton("Кол-во вопросов", callback_data=CB_ADM_DAILY_SET_NUM_QUESTIONS)],
                [InlineKeyboardButton("Интервал между вопросами", callback_data=CB_ADM_DAILY_SET_INTERVAL_SECONDS)], 
                [InlineKeyboardButton("Время на ответ", callback_data=CB_ADM_DAILY_SET_POLL_OPEN_SECONDS)],      
            ])
        kb.append([InlineKeyboardButton("⬅️ Назад в главное меню", callback_data=CB_ADM_BACK_TO_MAIN)])

        context.chat_data[CTX_CURRENT_MENU_SENDER_CB_NAME] = "_send_daily_cfg_menu"
        context.chat_data[CTX_INPUT_CANCEL_CB_DATA] = CB_ADM_BACK_TO_DAILY_MENU
        await self._update_config_message(query_or_update, context, text_for_menu, InlineKeyboardMarkup(kb))

    async def handle_daily_menu_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        query = update.callback_query
        await query.answer()
        action = query.data
        chat_id = context.chat_data.get(CTX_ADMIN_CFG_CHAT_ID)
        if not chat_id: return ConversationHandler.END

        settings = self.data_manager.get_chat_settings(chat_id)
        daily_s_defs_app = self.app_config.daily_quiz_defaults
        context.chat_data[CTX_CURRENT_MENU_SENDER_CB_NAME] = "_send_daily_cfg_menu"
        context.chat_data[CTX_INPUT_CANCEL_CB_DATA] = CB_ADM_BACK_TO_DAILY_MENU

        if action == CB_ADM_BACK_TO_MAIN:
            await self._send_main_cfg_menu(query, context)
            return CFG_MAIN_MENU
        if action == CB_ADM_BACK_TO_DAILY_MENU:
            await self._send_daily_cfg_menu(query, context)
            return CFG_DAILY_MENU
        elif action.startswith(CB_ADM_DAILY_TOGGLE_ENABLED):
            val_str_from_cb = action.split(":", 1)[1]
            new_enabled_state = val_str_from_cb == "true"
            self.data_manager.update_chat_setting(chat_id, ["daily_quiz", "enabled"], new_enabled_state)
            if self.daily_quiz_scheduler_ref:
                asyncio.create_task(self.daily_quiz_scheduler_ref.reschedule_job_for_chat(chat_id))
            await self._send_daily_cfg_menu(query, context)
            return CFG_DAILY_MENU
        elif action == CB_ADM_DAILY_MANAGE_TIMES:
            await self._send_daily_times_menu(query, context)
            return CFG_DAILY_TIMES_MENU
        elif action == CB_ADM_DAILY_SET_CATEGORIES_MODE:
            current_daily_s_in_chat = settings.get("daily_quiz", {})
            current_mode = current_daily_s_in_chat.get("categories_mode", daily_s_defs_app['categories_mode'])
            modes_map = {"random": "🎲 Случайные", "specific": "🗂️ Выбранные", "all_enabled": "✅ Все разрешенные"}
            kb = []
            for mode_val_internal, mode_text_display in modes_map.items():
                prefix = "✅ " if mode_val_internal == current_mode else "☑️ "
                kb.append([InlineKeyboardButton(f"{prefix}{mode_text_display}", callback_data=f"{CB_ADM_DAILY_SET_CATEGORIES_MODE_OPT}:{mode_val_internal}")])
            kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADM_BACK_TO_DAILY_MENU)])
            categories_mode_prompt = escape_markdown_v2("Выберите режим категорий для ежедневной викторины:")
            await self._update_config_message(query, context, categories_mode_prompt, InlineKeyboardMarkup(kb))
            return CFG_DAILY_MENU
        elif action.startswith(CB_ADM_DAILY_SET_CATEGORIES_MODE_OPT):
            mode_val_selected = action.split(":",1)[1]
            self.data_manager.update_chat_setting(chat_id, ["daily_quiz", "categories_mode"], mode_val_selected)
            if self.daily_quiz_scheduler_ref: asyncio.create_task(self.daily_quiz_scheduler_ref.reschedule_job_for_chat(chat_id))

            if mode_val_selected == "random":
                key_path, default_val, prompt_text_base, (min_val, max_val), val_type = (
                    ["daily_quiz", "num_random_categories"], daily_s_defs_app['num_random_categories'],
                    "Кол-во случайных категорий (ежедн.)", (1,10), 'int'
                )
                current_val = settings.get("daily_quiz", {}).get(key_path[1], default_val)
                escaped_prompt_base = escape_markdown_v2(prompt_text_base)
                escaped_current_val = escape_markdown_v2(str(current_val))
                escaped_range = escape_markdown_v2(f"{min_val}–{max_val}")
                prompt_to_show = (f"Введите новое значение для `{escaped_prompt_base}`\\.\nТекущее: `{escaped_current_val}`\\.\nДопустимый диапазон: `{escaped_range}`\\.")
                context.chat_data[CTX_INPUT_TARGET_KEY_PATH] = key_path
                context.chat_data[CTX_INPUT_PROMPT] = prompt_to_show
                context.chat_data[CTX_INPUT_CONSTRAINTS] = {'min': min_val, 'max': max_val, 'type': val_type}
                await self._update_config_message(query, context, prompt_to_show, InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data=CB_ADM_BACK_TO_DAILY_MENU)]]))
                return CFG_INPUT_VALUE
            elif mode_val_selected == "specific":
                current_daily_s_for_spec = settings.get("daily_quiz", {})
                context.chat_data[CTX_CATEGORY_SELECTION_MODE] = 'daily_specific_categories'
                context.chat_data[CTX_CATEGORY_SELECTION_TITLE] = escape_markdown_v2('категорий для ежедневной викторины')
                context.chat_data[CTX_TEMP_CATEGORY_SELECTION] = set(current_daily_s_for_spec.get('specific_categories', []))
                await self._send_category_selection_menu(query, context)
                return CFG_SELECT_GENERAL_CATEGORIES
            await self._send_daily_cfg_menu(query, context)
            return CFG_DAILY_MENU
        elif action in [CB_ADM_DAILY_SET_NUM_QUESTIONS, CB_ADM_DAILY_SET_INTERVAL_SECONDS, CB_ADM_DAILY_SET_POLL_OPEN_SECONDS, CB_ADM_DAILY_SET_NUM_RANDOM_CATEGORIES]:
            key_map_daily = {
                CB_ADM_DAILY_SET_NUM_QUESTIONS: (["daily_quiz", "num_questions"], daily_s_defs_app['num_questions'], "Кол-во вопросов (ежедн.)", (1, self.app_config.max_questions_per_session), 'int'),
                CB_ADM_DAILY_SET_INTERVAL_SECONDS: (["daily_quiz", "interval_seconds"], daily_s_defs_app['interval_seconds'], "Интервал между вопросами (ежедн. сек)", (10, 3600), 'int'), 
                CB_ADM_DAILY_SET_POLL_OPEN_SECONDS: (["daily_quiz", "poll_open_seconds"], daily_s_defs_app.get('poll_open_seconds',600) , "Время на ответ (ежедн. сек)", (30, 3600 * 2), 'int'), 
                CB_ADM_DAILY_SET_NUM_RANDOM_CATEGORIES: (["daily_quiz", "num_random_categories"], daily_s_defs_app['num_random_categories'], "Кол-во случайных категорий (ежедн.)", (1,10), 'int')
            }
            key_path, default_val, prompt_text_base, (min_val, max_val), val_type = key_map_daily[action]
            current_daily_s_val_resolved = settings.get("daily_quiz", {})
            current_val = current_daily_s_val_resolved.get(key_path[1], default_val)

            current_display_val_str = str(current_val)
            unit_for_range = "сек"
            if key_path in [["daily_quiz", "interval_seconds"], ["daily_quiz", "poll_open_seconds"]] and isinstance(current_val, int):
                current_display_val_str = format_seconds_to_human_readable_time(current_val)
            elif key_path == ["daily_quiz", "num_questions"] or key_path == ["daily_quiz", "num_random_categories"]:
                unit_for_range = ""

            escaped_prompt_base = escape_markdown_v2(prompt_text_base.replace(" (сек)", "")) 
            escaped_current_val_display = escape_markdown_v2(current_display_val_str)
            escaped_range = escape_markdown_v2(f"{min_val}–{max_val}")
            prompt_to_show = (f"Введите новое значение для `{escaped_prompt_base}`\\.\nТекущее: `{escaped_current_val_display}`\\.\nДопустимый диапазон: `{escaped_range}` {escape_markdown_v2(unit_for_range)}\\.")
            if key_path == ["daily_quiz", "interval_seconds"] or key_path == ["daily_quiz", "poll_open_seconds"]:
                 prompt_to_show += escape_markdown_v2("\nЗначение вводить в секундах.")

            context.chat_data[CTX_INPUT_TARGET_KEY_PATH] = key_path
            context.chat_data[CTX_INPUT_PROMPT] = prompt_to_show
            context.chat_data[CTX_INPUT_CONSTRAINTS] = {'min': min_val, 'max': max_val, 'type': val_type}
            await self._update_config_message(query, context, prompt_to_show, InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data=CB_ADM_BACK_TO_DAILY_MENU)]]))
            return CFG_INPUT_VALUE
        return CFG_DAILY_MENU

    async def _send_daily_times_menu(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
        chat_id = context.chat_data.get(CTX_ADMIN_CFG_CHAT_ID)
        if not chat_id: return

        settings = self.data_manager.get_chat_settings(chat_id)
        daily_settings = settings.setdefault("daily_quiz", {})
        times_list: List[Dict[str, int]] = daily_settings.setdefault("times_msk", [])
        times_list.sort(key=lambda t: (t.get("hour",0), t.get("minute",0)))

        text_lines = [f"*{escape_markdown_v2('⏰ Управление временами запуска Ежедневной Викторины (МСК)')}*"]
        kb = []

        if times_list:
            text_lines.append(escape_markdown_v2("Текущие времена запуска:"))
            for i, time_entry in enumerate(times_list):
                h, m = time_entry.get("hour",0), time_entry.get("minute",0)
                time_str_escaped = escape_markdown_v2(f"{h:02d}:{m:02d}")
                text_lines.append(f"{escape_markdown_v2(f'{i+1}.')} {time_str_escaped}")
                kb.append([InlineKeyboardButton(f"❌ Удалить {time_str_escaped}", callback_data=f"{CB_ADM_DAILY_TIME_REMOVE}:{i}")])
        else:
            text_lines.append(escape_markdown_v2("Времена запуска еще не добавлены."))

        max_times_allowed = self.app_config.max_daily_quiz_times_per_chat
        if len(times_list) < max_times_allowed:
            kb.append([InlineKeyboardButton("➕ Добавить время", callback_data=CB_ADM_DAILY_TIME_ADD)])
        else:
             text_lines.append(escape_markdown_v2(f"Достигнут лимит в {max_times_allowed} {pluralize(max_times_allowed, 'настройку', 'настройки', 'настроек')} времени."))

        kb.append([InlineKeyboardButton("⬅️ Назад в настройки Ежедн.Викторины", callback_data=CB_ADM_BACK_TO_DAILY_MENU)])

        final_text = "\n".join(text_lines)
        context.chat_data[CTX_CURRENT_MENU_SENDER_CB_NAME] = "_send_daily_times_menu"
        context.chat_data[CTX_INPUT_CANCEL_CB_DATA] = CB_ADM_DAILY_TIME_BACK_TO_LIST
        await self._update_config_message(query, context, final_text, InlineKeyboardMarkup(kb))

    async def handle_daily_times_menu_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        query = update.callback_query
        await query.answer()
        action = query.data
        chat_id = context.chat_data.get(CTX_ADMIN_CFG_CHAT_ID)
        if not chat_id: return ConversationHandler.END

        settings = self.data_manager.get_chat_settings(chat_id)
        daily_settings = settings.setdefault("daily_quiz", {})
        times_list: List[Dict[str, int]] = daily_settings.setdefault("times_msk", [])
        times_list.sort(key=lambda t: (t.get("hour",0), t.get("minute",0)))

        context.chat_data[CTX_CURRENT_MENU_SENDER_CB_NAME] = "_send_daily_times_menu"
        context.chat_data[CTX_INPUT_CANCEL_CB_DATA] = CB_ADM_DAILY_TIME_BACK_TO_LIST

        if action == CB_ADM_BACK_TO_DAILY_MENU:
            await self._send_daily_cfg_menu(query, context)
            return CFG_DAILY_MENU
        elif action == CB_ADM_DAILY_TIME_BACK_TO_LIST:
            await self._send_daily_times_menu(query, context)
            return CFG_DAILY_TIMES_MENU
        elif action == CB_ADM_DAILY_TIME_ADD:
            max_times = self.app_config.max_daily_quiz_times_per_chat
            if len(times_list) >= max_times:
                await query.answer(f"Достигнут лимит ({max_times}) времен.", show_alert=True)
                await self._send_daily_times_menu(query, context)
                return CFG_DAILY_TIMES_MENU

            prompt_for_new_time = escape_markdown_v2("Введите новое время для ежедневной викторины в формате ЧЧ:ММ (например, 14:30).")
            context.chat_data[CTX_INPUT_TARGET_KEY_PATH] = ["daily_quiz", "times_msk"]
            context.chat_data[CTX_INPUT_PROMPT] = prompt_for_new_time
            context.chat_data[CTX_INPUT_CONSTRAINTS] = {'type': 'time', 'action': 'add_to_list'}
            await self._update_config_message(query, context, prompt_for_new_time, InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data=CB_ADM_DAILY_TIME_BACK_TO_LIST)]]))
            return CFG_INPUT_VALUE
        elif action.startswith(CB_ADM_DAILY_TIME_REMOVE):
            try:
                time_index_to_remove_str = action.split(":",1)[1]
                time_index_to_remove = int(time_index_to_remove_str)
                if 0 <= time_index_to_remove < len(times_list):
                    removed_time = times_list.pop(time_index_to_remove)
                    logger.info(f"Удалено время {removed_time} из списка для чата {chat_id}")
                    self.data_manager.update_chat_setting(chat_id, ["daily_quiz", "times_msk"], times_list)
                    if self.daily_quiz_scheduler_ref:
                        asyncio.create_task(self.daily_quiz_scheduler_ref.reschedule_job_for_chat(chat_id))
                else: await query.answer("Ошибка: неверный индекс времени для удаления.", show_alert=True)
            except (ValueError, IndexError) as e:
                logger.error(f"Ошибка при удалении времени: {e}. Action: {action}")
                await query.answer("Ошибка при удалении времени.", show_alert=True)
            await self._send_daily_times_menu(query, context)
            return CFG_DAILY_TIMES_MENU
        return CFG_DAILY_TIMES_MENU

    async def handle_confirm_reset_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        query = update.callback_query
        await query.answer()
        action = query.data
        chat_id = context.chat_data.get(CTX_ADMIN_CFG_CHAT_ID)
        if not chat_id: return ConversationHandler.END

        context.chat_data[CTX_CURRENT_MENU_SENDER_CB_NAME] = "_send_main_cfg_menu"
        context.chat_data[CTX_INPUT_CANCEL_CB_DATA] = CB_ADM_BACK_TO_MAIN

        if action == CB_ADM_EXECUTE_RESET_SETTINGS:
            self.data_manager.reset_chat_settings(chat_id)
            if self.daily_quiz_scheduler_ref:
                asyncio.create_task(self.daily_quiz_scheduler_ref.reschedule_job_for_chat(chat_id))
            await self._send_main_cfg_menu(query, context)
            return CFG_MAIN_MENU
        elif action == CB_ADM_BACK_TO_MAIN:
            await self._send_main_cfg_menu(query, context)
            return CFG_MAIN_MENU
        return CFG_CONFIRM_RESET

    async def view_chat_config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_chat: return
        chat_id = update.effective_chat.id
        settings = self.data_manager.get_chat_settings(chat_id)
        settings_text = self._format_settings_display(settings, part="all")
        header = f"*{escape_markdown_v2('Текущие настройки для этого чата:')}*"
        final_text = f"{header}\n\n{settings_text}"
        if len(final_text) > 4096:
            parts = []
            current_part = header + "\n\n"
            for line in settings_text.split('\n'):
                if len(current_part) + len(line) + 1 <= 4096:
                    current_part += line + '\n'
                else:
                    parts.append(current_part.strip())
                    current_part = line + '\n'
            if current_part.strip(): parts.append(current_part.strip())

            for i, part_text in enumerate(parts):
                try:
                    await update.message.reply_text(part_text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)
                except Exception as e_part:
                    logger.error(f"Не удалось отправить часть ({i+1}) настроек: {e_part}")
                    await update.message.reply_text(escape_markdown_v2("Текст настроек слишком длинный, не удалось отправить частями."), parse_mode=ParseMode.MARKDOWN_V2)
                    break
        else:
            await update.message.reply_text(final_text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)

    async def cancel_config_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        final_message_unescaped = "Настройка отменена."
        final_message_escaped = escape_markdown_v2(final_message_unescaped)
        query = update.callback_query
        chat_id_for_ops = context.chat_data.get(CTX_ADMIN_CFG_CHAT_ID)
        original_menu_msg_id = context.chat_data.get(CTX_ADMIN_CFG_MSG_ID)

        if query:
            await query.answer()
            if query.message and original_menu_msg_id == query.message.message_id:
                try: await query.edit_message_text(final_message_escaped, reply_markup=None, parse_mode=ParseMode.MARKDOWN_V2)
                except BadRequest as e_br:
                    if "Message is not modified" not in str(e_br).lower(): logger.warning(f"Ошибка BadRequest при редактировании на отмену: {e_br}")
                except Exception as e_edit_cancel: logger.error(f"Ошибка редактирования при отмене диалога (кнопка): {e_edit_cancel}")
            elif chat_id_for_ops :
                 try: await context.bot.send_message(chat_id_for_ops, final_message_escaped, parse_mode=ParseMode.MARKDOWN_V2)
                 except Exception as e_send_cb_other: logger.error(f"Не удалось отправить сообщение отмены (кнопка, другое сообщение): {e_send_cb_other}")
        elif update.message:
            if chat_id_for_ops:
                if original_menu_msg_id:
                    try: await context.bot.delete_message(chat_id_for_ops, original_menu_msg_id)
                    except Exception as e_del_cfg_cmd: logger.debug(f"Не удалось удалить сообщение конфига при отмене (команда /cancel): {e_del_cfg_cmd}")
                try: await context.bot.send_message(chat_id_for_ops, final_message_escaped, parse_mode=ParseMode.MARKDOWN_V2, reply_to_message_id=update.message.message_id)
                except Exception as e_send_cancel_cmd: logger.error(f"Не удалось отправить сообщение отмены (команда /cancel): {e_send_cancel_cmd}")
            else:
                try: await update.message.reply_text(final_message_escaped, parse_mode=ParseMode.MARKDOWN_V2)
                except Exception as e_send_reply_cancel: logger.error(f"Не удалось отправить reply на отмену (команда /cancel): {e_send_reply_cancel}")

        logger.info(f"Диалог настройки отменен для чата {chat_id_for_ops if chat_id_for_ops else 'N/A'}.")
        context.chat_data.clear()
        return ConversationHandler.END

    def get_handlers(self) -> List[Any]:
        cancel_handler_for_conv = CommandHandler(self.app_config.commands.cancel, self.cancel_config_conversation)

        conv_handler = ConversationHandler(
            entry_points=[CommandHandler(self.app_config.commands.admin_settings, self.admin_settings_entry)],
            states={
                CFG_MAIN_MENU: [CallbackQueryHandler(self.handle_main_menu_callbacks, pattern=f"^{CB_ADM_}")],
                CFG_INPUT_VALUE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_input_value),
                    CallbackQueryHandler(self.handle_main_menu_callbacks, pattern=f"^{CB_ADM_BACK_TO_MAIN}$"),
                    CallbackQueryHandler(self.handle_daily_menu_callbacks, pattern=f"^{CB_ADM_BACK_TO_DAILY_MENU}$"),
                    CallbackQueryHandler(self.handle_daily_times_menu_callbacks, pattern=f"^{CB_ADM_DAILY_TIME_BACK_TO_LIST}$")
                ],
                CFG_SELECT_GENERAL_CATEGORIES: [
                    CallbackQueryHandler(self.handle_category_selection_callback, pattern=f"^{CB_ADM_CAT_SEL_}"),
                    CallbackQueryHandler(self.handle_main_menu_callbacks, pattern=f"^{CB_ADM_BACK_TO_MAIN}$"),
                    CallbackQueryHandler(self.handle_daily_menu_callbacks, pattern=f"^{CB_ADM_BACK_TO_DAILY_MENU}$")
                ],
                CFG_DAILY_MENU: [CallbackQueryHandler(self.handle_daily_menu_callbacks, pattern=f"^{CB_ADM_}")],
                CFG_CONFIRM_RESET: [CallbackQueryHandler(self.handle_confirm_reset_callbacks, pattern=f"^{CB_ADM_}")],
                CFG_DAILY_TIMES_MENU: [
                    CallbackQueryHandler(self.handle_daily_times_menu_callbacks, pattern=f"^{CB_ADM_DAILY_TIME_}"),
                    CallbackQueryHandler(self.handle_daily_menu_callbacks, pattern=f"^{CB_ADM_BACK_TO_DAILY_MENU}$")
                ],
            },
            fallbacks=[cancel_handler_for_conv],
            per_chat=True, per_user=True, name="admin_settings_conversation", persistent=True, allow_reentry=True
        )
        return [
            conv_handler,
            CommandHandler(self.app_config.commands.view_chat_config, self.view_chat_config_command),
        ]
