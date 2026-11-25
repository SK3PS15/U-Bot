import aiosqlite
from pathlib import Path

from app.config import settings

_db: aiosqlite.Connection | None = None

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


async def init_db() -> aiosqlite.Connection:
    global _db
    if _db is not None:
        return _db

    db_path = settings.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    _db = await aiosqlite.connect(str(db_path))
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA foreign_keys = ON")
    await _db.execute("PRAGMA journal_mode = WAL")

    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    await _db.executescript(schema)
    await _db.commit()
    await _db.execute(
        """CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )"""
    )
    await _db.commit()
    return _db


def get_db() -> aiosqlite.Connection:
    if _db is None:
        raise RuntimeError("Database is not initialized. Call init_db() first.")
    return _db


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def get_owner() -> aiosqlite.Row | None:
    db = get_db()
    async with db.execute("SELECT * FROM owner WHERE id = 1") as cur:
        return await cur.fetchone()


async def save_owner(telegram_id: int, master_password_hash: str) -> None:
    db = get_db()
    await db.execute(
        """INSERT INTO owner (id, telegram_id, master_password_hash)
           VALUES (1, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             telegram_id = excluded.telegram_id,
             master_password_hash = excluded.master_password_hash""",
        (telegram_id, master_password_hash),
    )
    await db.commit()
