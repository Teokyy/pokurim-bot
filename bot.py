import logging
import asyncio
import platform
import os
import time
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8690003152:AAEg4RBIqYy_bId65l0pwaz6SrwonlyoUI8")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "1320584749"))
DATA_FILE = os.environ.get("DATA_FILE", "users.json")
WAITING_FOR_SUBMISSION = 1

SHOPS = ["Сахарова 53", "Парина 33", "Ландау 45", "Сахарова 95"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ─── ДАННЫЕ ──────────────────────────────────────────────────────────────────

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
        data[uid] = {"discount": 0, "submissions": [], "name": "", "shop": None}
    return data[uid]

# ─── КЛАВИАТУРЫ ──────────────────────────────────────────────────────────────

def get_user_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📸 Отправить чек"), KeyboardButton("📊 Моя статистика")],
        [KeyboardButton("💳 Использовать скидку"), KeyboardButton("📋 История чеков")],
    ], resize_keyboard=True)

def get_admin_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📊 Статистика"), KeyboardButton("⏳ Ожидающие чеки")],
        [KeyboardButton("👥 Пользователи"), KeyboardButton("🏆 Конкурс магазинов")],
        [KeyboardButton("📢 Рассылка")],
    ], resize_keyboard=True)

def get_shop_keyboard():
    keyboard = [[InlineKeyboardButton(shop, callback_data=f"choose_shop|{shop}")] for shop in SHOPS]
    return InlineKeyboardMarkup(keyboard)

# ─── СТАРТ ───────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id == ADMIN_ID:
        await update.message.reply_text(
            "🔧 *Панель администратора*\n\nИспользуй кнопки ниже для управления ботом.",
            parse_mode="Markdown",
            reply_markup=get_admin_keyboard()
        )
        return
    data = load_data()
    u = get_user(data, user.id)
    u["name"] = user.full_name
    save_data(data)
    if not u.get("shop"):
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            f"🏁 *Программа лояльности сети «Покурим?!»*\n\n"
            f"Для начала выбери свой магазин:",
            parse_mode="Markdown",
            reply_markup=get_shop_keyboard()
        )
        return
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        f"🏁 *Программа лояльности сети «Покурим?!»*\n\n"
        f"Отправляй чеки от 1500 ₽ и получай скидку в «Апекс Симрейсинг».\n"
        f"Каждый подтверждённый чек = *+2% скидки* (макс. 25%)\n\n"
        f"🏪 Твой магазин: *{u['shop']}*\n"
        f"💳 Твоя текущая скидка: *{u['discount']}%*",
        parse_mode="Markdown",
        reply_markup=get_user_keyboard()
    )

async def choose_shop_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    shop = query.data.split("|")[1]
    user = update.effective_user
    data = load_data()
    u = get_user(data, user.id)
    u["shop"] = shop
    save_data(data)
    await query.edit_message_text(
        f"✅ Магазин *{shop}* выбран!\n\n"
        f"Отправляй чеки от 1500 ₽ и получай скидку в «Апекс Симрейсинг».\n"
        f"Каждый подтверждённый чек = *+2% скидки* (макс. 25%)",
        parse_mode="Markdown"
    )
    await context.bot.send_message(
        chat_id=user.id,
        text="Используй кнопки меню 👇",
        reply_markup=get_user_keyboard()
    )

# ─── СТАТИСТИКА ──────────────────────────────────────────────────────────────

async def my_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    u = get_user(data, update.effective_user.id)
    count = len([s for s in u["submissions"] if s["status"] == "approved"])
    shop_text = f"🏪 Твой магазин: *{u['shop']}*\n" if u.get("shop") else ""
    await update.message.reply_text(
        f"📊 *Твоя статистика*\n\n"
        f"{shop_text}"
        f"💳 Скидка: *{u['discount']}%* из 25%\n"
        f"✅ Подтверждённых чеков: *{count}*\n"
        f"📝 Всего заявок: *{len(u['submissions'])}*\n\n"
        f"До максимальной скидки осталось: *{max(0, 25 - u['discount'])}%*",
        parse_mode="Markdown",
        reply_markup=get_user_keyboard()
    )

