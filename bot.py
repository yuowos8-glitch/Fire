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

# ===== КУЛДАУН =====
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
    h = delta.seconds // 3600
    m = (delta.seconds % 3600) // 60
    return f"{h}ч {m}м"

def last_7_days(marks):
    """marks = список дат 'YYYY-MM-DD'. Возвращает 7 последних дней с отметками"""
    today = datetime.utcnow() + timedelta(hours=TZ_OFFSET)
    result = []
    for i in range(6, -1, -1):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        result.append("✅" if d in marks else "⬜")
    return " ".join(result)

# ===== ИМЯ =====
async def get_name(user_id):
    try:
        chat = await bot.get_chat(int(user_id))
        if chat.username:
            return f"@{chat.username}"
        if chat.first_name:
            return chat.first_name
        return f"ID {user_id}"
    except:
        return f"ID {user_id}"

# ===== ФРАЗЫ =====
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

def get_achievements(streak):
    """Возвращает список достижений"""
    all_ach = [
        (1, "🌱 Первый шаг"),
        (7, "🔥 Неделя"),
        (10, "💪 10 дней"),
        (30, "🏅 Месяц"),
        (100, "💎 100 дней"),
        (365, "👑 Год"),
    ]
    unlocked = [name for days, name in all_ach if streak >= days]
    locked = [f"🔒 {name}" for days, name in all_ach if streak < days]
    return unlocked, locked

# ===== ПОДПИСКА =====
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
    kb = [
        [InlineKeyboardButton(text="🔥 Отметиться", callback_data="mark")],
        [InlineKeyboardButton(text="👥 Огонь с друзьями", callback_data="pair_menu")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats"),
         InlineKeyboardButton(text="🏆 Топ-10", callback_data="top")],
        [InlineKeyboardButton(text="🏅 Достижения", callback_data="achievements"),
         InlineKeyboardButton(text="📅 Календарь", callback_data="calendar")],
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
        [InlineKeyboardButton(text="👤 Юзеры", callback_data="admin_users")],
        [InlineKeyboardButton(text="👥 Пары", callback_data="admin_pairs_list")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")],
    ])

def back_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin")]
    ])

# ===== ГЛАВНОЕ МЕНЮ =====
def render_main(user_id):
    db = load_db()
    u = db["users"].get(str(user_id), {})
    streak = u.get("streak", 0)
    best = u.get("best_streak", 0)
    marked = u.get("last_mark_date") == today_str()

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
            db["users"][sid] = {
                "streak": 0, "best_streak": 0,
                "last_mark_date": None, "marks": []
            }
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
                    f"Ты в паре с @{message.from_user.username or message.from_user.first_name}!\n"
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
        u = db["users"].setdefault(uid, {
            "streak": 0, "best_streak": 0,
            "last_mark_date": None, "marks": []
        })
        today = today_str()

        if u.get("last_mark_date") == today:
            await call.answer("✅ Ты уже отметился сегодня!", show_alert=True)
            return

        u["streak"] = u.get("streak", 0) + 1
        is_new_record = u["streak"] > u.get("best_streak", 0)
        u["best_streak"] = max(u.get("best_streak", 0), u["streak"])
        u["last_mark_date"] = today

        # Календарь
        marks = u.get("marks", [])
        if today not in marks:
            marks.append(today)
        u["marks"] = marks[-30:]  # храним последние 30 дней

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

        # Достижения
        unlocked, locked = get_achievements(streak)
        ach_text = "\n".join(unlocked + locked) if (unlocked or locked) else "—"

        text = (
            "╔══════════════════════╗\n"
            "      📊 СТАТИСТИКА\n"
            "╚══════════════════════╝\n\n"
            f"🔥 Личный огонёк: {streak} дн.\n"
            f"🏆 Рекорд: {best} дн.\n"
            f"📊 {bar}\n\n"
            f"👥 Огней с друзьями: {pairs_count}\n"
            f"📅 Последняя отметка: {u.get('last_mark_date') or '—'}\n\n"
            f"🏅 Достижения:\n{ach_text}"
        )
        await call.message.edit_text(text, reply_markup=back_main_kb())
    except:
        pass
    await call.answer()

