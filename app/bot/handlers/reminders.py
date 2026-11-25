import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext

from app.bot.states import NewReminder
from app.config import settings
from app.core.scheduler import schedule_reminder, unschedule_reminder
from app.db.db import get_db


router = Router(name="reminders")
TZ = ZoneInfo(settings.timezone)


def _fmt(s: str) -> str:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M")
    except Exception:
        return s


def _menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать напоминание", callback_data="rem:new")],
        [InlineKeyboardButton(text="🔔 Активные", callback_data="rem:list:active")],
        [InlineKeyboardButton(text="🔁 Повторяющиеся", callback_data="rem:list:repeat")],
        [InlineKeyboardButton(text="✅ Выполненные", callback_data="rem:list:done")],
        [InlineKeyboardButton(text="📜 История", callback_data="rem:list:history")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:main")],
    ])


@router.callback_query(F.data == "nav:reminders")
async def menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text("🔔 <b>Мои напоминания</b>", reply_markup=_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "rem:back")
async def back(callback: CallbackQuery) -> None:
    await callback.message.edit_text("🔔 <b>Мои напоминания</b>", reply_markup=_menu_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("rem:list:"))
async def list_reminders(callback: CallbackQuery) -> None:
    kind = callback.data.split(":")[2]
    db = get_db()

    if kind == "active":
        q = "SELECT * FROM reminders WHERE status='active' AND repeat_type='none' ORDER BY fire_at"
    elif kind == "repeat":
        q = "SELECT * FROM reminders WHERE status='active' AND repeat_type!='none' ORDER BY fire_at"
    elif kind == "done":
        q = "SELECT * FROM reminders WHERE status='done' ORDER BY fire_at DESC LIMIT 30"
    else:
        q = "SELECT * FROM reminders ORDER BY created_at DESC LIMIT 30"

    async with db.execute(q) as cur:
        rows = await cur.fetchall()

    if not rows:
        await callback.message.edit_text(
            "Пусто.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ Назад", callback_data="rem:back"),
            ]]),
        )
        await callback.answer()
        return

    buttons = []
    for r in rows:
        st = {"active":"🔔","done":"✅","cancelled":"🚫"}.get(r["status"], "•")
        label = f"{st} {_fmt(r['fire_at'])} — {r['text'][:40]}"
        buttons.append([InlineKeyboardButton(text=label[:60], callback_data=f"rem:view:{r['id']}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="rem:back")])
    await callback.message.edit_text(
        f"<b>{kind}</b> ({len(rows)}):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rem:view:"))
async def view(callback: CallbackQuery) -> None:
    rem_id = int(callback.data.split(":")[2])
    db = get_db()
    async with db.execute("SELECT * FROM reminders WHERE id=?", (rem_id,)) as cur:
        r = await cur.fetchone()
    if not r:
        await callback.answer("Не найдено.", show_alert=True)
        return

    text = (
        f"🔔 <b>Напоминание #{r['id']}</b>\n\n"
        f"{r['text']}\n\n"
        f"<b>Время:</b> {_fmt(r['fire_at'])}\n"
        f"<b>Повтор:</b> {r['repeat_type']}\n"
        f"<b>Статус:</b> {r['status']}"
    )
    buttons = []
    if r["status"] == "active":
        buttons.append([InlineKeyboardButton(text="✅ Выполнено", callback_data=f"rem:done:{rem_id}")])
        buttons.append([InlineKeyboardButton(text="🗑 Удалить", callback_data=f"rem:del:{rem_id}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="rem:back")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("rem:done:"))
async def mark_done(callback: CallbackQuery) -> None:
    rem_id = int(callback.data.split(":")[2])
    db = get_db()
    await db.execute("UPDATE reminders SET status='done' WHERE id=?", (rem_id,))
    await db.commit()
    unschedule_reminder(rem_id)
    await callback.message.edit_text(
        "✅ Отмечено выполненным.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад", callback_data="rem:back"),
        ]]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rem:del:"))
async def delete(callback: CallbackQuery) -> None:
    rem_id = int(callback.data.split(":")[2])
    db = get_db()
    await db.execute("DELETE FROM reminders WHERE id=?", (rem_id,))
    await db.commit()
    unschedule_reminder(rem_id)
    await callback.message.edit_text(
        "🗑 Удалено.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад", callback_data="rem:back"),
        ]]),
    )
    await callback.answer()