async def my_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    u = get_user(data, update.effective_user.id)
    subs = u["submissions"]
    if not subs:
        await update.message.reply_text("📋 У тебя пока нет отправленных чеков.", reply_markup=get_user_keyboard())
        return
    text = "📋 *История твоих чеков:*\n\n"
    for s in reversed(subs[-20:]):
        if s["status"] == "approved":
            icon, status = "✅", "Подтверждён"
        elif s["status"] == "pending":
            icon, status = "⏳", "Ожидает"
        elif s["status"] == "rejected":
            icon = "❌"
            reason = s.get("reject_reason", "")
            status = f"Отклонён — {reason}" if reason else "Отклонён"
        else:
            icon, status = "❓", s["status"]
        text += f"{icon} {s['date']} — {status}\n"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_user_keyboard())

# ─── ИСПОЛЬЗОВАНИЕ СКИДКИ ─────────────────────────────────────────────────────

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()
    u = get_user(data, user.id)
    if u["discount"] == 0:
        await update.message.reply_text(
            "❌ У тебя пока нет накопленной скидки.\n\nОтправляй чеки через 📸 чтобы накопить!",
            parse_mode="Markdown", reply_markup=get_user_keyboard()
        )
        return
    keyboard = [[
        InlineKeyboardButton("✅ Да, использовать", callback_data=f"redeem_confirm|{user.id}"),
        InlineKeyboardButton("❌ Отмена", callback_data="redeem_cancel")
    ]]
    await update.message.reply_text(
        f"💳 *Использование скидки*\n\n"
        f"Твоя текущая скидка: *{u['discount']}%*\n\n"
        f"После использования скидка обнулится и начнётся новый цикл.\n\nПодтвердить?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def redeem_confirm_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.data.split("|")[1]
    data = load_data()
    u = get_user(data, user_id)
    discount = u["discount"]
    if discount == 0:
        await query.edit_message_text("❌ Скидка уже равна 0.")
        return
    keyboard = [[
        InlineKeyboardButton("✅ Подтвердить", callback_data=f"redeem_admin_ok|{user_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"redeem_admin_no|{user_id}")
    ]]
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"Запрос на использование скидки\n\n"
            f"Пользователь: {u.get('name', '?')}\n"
            f"ID: {user_id}\n"
            f"Скидка: {discount}%\n\n"
            f"Подтверди что скидка была использована в Апекс Симрейсинг:"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await query.edit_message_text("✅ Запрос отправлен! Администратор подтвердит использование скидки.")

async def redeem_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Отменено.")

async def redeem_admin_ok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    user_id = query.data.split("|")[1]
    data = load_data()
    u = get_user(data, user_id)
    old_discount = u["discount"]
    u["discount"] = 0
    save_data(data)
    await query.edit_message_text(f"✅ Скидка {old_discount}% использована. Пользователь {user_id} начинает новый цикл.")
    await context.bot.send_message(
        chat_id=int(user_id),
        text=f"Скидка {old_discount}% успешно использована!\n\nТвой счётчик обнулён — начинай накапливать!\nОтправляй чеки через 📸",
    )

async def redeem_admin_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    user_id = query.data.split("|")[1]
    await query.edit_message_text(f"❌ Использование скидки отклонено для {user_id}.")
    await context.bot.send_message(
        chat_id=int(user_id),
        text="❌ Использование скидки отклонено. Обратитесь к администратору."
    )

# ─── ОТПРАВКА ЧЕКА ───────────────────────────────────────────────────────────

async def submit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()
    u = get_user(data, user.id)
    if not u.get("shop"):
        await update.message.reply_text("Сначала выбери свой магазин:", reply_markup=get_shop_keyboard())
        return ConversationHandler.END
    await update.message.reply_text(
        "📋 *Отправка чека*\n\n"
        "Пришли фото чека.\n\n"
        "Или отправь /cancel для отмены.",
        parse_mode="Markdown"
    )
    return WAITING_FOR_SUBMISSION

async def receive_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = update.effective_user
    if not message.photo:
        await message.reply_text("❌ Нужно отправить фото чека.")
        return WAITING_FOR_SUBMISSION
    data = load_data()
    u = get_user(data, user.id)
    new_file_id = message.photo[-1].file_id
    for s in u["submissions"]:
        if s["file_id"] == new_file_id and s["status"] != "rejected":
            await message.reply_text("❌ Этот чек уже был отправлен ранее.", reply_markup=get_user_keyboard())
            return ConversationHandler.END
    caption = message.caption or ""
    shop = u.get("shop", "Не указан")
    submission_id = f"{user.id}SPLIT{int(datetime.now().timestamp())}"
    submission = {
        "id": submission_id,
        "file_id": new_file_id,
        "caption": caption,
        "status": "pending",
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "user_id": user.id,
        "user_name": user.full_name,
        "username": user.username or "—",
        "shop": shop
    }
    u["submissions"].append(submission)
    save_data(data)
    await message.reply_text(
        f"✅ Заявка принята!\n\nМагазин: {shop}\n\nАдминистратор проверит чек и начислит скидку.\n\nЕсть ещё чек? Нажми 📸",
        reply_markup=get_user_keyboard()
    )
    keyboard = [[
        InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve|{submission_id}|{user.id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject|{submission_id}|{user.id}")
    ]]
    try:
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=new_file_id,
            caption=(
                f"Новая заявка\n\n"
                f"Пользователь: {user.full_name}\n"
                f"@{user.username or '—'}\n"
                f"ID: {user.id}\n"
                f"Магазин: {shop}\n"
                f"Дата: {submission['date']}"
            ),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Ошибка отправки фото админу: {e}")
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"Новая заявка (фото не прикрепилось)\n\n"
                f"Пользователь: {user.full_name}\n"
                f"ID: {user.id}\n"
                f"Магазин: {shop}\n"
                f"Дата: {submission['date']}"
            ),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено.", reply_markup=get_user_keyboard())
    return ConversationHandler.END

# ─── ОБРАБОТКА КНОПОК ADMIN ──────────────────────────────────────────────────

async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != ADMIN_ID:
        return
    parts = query.data.split("|")
    action = parts[0]
    submission_id = parts[1]
    user_id = parts[2]
    data = load_data()
    u = get_user(data, user_id)
    submission = next((s for s in u["submissions"] if s["id"] == submission_id), None)
    if not submission:
        try:
            await query.edit_message_caption("Заявка не найдена.")
        except:
            await query.edit_message_text("Заявка не найдена.")
        return
    if submission["status"] != "pending":
        try:
            await query.edit_message_caption(f"Уже обработана: {submission['status']}")
        except:
            await query.edit_message_text(f"Уже обработана: {submission['status']}")
        return
    if action == "approve":
        u["discount"] = min(25, u["discount"] + 2)
        submission["status"] = "approved"
        save_data(data)
        try:
            await query.edit_message_caption(
                f"Подтверждено\nМагазин: {submission.get('shop','?')}\nНовая скидка: {u['discount']}%"
            )
        except:
            await query.edit_message_text(
                f"Подтверждено\nМагазин: {submission.get('shop','?')}\nНовая скидка: {u['discount']}%"
            )
        await context.bot.send_message(
            chat_id=int(user_id),
            text=f"Чек подтверждён!\n\nВаша скидка: {u['discount']}%\n\nЕсть ещё чек? Нажми 📸"
        )
    elif action == "reject":
        context.user_data["pending_reject"] = {"submission_id": submission_id, "user_id": user_id}
        try:
            await query.edit_message_caption("Напиши причину отклонения следующим сообщением:")
        except:
            await query.edit_message_text("Напиши причину отклонения следующим сообщением:")

async def reject_reason_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if "pending_reject" not in context.user_data:
        return
    reason = update.message.text
    admin_buttons = ["📊 Статистика", "⏳ Ожидающие чеки", "👥 Пользователи", "🏆 Конкурс магазинов", "📢 Рассылка"]
    if reason in admin_buttons:
        return
    submission_id = context.user_data["pending_reject"]["submission_id"]
    user_id = context.user_data["pending_reject"]["user_id"]
    del context.user_data["pending_reject"]
    data = load_data()
    u = get_user(data, user_id)
    submission = next((s for s in u["submissions"] if s["id"] == submission_id), None)
    if not submission:
        await update.message.reply_text("Заявка не найдена.")
        return
    submission["status"] = "rejected"
    submission["reject_reason"] = reason
    save_data(data)
    await update.message.reply_text("❌ Отклонено. Причина отправлена пользователю.", reply_markup=get_admin_keyboard())
    await context.bot.send_message(
        chat_id=int(user_id),
        text=f"❌ Чек не подтверждён.\n\nПричина: {reason}\n\nЕсть другой чек? Нажми 📸"
    )

# ─── АДМИН ПАНЕЛЬ ────────────────────────────────────────────────────────────

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    data = load_data()
    total = approved = pending = rejected = 0
    for u in data.values():
        for s in u.get("submissions", []):
            total += 1
            if s["status"] == "approved": approved += 1
            elif s["status"] == "pending": pending += 1
            elif s["status"] == "rejected": rejected += 1
    await update.message.reply_text(
        f"🔧 *Панель администратора*\n\n"
        f"👥 Пользователей: *{len(data)}*\n\n"
        f"📋 Чеков всего: *{total}*\n"
        f"✅ Подтверждённых: *{approved}*\n"
        f"⏳ Ожидают: *{pending}*\n"
        f"❌ Отклонённых: *{rejected}*",
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard()
    )

async def admin_contest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    data = load_data()
    shop_counts = {shop: 0 for shop in SHOPS}
    for u in data.values():
        shop = u.get("shop")
        if shop in shop_counts:
            for s in u.get("submissions", []):
                if s["status"] == "approved":
                    shop_counts[shop] += 1
    sorted_shops = sorted(shop_counts.items(), key=lambda x: x[1], reverse=True)
    medals = ["🥇", "🥈", "🥉", "4️⃣"]
    text = "🏆 *Конкурс магазинов*\n\n"
    for i, (shop, count) in enumerate(sorted_shops):
        text += f"{medals[i]} *{shop}* — {count} чеков\n"
    text += "\n🎁 Приз: 2 пака Берна для победителя!"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

async def admin_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    data = load_data()
    found = False
    for uid, u in data.items():
        for s in u["submissions"]:
            if s["status"] == "pending":
                found = True
                keyboard = [[
                    InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve|{s['id']}|{uid}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"reject|{s['id']}|{uid}")
                ]]
                try:
                    await context.bot.send_photo(
                        chat_id=ADMIN_ID,
                        photo=s["file_id"],
                        caption=(
                            f"Ожидает подтверждения\n\n"
                            f"Пользователь: {s['user_name']}\n"
                            f"Магазин: {s.get('shop','Не указан')}\n"
                            f"Дата: {s['date']}"
                        ),
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки фото: {e}")
    if not found:
        await update.message.reply_text("✅ Нет чеков ожидающих подтверждения.", reply_markup=get_admin_keyboard())

async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    data = load_data()
    if not data:
        await update.message.reply_text("Пользователей пока нет.", reply_markup=get_admin_keyboard())
        return
    text = "📋 *Все пользователи:*\n\n"
    for uid, u in data.items():
        approved = len([s for s in u["submissions"] if s["status"] == "approved"])
        pending = len([s for s in u["submissions"] if s["status"] == "pending"])
        shop = u.get("shop", "—")
        text += f"👤 {u.get('name','?')} | {uid}\n🏪 {shop} | 💳 {u['discount']}% | ✅ {approved} | ⏳ {pending}\n\n"
    # Разбиваем на части если длинный
    if len(text) > 4000:
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for chunk in chunks:
            await update.message.reply_text(chunk, parse_mode="Markdown", reply_markup=get_admin_keyboard())
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

async def admin_set_discount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        _, user_id, percent = update.message.text.split()
        percent = int(percent)
        assert 0 <= percent <= 25
    except:
        await update.message.reply_text("Использование: /setdiscount USER_ID PERCENT (0-25)", reply_markup=get_admin_keyboard())
        return
    data = load_data()
    u = get_user(data, user_id)
    u["discount"] = percent
    save_data(data)
    await update.message.reply_text(f"✅ Скидка {user_id} = {percent}%", reply_markup=get_admin_keyboard())
    try:
        await context.bot.send_message(chat_id=int(user_id), text=f"Ваша скидка обновлена: {percent}%")
    except:
        pass

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text("Использование: /broadcast текст сообщения", reply_markup=get_admin_keyboard())
        return
    data = load_data()
    success = failed = 0
    for uid in data.keys():
        try:
            await context.bot.send_message(chat_id=int(uid), text=text)
            success += 1
        except:
            failed += 1
    await update.message.reply_text(f"✅ Отправлено: {success}\n❌ Не доставлено: {failed}", reply_markup=get_admin_keyboard())

# ─── ТЕКСТОВЫЕ КНОПКИ ────────────────────────────────────────────────────────

async def handle_text_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    if user.id == ADMIN_ID:
        if text == "📊 Статистика":
            await admin_panel(update, context)
        elif text == "⏳ Ожидающие чеки":
            await admin_pending(update, context)
        elif text == "👥 Пользователи":
            await admin_list(update, context)
        elif text == "🏆 Конкурс магазинов":
            await admin_contest(update, context)
        elif text == "📢 Рассылка":
            await update.message.reply_text("Используй: /broadcast текст", reply_markup=get_admin_keyboard())
        elif "pending_reject" in context.user_data:
            await reject_reason_handler(update, context)
    else:
        if text == "📸 Отправить чек":
            return await submit_start(update, context)
        elif text == "📊 Моя статистика":
            await my_status(update, context)
        elif text == "💳 Использовать скидку":
            await redeem(update, context)
        elif text == "📋 История чеков":
            await my_history(update, context)

# ─── ЗАПУСК ──────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("submit", submit_start),
            MessageHandler(
                filters.TEXT & filters.Regex("^📸 Отправить чек$") & ~filters.User(ADMIN_ID),
                submit_start
            )
        ],
        states={WAITING_FOR_SUBMISSION: [MessageHandler(filters.PHOTO, receive_submission)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mystatus", my_status))
    app.add_handler(CommandHandler("history", my_history))
    app.add_handler(CommandHandler("redeem", redeem))
    app.add_handler(CommandHandler("list", admin_list))
    app.add_handler(CommandHandler("pending", admin_pending))
    app.add_handler(CommandHandler("panel", admin_panel))
    app.add_handler(CommandHandler("contest", admin_contest))
    app.add_handler(CommandHandler("setdiscount", admin_set_discount))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(choose_shop_cb, pattern="^choose_shop\\|"))
    app.add_handler(CallbackQueryHandler(redeem_confirm_user, pattern="^redeem_confirm\\|"))
    app.add_handler(CallbackQueryHandler(redeem_cancel, pattern="^redeem_cancel$"))
    app.add_handler(CallbackQueryHandler(redeem_admin_ok, pattern="^redeem_admin_ok\\|"))
    app.add_handler(CallbackQueryHandler(redeem_admin_no, pattern="^redeem_admin_no\\|"))
    app.add_handler(CallbackQueryHandler(handle_admin_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_buttons))

    print("Покурим бот запущен!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            logger.error(f"Ошибка: {e}. Перезапуск через 5 секунд...")
            time.sleep(5)
