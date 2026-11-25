import json
from typing import Any

from aiogram import Bot

from app.db.db import get_db


RIGHTS_LABELS = {
    "can_post_messages": "Публикация сообщений",
    "can_edit_messages": "Редактирование сообщений",
    "can_delete_messages": "Удаление сообщений",
    "can_pin_messages": "Закрепление сообщений",
    "can_invite_users": "Приглашение пользователей",
    "can_restrict_members": "Ограничение участников",
    "can_promote_members": "Назначение администраторов",
    "can_change_info": "Изменение информации канала",
    "can_manage_topics": "Управление темами",
}


def extract_rights(member: Any) -> dict:
    return {k: bool(getattr(member, k, False)) for k in RIGHTS_LABELS}


async def upsert_channel_from_member(chat: Any, member: Any, is_managed: bool) -> None:
    db = get_db()
    rights = extract_rights(member)
    await db.execute(
        """INSERT INTO channels (chat_id, title, username, chat_type, is_managed, bot_status, bot_rights_json, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
           ON CONFLICT(chat_id) DO UPDATE SET
             title = excluded.title,
             username = excluded.username,
             bot_status = excluded.bot_status,
             bot_rights_json = excluded.bot_rights_json,
             updated_at = datetime('now')""",
        (
            chat.id,
            chat.title or str(chat.id),
            getattr(chat, "username", None),
            chat.type,
            1 if is_managed else 0,
            getattr(member, "status", None),
            json.dumps(rights, ensure_ascii=False),
        ),
    )
    await db.commit()


async def get_channel(chat_id: int):
    db = get_db()
    async with db.execute("SELECT * FROM channels WHERE chat_id = ?", (chat_id,)) as cur:
        return await cur.fetchone()


async def list_managed_channels():
    db = get_db()
    async with db.execute(
        "SELECT * FROM channels WHERE is_managed = 1 ORDER BY title COLLATE NOCASE"
    ) as cur:
        return await cur.fetchall()


async def set_managed(chat_id: int, managed: bool) -> None:
    db = get_db()
    await db.execute(
        "UPDATE channels SET is_managed = ?, updated_at = datetime('now') WHERE chat_id = ?",
        (1 if managed else 0, chat_id),
    )
    await db.commit()


async def delete_channel(chat_id: int) -> None:
    db = get_db()
    await db.execute("DELETE FROM channels WHERE chat_id = ?", (chat_id,))
    await db.commit()


async def refresh_rights(bot: Bot, chat_id: int) -> dict | None:
    try:
        me = await bot.me()
        member = await bot.get_chat_member(chat_id, me.id)
    except Exception:
        return None
    rights = extract_rights(member)
    db = get_db()
    await db.execute(
        "UPDATE channels SET bot_rights_json = ?, bot_status = ?, updated_at = datetime('now') WHERE chat_id = ?",
        (json.dumps(rights, ensure_ascii=False), getattr(member, "status", None), chat_id),
    )
    await db.commit()
    return rights


def format_rights(rights: dict) -> str:
    if not rights:
        return "—"
    return "\n".join(
        f"{'✅' if rights.get(k) else '❌'} {label}"
        for k, label in RIGHTS_LABELS.items()
    )


def missing_critical_rights(rights: dict) -> list[str]:
    missing = []
    if not rights.get("can_post_messages"):
        missing.append("Публикация сообщений")
    return missing