@router.callback_query(F.data == "rem:new")
async def new_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(NewReminder.choosing_date)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Сегодня", callback_data="rem:d:0")],
        [InlineKeyboardButton(text="📅 Завтра", callback_data="rem:d:1")],
        [InlineKeyboardButton(text="📅 Послезавтра", callback_data="rem:d:2")],
        [InlineKeyboardButton(text="🗓 Ввести дату вручную", callback_data="rem:d:manual")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="rem:cancel")],
    ])
    await callback.message.edit_text(
        "🔔 <b>Новое напоминание. Шаг 1.</b>\n\nВыбери дату:",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(NewReminder.choosing_date, F.data.startswith("rem:d:"))
async def choose_date(callback: CallbackQuery, state: FSMContext) -> None:
    part = callback.data.split(":")[2]
    if part == "manual":
        await state.set_state(NewReminder.custom_date)
        await callback.message.edit_text("Введи дату в формате <code>ДД.ММ.ГГГГ</code>:")
        await callback.answer()
        return
    days = int(part)
    d = (datetime.now(TZ) + timedelta(days=days)).strftime("%Y-%m-%d")
    await state.update_data(date=d)
    await _show_time_choices(callback, state)


async def _time_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="06:00", callback_data="rem:t:06:00"),
         InlineKeyboardButton(text="09:00", callback_data="rem:t:09:00"),
         InlineKeyboardButton(text="12:00", callback_data="rem:t:12:00")],
        [InlineKeyboardButton(text="15:00", callback_data="rem:t:15:00"),
         InlineKeyboardButton(text="18:00", callback_data="rem:t:18:00"),
         InlineKeyboardButton(text="21:00", callback_data="rem:t:21:00")],
        [InlineKeyboardButton(text="⏰ Ввести вручную", callback_data="rem:t:manual")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="rem:cancel")],
    ])


async def _show_time_choices(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewReminder.choosing_time)
    await callback.message.edit_text(
        "🔔 <b>Шаг 2.</b> Выбери время:",
        reply_markup=await _time_kb(),
    )
    await callback.answer()


@router.message(NewReminder.custom_date, F.text)
async def custom_date(message: Message, state: FSMContext) -> None:
    try:
        d = datetime.strptime(message.text.strip(), "%d.%m.%Y").strftime("%Y-%m-%d")
    except ValueError:
        await message.answer("Не понял. Пример: <code>25.12.2026</code>")
        return
    await state.update_data(date=d)
    await state.set_state(NewReminder.choosing_time)
    await message.answer("🔔 <b>Шаг 2.</b> Выбери время:", reply_markup=await _time_kb())


@router.callback_query(NewReminder.choosing_time, F.data.startswith("rem:t:"))
async def choose_time(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    if parts[2] == "manual":
        await state.set_state(NewReminder.custom_time)
        await callback.message.edit_text("Введи время в формате <code>ЧЧ:ММ</code>:")
        await callback.answer()
        return
    t = f"{parts[2]}:{parts[3]}"
    await state.update_data(time=t)
    await state.set_state(NewReminder.entering_text)
    await callback.message.edit_text("🔔 <b>Шаг 3.</b> Отправь текст напоминания:")
    await callback.answer()


@router.message(NewReminder.custom_time, F.text)
async def custom_time(message: Message, state: FSMContext) -> None:
    try:
        t = datetime.strptime(message.text.strip(), "%H:%M").strftime("%H:%M")
    except ValueError:
        await message.answer("Не понял. Пример: <code>18:30</code>")
        return
    await state.update_data(time=t)
    await state.set_state(NewReminder.entering_text)
    await message.answer("🔔 <b>Шаг 3.</b> Отправь текст напоминания:")


@router.message(NewReminder.entering_text, F.text)
async def enter_text(message: Message, state: FSMContext) -> None:
    await state.update_data(text=message.text.strip())
    await state.set_state(NewReminder.choosing_repeat)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Один раз", callback_data="rem:r:none")],
        [InlineKeyboardButton(text="Каждый день", callback_data="rem:r:daily")],
        [InlineKeyboardButton(text="Каждую неделю", callback_data="rem:r:weekly")],
        [InlineKeyboardButton(text="Каждый месяц", callback_data="rem:r:monthly")],
        [InlineKeyboardButton(text="Свой интервал (часы)", callback_data="rem:r:interval")],
        [InlineKeyboardButton(text="Выбранные дни недели", callback_data="rem:r:weekdays")],
    ])
    await message.answer("🔔 <b>Шаг 4.</b> Повторение:", reply_markup=kb)


