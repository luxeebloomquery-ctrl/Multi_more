# utils.py
# ----------------------------------------------------------------------
# Small stateless helpers shared across handler modules.
# ----------------------------------------------------------------------

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def parse_iso(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def parse_buttons_text(text: str) -> Optional[List[List[Dict[str, str]]]]:
    """Parse user-supplied button definitions into a button-rows structure.

    Format (one button per line, `|` separates multiple buttons on the
    same row):

        Visit Website - https://example.com
        Chat | https://t.me/username - https://t.me/username

    Returns None if no valid button line was found.
    """
    rows: List[List[Dict[str, str]]] = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        row: List[Dict[str, str]] = []
        for part in line.split("|"):
            part = part.strip()
            if " - " not in part:
                continue
            label, url = part.rsplit(" - ", 1)
            label, url = label.strip(), url.strip()
            if label and URL_RE.match(url):
                row.append({"text": label, "url": url})
        if row:
            rows.append(row)
    return rows or None


def build_inline_kb(button_rows: Optional[List[List[Dict[str, str]]]]) -> Optional[InlineKeyboardMarkup]:
    if not button_rows:
        return None
    keyboard = [
        [InlineKeyboardButton(text=b["text"], url=b["url"]) for b in row]
        for row in button_rows
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def format_buttons_preview(button_rows: Optional[List[List[Dict[str, str]]]]) -> str:
    if not button_rows:
        return ""
    lines = []
    for row in button_rows:
        lines.append(" | ".join(f"[{b['text']}]" for b in row))
    return "\n🔗 <b>Buttons:</b>\n" + "\n".join(lines)


def next_run_for_frequency(freq: str, minutes: Optional[int] = None, at: Optional[datetime] = None) -> datetime:
    now = utcnow()
    if freq == "once":
        return at or now
    if freq == "hourly":
        return now + timedelta(hours=1)
    if freq == "daily":
        return now + timedelta(days=1)
    if freq == "custom":
        return now + timedelta(minutes=minutes or 60)
    raise ValueError(f"Unknown frequency: {freq}")


def advance_recurring(schedule_row) -> Optional[datetime]:
    """Given a schedules DB row, compute its next run time after firing.
    Returns None for one-shot ('once') schedules."""
    schedule_type = schedule_row["schedule_type"]
    if schedule_type == "once":
        return None
    if schedule_type == "hourly":
        return utcnow() + timedelta(hours=1)
    if schedule_type == "daily":
        return utcnow() + timedelta(days=1)
    if schedule_type == "custom":
        minutes = schedule_row["interval_minutes"] or 60
        return utcnow() + timedelta(minutes=minutes)
    return None


def human_delta(dt: datetime) -> str:
    delta = dt - utcnow()
    total_seconds = int(delta.total_seconds())
    if total_seconds <= 0:
        return "due now"
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes and not days:
        parts.append(f"{minutes}m")
    return " ".join(parts) if parts else "<1m"


def truncate(text: str, length: int = 60) -> str:
    text = text or ""
    return text if len(text) <= length else text[: length - 1] + "…"
