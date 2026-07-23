# states.py
# ----------------------------------------------------------------------
# FSM state groups shared across handler modules.
# ----------------------------------------------------------------------

from aiogram.fsm.state import State, StatesGroup


class Announcement(StatesGroup):
    choosing_type = State()
    waiting_text = State()
    waiting_photo = State()
    waiting_album = State()
    waiting_video = State()
    waiting_buttons = State()
    previewing = State()


class Schedule(StatesGroup):
    choosing_frequency = State()
    waiting_datetime = State()
    waiting_custom_minutes = State()
