from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.core.channels import list_managed_channels, get_channel
from app.db.db import get_db


router = Router(name="stats")


def _menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 По каналам", callback_data="stats:ch")],
        [InlineKeyboardButton(text="📜 История", callback_data="stats:hist")],
        [InlineKeyboardButton(text="❌ Ошибки", callback_data="stats:err")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:main")],
    ])


@router.callback_query(F.data == "nav:stats")
async def menu(callback: CallbackQuery) -> None:
    db = get_db()

    async def scalar(q: str, args: tuple = ()):
        async with db.execute(q, args) as cur:
            row = await cur.fetchone()
        return row["v"] if row else 0

    total = await scalar("SELECT COUNT(*) AS v FROM publications")
    sent = await scalar("SELECT COUNT(*) AS v FROM publications WHERE status='sent'")
    sched = await scalar("SELECT COUNT(*) AS v FROM publications WHERE status='scheduled' AND paused=0")
    cancelled = await scalar("SELECT COUNT(*) AS v FROM publications WHERE status='cancelled'")
    failed = await scalar("SELECT COUNT(*) AS v FROM publications WHERE status='failed'")
    partial = await scalar("SELECT COUNT(*) AS v FROM publications WHERE status='partial'")
    missed = await scalar("SELECT COUNT(*) AS v FROM publications WHERE status='missed'")

    text = (
        f"📊 <b>Общая статистика</b>\n\n"
        f"<b>Всего:</b> {total}\n"
        f"✅ Отправлено: {sent}\n"
        f"🕒 Запланировано: {sched}\n"
        f"⚠️ Частично: {partial}\n"
        f"❌ Ошибки: {failed}\n"
        f"⏭ Пропущено: {missed}\n"
        f"🚫 Отменено: {cancelled}"
    )
    await callback.message.edit_text(text, reply_markup=_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "stats:back")
async def back(callback: CallbackQuery) -> None:
    await callback.message.edit_text("📊 <b>Статистика</b>", reply_markup=_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "stats:ch")
async def by_channel(callback: CallbackQuery) -> None:
    channels = await list_managed_channels()
    if not channels:
        await callback.answer("Каналов нет.", show_alert=True)
        return

    db = get_db()
    lines = ["📢 <b>Публикации по каналам</b>\n"]
    for ch in channels:
        async with db.execute(
            "SELECT COUNT(*) AS v FROM publication_targets WHERE chat_id=? AND status='sent'",
            (ch["chat_id"],),
        ) as cur:
            sent = (await cur.fetchone())["v"]
        async with db.execute(
            "SELECT COUNT(*) AS v FROM publication_targets WHERE chat_id=? AND status='failed'",
            (ch["chat_id"],),
        ) as cur:
            failed = (await cur.fetchone())["v"]
        lines.append(f"• <b>{ch['title']}</b> — ✅ {sent} / ❌ {failed}")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад", callback_data="stats:back"),
        ]]),
    )
    await callback.answer()


@router.callback_query(F.data == "stats:hist")
async def history(callback: CallbackQuery) -> None:
    db = get_db()
    async with db.execute(
        """SELECT p.id, p.scheduled_at, p.status, d.text, d.post_type
           FROM publications p JOIN drafts d ON d.id=p.draft_id
           ORDER BY p.scheduled_at DESC LIMIT 20"""
    ) as cur:
        rows = await cur.fetchall()

    if not rows:
        await callback.answer("Истории нет.", show_alert=True)
        return

    icons = {"sent":"✅","failed":"❌","partial":"⚠️","cancelled":"🚫","scheduled":"🕒","missed":"⏭","sending":"⏳"}
    lines = ["📜 <b>История (20 последних)</b>\n"]
    for r in rows:
        t = (r["text"] or f"[{r['post_type']}]")[:40]
        lines.append(f"{icons.get(r['status'],'•')} {r['scheduled_at']} — {t}")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад", callback_data="stats:back"),
        ]]),
    )
    await callback.answer()


@router.callback_query(F.data == "stats:err")
async def errors(callback: CallbackQuery) -> None:
    db = get_db()
    async with db.execute(
        """SELECT pt.*, p.scheduled_at FROM publication_targets pt
           JOIN publications p ON p.id=pt.publication_id
           WHERE pt.status='failed' ORDER BY p.scheduled_at DESC LIMIT 20"""
    ) as cur:
        rows = await cur.fetchall()

    if not rows:
        await callback.answer("Ошибок нет.", show_alert=True)
        return

    lines = ["❌ <b>Последние ошибки</b>\n"]
    for r in rows:
        ch = await get_channel(r["chat_id"])
        title = ch["title"] if ch else str(r["chat_id"])
        err = (r["last_error"] or "")[:80]
        lines.append(f"• {r['scheduled_at']} — {title}: <code>{err}</code>")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад", callback_data="stats:back"),
        ]]),
    )
    await callback.answer()
