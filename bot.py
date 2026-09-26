import os
import json
import asyncio
import random
import time
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
CHANNEL = "@firebotp"
CHANNEL_URL = "https://t.me/firebotp"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

DB_FILE = "db.json"

# ===== КУЛДАУН (антиспам) =====
_last_click = {}

def cooldown(user_id, seconds=1):
    now = time.time()
    last = _last_click.get(user_id, 0)
    if now - last < seconds:
        return False
    _last_click[user_id] = now
    return True

# ===== БАЗА =====
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

def time_to_midnight():
    now = datetime.utcnow() + timedelta(hours=TZ_OFFSET)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    delta = midnight - now
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    return f"{hours}ч {minutes}м"

# ===== КРАСИВЫЕ ТЕКСТЫ =====
MARK_PHRASES = [
    "🔥 Огонь горит ярче!",
    "💪 Ты сегодня красавчик!",
    "🚀 Ещё один день в копилку!",
    "⚡ Так держать!",
    "🏆 Не сбавляй обороты!",
    "💎 Твоя дисциплина растёт!",
    "🎯 Ещё день — ещё победа!",
]

BURN_PHRASES = [
    "💀 Огонёк сгорел... Начни заново!",
    "🥶 Холодно без огня? Зажги снова!",
    "😢 Серия прервалась. Не сдавайся!",
]

def progress_bar(current, target):
    if target <= 0:
        return "▱▱▱▱▱▱▱▱▱▱"
    filled = min(10, int((current / target) * 10))
    return "▰" * filled + "▱" * (10 - filled)

# ===== ПРОВЕРКА ПОДПИСКИ =====
async def is_subscribed(user_id):
    try:
        member = await bot.get_chat_member(CHANNEL, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        print("sub check error:", e)
        return False

def subscribe_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")],
    ])

async def send_subscribe(msg_or_call):
    text = (
        "╔══════════════════════╗\n"
        "   🔒 ДОСТУП ЗАКРЫТ\n"
        "╚══════════════════════╝\n\n"
        "Чтобы пользоваться ботом,\n"
        "подпишись на наш канал:\n\n"
        f"👉 {CHANNEL}\n\n"
        "После подписки нажми кнопку ниже 👇"
    )
    if isinstance(msg_or_call, Message):
        await msg_or_call.answer(text, reply_markup=subscribe_kb())
    else:
        try:
            await msg_or_call.message.edit_text(text, reply_markup=subscribe_kb())
        except:
            pass

# ===== КЛАВИАТУРЫ =====
def main_menu(is_admin=False):
    db = load_db()
    kb = [
        [InlineKeyboardButton(text="🔥 Отметиться", callback_data="mark")],
        [InlineKeyboardButton(text="👥 Огонь с друзьями", callback_data="pair_menu")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats"),
         InlineKeyboardButton(text="🏆 Топ-10", callback_data="top")],
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
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="back_main")]
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

    # Прогресс к рекорду
    if best > 0:
        bar = progress_bar(streak, best)
    else:
        bar = "▱▱▱▱▱▱▱▱▱▱"

    if marked:
        status = "✅ Сегодня отмечен"
        timer = ""
    else:
        status = "⏳ Ещё не отмечен"
        timer = f"\n⏰ До сброса: {time_to_midnight()}"

    text = (
        "╔══════════════════════╗\n"
        "       🔥 ОГОНЁК 🔥\n"
        "╚══════════════════════╝\n\n"
        f"🔥 Серия: {streak} дн.\n"
        f"🏆 Рекорд: {best} дн.\n"
        f"📊 {bar}\n\n"
        f"{status}{timer}"
    )
    return text, main_menu(is_admin=(user_id == ADMIN_ID))

# ===== START =====
@dp.message(CommandStart())
async def cmd_start(message: Message):
    try:
        uid = message.from_user.id
        args = message.text.split()

        if not await is_subscribed(uid):
            await send_subscribe(message)
            return

        db = load_db()
        sid = str(uid)

        if sid not in db["users"]:
            db["users"][sid] = {"streak": 0, "best_streak": 0, "last_mark_date": None}
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
            if pair["user1_id"] == sid:
                await message.answer("❌ Нельзя создать огонь с самим собой")
                return

            pair["user2_id"] = sid
            save_db(db)

            try:
                await bot.send_message(
                    int(pair["user1_id"]),
                    "╔══════════════════════╗\n"
                    "   🔥 НОВЫЙ ОГОНЬ 🔥\n"
                    "╚══════════════════════╝\n\n"
                    f"Ты в паре с @{message.from_user.username or 'друг'}!\n"
                    "Отмечайтесь оба до 00:00."
                )
            except:
                pass

            await message.answer(
                "🔥 У вас теперь общий огонь!\n\nОба отмечайтесь до 00:00.",
                reply_markup=back_main_kb()
            )
            return

        text, kb = render_main(uid)
        await message.answer(text, reply_markup=kb)
    except Exception as e:
        print("start error:", e)

