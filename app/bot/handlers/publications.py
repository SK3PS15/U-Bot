import json
import logging
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

from app.bot.states import NewPost
from app.bot.keyboards.publications import (
    channels_select_kb,
    post_type_kb,
    media_done_kb,
    caption_done_kb,
    preview_actions_kb,
    buttons_editor_kb,
)
from app.core.channels import list_managed_channels, get_channel
from app.core.drafts import (
    create_draft,
    set_draft_channels,
    set_draft_text,
    add_attachment,
    count_attachments,
    get_draft,
    get_draft_channels,
    get_draft_attachments,
    set_draft_inline_buttons,
    get_draft_inline_buttons,
    delete_draft,
)
from app.core.publisher import publish_to_chat
from app.core.scheduler import schedule_publication, schedule_prealert
from app.core.app_settings import get_prealert_minutes
from app.db.db import get_db


router = Router(name="publications")
log = logging.getLogger("ubot.publications")

MAX_ALBUM = 10


@router.callback_query(F.data == "nav:new_post")
async def new_post_start(callback: CallbackQuery, state: FSMContext) -> None:
    channels = await list_managed_channels()
    if not channels:
        await callback.message.edit_text(
            "✍️ <b>Создать публикацию</b>\n\n"
            "Сначала добавь хотя бы один канал в «📢 Мои каналы».",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:main")
            ]]),
        )
        await callback.answer()
        return

    await state.clear()
    await state.update_data(selected_channels=set())
    await state.set_state(NewPost.choosing_channels)
    await callback.message.edit_text(
        "✍️ <b>Шаг 1. Выбор каналов</b>\n\n"
        "Отметь каналы для публикации и нажми «Далее».",
        reply_markup=channels_select_kb(channels, set()),
    )
    await callback.answer()


@router.callback_query(NewPost.choosing_channels, F.data.startswith("np:ch:"))
async def toggle_channel(callback: CallbackQuery, state: FSMContext) -> None:
    chat_id = int(callback.data.split(":")[2])
    data = await state.get_data()
    selected: set[int] = set(data.get("selected_channels", set()))
    if chat_id in selected:
        selected.remove(chat_id)
    else:
        selected.add(chat_id)
    await state.update_data(selected_channels=selected)
    channels = await list_managed_channels()
    await callback.message.edit_reply_markup(reply_markup=channels_select_kb(channels, selected))
    await callback.answer()


@router.callback_query(NewPost.choosing_channels, F.data == "np:ch_confirm")
async def channels_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected: set[int] = set(data.get("selected_channels", set()))
    if not selected:
        await callback.answer("Выбери хотя бы один канал.", show_alert=True)
        return
    await state.set_state(NewPost.choosing_type)
    await callback.message.edit_text(
        "✍️ <b>Шаг 2. Тип поста</b>\n\n"
        "Выбери тип. Один пост = один тип.",
        reply_markup=post_type_kb(),
    )
    await callback.answer()


@router.callback_query(NewPost.choosing_type, F.data.startswith("np:type:"))
async def choose_type(callback: CallbackQuery, state: FSMContext) -> None:
    post_type = callback.data.split(":")[2]
    draft_id = await create_draft(post_type)
    data = await state.get_data()
    await set_draft_channels(draft_id, list(data["selected_channels"]))
    await state.update_data(draft_id=draft_id, post_type=post_type)

    if post_type == "text":
        await state.set_state(NewPost.entering_text)
        await callback.message.edit_text(
            "📝 <b>Шаг 3. Текст</b>\n\n"
            "Отправь текст. HTML-разметка Telegram поддерживается."
        )
    elif post_type == "media":
        await state.set_state(NewPost.attaching_media)
        await callback.message.edit_text(
            "🖼 <b>Шаг 3. Вложение</b>\n\n"
            "Отправь один фото/видео/документ. Затем нажми «Готово»."
        )
    elif post_type == "album":
        await state.set_state(NewPost.attaching_media)
        await callback.message.edit_text(
            f"🎞 <b>Шаг 3. Альбом</b>\n\n"
            f"Отправь 2–{MAX_ALBUM} фото/видео по одному."
        )
    elif post_type == "poll":
        await state.set_state(NewPost.creating_poll)
        await callback.message.edit_text(
            "📊 <b>Шаг 3. Опрос</b>\n\nВведи вопрос опроса."
        )
    await callback.answer()


