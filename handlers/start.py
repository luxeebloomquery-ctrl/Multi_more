# handlers/start.py
# ----------------------------------------------------------------------
# /start, /help, main-menu navigation, and automatic group tracking.
# The bot is public/multi-user: any Telegram user can use it, and the
# group that gets auto-saved when the bot is promoted to admin is
# attributed to whichever user performed that promotion.
# ----------------------------------------------------------------------

import logging

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message

import database as db
from keyboards import main_menu_kb

logger = logging.getLogger(__name__)
router = Router(name="start")


WELCOME_TEXT = (
    "👋 <b>Welcome to the Announcement Bot</b>\n\n"
    "This bot lets you broadcast text, photos, albums, and videos to all "
    "the Telegram groups you manage -- with scheduling, inline buttons, "
    "and full formatting support.\n\n"
    "Your groups, selections, and broadcast history are private to you; "
    "no other user can see or touch them.\n\n"
    "<b>Quick start</b>\n"
    "1. Add this bot to a group and promote it to <b>admin</b> -- it's saved automatically.\n"
    "2. Tap <b>View Groups</b> and select where to broadcast.\n"
    "3. Tap <b>Send Announcement</b> and follow the steps.\n\n"
    "Use the buttons below to get started."
)

HELP_TEXT = (
    "<b>Commands</b>\n"
    "/start - open the control panel\n"
    "/help - show this help\n\n"
    "<b>Button formatting</b>\n"
    "When adding inline buttons, send one per line:\n"
    "<code>Visit Website - https://example.com</code>\n"
    "Put two buttons on the same row with <code>|</code>:\n"
    "<code>Site - https://a.com | Chat - https://t.me/x</code>\n\n"
    "<b>Formatting</b>\n"
    "Bold, italic, links, etc. that you type in Telegram (Markdown or the "
    "formatting toolbar) are preserved automatically when broadcast."
)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    if message.chat.type != ChatType.PRIVATE:
        return  # panel only works in private chat

    db.touch_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await state.clear()
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    if message.chat.type != ChatType.PRIVATE:
        return
    await message.answer(HELP_TEXT)


@router.callback_query(F.data == "back_main")
async def cb_back_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await callback.message.edit_text(
            "👋 <b>Announcement Bot Control Panel</b>\n\n"
            "Use the buttons below to manage your groups and send announcements.",
            reply_markup=main_menu_kb(),
        )
    except Exception:  # noqa: BLE001 - message may be a photo/video, can't edit_text
        await callback.message.answer(
            "👋 <b>Announcement Bot Control Panel</b>\n\n"
            "Use the buttons below to manage your groups and send announcements.",
            reply_markup=main_menu_kb(),
        )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()


# ----------------------------------------------------------------------
# Group tracking - auto save/remove when bot's membership changes.
# The group is attributed to whoever performed the membership change
# (i.e. whoever added/promoted the bot), keeping per-user isolation.
# ----------------------------------------------------------------------
@router.my_chat_member()
async def on_bot_membership_change(event: ChatMemberUpdated) -> None:
    if event.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    new_status = event.new_chat_member.status
    chat_id = event.chat.id
    title = event.chat.title or "Unnamed group"
    actor_id = event.from_user.id if event.from_user else None

    if new_status == ChatMemberStatus.ADMINISTRATOR and actor_id:
        db.add_group(actor_id, chat_id, title)
        logger.info("Group saved for user %s: %s (%s)", actor_id, title, chat_id)
    elif new_status in (
        ChatMemberStatus.LEFT,
        ChatMemberStatus.KICKED,
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.RESTRICTED,
    ):
        # Bot was removed, or demoted from admin -> nobody can broadcast
        # there anymore, so drop it for every user who had it saved.
        owners = db.owners_of_group(chat_id)
        if owners:
            db.remove_group_for_all_owners(chat_id)
            logger.info("Group removed for %s owner(s): %s (%s)", len(owners), title, chat_id)
          
