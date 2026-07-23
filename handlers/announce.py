# handlers/announce.py
# ----------------------------------------------------------------------
# The full announcement composition flow:
#   choose type -> collect content -> optional inline buttons -> preview
#   -> confirm & send now (or hand off to handlers/schedule.py)
#
# Also owns the Retry Failed button and Broadcast History screen, since
# both operate on the same broadcast records produced here.
# ----------------------------------------------------------------------

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import broadcast
import database as db
from config import MAX_ALBUM_PHOTOS, MAX_VIDEO_SECONDS
from keyboards import (
    album_done_kb,
    buttons_choice_kb,
    cancel_kb,
    confirm_or_schedule_kb,
    history_kb,
    main_menu_kb,
    message_type_kb,
    retry_failed_kb,
)
from states import Announcement
from utils import build_inline_kb, format_buttons_preview, parse_buttons_text, truncate

logger = logging.getLogger(__name__)
router = Router(name="announce")


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------
@router.callback_query(F.data == "ask_send")
async def cb_ask_send(callback: CallbackQuery, state: FSMContext) -> None:
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
        f"📢 <b>Send Announcement</b>\n\n"
        f"Selected groups: <b>{len(selected)}</b>\n\n"
        "Choose the type of message you want to send:",
        reply_markup=message_type_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "type_text")
async def cb_type_text(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Announcement.waiting_text)
    await callback.message.edit_text(
        "📝 Send me the <b>text message</b> you want to broadcast.\n\n"
        "Formatting (bold, italic, links, etc.) is preserved automatically.",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "type_photo")
async def cb_type_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Announcement.waiting_photo)
    await callback.message.edit_text(
        "🖼 Send me the <b>photo</b> (with an optional caption) you want to broadcast.",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "type_album")
async def cb_type_album(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Announcement.waiting_album)
    await state.update_data(album=[], caption="")
    await callback.message.edit_text(
        f"🖼🖼 Send up to <b>{MAX_ALBUM_PHOTOS} photos</b>, one at a time. "
        "The caption on any of them will be used as the album caption.\n\n"
        "Tap <b>Done</b> once you've sent all your photos.",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "type_video")
async def cb_type_video(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Announcement.waiting_video)
    await callback.message.edit_text(
        f"🎬 Send me a <b>video (max {MAX_VIDEO_SECONDS} seconds)</b> with an optional caption.",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


# ----------------------------------------------------------------------
# Content collection
# ----------------------------------------------------------------------
@router.message(Announcement.waiting_text, F.text)
async def receive_text(message: Message, state: FSMContext) -> None:
    await state.update_data(msg_type="text", text=message.html_text)
    await ask_buttons(message, state)


@router.message(Announcement.waiting_text)
async def receive_text_invalid(message: Message) -> None:
    await message.answer("⚠️ Please send a text message, or press Cancel below.", reply_markup=cancel_kb())


@router.message(Announcement.waiting_photo, F.photo)
async def receive_photo(message: Message, state: FSMContext) -> None:
    photo_id = message.photo[-1].file_id
    caption = message.html_text if message.caption else ""
    await state.update_data(msg_type="photo", photo_id=photo_id, caption=caption)
    await ask_buttons(message, state)


@router.message(Announcement.waiting_photo)
async def receive_photo_invalid(message: Message) -> None:
    await message.answer("⚠️ Please send a photo, or press Cancel below.", reply_markup=cancel_kb())


@router.message(Announcement.waiting_album, F.photo)
async def receive_album_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    album = list(data.get("album", []))
    caption = data.get("caption", "")

    if len(album) >= MAX_ALBUM_PHOTOS:
        await message.answer(
            f"⚠️ Maximum of {MAX_ALBUM_PHOTOS} photos reached. Tap Done to continue.",
            reply_markup=album_done_kb(len(album), MAX_ALBUM_PHOTOS),
        )
        return

    album.append(message.photo[-1].file_id)
    if not caption and message.caption:
        caption = message.html_text

    await state.update_data(album=album, caption=caption)
    await message.answer(
        f"✅ Photo {len(album)}/{MAX_ALBUM_PHOTOS} added.",
        reply_markup=album_done_kb(len(album), MAX_ALBUM_PHOTOS),
    )


@router.message(Announcement.waiting_album)
async def receive_album_invalid(message: Message) -> None:
    await message.answer("⚠️ Please send a photo, or tap Done / Cancel below.")


@router.callback_query(Announcement.waiting_album, F.data == "album_done")
async def cb_album_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    album = data.get("album", [])
    if not album:
        await callback.answer("⚠️ Send at least 1 photo first.", show_alert=True)
        return
    await state.update_data(msg_type="album")
    await callback.answer()
    await ask_buttons(callback.message, state)


@router.message(Announcement.waiting_video, F.video)
async def receive_video(message: Message, state: FSMContext) -> None:
    duration = message.video.duration or 0
    if duration > MAX_VIDEO_SECONDS:
        await message.answer(
            f"⚠️ That video is {duration}s long. Please send one that is "
            f"{MAX_VIDEO_SECONDS} seconds or shorter.",
            reply_markup=cancel_kb(),
        )
        return

    caption = message.html_text if message.caption else ""
    await state.update_data(msg_type="video", video_id=message.video.file_id, caption=caption)
    await ask_buttons(message, state)


@router.message(Announcement.waiting_video)
async def receive_video_invalid(message: Message) -> None:
    await message.answer("⚠️ Please send a video, or press Cancel below.", reply_markup=cancel_kb())


# ----------------------------------------------------------------------
# Inline buttons
# ----------------------------------------------------------------------
async def ask_buttons(message: Message, state: FSMContext) -> None:
    await message.answer(
        "🔗 Would you like to add <b>inline buttons</b> (e.g. a website link) to this message?",
        reply_markup=buttons_choice_kb(),
    )


@router.callback_query(F.data == "buttons_add")
async def cb_buttons_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Announcement.waiting_buttons)
    await callback.message.edit_text(
        "Send your button(s), one per line, in this format:\n\n"
        "<code>Button Text - https://example.com</code>\n\n"
        "Put multiple buttons on the same row separated by <code>|</code>:\n"
        "<code>Site - https://a.com | Chat - https://t.me/x</code>",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "buttons_skip")
