# main.py
# ----------------------------------------------------------------------
# Telegram Announcement Bot - aiogram 3.x, public multi-user edition.
#
# Features:
#   - Public, multi-user: every Telegram user gets fully isolated
#     groups / selections / broadcast history / schedules
#   - Text, single photo, up to 9-photo album, and video (<=20s)
#     announcements, all with optional inline URL buttons
#   - HTML/Markdown formatting preserved automatically from user input
#   - Preview before sending
#   - Live sending progress + success/failed/skipped report
#   - Retry Failed button
#   - Scheduling: once / hourly / daily / custom minutes, with list
#     and cancel, fully restored from SQLite after a restart/reboot
#   - FloodWait handling, per-chat retries, SQLite (WAL) persistence
# ----------------------------------------------------------------------

import asyncio
import logging
import logging.handlers
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import database as db
from config import BOT_TOKEN, LOG_FILE, LOG_LEVEL
from handlers import router
from scheduler import Scheduler


def setup_logging() -> None:
    os.makedirs(os.path.dirname(LOG_FILE) or ".", exist_ok=True)
    handlers = [
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        ),
    ]
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=handlers,
    )
    # aiogram's own event-loop noise at INFO is fine, but silence the
    # very chatty asyncio/aiohttp debug logs unless explicitly requested.
    if LOG_LEVEL != "DEBUG":
        logging.getLogger("aiohttp").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    db.init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    scheduler = Scheduler(bot)

    await bot.delete_webhook(drop_pending_updates=True)
    scheduler.start()  # restores + resumes all active schedules from SQLite

    logger.info("Bot started. Polling for updates...")
    try:
        await dp.start_polling(bot)
    finally:
        await scheduler.stop()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
