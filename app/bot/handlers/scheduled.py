from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext

from app.bot.states import EditingPublication
from app.config import settings
from app.core.channels import get_channel
from app.core.drafts import (
    get_draft, get_draft_channels, get_draft_attachments,
    get_draft_inline_buttons, delete_draft, set_draft_text,
)
from app.core.publisher import publish_to_chat
from app.core.scheduler import unschedule_publication, schedule_publication
from app.db.db import get_db


router = Router(name="scheduled")
TZ = ZoneInfo(settings.timezone)


def _fmt(s: str) -> str:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M")
    except Exception:
        return s


def _short_text(draft) -> str:
    t = draft["text"] or f"[{draft['post_type']}]"
    return t[:80] + ("…" if len(t) > 80 else "")


def _menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Предстоящие", callback_data="sch:up")],
        [InlineKeyboardButton(text="✅ Опубликованные", callback_data="sch:pub")],
        [InlineKeyboardButton(text="📝 Черновики", callback_data="sch:dr")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:main")],
    ])


@router.callback_query(F.data == "nav:scheduled")
async def menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text("🕒 <b>Отложенные публикации</b>\n\nВыбери раздел:", reply_markup=_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "sch:menu")
async def back_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text("🕒 <b>Отложенные публикации</b>", reply_markup=_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "sch:up")
async def upcoming(callback: CallbackQuery) -> None:
    db = get_db()
    async with db.execute(
        """SELECT p.*, d.post_type, d.text FROM publications p
           JOIN drafts d ON d.id = p.draft_id
           WHERE p.status IN ('scheduled','sending','partial','failed','missed')
           ORDER BY p.scheduled_at"""
    ) as cur:
        rows = await cur.fetchall()

    if not rows:
        await callback.message.edit_text(
            "📅 Предстоящих публикаций нет.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ Назад", callback_data="sch:menu"),
            ]]),
        )
        await callback.answer()
        return

    buttons = []
    for r in rows:
        state = {"scheduled":"🕒","sending":"⏳","partial":"⚠️","failed":"❌","missed":"⚠️"}.get(r["status"], "•")
        if r["paused"]:
            state = "⏸"
        label = f"{state} {_fmt(r['scheduled_at'])} — {_short_text(r)}"
        buttons.append([InlineKeyboardButton(text=label[:60], callback_data=f"sch:view:{r['id']}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="sch:menu")])
    await callback.message.edit_text(
        f"📅 <b>Предстоящие</b> ({len(rows)}):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sch:view:"))
async def view_publication(callback: CallbackQuery) -> None:
    pub_id = int(callback.data.split(":")[2])
    db = get_db()
    async with db.execute(
        """SELECT p.*, d.post_type, d.text FROM publications p
           JOIN drafts d ON d.id = p.draft_id WHERE p.id = ?""",
        (pub_id,),
    ) as cur:
        pub = await cur.fetchone()
    if not pub:
        await callback.answer("Не найдено.", show_alert=True)
        return

    chat_ids = await get_draft_channels(pub["draft_id"])
    titles = []
    for cid in chat_ids:
        ch = await get_channel(cid)
        titles.append(ch["title"] if ch else str(cid))

    state = "paused" if pub["paused"] else pub["status"]
    text = (
        f"🕒 <b>Публикация #{pub['id']}</b>\n\n"
        f"<b>Статус:</b> {state}\n"
        f"<b>Время:</b> {_fmt(pub['scheduled_at'])}\n"
        f"<b>Каналы:</b> {', '.join(titles)}\n"
        f"<b>Тип:</b> {pub['post_type']}\n\n"
        f"<b>Содержимое:</b> {(pub['text'] or '')[:300]}"
    )

    buttons = []
    if pub["status"] in ("scheduled", "paused", "missed"):
        buttons.append([InlineKeyboardButton(text="🚀 Опубликовать сейчас", callback_data=f"sch:pubnow:{pub_id}")])
    buttons.append([InlineKeyboardButton(text="✏️ Редактировать материал", callback_data=f"sch:edit:{pub_id}")])
    if pub["status"] in ("scheduled", "paused", "missed"):
        buttons.append([InlineKeyboardButton(text="🕒 Перенести время", callback_data=f"sch:resched:{pub_id}")])
        buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data=f"sch:cancel:{pub_id}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="sch:up")])

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("sch:pubnow:"))
async def publish_now(callback: CallbackQuery, bot) -> None:
    pub_id = int(callback.data.split(":")[2])
    db = get_db()
    async with db.execute("SELECT * FROM publications WHERE id=?", (pub_id,)) as cur:
        pub = await cur.fetchone()
    if not pub:
        await callback.answer("Не найдено.", show_alert=True)
        return

    draft = await get_draft(pub["draft_id"])
    attachments = await get_draft_attachments(pub["draft_id"])
    buttons_data = await get_draft_inline_buttons(pub["draft_id"])
    chat_ids = await get_draft_channels(pub["draft_id"])

    await db.execute("UPDATE publications SET status='sending', paused=0 WHERE id=?", (pub_id,))
    await db.commit()
    unschedule_publication(pub_id)

    ok_count = 0
    text = "📢 <b>Результаты</b>\n\n"
    for cid in chat_ids:
        ok, mid, err = await publish_to_chat(bot, cid, draft, attachments, buttons_data)
        ch = await get_channel(cid)
        title = ch["title"] if ch else str(cid)
        if ok:
            ok_count += 1
            text += f"✅ {title}\n"
            await db.execute(
                """UPDATE publication_targets
                   SET status='sent', message_id=?, sent_at=datetime('now'),
                       attempt_count=attempt_count+1
                   WHERE publication_id=? AND chat_id=?""",
                (mid, pub_id, cid),
            )
        else:
            text += f"❌ {title}: <code>{err}</code>\n"
            await db.execute(
                """UPDATE publication_targets
                   SET status='failed', last_error=?, attempt_count=attempt_count+1
                   WHERE publication_id=? AND chat_id=?""",
                (err, pub_id, cid),
            )
    await db.commit()

    final = "sent" if ok_count == len(chat_ids) else ("partial" if ok_count > 0 else "failed")
    await db.execute("UPDATE publications SET status=? WHERE id=?", (final, pub_id))
    await db.commit()

    text += f"\nУспешно: {ok_count}/{len(chat_ids)}"
    await callback.message.edit_text(text)
    await callback.answer()


@router.callback_query(F.data.startswith("sch:edit:"))
async def edit_material(callback: CallbackQuery, bot) -> None:
    pub_id = int(callback.data.split(":")[2])
    db = get_db()
    async with db.execute("SELECT draft_id FROM publications WHERE id=?", (pub_id,)) as cur:
        pub = await cur.fetchone()
    if not pub:
        await callback.answer("Не найдено.", show_alert=True)
        return

    draft = await get_draft(pub["draft_id"])
    attachments = await get_draft_attachments(pub["draft_id"])
    buttons_data = await get_draft_inline_buttons(pub["draft_id"])

    await db.execute("UPDATE publications SET paused=1 WHERE id=?", (pub_id,))
    await db.commit()
    unschedule_publication(pub_id)

    ok, _, err = await publish_to_chat(
        bot, settings.owner_telegram_id, draft, attachments, buttons_data
    )
    if not ok:
        await callback.answer(f"Ошибка предпросмотра: {err}", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Опубликовать сейчас", callback_data=f"sch:pubnow:{pub_id}")],
        [InlineKeyboardButton(text="✏️ Заменить текст", callback_data=f"sch:retext:{pub_id}")],
        [InlineKeyboardButton(text="🕒 Перенести время", callback_data=f"sch:resched:{pub_id}")],
        [InlineKeyboardButton(text="❌ Отменить публикацию", callback_data=f"sch:cancel:{pub_id}")],
    ])
    await callback.message.edit_text(
        f"✏️ <b>Публикация #{pub_id} на паузе.</b>\n"
        f"Предпросмотр отправлен выше. Выбери действие:",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sch:retext:"))
async def retext_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    pub_id = int(callback.data.split(":")[2])
    await state.set_state(EditingPublication.waiting_text)
    await state.update_data(edit_pub_id=pub_id)
    await callback.message.edit_text(f"✏️ Отправь новый текст для публикации #{pub_id}.")
    await callback.answer()


@router.message(EditingPublication.waiting_text, F.text)
async def retext_save(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    pub_id = data["edit_pub_id"]
    db = get_db()
    async with db.execute("SELECT draft_id FROM publications WHERE id=?", (pub_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        await state.clear()
        await message.answer("Публикация не найдена.")
        return
    await set_draft_text(row["draft_id"], message.html_text)
    await state.clear()
    await message.answer(
        f"✅ Текст публикации #{pub_id} обновлён.\n"
        f"Открой «🕒 Отложенные → Предстоящие» и выбери действие."
    )


@router.callback_query(F.data.startswith("sch:resched:"))
async def resched_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    pub_id = int(callback.data.split(":")[2])
    await state.set_state(EditingPublication.waiting_reschedule)
    await state.update_data(edit_pub_id=pub_id)
    await callback.message.edit_text(
        f"🕒 Отправь новую дату для публикации #{pub_id} в формате <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>."
    )
    await callback.answer()


@router.message(EditingPublication.waiting_reschedule, F.text)
async def resched_save(message: Message, state: FSMContext) -> None:
    try:
        dt = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
    except ValueError:
        await message.answer("Формат: <code>25.12.2026 18:30</code>")
        return
    if dt <= datetime.now():
        await message.answer("Дата должна быть в будущем.")
        return
    data = await state.get_data()
    pub_id = data["edit_pub_id"]
    db = get_db()
    await db.execute(
        "UPDATE publications SET scheduled_at=?, status='scheduled', paused=0 WHERE id=?",
        (dt.strftime("%Y-%m-%d %H:%M:%S"), pub_id),
    )
    await db.commit()
    await state.clear()
    schedule_publication(pub_id, dt)
    await message.answer(f"✅ Публикация #{pub_id} запланирована на {dt.strftime('%d.%m.%Y %H:%M')}.")


@router.callback_query(F.data.startswith("sch:cancel:"))
async def cancel_pub(callback: CallbackQuery) -> None:
    pub_id = int(callback.data.split(":")[2])
    db = get_db()
    await db.execute("UPDATE publications SET status='cancelled' WHERE id=?", (pub_id,))
    await db.commit()
    unschedule_publication(pub_id)
    await callback.message.edit_text(f"❌ Публикация #{pub_id} отменена.")
    await callback.answer()


@router.callback_query(F.data == "sch:pub")
async def published(callback: CallbackQuery) -> None:
    db = get_db()
    async with db.execute(
        """SELECT p.*, d.post_type, d.text FROM publications p
           JOIN drafts d ON d.id = p.draft_id
           WHERE p.status IN ('sent','partial','failed','cancelled')
           ORDER BY p.scheduled_at DESC LIMIT 30"""
    ) as cur:
        rows = await cur.fetchall()

    if not rows:
        await callback.message.edit_text(
            "✅ Опубликованных пока нет.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ Назад", callback_data="sch:menu"),
            ]]),
        )
        await callback.answer()
        return

    buttons = []
    for r in rows:
        st = {"sent":"✅","partial":"⚠️","failed":"❌","cancelled":"🚫"}.get(r["status"], "•")
        label = f"{st} {_fmt(r['scheduled_at'])} — {_short_text(r)}"
        buttons.append([InlineKeyboardButton(text=label[:60], callback_data=f"sch:pview:{r['id']}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="sch:menu")])
    await callback.message.edit_text(
        f"✅ <b>Опубликованные</b> ({len(rows)}):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sch:pview:"))
async def pview(callback: CallbackQuery) -> None:
    pub_id = int(callback.data.split(":")[2])
    db = get_db()
    async with db.execute(
        """SELECT p.*, d.post_type, d.text FROM publications p
           JOIN drafts d ON d.id = p.draft_id WHERE p.id=?""",
        (pub_id,),
    ) as cur:
        pub = await cur.fetchone()
    if not pub:
        await callback.answer("Не найдено.", show_alert=True)
        return

    async with db.execute(
        "SELECT * FROM publication_targets WHERE publication_id=?", (pub_id,)
    ) as cur:
        targets = await cur.fetchall()

    lines = [f"🕒 <b>Публикация #{pub_id}</b>", f"<b>Время:</b> {_fmt(pub['scheduled_at'])}", ""]
    for t in targets:
        ch = await get_channel(t["chat_id"])
        title = ch["title"] if ch else str(t["chat_id"])
        st = {"sent":"✅","failed":"❌","pending":"⏳","skipped":"⏭"}.get(t["status"], "•")
        if t["status"] == "sent" and t["message_id"] and ch and ch["username"]:
            link = f"https://t.me/{ch['username']}/{t['message_id']}"
            lines.append(f"{st} {title} — {link}")
        elif t["status"] == "failed":
            lines.append(f"{st} {title} — <code>{(t['last_error'] or '')[:100]}</code>")
        else:
            lines.append(f"{st} {title}")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад", callback_data="sch:pub"),
        ]]),
    )
    await callback.answer()


