# config.py
# ----------------------------------------------------------------------
# Configuration for the Announcement Bot.
#
# The bot token is read from the BOT_TOKEN environment variable (or a
# .env file, see README). Do NOT hardcode real tokens in this file --
# if you ever paste a real token into source control or share the code,
# revoke it immediately via @BotFather (/revoke) and issue a new one.
#
# ADMIN_IDS has been removed on purpose: this bot is now a PUBLIC,
# MULTI-USER bot. Every Telegram user who starts a chat with it gets
# their own fully isolated groups / selections / broadcast history /
# schedules. See OWNER_IDS below if you want a couple of maintenance-
# only commands reserved for yourself (optional, not required).
# ----------------------------------------------------------------------

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # python-dotenv is optional; if it's not installed we just rely on
    # real environment variables (e.g. set by Docker / systemd).
    pass

# --- Required ---------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# --- Optional -----------------------------------------------------------
# Comma-separated Telegram user IDs that get access to a couple of
# owner-only maintenance commands (/stats_global, /broadcast_status).
# This is NOT required for normal use -- every user can already use the
# bot fully without being listed here. Leave empty to disable.
OWNER_IDS = [
    int(x) for x in os.getenv("OWNER_IDS", "").split(",") if x.strip().isdigit()
]

# Path to the SQLite database file.
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "data", "bot.db"))

# --- Content limits -----------------------------------------------------
MAX_ALBUM_PHOTOS = 9          # Telegram media group hard limit is 10; we cap at 9 per spec
MAX_VIDEO_SECONDS = 20        # Max allowed video duration for announcements
MAX_BUTTON_ROWS = 8           # Safety cap on number of inline button rows per message

# --- Broadcast tuning -----------------------------------------------------
BROADCAST_DELAY_SECONDS = float(os.getenv("BROADCAST_DELAY_SECONDS", "0.05"))
PROGRESS_UPDATE_EVERY = int(os.getenv("PROGRESS_UPDATE_EVERY", "5"))   # edit progress msg every N sends
PROGRESS_UPDATE_MIN_INTERVAL = 2.0  # seconds, avoid hitting edit-message flood limits
MAX_SEND_RETRIES = 3

# --- Scheduler tuning -----------------------------------------------------
SCHEDULER_POLL_SECONDS = 15   # how often the internal scheduler wakes up to check due jobs

# --- Logging -----------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("LOG_FILE", os.path.join(os.path.dirname(__file__), "data", "bot.log"))

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set. Create a .env file (see .env.example) or export "
        "the BOT_TOKEN environment variable before starting the bot."
    )
