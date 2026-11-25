import asyncio
import logging

import aiohttp

from app.config import settings


log = logging.getLogger("ubot.healthchecks")
_task: asyncio.Task | None = None


async def _loop() -> None:
    if not settings.healthchecks_url:
        return
    while True:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(settings.healthchecks_url, timeout=10) as resp:
                    if resp.status >= 400:
                        log.warning("Healthchecks ответил %s", resp.status)
        except Exception as e:
            log.warning("Healthchecks ping ошибка: %s", e)
        await asyncio.sleep(300)


def start() -> None:
    global _task
    if settings.healthchecks_url and _task is None:
        _task = asyncio.create_task(_loop())


def stop() -> None:
    global _task
    if _task:
        _task.cancel()
        _task = None
