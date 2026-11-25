from app.db.db import get_db


DEFAULTS = {
    "date_format": "%d.%m.%Y %H:%M",
    "prealert_minutes": "60",
}


async def get_app_setting(key: str) -> str:
    db = get_db()
    async with db.execute("SELECT value FROM app_settings WHERE key = ?", (key,)) as cur:
        row = await cur.fetchone()
    if row:
        return row["value"]
    return DEFAULTS.get(key, "")


async def set_app_setting(key: str, value: str) -> None:
    db = get_db()
    await db.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    await db.commit()


async def get_prealert_minutes() -> list[int]:
    raw = await get_app_setting("prealert_minutes")
    result = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            result.append(int(part))
    return result
