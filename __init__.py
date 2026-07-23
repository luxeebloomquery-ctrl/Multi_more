# handlers/__init__.py
# ----------------------------------------------------------------------
# Aggregates all feature routers into a single router that main.py
# includes into the Dispatcher.
# ----------------------------------------------------------------------

from aiogram import Router

from . import announce, groups, schedule, start

router = Router(name="root")
router.include_router(start.router)
router.include_router(groups.router)
router.include_router(announce.router)
router.include_router(schedule.router)

__all__ = ["router"]
