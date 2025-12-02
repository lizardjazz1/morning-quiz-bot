#!/usr/bin/env python3
"""
Модуль для отправки уведомлений разработчику в Telegram
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class DeveloperNotifier:
    """
    Класс для отправки уведомлений разработчику о проблемах в системе
    """
    
    def __init__(self, bot, app_config):
        self.bot = bot
        self.app_config = app_config
        self.notifications_enabled = app_config.global_settings.get("developer_notifications", {}).get("enabled", False)
        self.developer_user_id = app_config.global_settings.get("developer_notifications", {}).get("developer_user_id")
        self.notify_malformed = app_config.global_settings.get("developer_notifications", {}).get("notify_on_malformed_questions", True)
        self.notify_data_errors = app_config.global_settings.get("developer_notifications", {}).get("notify_on_data_errors", True)
        self.notify_system_errors = app_config.global_settings.get("developer_notifications", {}).get("notify_system_errors", False)
        
        if not self.notifications_enabled:
            logger.info("Уведомления разработчику отключены")
        elif not self.developer_user_id:
            logger.warning("Уведомления разработчику включены, но developer_user_id не установлен")
        else:
            logger.info(f"Уведомления разработчику включены для пользователя {self.developer_user_id}")
    
    def notify_malformed_questions(self, malformed_entries: List[Dict[str, Any]]) -> None:
        """Отправляет уведомление о малформированных вопросах"""
        if not self._should_notify("malformed"):
            return
        
        if not malformed_entries:
            return
        
        try:
            message = self._format_malformed_questions_message(malformed_entries)
            self._send_notification(message, "🚨 Проблемы с вопросами")
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о малформированных вопросах: {e}")
    
    def notify_data_error(self, error_type: str, error_details: str, context: str = "") -> None:
        """Отправляет уведомление об ошибке данных"""
        if not self._should_notify("data_errors"):
            return
        
        try:
            message = self._format_data_error_message(error_type, error_details, context)
            self._send_notification(message, "⚠️ Ошибка данных")
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об ошибке данных: {e}")
    
    def notify_system_error(self, error_type: str, error_details: str, context: str = "") -> None:
        """Отправляет уведомление о системной ошибке"""
        if not self._should_notify("system_errors"):
            return
        
        try:
            message = self._format_system_error_message(error_type, error_details, context)
            self._send_notification(message, "💥 Системная ошибка")
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о системной ошибке: {e}")
    
    def notify_auto_fix_success(self, fixed_categories: List[str]) -> None:
        """Отправляет уведомление об успешном автоматическом исправлении"""
        if not self._should_notify("malformed"):
            return
        
        if not fixed_categories:
            return
        
        try:
            message = self._format_auto_fix_message(fixed_categories)
            self._send_notification(message, "✅ Автоисправление")
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об автоисправлении: {e}")
    
    def _should_notify(self, notification_type: str) -> bool:
        """Проверяет, нужно ли отправлять уведомление"""
        if not self.notifications_enabled:
            return False
        
        if not self.developer_user_id:
            return False
        
        if notification_type == "malformed":
            return self.notify_malformed
        elif notification_type == "data_errors":
            return self.notify_data_errors
        elif notification_type == "system_errors":
            return self.notify_system_errors
        
        return False
    
    def _format_malformed_questions_message(self, malformed_entries: List[Dict[str, Any]]) -> str:
        """Форматирует сообщение о малформированных вопросах"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        message = f"🚨 *Проблемы с вопросами* ({timestamp})\n\n"
        message += f"Найдено проблемных файлов: {len(malformed_entries)}\n\n"
        
        for i, entry in enumerate(malformed_entries[:5], 1):  # Показываем первые 5
            category = entry.get("category", "Неизвестно")
            error_type = entry.get("error_type", "Неизвестно")
            error = entry.get("error", "Нет деталей")
            
            message += f"{i}. *{category}* ({error_type})\n"
            message += f"   Ошибка: {error}\n\n"
        
        if len(malformed_entries) > 5:
            message += f"... и еще {len(malformed_entries) - 5} проблемных файлов\n"
        
        return message
    
    def _format_data_error_message(self, error_type: str, error_details: str, context: str = "") -> str:
        """Форматирует сообщение об ошибке данных"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        message = f"⚠️ *Ошибка данных* ({timestamp})\n\n"
        message += f"Тип: {error_type}\n"
        message += f"Детали: {error_details}\n"
        
        if context:
            message += f"Контекст: {context}\n"
        
        return message
    
    def _format_system_error_message(self, error_type: str, error_details: str, context: str = "") -> str:
        """Форматирует сообщение о системной ошибке"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        message = f"💥 *Системная ошибка* ({timestamp})\n\n"
        message += f"Тип: {error_type}\n"
        message += f"Детали: {error_details}\n"
        
        if context:
            message += f"Контекст: {context}\n"
        
        return message
    
    def _format_auto_fix_message(self, fixed_categories: List[str]) -> str:
        """Форматирует сообщение об автоматическом исправлении"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        message = f"✅ *Автоматическое исправление* ({timestamp})\n\n"
        message += f"Исправлено файлов: {len(fixed_categories)}\n\n"
        
        for i, category in enumerate(fixed_categories[:5], 1):
            message += f"{i}. {category}\n"
        
        if len(fixed_categories) > 5:
            message += f"... и еще {len(fixed_categories) - 5} файлов\n"
        
        return message
    
    def _send_notification(self, message: str, title: str = "") -> None:
        """Отправляет уведомление разработчику"""
        try:
            if title:
                full_message = f"{title}\n\n{message}"
            else:
                full_message = message
            
            # Отправляем сообщение в личку разработчику
            self.bot.send_message(
                chat_id=self.developer_user_id,
                text=full_message,
                parse_mode='Markdown'
            )
            
            logger.info(f"Уведомление отправлено разработчику {self.developer_user_id}")
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления разработчику: {e}")
    
    def test_notification(self) -> bool:
        """Отправляет тестовое уведомление для проверки настроек"""
        if not self._should_notify("malformed"):
            return False
        
        try:
            test_message = "🧪 *Тестовое уведомление*\n\nЭто тестовое сообщение для проверки настроек уведомлений разработчику.\n\nВремя: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            self._send_notification(test_message, "🧪 Тест уведомлений")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка отправки тестового уведомления: {e}")
            return False
