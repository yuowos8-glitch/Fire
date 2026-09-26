import os
import json
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import CommandStart
from apscheduler.schedulers.asyncio import AsyncIOScheduler

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
TZ_OFFSET = 3

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

DB_FILE = "db.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}, "pairs": {}, "next_pair_id": 1}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def today_str():
    now = datetime.utcnow() + timedelta(hours=TZ_OFFSET)
    return now.strftime("%Y-%m-%d")

def main_menu(is_admin=False):
    kb = [
        [InlineKeyboardButton(text="🔥 Отметиться", callback_data="mark")],
        [InlineKeyboardButton(text="👥 Огонь с другом", callback_data="pair_menu")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
    ]
    if is_admin:
        kb.append([InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def pair_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать пару", callback_data="create_pair")],
        [InlineKeyboardButton(text="📋 Моя пара", callback_data="my_pair")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")],
    ])

def back_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Накрутить юзеру", callback_data="admin_user")],
        [InlineKeyboardButton(text="👥 Накрутить паре", callback_data="admin_pair")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")],
    ])

def render_main(user_id):
    db = load_db()
    u = db["users"].get(str(user_id), {})
    streak = u.get("streak", 0)
    best = u.get("best_streak", 0)
    marked = u.get("last_mark_date") == today_str()
    text = (
        f"🔥 Твой огонёк: {streak} дней\n"
        f"🏆 Рекорд: {best} дней\n"
        f"{'✅ Сегодня отмечен' if marked else '⏳ Ещё не отмечен'}"
    )
    return text, main_menu(is_admin=(user_id == ADMIN_ID))

@dp.message(CommandStart())
async def cmd_start(message: Message):
    args = message.text.split()
    db = load_db()
    uid = str(message.from_user.id)

    if uid not in db["users"]:
        db["users"][uid] = {"streak": 0, "best_streak": 0, "last_mark_date": None}
        save_db(db)

    if len(args) > 1 and args[1].startswith("pair_"):
        pair_id = args[1].replace("pair_", "")
        pair = db["pairs"].get(pair_id)
        if not pair:
            await message.answer("❌ Ссылка недействительна")
            return
        if pair["user2_id"] is not None:
            await message.answer("❌ Пара уже занята")
            return
        if pair["user1_id"] == uid:
            await message.answer("❌ Нельзя создать пару с самим собой")
            return

        pair["user2_id"] = uid
        db["users"][uid]["pair_id"] = pair_id
        save_db(db)

        try:
            await bot.send_message(
                int(pair["user1_id"]),
                f"🔥 Вы в паре с @{message.from_user.username or 'друг'}!\n"
                f"Отмечайтесь оба до 00:00."
            )
        except:
            pass

        await message.answer("🔥 Вы в паре!\nОба отмечайтесь до 00:00.", reply_markup=back_main_kb())
        return

    text, kb = render_main(message.from_user.id)
    await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "back_main")
async def back_main(call: CallbackQuery):
    text, kb = render_main(call.from_user.id)
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data == "mark")
async def mark(call: CallbackQuery):
    db = load_db()
    uid = str(call.from_user.id)
    u = db["users"].setdefault(uid, {"streak": 0, "best_streak": 0, "last_mark_date": None})
    today = today_str()

    if u.get("last_mark_date") == today:
        await call.answer("✅ Ты уже отметился сегодня!", show_alert=True)
        return

    u["streak"] = u.get("streak", 0) + 1
    u["best_streak"] = max(u.get("best_streak", 0), u["streak"])
    u["last_mark_date"] = today

    pair_id = u.get("pair_id")
    if pair_id and pair_id in db["pairs"]:
        pair = db["pairs"][pair_id]
        if pair["user1_id"] == uid:
            pair["user1_marked"] = True
            partner_id = pair["user2_id"]
        elif pair["user2_id"] == uid:
            pair["user2_marked"] = True
            partner_id = pair["user1_id"]
        else:
            partner_id = None

        if partner_id and pair.get("user1_marked") and pair.get("user2_marked"):
            pair["streak"] = pair.get("streak", 0) + 1
            pair["last_mark_date"] = today

    save_db(db)

    await call.answer(f"🔥 Огонёк: {u['streak']} дней!", show_alert=True)
    text, kb = render_main(call.from_user.id)
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data == "stats")
async def stats(call: CallbackQuery):
    db = load_db()
    u = db["users"].get(str(call.from_user.id), {})
    text = (
        f"📊 Твоя статистика\n\n"
        f"🔥 Текущий огонёк: {u.get('streak', 0)}\n"
        f"🏆 Рекорд: {u.get('best_streak', 0)}\n"
        f"📅 Последняя отметка: {u.get('last_mark_date') or '—'}"
    )
    await call.message.edit_text(text, reply_markup=back_main_kb())

@dp.callback_query(F.data == "pair_menu")
async def pair_menu_handler(call: CallbackQuery):
    await call.message.edit_text("👥 Огонь с другом\n\nВыбери действие:", reply_markup=pair_menu())

