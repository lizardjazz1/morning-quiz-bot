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
from state import BotState
from data_manager import DataManager
from modules.category_manager import CategoryManager
from utils import is_user_admin_in_update, escape_markdown_v2, pluralize

if TYPE_CHECKING:
    from .daily_quiz_scheduler import DailyQuizScheduler

logger = logging.getLogger(__name__)

(
    CFG_MAIN_MENU, CFG_INPUT_VALUE,
    CFG_SELECT_GENERAL_CATEGORIES,
    CFG_DAILY_MENU,
    CFG_DAILY_SELECT_CATEGORIES_MODE,
    CFG_CONFIRM_RESET
) = map(str, range(6))

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
CB_ADM_DAILY_SET_TIME = f"{CB_ADM_}daily_set_time"
CB_ADM_DAILY_SET_CATEGORIES_MODE = f"{CB_ADM_}daily_set_cat_mode"
CB_ADM_DAILY_SET_CATEGORIES_MODE_OPT = f"{CB_ADM_}daily_set_cat_mode_opt"
CB_ADM_DAILY_SET_NUM_RANDOM_CATEGORIES = f"{CB_ADM_}daily_set_num_rand_cat"
CB_ADM_DAILY_MANAGE_SPECIFIC_CATEGORIES = f"{CB_ADM_}daily_manage_spec_cat"
CB_ADM_DAILY_SET_NUM_QUESTIONS = f"{CB_ADM_}daily_set_num_q"
CB_ADM_DAILY_SET_INTERVAL_SECONDS = f"{CB_ADM_}daily_set_interval"
CB_ADM_DAILY_SET_POLL_OPEN_SECONDS = f"{CB_ADM_}daily_set_poll_open"

CTX_ADMIN_CFG_CHAT_ID = 'admin_cfg_chat_id'
CTX_ADMIN_CFG_MSG_ID = 'admin_cfg_msg_id'
CTX_INPUT_TARGET_KEY_PATH = 'input_target_key_path'
CTX_INPUT_PROMPT = 'input_prompt_text'
CTX_INPUT_CONSTRAINTS = 'input_constraints_dict'
CTX_CURRENT_MENU_SENDER_CB_NAME = 'current_menu_sender_callback_name'
CTX_TEMP_CATEGORY_SELECTION = 'temp_category_selection_set'
CTX_CATEGORY_SELECTION_MODE = 'category_selection_mode_str'
CTX_CATEGORY_SELECTION_TITLE = 'category_selection_title_str'