# ===== ДОСТИЖЕНИЯ =====
@dp.callback_query(F.data == "achievements")
async def achievements(call: CallbackQuery):
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
        streak = u.get("streak", 0)

        unlocked, locked = get_achievements(streak)
        text = (
            "╔══════════════════════╗\n"
            "      🏅 ДОСТИЖЕНИЯ\n"
            "╚══════════════════════╝\n\n"
            f"🔥 Твоя серия: {streak} дн.\n\n"
            "✅ Открыто:\n"
            + ("\n".join(unlocked) if unlocked else "— пока ничего")
            + "\n\n🔒 Закрыто:\n"
            + ("\n".join(locked) if locked else "— всё открыто!")
        )
        await call.message.edit_text(text, reply_markup=back_main_kb())
    except:
        pass
    await call.answer()

# ===== КАЛЕНДАРЬ =====
@dp.callback_query(F.data == "calendar")
async def calendar(call: CallbackQuery):
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
        marks = u.get("marks", [])
        week = last_7_days(marks)

        text = (
            "╔══════════════════════╗\n"
            "      📅 КАЛЕНДАРЬ\n"
            "╚══════════════════════╝\n\n"
            "Последние 7 дней:\n\n"
            f"{week}\n\n"
            "✅ — отметился\n"
            "⬜ — пропустил\n\n"
            f"🔥 Текущая серия: {u.get('streak', 0)} дн."
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
            name = await get_name(uid)
            lines.append(f"{prefix} {streak} дн. — {name}")

        text = (
            "╔══════════════════════╗\n"
            "        🏆 ТОП-10\n"
            "╚══════════════════════╝\n\n"
            + "\n".join(lines)
        )
        await call.message.edit_text(text, reply_markup=back_main_kb())
    except Exception as e:
        print("top error:", e)
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
            name = await get_name(partner_id)

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
                    text=f"{status} {name} — {pair.get('streak', 0)} дн. [ID {pid}]",
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
        name = await get_name(partner_id)

        my_mark = "✅" if (pair["user1_marked"] if pair["user1_id"] == uid else pair["user2_marked"]) else "⏳"
        his_mark = "✅" if (pair["user2_marked"] if pair["user1_id"] == uid else pair["user1_marked"]) else "⏳"

        text = (
            "╔══════════════════════╗\n"
            "      🔥 ВАШ ОГОНЬ\n"
            "╚══════════════════════╝\n\n"
            f"👤 Друг: {name}\n"
            f"🔥 Серия: {pair.get('streak', 0)} дн.\n"
            f"🆔 ID пары: {pid}\n\n"
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
        await call.message.edit_text("💔 Огонь разорван.", reply_markup=pair_menu())
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

# ===== АДМИН: ЮЗЕРЫ =====
@dp.callback_query(F.data == "admin_users")
async def admin_users(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    try:
        db = load_db()
        if not db["users"]:
            await call.message.edit_text("👤 Юзеров нет.", reply_markup=back_admin_kb())
            await call.answer()
            return

        buttons = []
        for uid, u in list(db["users"].items())[:30]:
            name = await get_name(uid)
            streak = u.get("streak", 0)
            buttons.append([
                InlineKeyboardButton(
                    text=f"🔥 {name} — {streak} дн.",
                    callback_data=f"admin_edit_user_{uid}"
                )
            ])
        buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin")])

        await call.message.edit_text(
            "👤 Выбери юзера для накрутки:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    except Exception as e:
        print("admin_users error:", e)
    await call.answer()

@dp.callback_query(F.data.startswith("admin_edit_user_"))
async def admin_edit_user(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    uid = call.data.replace("admin_edit_user_", "")
    name = await get_name(uid)
    try:
        await call.message.edit_text(
            f"👤 Юзер: {name}\n"
            f"🆔 ID: {uid}\n\n"
            f"Напиши число в чат — накручу на этот ID.\n"
            f"Пример: 100",
            reply_markup=back_admin_kb()
        )
        # Сохраняем контекст
        db = load_db()
        db["admin_context"] = {"type": "user", "id": uid}
        save_db(db)
    except:
        pass
    await call.answer()

# ===== АДМИН: ПАРЫ =====
@dp.callback_query(F.data == "admin_pairs_list")
async def admin_pairs_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    try:
        db = load_db()
        pairs = [(pid, p) for pid, p in db["pairs"].items() if p.get("user2_id")]

        if not pairs:
            await call.message.edit_text("👥 Пар нет.", reply_markup=back_admin_kb())
            await call.answer()
            return

        buttons = []
        for pid, p in pairs[:30]:
            n1 = await get_name(p["user1_id"])
            n2 = await get_name(p["user2_id"])
            streak = p.get("streak", 0)
            buttons.append([
                InlineKeyboardButton(
                    text=f"🔥 {n1} + {n2} — {streak} дн.",
                    callback_data=f"admin_edit_pair_{pid}"
                )
            ])
        buttons