@dp.callback_query(F.data == "check_sub")
async def check_sub(call: CallbackQuery):
    try:
        if await is_subscribed(call.from_user.id):
            await call.answer("✅ Спасибо за подписку!", show_alert=False)
            text, kb = render_main(call.from_user.id)
            try:
                await call.message.edit_text(text, reply_markup=kb)
            except:
                await call.message.answer(text, reply_markup=kb)
        else:
            await call.answer("❌ Ты ещё не подписался!", show_alert=True)
    except Exception as e:
        print("check_sub error:", e)
        await call.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data == "back_main")
async def back_main(call: CallbackQuery):
    if not cooldown(call.from_user.id):
        await call.answer()
        return
    try:
        if not await is_subscribed(call.from_user.id):
            await send_subscribe(call)
            await call.answer()
            return
        text, kb = render_main(call.from_user.id)
        await call.message.edit_text(text, reply_markup=kb)
    except:
        pass
    await call.answer()

# ===== ОТМЕТКА =====
@dp.callback_query(F.data == "mark")
async def mark(call: CallbackQuery):
    if not cooldown(call.from_user.id):
        await call.answer()
        return
    try:
        if not await is_subscribed(call.from_user.id):
            await send_subscribe(call)
            await call.answer()
            return

        db = load_db()
        uid = str(call.from_user.id)
        u = db["users"].setdefault(uid, {"streak": 0, "best_streak": 0, "last_mark_date": None})
        today = today_str()

        if u.get("last_mark_date") == today:
            await call.answer("✅ Ты уже отметился сегодня!", show_alert=True)
            return

        u["streak"] = u.get("streak", 0) + 1
        is_new_record = u["streak"] > u.get("best_streak", 0)
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

        phrase = random.choice(MARK_PHRASES)
        if is_new_record:
            alert = f"🏆 НОВЫЙ РЕКОРД: {u['streak']}!"
        else:
            alert = phrase

        await call.answer(alert, show_alert=False)
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
    if not cooldown(call.from_user.id):
        await call.answer()
        return
    try:
        if not await is_subscribed(call.from_user.id):
            await send_subscribe(call)
            await call.answer()
            return

        db = load_db()
        u = db["users"].get(str(call.from_user.id), {})
        pairs_count = 0
        for pid, pair in db["pairs"].items():
            if pair.get("user2_id") and str(call.from_user.id) in [pair["user1_id"], pair["user2_id"]]:
                pairs_count += 1

        streak = u.get("streak", 0)
        best = u.get("best_streak", 0)
        bar = progress_bar(streak, best) if best > 0 else "▱▱▱▱▱▱▱▱▱▱"

        text = (
            "╔══════════════════════╗\n"
            "      📊 СТАТИСТИКА\n"
            "╚══════════════════════╝\n\n"
            f"🔥 Личный огонёк: {streak} дн.\n"
            f"🏆 Рекорд: {best} дн.\n"
            f"📊 {bar}\n\n"
            f"👥 Огней с друзьями: {pairs_count}\n"
            f"📅 Последняя отметка: {u.get('last_mark_date') or '—'}"
        )
        await call.message.edit_text(text, reply_markup=back_main_kb())
    except:
        pass
    await call.answer()

# ===== ТОП-10 =====
@dp.callback_query(F.data == "top")
async def top(call: CallbackQuery):
    if not cooldown(call.from_user.id):
        await call.answer()
        return
    try:
        if not await is_subscribed(call.from_user.id):
            await send_subscribe(call)
            await call.answer()
            return

        db = load_db()
        sorted_users = sorted(db["users"].items(), key=lambda x: x[1].get("streak", 0), reverse=True)[:10]

        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, (uid, u) in enumerate(sorted_users):
            prefix = medals[i] if i < 3 else f"{i+1}."
            streak = u.get("streak", 0)
            lines.append(f"{prefix} {streak} дн. — ID {uid}")

        text = (
            "╔══════════════════════╗\n"
            "        🏆 ТОП-10\n"
            "╚══════════════════════╝\n\n"
            + "\n".join(lines)
        )
        await call.message.edit_text(text, reply_markup=back_main_kb())
    except:
        pass
    await call.answer()

# ===== МЕНЮ ПАР =====
@dp.callback_query(F.data == "pair_menu")
async def pair_menu_handler(call: CallbackQuery):
    if not cooldown(call.from_user.id):
        await call.answer()
        return
    try:
        if not await is_subscribed(call.from_user.id):
            await send_subscribe(call)
            await call.answer()
            return
        text = (
            "╔══════════════════════╗\n"
            "    👥 ОГОНЬ С ДРУЗЬЯМИ\n"
            "╚══════════════════════╝\n\n"
            "Приглашай друзей и ведите огонь вместе.\n"
            "Оба должны отметиться до 00:00."
        )
        await call.message.edit_text(text, reply_markup=pair_menu())
    except:
        pass
    await call.answer()

# ===== СОЗДАТЬ ПАРУ =====
@dp.callback_query(F.data == "create_pair")
async def create_pair(call: CallbackQuery):
    if not cooldown(call.from_user.id):
        await call.answer()
        return
    try:
        if not await is_subscribed(call.from_user.id):
            await send_subscribe(call)
            await call.answer()
            return

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
        text = (
            "╔══════════════════════╗\n"
            "     📤 ПРИГЛАШЕНИЕ\n"
            "╚══════════════════════╝\n\n"
            "Отправь ссылку другу:\n\n"
            f"{link}\n\n"
            "Когда он зайдёт — у вас будет общий огонь."
        )
        await call.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={link}")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="pair_menu")],
            ])
        )
    except Exception as e:
        print("create_pair error:", e)
    await call.answer()

