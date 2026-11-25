from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:main")]]
    )
