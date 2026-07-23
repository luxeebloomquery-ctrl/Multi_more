# keyboards.py
# ----------------------------------------------------------------------
# All inline keyboards used by the bot are built here.
# ----------------------------------------------------------------------

from typing import List, Optional, Sequence, Set, Tuple

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 View Groups", callback_data="view_groups")
    builder.button(text="📢 Send Announcement", callback_data="ask_send")
    builder.button(text="⏰ Schedule Announcement", callback_data="schedule_new")
    builder.button(text="🗂 My Schedules", callback_data="schedule_list")
    builder.button(text="🕘 Broadcast History", callback_data="history")
    builder.adjust(1)
    return builder.as_markup()


def groups_list_kb(
    groups: List[Tuple[int, int, str]], selected: Set[int]
) -> InlineKeyboardMarkup:
    """Build the group list with a checkbox-style toggle for each group."""
    builder = InlineKeyboardBuilder()

    if not groups:
        builder.row(
            InlineKeyboardButton(text="No groups connected yet", callback_data="noop")
        )
    else:
        for _id, chat_id, title in groups:
            mark = "✅" if chat_id in selected else "⬜"
            label = title if len(title) <= 35 else title[:32] + "..."
            builder.row(
                InlineKeyboardButton(
                    text=f"{mark} {label}", callback_data=f"toggle:{chat_id}"
                )
            )

    builder.row(
        InlineKeyboardButton(text="☑️ Select All", callback_data="select_all"),
        InlineKeyboardButton(text="⬛ Unselect All", callback_data="unselect_all"),
    )
    builder.row(
        InlineKeyboardButton(text="📢 Send Announcement", callback_data="ask_send")
    )
    builder.row(InlineKeyboardButton(text="🔙 Back", callback_data="back_main"))
    return builder.as_markup()


def message_type_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Text Message", callback_data="type_text")
    builder.button(text="🖼 Photo + Caption", callback_data="type_photo")
    builder.button(text="🖼🖼 Album (up to 9 photos)", callback_data="type_album")
    builder.button(text="🎬 Video (max 20s)", callback_data="type_video")
    builder.button(text="🔙 Cancel", callback_data="back_main")
    builder.adjust(1)
    return builder.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Cancel", callback_data="back_main")
    return builder.as_markup()


def album_done_kb(count: int, max_count: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"✅ Done ({count}/{max_count} photos)", callback_data="album_done")
    builder.button(text="❌ Cancel", callback_data="back_main")
    builder.adjust(1)
    return builder.as_markup()


def buttons_choice_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔗 Add Inline Buttons", callback_data="buttons_add")
    builder.button(text="⏭ Skip", callback_data="buttons_skip")
    builder.button(text="❌ Cancel", callback_data="back_main")
    builder.adjust(1)
    return builder.as_markup()


def confirm_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Confirm & Send", callback_data="confirm_send")
    builder.button(text="❌ Cancel", callback_data="back_main")
    builder.adjust(1)
    return builder.as_markup()


def confirm_or_schedule_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Confirm & Send Now", callback_data="confirm_send")
    builder.button(text="⏰ Schedule Instead", callback_data="schedule_from_preview")
    builder.button(text="❌ Cancel", callback_data="back_main")
    builder.adjust(1)
    return builder.as_markup()


def retry_failed_kb(broadcast_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔁 Retry Failed", callback_data=f"retry:{broadcast_id}")
    builder.button(text="🔙 Main Menu", callback_data="back_main")
    builder.adjust(1)
    return builder.as_markup()


def schedule_frequency_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="1️⃣ Once", callback_data="freq_once")
    builder.button(text="🕐 Every Hour", callback_data="freq_hourly")
    builder.button(text="📅 Every Day", callback_data="freq_daily")
    builder.button(text="⏱ Custom Minutes", callback_data="freq_custom")
    builder.button(text="❌ Cancel", callback_data="back_main")
    builder.adjust(1)
    return builder.as_markup()


def schedule_list_kb(schedules: Sequence) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if not schedules:
        builder.row(InlineKeyboardButton(text="No active schedules", callback_data="noop"))
    else:
        for s in schedules:
            label = s["label"] or f"{s['msg_type']} ({s['schedule_type']})"
            builder.row(
                InlineKeyboardButton(
                    text=f"🗑 Cancel: {label}", callback_data=f"schedule_cancel:{s['id']}"
                )
            )
    builder.row(InlineKeyboardButton(text="🔙 Back", callback_data="back_main"))
    return builder.as_markup()


def history_kb(rows: Sequence) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for r in rows:
        label = f"#{r['id']} {r['msg_type']} ✅{r['success']} ❌{r['failed']}"
        if r["failed"]:
            builder.row(InlineKeyboardButton(text=label + " 🔁 Retry", callback_data=f"retry:{r['id']}"))
        else:
            builder.row(InlineKeyboardButton(text=label, callback_data="noop"))
    builder.row(InlineKeyboardButton(text="🔙 Back", callback_data="back_main"))
    return builder.as_markup()
