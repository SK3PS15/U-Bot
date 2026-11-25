from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.core.notifications import DEFAULTS, LABELS, get_setting, set_setting


router = Router(name="notifications")


async def _kb() -> InlineKeyboardMarkup:
    rows = []
    for key in DEFAULTS:
        enabled = await get_setting(key)
        mark = "✅" if enabled else "⬜️"
        rows.append([InlineKeyboardButton(
            text=f"{mark} {LABELS[key]}",
            callback_data=f"notif:t:{key}",
        )])
    rows.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "nav:notifications")
async def menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "📨 <b>Уведомления</b>\n\nНажми, чтобы включить/выключить категорию.",
        reply_markup=await _kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("notif:t:"))
async def toggle(callback: CallbackQuery) -> None:
    key = callback.data[len("notif:t:"):]
    current = await get_setting(key)
    await set_setting(key, not current)
    await callback.message.edit_reply_markup(reply_markup=await _kb())
    await callback.answer("Включено" if not current else "Выключено")
