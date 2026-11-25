import json
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

from app.core.channels import (
    list_managed_channels,
    get_channel,
    set_managed,
    refresh_rights,
    format_rights,
    missing_critical_rights,
    delete_channel,
)


router = Router(name="channels")


def _channels_list_kb(channels) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(
        text=ch["title"], callback_data=f"ch:view:{ch['chat_id']}"
    )] for ch in channels]
    buttons.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "nav:channels")
async def channels_menu(callback: CallbackQuery) -> None:
    channels = await list_managed_channels()
    if not channels:
        await callback.message.edit_text(
            "📢 <b>Мои каналы</b>\n\n"
            "Пока нет управляемых каналов.\n\n"
            "Добавь бота администратором в канал — я сразу пришлю уведомление.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:main")
            ]]),
        )
    else:
        await callback.message.edit_text(
            f"📢 <b>Мои каналы</b> ({len(channels)}):\n\nВыбери канал:",
            reply_markup=_channels_list_kb(channels),
        )
    await callback.answer()


@router.callback_query(F.data == "ch:list")
async def on_list(callback: CallbackQuery) -> None:
    channels = await list_managed_channels()
    if not channels:
        await callback.message.edit_text(
            "📢 Управляемых каналов нет.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:main")
            ]]),
        )
    else:
        await callback.message.edit_text(
            f"📢 <b>Мои каналы</b> ({len(channels)}):",
            reply_markup=_channels_list_kb(channels),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("ch:add:"))
async def on_add(callback: CallbackQuery, bot: Bot) -> None:
    chat_id = int(callback.data.split(":")[2])
    row = await get_channel(chat_id)
    if row is None:
        await callback.answer("Канал не найден.", show_alert=True)
        return
    rights = await refresh_rights(bot, chat_id)
    if rights is None:
        await callback.answer("Не удалось проверить права бота.", show_alert=True)
        return
    if not rights.get("can_post_messages"):
        await callback.answer(
            "Без права «Публикация сообщений» добавить нельзя.",
            show_alert=True,
        )
        return
    await set_managed(chat_id, True)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"✅ Канал <b>{row['title']}</b> добавлен в управляемые.")
    await callback.answer("Добавлен")


@router.callback_query(F.data.startswith("ch:leave:"))
async def on_leave(callback: CallbackQuery, bot: Bot) -> None:
    chat_id = int(callback.data.split(":")[2])
    try:
        await bot.leave_chat(chat_id)
    except Exception:
        pass
    await delete_channel(chat_id)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("🚪 Бот вышел из канала. Канал удалён из списка.")
    await callback.answer("Вышли")


@router.callback_query(F.data.startswith("ch:view:"))
async def on_view(callback: CallbackQuery, bot: Bot) -> None:
    chat_id = int(callback.data.split(":")[2])
    row = await get_channel(chat_id)
    if row is None:
        await callback.answer("Канал не найден.", show_alert=True)
        return

    rights = await refresh_rights(bot, chat_id) or json.loads(row["bot_rights_json"] or "{}")
    text = (
        f"📢 <b>{row['title']}</b>\n\n"
        f"<b>ID:</b> <code>{row['chat_id']}</code>\n"
        f"<b>Username:</b> {'@' + row['username'] if row['username'] else '—'}\n"
        f"<b>Статус бота:</b> {row['bot_status'] or '—'}\n\n"
        f"<b>Права:</b>\n{format_rights(rights)}"
    )
    missing = missing_critical_rights(rights)
    if missing:
        text += f"\n\n⚠️ <b>Не хватает:</b> {', '.join(missing)}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить права", callback_data=f"ch:check:{chat_id}")],
        [InlineKeyboardButton(text="🗑 Удалить из управления", callback_data=f"ch:remove:{chat_id}")],
        [InlineKeyboardButton(text="⬅️ К списку каналов", callback_data="ch:list")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("ch:check:"))
async def on_check(callback: CallbackQuery, bot: Bot) -> None:
    chat_id = int(callback.data.split(":")[2])
    rights = await refresh_rights(bot, chat_id)
    if rights is None:
        await callback.answer("Не удалось проверить (бот не админ или канала нет).", show_alert=True)
        return
    missing = missing_critical_rights(rights)
    if missing:
        await callback.answer(f"Не хватает: {', '.join(missing)}", show_alert=True)
    else:
        await callback.answer("✅ Критичные права на месте.")


@router.callback_query(F.data.startswith("ch:remove:"))
async def on_remove_ask(callback: CallbackQuery) -> None:
    chat_id = int(callback.data.split(":")[2])
    await callback.message.edit_text(
        "🗑 Убрать канал из списка управляемых?\n\n"
        "Сам канал, его участники и публикации останутся. Бот тоже останется админом, "
        "если не удалить его вручную.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, убрать", callback_data=f"ch:removeok:{chat_id}")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"ch:view:{chat_id}")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ch:removeok:"))
async def on_remove_confirm(callback: CallbackQuery) -> None:
    chat_id = int(callback.data.split(":")[2])
    await set_managed(chat_id, False)
    await callback.message.edit_text(
        "✅ Канал убран из управления.\n\n"
        "Бот остался в канале. Если нужно вывести — удали вручную в Telegram.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ К списку каналов", callback_data="ch:list")
        ]]),
    )
    await callback.answer()