@dp.callback_query(F.data == "create_pair")
async def create_pair(call: CallbackQuery):
    db = load_db()
    uid = str(call.from_user.id)

    if db["users"].get(uid, {}).get("pair_id"):
        await call.answer("❌ У тебя уже есть пара", show_alert=True)
        return

    pair_id = str(db["next_pair_id"])
    db["next_pair_id"] += 1
    db["pairs"][pair_id] = {
        "user1_id": uid,
        "user2_id": None,
        "streak": 0,
        "last_mark_date": None,
        "user1_marked": False,
        "user2_marked": False,
    }
    db["users"].setdefault(uid, {"streak": 0, "best_streak": 0, "last_mark_date": None})
    db["users"][uid]["pair_id"] = pair_id
    save_db(db)

    link = f"https://t.me/{(await bot.get_me()).username}?start=pair_{pair_id}"
    await call.message.edit_text(
        f"Отправь эту ссылку другу:\n\n{link}\n\nКогда он зайдёт — вы в паре.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={link}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="pair_menu")],
        ])
    )

@dp.callback_query(F.data == "my_pair")
async def my_pair(call: CallbackQuery):
    db = load_db()
    uid = str(call.from_user.id)
    pair_id = db["users"].get(uid, {}).get("pair_id")

    if not pair_id or pair_id not in db["pairs"]:
        await call.answer("❌ У тебя нет пары", show_alert=True)
        return

    pair = db["pairs"][pair_id]
    partner_id = pair["user2_id"] if pair["user1_id"] == uid else pair["user1_id"]

    if not partner_id:
        await call.answer("⏳ Ждём, пока друг зайдёт", show_alert=True)
        return

    try:
        partner = await bot.get_chat(int(partner_id))
        partner_name = f"@{partner.username}" if partner.username else partner.first_name
    except:
        partner_name = "друг"

    my_mark = "✅" if (pair["user1_marked"] if pair["user1_id"] == uid else pair["user2_marked"]) else "⏳"
    his_mark = "✅" if (pair["user2_marked"] if pair["user1_id"] == uid else pair["user1_marked"]) else "⏳"

    text = (
        f"🔥 Пара с {partner_name} — {pair.get('streak', 0)} дней\n\n"
        f"{my_mark} Ты\n"
        f"{his_mark} {partner_name}"
    )
    await call.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔥 Отметиться", callback_data="mark")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="pair_menu")],
        ])
    )

@dp.callback_query(F.data == "admin")
async def admin(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("❌ Нет доступа", show_alert=True)
        return
    await call.message.edit_text("🛠 Админ-панель", reply_markup=admin_menu())

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    db = load_db()
    users = len(db["users"])
    pairs = len(db["pairs"])
    top = sorted(db["users"].items(), key=lambda x: x[1].get("streak", 0), reverse=True)[:5]
    top_text = "\n".join([f"{i+1}. ID {uid} — {u.get('streak',0)} дней" for i, (uid, u) in enumerate(top)])
    await call.message.edit_text(
        f"📊 Юзеров: {users}\n👥 Пар: {pairs}\n\n🏆 Топ-5:\n{top_text}",
        reply_markup=admin_menu()
    )

@dp.callback_query(F.data == "admin_user")
async def admin_user(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text("Введи: ID юзера и число\nПример: 123456789 100", reply_markup=back_main_kb())

@dp.callback_query(F.data == "admin_pair")
async def admin_pair(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text("Введи: ID пары и число\nПример: 1 100", reply_markup=back_main_kb())

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text("Введи текст для рассылки:", reply_markup=back_main_kb())

@dp.message(F.from_user.id == ADMIN_ID)
async def admin_text(message: Message):
    db = load_db()
    text = message.text or ""
    parts = text.split()

    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        uid, num = parts[0], int(parts[1])
        if uid in db["users"]:
            db["users"][uid]["streak"] = num
            db["users"][uid]["best_streak"] = max(db["users"][uid].get("best_streak", 0), num)
            save_db(db)
            await message.answer(f"✅ Юзеру {uid} накручено {num}")
            return

    if text.startswith("pair ") and len(parts) == 3:
        pid, num = parts[1], int(parts[2])
        if pid in db["pairs"]:
            db["pairs"][pid]["streak"] = num
            save_db(db)
            await message.answer(f"✅ Паре {pid} накручено {num}")
            return

    if text.startswith("broadcast "):
        msg = text.replace("broadcast ", "", 1)
        sent = 0
        for uid in db["users"]:
            try:
                await bot.send_message(int(uid), msg)
                sent += 1
            except:
                pass
        await message.answer(f"✅ Отправлено {sent}")
        return

    await message.answer("❌ Не понял.")

async def daily_reset():
    db = load_db()
    today = today_str()
    for uid, u in db["users"].items():
        if u.get("last_mark_date") != today:
            u["streak"] = 0
            u["last_mark_date"] = None
            try:
                await bot.send_message(int(uid), "💀 Твой огонёк сгорел. Начни заново!\n\nНажми /start")
            except:
                pass
    for pid, pair in db["pairs"].items():
        if pair.get("user2_id") is None:
            continue
        if not (pair.get("user1_marked") and pair.get("user2_marked")):
            pair["streak"] = 0
            pair["last_mark_date"] = None
        pair["user1_marked"] = False
        pair["user2_marked"] = False
    save_db(db)

async def reminder():
    db = load_db()
    today = today_str()
    for uid, u in db["users"].items():
        if u.get("last_mark_date") != today:
            try:
                await bot.send_message(
                    int(uid),
                    "⚠️ Огонёк сгорит в полночь!",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔥 Отметиться", callback_data="mark")]
                    ])
                )
            except:
                pass

async def main():
    scheduler.add_job(daily_reset, "cron", hour=21, minute=0)
    scheduler.add_job(reminder, "cron", hour=18, minute=0)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())