@router.message(NewPost.entering_text, F.text)
async def receive_text(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    draft_id = data["draft_id"]
    await set_draft_text(draft_id, message.html_text)
    await _show_preview(message, bot, state, draft_id)


@router.message(NewPost.attaching_media, F.photo | F.video | F.document)
async def receive_media(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    draft_id = data["draft_id"]
    post_type = data["post_type"]
    current = await count_attachments(draft_id)

    if post_type == "media" and current >= 1:
        await message.answer("Для медиа-поста достаточно одного файла. Нажми «Готово».")
        return
    if post_type == "album" and current >= MAX_ALBUM:
        await message.answer(f"Максимум {MAX_ALBUM} файлов.")
        return

    file_id = None
    file_type = None
    meta = {}
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
        meta = {"w": message.photo[-1].width, "h": message.photo[-1].height}
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
        meta = {"duration": message.video.duration}
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
        meta = {"file_name": message.document.file_name}
    else:
        return

    await add_attachment(draft_id, file_id, file_type, metadata=meta)
    total = current + 1

    if post_type == "media":
        await state.set_state(NewPost.entering_caption)
        await message.answer(
            "✅ Файл добавлен.\n\nОтправь подпись (до 1024 символов) или «Без подписи».",
            reply_markup=caption_done_kb(),
        )
    else:
        await message.answer(
            f"✅ Файлов: {total}. Ещё или «Готово».",
            reply_markup=media_done_kb(),
        )


@router.message(NewPost.entering_caption, F.text)
async def receive_caption(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await set_draft_text(data["draft_id"], message.html_text)
    await _show_preview(message, bot, state, data["draft_id"])


@router.callback_query(NewPost.entering_caption, F.data == "np:caption_skip")
async def caption_skip(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await _show_preview(callback.message, bot, state, data["draft_id"])
    await callback.answer()


@router.callback_query(NewPost.attaching_media, F.data == "np:media_done")
async def media_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    draft_id = data["draft_id"]
    post_type = data["post_type"]
    total = await count_attachments(draft_id)

    if post_type == "media" and total < 1:
        await callback.answer("Добавь хотя бы один файл.", show_alert=True)
        return
    if post_type == "album" and total < 2:
        await callback.answer("Для альбома нужно минимум 2 файла.", show_alert=True)
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    if post_type == "album":
        await state.set_state(NewPost.entering_caption)
        await callback.message.answer(
            "Отправь общую подпись (до 1024 символов) или «Без подписи».",
            reply_markup=caption_done_kb(),
        )
    await callback.answer()


@router.callback_query(NewPost.attaching_media, F.data == "np:caption_done")
async def caption_done_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.message(NewPost.creating_poll, F.text)
async def poll_question(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("poll_question"):
        await state.update_data(poll_question=message.text, poll_options=[])
        await message.answer(
            "Вопрос сохранён. Отправляй варианты по одному.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Готово", callback_data="np:poll_done")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="np:cancel")],
            ]),
        )
        return

    options = list(data.get("poll_options", []))
    if len(options) >= 10:
        await message.answer("Максимум 10 вариантов.")
        return
    options.append(message.text)
    await state.update_data(poll_options=options)
    await message.answer(
        f"Вариант {len(options)} добавлен.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Готово", callback_data="np:poll_done")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="np:cancel")],
        ]),
    )


@router.callback_query(NewPost.creating_poll, F.data == "np:poll_done")
async def poll_done(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    options = data.get("poll_options", [])
    if len(options) < 2:
        await callback.answer("Нужно минимум 2 варианта.", show_alert=True)
        return
    db = get_db()
    await db.execute(
        "UPDATE drafts SET poll_json = ? WHERE id = ?",
        (json.dumps({
            "question": data["poll_question"],
            "options": options,
            "anonymous": True,
            "type": "regular",
        }, ensure_ascii=False), data["draft_id"]),
    )
    await db.commit()
    await callback.message.edit_reply_markup(reply_markup=None)
    await _show_preview(callback.message, bot, state, data["draft_id"])
    await callback.answer()


async def _show_preview(
    message: Message, bot: Bot, state: FSMContext, draft_id: int,
) -> None:
    from app.config import settings as s
    draft = await get_draft(draft_id)
    attachments = await get_draft_attachments(draft_id)
    buttons = await get_draft_inline_buttons(draft_id)

    ok, _, err = await publish_to_chat(
        bot, s.owner_telegram_id, draft, attachments, buttons
    )

    await state.set_state(NewPost.preview)

    text = "🔎 <b>Предпросмотр</b>\n\n"
    if ok:
        text += "Пост выше — реальный, как увидят подписчики."
    else:
        text += f"⚠️ Не удалось отправить превью: <code>{err}</code>"
    text += (
        f"\n\n<b>Тип:</b> {draft['post_type']}\n"
        f"<b>Каналов:</b> {len(await get_draft_channels(draft_id))}\n"
        f"<b>Кнопок:</b> {len(buttons)}"
    )
    await message.answer(text, reply_markup=preview_actions_kb(draft_id, bool(buttons)))


@router.callback_query(NewPost.preview, F.data.startswith("np:edit_text:"))
async def edit_text_action(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewPost.entering_text)
    await callback.message.edit_text("✏️ Отправь новый текст поста. Текущий будет заменён.")
    await callback.answer()


@router.callback_query(NewPost.preview, F.data.startswith("np:cancel:"))
async def cancel_with_delete(callback: CallbackQuery, state: FSMContext) -> None:
    draft_id = int(callback.data.split(":")[2])
    await delete_draft(draft_id)
    await state.clear()
    await callback.message.edit_text(
        "❌ Черновик удалён.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:main")
        ]]),
    )
    await callback.answer()


