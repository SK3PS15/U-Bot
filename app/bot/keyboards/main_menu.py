from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Мои каналы", callback_data="nav:channels"),
         InlineKeyboardButton(text="✍️ Создать публикацию", callback_data="nav:new_post")],
        [InlineKeyboardButton(text="🕒 Отложенные", callback_data="nav:scheduled"),
         InlineKeyboardButton(text="🔔 Напоминания", callback_data="nav:reminders")],
        [InlineKeyboardButton(text="📨 Уведомления", callback_data="nav:notifications"),
         InlineKeyboardButton(text="📊 Статистика", callback_data="nav:stats")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="nav:settings")],
    ])
