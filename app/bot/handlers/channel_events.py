import logging
from aiogram import Router, Bot
from aiogram.types import ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton

from app.config import settings
from app.core.channels import (
    upsert_channel_from_member,
    get_channel,
    delete_channel,
    format_rights,
    extract_rights,
    missing_critical_rights,
)


router = Router(name="channel_events")
log = logging.getLogger("ubot.channel_events")


@router.my_chat_member()
async def on_my_chat_member(event: ChatMemberUpdated, bot: Bot) -> None:
    chat = event.chat
    if chat.type != "channel":
        return

    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status

    was_admin = old_status in ("administrator", "creator")
    is_admin = new_status in ("administrator", "creator")

    if is_admin and not was_admin:
        await _on_bot_added(bot, event)
    elif was_admin and not is_admin:
        await _on_bot_demoted(bot, event)
    elif new_status in ("left", "kicked"):
        await _on_bot_removed(bot, event)


async def _on_bot_added(bot: Bot, event: ChatMemberUpdated) -> None:
    chat = event.chat
    member = event.new_chat_member
    await upsert_channel_from_member(chat, member, is_managed=False)

    rights = extract_rights(member)
    missing = missing_critical_rights(rights)

    text = (
        "📢 <b>Бот добавлен в канал</b>\n\n"
        f"<b>Название:</b> {chat.title}\n"
        f"<b>ID:</b> <code>{chat.id}</code>\n"
        f"<b>Username:</b> {'@' + chat.username if chat.username else '—'}\n\n"
        "<b>Права бота:</b>\n"
        f"{format_rights(rights)}"
    )
    if missing:
        text += f"\n\n⚠️ <b>Не хватает:</b> {', '.join(missing)}"

    buttons = []
    if not missing:
        buttons.append([InlineKeyboardButton(
            text="✅ Добавить в управляемые",
            callback_data=f"ch:add:{chat.id}",
        )])
    buttons.append([InlineKeyboardButton(
        text="🚪 Удалить из списка и выйти",
        callback_data=f"ch:leave:{chat.id}",
    )])

    await bot.send_message(
        settings.owner_telegram_id,
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


async def _on_bot_demoted(bot: Bot, event: ChatMemberUpdated) -> None:
    chat = event.chat
    row = await get_channel(chat.id)
    if row is None:
        return
    await upsert_channel_from_member(chat, event.new_chat_member, bool(row["is_managed"]))
    if not row["is_managed"]:
        return
    await bot.send_message(
        settings.owner_telegram_id,
        f"⚠️ <b>Права бота в канале снижены</b>\n\n"
        f"<b>Канал:</b> {chat.title}\n"
        f"<b>ID:</b> <code>{chat.id}</code>\n\n"
        f"Публикации в этот канал работать не будут, пока бот снова не станет администратором.",
    )


async def _on_bot_removed(bot: Bot, event: ChatMemberUpdated) -> None:
    chat = event.chat
    row = await get_channel(chat.id)
    if row is None:
        return
    was_managed = bool(row["is_managed"])
    await delete_channel(chat.id)
    if was_managed:
        await bot.send_message(
            settings.owner_telegram_id,
            f"🚪 <b>Бот удалён из канала</b>\n\n"
            f"<b>Канал:</b> {chat.title}\n"
            f"<b>ID:</b> <code>{chat.id}</code>\n\n"
            f"Канал убран из списка управляемых.",
        )
