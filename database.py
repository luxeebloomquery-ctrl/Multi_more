# database.py
# ----------------------------------------------------------------------
# SQLite persistence layer for the multi-user Announcement Bot.
#
# Every table that stores user content is keyed by user_id so that data
# for different Telegram users is always fully isolated. All read/write
# helpers require an explicit user_id where relevant -- there is no
# "global" group list anymore.
# ----------------------------------------------------------------------

import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from config import DB_PATH

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.execute("PRAGMA foreign_keys=ON")
    return _conn


def init_db() -> None:
    """Create all tables/indexes if they don't already exist."""
    with _lock:
        conn = _get_conn()
        cur = conn.cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                first_name  TEXT,
                first_seen  TEXT DEFAULT CURRENT_TIMESTAMP,
                last_seen   TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS groups (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                chat_id     INTEGER NOT NULL,
                title       TEXT NOT NULL,
                added_date  TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, chat_id)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_groups_user ON groups(user_id)")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS selected_groups (
                user_id     INTEGER NOT NULL,
                chat_id     INTEGER NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS broadcasts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                msg_type    TEXT NOT NULL,
                content     TEXT NOT NULL,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
                total       INTEGER DEFAULT 0,
                success     INTEGER DEFAULT 0,
                failed      INTEGER DEFAULT 0,
                skipped     INTEGER DEFAULT 0,
                status      TEXT DEFAULT 'done'
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_broadcasts_user ON broadcasts(user_id)")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS broadcast_failed_targets (
                broadcast_id INTEGER NOT NULL,
                chat_id      INTEGER NOT NULL,
                reason       TEXT,
                PRIMARY KEY (broadcast_id, chat_id)
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schedules (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER NOT NULL,
                msg_type         TEXT NOT NULL,
                content          TEXT NOT NULL,
                schedule_type    TEXT NOT NULL,   -- once | hourly | daily | custom
                interval_minutes INTEGER,
                next_run         TEXT NOT NULL,   -- ISO 8601 UTC
                active           INTEGER DEFAULT 1,
                created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
                last_run         TEXT,
                label            TEXT
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_schedules_user ON schedules(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_schedules_active ON schedules(active, next_run)")

        conn.commit()
    logger.info("Database initialised at %s", DB_PATH)


# ----------------------------------------------------------------------
# Users
# ----------------------------------------------------------------------
def touch_user(user_id: int, username: Optional[str], first_name: Optional[str]) -> None:
    with _lock:
        conn = _get_conn()
        conn.execute(
            """
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_seen = CURRENT_TIMESTAMP
            """,
            (user_id, username, first_name),
        )
        conn.commit()


def count_users() -> int:
    with _lock:
        conn = _get_conn()
        row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
        return row["c"] if row else 0


# ----------------------------------------------------------------------
# Groups (per-user)
# ----------------------------------------------------------------------
def add_group(user_id: int, chat_id: int, title: str) -> None:
    with _lock:
        conn = _get_conn()
        conn.execute(
            """
            INSERT INTO groups (user_id, chat_id, title) VALUES (?, ?, ?)
            ON CONFLICT(user_id, chat_id) DO UPDATE SET title = excluded.title
            """,
            (user_id, chat_id, title),
        )
        conn.commit()


def remove_group(user_id: int, chat_id: int) -> None:
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM groups WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        conn.execute(
            "DELETE FROM selected_groups WHERE user_id = ? AND chat_id = ?", (user_id, chat_id)
        )
        conn.commit()


def remove_group_for_all_owners(chat_id: int) -> None:
    """Used when the bot is removed from a group entirely -- clears it for
    whichever user(s) had it saved, not just the one who triggered the event."""
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM groups WHERE chat_id = ?", (chat_id,))
        conn.execute("DELETE FROM selected_groups WHERE chat_id = ?", (chat_id,))
        conn.commit()


def get_all_groups(user_id: int) -> List[Tuple[int, int, str]]:
    with _lock:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT id, chat_id, title FROM groups WHERE user_id = ? ORDER BY title COLLATE NOCASE",
            (user_id,),
        ).fetchall()
        return [(r["id"], r["chat_id"], r["title"]) for r in rows]


def group_exists(user_id: int, chat_id: int) -> bool:
    with _lock:
        conn = _get_conn()
        row = conn.execute(
            "SELECT 1 FROM groups WHERE user_id = ? AND chat_id = ?", (user_id, chat_id)
        ).fetchone()
        return row is not None


def owners_of_group(chat_id: int) -> List[int]:
    with _lock:
        conn = _get_conn()
        rows = conn.execute("SELECT user_id FROM groups WHERE chat_id = ?", (chat_id,)).fetchall()
        return [r["user_id"] for r in rows]


# ----------------------------------------------------------------------
# Selected groups (per-user, persisted so it survives restarts)
# ----------------------------------------------------------------------
def get_selected(user_id: int) -> set:
    with _lock:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT chat_id FROM selected_groups WHERE user_id = ?", (user_id,)
        ).fetchall()
        return {r["chat_id"] for r in rows}


