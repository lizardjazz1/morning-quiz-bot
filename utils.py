# utils.py
def pluralize_points(count: int) -> str:
    """
    Возвращает правильное склонение слова "очко" в зависимости от числа.
    1 очко, 2 очка, 5 очков.
    """
    if count % 10 == 1 and count % 100 != 11:
        return f"{count} очко"
    elif 2 <= count % 10 <= 4 and (count % 100 < 10 or count % 100 >= 20):
        return f"{count} очка"
    else:
        return f"{count} очков"