# ===== МОИ ОГНИ =====
@dp.callback_query(F.data == "my_pairs")
async def my_pairs(call: CallbackQuery):
    if not cooldown(call.from_user.id):
        await call.answer()
        return
    try:
        if not await is_subscribed(call.from_user.id):
            await send_subscribe(call)
            await call.answer()
            return

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
                "╔══════════════════════╗\n"
                "      📋 МОИ ОГНИ\n"
                "╚══════════════════════╝\n\n"
                "Пока пусто.\nНажми «Пригласить друга».",
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
            # статус
            my_m = pair["user1_marked"] if pair["user1_id"] == uid else pair["user2_marked"]
            his_m = pair["user2_marked"] if pair["user1_id"] == uid else pair["user1_marked"]
            if my_m and his_m:
                status = "🔥"
            elif my_m or his_m:
                status = "⚠️"
            else:
                status = "💤"
            buttons.append([
                InlineKeyboardButton(
                    text=f"{status} {name} — {pair.get('streak', 0)} дн.",
                    callback_data=f"open_pair_{pid}"
                )
            ])
        buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="pair_menu")])

        await call.message.edit_text(
            "╔══════════════════════╗\n"
            "      📋 МОИ ОГНИ\n"
            "╚══════════════════════╝\n\n"
            "🔥 оба отметились\n"
            "⚠️ ждём одного\n"
            "💤 ещё не отмечались",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    except Exception as e:
        print("my_pairs error:", e)
    await call.answer()

# ===== ОТКРЫТЬ ПАРУ =====
@dp.callback_query(F.data.startswith("open_pair_"))
async def open_pair(call: CallbackQuery):
    if not cooldown(call.from_user.id):
        await call.answer()
        return
    try:
        if not await is_subscribed(call.from_user.id):
            await send_subscribe(call)
            await call.answer()
            return

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
            "╔══════════════════════╗\n"
            "      🔥 ВАШ ОГОНЬ\n"
            "╚══════════════════════╝\n\n"
            f"👤 Друг: {name}\n"
            f"🔥 Серия: {pair.get('streak', 0)} дн.\n\n"
            f"{my_mark} Ты\n"
            f"{his_mark} {name}"
        )
        await call.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔥 Отметиться", callback_data="mark")],
                [InlineKeyboardButton(text="❌ Разорвать", callback_data=f"confirm_break_{pid}")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="my_pairs")],
            ])
        )
    except Exception as e:
        print("open_pair error:", e)
    await call.answer()

# ===== ПОДТВЕРЖДЕНИЕ РАЗРЫВА =====
@dp.callback_query(F.data.startswith("confirm_break_"))
async def confirm_break(call: CallbackQuery):
    pid = call.data.replace("confirm_break_", "")
    try:
        await call.message.edit_text(
            "⚠️ Точно разорвать огонь?\n\nСерия сгорит навсегда.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Да, разорвать", callback_data=f"break_{pid}")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data=f"open_pair_{pid}")],
            ])
        )
    except:
        pass
    await call.answer()

@dp.callback_query(F.data.startswith("break_"))
async def do_break(call: CallbackQuery):
    pid = call.data.replace("break_", "")
    try:
        db = load_db()
        uid = str(call.from_user.id)
        pair = db["pairs"].get(pid)
        if not pair or uid not in [pair["user1_id"], pair["user2_id"]]:
            await call.answer("❌ Нет доступа", show_alert=True)
            return

        partner_id = pair["user2_id"] if pair["user1_id"] == uid else pair["user1_id"]
        del db["pairs"][pid]
        save_db(db)

        try:
            await bot.send_message(int(partner_id), "💔 Твой друг разорвал огонь.")
        except:
            pass

        await call.answer("Огонь разорван", show_alert=False)
        await call.message.edit_text(
            "💔 Огонь разорван.",
            reply_markup=pair_menu()
        )
    except Exception as e:
        print("break error:", e)
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
        total_streak = sum(u.get("streak", 0) for u in db["users"].values())
        top = sorted(db["users"].items(), key=lambda x: x[1].get("streak", 0), reverse=True)[:5]
        top_text = "\n".join([f"{i+1}. ID {uid} — {u.get('streak',0)} дн." for i, (uid, u) in enumerate(top)])
        await call.message.edit_text(
            f"📊 Юзеров: {users}\n"
            f"👥 Пар: {pairs}\n"
            f"🔥 Суммарный стрик: {total_streak}\n\n"
            f"🏆 Топ-5:\n{top_text}",
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
                    phrase = random.choice(BURN_PHRASES)
                    await bot.send_message(int(uid), f"{phrase}\n\nНажми /start")
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
                        "⚠️ Огонёк сгорит через 3 часа!\nУспей отметиться 👇",
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
