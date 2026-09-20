"""
MADARA BOT - Free Fire Info Telegram Bot
Single-file implementation for Termux (aiogram 3.x + aiohttp + sqlite3)

Run:
    pip install aiogram aiohttp
    python main.py
"""

import asyncio
import logging
import sqlite3
import time
from typing import Optional

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.exceptions import TelegramBadRequest

# ══════════════════════════════════════════════════════════════
# CONFIGURATION — edit these values
# ══════════════════════════════════════════════════════════════

BOT_TOKEN = "PUT_BOT_TOKEN_HERE"

OWNER_ID = 0

CHANNEL_ID = -1002740009398
CHANNEL_LINK = "https://t.me/+2Fxg6o4jEKAxOGQ1"

EXAMPLE_GROUP_ID = -1002707821928
EXAMPLE_GROUP_LINK = "https://t.me/+UjfE3wtSXcsyODg1"

PLAYER_API = "https://crystal-ffinfo.vercel.app/player-info"
PLAYER_API_KEY = "crystal"

GUILD_API = "https://star-guild-info.lovable.app/api/public/info"

DB_PATH = "madara_bot.db"

# ══════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("madara_bot")

# ══════════════════════════════════════════════════════════════
# DATABASE (built-in sqlite3, synchronous — small workload, safe)
# ══════════════════════════════════════════════════════════════


