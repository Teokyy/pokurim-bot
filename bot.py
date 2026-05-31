import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)
import json
from datetime import datetime

# Настройки
BOT_TOKEN = "8690003152:AAERIPNB18JZKIJ8uTLZf-0KXgt7P_4zAcI"
ADMIN_ID = 1320584749

# Файл для хранения данных
DATA_FILE = "users.json"

# Состояния разговора
WAITING_FOR_SUBMISSION = 1

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─── Работа с данными ───────────────────────────────────────────────────────

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(data, user_id):
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"discount": 0, "submissions": [], "name": ""}
    return data[uid]


# ─── Команды пользователя ───────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()
    u = get_user(data, user.id)
    u["name"] = user.full_name
    save_data(data)

    text = (
        f"👋 Привет, {user.first_name}!\n\n"
        f"🏁 *Программа лояльности сети «Покурим?!»*\n\n"
        f"Отправляй чеки от 1500 ₽ и получай скидку в «Апекс Симрейсинг».\n"
        f"Каждый подтверждённый чек = *+2% скидки* (макс. 25%)\n\n"
        f"💳 Твоя текущая скидка: *{u['discount']}%*\n\n"
        f"Чтобы отправить чек — используй /submit\n"
        f"Проверить скидку — /mystatus"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def my_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    u = get_user(data, update.effective_user.id)
    count = len([s for s in u["submissions"] if s["status"] == "approved"])

    text = (
        f"📊 *Твоя статистика*\n\n"
        f"💳 Скидка: *{u['discount']}%* из 25%\n"
        f"✅ Подтверждённых чеков: *{count}*\n"
        f"📝 Всего заявок: *{len(u['submissions'])}*\n\n"
        f"До максимальной скидки осталось: *{max(0, 25 - u['discount'])}%*"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def submit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *Отправка чека*\n\n"
        "Пришли одним сообщением:\n"
        "📸 Фото чека\n"
        "🏪 Адрес магазина\n"
        "👤 Имя сотрудника\n\n"
        "_(Фото + подпись с адресом и именем)_\n\n"
        "Или отправь /cancel для отмены.",
        parse_mode="Markdown"
    )
    return WAITING_FOR_SUBMISSION

async def receive_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = update.effective_user

    if not message.photo:
        await message.reply_text(
            "❌ Нужно отправить *фото чека* с подписью (адрес магазина и имя сотрудника).",
            parse_mode="Markdown"
        )
        return WAITING_FOR_SUBMISSION

    caption = message.caption or ""
    if len(caption.strip()) < 5:
        await message.reply_text(
            "❌ Добавь подпись к фото: *адрес магазина* и *имя сотрудника*.",
            parse_mode="Markdown"
        )
        return WAITING_FOR_SUBMISSION

    data = load_data()
    u = get_user(data, user.id)

    submission_id = f"{user.id}_{int(datetime.now().timestamp())}"
    submission = {
        "id": submission_id,
        "file_id": message.photo[-1].file_id,
        "caption": caption,
        "status": "pending",
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "user_id": user.id,
        "user_name": user.full_name,
        "username": user.username or "—"
    }
    u["submissions"].append(submission)
    save_data(data)

    await message.reply_text(
        "✅ *Заявка принята!*\n\n"
        "Администратор проверит чек и начислит скидку.\n"
        "Вы получите уведомление после проверки.",
        parse_mode="Markdown"
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_{submission_id}_{user.id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{submission_id}_{user.id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    admin_text = (
        f"📥 *Новая заявка*\n\n"
        f"👤 Пользователь: {user.full_name}\n"
        f"🔗 Username: @{user.username or '—'}\n"
        f"🆔 ID: `{user.id}`\n"
        f"📝 Описание: {caption}\n"
        f"📅 Дата: {submission['date']}\n"
        f"🔑 ID заявки: `{submission_id}`"
    )

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=message.photo[-1].file_id,
        caption=admin_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END


# ─── Команды администратора ─────────────────────────────────────────────────

async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    data = load_data()
    if not data:
        await update.message.reply_text("Пользователей пока нет.")
        return

    text = "📋 *Все пользователи:*\n\n"
    for uid, u in data.items():
        approved = len([s for s in u["submissions"] if s["status"] == "approved"])
        pending = len([s for s in u["submissions"] if s["status"] == "pending"])
        text += (
            f"👤 {u.get('name', '?')} | ID: `{uid}`\n"
            f"💳 Скидка: *{u['discount']}%* | ✅ {approved} | ⏳ {pending}\n\n"
        )

    await update.message.reply_text(text, parse_mode="Markdown")

async def admin_set_discount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    try:
        _, user_id, percent = update.message.text.split()
        percent = int(percent)
        assert 0 <= percent <= 25
    except:
        await update.message.reply_text("Использование: /setdiscount USER_ID PERCENT (0-25)")
        return

    data = load_data()
    u = get_user(data, user_id)
    u["discount"] = percent
    save_data(data)

    await update.message.reply_text(f"✅ Скидка пользователя {user_id} установлена: {percent}%")
    try:
        await context.bot.send_message(
            chat_id=int(user_id),
            text=f"🎉 Ваша скидка обновлена администратором: *{percent}%*",
            parse_mode="Markdown"
        )
    except:
        pass


# ─── Обработка кнопок ───────────────────────────────────────────────────────

async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != ADMIN_ID:
        return

    parts = query.data.split("_", 2)
    action = parts[0]
    user_id = parts[-1]
    submission_id = "_".join(parts[1:-1])

    data = load_data()
    u = get_user(data, user_id)

    submission = next((s for s in u["submissions"] if s["id"] == submission_id), None)
    if not submission:
        await query.edit_message_caption("⚠️ Заявка не найдена.", parse_mode="Markdown")
        return

    if submission["status"] != "pending":
        await query.edit_message_caption(
            f"ℹ️ Заявка уже обработана: *{submission['status']}*",
            parse_mode="Markdown"
        )
        return

    if action == "approve":
        if u["discount"] < 25:
            u["discount"] = min(25, u["discount"] + 2)
        submission["status"] = "approved"
        save_data(data)

        await query.edit_message_caption(
            f"✅ *Подтверждено*\n{query.message.caption}\n\n💳 Новая скидка: *{u['discount']}%*",
            parse_mode="Markdown"
        )
        await context.bot.send_message(
            chat_id=int(user_id),
            text=(
                f"🎉 *Чек подтверждён!*\n\n"
                f"💳 Ваша новая скидка: *{u['discount']}%*\n"
                f"До максимума осталось: *{max(0, 25 - u['discount'])}%*"
            ),
            parse_mode="Markdown"
        )

    elif action == "reject":
        submission["status"] = "rejected"
        save_data(data)

        await query.edit_message_caption(
            f"❌ *Отклонено*\n{query.message.caption}",
            parse_mode="Markdown"
        )
        await context.bot.send_message(
            chat_id=int(user_id),
            text=(
                "❌ *Чек не подтверждён.*\n\n"
                "Возможные причины:\n"
                "• Сумма чека менее 1500 ₽\n"
                "• Нечитаемое фото\n"
                "• Не указан адрес или сотрудник\n\n"
                "Обратитесь к администратору за уточнением."
            ),
            parse_mode="Markdown"
        )


# ─── Запуск ─────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("submit", submit_start)],
        states={
            WAITING_FOR_SUBMISSION: [
                MessageHandler(filters.PHOTO, receive_submission)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mystatus", my_status))
    app.add_handler(CommandHandler("list", admin_list))
    app.add_handler(CommandHandler("setdiscount", admin_set_discount))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(handle_admin_callback))

    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()