@router.callback_query(F.data == "np:cancel")
async def cancel_simple(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    draft_id = data.get("draft_id")
    if draft_id:
        await delete_draft(draft_id)
    await state.clear()
    await callback.message.edit_text(
        "❌ Создание публикации отменено.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:main")
        ]]),
    )
    await callback.answer()


@router.callback_query(NewPost.preview, F.data.startswith("np:pub:"))
async def publish_now(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    draft_id = int(callback.data.split(":")[2])
    draft = await get_draft(draft_id)
    attachments = await get_draft_attachments(draft_id)
    buttons = await get_draft_inline_buttons(draft_id)
    chat_ids = await get_draft_channels(draft_id)

    db = get_db()
    cur = await db.execute(
        "INSERT INTO publications (draft_id, scheduled_at, status) VALUES (?, datetime('now'), 'sending')",
        (draft_id,),
    )
    publication_id = cur.lastrowid
    await db.commit()

    text = "📢 <b>Результаты публикации</b>\n\n"
    ok_count = 0
    for cid in chat_ids:
        ok, mid, err = await publish_to_chat(bot, cid, draft, attachments, buttons)
        status = "sent" if ok else "failed"
        await db.execute(
            """INSERT INTO publication_targets
               (publication_id, chat_id, status, message_id, last_error, attempt_count, sent_at)
               VALUES (?, ?, ?, ?, ?, 1, datetime('now'))""",
            (publication_id, cid, status, mid, err),
        )
        ch_row = await get_channel(cid)
        title = ch_row["title"] if ch_row else str(cid)
        if ok:
            ok_count += 1
            text += f"✅ {title}\n"
        else:
            text += f"❌ {title} — <code>{err}</code>\n"
    await db.execute("UPDATE publications SET status = 'sent' WHERE id = ?", (publication_id,))
    await db.commit()

    text += f"\nУспешно: {ok_count} из {len(chat_ids)}"
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:main")
        ]]),
    )
    await state.clear()
    await callback.answer()


@router.callback_query(NewPost.preview, F.data.startswith("np:sched:"))
async def schedule_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewPost.scheduling_input)
    await callback.message.edit_text(
        "🕒 <b>Планирование</b>\n\n"
        "Отправь дату и время в формате:\n"
        "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
        "Например: <code>25.12.2026 18:30</code>\n\n"
        "Время — Europe/Moscow."
    )
    await callback.answer()


@router.message(NewPost.scheduling_input, F.text)
async def schedule_input(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    try:
        dt = datetime.strptime(raw, "%d.%m.%Y %H:%M")
    except ValueError:
        await message.answer("Не понял формат. Пример: <code>25.12.2026 18:30</code>")
        return

    if dt <= datetime.now():
        await message.answer("Дата должна быть в будущем.")
        return

    data = await state.get_data()
    draft_id = data["draft_id"]
    chat_ids = await get_draft_channels(draft_id)

    db = get_db()
    cur = await db.execute(
        "INSERT INTO publications (draft_id, scheduled_at, status) VALUES (?, ?, 'scheduled')",
        (draft_id, dt.strftime("%Y-%m-%d %H:%M:%S")),
    )
    publication_id = cur.lastrowid
    for cid in chat_ids:
        await db.execute(
            "INSERT INTO publication_targets (publication_id, chat_id, status) VALUES (?, ?, 'pending')",
            (publication_id, cid),
        )
    await db.commit()

    from datetime import timedelta
    minutes_list = await get_prealert_minutes()
    scheduled_alerts = []
    for m in minutes_list:
        alert_at = dt - timedelta(minutes=m)
        if alert_at <= datetime.now():
            continue
        cur2 = await db.execute(
            "INSERT INTO publication_prealerts (publication_id, minutes_before) VALUES (?, ?)",
            (publication_id, m),
        )
        await db.commit()
        schedule_prealert(cur2.lastrowid, alert_at)
        scheduled_alerts.append(m)

    schedule_publication(publication_id, dt)

    alerts_text = ", ".join(f"за {m} мин" for m in scheduled_alerts) or "нет"
    await message.answer(
        f"✅ Публикация запланирована на <b>{dt.strftime('%d.%m.%Y %H:%M')}</b>.\n\n"
        f"<b>Предуведомления:</b> {alerts_text}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:main")
        ]]),
    )
    await state.clear()


