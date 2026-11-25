from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from app.bot.keyboards.main_menu import main_menu_kb


router = Router(name="menu")


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("Главное меню:", reply_markup=main_menu_kb())


@router.callback_query(F.data == "nav:main")
async def nav_main(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Главное меню:", reply_markup=main_menu_kb())
    await callback.answer()
