# bot/utils.py
import re
from typing import List, Dict, Any, Tuple, Optional # Added for type hints if needed later
import pytz # For moscow_time
from datetime import time # For moscow_time

def pluralize(count: int, form_one: str, form_two: str, form_five: str) -> str:
    abs_count = abs(count)
    if abs_count % 10 == 1 and abs_count % 100 != 11:
        form = form_one
    elif 2 <= abs_count % 10 <= 4 and (abs_count % 100 < 10 or abs_count % 100 >= 20):
        form = form_two
    else:
        form = form_five
    return f"{count} {form}"

def escape_markdown_v2(text: str) -> str:
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

def moscow_time(hour: int, minute: int) -> time:
    """Создает объект datetime.time для указанного часа и минуты по Московскому времени."""
    moscow_tz = pytz.timezone('Europe/Moscow')
    return time(hour=hour, minute=minute, tzinfo=moscow_tz)

def parse_time_hh_mm(time_str: str) -> Optional[Tuple[int, int]]:
    """Парсит время из строки HH:MM или HH.MM или HH в (час, минута)."""
    match_hh_mm = re.fullmatch(r"(\d{1,2})[:.](\d{1,2})", time_str)
    if match_hh_mm:
        h_str, m_str = match_hh_mm.groups()
        try:
            h, m = int(h_str), int(m_str)
            if 0 <= h <= 23 and 0 <= m <= 59: return h, m
        except ValueError: pass
        return None
    match_hh = re.fullmatch(r"(\d{1,2})", time_str)
    if match_hh:
        h_str = match_hh.group(1)
        try:
            h = int(h_str)
            if 0 <= h <= 23: return h, 0 # По умолчанию 0 минут, если указан только час
        except ValueError: pass
    return None
