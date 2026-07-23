# Telegram Announcement Bot (Public Multi-User Edition)

A production-ready Telegram bot (aiogram 3.x + SQLite) that lets **any**
Telegram user broadcast text, photos, albums, or videos to all the groups
they manage -- with scheduling, inline buttons, live progress, and
automatic retry. Every user's groups, selections, history, and schedules
are completely private and isolated from every other user.

## Features

- **Public & multi-user** — no admin allowlist; anyone can use the bot,
  and their data never mixes with anyone else's
- Automatically saves a group when you promote the bot to admin there,
  and automatically drops it if the bot is demoted/removed
- View / Select / Select All / Unselect All groups (persisted per user)
- Announcement types:
  - Text message
  - Single photo + caption
  - Album — up to **9 photos** + one caption (sent as a real Telegram media group)
  - Video (max **20 seconds**) + caption
- **Inline URL buttons** on any announcement type
- Formatting: bold/italic/links/etc. that you type (Markdown or the
  Telegram formatting toolbar) is preserved automatically — HTML and
  Markdown both work since we capture your original entities
- **Preview before sending** — see exactly what your groups will see
- Live sending progress (`Sending... 15/200`) that updates as it goes
- Final report: ✅ Success / ❌ Failed / ⚠️ Skipped
- **Retry Failed** button to resend only to the chats that failed
- Broadcast history (last 10 per user), each retryable
- **Scheduling**: Once / Every hour / Every day / Custom minutes, with
  List and Cancel — schedules are stored in SQLite and automatically
  **restored after a VPS reboot or process restart**
- FloodWait handling with automatic wait + retry, per-chat error
  isolation, rotating file + console logging
- SQLite with WAL mode for better concurrent read/write performance

## Project Structure

```
announcement-bot/
├── main.py                          # Entry point: bot, dispatcher, scheduler wiring
├── config.py                        # Env-based configuration (BOT_TOKEN, limits, tuning)
├── database.py                      # SQLite schema + all per-user data access
├── keyboards.py                     # All inline keyboards
├── states.py                        # FSM state groups
├── utils.py                         # Button parsing, datetime helpers, formatting
├── broadcast.py                     # Core send logic: FloodWait, progress, retry
├── scheduler.py                     # Restart-safe polling scheduler
├── handlers/
│   ├── __init__.py                  # Aggregates all routers
│   ├── start.py                     # /start, /help, group auto-save/removal
│   ├── groups.py                    # View/select groups
│   ├── announce.py                  # Compose → buttons → preview → send/retry/history
│   └── schedule.py                  # Frequency selection, list, cancel
├── requirements.txt
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── announcement-bot.service.example # systemd unit (non-Docker VPS deploys)
└── README.md
```

## Setup

1. **Create a bot** with [@BotFather](https://t.me/BotFather) and copy the token.

   > ⚠️ If you previously hardcoded a token in `config.py` in an older
   > version of this project and shared that code with anyone (including
   > pasting it into a chat), treat that token as compromised: open
   > @BotFather → `/revoke` → generate a new one.

2. **Configure environment variables**:

   ```bash
   cp .env.example .env
   # then edit .env and set BOT_TOKEN=...
   ```

   `config.py` now reads `BOT_TOKEN` from the environment (via `.env` or
   real env vars) instead of a hardcoded value, and refuses to start if
   it's missing.

3. **Install dependencies**:

   ```bash
   python3.12 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Run the bot**:

   ```bash
   python main.py
   ```

### Running with Docker

```bash
docker compose up -d --build
```

The `data/` folder (SQLite DB + logs) is mounted as a volume so it
survives container rebuilds, and `restart: unless-stopped` brings the
bot back automatically after a VPS reboot (make sure the Docker daemon
itself is enabled to start on boot: `sudo systemctl enable docker`).

### Running with systemd (no Docker)

```bash
sudo cp announcement-bot.service.example /etc/systemd/system/announcement-bot.service
# edit the User/WorkingDirectory/ExecStart paths to match your setup
sudo systemctl daemon-reload
sudo systemctl enable --now announcement-bot
```

`Restart=always` + `enable` means systemd restarts the bot on crash and
on boot. Either way, all scheduled announcements are restored from
`data/bot.db` on startup — nothing is lost.

## How to use

1. Add the bot to a group and **promote it to admin**. It's saved to
   your personal group list automatically (whoever performed the
   promotion "owns" that group for broadcasting).
2. Open a private chat with the bot and send `/start`.
3. Tap **View Groups**, select the groups you want (or Select All).
4. Tap **Send Announcement**, pick a type (text / photo / album / video),
   send the content, optionally add inline buttons, then review the
   **preview** and tap **Confirm & Send Now** — or **Schedule Instead**
   to set it up as a recurring or one-time send.
5. Watch the live progress, then get your ✅/❌/⚠️ report. If anything
   failed, tap **Retry Failed** to resend only to those chats.
6. Use **My Schedules** to see or cancel anything you've scheduled.

### Inline button format

When asked, send one button per line:

```
Visit Website - https://example.com
```

Put two buttons on the same row with `|`:

```
Site - https://a.com | Chat - https://t.me/username
```

## Notes & limitations

- The bot must remain an **admin** in a group to keep sending there.
- Telegram media groups (albums) cannot carry an inline keyboard — if
  you attach buttons to an album, they're delivered as a small
  follow-up message right after the album.
- Scheduled "once" times are specified in **UTC**.
- `data/bot.db` (SQLite, WAL mode) is created automatically on first
  run. Back it up along with `data/` if you migrate servers.
- `OWNER_IDS` in `.env` is optional and not required for normal use —
  the bot is fully public/multi-user without it.
