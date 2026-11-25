from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove

from app.db.db import get_db, get_owner
from app.bot.keyboards.main_menu import main_menu_kb, author_kb


router = Router(name="start")


WELCOME_TEXT = (
    "👋 <b>Привет!</b>\n\n"
    "Я — <b>U-Bot</b>, твой персональный помощник для управления "
    "Telegram-каналами и домашним сервером.\n\n"
    "Создатель: @sk3ps15\n\n"
    "Нажми «Я ознакомился», чтобы начать."
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    owner = await get_owner()
    if owner is None:
        await message.answer("⚠️ Бот не настроен. Запустите мастер настройки на сервере.")
        return

    if owner["intro_shown"]:
        await message.answer("Очищаю старые кнопки...", reply_markup=ReplyKeyboardRemove())
        await message.answer("Главное меню:", reply_markup=main_menu_kb())
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я ознакомился", callback_data="intro_ok")],
            [InlineKeyboardButton(text="👨‍💻 Автор / Канал", url="https://t.me/sk3ps15")],
        ]
    )
    await message.answer(WELCOME_TEXT, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "intro_ok")
async def intro_ok(callback: CallbackQuery) -> None:
    db = get_db()
    await db.execute("UPDATE owner SET intro_shown = 1 WHERE id = 1")
    await db.commit()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Готово! Выбери раздел:", reply_markup=main_menu_kb())
    await callback.answer()
