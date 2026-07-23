# broadcast.py
# ----------------------------------------------------------------------
# Core "send this content to a list of chat_ids" logic, shared by the
# manual broadcast flow, the Retry Failed button, and the scheduler.
# Handles FloodWait, per-chat retries, progress reporting, and DB
# bookkeeping (broadcast history + failed targets for retry).
# ----------------------------------------------------------------------

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InputMediaPhoto, Message

import database as db
from config import (
    BROADCAST_DELAY_SECONDS,
    MAX_SEND_RETRIES,
    PROGRESS_UPDATE_EVERY,
    PROGRESS_UPDATE_MIN_INTERVAL,
)
from utils import build_inline_kb

logger = logging.getLogger(__name__)


async def send_content_to_chat(bot: Bot, chat_id: int, data: Dict[str, Any]) -> Tuple[bool, str]:
    """Send one piece of announcement content to a single chat.
    Returns (success, reason). Automatically waits out FloodWait."""
    msg_type = data.get("msg_type")
    kb = build_inline_kb(data.get("buttons"))

    for attempt in range(MAX_SEND_RETRIES):
        try:
            if msg_type == "text":
                await bot.send_message(chat_id=chat_id, text=data["text"], reply_markup=kb)
            elif msg_type == "photo":
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=data["photo_id"],
                    caption=data.get("caption") or None,
                    reply_markup=kb,
                )
            elif msg_type == "album":
                media = [
                    InputMediaPhoto(media=fid, caption=data.get("caption") if i == 0 else None)
                    for i, fid in enumerate(data["album"])
                ]
                await bot.send_media_group(chat_id=chat_id, media=media)
                # Telegram media groups cannot carry an inline keyboard, so if
                # buttons were attached we send them as a small follow-up.
                if kb:
                    await bot.send_message(chat_id=chat_id, text="🔗 Links", reply_markup=kb)
            elif msg_type == "video":
                await bot.send_video(
                    chat_id=chat_id,
                    video=data["video_id"],
                    caption=data.get("caption") or None,
                    reply_markup=kb,
                )
            else:
                return False, f"unknown msg_type: {msg_type}"
            return True, "ok"

        except TelegramRetryAfter as e:
            logger.warning("FloodWait on %s: sleeping %s sec", chat_id, e.retry_after)
            await asyncio.sleep(e.retry_after + 1)
            continue
        except TelegramForbiddenError as e:
            logger.info("Bot blocked/kicked in %s: %s", chat_id, e)
            return False, "forbidden"
        except TelegramBadRequest as e:
            logger.warning("Bad request sending to %s: %s", chat_id, e)
            return False, f"bad_request: {e}"
        except Exception as e:  # noqa: BLE001 - one bad chat must not kill the whole run
            logger.warning("Unexpected error sending to %s: %s", chat_id, e)
            return False, f"error: {e}"

    return False, "flood_wait_exhausted"


def _progress_text(sent: int, total: int) -> str:
    return f"⏳ <b>Sending...</b>\n\n{sent}/{total}"


def _result_text(success: int, failed: int, skipped: int, total: int) -> str:
    return (
        "📢 <b>Broadcast Complete</b>\n\n"
        f"✅ Success: <b>{success}</b>\n"
        f"❌ Failed: <b>{failed}</b>\n"
        f"⚠️ Skipped: <b>{skipped}</b>\n"
        f"📊 Total: <b>{total}</b>"
    )


async def run_broadcast(
    bot: Bot,
    user_id: int,
    chat_ids: List[int],
    data: Dict[str, Any],
    progress_message: Optional[Message] = None,
) -> int:
    """Send `data` to every chat_id in chat_ids, updating progress_message
    (if given) as it goes. Persists a broadcast record + failed targets.
    Returns the broadcast_id (for the Retry Failed button)."""
    total = len(chat_ids)
    broadcast_id = db.create_broadcast(user_id, data.get("msg_type", "text"), data, total)

    success = failed = skipped = 0
    last_edit = 0.0

    for i, chat_id in enumerate(chat_ids, start=1):
        if not db.group_exists(user_id, chat_id):
            skipped += 1
            continue

        ok, reason = await send_content_to_chat(bot, chat_id, data)
        if ok:
            success += 1
            db.clear_failed_target(broadcast_id, chat_id)
        else:
            failed += 1
            db.add_failed_target(broadcast_id, chat_id, reason)

        now = time.monotonic()
        if progress_message and (
            i % PROGRESS_UPDATE_EVERY == 0
            or i == total
            or now - last_edit >= PROGRESS_UPDATE_MIN_INTERVAL
        ):
            try:
                await progress_message.edit_text(_progress_text(i, total))
                last_edit = now
            except TelegramBadRequest:
                pass

        await asyncio.sleep(BROADCAST_DELAY_SECONDS)

    db.finish_broadcast(broadcast_id, success, failed, skipped)
    return broadcast_id


async def retry_failed(bot: Bot, user_id: int, broadcast_id: int) -> Optional[Dict[str, int]]:
    """Resend a previous broadcast's content only to chats that failed."""
    record = db.get_broadcast(broadcast_id)
    if record is None or record["user_id"] != user_id:
        return None

    import json

    data = json.loads(record["content"])
    failed_targets = db.get_failed_targets(broadcast_id)
    if not failed_targets:
        return {"success": 0, "failed": 0, "skipped": 0, "total": 0}

    success = failed = skipped = 0
    for chat_id in failed_targets:
        if not db.group_exists(user_id, chat_id):
            skipped += 1
            db.clear_failed_target(broadcast_id, chat_id)
            continue
        ok, reason = await send_content_to_chat(bot, chat_id, data)
        if ok:
            success += 1
            db.clear_failed_target(broadcast_id, chat_id)
        else:
            failed += 1
            db.add_failed_target(broadcast_id, chat_id, reason)
        await asyncio.sleep(BROADCAST_DELAY_SECONDS)

    # Update the aggregate counts on the original broadcast record.
    new_success = record["success"] + success
    new_failed = record["failed"] - success  # failed ones that succeeded are no longer failed
    db.finish_broadcast(broadcast_id, new_success, max(new_failed, failed), record["skipped"] + skipped)

    return {"success": success, "failed": failed, "skipped": skipped, "total": len(failed_targets)}


def result_message_text(success: int, failed: int, skipped: int, total: int) -> str:
    return _result_text(success, failed, skipped, total)
  
