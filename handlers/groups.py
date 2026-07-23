# handlers/groups.py
# ----------------------------------------------------------------------
# View Groups / Select / Select All / Unselect All.
# Selection is persisted per-user in the database (survives restarts).
# ----------------------------------------------------------------------

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

import database as db
from keyboards import groups_list_kb

router = Router(name="groups")


@router.callback_query(F.data == "view_groups")
async def cb_view_groups(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    groups = db.get_all_groups(user_id)
    selected = db.get_selected(user_id)
    text = (
        f"📋 <b>Your Connected Groups</b> ({len(groups)})\n\n"
        "Tap a group to select/unselect it for the next announcement.\n"
        "Only groups where you added this bot as admin appear here."
    )
    await callback.message.edit_text(text, reply_markup=groups_list_kb(groups, selected))
    await callback.answer()


@router.callback_query(F.data.startswith("toggle:"))
async def cb_toggle_group(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    chat_id = int(callback.data.split(":", 1)[1])
    selected = db.toggle_selected(user_id, chat_id)

    groups = db.get_all_groups(user_id)
    try:
        await callback.message.edit_reply_markup(reply_markup=groups_list_kb(groups, selected))
    except TelegramBadRequest:
        pass  # message not modified, safe to ignore
    await callback.answer()


@router.callback_query(F.data == "select_all")
async def cb_select_all(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    groups = db.get_all_groups(user_id)
    selected = {chat_id for _id, chat_id, _title in groups}
    db.set_selected(user_id, selected)
    try:
        await callback.message.edit_reply_markup(reply_markup=groups_list_kb(groups, selected))
    except TelegramBadRequest:
        pass
    await callback.answer("All groups selected ✅")


@router.callback_query(F.data == "unselect_all")
async def cb_unselect_all(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    groups = db.get_all_groups(user_id)
    db.set_selected(user_id, set())
    try:
        await callback.message.edit_reply_markup(reply_markup=groups_list_kb(groups, set()))
    except TelegramBadRequest:
        pass
    await callback.answer("Selection cleared")
  