async def cb_buttons_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(buttons=None)
    await callback.answer()
    await show_preview(callback.message, state, callback.from_user.id)


@router.message(Announcement.waiting_buttons, F.text)
async def receive_buttons(message: Message, state: FSMContext) -> None:
    rows = parse_buttons_text(message.text)
    if not rows:
        await message.answer(
            "⚠️ I couldn't find any valid buttons in that. Use the format:\n"
            "<code>Button Text - https://example.com</code>\n\nTry again, or press Cancel.",
            reply_markup=cancel_kb(),
        )
        return
    await state.update_data(buttons=rows)
    await show_preview(message, state, message.from_user.id)


# ----------------------------------------------------------------------
# Preview
# ----------------------------------------------------------------------
async def show_preview(message: Message, state: FSMContext, user_id: int) -> None:
    await state.set_state(Announcement.previewing)
    data = await state.get_data()
    selected = db.get_selected(user_id)
    kb = build_inline_kb(data.get("buttons"))
    bot = message.bot

    msg_type = data.get("msg_type")
    if msg_type == "text":
        await bot.send_message(chat_id=message.chat.id, text=data["text"], reply_markup=kb)
    elif msg_type == "photo":
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=data["photo_id"],
            caption=data.get("caption") or None,
            reply_markup=kb,
        )
    elif msg_type == "album":
        from aiogram.types import InputMediaPhoto

        media = [
            InputMediaPhoto(media=fid, caption=data.get("caption") if i == 0 else None)
            for i, fid in enumerate(data["album"])
        ]
        await bot.send_media_group(chat_id=message.chat.id, media=media)
        if kb:
            await bot.send_message(chat_id=message.chat.id, text="🔗 Links (sent as follow-up)", reply_markup=kb)
    elif msg_type == "video":
        await bot.send_video(
            chat_id=message.chat.id,
            video=data["video_id"],
            caption=data.get("caption") or None,
            reply_markup=kb,
        )

    await message.answer(
        f"👀 <b>Preview above</b>\n\n"
        f"This will be sent to <b>{len(selected)}</b> group(s).\n"
        "Send now, schedule it for later, or cancel.",
        reply_markup=confirm_or_schedule_kb(),
    )


# ----------------------------------------------------------------------
# Confirm & send
# ----------------------------------------------------------------------
@router.callback_query(F.data == "confirm_send")
async def cb_confirm_send(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    data = await state.get_data()
    selected = db.get_selected(user_id)

    if not selected or "msg_type" not in data:
        await callback.answer("Nothing to send.", show_alert=True)
        return

    await callback.answer()
    progress_msg = await callback.message.answer("⏳ <b>Sending...</b>\n\n0/{}".format(len(selected)))

    broadcast_id = await broadcast.run_broadcast(
        callback.bot, user_id, list(selected), data, progress_message=progress_msg
    )

    record = db.get_broadcast(broadcast_id)
    await state.clear()

    text = broadcast.result_message_text(record["success"], record["failed"], record["skipped"], record["total"])
    kb = retry_failed_kb(broadcast_id) if record["failed"] else main_menu_kb()
    await progress_msg.edit_text(text, reply_markup=kb)


@router.callback_query(F.data.startswith("retry:"))
async def cb_retry_failed(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    broadcast_id = int(callback.data.split(":", 1)[1])

    await callback.answer("Retrying failed sends...")
    result = await broadcast.retry_failed(callback.bot, user_id, broadcast_id)

    if result is None:
        await callback.message.answer("⚠️ Couldn't find that broadcast.", reply_markup=main_menu_kb())
        return
    if result["total"] == 0:
        await callback.message.answer("✅ Nothing left to retry.", reply_markup=main_menu_kb())
        return

    text = (
        "🔁 <b>Retry Complete</b>\n\n"
        f"✅ Success: <b>{result['success']}</b>\n"
        f"❌ Still Failed: <b>{result['failed']}</b>\n"
        f"⚠️ Skipped: <b>{result['skipped']}</b>"
    )
    kb = retry_failed_kb(broadcast_id) if result["failed"] else main_menu_kb()
    await callback.message.answer(text, reply_markup=kb)


# ----------------------------------------------------------------------
# History
# ----------------------------------------------------------------------
@router.callback_query(F.data == "history")
async def cb_history(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    rows = db.get_broadcast_history(user_id, limit=10)
    if not rows:
        await callback.message.edit_text(
            "🕘 <b>Broadcast History</b>\n\nNo broadcasts sent yet.", reply_markup=main_menu_kb()
        )
        await callback.answer()
        return

    lines = ["🕘 <b>Broadcast History</b> (last 10)\n"]
    for r in rows:
        lines.append(
            f"#{r['id']} • {r['msg_type']} • {r['created_at']} • "
            f"✅{r['success']} ❌{r['failed']} ⚠️{r['skipped']}"
        )
    await callback.message.edit_text("\n".join(lines), reply_markup=history_kb(rows))
    await callback.answer()
  
