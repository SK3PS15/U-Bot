import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.db.db import init_db, close_db, get_owner
from app.core.scheduler import init_scheduler, shutdown_scheduler, restore_jobs
from app.core import healthchecks
from app.bot.middlewares.auth import AuthMiddleware
from app.bot.handlers import (
    start as h_start,
    menu as h_menu,
    channel_events as h_channel_events,
    channels as h_channels,
    publications as h_publications,
    scheduled as h_scheduled,
    reminders as h_reminders,
    notifications as h_notifications,
    stats as h_stats,
    settings as h_settings,
    server as h_server,
)


logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("ubot")


async def on_startup(bot: Bot) -> None:
    await init_db()
    owner = await get_owner()
    if owner is None:
        log.error("Конфигурация отсутствует. Запустите мастер настройки.")
        sys.exit(1)
    init_scheduler(bot)
    await restore_jobs()
    healthchecks.start()
    log.info("Бот запущен. Владелец: %s", owner["telegram_id"])


async def on_shutdown(bot: Bot) -> None:
    healthchecks.stop()
    shutdown_scheduler()
    await close_db()
    log.info("Бот остановлен.")


async def main() -> None:
    if not settings.is_configured:
        log.error("Не настроен .env (BOT_TOKEN / OWNER_TELEGRAM_ID).")
        sys.exit(1)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.update.middleware(AuthMiddleware())

    dp.include_router(h_start.router)
    dp.include_router(h_menu.router)
    dp.include_router(h_channel_events.router)
    dp.include_router(h_channels.router)
    dp.include_router(h_publications.router)
    dp.include_router(h_scheduled.router)
    dp.include_router(h_reminders.router)
    dp.include_router(h_notifications.router)
    dp.include_router(h_stats.router)
    dp.include_router(h_settings.router)
    dp.include_router(h_server.router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    log.info("Запуск polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