@router.callback_query(NewReminder.choosing_repeat, F.data.startswith("rem:r:"))
async def choose_repeat(callback: CallbackQuery, state: FSMContext) -> None:
    kind = callback.data.split(":")[2]
    await state.update_data(repeat_type=kind)

    if kind == "interval":
        await state.set_state(NewReminder.custom_interval)
        await callback.message.edit_text("Сколько часов между повторами? Введи число:")
        await callback.answer()
        return
    if kind == "weekdays":
        await state.set_state(NewReminder.choosing_weekdays)
        await state.update_data(days=[])
        await _show_weekdays(callback, state, [])
        return
    await _confirm(callback, state, repeat_type=kind)


async def _show_weekdays(callback: CallbackQuery, state: FSMContext, selected: list[int]) -> None:
    names = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]
    rows, row = [], []
    for i, name in enumerate(names, 1):
        mark = "✅" if i in selected else "⬜"
        row.append(InlineKeyboardButton(text=f"{mark}{name}", callback_data=f"rem:wd:{i}"))
        if len(row) == 4:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="💾 Сохранить", callback_data="rem:wd:done")])
    await callback.message.edit_text(
        "Выбери дни недели:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(NewReminder.choosing_weekdays, F.data.startswith("rem:wd:"))
async def toggle_weekday(callback: CallbackQuery, state: FSMContext) -> None:
    part = callback.data.split(":")[2]
    if part == "done":
        data = await state.get_data()
        days = data.get("days", [])
        if not days:
            await callback.answer("Выбери хотя бы один день.", show_alert=True)
            return
        await _confirm(callback, state, repeat_type="weekdays", days=days)
        return
    d = int(part)
    data = await state.get_data()
    days = list(data.get("days", []))
    if d in days:
        days.remove(d)
    else:
        days.append(d)
    await state.update_data(days=days)
    await _show_weekdays(callback, state, days)


@router.message(NewReminder.custom_interval, F.text)
async def custom_interval(message: Message, state: FSMContext) -> None:
    try:
        hours = int(message.text.strip())
        if hours < 1:
            raise ValueError
    except ValueError:
        await message.answer("Введи целое число часов ≥ 1.")
        return
    await state.update_data(seconds=hours * 3600)
    data = await state.get_data()
    await _show_confirm_msg(message, state, data, repeat_type="interval", seconds=hours * 3600)


async def _confirm(callback: CallbackQuery, state: FSMContext, repeat_type: str, **kwargs):
    data = await state.get_data()
    await _show_confirm_msg(callback.message, state, data, repeat_type=repeat_type, edit=True, **kwargs)
    await callback.answer()


async def _show_confirm_msg(
    message: Message, state: FSMContext, data: dict, repeat_type: str, edit=False, **kwargs
):
    repeat_json = {}
    if repeat_type == "interval":
        repeat_json["seconds"] = kwargs.get("seconds", 3600)
    if repeat_type == "weekdays":
        repeat_json["days"] = kwargs.get("days", [])

    await state.update_data(
        repeat_type=repeat_type,
        repeat_json=json.dumps(repeat_json) if repeat_json else None,
    )

    text = (
        f"🔔 <b>Проверь напоминание</b>\n\n"
        f"<b>Текст:</b> {data['text']}\n"
        f"<b>Дата:</b> {data['date']}\n"
        f"<b>Время:</b> {data['time']}\n"
        f"<b>Повтор:</b> {repeat_type}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Создать", callback_data="rem:create")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="rem:cancel")],
    ])
    await state.set_state(NewReminder.confirm)
    if edit:
        await message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "rem:cancel")
async def cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Отменено.")
    await callback.answer()


@router.callback_query(NewReminder.confirm, F.data == "rem:create")
async def create(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    dt = datetime.strptime(f"{data['date']} {data['time']}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    if dt <= datetime.now(TZ):
        await callback.answer("Дата уже в прошлом.", show_alert=True)
        return

    db = get_db()
    cur = await db.execute(
        """INSERT INTO reminders (text, fire_at, repeat_type, repeat_json, status)
           VALUES (?, ?, ?, ?, 'active')""",
        (data["text"], dt.strftime("%Y-%m-%d %H:%M:%S"), data["repeat_type"], data.get("repeat_json")),
    )
    rem_id = cur.lastrowid
    await db.commit()

    schedule_reminder(rem_id, dt)
    await state.clear()
    await callback.message.edit_text(
        f"✅ Напоминание создано на <b>{dt.strftime('%d.%m.%Y %H:%M')}</b>."
    )
    await callback.answer()