@router.callback_query(NewPost.preview, F.data.startswith("np:btn_list:"))
async def btn_list(callback: CallbackQuery, state: FSMContext) -> None:
    draft_id = int(callback.data.split(":")[2])
    buttons = await get_draft_inline_buttons(draft_id)
    await state.set_state(NewPost.buttons_list)
    await state.update_data(draft_id=draft_id)

    if not buttons:
        text = "🔗 <b>Кнопки</b>\n\nСписок пуст. Добавь первую кнопку."
    else:
        lines = ["🔗 <b>Кнопки под постом</b>\n"]
        for i, b in enumerate(buttons, 1):
            lines.append(f"{i}. <b>{b['text']}</b> → {b['url']}")
        text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=buttons_editor_kb(draft_id, buttons))
    await callback.answer()


@router.callback_query(NewPost.buttons_list, F.data.startswith("np:btn_add:"))
async def btn_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NewPost.adding_button_text)
    await state.update_data(editing_index=None)
    await callback.message.edit_text("Введи <b>текст</b> кнопки (до 64 символов).")
    await callback.answer()


@router.message(NewPost.adding_button_text, F.text)
async def btn_add_text(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text or len(text) > 64:
        await message.answer("Текст от 1 до 64 символов. Попробуй снова.")
        return
    await state.update_data(pending_btn_text=text)
    await state.set_state(NewPost.adding_button_url)
    await message.answer("Теперь отправь <b>URL</b> (начинается с http:// или https://).")


@router.callback_query(NewPost.buttons_list, F.data.startswith("np:btn_edit:"))
async def btn_edit(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, draft_id, index = callback.data.split(":")
    index = int(index)
    buttons = await get_draft_inline_buttons(int(draft_id))
    if index >= len(buttons):
        await callback.answer("Кнопка не найдена.", show_alert=True)
        return
    await state.update_data(editing_index=index, draft_id=int(draft_id))
    await state.set_state(NewPost.adding_button_text)
    await callback.message.edit_text(
        f"Текущий текст: <b>{buttons[index]['text']}</b>\n\nВведи новый текст."
    )
    await callback.answer()


@router.message(NewPost.adding_button_url, F.text)
async def btn_add_url(message: Message, state: FSMContext) -> None:
    url = message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer("URL должен начинаться с http:// или https://")
        return

    data = await state.get_data()
    draft_id = data["draft_id"]
    text = data["pending_btn_text"]
    editing_index = data.get("editing_index")

    buttons = await get_draft_inline_buttons(draft_id)
    if editing_index is not None and editing_index < len(buttons):
        buttons[editing_index] = {"text": text, "url": url}
    else:
        buttons.append({"text": text, "url": url})
    await set_draft_inline_buttons(draft_id, buttons)

    await state.set_state(NewPost.buttons_list)
    lines = ["🔗 <b>Кнопки под постом</b>\n"]
    for i, b in enumerate(buttons, 1):
        lines.append(f"{i}. <b>{b['text']}</b> → {b['url']}")
    await message.answer("\n".join(lines), reply_markup=buttons_editor_kb(draft_id, buttons))


@router.callback_query(NewPost.buttons_list, F.data.startswith("np:btn_del:"))
async def btn_del(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, draft_id, index = callback.data.split(":")
    draft_id, index = int(draft_id), int(index)
    buttons = await get_draft_inline_buttons(draft_id)
    if index < len(buttons):
        buttons.pop(index)
        await set_draft_inline_buttons(draft_id, buttons)
    if not buttons:
        text = "🔗 <b>Кнопки</b>\n\nСписок пуст."
    else:
        lines = ["🔗 <b>Кнопки под постом</b>\n"]
        for i, b in enumerate(buttons, 1):
            lines.append(f"{i}. <b>{b['text']}</b> → {b['url']}")
        text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=buttons_editor_kb(draft_id, buttons))
    await callback.answer("Удалено")


@router.callback_query(NewPost.buttons_list, F.data.startswith("np:btn_done:"))
async def btn_done(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    draft_id = int(callback.data.split(":")[2])
    await callback.message.delete()
    await _show_preview(callback.message, bot, state, draft_id)
    await callback.answer()
