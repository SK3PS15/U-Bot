import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from app.config import settings
from app.core.channels import get_channel
from app.core.drafts import (
    get_draft, get_draft_attachments, get_draft_inline_buttons, get_draft_channels,
)
from app.core.publisher import publish_to_chat
from app.core.reminders import compute_next
from app.db.db import get_db


log = logging.getLogger("ubot.scheduler")
TZ = ZoneInfo(settings.timezone)

_scheduler: AsyncIOScheduler | None = None
_bot: Bot | None = None


def init_scheduler(bot: Bot) -> AsyncIOScheduler:
    global _scheduler, _bot
    _bot = bot
    _scheduler = AsyncIOScheduler(timezone=TZ)
    _scheduler.start()
    return _scheduler


def shutdown_scheduler() -> None:
    if _scheduler:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass


async def _notify(text: str, kb: InlineKeyboardMarkup | None = None) -> None:
    try:
        await _bot.send_message(settings.owner_telegram_id, text, reply_markup=kb)
    except Exception as e:
        log.warning("Не удалось отправить уведомление: %s", e)


def schedule_publication(pub_id: int, run_at: datetime) -> None:
    _scheduler.add_job(
        _run_publication,
        trigger=DateTrigger(run_date=run_at, timezone=TZ),
        id=f"pub:{pub_id}",
        args=[pub_id],
        misfire_grace_time=300,
        replace_existing=True,
    )
    log.info("Публикация %s запланирована на %s", pub_id, run_at)


def unschedule_publication(pub_id: int) -> None:
    try:
        _scheduler.remove_job(f"pub:{pub_id}")
    except Exception:
        pass


async def _run_publication(pub_id: int) -> None:
    db = get_db()
    async with db.execute("SELECT * FROM publications WHERE id = ?", (pub_id,)) as cur:
        pub = await cur.fetchone()
    if not pub or pub["status"] not in ("scheduled", "paused") or pub["paused"]:
        return

    draft = await get_draft(pub["draft_id"])
    attachments = await get_draft_attachments(pub["draft_id"])
    buttons = await get_draft_inline_buttons(pub["draft_id"])
    chat_ids = await get_draft_channels(pub["draft_id"])

    await db.execute("UPDATE publications SET status='sending' WHERE id=?", (pub_id,))
    await db.commit()

    any_ok, all_ok = False, True
    for cid in chat_ids:
        async with db.execute(
            "SELECT * FROM publication_targets WHERE publication_id=? AND chat_id=?",
            (pub_id, cid),
        ) as cur:
            target = await cur.fetchone()

        if target and target["status"] == "sent":
            any_ok = True
            continue

        ok, mid, err = await publish_to_chat(_bot, cid, draft, attachments, buttons)
        ch = await get_channel(cid)
        title = ch["title"] if ch else str(cid)

        if ok:
            await db.execute(
                """UPDATE publication_targets
                   SET status='sent', message_id=?, sent_at=datetime('now'),
                       last_error=NULL, attempt_count=attempt_count+1
                   WHERE publication_id=? AND chat_id=?""",
                (mid, pub_id, cid),
            )
            any_ok = True
        else:
            attempts = (target["attempt_count"] if target else 0) + 1
            await db.execute(
                """UPDATE publication_targets
                   SET status='failed', last_error=?, attempt_count=?
                   WHERE publication_id=? AND chat_id=?""",
                (err, attempts, pub_id, cid),
            )
            all_ok = False
            if attempts < 5:
                delay = 60 * (2 ** (attempts - 1))
                _scheduler.add_job(
                    _retry_target,
                    trigger=DateTrigger(
                        run_date=datetime.now(TZ) + timedelta(seconds=delay),
                        timezone=TZ,
                    ),
                    args=[pub_id, cid],
                    id=f"retry:{pub_id}:{cid}",
                    replace_existing=True,
                )
            else:
                await _notify(f"❌ Не удалось отправить в «{title}»:\n<code>{err}</code>")
        await db.commit()

    if all_ok and any_ok:
        await db.execute("UPDATE publications SET status='sent' WHERE id=?", (pub_id,))
    elif any_ok:
        await db.execute("UPDATE publications SET status='partial' WHERE id=?", (pub_id,))
    else:
        await db.execute("UPDATE publications SET status='failed' WHERE id=?", (pub_id,))
    await db.commit()

    if any_ok:
        await _notify(f"✅ Публикация #{pub_id} отправлена.")


async def _retry_target(pub_id: int, chat_id: int) -> None:
    db = get_db()
    async with db.execute(
        "SELECT status FROM publication_targets WHERE publication_id=? AND chat_id=?",
        (pub_id, chat_id),
    ) as cur:
        target = await cur.fetchone()
    if not target or target["status"] == "sent":
        return

    async with db.execute("SELECT * FROM publications WHERE id=?", (pub_id,)) as cur:
        pub = await cur.fetchone()
    if not pub:
        return

    draft = await get_draft(pub["draft_id"])
    attachments = await get_draft_attachments(pub["draft_id"])
    buttons = await get_draft_inline_buttons(pub["draft_id"])

    ok, mid, err = await publish_to_chat(_bot, chat_id, draft, attachments, buttons)
    if ok:
        await db.execute(
            """UPDATE publication_targets
               SET status='sent', message_id=?, sent_at=datetime('now'),
                   last_error=NULL, attempt_count=attempt_count+1
               WHERE publication_id=? AND chat_id=?""",
            (mid, pub_id, chat_id),
        )
        await db.commit()
        async with db.execute(
            "SELECT status FROM publication_targets WHERE publication_id=?", (pub_id,)
        ) as cur:
            rows = await cur.fetchall()
        if all(r["status"] == "sent" for r in rows):
            await db.execute("UPDATE publications SET status='sent' WHERE id=?", (pub_id,))
            await db.commit()