def db_init() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS approved_groups (
            group_id INTEGER PRIMARY KEY,
            approved_by INTEGER,
            approved_at INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS verified_users (
            user_id INTEGER PRIMARY KEY,
            verified_at INTEGER
        )
        """
    )
    conn.commit()
    conn.close()


def db_approve_group(group_id: int, admin_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO approved_groups (group_id, approved_by, approved_at) "
        "VALUES (?, ?, ?)",
        (group_id, admin_id, int(time.time())),
    )
    conn.commit()
    conn.close()


def db_is_group_approved(group_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM approved_groups WHERE group_id = ?", (group_id,))
    row = cur.fetchone()
    conn.close()
    return row is not None


def db_all_approved_groups() -> list:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT group_id FROM approved_groups")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


def db_mark_verified(user_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO verified_users (user_id, verified_at) VALUES (?, ?)",
        (user_id, int(time.time())),
    )
    conn.commit()
    conn.close()


# ══════════════════════════════════════════════════════════════
# KEYBOARDS
# ══════════════════════════════════════════════════════════════


def kb_join_verify() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Join Channel", url=CHANNEL_LINK)],
            [InlineKeyboardButton(text="✅ Verify", callback_data="verify")],
        ]
    )


def kb_join_verify_again() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Join Channel", url=CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Verify Again", callback_data="verify")],
        ]
    )


# ══════════════════════════════════════════════════════════════
# TEXT TEMPLATES
# ══════════════════════════════════════════════════════════════

TXT_WELCOME = (
    "╭━━━〔 ✦ 𝐖𝐄𝐋𝐂𝐎𝐌𝐄 ✦ 〕━━━╮\n\n"
    "👋 Welcome to 𝐌𝐀𝐃𝐀𝐑𝐀 𝐁𝐎𝐓!\n\n"
    "🔐 To use this bot, you must join\n"
    "our official channel first.\n\n"
    "📢 Join the channel and then\n"
    "click the Verify button below.\n\n"
    "╰━━━━━━━━━━━━━━━━━━━━━━╯"
)

TXT_NOT_JOINED = (
    "╭━━━〔 ⚠️ 𝐕𝐄𝐑𝐈𝐅𝐈𝐂𝐀𝐓𝐈𝐎𝐍 〕━━━╮\n\n"
    "❌ You haven't joined our channel yet.\n\n"
    "📢 Please join the channel first,\n"
    "then click Verify again.\n\n"
    "╰━━━━━━━━━━━━━━━━━━━━━━╯"
)

TXT_VERIFIED = (
    "╭━━━〔 ✅ 𝐕𝐄𝐑𝐈𝐅𝐈𝐄𝐃 〕━━━╮\n\n"
    "🎉 Verification successful!\n\n"
    "You can now use 𝐌𝐀𝐃𝐀𝐑𝐀 𝐁𝐎𝐓.\n\n"
    "⚠️ Commands are available\n"
    "only inside approved groups.\n\n"
    "╰━━━━━━━━━━━━━━━━━━━━━━╯"
)

TXT_GROUP_ONLY = (
    "╭━━━〔 🚫 𝐆𝐑𝐎𝐔𝐏 𝐎𝐍𝐋𝐘 〕━━━╮\n\n"
    "This bot works only in Telegram groups.\n\n"
    "➜ Add me to your group\n"
    "➜ Get the group approved\n"
    "➜ Then use the commands.\n\n"
    "╰━━━━━━━━━━━━━━━━━━━━━━╯"
)

TXT_ACCESS_DENIED = (
    "╭━━━〔 ⚠️ 𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃 〕━━━╮\n\n"
    "❌ Only group administrators\n"
    "can approve this bot.\n\n"
    "╰━━━━━━━━━━━━━━━━━━━━━━╯"
)

TXT_GROUP_APPROVED = (
    "╭━━━〔 ✦ 𝐆𝐑𝐎𝐔𝐏 𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃 ✦ 〕━━━╮\n\n"
    "✅ Group successfully approved!\n\n"
    "🤖 𝐌𝐀𝐃𝐀𝐑𝐀 𝐁𝐎𝐓 is now active\n"
    "in this group.\n\n"
    "🎮 Available Commands:\n\n"
    "/player <UID>\n"
    "/guild <GUILD_ID> <REGION>\n"
    "/like <UID> <REGION>\n\n"
    "╰━━━━━━━━━━━━━━━━━━━━━━╯"
)

TXT_NOT_APPROVED = (
    "╭━━━〔 🔒 𝐍𝐎𝐓 𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃 〕━━━╮\n\n"
    "This group has not been approved yet.\n\n"
    "👑 A group administrator must use\n"
    "/approve before the bot can be used.\n\n"
    "╰━━━━━━━━━━━━━━━━━━━━━━╯"
)

TXT_HELP = (
    "╭━━━〔 ✦ 𝐌𝐀𝐃𝐀𝐑𝐀 𝐁𝐎𝐓 ✦ 〕━━━╮\n\n"
    "🎮 𝐀𝐕𝐀𝐈𝐋𝐀𝐁𝐋𝐄 𝐂𝐎𝐌𝐌𝐀𝐍𝐃𝐒\n\n"
    "👤 /player <UID>\n"
    "└─ Get Free Fire player details\n\n"
    "🏰 /guild <GUILD_ID> <REGION>\n"
    "└─ Get Free Fire guild details\n\n"
    "❤️ /like <UID> <REGION>\n"
    "└─ Check player information\n\n"
    "📌 Examples:\n\n"
    "/player 11111111\n\n"
    "/guild 60658578 IND\n\n"
    "/like 576677666 IND\n\n"
    "╰━━━━━━━━━━━━━━━━━━━━━━╯"
)


def txt_invalid_format(command_example: str, second_example: str) -> str:
    return (
        "╭━━━〔 ⚠️ 𝐈𝐍𝐕𝐀𝐋𝐈𝐃 𝐅𝐎𝐑𝐌𝐀𝐓 〕━━━╮\n\n"
        "Correct format:\n\n"
        f"{command_example}\n\n"
        "Example:\n\n"
        f"{second_example}\n\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━╯"
    )


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

ALLOWED_MEMBER_STATUSES = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
}

ADMIN_STATUSES = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}


async def is_channel_member(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ALLOWED_MEMBER_STATUSES
    except TelegramBadRequest as e:
        log.warning("Channel membership check failed for %s: %s", user_id, e)
        return False
    except Exception as e:
        log.error("Unexpected error checking channel membership: %s", e)
        return False


async def is_group_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status in ADMIN_STATUSES
    except Exception as e:
        log.error("Unexpected error checking group admin: %s", e)
        return False


async def fetch_json(session: aiohttp.ClientSession, url: str, params: dict) -> Optional[dict]:
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with session.get(url, params=params, timeout=timeout) as resp:
            if resp.status != 200:
                log.warning("API %s returned status %s", url, resp.status)
                return None
            return await resp.json(content_type=None)
    except asyncio.TimeoutError:
        log.warning("API %s timed out", url)
        return None
    except Exception as e:
        log.error("API %s request failed: %s", url, e)
        return None


def safe_get(d: dict, *keys, default="N/A"):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur or cur[k] is None:
            return default
        cur = cur[k]
    if cur == "" or cur is None:
        return default
    return cur


async def animate_loading(message: Message, frames: list, delay: float = 0.7) -> Message:
    """Send the first frame, then edit it through the remaining frames."""
    sent = await message.answer(frames[0])
    for frame in frames[1:]:
        await asyncio.sleep(delay)
        try:
            await sent.edit_text(frame)
        except TelegramBadRequest:
            pass
    return sent


# ══════════════════════════════════════════════════════════════
# ROUTER
# ══════════════════════════════════════════════════════════════

router = Router()


# ---------------- /start ----------------


@router.message(Command("start"), F.chat.type == "private")
async def cmd_start(message: Message, bot: Bot):
    if await is_channel_member(bot, message.from_user.id):
        db_mark_verified(message.from_user.id)
        await message.answer(TXT_VERIFIED)
    else:
        await message.answer(TXT_WELCOME, reply_markup=kb_join_verify())


@router.callback_query(F.data == "verify")
async def cb_verify(callback: CallbackQuery, bot: Bot):
    if await is_channel_member(bot, callback.from_user.id):
        db_mark_verified(callback.from_user.id)
        await callback.message.edit_text(TXT_VERIFIED)
    else:
        try:
            await callback.message.edit_text(TXT_NOT_JOINED, reply_markup=kb_join_verify_again())
        except TelegramBadRequest:
            pass
    await callback.answer()


# ---------------- /help ----------------


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(TXT_HELP)


# ---------------- /approve ----------------


@router.message(Command("approve"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_approve(message: Message, bot: Bot):
    if not await is_group_admin(bot, message.chat.id, message.from_user.id):
        await message.answer(TXT_ACCESS_DENIED)
        return
    db_approve_group(message.chat.id, message.from_user.id)
    await message.answer(TXT_GROUP_APPROVED)


# ---------------- group-only guard for game commands in private ----------------


@router.message(Command("player", "guild", "like"), F.chat.type == "private")
async def cmd_group_only(message: Message):
    await message.answer(TXT_GROUP_ONLY)


# ---------------- /player ----------------


@router.message(Command("player"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_player(message: Message, command: CommandObject):
    if not db_is_group_approved(message.chat.id):
        await message.answer(TXT_NOT_APPROVED)
        return

    args = (command.args or "").strip().split()
    if len(args) != 1 or not args[0].isdigit():
        await message.answer(txt_invalid_format("/player <UID>", "/player 11111111"))
        return

    uid = args[0]

    frames = [
        "⏳ Fetching player information...",
        "🔄 Connecting to Player API...",
        "🔄 Fetching player data...",
        "⚙️ Processing player information...",
    ]
    sent = await animate_loading(message, frames)

    async with aiohttp.ClientSession() as session:
        data = await fetch_json(
            session, PLAYER_API, {"uid": uid, "key": PLAYER_API_KEY}
        )

    if not data:
        await sent.edit_text(
            "╭━━━〔 ⚠️ 𝐄𝐑𝐑𝐎𝐑 〕━━━╮\n\n"
            "❌ Could not fetch player data.\n"
            "Please check the UID and try again.\n\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        return

    basic = data.get("basicInfo", {}) or {}
    clan = data.get("clanBasicInfo", {}) or {}
    pet = data.get("petInfo", {}) or {}
    diamond = data.get("diamondCostRes", {}) or {}
    credit = data.get("creditScoreInfo", {}) or {}

    result = (
        "╭━━━〔 ✦ 𝐅𝐑𝐄𝐄 𝐅𝐈𝐑𝐄 𝐏𝐋𝐀𝐘𝐄𝐑 ✦ 〕━━━╮\n\n"
        f"👤 𝐍𝐚𝐦𝐞 ➜ {safe_get(basic, 'nickname')}\n"
        f"🆔 𝐔𝐈𝐃 ➜ {safe_get(basic, 'accountId')}\n"
        f"🌐 𝐑𝐞𝐠𝐢𝐨𝐧 ➜ {safe_get(basic, 'region')}\n"
        f"⭐ 𝐋𝐞𝐯𝐞𝐥 ➜ {safe_get(basic, 'level')}\n"
        f"❤️ 𝐋𝐢𝐤𝐞𝐬 ➜ {safe_get(basic, 'liked')}\n\n"
        "├──────〔 🏆 𝐑𝐀𝐍𝐊 〕──────\n\n"
        f"🏅 𝐁𝐑 𝐑𝐚𝐧𝐤 ➜ {safe_get(basic, 'rank')}\n"
        f"🎯 𝐁𝐑 𝐏𝐨𝐢𝐧𝐭𝐬 ➜ {safe_get(basic, 'rankingPoints')}\n"
        f"⚔️ 𝐂𝐒 𝐑𝐚𝐧𝐤 ➜ {safe_get(basic, 'csRank')}\n"
        f"🎯 𝐂𝐒 𝐏𝐨𝐢𝐧𝐭𝐬 ➜ {safe_get(basic, 'csRankingPoints')}\n\n"
        "├──────〔 🏰 𝐆𝐔𝐈𝐋𝐃 〕──────\n\n"
        f"🏷️ 𝐍𝐚𝐦𝐞 ➜ {safe_get(clan, 'clanName')}\n"
        f"🆔 𝐆𝐮𝐢𝐥𝐝 𝐈𝐃 ➜ {safe_get(clan, 'clanId')}\n"
        f"⭐ 𝐋𝐞𝐯𝐞𝐥 ➜ {safe_get(clan, 'clanLevel')}\n"
        f"👥 𝐌𝐞𝐦𝐛𝐞𝐫𝐬 ➜ {safe_get(clan, 'memberNum')}/{safe_get(clan, 'capacity')}\n\n"
        "├──────〔 🐾 𝐏𝐄𝐓 〕──────\n\n"
        f"🐾 𝐋𝐞𝐯𝐞𝐥 ➜ {safe_get(pet, 'level')}\n"
        f"🆔 𝐏𝐞𝐭 𝐈𝐃 ➜ {safe_get(pet, 'id')}\n\n"
        "├──────〔 🛡️ 𝐒𝐓𝐀𝐓𝐔𝐒 〕──────\n\n"
        f"💯 𝐂𝐫𝐞𝐝𝐢𝐭 ➜ {safe_get(credit, 'creditScore')}\n"
        f"💎 𝐃𝐢𝐚𝐦𝐨𝐧𝐝 ➜ {safe_get(diamond, 'diamondCost')}\n\n"
        "╰━━━〔 ✦ 𝐌𝐀𝐃𝐀𝐑𝐀 𝐁𝐎𝐓 ✦ 〕━━━╯"
    )

    await sent.edit_text(result)


# ---------------- /guild ----------------


@router.message(Command("guild"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_guild(message: Message, command: CommandObject):
    if not db_is_group_approved(message.chat.id):
        await message.answer(TXT_NOT_APPROVED)
        return

    args = (command.args or "").strip().split()
    if len(args) != 2 or not args[0].isdigit():
        await message.answer(
            txt_invalid_format("/guild <GUILD_ID> <REGION>", "/guild 60658578 IND")
        )
        return

    clan_id, region = args[0], args[1].upper()

    frames = [
        "⏳ Fetching guild information...",
        "🔄 Connecting to Guild API...",
        "🔄 Fetching guild data...",
        "⚙️ Processing guild information...",
    ]
    sent = await animate_loading(message, frames)

    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, GUILD_API, {"clan_id": clan_id, "region": region})

    if not data:
        await sent.edit_text(
            "╭━━━〔 ⚠️ 𝐄𝐑𝐑𝐎𝐑 〕━━━╮\n\n"
            "❌ Could not fetch guild data.\n"
            "Please check the Guild ID / region and try again.\n\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        return

    result = (
        "╭━━━〔 ✦ 𝐆𝐔𝐈𝐋𝐃 𝐈𝐍𝐅𝐎 ✦ 〕━━━╮\n\n"
        f"🏷️ 𝐆𝐮𝐢𝐥𝐝 ➜ {safe_get(data, 'clanName')}\n"
        f"🆔 𝐈𝐃 ➜ {safe_get(data, 'clanId')}\n"
        f"🌐 𝐑𝐞𝐠𝐢𝐨𝐧 ➜ {safe_get(data, 'region')}\n\n"
        "├──────〔 📊 𝐒𝐓𝐀𝐓𝐈𝐒𝐓𝐈𝐂𝐒 〕──────\n\n"
        f"⭐ 𝐋𝐞𝐯𝐞𝐥 ➜ {safe_get(data, 'level')}\n"
        f"🏆 𝐑𝐚𝐧𝐤 ➜ {safe_get(data, 'rank')}\n"
        f"💎 𝐆𝐥𝐨𝐫𝐲 𝐏𝐨𝐢𝐧𝐭𝐬 ➜ {safe_get(data, 'gloryPoints')}\n"
        f"⚡ 𝐀𝐜𝐭𝐢𝐯𝐢𝐭𝐲 𝐗𝐏 ➜ {safe_get(data, 'activityXp')}\n\n"
        "├──────〔 👥 𝐌𝐄𝐌𝐁𝐄𝐑𝐒 〕──────\n\n"
        f"👥 𝐌𝐞𝐦𝐛𝐞𝐫𝐬 ➜ {safe_get(data, 'memberCount')}/{safe_get(data, 'capacity')}\n"
        f"🟢 𝐎𝐧𝐥𝐢𝐧𝐞 ➜ {safe_get(data, 'onlineMembers')}\n"
        f"👑 𝐌𝐚𝐧𝐚𝐠𝐞𝐫𝐬 ➜ {safe_get(data, 'managerCount')}\n\n"
        "├──────〔 👑 𝐋𝐄𝐀𝐃𝐄𝐑 〕──────\n\n"
        f"🆔 𝐋𝐞𝐚𝐝𝐞𝐫 ➜ {safe_get(data, 'leaderName')}\n"
        f"🆔 𝐎𝐰𝐧𝐞𝐫 ➜ {safe_get(data, 'ownerId')}\n\n"
        "├──────〔 📝 𝐀𝐁𝐎𝐔𝐓 〕──────\n\n"
        f"💬 {safe_get(data, 'notice')}\n\n"
        "╰━━━〔 ✦ 𝐌𝐀𝐃𝐀𝐑𝐀 𝐁𝐎𝐓 ✦ 〕━━━╯"
    )

    await sent.edit_text(result)


# ---------------- /like ----------------


@router.message(Command("like"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_like(message: Message, command: CommandObject):
    if not db_is_group_approved(message.chat.id):
        await message.answer(TXT_NOT_APPROVED)
        return

    args = (command.args or "").strip().split()
    if len(args) != 2 or not args[0].isdigit():
        await message.answer(
            txt_invalid_format("/like <UID> <REGION>", "/like 576677666 IND")
        )
        return

    uid, region = args[0], args[1].upper()

    frames = [
        "⏳ Processing like request...",
        "🔄 Fetching player information...",
        "🔄 Checking player data...",
        "⚙️ Processing request...",
    ]
    sent = await animate_loading(message, frames)

    start_time = time.monotonic()

    async with aiohttp.ClientSession() as session:
        data = await fetch_json(
            session, PLAYER_API, {"uid": uid, "key": PLAYER_API_KEY}
        )

    elapsed = round(time.monotonic() - start_time, 2)

    if not data:
        await sent.edit_text(
            "╭━━━〔 ⚠️ 𝐄𝐑𝐑𝐎𝐑 〕━━━╮\n\n"
            "❌ Could not fetch player data.\n"
            "Please check the UID and try again.\n\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━╯"
        )
        return

    basic = data.get("basicInfo", {}) or {}
    nickname = safe_get(basic, "nickname")
    account_id = safe_get(basic, "accountId")
    level = safe_get(basic, "level")
    before = safe_get(basic, "liked")
    after = before  # no real Like API — value cannot change
    given = 0

    result = (
        "┌ ᴘʟᴀʏᴇʀ ɪɴꜰᴏʀᴍᴀᴛɪᴏɴ ☠️\n"
        f"├─ ɴɪᴄᴋɴᴀᴍᴇ: {nickname}\n"
        f"├─ ᴜɪᴅ: {account_id}\n"
        f"├─ ʀᴇɢɪᴏɴ: {region} 🇮🇳\n"
        f"├─ ʟᴇᴠᴇʟ: {level}\n"
        f"├─ ʙᴇꜰᴏʀᴇ: {before}\n"
        f"├─ ᴀꜰᴛᴇʀ: {after}\n"
        f"├─ ɢɪᴠᴇɴ: {given}\n"
        f"└─ ᴛɪᴍᴇ ᴛᴀᴋᴇɴ: {elapsed}s"
    )

    await sent.edit_text(result)

    if given == 0:
        await message.answer("⚠️ ᴛʀʏ ɴᴇxᴛ ᴛɪᴍᴇ ʙʀᴏ 👍")


# ---------------- /broadcast ----------------


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, command: CommandObject, bot: Bot):
    if message.from_user.id != OWNER_ID:
        return

    text = (command.args or "").strip()
    if not text:
        await message.answer(
            txt_invalid_format("/broadcast <message>", "/broadcast Hello everyone!")
        )
        return

    groups = db_all_approved_groups()
    sent_count = 0
    failed_count = 0

    for gid in groups:
        try:
            await bot.send_message(gid, text)
            sent_count += 1
        except Exception as e:
            log.warning("Broadcast failed for group %s: %s", gid, e)
            failed_count += 1
        await asyncio.sleep(0.05)  # gentle rate limiting

    await message.answer(
        "📢 Broadcast completed!\n\n"
        f"✅ Sent: {sent_count}\n"
        f"❌ Failed: {failed_count}"
    )


# ══════════════════════════════════════════════════════════════
# ENTRYPOINT
# ══════════════════════════════════════════════════════════════


async def main():
    if BOT_TOKEN == "PUT_BOT_TOKEN_HERE" or not BOT_TOKEN:
        raise SystemExit(
            "Please set BOT_TOKEN at the top of main.py before running the bot."
        )

    db_init()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    log.info("MADARA BOT starting...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot stopped.")