@router.callback_query(F.data == "sch:dr")
async def drafts_list(callback: CallbackQuery) -> None:
    db = get_db()
    async with db.execute(
        """SELECT d.* FROM drafts d
           WHERE d.id NOT IN (SELECT draft_id FROM publications)
           ORDER BY d.updated_at DESC LIMIT 30"""
    ) as cur:
        rows = await cur.fetchall()

    if not rows:
        await callback.message.edit_text(
            "📝 Черновиков нет.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ Назад", callback_data="sch:menu"),
            ]]),
        )
        await callback.answer()
        return

    buttons = []
    for r in rows:
        label = f"📝 {_short_text(r)}"
        buttons.append([InlineKeyboardButton(text=label[:60], callback_data=f"sch:dview:{r['id']}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="sch:menu")])
    await callback.message.edit_text(
        f"📝 <b>Черновики</b> ({len(rows)}):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sch:dview:"))
async def draft_view(callback: CallbackQuery, bot) -> None:
    draft_id = int(callback.data.split(":")[2])
    draft = await get_draft(draft_id)
    if not draft:
        await callback.answer("Не найдено.", show_alert=True)
        return

    attachments = await get_draft_attachments(draft_id)
    buttons_data = await get_draft_inline_buttons(draft_id)
    ok, _, err = await publish_to_chat(
        bot, settings.owner_telegram_id, draft, attachments, buttons_data
    )

    text = f"📝 <b>Черновик #{draft_id}</b>\n<b>Тип:</b> {draft['post_type']}\n"
    if not ok:
        text += f"⚠️ Предпросмотр не удался: <code>{err}</code>"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"sch:ddel:{draft_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="sch:dr")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("sch:ddel:"))
async def draft_del(callback: CallbackQuery) -> None:
    draft_id = int(callback.data.split(":")[2])
    await delete_draft(draft_id)
    await callback.message.edit_text(
        "🗑 Черновик удалён.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад", callback_data="sch:dr"),
        ]]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pub:fix:"))
