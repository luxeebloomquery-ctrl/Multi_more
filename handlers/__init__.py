from aiogram import Router

from .start import router as start_router
from .announce import router as announce_router
from .broadcast import router as broadcast_router
from .groups import router as groups_router
from .schedule import router as schedule_router

router = Router()

router.include_router(start_router)
router.include_router(announce_router)
router.include_router(broadcast_router)
router.include_router(groups_router)
router.include_router(schedule_router)
