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

# ===== КЛАВИАТУРЫ =====
def main_menu(is_admin=False):
    kb = [
        [InlineKeyboardButton(text="🔥 Отметиться", callback_data="mark")],
        [InlineKeyboardButton(text="👥 Огонь с друзьями", callback_data="pair_menu")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
    ]
    if is_admin:
        kb.append([InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def pair_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Пригласить друга", callback_data="create_pair")],
        [InlineKeyboardButton(text="📋 Мои огни", callback_data="my_pairs")],
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

# ===== ГЛАВНОЕ МЕНЮ =====
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

# ===== START =====
@dp.message(CommandStart())
async def cmd_start(message: Message):
    try:
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
                await message.answer("❌ Нельзя создать огонь с самим собой")
                return

            pair["user2_id"] = uid
            save_db(db)

            try:
                await bot.send_message(
                    int(pair["user1_id"]),
                    f"🔥 У вас огонь с @{message.from_user.username or 'друг'}!\n"
                    f"Отмечайтесь оба до 00:00."
                )
            except:
                pass

            await message.answer(
                "🔥 У вас теперь общий огонь!\nОба отмечайтесь до 00:00.",
                reply_markup=back_main_kb()
            )
            return

        text, kb = render_main(message.from_user.id)
        await message.answer(text, reply_markup=kb)
    except Exception as e:
        print("start error:", e)

# ===== НАЗАД =====
@dp.callback_query(F.data == "back_main")
async def back_main(call: CallbackQuery):
    try:
        text, kb = render_main(call.from_user.id)
        await call.message.edit_text(text, reply_markup=kb)
    except:
        pass
    await call.answer()

# ===== ОТМЕТКА =====
@dp.callback_query(F.data == "mark")
async def mark(call: CallbackQuery):
    try:
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

        # Отметка во всех парах
        for pid, pair in db["pairs"].items():
            if pair.get("user2_id") is None:
                continue
            if pair["user1_id"] == uid:
                pair["user1_marked"] = True
            elif pair["user2_id"] == uid:
                pair["user2_marked"] = True
            else:
                continue

            if pair.get("user1_marked") and pair.get("user2_marked"):
                pair["streak"] = pair.get("streak", 0) + 1
                pair["last_mark_date"] = today

        save_db(db)

        await call.answer(f"🔥 Огонёк: {u['streak']} дней!", show_alert=False)
        text, kb = render_main(call.from_user.id)
        try:
            await call.message.edit_text(text, reply_markup=kb)
        except:
            pass
    except Exception as e:
        print("mark error:", e)
        await call.answer("Ошибка, попробуй ещё", show_alert=True)

# ===== СТАТИСТИКА =====
@dp.callback_query(F.data == "stats")
async def stats(call: CallbackQuery):
    try:
        db = load_db()
        u = db["users"].get(str(call.from_user.id), {})
        # Считаем сколько пар
        pairs_count = 0
        for pid, pair in db["pairs"].items():
            if pair.get("user2_id") and str(call.from_user.id) in [pair["user1_id"], pair["user2_id"]]:
                pairs_count += 1

        text = (
            f"📊 Твоя статистика\n\n"
            f"🔥 Личный огонёк: {u.get('streak', 0)}\n"
            f"🏆 Рекорд: {u.get('best_streak', 0)}\n"
            f"👥 Огней с друзьями: {pairs_count}\n"
            f"📅 Последняя отметка: {u.get('last_mark_date') or '—'}"
        )
        await call.message.edit_text(text, reply_markup=back_main_kb())
    except:
        pass
    await call.answer()

# ===== МЕНЮ ПАР =====
@dp.callback_query(F.data == "pair_menu")
async def pair_menu_handler(call: CallbackQuery):
    try:
        await call.message.edit_text("👥 Огонь с друзьями\n\nВыбери действие:", reply_markup=pair_menu())
    except:
        pass
    await call.answer()

# ===== СОЗДАТЬ ПАРУ =====
@dp.callback_query(F.data == "create_pair")
async def create_pair(call: CallbackQuery):
    try:
        db = load_db()
        uid = str(call.from_user.id)

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
        save_db(db)

        link = f"https://t.me/{(await bot.get_me()).username}?start=pair_{pair_id}"
        await call.message.edit_text(
            f"Отправь эту ссылку другу:\n\n{link}\n\nКогда он зайдёт — у вас появится общий огонь.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={link}")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="pair_menu")],
            ])
        )
    except Exception as e:
        print("create_pair error:", e)
    await call.answer()