def set_selected(user_id: int, chat_ids: set) -> None:
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM selected_groups WHERE user_id = ?", (user_id,))
        if chat_ids:
            conn.executemany(
                "INSERT OR IGNORE INTO selected_groups (user_id, chat_id) VALUES (?, ?)",
                [(user_id, cid) for cid in chat_ids],
            )
        conn.commit()


def toggle_selected(user_id: int, chat_id: int) -> set:
    selected = get_selected(user_id)
    if chat_id in selected:
        selected.discard(chat_id)
    else:
        selected.add(chat_id)
    set_selected(user_id, selected)
    return selected


# ----------------------------------------------------------------------
# Broadcasts (history + retry support)
# ----------------------------------------------------------------------
def create_broadcast(user_id: int, msg_type: str, content: Dict[str, Any], total: int) -> int:
    with _lock:
        conn = _get_conn()
        cur = conn.execute(
            """
            INSERT INTO broadcasts (user_id, msg_type, content, total, status)
            VALUES (?, ?, ?, ?, 'running')
            """,
            (user_id, msg_type, json.dumps(content), total),
        )
        conn.commit()
        return cur.lastrowid


def finish_broadcast(broadcast_id: int, success: int, failed: int, skipped: int) -> None:
    with _lock:
        conn = _get_conn()
        conn.execute(
            """
            UPDATE broadcasts SET success = ?, failed = ?, skipped = ?, status = 'done'
            WHERE id = ?
            """,
            (success, failed, skipped, broadcast_id),
        )
        conn.commit()


def add_failed_target(broadcast_id: int, chat_id: int, reason: str) -> None:
    with _lock:
        conn = _get_conn()
        conn.execute(
            """
            INSERT INTO broadcast_failed_targets (broadcast_id, chat_id, reason)
            VALUES (?, ?, ?)
            ON CONFLICT(broadcast_id, chat_id) DO UPDATE SET reason = excluded.reason
            """,
            (broadcast_id, chat_id, reason),
        )
        conn.commit()


def clear_failed_target(broadcast_id: int, chat_id: int) -> None:
    with _lock:
        conn = _get_conn()
        conn.execute(
            "DELETE FROM broadcast_failed_targets WHERE broadcast_id = ? AND chat_id = ?",
            (broadcast_id, chat_id),
        )
        conn.commit()


def get_failed_targets(broadcast_id: int) -> List[int]:
    with _lock:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT chat_id FROM broadcast_failed_targets WHERE broadcast_id = ?", (broadcast_id,)
        ).fetchall()
        return [r["chat_id"] for r in rows]


def get_broadcast(broadcast_id: int) -> Optional[sqlite3.Row]:
    with _lock:
        conn = _get_conn()
        return conn.execute("SELECT * FROM broadcasts WHERE id = ?", (broadcast_id,)).fetchone()


def get_broadcast_history(user_id: int, limit: int = 10) -> List[sqlite3.Row]:
    with _lock:
        conn = _get_conn()
        return conn.execute(
            "SELECT * FROM broadcasts WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()


# ----------------------------------------------------------------------
# Schedules
# ----------------------------------------------------------------------
def create_schedule(
    user_id: int,
    msg_type: str,
    content: Dict[str, Any],
    schedule_type: str,
    next_run_iso: str,
    interval_minutes: Optional[int] = None,
    label: Optional[str] = None,
) -> int:
    with _lock:
        conn = _get_conn()
        cur = conn.execute(
            """
            INSERT INTO schedules
                (user_id, msg_type, content, schedule_type, interval_minutes, next_run, label)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, msg_type, json.dumps(content), schedule_type, interval_minutes, next_run_iso, label),
        )
        conn.commit()
        return cur.lastrowid


def get_active_schedules() -> List[sqlite3.Row]:
    with _lock:
        conn = _get_conn()
        return conn.execute("SELECT * FROM schedules WHERE active = 1").fetchall()


def get_user_schedules(user_id: int) -> List[sqlite3.Row]:
    with _lock:
        conn = _get_conn()
        return conn.execute(
            "SELECT * FROM schedules WHERE user_id = ? AND active = 1 ORDER BY next_run",
            (user_id,),
        ).fetchall()


def get_schedule(schedule_id: int) -> Optional[sqlite3.Row]:
    with _lock:
        conn = _get_conn()
        return conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()


def update_schedule_next_run(schedule_id: int, next_run_iso: str) -> None:
    with _lock:
        conn = _get_conn()
        conn.execute(
            "UPDATE schedules SET next_run = ?, last_run = ? WHERE id = ?",
            (next_run_iso, time.strftime("%Y-%m-%dT%H:%M:%S"), schedule_id),
        )
        conn.commit()


def deactivate_schedule(schedule_id: int, user_id: Optional[int] = None) -> bool:
    with _lock:
        conn = _get_conn()
        if user_id is not None:
            cur = conn.execute(
                "UPDATE schedules SET active = 0 WHERE id = ? AND user_id = ?",
                (schedule_id, user_id),
            )
        else:
            cur = conn.execute("UPDATE schedules SET active = 0 WHERE id = ?", (schedule_id,))
        conn.commit()
        return cur.rowcount > 0
