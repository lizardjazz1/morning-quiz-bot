# utils.py
def pluralize_points(count: int) -> str:
    # Для логики склонения используется модуль числа
    abs_count = abs(count)
    if abs_count % 10 == 1 and abs_count % 100 != 11:
        form = "очко"
    elif 2 <= abs_count % 10 <= 4 and (abs_count % 100 < 10 or abs_count % 100 >= 20):
        form = "очка"
    else:
        form = "очков"
    return f"{count} {form}"
