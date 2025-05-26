# utils.py
import re

def pluralize(count: int, form_one: str, form_two: str, form_five: str) -> str:
    """
    Возвращает строку с числом и правильной формой слова в зависимости от числа.
    Например: pluralize(5, "яблоко", "яблока", "яблок") -> "5 яблок"
    """
    abs_count = abs(count)
    if abs_count % 10 == 1 and abs_count % 100 != 11:
        form = form_one
    elif 2 <= abs_count % 10 <= 4 and (abs_count % 100 < 10 or abs_count % 100 >= 20):
        form = form_two
    else:
        form = form_five
    return f"{count} {form}"

def escape_markdown_v2(text: str) -> str:
    """
    Escapes characters for Telegram MarkdownV2.
    Characters to escape: _ * [ ] ( ) ~ ` > # + - = | { } . !
    """
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

