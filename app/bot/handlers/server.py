from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from app.bot.states import ServerSettings
from app.config import settings
from app.core.security import verify_password
from app.db.db import get_owner
from app.platform import host_agent_client as host


router = Router(name="server")


def _menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Состояние", callback_data="srv:status")],
        [InlineKeyboardButton(text="🔄 Перезагрузка", callback_data="srv:reboot")],
        [InlineKeyboardButton(text="⏻ Выключение", callback_data="srv:shutdown")],
        [InlineKeyboardButton(text="💻 Терминал", callback_data="srv:terminal")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="set:back")],
    ])


def _fmt_bytes(b: float) -> str:
    for u in ("B", "КБ", "МБ", "ГБ"):
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} ТБ"


@router.callback_query(F.data == "set:server")
async def menu(callback: CallbackQuery) -> None:
    if not settings.host_agent_url:
        await callback.message.edit_text(
            "🖥 <b>Сервер</b>\n\n"
            "Host-agent не настроен. Укажи <code>HOST_AGENT_URL</code> "
            "и <code>HOST_AGENT_TOKEN</code> в <code>.env</code>.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ Назад", callback_data="set:back"),
            ]]),
        )
        await callback.answer()
        return
    await callback.message.edit_text("🖥 <b>Сервер</b>", reply_markup=_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "srv:status")
async def status(callback: CallbackQuery) -> None:
    m = await host.get_metrics()
    if not m:
        await callback.answer("Не удалось получить метрики.", show_alert=True)
        return
    from datetime import datetime
    boot = datetime.fromtimestamp(m.get("boot_time", 0))
    up_sec = int((datetime.now() - boot).total_seconds())
    days, rem = divmod(up_sec, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)

    ram = m.get("ram", {})
    disk = m.get("disk", {})

    text = (
        f"📊 <b>Состояние сервера</b>\n\n"
        f"<b>CPU:</b> {m.get('cpu_percent', 0):.1f}%\n"
        f"<b>RAM:</b> {_fmt_bytes(ram.get('used',0))} / {_fmt_bytes(ram.get('total',0))} ({ram.get('percent',0)}%)\n"
        f"<b>Диск:</b> {_fmt_bytes(disk.get('used',0))} / {_fmt_bytes(disk.get('total',0))} ({disk.get('percent',0)}%)\n"
        f"<b>Uptime:</b> {days}д {hours}ч {mins}м\n"
        f"<b>Последняя загрузка:</b> {boot.strftime('%d.%m.%Y %H:%M')}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="srv:status")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="set:server")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "srv:reboot")
async def reboot_confirm(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "🔄 <b>Перезагрузить сервер?</b>\n\nЭто прервёт работу бота.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, перезагрузить", callback_data="srv:reboot:ok")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="set:server")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "srv:reboot:ok")
async def reboot_do(callback: CallbackQuery) -> None:
    ok, err = await host.power_action("reboot")
    if ok:
        await callback.message.edit_text("🔄 Команда перезагрузки отправлена.")
    else:
        await callback.message.edit_text(f"❌ Ошибка: <code>{err}</code>")
    await callback.answer()


@router.callback_query(F.data == "srv:shutdown")
async def shutdown_confirm(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "⏻ <b>Выключить сервер?</b>\n\nУдалённое включение не предусмотрено.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, выключить", callback_data="srv:shutdown:ok")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="set:server")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "srv:shutdown:ok")
async def shutdown_do(callback: CallbackQuery) -> None:
    ok, err = await host.power_action("shutdown")
    if ok:
        await callback.message.edit_text("⏻ Команда выключения отправлена.")
    else:
        await callback.message.edit_text(f"❌ Ошибка: <code>{err}</code>")
    await callback.answer()


@router.callback_query(F.data == "srv:terminal")
async def terminal_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ServerSettings.terminal_password)
    await callback.message.edit_text("🔒 Введи мастер-пароль для доступа к терминалу:")
    await callback.answer()


@router.message(ServerSettings.terminal_password, F.text)
async def terminal_check(message: Message, state: FSMContext) -> None:
    owner = await get_owner()
    if not owner:
        await state.clear()
        await message.answer("Нет владельца.")
        return
    if not verify_password(message.text.strip(), owner["master_password_hash"]):
        try:
            await message.delete()
        except Exception:
            pass
        await message.answer("❌ Неверный пароль.")
        return

    try:
        await message.delete()
    except Exception:
        pass

    await state.set_state(ServerSettings.terminal_active)
    await message.answer(
        "💻 <b>Терминал активен.</b>\n\n"
        "Отправляй команды сообщениями. Они выполняются от имени отдельного "
        "системного пользователя.\n\n"
        "Выход: /exit\n"
        "Таймаут одной команды: 30 секунд, вывод до 4000 символов."
    )


@router.message(ServerSettings.terminal_active, F.text == "/exit")
async def terminal_exit(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("💻 Терминал закрыт.")


@router.message(ServerSettings.terminal_active, F.text)
async def terminal_exec(message: Message) -> None:
    cmd = message.text.strip()
    if not cmd:
        return
    result = await host.exec_command(cmd)
    out = (result.get("output") or "").strip() or "(пусто)"
    ok = result.get("ok", False)
    head = "✅" if ok else f"❌ exit={result.get('exit_code')}"
    await message.answer(f"<b>{head}</b>\n<pre>{out[:3800]}</pre>")