async def prealert_fix(callback: CallbackQuery, bot) -> None:
    pub_id = int(callback.data.split(":")[2])
    db = get_db()
    await db.execute("UPDATE publications SET paused=1 WHERE id=?", (pub_id,))
    await db.commit()
    unschedule_publication(pub_id)

    async with db.execute("SELECT draft_id FROM publications WHERE id=?", (pub_id,)) as cur:
        pub = await cur.fetchone()
    if not pub:
        await callback.answer("Не найдено.", show_alert=True)
        return

    draft = await get_draft(pub["draft_id"])
    attachments = await get_draft_attachments(pub["draft_id"])
    buttons_data = await get_draft_inline_buttons(pub["draft_id"])
    await publish_to_chat(bot, settings.owner_telegram_id, draft, attachments, buttons_data)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Опубликовать сейчас", callback_data=f"sch:pubnow:{pub_id}")],
        [InlineKeyboardButton(text="✏️ Заменить текст", callback_data=f"sch:retext:{pub_id}")],
        [InlineKeyboardButton(text="🕒 Перенести", callback_data=f"sch:resched:{pub_id}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"sch:cancel:{pub_id}")],
    ])
    await callback.message.edit_text(
        f"⏸ Публикация #{pub_id} на паузе. Предпросмотр выше.",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pub:cancel:"))
async def prealert_cancel(callback: CallbackQuery) -> None:
    pub_id = int(callback.data.split(":")[2])
    db = get_db()
    await db.execute("UPDATE publications SET status='cancelled' WHERE id=?", (pub_id,))
    await db.commit()
    unschedule_publication(pub_id)
    await callback.message.edit_text(f"❌ Публикация #{pub_id} отменена.")
    await callback.answer()
