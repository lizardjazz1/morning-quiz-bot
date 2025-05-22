# handlers/start_handler.py

from telegram import Update
from telegram.ext import ContextTypes
from utils.users import load_user_data, save_user_data
from main import user_scores

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.full_name

    # Регистрация пользователя
    if chat_id not in user_scores:
        user_scores[chat_id] = {}
    if user_id not in user_scores.get(chat_id, {}):
        user_scores[chat_id][user_id] = {"name": user_name, "score": 0}
        save_user_data(user_scores)

    await update.message.reply_text("Привет! Я буду присылать вам утреннюю викторину в формате опроса!")

#     # Добавляем чат в список активных
#     active_chats = context.bot_data.get("active_chats", set())
#     active_chats.add(chat_id)
#     context.bot_data["active_chats"] = active_chats
    
# async def send_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id=None):
#     active_chats = context.bot_data.get("active_chats", set())

#     if not active_chats:
#         logging.warning("Нет активных чатов для рассылки")
#         return

#     categories = list(quiz_data.keys())
#     category = random.choice(categories)
#     question_data = random.choice(quiz_data[category])
#     options = question_data["options"]
#     correct_answer = question_data["correct"]

#     for cid in active_chats:
#         try:
#             message = await context.bot.send_poll(
#                 chat_id=cid,
#                 question=question_data["question"],
#                 options=options,
#                 type=Poll.QUIZ,
#                 correct_option_id=options.index(correct_answer),
#                 is_anonymous=False
#             )

#             poll_id = message.poll.id
#             correct_index = options.index(correct_answer)

#             current_poll[poll_id] = {
#                 "chat_id": cid,
#                 "correct_index": correct_index,
#                 "message_id": message.message_id,
#                 "quiz_session": False
#             }

#         except Exception as e:
#             logging.error(f"Ошибка при отправке опроса в чат {cid}: {e}")