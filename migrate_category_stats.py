#!/usr/bin/env python3
"""
Скрипт миграции статистики категорий из старого формата в новый.

Старый формат:
    "total_usage": 123,      // число (устарело)
    "chat_usage": 456        // число (устарело)

Новый формат:
    "global_usage": 123,     // число - общее использование
    "chat_usage": {...}      // словарь - использование по чатам
"""

import json
import shutil
from pathlib import Path
from datetime import datetime

def migrate_category_stats():
    """Мигрирует статистику категорий из старого формата в новый"""

    stats_file = Path("data/statistics/categories_stats.json")

    if not stats_file.exists():
        print(f"❌ Файл не найден: {stats_file}")
        return False

    print(f"📁 Читаем файл: {stats_file}")

    # Создаем бэкап перед миграцией
    backup_file = stats_file.parent / f"categories_stats.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    shutil.copy2(stats_file, backup_file)
    print(f"💾 Создан бэкап: {backup_file}")

    # Читаем данные
    with open(stats_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"📊 Найдено категорий: {len(data)}")

    migrated_count = 0
    skipped_count = 0

    for cat_name, cat_data in data.items():
        changed = False

        # 1. Миграция total_usage -> global_usage
        if "total_usage" in cat_data:
            old_value = cat_data["total_usage"]

            # Если total_usage не 0 и global_usage еще нет или равен 0
            if old_value != 0:
                current_global = cat_data.get("global_usage", 0)
                if current_global == 0:
                    cat_data["global_usage"] = old_value
                    print(f"  ✅ {cat_name}: total_usage ({old_value}) -> global_usage")
                    changed = True
                elif current_global != old_value:
                    print(f"  ⚠️  {cat_name}: расхождение! total_usage={old_value}, global_usage={current_global}")
                    print(f"      Используем максимальное значение: {max(old_value, current_global)}")
                    cat_data["global_usage"] = max(old_value, current_global)
                    changed = True

            # Удаляем старое поле
            del cat_data["total_usage"]
            changed = True

        # 2. Проверка формата chat_usage
        if "chat_usage" in cat_data:
            chat_usage = cat_data["chat_usage"]

            # Если это число (старый формат), конвертируем в словарь
            if isinstance(chat_usage, (int, float)):
                print(f"  ⚠️  {cat_name}: chat_usage={chat_usage} (число) - требуется ручная миграция")
                # Мы не можем автоматически мигрировать, так как неизвестно какой chat_id
                # Оставляем как есть, код будет поддерживать оба формата
                skipped_count += 1
            elif isinstance(chat_usage, dict):
                # Новый формат - всё ОК
                pass
            else:
                print(f"  ❌ {cat_name}: неизвестный формат chat_usage: {type(chat_usage)}")

        # 3. Убеждаемся что есть обязательные поля
        if "global_usage" not in cat_data:
            # Если нет global_usage, пытаемся вычислить из chat_usage
            chat_usage = cat_data.get("chat_usage", {})
            if isinstance(chat_usage, dict):
                cat_data["global_usage"] = sum(chat_usage.values())
                print(f"  🔧 {cat_name}: вычислен global_usage={cat_data['global_usage']} из chat_usage")
                changed = True
            else:
                cat_data["global_usage"] = 0
                print(f"  ⚠️  {cat_name}: установлен global_usage=0 (нет данных)")
                changed = True

        if changed:
            migrated_count += 1

    # Сохраняем обновленные данные
    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Миграция завершена!")
    print(f"   Мигрировано категорий: {migrated_count}")
    print(f"   Пропущено (требуют ручной миграции): {skipped_count}")
    print(f"   Всего категорий: {len(data)}")
    print(f"   Бэкап сохранен: {backup_file}")

    return True

def validate_migration():
    """Проверяет корректность миграции"""

    stats_file = Path("data/statistics/categories_stats.json")

    if not stats_file.exists():
        print(f"❌ Файл не найден: {stats_file}")
        return False

    with open(stats_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print("\n🔍 Проверка миграции:")

    has_old_format = False
    has_issues = False

    for cat_name, cat_data in data.items():
        # Проверка на старые поля
        if "total_usage" in cat_data:
            print(f"  ⚠️  {cat_name}: найдено старое поле 'total_usage'")
            has_old_format = True

        # Проверка на обязательные поля
        if "global_usage" not in cat_data:
            print(f"  ❌ {cat_name}: отсутствует обязательное поле 'global_usage'")
            has_issues = True

        # Проверка формата chat_usage
        if "chat_usage" in cat_data:
            chat_usage = cat_data["chat_usage"]
            if not isinstance(chat_usage, dict) and not isinstance(chat_usage, (int, float)):
                print(f"  ❌ {cat_name}: неправильный формат 'chat_usage': {type(chat_usage)}")
                has_issues = True

    if has_old_format:
        print("\n⚠️  Найдены категории со старым форматом - требуется повторная миграция")

    if has_issues:
        print("\n❌ Найдены проблемы в данных")
        return False

    print("\n✅ Все данные в правильном формате!")

    # Показываем топ-10 категорий для проверки
    print("\n📊 Топ-10 категорий по использованию:")
    sorted_cats = sorted(data.items(), key=lambda x: x[1].get("global_usage", 0), reverse=True)[:10]
    for i, (cat_name, cat_data) in enumerate(sorted_cats, 1):
        global_usage = cat_data.get("global_usage", 0)
        total_questions = cat_data.get("total_questions", 0)
        chat_usage = cat_data.get("chat_usage", {})
        if isinstance(chat_usage, dict):
            chats_count = len(chat_usage)
        else:
            chats_count = "?"
        print(f"  {i:2d}. {cat_name}: {global_usage} использований, {total_questions} вопросов, {chats_count} чатов")

    return True

if __name__ == "__main__":
    print("=" * 70)
    print("МИГРАЦИЯ СТАТИСТИКИ КАТЕГОРИЙ")
    print("=" * 70)
    print()

    # Выполняем миграцию
    success = migrate_category_stats()

    if success:
        # Проверяем результат
        validate_migration()

    print("\n" + "=" * 70)
    print("Готово!")
    print("=" * 70)
