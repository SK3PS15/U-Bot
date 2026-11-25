from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.config import settings
from app.core import backups
from app.core.app_settings import get_app_setting, set_app_setting


router = Router(name="settings")


def _menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌍 Общие", callback_data="set:general")],
        [InlineKeyboardButton(text="💾 Память и бэкапы", callback_data="set:backups")],
        [InlineKeyboardButton(text="🖥 Сервер", callback_data="set:server")],
        [InlineKeyboardButton(text="👨‍💻 Автор / Канал", url="https://t.me/sk3ps15")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:main")],
    ])


@router.callback_query(F.data == "nav:settings")
async def menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text("⚙️ <b>Настройки</b>", reply_markup=_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "set:back")
async def back(callback: CallbackQuery) -> None:
    await callback.message.edit_text("⚙️ <b>Настройки</b>", reply_markup=_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "set:general")
async def general(callback: CallbackQuery) -> None:
    prealert = await get_app_setting("prealert_minutes")
    text = (
        "🌍 <b>Общие настройки</b>\n\n"
        f"<b>Часовой пояс:</b> {settings.timezone}\n"
        "<i>(фиксирован для всех каналов и публикаций)</i>\n\n"
        f"<b>Предуведомления за:</b> {prealert} мин. до публикации"
    )
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Время предуведомлений", callback_data="set:prealert")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="set:back")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "set:prealert")
async def edit_prealert(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "Отправь список минут через запятую.\n"
        "Например: <code>1440,60,10</code> — за сутки, час и 10 минут.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад", callback_data="set:general"),
        ]]),
    )
    await callback.answer()


@router.message(F.text.regexp(r"^\d+(\s*,\s*\d+)*$"))
async def save_prealert(message: Message) -> None:
    await set_app_setting("prealert_minutes", message.text.replace(" ", ""))
    await message.answer("✅ Сохранено.")


@router.callback_query(F.data == "set:backups")
async def backups_menu(callback: CallbackQuery) -> None:
    size = await backups.db_size()
    files = await backups.list_backups()
    text = (
        f"💾 <b>Память и бэкапы</b>\n\n"
        f"<b>Размер БД:</b> {size / 1024:.1f} КБ\n"
        f"<b>Резервных копий:</b> {len(files)}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список бэкапов", callback_data="bak:list")],
        [InlineKeyboardButton(text="➕ Создать бэкап", callback_data="bak:create")],
        [InlineKeyboardButton(text="🧹 Очистки", callback_data="bak:cleanup")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="set:back")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "bak:list")
async def bak_list(callback: CallbackQuery) -> None:
    files = await backups.list_backups()
    if not files:
        await callback.message.edit_text(
            "Бэкапов нет.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ Назад", callback_data="set:backups"),
            ]]),
        )
        await callback.answer()
        return

    rows = []
    for f, sz in files[:10]:
        rows.append([InlineKeyboardButton(
            text=f"{f.name} ({sz // 1024} КБ)",
            callback_data=f"bak:del:{f.name}",
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="set:backups")])
    await callback.message.edit_text(
        "📋 <b>Бэкапы</b>\nНажми на файл, чтобы удалить:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data == "bak:create")
async def bak_create(callback: CallbackQuery) -> None:
    await callback.answer("Создаю...")
    path = await backups.create_backup()
    await callback.message.edit_text(
        f"✅ Создан бэкап: <code>{path.name}</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад", callback_data="set:backups"),
        ]]),
    )


@router.callback_query(F.data.startswith("bak:del:"))
async def bak_del(callback: CallbackQuery) -> None:
    name = callback.data[len("bak:del:"):]
    d = await backups.backups_dir()
    path = d / name
    if not path.exists():
        await callback.answer("Файл не найден.", show_alert=True)
        return
    await backups.delete_backup(path)
    await callback.message.edit_text(
        f"🗑 Удалён: <code>{name}</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад", callback_data="set:backups"),
        ]]),
    )
    await callback.answer()


@router.callback_query(F.data == "bak:cleanup")
async def bak_cleanup_menu(callback: CallbackQuery) -> None:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Старые черновики (30+ дней)", callback_data="cln:drafts")],
        [InlineKeyboardButton(text="История публикаций (90+ дней)", callback_data="cln:hist")],
        [InlineKeyboardButton(text="Выполненные напоминания (90+ дней)", callback_data="cln:rem")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="set:backups")],
    ])
    await callback.message.edit_text(
        "🧹 <b>Очистка</b>\n\nВыбери, что удалить. Перед удалением будет подтверждение.",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data == "cln:drafts")
async def cln_drafts_confirm(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "Удалить черновики старше 30 дней, не связанные с публикациями?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Удалить", callback_data="cln:drafts:ok")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="bak:cleanup")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "cln:drafts:ok")
async def cln_drafts_do(callback: CallbackQuery) -> None:
    n = await backups.cleanup_old_drafts(30)
    await callback.message.edit_text(
        f"✅ Удалено черновиков: {n}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад", callback_data="set:backups"),
        ]]),
    )
    await callback.answer()


@router.callback_query(F.data == "cln:hist")
async def cln_hist_confirm(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "Удалить историю публикаций старше 90 дней?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Удалить", callback_data="cln:hist:ok")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="bak:cleanup")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "cln:hist:ok")
async def cln_hist_do(callback: CallbackQuery) -> None:
    n = await backups.cleanup_old_history(90)
    await callback.message.edit_text(
        f"✅ Удалено записей: {n}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад", callback_data="set:backups"),
        ]]),
    )
    await callback.answer()


@router.callback_query(F.data == "cln:rem")
async def cln_rem_confirm(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "Удалить выполненные напоминания старше 90 дней?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Удалить", callback_data="cln:rem:ok")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="bak:cleanup")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "cln:rem:ok")
async def cln_rem_do(callback: CallbackQuery) -> None:
    n = await backups.cleanup_done_reminders(90)
    await callback.message.edit_text(
        f"✅ Удалено напоминаний: {n}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад", callback_data="set:backups"),
        ]]),
    )
    await callback.answer()
