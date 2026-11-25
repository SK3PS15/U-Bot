import json

from app.db.db import get_db


POST_TYPES = ("text", "media", "album", "poll")


async def create_draft(post_type: str) -> int:
    db = get_db()
    cur = await db.execute("INSERT INTO drafts (post_type) VALUES (?)", (post_type,))
    await db.commit()
    return cur.lastrowid


async def set_draft_text(draft_id: int, text: str, entities_json: str | None = None) -> None:
    db = get_db()
    await db.execute(
        "UPDATE drafts SET text = ?, entities_json = ?, updated_at = datetime('now') WHERE id = ?",
        (text, entities_json, draft_id),
    )
    await db.commit()


async def set_draft_channels(draft_id: int, chat_ids: list[int]) -> None:
    db = get_db()
    await db.execute("DELETE FROM draft_channels WHERE draft_id = ?", (draft_id,))
    await db.executemany(
        "INSERT INTO draft_channels (draft_id, chat_id) VALUES (?, ?)",
        [(draft_id, cid) for cid in chat_ids],
    )
    await db.commit()


async def get_draft(draft_id: int):
    db = get_db()
    async with db.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)) as cur:
        return await cur.fetchone()


async def get_draft_channels(draft_id: int) -> list[int]:
    db = get_db()
    async with db.execute(
        "SELECT chat_id FROM draft_channels WHERE draft_id = ?", (draft_id,)
    ) as cur:
        rows = await cur.fetchall()
    return [r["chat_id"] for r in rows]


async def get_draft_attachments(draft_id: int):
    db = get_db()
    async with db.execute(
        "SELECT * FROM draft_attachments WHERE draft_id = ? ORDER BY position",
        (draft_id,),
    ) as cur:
        return await cur.fetchall()


async def add_attachment(
    draft_id: int,
    file_id: str,
    file_type: str,
    caption: str | None = None,
    metadata: dict | None = None,
) -> int:
    db = get_db()
    async with db.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 AS pos FROM draft_attachments WHERE draft_id = ?",
        (draft_id,),
    ) as cur:
        row = await cur.fetchone()
    pos = row["pos"]
    await db.execute(
        """INSERT INTO draft_attachments (draft_id, position, file_id, file_type, caption, metadata_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            draft_id,
            pos,
            file_id,
            file_type,
            caption,
            json.dumps(metadata, ensure_ascii=False) if metadata else None,
        ),
    )
    await db.commit()
    return pos


async def remove_attachment(attachment_id: int) -> None:
    db = get_db()
    await db.execute("DELETE FROM draft_attachments WHERE id = ?", (attachment_id,))
    await db.commit()


async def count_attachments(draft_id: int) -> int:
    db = get_db()
    async with db.execute(
        "SELECT COUNT(*) AS c FROM draft_attachments WHERE draft_id = ?", (draft_id,)
    ) as cur:
        row = await cur.fetchone()
    return row["c"]


async def set_draft_inline_buttons(draft_id: int, buttons: list[dict]) -> None:
    db = get_db()
    await db.execute(
        "UPDATE drafts SET inline_buttons_json = ?, updated_at = datetime('now') WHERE id = ?",
        (json.dumps(buttons, ensure_ascii=False), draft_id),
    )
    await db.commit()


async def get_draft_inline_buttons(draft_id: int) -> list[dict]:
    draft = await get_draft(draft_id)
    if not draft or not draft["inline_buttons_json"]:
        return []
    try:
        return json.loads(draft["inline_buttons_json"])
    except Exception:
        return []


async def delete_draft(draft_id: int) -> None:
    db = get_db()
    await db.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))
    await db.commit()
