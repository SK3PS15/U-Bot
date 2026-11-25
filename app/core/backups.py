from datetime import datetime
from pathlib import Path

import aiosqlite

from app.config import settings
from app.db.db import get_db


async def backups_dir() -> Path:
    p = Path(settings.data_dir) / "backups"
    p.mkdir(parents=True, exist_ok=True)
    return p


async def create_backup() -> Path:
    dest_dir = await backups_dir()
    name = f"ubot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    dest = dest_dir / name
    source = get_db()
    async with aiosqlite.connect(str(dest)) as target:
        await source.backup(target)
    return dest


async def list_backups() -> list[tuple[Path, int]]:
    d = await backups_dir()
    result = []
    for f in sorted(d.glob("*.db"), reverse=True):
        try:
            result.append((f, f.stat().st_size))
        except Exception:
            pass
    return result


async def delete_backup(path: Path) -> None:
    try:
        if path.parent.resolve() == (await backups_dir()).resolve():
            path.unlink(missing_ok=True)
    except Exception:
        pass


async def db_size() -> int:
    try:
        return settings.db_path.stat().st_size
    except Exception:
        return 0


async def cleanup_old_drafts(days: int = 30) -> int:
    db = get_db()
    async with db.execute(
        "SELECT COUNT(*) AS c FROM drafts WHERE "
        "updated_at < datetime('now', ?) AND id NOT IN (SELECT draft_id FROM publications)",
        (f"-{days} days",),
    ) as cur:
        row = await cur.fetchone()
    count = row["c"]
    if count:
        await db.execute(
            "DELETE FROM drafts WHERE "
            "updated_at < datetime('now', ?) AND id NOT IN (SELECT draft_id FROM publications)",
            (f"-{days} days",),
        )
        await db.commit()
    return count


async def cleanup_old_history(days: int = 90) -> int:
    db = get_db()
    async with db.execute(
        "SELECT COUNT(*) AS c FROM publications WHERE "
        "scheduled_at < datetime('now', ?) AND status IN ('sent','cancelled','failed','partial','missed')",
        (f"-{days} days",),
    ) as cur:
        row = await cur.fetchone()
    count = row["c"]
    if count:
        await db.execute(
            "DELETE FROM publications WHERE "
            "scheduled_at < datetime('now', ?) AND status IN ('sent','cancelled','failed','partial','missed')",
            (f"-{days} days",),
        )
        await db.commit()
    return count


async def cleanup_done_reminders(days: int = 90) -> int:
    db = get_db()
    async with db.execute(
        "SELECT COUNT(*) AS c FROM reminders WHERE status='done' AND fire_at < datetime('now', ?)",
        (f"-{days} days",),
    ) as cur:
        row = await cur.fetchone()
    count = row["c"]
    if count:
        await db.execute(
            "DELETE FROM reminders WHERE status='done' AND fire_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        await db.commit()
    return count