# ===== МОИ ОГНИ (список) =====
@dp.callback_query(F.data == "my_pairs")
async def my_pairs(call: CallbackQuery):
    try:
        db = load_db()
        uid = str(call.from_user.id)

        my = []
        for pid, pair in db["pairs"].items():
            if pair.get("user2_id") is None:
                continue
            if uid in [pair["user1_id"], pair["user2_id"]]:
                my.append((pid, pair))

        if not my:
            await call.message.edit_text(
                "📋 У тебя пока нет огней с друзьями.\n\nНажми «Пригласить друга».",
                reply_markup=pair_menu()
            )
            await call.answer()
            return

        buttons = []
        for pid, pair in my:
            partner_id = pair["user2_id"] if pair["user1_id"] == uid else pair["user1_id"]
            try:
                partner = await bot.get_chat(int(partner_id))
                name = f"@{partner.username}" if partner.username else partner.first_name
            except:
                name = "друг"
            buttons.append([
                InlineKeyboardButton(
                    text=f"🔥 {name} — {pair.get('streak', 0)} дн.",
                    callback_data=f"open_pair_{pid}"
                )
            ])
        buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="pair_menu")])

        await call.message.edit_text(
            "📋 Твои огни с друзьями:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    except Exception as e:
        print("my_pairs error:", e)
    await call.answer()

# ===== ОТКРЫТЬ КОНКРЕТНУЮ ПАРУ =====
@dp.callback_query(F.data.startswith("open_pair_"))
async def open_pair(call: CallbackQuery):
    try:
        pid = call.data.replace("open_pair_", "")
        db = load_db()
        uid = str(call.from_user.id)
        pair = db["pairs"].get(pid)

        if not pair or uid not in [pair["user1_id"], pair["user2_id"]]:
            await call.answer("❌ Нет доступа", show_alert=True)
            return

        partner_id = pair["user2_id"] if pair["user1_id"] == uid else pair["user1_id"]
        try:
            partner = await bot.get_chat(int(partner_id))
            name = f"@{partner.username}" if partner.username else partner.first_name
        except:
            name = "друг"

        my_mark = "✅" if (pair["user1_marked"] if pair["user1_id"] == uid else pair["user2_marked"]) else "⏳"
        his_mark = "✅" if (pair["user2_marked"] if pair["user1_id"] == uid else pair["user1_marked"]) else "⏳"

        text = (
            f"🔥 Огонь с {name} — {pair.get('streak', 0)} дней\n\n"
            f"{my_mark} Ты\n"
            f"{his_mark} {name}"
        )
        await call.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔥 Отметиться", callback_data="mark")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="my_pairs")],
            ])
        )
    except Exception as e:
        print("open_pair error:", e)
    await call.answer()

# ===== АДМИНКА =====
@dp.callback_query(F.data == "admin")
async def admin(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("❌ Нет доступа", show_alert=True)
        return
    try:
        await call.message.edit_text("🛠 Админ-панель", reply_markup=admin_menu())
    except:
        pass
    await call.answer()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    try:
        db = load_db()
        users = len(db["users"])
        pairs = len(db["pairs"])
        top = sorted(db["users"].items(), key=lambda x: x[1].get("streak", 0), reverse=True)[:5]
        top_text = "\n".join([f"{i+1}. ID {uid} — {u.get('streak',0)} дней" for i, (uid, u) in enumerate(top)])
        await call.message.edit_text(
            f"📊 Юзеров: {users}\n👥 Пар: {pairs}\n\n🏆 Топ-5:\n{top_text}",
            reply_markup=admin_menu()
        )
    except:
        pass
    await call.answer()

@dp.callback_query(F.data == "admin_user")
async def admin_user(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    try:
        await call.message.edit_text("Введи: ID юзера и число\nПример: 123456789 100", reply_markup=back_main_kb())
    except:
        pass
    await call.answer()

@dp.callback_query(F.data == "admin_pair")
async def admin_pair(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    try:
        await call.message.edit_text("Введи: ID пары и число\nПример: 1 100", reply_markup=back_main_kb())
    except:
        pass
    await call.answer()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    try:
        await call.message.edit_text("Введи текст для рассылки:", reply_markup=back_main_kb())
    except:
        pass
    await call.answer()

# ===== АДМИН-ТЕКСТ =====
@dp.message(F.from_user.id == ADMIN_ID)
async def admin_text(message: Message):
    try:
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
    except Exception as e:
        print("admin_text error:", e)

# ===== ЦИКЛ 00:00 =====
async def daily_reset():
    try:
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
    except Exception as e:
        print("daily_reset error:", e)

async def reminder():
    try:
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
    except Exception as e:
        print("reminder error:", e)

async def main():
    scheduler.add_job(daily_reset, "cron", hour=21, minute=0)
    scheduler.add_job(reminder, "cron", hour=18, minute=0)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
