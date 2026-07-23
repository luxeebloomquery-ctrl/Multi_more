from aiogram import Router

from . import start
from . import announce
from . import groups
from . import schedule

router = Router()

router.include_router(start.router)
router.include_router(announce.router)
router.include_router(groups.router)
router.include_router(schedule.router)
