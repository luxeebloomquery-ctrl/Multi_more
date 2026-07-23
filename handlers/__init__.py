from aiogram import Router

from . import start, announce, broadcast, groups, schedule

router = Router()

router.include_router(start.router)
router.include_router(announce.router)
router.include_router(broadcast.router)
router.include_router(groups.router)
router.include_router(schedule.router)
