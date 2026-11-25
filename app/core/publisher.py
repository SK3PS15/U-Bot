import json
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto, InputMediaVideo,
)


log = logging.getLogger("ubot.publisher")


def build_inline_kb(buttons: list[dict] | None) -> InlineKeyboardMarkup | None:
    if not buttons:
        return None
    rows = []
    for btn in buttons:
        text = (btn.get("text") or "").strip()
        url = (btn.get("url") or "").strip()
        if not text or not url:
            continue
        rows.append([InlineKeyboardButton(text=text, url=url)])
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def publish_to_chat(
    bot: Bot,
    chat_id: int,
    draft,
    attachments: list,
    buttons: list[dict] | None,
) -> tuple[bool, int | None, str | None]:
    try:
        post_type = draft["post_type"]
        text = draft["text"] or ""
        kb = build_inline_kb(buttons) if post_type != "album" else None
        msg = None

        if post_type == "text":
            if not text.strip():
                return False, None, "Пустой текст"
            msg = await bot.send_message(chat_id, text, reply_markup=kb)

        elif post_type == "media":
            if not attachments:
                return False, None, "Нет вложения"
            att = attachments[0]
            ft, fid = att["file_type"], att["file_id"]
            caption = text or None
            if ft == "photo":
                msg = await bot.send_photo(chat_id, fid, caption=caption, reply_markup=kb)
            elif ft == "video":
                msg = await bot.send_video(chat_id, fid, caption=caption, reply_markup=kb)
            elif ft == "document":
                msg = await bot.send_document(chat_id, fid, caption=caption, reply_markup=kb)
            else:
                return False, None, f"Неподдерживаемый тип: {ft}"

        elif post_type == "album":
            if len(attachments) < 2:
                return False, None, "Для альбома нужно минимум 2 файла"
            media = []
            for att in attachments:
                if att["file_type"] == "photo":
                    media.append(InputMediaPhoto(media=att["file_id"]))
                elif att["file_type"] == "video":
                    media.append(InputMediaVideo(media=att["file_id"]))
                else:
                    return False, None, "Альбом поддерживает только фото и видео"
            msgs = await bot.send_media_group(chat_id, media=media)
            msg = msgs[0] if msgs else None
            if text.strip() and msg:
                await bot.send_message(chat_id, text, reply_markup=kb)

        elif post_type == "poll":
            if not draft["poll_json"]:
                return False, None, "Опрос пуст"
            poll = json.loads(draft["poll_json"])
            msg = await bot.send_poll(
                chat_id,
                question=poll["question"],
                options=poll["options"],
                is_anonymous=poll.get("anonymous", True),
                type=poll.get("type", "regular"),
            )

        else:
            return False, None, f"Неизвестный тип: {post_type}"

        return True, msg.message_id if msg else None, None

    except TelegramAPIError as e:
        return False, None, f"Telegram API: {e}"
    except Exception as e:
        return False, None, f"{type(e).__name__}: {e}"
