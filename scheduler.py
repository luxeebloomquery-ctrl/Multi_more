# scheduler.py
# ----------------------------------------------------------------------
# A small dependency-free scheduler. Schedules live in the `schedules`
# SQLite table (see database.py) so that on every startup -- including
# after a VPS reboot -- we simply re-read all active schedules and keep
# polling; nothing is kept only in memory.
#
# We deliberately avoid an external scheduler library: the requirement
# set (once / hourly / daily / custom-minutes, with cancel + list) is
# simple enough that a polling loop backed by the DB is easier to
# reason about and fully restart-safe by construction.
# ----------------------------------------------------------------------

import asyncio
import json
import logging

from aiogram import Bot

import database as db
from broadcast import run_broadcast
from config import SCHEDULER_POLL_SECONDS
from utils import advance_recurring, iso, parse_iso, utcnow

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        if self._task is None:
            self._running = True
            self._task = asyncio.create_task(self._loop())
            logger.info("Scheduler started (poll every %ss)", SCHEDULER_POLL_SECONDS)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except Exception:  # noqa: BLE001 - the loop must never die
                logger.exception("Scheduler tick failed")
            await asyncio.sleep(SCHEDULER_POLL_SECONDS)

    async def _tick(self) -> None:
        now = utcnow()
        for row in db.get_active_schedules():
            try:
                due = parse_iso(row["next_run"]) <= now
            except ValueError:
                logger.warning("Bad next_run for schedule %s, deactivating", row["id"])
                db.deactivate_schedule(row["id"])
                continue

            if not due:
                continue

            await self._fire(row)

    async def _fire(self, row) -> None:
        content = json.loads(row["content"])
        targets = content.get("targets") or []
        user_id = row["user_id"]

        logger.info(
            "Firing schedule #%s for user %s (%s targets)", row["id"], user_id, len(targets)
        )

        if targets:
            try:
                await run_broadcast(self.bot, user_id, targets, content)
            except Exception:
                logger.exception("Scheduled broadcast #%s failed", row["id"])
        else:
            logger.info("Schedule #%s has no target groups, skipping send", row["id"])

        next_run = advance_recurring(row)
        if next_run is None:
            db.deactivate_schedule(row["id"])
        else:
            db.update_schedule_next_run(row["id"], iso(next_run))
