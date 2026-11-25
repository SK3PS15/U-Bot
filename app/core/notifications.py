import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from app.config import settings
from app.db.db import get_db


log = logging.getLogger("ubot.notify")

DEFAULTS = {
    "channels.posts": 1,
    "channels.edits": 1,
    "channels.admins": 1,
    "channels.pins": 1,
    "publications.success": 1,
    "publications.error": 1,
    "publications.prealert": 1,
    "reminders.fire": 1,
    "reminders.overdue": 1,
    "server.internet": 1,
    "server.cpu": 1,
    "server.ram": 1,
    "server.disk": 1,
    "server.power": 1,
}

LABELS = {
    "channels.posts": "Новые публикации в каналах",
    "channels.edits": "Изменения публикаций",
    "channels.admins": "Изменения администраторов",
    "channels.pins": "Закрепления",
    "publications.success": "Успешная отправка",
    "publications.error": "Ошибки публикаций",
    "publications.prealert": "Предуведомления",
    "reminders.fire": "Сработавшие напоминания",
    "reminders.overdue": "Просроченные напоминания",
    "server.internet": "Проблемы с интернетом",
    "server.cpu": "Высокая загрузка CPU",
    "server.ram": "Нехватка RAM",
    "server.disk": "Мало места на диске",
    "server.power": "Запуск/остановка бота",
}


async def get_setting(key: str) -> bool:
    db = get_db()
    async with db.execute("SELECT enabled FROM notification_settings WHERE key = ?", (key,)) as cur:
        row = await cur.fetchone()
    if row:
        return bool(row["enabled"])
    return bool(DEFAULTS.get(key, 1))


async def set_setting(key: str, enabled: bool) -> None:
    db = get_db()
    await db.execute(
        "INSERT INTO notification_settings (key, enabled) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET enabled = excluded.enabled",
        (key, 1 if enabled else 0),
    )
    await db.commit()


async def notify(bot: Bot, key: str, text: str, kb: InlineKeyboardMarkup | None = None) -> None:
    if not await get_setting(key):
        return
    try:
        await bot.send_message(settings.owner_telegram_id, text, reply_markup=kb)
    except Exception as e:
        log.warning("Не удалось отправить уведомление %s: %s", key, e)
