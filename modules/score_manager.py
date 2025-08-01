# modules/score_manager.py
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone # datetime используется для now_utc

from telegram import User as TelegramUser

from app_config import AppConfig
from state import BotState
from data_manager import DataManager
from utils import escape_markdown_v2, pluralize, get_username_or_firstname # get_username_or_firstname используется для мотивационных сообщений

logger = logging.getLogger(__name__)

class ScoreManager:
    def __init__(self, app_config: AppConfig, state: BotState, data_manager: DataManager):
        self.app_config = app_config
        self.state = state
        self.data_manager = data_manager

    async def update_score_and_get_motivation(
        self, chat_id: int, user: TelegramUser, poll_id: str, is_correct: bool,
        quiz_type_of_poll: str
    ) -> Tuple[bool, Optional[str]]:
        user_id_str = str(user.id)
        chat_id_str = str(chat_id)

        # ИЗМЕНЕНО: Логика определения имени для state. Приоритет first_name.
        user_first_name = user.first_name
        if user_first_name and user_first_name.strip():
            user_name_for_state = user_first_name.strip()
        elif user.username:
            user_name_for_state = f"@{user.username}"
        else:
            user_name_for_state = f"User {user_id_str}"

        score_updated_in_global_state = False
        motivational_message_text: Optional[str] = None

        # Обновление очков в активной сессии викторины (QuizState.scores)
        active_quiz = self.state.get_active_quiz(chat_id)
        if active_quiz:
            active_quiz.scores.setdefault(user_id_str, {"name": user_name_for_state, "score": 0, "answered_this_session": set()})
            # Убедимся, что имя в сессии тоже обновляется, если пользователь его сменил
            if active_quiz.scores[user_id_str].get("name") != user_name_for_state:
                 active_quiz.scores[user_id_str]["name"] = user_name_for_state

            if poll_id not in active_quiz.scores[user_id_str]["answered_this_session"]:
                if is_correct:
                    active_quiz.scores[user_id_str]["score"] += 1
                active_quiz.scores[user_id_str]["answered_this_session"].add(poll_id)

        # Обновление очков в глобальной статистике (BotState.user_scores)
        self.state.user_scores.setdefault(chat_id_str, {})
        self.state.user_scores[chat_id_str].setdefault(user_id_str, {
            "name": user_name_for_state,
            "score": 0,
            "answered_polls": set(),
            "first_answer_time": None,
            "last_answer_time": None,
            "milestones_achieved": set()
        })

        current_user_data_global = self.state.user_scores[chat_id_str][user_id_str]

        # Обновляем имя в глобальном state, если оно изменилось
        if current_user_data_global.get("name") != user_name_for_state:
            current_user_data_global["name"] = user_name_for_state
            score_updated_in_global_state = True # Считаем это обновлением, чтобы данные сохранились

        if poll_id not in current_user_data_global["answered_polls"]:
            if is_correct:
                current_user_data_global["score"] += 1
            score_updated_in_global_state = True
            current_user_data_global["answered_polls"].add(poll_id)

            now_utc = datetime.now(timezone.utc)
            if current_user_data_global["first_answer_time"] is None:
                current_user_data_global["first_answer_time"] = now_utc.isoformat()
            current_user_data_global["last_answer_time"] = now_utc.isoformat()

            # Логика мотивационных сообщений
            # Используем get_username_or_firstname для текста мотивационного сообщения,
            # чтобы сохранить старое поведение (показ @username если есть).
            name_for_motivation = get_username_or_firstname(user)
            current_score_for_motivation = current_user_data_global["score"]
            milestones_config = self.app_config.parsed_motivational_messages

            # Ищем подходящее сообщение по очкам, начиная с наибольшего порога
            # Сообщения могут быть как для положительных, так и для отрицательных порогов
            # Сортируем ключи (очки) по убыванию абсолютного значения, чтобы сначала проверять "крупные" изменения
            sorted_milestones_keys = sorted(milestones_config.keys(), key=abs, reverse=True)

            found_milestone_for_message = None

            for score_threshold in sorted_milestones_keys:
                # Положительные пороги: достигаются при score >= threshold
                if score_threshold > 0 and current_score_for_motivation >= score_threshold:
                    found_milestone_for_message = score_threshold
                    break
                # Отрицательные пороги: достигаются при score <= threshold
                elif score_threshold < 0 and current_score_for_motivation <= score_threshold:
                    found_milestone_for_message = score_threshold
                    break
                # Порог 0: если других не подошло и есть сообщение для 0
                elif score_threshold == 0 and current_score_for_motivation == 0 :
                    found_milestone_for_message = score_threshold
                    # не break, т.к. могут быть специфичные отрицательные пороги ниже 0

            if found_milestone_for_message is not None:
                # Проверяем, не было ли это сообщение уже отправлено для этого порога
                milestone_id_str = f"motivational_{chat_id_str}_{user_id_str}_{found_milestone_for_message}" # Более уникальный ID
                achieved_milestones_set = current_user_data_global.setdefault("milestones_achieved", set())

                should_send_message = False
                if found_milestone_for_message > 0 and current_score_for_motivation >= found_milestone_for_message:
                    should_send_message = True
                elif found_milestone_for_message < 0 and current_score_for_motivation <= found_milestone_for_message:
                    should_send_message = True

                if should_send_message and milestone_id_str not in achieved_milestones_set:
                    motivational_message_text = self.app_config.parsed_motivational_messages[found_milestone_for_message].format(
                        user_name=escape_markdown_v2(name_for_motivation),
                        user_score=current_score_for_motivation
                    )
                    achieved_milestones_set.add(milestone_id_str)
                    score_updated_in_global_state = True
                    logger.info(f"Пользователь {user_id_str} ({user_name_for_state}) в чате {chat_id_str} достиг рубежа {found_milestone_for_message} ({current_score_for_motivation} очков). Сообщение: '{motivational_message_text[:50]}...'")
                    # break # Если хотим отправлять только одно сообщение за раз, раскомментировать
        else: # poll_id уже был в answered_polls, но имя могло измениться
            if not score_updated_in_global_state: # Если только имя изменилось, а очки нет
                 pass # score_updated_in_global_state уже true, если имя менялось

        if score_updated_in_global_state:
            self.data_manager.save_user_data()

        return score_updated_in_global_state, motivational_message_text

    def get_rating_icon(self, score: int) -> str:
        if score > 0:
            if score >= 1000: return "🌟"  # Легенда
            elif score >= 500: return "🏆"  # Чемпион
            elif score >= 100: return "👑"  # Лапочка
            elif score >= 50: return "🔥"  # Огонь
            elif score >= 10: return "👍"  # Новичок с очками
            else: return "🙂"             # Мало очков (1-9)
        elif score < 0:
            return "💀"  # Отрицательный рейтинг
        else:  # player_score == 0
            return "😐"  # Нейтрально

    def format_scores(
        self,
        scores_list: List[Dict[str, Any]],
        title: str,
        is_session_score: bool = False,
        num_questions_in_session: Optional[int] = None
    ) -> str:
        logger.debug(f"format_scores вызван. Title: '{title}', is_session: {is_session_score}, num_q_sess: {num_questions_in_session}, items: {len(scores_list)}")

        escaped_title = escape_markdown_v2(title)
        if not scores_list:
            empty_message = "Пока нет результатов для отображения."
            if is_session_score:
                empty_message = "Никто не набрал очков в этой сессии."
            return f"*{escaped_title}*\n\n{escape_markdown_v2(empty_message)}"

        lines = [f"*{escaped_title}*"]

        if is_session_score and num_questions_in_session is not None:
            # В сессионном счете мы показываем X/Y, поэтому счет в скобках не нужен
            # lines.append(escape_markdown_v2(f"(Всего вопросов в сессии: {num_questions_in_session})"))
            pass # Убрано для компактности и соответствия новому формату

        lines.append("") # Пустая строка для разделения

        place_icons = ["🥇", "🥈", "🥉"] # Определяем здесь, чтобы использовать ниже

        for i, entry in enumerate(scores_list):
            user_id_for_name = entry.get("user_id", "??") # Используем user_id для fallback имени
            user_name_raw = entry.get('name', f'Игрок {user_id_for_name}')
            score_val = entry.get('score', 0)

            line_parts: List[str] = []

            # 1. Место (иконка или номер)
            if i < len(place_icons) and score_val > 0: # Медали только для топ-3 с положительным счетом
                line_parts.append(place_icons[i])
            else:
                line_parts.append(f"{escape_markdown_v2(str(i + 1))}\.") # Экранируем точку

            # 2. Иконка рейтинга (эмодзи) - теперь определяется score, а не рангом
            rating_icon = self.get_rating_icon(score_val)
            line_parts.append(rating_icon)

            # 3. Имя и очки - ИЗМЕНЕНА ЛОГИКА ФОРМИРОВАНИЯ ЭТОЙ ЧАСТИ
            escaped_user_name = escape_markdown_v2(user_name_raw)

            final_name_score_segment: str
            if is_session_score and num_questions_in_session is not None:
                # Формат для сессии с количеством вопросов: "Имя: X/Y"
                score_display_for_session = f"{score_val}/{num_questions_in_session}"
                # escape_markdown_v2 применяется к числу и знаку /, т.к. они могут быть частью формата
                final_name_score_segment = f"{escaped_user_name}: `{escape_markdown_v2(score_display_for_session)}`" # Числа в коде
            else:
                # Общий формат "Имя - X очков" (для общего рейтинга и для сессии без X/Y)
                # Текст очков с правильным окончанием ("1 очко", "2 очка", "5 очков")
                player_score_pluralized_text = pluralize(score_val, "очко", "очка", "очков")

                # Определяем часть со счетом для вывода
                score_display_part: str
                if score_val < 0:
                    # Для отрицательного счета добавляем минус перед числом
                    # Используем абсолютное значение для текста плюрализации, но сохраняем знак для вывода
                    # Предполагаем, что pluralize(score_val) вернет текст типа "74 очка" для score_val=-74
                    score_display_part = f"- {escape_markdown_v2(player_score_pluralized_text)}" # Добавляем минус и пробел
                else:
                    score_display_part = escape_markdown_v2(player_score_pluralized_text)

                # Формируем конечный сегмент "Имя: `Счет`"
                final_name_score_segment = f"{escaped_user_name}: `{score_display_part}`" # Числа в коде

            line_parts.append(final_name_score_segment)
            lines.append(" ".join(line_parts))

        return "\n".join(lines)

    def get_chat_rating(self, chat_id: int, top_n: int = 10) -> List[Dict[str, Any]]:
        chat_id_str = str(chat_id)
        if chat_id_str not in self.state.user_scores or not self.state.user_scores[chat_id_str]:
            return []

        scores_in_chat = self.state.user_scores[chat_id_str]
        # Сортируем по убыванию очков, затем по имени (для стабильности при равных очках)
        # data.get('name', '') or f"User {uid}" ensures name exists for sorting
        sorted_users = sorted(
            scores_in_chat.items(),
            key=lambda item: (-item[1].get("score", 0), item[1].get("name", f"User {item[0]}")),
        )

        top_users_list = []
        for i, (user_id_str, data) in enumerate(sorted_users[:top_n]):
            user_name = data.get("name", f"User {user_id_str}") # Уже должно быть подготовлено
            score = data.get("score", 0)
            try:
                user_id_int = int(user_id_str)
            except ValueError:
                user_id_int = 0 # Fallback, should not happen if user_id_str is always int
            top_users_list.append({"user_id": user_id_int, "name": user_name, "score": score})
        return top_users_list

    def get_global_rating(self, top_n: int = 10) -> List[Dict[str, Any]]:
        global_scores_agg: Dict[str, Dict[str, Any]] = {} # user_id_str -> {"name": ..., "score": ...}

        for chat_id_str, users_in_chat_dict in self.state.user_scores.items():
            for user_id_str, user_data_dict in users_in_chat_dict.items():
                user_score = user_data_dict.get("score", 0)
                user_name = user_data_dict.get("name", f"User {user_id_str}") # Имя уже должно быть подготовлено

                if user_id_str not in global_scores_agg:
                    global_scores_agg[user_id_str] = {"name": user_name, "score": 0}

                global_scores_agg[user_id_str]["score"] += user_score
                # Имя берем из первой встреченной записи; можно улучшить, если имя может меняться глобально
                # Но так как имя теперь first_name, оно должно быть консистентно для user_id
                if global_scores_agg[user_id_str]["name"] == f"User {user_id_str}" and user_name != f"User {user_id_str}":
                    global_scores_agg[user_id_str]["name"] = user_name


        sorted_global_users = sorted(
            global_scores_agg.items(),
            key=lambda item: (-item[1].get("score", 0), item[1].get("name", f"User {item[0]}")),
        )

        top_global_list = []
        for i, (user_id_str, data) in enumerate(sorted_global_users[:top_n]):
            try:
                user_id_int = int(user_id_str)
            except ValueError:
                user_id_int = 0
            top_global_list.append({
                "user_id": user_id_int,
                "name": data.get("name", f"User {user_id_str}"),
                "score": data.get("score", 0)
            })
        return top_global_list

    def get_user_stats_in_chat(self, chat_id: int, user_id: str) -> Optional[Dict[str, Any]]:
        chat_id_str = str(chat_id)
        user_scores_chat = self.state.user_scores.get(chat_id_str, {}).get(user_id)
        if not user_scores_chat:
            return None

        # Возвращаем копию, чтобы избежать случайных модификаций извне
        stats = {
            "name": user_scores_chat.get("name", f"User {user_id}"),
            "score": user_scores_chat.get("score", 0),
            "answered_polls_count": len(user_scores_chat.get("answered_polls", set())), # Теперь set в state
            "first_answer_time": user_scores_chat.get("first_answer_time"),
            "last_answer_time": user_scores_chat.get("last_answer_time"),
        }
        # Удаляем сам set из возвращаемых данных, если он не нужен напрямую
        # stats.pop("answered_polls", None) # Уже не нужно, так как len берется
        # stats.pop("milestones_achieved", None) # Уже не нужно
        return stats

    def get_global_user_stats(self, user_id: str) -> Optional[Dict[str, Any]]:
        total_score = 0
        total_answered_polls = 0
        # Имя пользователя может отличаться в разных чатах, если логика user_name_for_state была другой.
        # С новой логикой (приоритет first_name) имя должно быть одинаковым.
        # Берем первое не-дефолтное имя.
        display_name: Optional[str] = None
        first_answer_overall: Optional[str] = None
        last_answer_overall: Optional[str] = None

        found_user_data = False
        for chat_data in self.state.user_scores.values():
            user_chat_data = chat_data.get(user_id)
            if user_chat_data:
                found_user_data = True
                total_score += user_chat_data.get("score", 0)
                answered_in_chat = user_chat_data.get("answered_polls", set())
                total_answered_polls += len(answered_in_chat) if isinstance(answered_in_chat, set) else 0

                current_name = user_chat_data.get("name")
                if display_name is None or display_name.startswith("User "): # Обновляем, если нашли более осмысленное имя
                    if current_name and not current_name.startswith("User "):
                        display_name = current_name

                # Обновление временных меток
                fat_str = user_chat_data.get("first_answer_time")
                lat_str = user_chat_data.get("last_answer_time")
                if fat_str:
                    try:
                        fat_dt = datetime.fromisoformat(fat_str)
                        if first_answer_overall is None or fat_dt < datetime.fromisoformat(first_answer_overall):
                            first_answer_overall = fat_str
                    except ValueError:
                         logger.warning(f"Неверный формат first_answer_time для пользователя {user_id} в чате: {fat_str}")

                if lat_str:
                    try:
                        lat_dt = datetime.fromisoformat(lat_str)
                        if last_answer_overall is None or lat_dt > datetime.fromisoformat(last_answer_overall):
                            last_answer_overall = lat_str
                    except ValueError:
                        logger.warning(f"Неверный формат last_answer_time для пользователя {user_id} в чате: {lat_str}")

        if not found_user_data:
            return None

        if display_name is None: # Если пользователь нигде не имел осмысленного имени
            display_name = f"User {user_id}"

        # Избегаем деления на ноль
        average_score_per_poll = (total_score / total_answered_polls) if total_answered_polls > 0 else 0.0

        return {
            "name": display_name,
            "total_score": total_score,
            "answered_polls": total_answered_polls,
            "average_score_per_poll": average_score_per_poll,
            "first_answer_time_overall": first_answer_overall,
            "last_answer_time_overall": last_answer_overall,
        }

