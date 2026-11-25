from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def channels_select_kb(channels, selected: set[int]) -> InlineKeyboardMarkup:
    rows = []
    for ch in channels:
        mark = "✅" if ch["chat_id"] in selected else "⬜️"
        rows.append([InlineKeyboardButton(
            text=f"{mark} {ch['title']}",
            callback_data=f"np:ch:{ch['chat_id']}",
        )])
    rows.append([InlineKeyboardButton(text=f"➡️ Далее ({len(selected)})", callback_data="np:ch_confirm")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="np:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def post_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Текст", callback_data="np:type:text")],
        [InlineKeyboardButton(text="🖼 Медиа (1 файл + подпись)", callback_data="np:type:media")],
        [InlineKeyboardButton(text="🎞 Альбом (2–10 файлов)", callback_data="np:type:album")],
        [InlineKeyboardButton(text="📊 Опрос", callback_data="np:type:poll")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="np:cancel")],
    ])


def media_done_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готово", callback_data="np:media_done")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="np:cancel")],
    ])


def caption_done_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готово", callback_data="np:caption_done")],
        [InlineKeyboardButton(text="⏭ Без подписи", callback_data="np:caption_skip")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="np:cancel")],
    ])


def preview_actions_kb(draft_id: int, has_buttons: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опубликовать сейчас", callback_data=f"np:pub:{draft_id}")],
        [InlineKeyboardButton(text="🕒 Запланировать", callback_data=f"np:sched:{draft_id}")],
        [InlineKeyboardButton(text=f"🔗 Кнопки ({'изменить' if has_buttons else 'добавить'})", callback_data=f"np:btn_list:{draft_id}")],
        [InlineKeyboardButton(text="✏️ Изменить текст", callback_data=f"np:edit_text:{draft_id}")],
        [InlineKeyboardButton(text="❌ Отменить и удалить", callback_data=f"np:cancel:{draft_id}")],
    ])


def buttons_editor_kb(draft_id: int, buttons: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for i, btn in enumerate(buttons):
        rows.append([InlineKeyboardButton(text=f"✏️ {btn['text'][:30]}", callback_data=f"np:btn_edit:{draft_id}:{i}")])
        rows.append([InlineKeyboardButton(text="🗑 Удалить", callback_data=f"np:btn_del:{draft_id}:{i}")])
    rows.append([InlineKeyboardButton(text="➕ Добавить кнопку", callback_data=f"np:btn_add:{draft_id}")])
    rows.append([InlineKeyboardButton(text="✅ Готово", callback_data=f"np:btn_done:{draft_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
