from __future__ import annotations

import html

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Config
from helper.buttons import send_photo_styled
from helper.database import settings_db
from helper.rename.models import QueuedItem
from helper.rename.state import BATCH_STATUS_MESSAGES
from helper.utils import safe_edit_text


async def reply_status(message: Message, caption: str, reply_markup=None) -> Message:
    """Send one branded status photo; later stages only edit its caption."""
    user = await settings_db.get_user(message.from_user.id)
    status_pic = user.get("ui_status_pic") or Config.STATUS_PIC
    try:
        if reply_markup is not None:
            sent = await send_photo_styled(getattr(message, "_client", None), message, status_pic, caption, reply_markup)
        else:
            sent = await message.reply_photo(status_pic, caption=caption)
    except Exception:
        # Never make processing depend on a decorative image being reachable.
        sent = await message.reply_text(caption, reply_markup=reply_markup)
    return sent


def batch_queue_markup(*, running: bool = False) -> InlineKeyboardMarkup:
    if running:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("ᴄʟᴇᴀʀ ɴᴇxᴛ ǫᴜᴇᴜᴇ", callback_data="batch:clear")],
            [InlineKeyboardButton("ᴄᴀɴᴄᴇʟ ᴄᴜʀʀᴇɴᴛ ʙᴀᴛᴄʜ", callback_data="batch:cancel")],
        ])
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("ᴅᴏɴᴇ • sᴛᴀʀᴛ", callback_data="batch:done"),
            InlineKeyboardButton("ᴄʟᴇᴀʀ", callback_data="batch:clear"),
        ]
    ])


def active_batch_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ᴄᴀɴᴄᴇʟ ᴄᴜʀʀᴇɴᴛ ʙᴀᴛᴄʜ", callback_data="batch:cancel")]
    ])


def _queue_text(items: list[QueuedItem], *, next_batch: bool = False) -> str:
    items = sorted(items, key=lambda item: item.message.id)
    total = len(items)
    header = "<b>ɴᴇxᴛ ʙᴀᴛᴄʜ ǫᴜᴇᴜᴇ</b>" if next_batch else "<b>ʙᴀᴛᴄʜ ǫᴜᴇᴜᴇ</b>"
    lines = [
        header,
        "",
        f"<blockquote><b>ғɪʟᴇs ʀᴇᴄᴇɪᴠᴇᴅ:</b> <code>{total}</code>\n"
        "<b>sᴇǫᴜᴇɴᴄᴇ:</b> <code>ʀᴇᴀᴅʏ</code></blockquote>",
        "",
    ]
    # Keep Telegram messages compact while still making the order obvious.
    shown = items[:8]
    for index, item in enumerate(shown, 1):
        name = html.escape(item.original_name)
        if len(name) > 58:
            name = name[:55] + "..."
        lines.append(f"<b>{index:02d}.</b> <code>{name}</code>")
    if total > len(shown):
        lines.append(f"\n<code>+ {total - len(shown)} ᴍᴏʀᴇ ғɪʟᴇs</code>")
    lines += [
        "",
        "<b>ᴡʜᴇɴ ʏᴏᴜ ʜᴀᴠᴇ sᴇɴᴛ ᴀʟʟ ғɪʟᴇs, sᴇɴᴅ /done ᴛᴏ sᴛᴀʀᴛ.</b>",
        "<code>/done</code> → ᴘʀᴏᴄᴇssɪɴɢ sᴛᴀʀᴛ",
        "<code>/clear</code> → ᴡᴀɪᴛɪɴɢ ǫᴜᴇᴜᴇ ᴄʟᴇᴀʀ",
        "<code>/cancel</code> → ʙᴀᴛᴄʜ ᴄᴀɴᴄᴇʟ",
    ]
    if next_batch:
        lines += ["", "<blockquote>ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ʙᴀᴛᴄʜ ɪs sᴛɪʟʟ ʀᴜɴɴɪɴɢ. ᴛʜᴇsᴇ ғɪʟᴇs ᴡɪʟʟ ʀᴇᴍᴀɪɴ ǫᴜᴇᴜᴇᴅ ғᴏʀ ᴛʜᴇ ɴᴇxᴛ ʙᴀᴛᴄʜ.</blockquote>"]
    return "\n".join(lines)


async def _update_queue_message(message: Message, items: list[QueuedItem], running: bool) -> None:
    uid = message.from_user.id
    text = _queue_text(items, next_batch=running)
    status = BATCH_STATUS_MESSAGES.get(uid)
    markup = batch_queue_markup(running=running)
    if status:
        edited = await safe_edit_text(status, text, reply_markup=markup)
        if edited:
            return
    try:
        BATCH_STATUS_MESSAGES[uid] = await reply_status(message, text, reply_markup=markup)
    except Exception:
        pass
