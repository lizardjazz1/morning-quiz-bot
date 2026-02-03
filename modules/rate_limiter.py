# modules/rate_limiter.py
"""
Rate Limiter для соблюдения лимитов Telegram Bot API.
Telegram API ограничивает до ~30 сообщений в секунду.
Best practice 2025: использовать token bucket или sliding window алгоритм.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List
from collections import deque

logger = logging.getLogger(__name__)


class TelegramRateLimiter:
    """
    Rate limiter для Telegram Bot API с использованием sliding window алгоритма.

    Telegram API лимиты:
    - Максимум ~30 сообщений в секунду
    - Максимум ~20 сообщений в минуту в один чат

    Args:
        max_requests_per_second: Максимальное количество запросов в секунду (default: 25)
        max_requests_per_minute_per_chat: Максимальное количество запросов в минуту на чат (default: 18)
    """

    def __init__(
        self,
        max_requests_per_second: int = 25,  # Консервативное значение (Telegram лимит ~30)
        max_requests_per_minute_per_chat: int = 18  # Консервативное значение (Telegram лимит ~20)
    ):
        self.max_global_rps = max_requests_per_second
        self.max_chat_rpm = max_requests_per_minute_per_chat

        # Глобальный sliding window для всех запросов (за последнюю секунду)
        self.global_requests: deque = deque()

        # Per-chat sliding windows (за последнюю минуту)
        self.chat_requests: Dict[int, deque] = {}

        # Метрики для отслеживания
        self.total_requests = 0
        self.total_delays = 0
        self.total_delay_time = 0.0

        logger.info(
            f"TelegramRateLimiter инициализирован: "
            f"global={self.max_global_rps} req/s, "
            f"per_chat={self.max_chat_rpm} req/min"
        )

    async def acquire(self, chat_id: int) -> bool:
        """
        Запрашивает разрешение на отправку запроса.
        Блокирует выполнение если достигнуты лимиты.

        Args:
            chat_id: ID чата, в который отправляется запрос

        Returns:
            True когда можно отправлять запрос
        """
        now = datetime.now()
        delay_applied = False

        # Проверяем глобальный лимит (запросов в секунду)
        while True:
            # Очищаем старые записи (старше 1 секунды)
            while self.global_requests and (now - self.global_requests[0]) > timedelta(seconds=1):
                self.global_requests.popleft()

            # Если не превышен лимит - выходим
            if len(self.global_requests) < self.max_global_rps:
                break

            # Иначе ждем минимальное время до освобождения слота
            oldest_request = self.global_requests[0]
            wait_until = oldest_request + timedelta(seconds=1)
            wait_time = (wait_until - now).total_seconds()

            if wait_time > 0:
                if not delay_applied:
                    logger.debug(
                        f"Rate limit: глобальный лимит достигнут ({len(self.global_requests)}/{self.max_global_rps}), "
                        f"ожидание {wait_time:.2f}с"
                    )
                    delay_applied = True
                    self.total_delays += 1
                    self.total_delay_time += wait_time

                await asyncio.sleep(wait_time)
                now = datetime.now()
            else:
                break

        # Проверяем per-chat лимит (запросов в минуту)
        if chat_id not in self.chat_requests:
            self.chat_requests[chat_id] = deque()

        chat_queue = self.chat_requests[chat_id]

        while True:
            # Очищаем старые записи (старше 1 минуты)
            while chat_queue and (now - chat_queue[0]) > timedelta(minutes=1):
                chat_queue.popleft()

            # Если не превышен лимит - выходим
            if len(chat_queue) < self.max_chat_rpm:
                break

            # Иначе ждем минимальное время до освобождения слота
            oldest_request = chat_queue[0]
            wait_until = oldest_request + timedelta(minutes=1)
            wait_time = (wait_until - now).total_seconds()

            if wait_time > 0:
                if not delay_applied:
                    logger.debug(
                        f"Rate limit: лимит для чата {chat_id} достигнут ({len(chat_queue)}/{self.max_chat_rpm}), "
                        f"ожидание {wait_time:.2f}с"
                    )
                    delay_applied = True
                    self.total_delays += 1
                    self.total_delay_time += wait_time

                await asyncio.sleep(wait_time)
                now = datetime.now()
            else:
                break

        # Регистрируем запрос
        self.global_requests.append(now)
        chat_queue.append(now)
        self.total_requests += 1

        return True

    def get_stats(self) -> Dict[str, any]:
        """
        Возвращает статистику работы rate limiter для отображения в веб-интерфейсе.

        Returns:
            Словарь с метриками
        """
        now = datetime.now()

        # Очищаем старые записи для точной статистики
        while self.global_requests and (now - self.global_requests[0]) > timedelta(seconds=1):
            self.global_requests.popleft()

        active_chats = 0
        for chat_id, chat_queue in self.chat_requests.items():
            while chat_queue and (now - chat_queue[0]) > timedelta(minutes=1):
                chat_queue.popleft()
            if len(chat_queue) > 0:
                active_chats += 1

        avg_delay = self.total_delay_time / self.total_delays if self.total_delays > 0 else 0

        return {
            "total_requests": self.total_requests,
            "current_rps": len(self.global_requests),
            "max_rps": self.max_global_rps,
            "active_chats": active_chats,
            "total_delays": self.total_delays,
            "total_delay_time": round(self.total_delay_time, 2),
            "avg_delay_time": round(avg_delay, 3),
            "delay_rate": round((self.total_delays / self.total_requests * 100), 2) if self.total_requests > 0 else 0
        }

    def reset_stats(self):
        """Сбрасывает статистику (полезно для тестирования)."""
        self.total_requests = 0
        self.total_delays = 0
        self.total_delay_time = 0.0
        logger.info("Rate limiter статистика сброшена")
