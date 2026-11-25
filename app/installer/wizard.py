import asyncio
import sys
from pathlib import Path

import aiohttp

from app.config import settings
from app.core.security import hash_password
from app.db.db import init_db, save_owner, close_db


def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        print("\n[!] Ввод прерван.")
        sys.exit(1)


async def _verify_token(token: str) -> dict | None:
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15) as resp:
                data = await resp.json(content_type=None)
                if data.get("ok"):
                    return data["result"]
                return None
    except Exception as e:
        print(f"[!] Ошибка проверки токена: {e}")
        return None


async def _get_updates(token: str, offset: int | None) -> list[dict]:
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {"timeout": 25, "allowed_updates": '["message"]'}
    if offset is not None:
        params["offset"] = offset
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=35) as resp:
                data = await resp.json(content_type=None)
                if data.get("ok"):
                    return data["result"]
    except Exception:
        pass
    return []


async def _wait_for_start(token: str, expected_id: int) -> dict | None:
    print("\n[→] Открой Telegram и отправь боту команду /start")
    print("    Ожидание (до 5 минут)...\n")
    offset = None
    for _ in range(12):
        updates = await _get_updates(token, offset)
        for upd in updates:
            offset = upd["update_id"] + 1
            msg = upd.get("message")
            if not msg:
                continue
            text = (msg.get("text") or "").strip()
            if not text.startswith("/start"):
                continue
            sender = msg.get("from") or {}
            sender_id = sender.get("id")
            if sender_id == expected_id:
                return sender
            else:
                print(f"[!] Получен /start от чужого ID {sender_id}. Ожидаем нужный.")
    return None


async def run_wizard() -> None:
    print("=" * 60)
    print("  U-Bot — первоначальная настройка")
    print("=" * 60)

    while True:
        token = _ask("\n[1/4] Введите токен Telegram-бота: ")
        if not token:
            print("[!] Пустой токен.")
            continue
        print("[→] Проверка токена...")
        me = await _verify_token(token)
        if not me:
            print("[!] Токен недействителен. Попробуйте снова.")
            continue
        print(f"[✓] Бот: @{me.get('username')} ({me.get('first_name')})")
        if _ask("    Всё верно? (y/n): ").lower() == "y":
            break

    while True:
        raw = _ask("\n[2/4] Введите ваш Telegram ID (число): ")
        if not raw.isdigit():
            print("[!] Нужно числовое значение.")
            continue
        owner_id = int(raw)
        if owner_id <= 0:
            print("[!] Некорректный ID.")
            continue
        break

    sender = await _wait_for_start(token, owner_id)
    if not sender:
        print("[!] Не дождались /start. Выход.")
        sys.exit(1)
    print(f"[✓] Получен /start от ID {sender.get('id')}")
    print(f"    Имя: {sender.get('first_name')} {sender.get('last_name') or ''}".strip())
    print(f"    Username: @{sender.get('username') or '—'}")
    if _ask("    Это вы? (y/n): ").lower() != "y":
        print("[!] Настройка прервана пользователем.")
        sys.exit(1)

    while True:
        pwd1 = _ask("\n[3/4] Придумайте мастер-пароль: ")
        if len(pwd1) < 6:
            print("[!] Минимум 6 символов.")
            continue
        pwd2 = _ask("       Повторите пароль: ")
        if pwd1 != pwd2:
            print("[!] Пароли не совпадают.")
            continue
        break

    print("\n[4/4] Сохранение конфигурации...")

    env_path = Path(settings.data_dir) / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"BOT_TOKEN={token}",
        f"OWNER_TELEGRAM_ID={owner_id}",
        f"TIMEZONE={settings.timezone}",
        f"DATA_DIR={settings.data_dir}",
        f"DATABASE_PATH={settings.database_path}",
        f"LOG_LEVEL={settings.log_level}",
        "HOST_AGENT_URL=",
        "HOST_AGENT_TOKEN=",
        "HEALTHCHECKS_URL=",
        "",
    ]
    env_path.write_text("\n".join(lines), encoding="utf-8")
    try:
        env_path.chmod(0o600)
    except Exception:
        pass

    await init_db()
    await save_owner(owner_id, hash_password(pwd1))
    await close_db()

    print("\n" + "=" * 60)
    print("  Настройка завершена успешно.")
    print("  Запуск: docker compose up -d")
    print("=" * 60)


def main() -> None:
    asyncio.run(run_wizard())


if __name__ == "__main__":
    main()