class ConfigHandlers:
    def __init__(self, app_config: AppConfig, state: BotState, data_manager: DataManager,
                 category_manager: CategoryManager, application: Application):
        self.app_config = app_config
        self.state = state
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
            logger.error("_update_config_message: chat_id не найден.")
            return

        current_message: Optional[Message] = None
        is_callback_query = isinstance(query_or_update, CallbackQuery)
        
        if is_callback_query and query_or_update.message: # type: ignore
            current_message = query_or_update.message # type: ignore
        elif isinstance(query_or_update, Update) and query_or_update.message:
            current_message = query_or_update.message
        
        if current_message and target_msg_id == current_message.message_id:
            try:
                await current_message.edit_text(text=new_text, reply_markup=new_markup, parse_mode=ParseMode.MARKDOWN_V2)
                if is_callback_query: await query_or_update.answer() # type: ignore
                return
            except BadRequest as e:
                if "Message is not modified" in str(e).lower():
                    if is_callback_query: await query_or_update.answer() # type: ignore
                    return
                logger.warning(f"Не удалось отредактировать {target_msg_id} в {chat_id}: {e}. Отправка нового.")
            except Exception as e_edit:
                logger.error(f"Ошибка редактирования {target_msg_id}: {e_edit}. Отправка нового.")
        
        if target_msg_id and (not current_message or target_msg_id != current_message.message_id):
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=target_msg_id)
            except Exception as e_del:
                logger.debug(f"Не удалось удалить старое меню {target_msg_id}: {e_del}")
        
        try:
            if current_message and isinstance(query_or_update, Update): # Отвечаем на команду/сообщение
                 sent_msg = await current_message.reply_text(text=new_text, reply_markup=new_markup, parse_mode=ParseMode.MARKDOWN_V2)
            elif current_message and is_callback_query: # Если коллбэк от другого сообщения, отправляем новое
                 sent_msg = await current_message.chat.send_message(text=new_text, reply_markup=new_markup, parse_mode=ParseMode.MARKDOWN_V2)
            else: # Общий случай отправки, если нет контекста сообщения
                 sent_msg = await context.bot.send_message(chat_id=chat_id, text=new_text, reply_markup=new_markup, parse_mode=ParseMode.MARKDOWN_V2)
            context.chat_data[CTX_ADMIN_CFG_MSG_ID] = sent_msg.message_id
            if is_callback_query: await query_or_update.answer() # type: ignore
        except Exception as e_send:
            logger.error(f"Не удалось отправить новое меню в чат {chat_id}: {e_send}")


    async def admin_settings_entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        if not update.message or not update.effective_chat or not update.effective_user:
            return ConversationHandler.END
        if not await self._is_admin(update, context):
            await update.message.reply_text("Эта команда доступна только администраторам чата.")
            return ConversationHandler.END

        context.chat_data.clear()
        context.chat_data[CTX_ADMIN_CFG_CHAT_ID] = update.effective_chat.id
        
        await self._send_main_cfg_menu(update, context)
        return CFG_MAIN_MENU

    async def _send_main_cfg_menu(self, query_or_update: Optional[Union[Update, CallbackQuery]], context: ContextTypes.DEFAULT_TYPE):
        chat_id = context.chat_data[CTX_ADMIN_CFG_CHAT_ID]
        settings = self.data_manager.get_chat_settings(chat_id)
        
        display_text = self._format_settings_display(settings, part="main")
        daily_brief = self._format_settings_display(settings, part="daily_brief")

        text = (f"🛠️ *Админ. настройки чата*\n\n{display_text}\n\n{daily_brief}\n\nВыберите параметр для изменения:")
        kb_buttons = [
            [InlineKeyboardButton("Тип /quiz", callback_data=CB_ADM_SET_DEFAULT_QUIZ_TYPE),
             InlineKeyboardButton("Кол-во /quiz", callback_data=CB_ADM_SET_DEFAULT_NUM_QUESTIONS)],
            [InlineKeyboardButton("Время ответа /quiz", callback_data=CB_ADM_SET_DEFAULT_OPEN_PERIOD)],
            [InlineKeyboardButton("Анонс /quiz", callback_data=CB_ADM_SET_DEFAULT_ANNOUNCE_QUIZ),
             InlineKeyboardButton("Задержка анонса", callback_data=CB_ADM_SET_DEFAULT_ANNOUNCE_DELAY)],
            [InlineKeyboardButton("Разреш. категории /quiz", callback_data=CB_ADM_MANAGE_ENABLED_CATEGORIES)],
            [InlineKeyboardButton("Запрещ. категории (все)", callback_data=CB_ADM_MANAGE_DISABLED_CATEGORIES)],
            [InlineKeyboardButton("Ежедневная Викторина ➡️", callback_data=CB_ADM_GOTO_DAILY_MENU)],
            [InlineKeyboardButton("Сбросить всё к по умолчанию", callback_data=CB_ADM_CONFIRM_RESET_SETTINGS)],
            [InlineKeyboardButton("✅ Завершить настройку", callback_data=CB_ADM_FINISH_CONFIG)],
        ]
        context.chat_data[CTX_CURRENT_MENU_SENDER_CB_NAME] = "_send_main_cfg_menu"
        await self._update_config_message(query_or_update, context, text, InlineKeyboardMarkup(kb_buttons))

    def _format_settings_display(self, settings: Dict[str, Any], part: str = "main") -> str:
        lines = []
        def_chat_s = self.app_config.default_chat_settings

        if part == "main" or part == "all":
            lines.append(f"*Тип /quiz по умолчанию:* `{escape_markdown_v2(settings.get('default_quiz_type', def_chat_s.get('default_quiz_type')))}`")
            lines.append(f"*Кол-во вопросов /quiz:* `{settings.get('default_num_questions', def_chat_s.get('default_num_questions'))}`")
            lines.append(f"*Время на ответ /quiz (сек):* `{settings.get('default_open_period_seconds', def_chat_s.get('default_open_period_seconds'))}`")
            lines.append(f"*Анонс /quiz:* `{'Вкл' if settings.get('default_announce_quiz', def_chat_s.get('default_announce_quiz')) else 'Выкл'}`")
            lines.append(f"*Задержка анонса (сек):* `{settings.get('default_announce_delay_seconds', def_chat_s.get('default_announce_delay_seconds'))}`")

            en_cats = settings.get('enabled_categories')
            en_str = escape_markdown_v2(", ".join(sorted(en_cats))) if en_cats else "_Все системные_"
            lines.append(f"*Разрешенные категории для /quiz:* {en_str}")

            dis_cats = settings.get('disabled_categories', def_chat_s.get('disabled_categories',[]))
            dis_str = escape_markdown_v2(", ".join(sorted(dis_cats))) if dis_cats else "_Нет_"
            lines.append(f"*Запрещенные категории (для всех квизов):* {dis_str}")

        if part == "daily_brief" or part == "daily" or part == "all":
            daily_cfg_chat = settings.get("daily_quiz", {})
            def_daily_s_appconfig = self.app_config.daily_quiz_defaults
            enabled = daily_cfg_chat.get("enabled", def_daily_s_appconfig.get("enabled", False))
            lines.append(f"\n*Ежедневная викторина:* `{'Включена' if enabled else 'Выключена'}`")
            if enabled and part == "daily_brief":
                h = daily_cfg_chat.get('hour_msk', def_daily_s_appconfig['hour_msk'])
                m = daily_cfg_chat.get('minute_msk', def_daily_s_appconfig['minute_msk'])
                lines.append(f"  (Запуск в `{h:02d}:{m:02d}` МСК)")

        if part == "daily" and enabled:
            daily_cfg_chat = settings.get("daily_quiz", {})
            def_daily_s_appconfig = self.app_config.daily_quiz_defaults

            h = daily_cfg_chat.get('hour_msk', def_daily_s_appconfig['hour_msk'])
            m = daily_cfg_chat.get('minute_msk', def_daily_s_appconfig['minute_msk'])
            lines.append(f"  *Время запуска (МСК):* `{h:02d}:{m:02d}`")

            cat_mode = daily_cfg_chat.get('categories_mode', def_daily_s_appconfig['categories_mode'])
            cat_mode_display = {"random": "Случайные", "specific": "Выбранные", "all_enabled": "Все разрешенные"}.get(cat_mode, cat_mode)
            lines.append(f"  *Режим категорий:* `{escape_markdown_v2(cat_mode_display)}`")

            if cat_mode == "random":
                num_rc = daily_cfg_chat.get('num_random_categories', def_daily_s_appconfig['num_random_categories'])
                lines.append(f"    *Кол-во случайных категорий:* `{num_rc}`")
            elif cat_mode == "specific":
                spec_c = daily_cfg_chat.get('specific_categories', def_daily_s_appconfig['specific_categories'])
                spec_c_str = escape_markdown_v2(", ".join(sorted(spec_c))) if spec_c else "_Не выбраны_"
                lines.append(f"    *Выбранные категории:* {spec_c_str}")

            lines.append(f"  *Кол-во вопросов:* `{daily_cfg_chat.get('num_questions', def_daily_s_appconfig['num_questions'])}`")
            lines.append(f"  *Интервал между вопросами (сек):* `{daily_cfg_chat.get('interval_seconds', def_daily_s_appconfig['interval_seconds'])}`")
            lines.append(f"  *Время на ответ (сек):* `{daily_cfg_chat.get('poll_open_seconds', def_daily_s_appconfig['open_period_seconds'])}`")
        
        return "\n".join(lines)

    async def handle_main_menu_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        query = update.callback_query
        action = query.data
        chat_id = context.chat_data[CTX_ADMIN_CFG_CHAT_ID]
        settings = self.data_manager.get_chat_settings(chat_id)
        def_s = self.app_config.default_chat_settings

        context.chat_data[CTX_CURRENT_MENU_SENDER_CB_NAME] = "_send_main_cfg_menu"

        if action == CB_ADM_FINISH_CONFIG:
            await query.edit_message_text("Настройки сохранены. Завершение.")
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
            await self._update_config_message(query, context, "Выберите тип /quiz по умолчанию:", InlineKeyboardMarkup(kb))
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
            await self._update_config_message(query, context, "Включить анонс для /quiz по умолчанию?", InlineKeyboardMarkup(kb))
            return CFG_MAIN_MENU

        elif action.startswith(CB_ADM_SET_DEFAULT_ANNOUNCE_QUIZ_OPT):
            val = action.split(":", 1)[1] == "true"
            self.data_manager.update_chat_setting(chat_id, ["default_announce_quiz"], val)
            await self._send_main_cfg_menu(query, context)
            return CFG_MAIN_MENU

        elif action in [CB_ADM_SET_DEFAULT_NUM_QUESTIONS, CB_ADM_SET_DEFAULT_OPEN_PERIOD, CB_ADM_SET_DEFAULT_ANNOUNCE_DELAY]:
            key_map = {
                CB_ADM_SET_DEFAULT_NUM_QUESTIONS: (["default_num_questions"], def_s.get('default_num_questions', 10), "Кол-во вопросов в /quiz", (1, self.app_config.max_questions_per_session), 'int'),
                CB_ADM_SET_DEFAULT_OPEN_PERIOD: (["default_open_period_seconds"], def_s.get('default_open_period_seconds', 30), "Время на ответ в /quiz (сек)", (10, 600), 'int'),
                CB_ADM_SET_DEFAULT_ANNOUNCE_DELAY: (["default_announce_delay_seconds"], def_s.get('default_announce_delay_seconds', 30), "Задержка перед анонсом /quiz (сек)", (0, 300), 'int'),
            }
            key_path, default_val_from_def_s, prompt_text, (min_val, max_val), val_type = key_map[action]
            current_val = settings.get(key_path[0], default_val_from_def_s)

            context.chat_data[CTX_INPUT_TARGET_KEY_PATH] = key_path
            context.chat_data[CTX_INPUT_PROMPT] = f"Введите новое значение для '{prompt_text}'.\nТекущее: {current_val}. Допустимый диапазон: {min_val}–{max_val}."
            context.chat_data[CTX_INPUT_CONSTRAINTS] = {'min': min_val, 'max': max_val, 'type': val_type}
            
            await self._update_config_message(query, context, context.chat_data[CTX_INPUT_PROMPT], InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена (назад в гл. меню)", callback_data=CB_ADM_BACK_TO_MAIN)]]))
            return CFG_INPUT_VALUE

        elif action == CB_ADM_MANAGE_ENABLED_CATEGORIES:
            context.chat_data[CTX_CATEGORY_SELECTION_MODE] = 'enabled_categories'
            context.chat_data[CTX_CATEGORY_SELECTION_TITLE] = 'разрешенных категорий для /quiz'
            current_selection = settings.get('enabled_categories') 
            context.chat_data[CTX_TEMP_CATEGORY_SELECTION] = set(current_selection) if current_selection is not None else None
            await self._send_category_selection_menu(query, context)
            return CFG_SELECT_GENERAL_CATEGORIES

        elif action == CB_ADM_MANAGE_DISABLED_CATEGORIES:
            context.chat_data[CTX_CATEGORY_SELECTION_MODE] = 'disabled_categories'
            context.chat_data[CTX_CATEGORY_SELECTION_TITLE] = 'запрещенных категорий (для всех квизов)'
            context.chat_data[CTX_TEMP_CATEGORY_SELECTION] = set(settings.get('disabled_categories', []))
            await self._send_category_selection_menu(query, context)
            return CFG_SELECT_GENERAL_CATEGORIES

        elif action == CB_ADM_GOTO_DAILY_MENU:
            await self._send_daily_cfg_menu(query, context)
            return CFG_DAILY_MENU

        elif action == CB_ADM_CONFIRM_RESET_SETTINGS:
            kb = [[InlineKeyboardButton("‼️ ДА, СБРОСИТЬ ВСЕ НАСТРОЙКИ ‼️", callback_data=CB_ADM_EXECUTE_RESET_SETTINGS)],
                  [InlineKeyboardButton("⬅️ Нет, отмена", callback_data=CB_ADM_BACK_TO_MAIN)]]
            await self._update_config_message(query, context, "Вы уверены, что хотите сбросить ВСЕ настройки этого чата к значениям по умолчанию?", InlineKeyboardMarkup(kb))
            return CFG_CONFIRM_RESET

        await query.answer()
        return CFG_MAIN_MENU

    async def handle_input_value(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        if not update.message or not update.message.text:
            await update.message.reply_text("Пожалуйста, введите значение.")
            return CFG_INPUT_VALUE

        chat_id = context.chat_data[CTX_ADMIN_CFG_CHAT_ID]
        key_path: List[str] = context.chat_data[CTX_INPUT_TARGET_KEY_PATH]
        constraints: Dict[str, Any] = context.chat_data[CTX_INPUT_CONSTRAINTS]
        
        menu_sender_method_name = context.chat_data.get(CTX_CURRENT_MENU_SENDER_CB_NAME)
        menu_sender_cb = getattr(self, menu_sender_method_name, self._send_main_cfg_menu)
        fallback_state = CFG_DAILY_MENU if menu_sender_method_name == "_send_daily_cfg_menu" else CFG_MAIN_MENU

        raw_value = update.message.text.strip()
        parsed_value: Any = None
        error_msg: Optional[str] = None
        val_type = constraints.get('type', 'int')

        if val_type == 'int':
            try:
                val = int(raw_value)
                min_val, max_val = constraints.get('min'), constraints.get('max')
                if (min_val is not None and val < min_val) or \
                   (max_val is not None and val > max_val):
                    error_msg = f"Значение должно быть в диапазоне от {min_val} до {max_val}."
                else:
                    parsed_value = val
            except ValueError:
                error_msg = "Некорректное число. Пожалуйста, введите целое число."
        
        elif val_type == 'time':
            try:
                h_str, m_str = raw_value.split(':')
                h, m = int(h_str), int(m_str)
                if not (0 <= h <= 23 and 0 <= m <= 59):
                    error_msg = "Некорректное время. Часы 0-23, минуты 0-59."
                else:
                    self.data_manager.update_chat_setting(chat_id, key_path + ["hour_msk"], h)
                    self.data_manager.update_chat_setting(chat_id, key_path + ["minute_msk"], m)
            except ValueError:
                error_msg = "Неверный формат времени. Ожидается ЧЧ:ММ (например, 07:30)."
            except Exception as e_time:
                logger.error(f"Ошибка парсинга времени '{raw_value}': {e_time}")
                error_msg = "Произошла ошибка при обработке времени."
        
        try: await update.message.delete()
        except Exception as e_del_input: logger.debug(f"Не удалось удалить сообщение с вводом: {e_del_input}")

        if error_msg:
            prompt_text = context.chat_data.get(CTX_INPUT_PROMPT, "Пожалуйста, введите корректное значение:")
            cancel_button_cb = CB_ADM_BACK_TO_MAIN if fallback_state == CFG_MAIN_MENU else CB_ADM_BACK_TO_DAILY_MENU
            await self._update_config_message(update, context, f"{error_msg}\n{prompt_text}", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data=cancel_button_cb)]]))
            return CFG_INPUT_VALUE

        if parsed_value is not None and val_type != 'time':
            self.data_manager.update_chat_setting(chat_id, key_path, parsed_value)

        if key_path and key_path[0].startswith("daily_quiz") and self.daily_quiz_scheduler_ref:
            asyncio.create_task(self.daily_quiz_scheduler_ref.reschedule_job_for_chat(chat_id))
        
        await menu_sender_cb(update, context)
        return fallback_state

    async def _send_category_selection_menu(self, query: Optional[CallbackQuery], context: ContextTypes.DEFAULT_TYPE):
        selection_mode: str = context.chat_data[CTX_CATEGORY_SELECTION_MODE]
        title_part: str = context.chat_data[CTX_CATEGORY_SELECTION_TITLE]
        temp_selection: Optional[Set[str]] = context.chat_data[CTX_TEMP_CATEGORY_SELECTION]

        all_sys_categories = sorted(self.category_manager.get_all_category_names())
        back_cb_data = CB_ADM_BACK_TO_MAIN if selection_mode != 'daily_specific_categories' else CB_ADM_BACK_TO_DAILY_MENU

        if not all_sys_categories:
             await self._update_config_message(query, context, f"Нет доступных категорий для выбора {title_part}.", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=back_cb_data)]]))
             return

        kb = []
        text_lines = [f"Выберите {title_part}:"]
        
        if selection_mode == 'enabled_categories':
            text_lines.append("Если ни одна не выбрана, разрешены все (кроме 'Запрещенных').")
            is_all_enabled_mode = temp_selection is None
            prefix_all = "✅ " if is_all_enabled_mode else "☑️ "
            kb.append([InlineKeyboardButton(f"{prefix_all}Все категории разрешены", callback_data=f"{CB_ADM_CAT_CLEAR_SELECTION}:all_mode")])

        for cat_name in all_sys_categories:
            is_selected = temp_selection is not None and cat_name in temp_selection
            prefix = "✅ " if is_selected else "☑️ "
            kb.append([InlineKeyboardButton(f"{prefix}{escape_markdown_v2(cat_name)}", callback_data=f"{CB_ADM_CAT_TOGGLE}:{cat_name}")])
        
        kb.append([InlineKeyboardButton("💾 Сохранить выбранное", callback_data=CB_ADM_CAT_SAVE_SELECTION),
                   InlineKeyboardButton("⬅️ Назад", callback_data=back_cb_data)])
        
        if selection_mode != 'enabled_categories':
             kb.append([InlineKeyboardButton("🧹 Очистить текущий список", callback_data=f"{CB_ADM_CAT_CLEAR_SELECTION}:clear_list")])

        await self._update_config_message(query, context, "\n".join(text_lines), InlineKeyboardMarkup(kb))

    async def handle_category_selection_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        query = update.callback_query
        action = query.data
        chat_id = context.chat_data[CTX_ADMIN_CFG_CHAT_ID]
        selection_mode: str = context.chat_data[CTX_CATEGORY_SELECTION_MODE]
        temp_selection: Optional[Set[str]] = context.chat_data.get(CTX_TEMP_CATEGORY_SELECTION)

        if action.startswith(CB_ADM_CAT_TOGGLE):
            cat_name = action.split(":", 1)[1]
            if selection_mode == 'enabled_categories':
                if temp_selection is None: temp_selection = {cat_name}
                elif cat_name in temp_selection:
                    temp_selection.remove(cat_name)
                    if not temp_selection: temp_selection = None
                else: temp_selection.add(cat_name)
            else:
                if temp_selection is None: temp_selection = set()
                if cat_name in temp_selection: temp_selection.remove(cat_name)
                else: temp_selection.add(cat_name)
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
            final_selection_to_save: Optional[List[str]] = sorted(list(temp_selection)) if temp_selection is not None else None
            key_path_map = {
                'enabled_categories': ["enabled_categories"],
                'disabled_categories': ["disabled_categories"],
                'daily_specific_categories': ["daily_quiz", "specific_categories"]
            }
            key_path_to_save = key_path_map[selection_mode]
            self.data_manager.update_chat_setting(chat_id, key_path_to_save, final_selection_to_save)

            if selection_mode == 'daily_specific_categories' and self.daily_quiz_scheduler_ref:
                 asyncio.create_task(self.daily_quiz_scheduler_ref.reschedule_job_for_chat(chat_id))
            
            await query.answer("Выбор сохранен!")
            if selection_mode == 'daily_specific_categories':
                await self._send_daily_cfg_menu(query, context)
                return CFG_DAILY_MENU
            else:
                await self._send_main_cfg_menu(query, context)
                return CFG_MAIN_MENU
        
        await query.answer()
        return CFG_SELECT_GENERAL_CATEGORIES

    async def _send_daily_cfg_menu(self, query_or_update: Optional[Union[Update, CallbackQuery]], context: ContextTypes.DEFAULT_TYPE):
        chat_id = context.chat_data[CTX_ADMIN_CFG_CHAT_ID]
        settings = self.data_manager.get_chat_settings(chat_id)
        display_text = self._format_settings_display(settings, part="daily")
        text = f"📅 *Настройки Ежедневной Викторины*\n\n{display_text}\n\nВыберите параметр для изменения:"

        daily_s_chat = settings.get("daily_quiz", {})
        def_daily_s_app = self.app_config.daily_quiz_defaults
        is_enabled = daily_s_chat.get("enabled", def_daily_s_app.get("enabled", False))

        kb = [[InlineKeyboardButton(f"{'Выключить' if is_enabled else 'Включить'} ежедневную викторину",
                                   callback_data=f"{CB_ADM_DAILY_TOGGLE_ENABLED}:{str(not is_enabled).lower()}")]]
        if is_enabled:
            kb.extend([
                [InlineKeyboardButton("Время запуска (МСК)", callback_data=CB_ADM_DAILY_SET_TIME)],
                [InlineKeyboardButton("Режим выбора категорий", callback_data=CB_ADM_DAILY_SET_CATEGORIES_MODE)],
                [InlineKeyboardButton("Кол-во вопросов", callback_data=CB_ADM_DAILY_SET_NUM_QUESTIONS)],
                [InlineKeyboardButton("Интервал между вопросами (сек)", callback_data=CB_ADM_DAILY_SET_INTERVAL_SECONDS)],
                [InlineKeyboardButton("Время на ответ (сек)", callback_data=CB_ADM_DAILY_SET_POLL_OPEN_SECONDS)],
            ])
        kb.append([InlineKeyboardButton("⬅️ Назад в главное меню", callback_data=CB_ADM_BACK_TO_MAIN)])
        
        context.chat_data[CTX_CURRENT_MENU_SENDER_CB_NAME] = "_send_daily_cfg_menu"
        await self._update_config_message(query_or_update, context, text, InlineKeyboardMarkup(kb))

    async def handle_daily_menu_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        query = update.callback_query
        action = query.data
        chat_id = context.chat_data[CTX_ADMIN_CFG_CHAT_ID]
        settings = self.data_manager.get_chat_settings(chat_id)
        daily_s_defs_app = self.app_config.daily_quiz_defaults
        
        context.chat_data[CTX_CURRENT_MENU_SENDER_CB_NAME] = "_send_daily_cfg_menu"

        if action == CB_ADM_BACK_TO_MAIN:
            await self._send_main_cfg_menu(query, context)
            return CFG_MAIN_MENU
        if action == CB_ADM_BACK_TO_DAILY_MENU:
            await self._send_daily_cfg_menu(query, context)
            return CFG_DAILY_MENU

        elif action.startswith(CB_ADM_DAILY_TOGGLE_ENABLED):
            val_str = action.split(":", 1)[1]
            val = val_str == "true"
            self.data_manager.update_chat_setting(chat_id, ["daily_quiz", "enabled"], val)
            if self.daily_quiz_scheduler_ref:
                asyncio.create_task(self.daily_quiz_scheduler_ref.reschedule_job_for_chat(chat_id))
            await self._send_daily_cfg_menu(query, context)
            return CFG_DAILY_MENU

        elif action == CB_ADM_DAILY_SET_TIME:
            current_daily_s = settings.get("daily_quiz", {})
            current_h = current_daily_s.get("hour_msk", daily_s_defs_app['hour_msk'])
            current_m = current_daily_s.get("minute_msk", daily_s_defs_app['minute_msk'])

            context.chat_data[CTX_INPUT_TARGET_KEY_PATH] = ["daily_quiz"]
            context.chat_data[CTX_INPUT_PROMPT] = f"Введите время запуска (МСК) в формате ЧЧ:ММ (например, 08:00).\nТекущее: {current_h:02d}:{current_m:02d}."
            context.chat_data[CTX_INPUT_CONSTRAINTS] = {'type': 'time'}
            await self._update_config_message(query, context, context.chat_data[CTX_INPUT_PROMPT], InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data=CB_ADM_BACK_TO_DAILY_MENU)]]))
            return CFG_INPUT_VALUE

        elif action == CB_ADM_DAILY_SET_CATEGORIES_MODE:
            current_daily_s = settings.get("daily_quiz", {})
            current_mode = current_daily_s.get("categories_mode", daily_s_defs_app['categories_mode'])
            modes_map = {"random": "Случайные", "specific": "Выбранные", "all_enabled": "Все разрешенные"}
            kb = []
            for mode_val, mode_text in modes_map.items():
                prefix = "✅ " if mode_val == current_mode else "☑️ "
                kb.append([InlineKeyboardButton(f"{prefix}{mode_text}", callback_data=f"{CB_ADM_DAILY_SET_CATEGORIES_MODE_OPT}:{mode_val}")])
            kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=CB_ADM_BACK_TO_DAILY_MENU)])
            await self._update_config_message(query, context, "Выберите режим категорий для ежедневной викторины:", InlineKeyboardMarkup(kb))
            return CFG_DAILY_MENU

        elif action.startswith(CB_ADM_DAILY_SET_CATEGORIES_MODE_OPT):
            mode_val = action.split(":",1)[1]
            self.data_manager.update_chat_setting(chat_id, ["daily_quiz", "categories_mode"], mode_val)
            
            if self.daily_quiz_scheduler_ref:
                 asyncio.create_task(self.daily_quiz_scheduler_ref.reschedule_job_for_chat(chat_id))

            if mode_val == "random":
                current_daily_s = self.data_manager.get_chat_settings(chat_id).get("daily_quiz", {})
                current_num_rand = current_daily_s.get("num_random_categories", daily_s_defs_app['num_random_categories'])
                context.chat_data[CTX_INPUT_TARGET_KEY_PATH] = ["daily_quiz", "num_random_categories"]
                context.chat_data[CTX_INPUT_PROMPT] = f"Введите кол-во случайных категорий (1-10).\nТекущее: {current_num_rand}."
                context.chat_data[CTX_INPUT_CONSTRAINTS] = {'min': 1, 'max': 10, 'type': 'int'}
                await self._update_config_message(query, context, context.chat_data[CTX_INPUT_PROMPT], InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data=CB_ADM_BACK_TO_DAILY_MENU)]]))
                return CFG_INPUT_VALUE
            elif mode_val == "specific":
                current_daily_s = self.data_manager.get_chat_settings(chat_id).get("daily_quiz", {})
                context.chat_data[CTX_CATEGORY_SELECTION_MODE] = 'daily_specific_categories'
                context.chat_data[CTX_CATEGORY_SELECTION_TITLE] = 'категорий для ежедневной викторины'
                context.chat_data[CTX_TEMP_CATEGORY_SELECTION] = set(current_daily_s.get('specific_categories', []))
                await self._send_category_selection_menu(query, context)
                return CFG_SELECT_GENERAL_CATEGORIES
            
            await self._send_daily_cfg_menu(query, context)
            return CFG_DAILY_MENU

        elif action in [CB_ADM_DAILY_SET_NUM_QUESTIONS, CB_ADM_DAILY_SET_INTERVAL_SECONDS, CB_ADM_DAILY_SET_POLL_OPEN_SECONDS, CB_ADM_DAILY_SET_NUM_RANDOM_CATEGORIES]:
            key_map_daily = {
                CB_ADM_DAILY_SET_NUM_QUESTIONS: (["daily_quiz", "num_questions"], daily_s_defs_app['num_questions'], "Кол-во вопросов (ежедн.)", (1, self.app_config.max_questions_per_session), 'int'),
                CB_ADM_DAILY_SET_INTERVAL_SECONDS: (["daily_quiz", "interval_seconds"], daily_s_defs_app['interval_seconds'], "Интервал м/у вопросами (ежедн. сек)", (10, 3600), 'int'),
                CB_ADM_DAILY_SET_POLL_OPEN_SECONDS: (["daily_quiz", "poll_open_seconds"], daily_s_defs_app['open_period_seconds'], "Время на ответ (ежедн. сек)", (30, 3600 * 2), 'int'),
                CB_ADM_DAILY_SET_NUM_RANDOM_CATEGORIES: (["daily_quiz", "num_random_categories"], daily_s_defs_app['num_random_categories'], "Кол-во случайных категорий (ежедн.)", (1,10), 'int')
            }
            key_path, default_val, prompt_text_base, (min_val, max_val), val_type = key_map_daily[action]
            current_daily_s = settings.get("daily_quiz", {})
            current_val = current_daily_s.get(key_path[1], default_val)

            context.chat_data[CTX_INPUT_TARGET_KEY_PATH] = key_path
            context.chat_data[CTX_INPUT_PROMPT] = f"Введите новое значение для '{prompt_text_base}'.\nТекущее: {current_val}. Диапазон: {min_val}–{max_val}."
            context.chat_data[CTX_INPUT_CONSTRAINTS] = {'min': min_val, 'max': max_val, 'type': val_type}

            await self._update_config_message(query, context, context.chat_data[CTX_INPUT_PROMPT], InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data=CB_ADM_BACK_TO_DAILY_MENU)]]))
            return CFG_INPUT_VALUE
        
        await query.answer()
        return CFG_DAILY_MENU

    async def handle_confirm_reset_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        query = update.callback_query
        action = query.data
        chat_id = context.chat_data[CTX_ADMIN_CFG_CHAT_ID]

        if action == CB_ADM_EXECUTE_RESET_SETTINGS:
            self.data_manager.reset_chat_settings(chat_id)
            if self.daily_quiz_scheduler_ref:
                asyncio.create_task(self.daily_quiz_scheduler_ref.reschedule_job_for_chat(chat_id))
            await query.answer("Настройки чата сброшены!")
            await self._send_main_cfg_menu(query, context)
            return CFG_MAIN_MENU
        
        elif action == CB_ADM_BACK_TO_MAIN:
            await query.answer()
            await self._send_main_cfg_menu(query, context)
            return CFG_MAIN_MENU
        
        await query.answer()
        return CFG_CONFIRM_RESET

    async def view_chat_config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_chat: return
        chat_id = update.effective_chat.id
        settings = self.data_manager.get_chat_settings(chat_id)
        settings_text = self._format_settings_display(settings, part="all")
        
        final_text = f"Текущие настройки для этого чата:\n\n{settings_text}"
        if len(final_text) > 4096:
            await update.message.reply_text("Текст настроек слишком длинный. Используйте меню администрирования.", parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await update.message.reply_text(final_text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)

    async def cancel_config_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        final_message = "Настройка отменена."
        query = update.callback_query

        if query:
            await query.answer()
            try: await query.edit_message_text(final_message, reply_markup=None, parse_mode=None)
            except BadRequest:
                try: await query.message.reply_text(final_message, parse_mode=None)
                except Exception as e_reply: logger.error(f"Ошибка отправки отмены: {e_reply}")
            except Exception as e_edit: logger.error(f"Ошибка редактирования при отмене: {e_edit}")
        elif update.message:
            await update.message.reply_text(final_message, parse_mode=None)
            target_msg_id = context.chat_data.get(CTX_ADMIN_CFG_MSG_ID)
            chat_id = context.chat_data.get(CTX_ADMIN_CFG_CHAT_ID)
            if target_msg_id and chat_id:
                try: await context.bot.delete_message(chat_id, target_msg_id)
                except: pass

        logger.info(f"Диалог настройки отменен для чата {context.chat_data.get(CTX_ADMIN_CFG_CHAT_ID)}.")
        context.chat_data.clear()
        return ConversationHandler.END

    def get_handlers(self) -> List[Any]:
        cancel_handler = CommandHandler(self.app_config.commands.cancel, self.cancel_config_conversation)
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler(self.app_config.commands.admin_settings, self.admin_settings_entry)],
            states={
                CFG_MAIN_MENU: [CallbackQueryHandler(self.handle_main_menu_callbacks, pattern=f"^{CB_ADM_}")],
                CFG_INPUT_VALUE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_input_value),
                    CallbackQueryHandler(self.handle_main_menu_callbacks, pattern=f"^{CB_ADM_BACK_TO_MAIN}$"),
                    CallbackQueryHandler(self.handle_daily_menu_callbacks, pattern=f"^{CB_ADM_BACK_TO_DAILY_MENU}$")
                ],
                CFG_SELECT_GENERAL_CATEGORIES: [
                    CallbackQueryHandler(self.handle_category_selection_callback, pattern=f"^{CB_ADM_CAT_SEL_}"),
                    CallbackQueryHandler(self.handle_main_menu_callbacks, pattern=f"^{CB_ADM_BACK_TO_MAIN}$"),
                    CallbackQueryHandler(self.handle_daily_menu_callbacks, pattern=f"^{CB_ADM_BACK_TO_DAILY_MENU}$")
                ],
                CFG_DAILY_MENU: [CallbackQueryHandler(self.handle_daily_menu_callbacks, pattern=f"^{CB_ADM_}")],
                CFG_CONFIRM_RESET: [CallbackQueryHandler(self.handle_confirm_reset_callbacks, pattern=f"^{CB_ADM_}")],
            },
            fallbacks=[
                cancel_handler,
                CallbackQueryHandler(self.cancel_config_conversation, pattern=f"^{CB_ADM_FINISH_CONFIG}$")
            ],
            per_chat=True, per_user=True, name="admin_settings_conversation", persistent=True, allow_reentry=True
        )
        return [
            conv_handler,
            CommandHandler(self.app_config.commands.view_chat_config, self.view_chat_config_command),
        ]
