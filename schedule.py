# handlers/schedule.py
# ----------------------------------------------------------------------
# Scheduling: once / every hour / every day / custom minutes, plus
# listing and cancelling a user's own schedules. Entry into content
# composition is shared with handlers/announce.py (same states) --
# this module only handles the "what frequency, and finalize" part,
# reached via the "Schedule Instead" button on the preview screen.
# ----------------------------------------------------------------------

import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from keyboards import (
    cancel_kb,
    main_menu_kb,
    message_type_kb,
    schedule_frequency_kb,
    schedule_list_kb,
)
from states import Schedule
from utils import human_delta, iso, next_run_for_frequency, truncate, utcnow

logger = logging.getLogger(__name__)
router = Router(name="schedule")


@router.callback_query(F.data == "schedule_new")
async def cb_schedule_new(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    selected = db.get_selected(user_id)
    if not selected:
        await callback.answer(
            "⚠️ No groups selected. Go to 'View Groups' and select at least one.",
            show_alert=True,
        )
        return

    await state.clear()
    await callback.message.edit_text(
        f"⏰ <b>Schedule Announcement</b>\n\n"
        f"Selected groups: <b>{len(selected)}</b>\n\n"
        "Choose the type of message you want to schedule:",
        reply_markup=message_type_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "schedule_from_preview")
async def cb_schedule_from_preview(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if "msg_type" not in data:
        await callback.answer("Nothing to schedule.", show_alert=True)
        return
    await state.set_state(Schedule.choosing_frequency)
    await callback.message.answer(
        "⏰ <b>Choose a schedule</b>", reply_markup=schedule_frequency_kb()
    )
    await callback.answer()


@router.callback_query(Schedule.choosing_frequency, F.data == "freq_once")
async def cb_freq_once(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Schedule.waiting_datetime)
    await callback.message.edit_text(
        "🗓 Send the date & time (UTC) to send at, in this format:\n\n"
        "<code>YYYY-MM-DD HH:MM</code>\n\nExample: <code>2026-08-01 09:00</code>",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.callback_query(Schedule.choosing_frequency, F.data == "freq_hourly")
async def cb_freq_hourly(callback: CallbackQuery, state: FSMContext) -> None:
    await finalize_schedule(callback.message, state, callback.from_user.id, "hourly")
    await callback.answer()


@router.callback_query(Schedule.choosing_frequency, F.data == "freq_daily")
async def cb_freq_daily(callback: CallbackQuery, state: FSMContext) -> None:
    await finalize_schedule(callback.message, state, callback.from_user.id, "daily")
    await callback.answer()


@router.callback_query(Schedule.choosing_frequency, F.data == "freq_custom")
async def cb_freq_custom(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Schedule.waiting_custom_minutes)
    await callback.message.edit_text(
        "⏱ Send the number of <b>minutes</b> between each send (e.g. <code>90</code>).",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(Schedule.waiting_datetime, F.text)
async def receive_datetime(message: Message, state: FSMContext) -> None:
    try:
        dt = datetime.strptime(message.text.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        await message.answer(
            "⚠️ Invalid format. Please use <code>YYYY-MM-DD HH:MM</code> (UTC), e.g. "
            "<code>2026-08-01 09:00</code>",
            reply_markup=cancel_kb(),
        )
        return
    if dt <= utcnow():
        await message.answer("⚠️ That time is in the past. Please send a future date/time.", reply_markup=cancel_kb())
        return

    await finalize_schedule(message, state, message.from_user.id, "once", at=dt)


@router.message(Schedule.waiting_custom_minutes, F.text)
async def receive_custom_minutes(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("⚠️ Please send a positive whole number of minutes.", reply_markup=cancel_kb())
        return

    await finalize_schedule(message, state, message.from_user.id, "custom", minutes=int(text))


async def finalize_schedule(
    message: Message,
    state: FSMContext,
    user_id: int,
    schedule_type: str,
    minutes: int | None = None,
    at: datetime | None = None,
) -> None:
    data = await state.get_data()
    selected = db.get_selected(user_id)

    content = {
        "msg_type": data.get("msg_type"),
        "text": data.get("text"),
        "photo_id": data.get("photo_id"),
        "album": data.get("album"),
        "video_id": data.get("video_id"),
        "caption": data.get("caption"),
        "buttons": data.get("buttons"),
        "targets": list(selected),
    }

    next_run = next_run_for_frequency(schedule_type, minutes=minutes, at=at)
    label = f"{content['msg_type']} → {len(selected)} group(s)"

    schedule_id = db.create_schedule(
        user_id=user_id,
        msg_type=content["msg_type"],
        content=content,
        schedule_type=schedule_type,
        next_run_iso=iso(next_run),
        interval_minutes=minutes,
        label=truncate(label, 60),
    )

    await state.clear()
    await message.answer(
        f"✅ <b>Schedule Created</b> (#{schedule_id})\n\n"
        f"Type: <b>{schedule_type}</b>\n"
        f"Targets: <b>{len(selected)}</b> group(s)\n"
        f"Next send: in <b>{human_delta(next_run)}</b> ({next_run.strftime('%Y-%m-%d %H:%M UTC')})",
        reply_markup=main_menu_kb(),
    )


# ----------------------------------------------------------------------
# List / cancel
# ----------------------------------------------------------------------
@router.callback_query(F.data == "schedule_list")
async def cb_schedule_list(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    schedules = db.get_user_schedules(user_id)

    if not schedules:
        text = "🗂 <b>My Schedules</b>\n\nYou have no active schedules."
    else:
        lines = ["🗂 <b>My Schedules</b>\n"]
        for s in schedules:
            from utils import parse_iso

            next_run = parse_iso(s["next_run"])
            lines.append(
                f"#{s['id']} • {s['msg_type']} • {s['schedule_type']} • "
                f"next in {human_delta(next_run)}"
            )
        text = "\n".join(lines)

    await callback.message.edit_text(text, reply_markup=schedule_list_kb(schedules))
    await callback.answer()


@router.callback_query(F.data.startswith("schedule_cancel:"))
async def cb_schedule_cancel(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    schedule_id = int(callback.data.split(":", 1)[1])
    ok = db.deactivate_schedule(schedule_id, user_id=user_id)
    await callback.answer("Schedule cancelled ✅" if ok else "Not found.", show_alert=not ok)

    schedules = db.get_user_schedules(user_id)
    lines = ["🗂 <b>My Schedules</b>\n"] if schedules else ["🗂 <b>My Schedules</b>\n\nYou have no active schedules."]
    for s in schedules:
        from utils import parse_iso

        next_run = parse_iso(s["next_run"])
        lines.append(f"#{s['id']} • {s['msg_type']} • {s['schedule_type']} • next in {human_delta(next_run)}")
    try:
        await callback.message.edit_text("\n".join(lines), reply_markup=schedule_list_kb(schedules))
    except Exception:  # noqa: BLE001
        pass