def schedule_prealert(prealert_id: int, run_at: datetime) -> None:
    _scheduler.add_job(
        _run_prealert,
        trigger=DateTrigger(run_date=run_at, timezone=TZ),
        id=f"pre:{prealert_id}",
        args=[prealert_id],
        replace_existing=True,
    )


async def _run_prealert(prealert_id: int) -> None:
    db = get_db()
    async with db.execute(
        """SELECT pa.*, p.scheduled_at, p.draft_id, p.status AS pub_status
           FROM publication_prealerts pa
           JOIN publications p ON p.id = pa.publication_id
           WHERE pa.id = ?""",
        (prealert_id,),
    ) as cur:
        pa = await cur.fetchone()
    if not pa or pa["sent_at"] or pa["pub_status"] != "scheduled":
        return

    draft = await get_draft(pa["draft_id"])
    preview = (draft["text"] or "")[:200] or f"[{draft['post_type']}]"

    text = (
        f"⏰ <b>Скоро публикация</b>\n\n"
        f"<b>Время:</b> {pa['scheduled_at']}\n"
        f"<b>Через:</b> {pa['minutes_before']} мин\n\n"
        f"{preview}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Исправить", callback_data=f"pub:fix:{pa['publication_id']}")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data=f"pub:cancel:{pa['publication_id']}")],
    ])
    await _notify(text, kb)
    await db.execute(
        "UPDATE publication_prealerts SET sent_at=datetime('now') WHERE id=?",
        (prealert_id,),
    )
    await db.commit()


def schedule_reminder(rem_id: int, run_at: datetime) -> None:
    _scheduler.add_job(
        _run_reminder,
        trigger=DateTrigger(run_date=run_at, timezone=TZ),
        id=f"rem:{rem_id}",
        args=[rem_id],
        replace_existing=True,
    )


def unschedule_reminder(rem_id: int) -> None:
    try:
        _scheduler.remove_job(f"rem:{rem_id}")
    except Exception:
        pass


async def _run_reminder(rem_id: int) -> None:
    db = get_db()
    async with db.execute("SELECT * FROM reminders WHERE id=?", (rem_id,)) as cur:
        r = await cur.fetchone()
    if not r or r["status"] != "active":
        return

    await _notify(f"🔔 <b>Напоминание</b>\n\n{r['text']}")

    nxt = compute_next(r)
    if nxt:
        await db.execute(
            "UPDATE reminders SET fire_at=? WHERE id=?",
            (nxt.strftime("%Y-%m-%d %H:%M:%S"), rem_id),
        )
        await db.commit()
        schedule_reminder(rem_id, nxt)
    else:
        await db.execute("UPDATE reminders SET status='done' WHERE id=?", (rem_id,))
        await db.commit()


async def restore_jobs() -> None:
    now = datetime.now(TZ)
    now_s = now.strftime("%Y-%m-%d %H:%M:%S")
    db = get_db()

    async with db.execute(
        "SELECT * FROM publications WHERE status='scheduled' AND paused=0 AND scheduled_at > ?",
        (now_s,),
    ) as cur:
        for pub in await cur.fetchall():
            dt = datetime.strptime(pub["scheduled_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
            schedule_publication(pub["id"], dt)

    async with db.execute(
        "SELECT id FROM publications WHERE status='scheduled' AND paused=1 AND scheduled_at > ?",
        (now_s,),
    ) as cur:
        for pub in await cur.fetchall():
            await _notify(
                f"⏸ Публикация #{pub['id']} на паузе. Открой «🕒 Отложенные → Предстоящие»."
            )

    async with db.execute(
        "SELECT * FROM publications WHERE status='scheduled' AND scheduled_at <= ?",
        (now_s,),
    ) as cur:
        missed = await cur.fetchall()
    for pub in missed:
        await db.execute("UPDATE publications SET status='missed' WHERE id=?", (pub["id"],))
        await _notify(
            f"⚠️ <b>Пропущена публикация #{pub['id']}</b>\n\n"
            f"Было запланировано на {pub['scheduled_at']}."
        )
    await db.commit()

    async with db.execute(
        """SELECT pa.id, pa.minutes_before, p.scheduled_at
           FROM publication_prealerts pa
           JOIN publications p ON p.id = pa.publication_id
           WHERE pa.sent_at IS NULL AND p.status='scheduled'"""
    ) as cur:
        for pa in await cur.fetchall():
            sched = datetime.strptime(pa["scheduled_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
            alert_at = sched - timedelta(minutes=pa["minutes_before"])
            if alert_at > now:
                schedule_prealert(pa["id"], alert_at)

    async with db.execute("SELECT * FROM reminders WHERE status='active'") as cur:
        for r in await cur.fetchall():
            fire = datetime.strptime(r["fire_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
            if fire > now:
                schedule_reminder(r["id"], fire)
            else:
                await _notify(
                    f"⚠️ <b>Просроченное напоминание</b>\n\n{r['text']}\n\nБыло: {r['fire_at']}"
                )

    log.info("Задачи восстановлены.")
