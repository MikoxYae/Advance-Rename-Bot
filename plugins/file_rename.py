from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

from helper.database import settings_db
from helper.rename.batch import _clear_waiting_queue, _start_batch_for_user
from helper.rename.models import QueuedItem
from helper.rename.state import (
    ACTIVE_BATCH_STATUS, BATCH_CANCEL_EVENTS, BATCH_STATUS_MESSAGES, PENDING_BATCHES,
    QUEUED_FILE_KEYS, RUNNING_BATCHES, get_batch_lock,
)
from helper.rename.ui import _update_queue_message, reply_status
from helper.utils import safe_edit_text


async def batch_collect_handler(client: Client, message: Message):
    uid = message.from_user.id
    user = await settings_db.get_user(uid)
    if not user.get("format_template"):
        return await message.reply_text(
            "<b>ᴀᴜᴛᴏ ʀᴇɴᴀᴍᴇ ғᴏʀᴍᴀᴛ ɪs ɴᴏᴛ sᴇᴛ.</b>\n\n"
            "ᴏᴘᴇɴ /settings ᴀɴᴅ sᴇᴛ ɪᴛ ғɪʀsᴛ."
        )

    media = message.document or message.video or message.audio
    unique = str(getattr(media, "file_unique_id", None) or media.file_id)
    active_key = (uid, unique)
    if active_key in QUEUED_FILE_KEYS:
        return await message.reply_text("<b>ᴛʜɪs ғɪʟᴇ ɪs ᴀʟʀᴇᴀᴅʏ ɪɴ ᴛʜᴇ ǫᴜᴇᴜᴇ.</b>")

    original_name = getattr(media, "file_name", None) or (
        "video.mp4" if message.video else "audio.mp3" if message.audio else "file.bin"
    )
    item = QueuedItem(
        message=message,
        media=media,
        unique=unique,
        original_name=original_name,
    )

    lock = get_batch_lock(uid)
    async with lock:
        QUEUED_FILE_KEYS.add(active_key)
        queue = PENDING_BATCHES.setdefault(uid, [])
        queue.append(item)
        queue.sort(key=lambda queued: queued.message.id)
        running = uid in RUNNING_BATCHES
        await _update_queue_message(message, queue, running)


async def done_handler(client: Client, message: Message):
    await _start_batch_for_user(client, message.from_user.id, message, delete_trigger=True)


async def clear_handler(client: Client, message: Message):
    uid = message.from_user.id
    lock = get_batch_lock(uid)
    async with lock:
        items, status = await _clear_waiting_queue(uid)
        running = uid in RUNNING_BATCHES

    if status:
        await safe_edit_text(
            status,
            "<b>ǫᴜᴇᴜᴇ ᴄʟᴇᴀʀᴇᴅ</b>\n\n"
            f"<b>ʀᴇᴍᴏᴠᴇᴅ:</b> <code>{len(items)} ғɪʟᴇs</code>\n"
            + ("<blockquote>ᴄᴜʀʀᴇɴᴛ ʀᴜɴɴɪɴɢ ʙᴀᴛᴄʜ ɪs ɴᴏᴛ ᴀғғᴇᴄᴛᴇᴅ.</blockquote>" if running else ""),
            reply_markup=None,
        )
    else:
        await reply_status(
            message,
            "<b>ǫᴜᴇᴜᴇ ᴄʟᴇᴀʀᴇᴅ</b>\n\n"
            f"<b>ʀᴇᴍᴏᴠᴇᴅ:</b> <code>{len(items)} ғɪʟᴇs</code>\n"
            + ("<blockquote>ᴄᴜʀʀᴇɴᴛ ʀᴜɴɴɪɴɢ ʙᴀᴛᴄʜ ɪs ɴᴏᴛ ᴀғғᴇᴄᴛᴇᴅ. /cancel ᴜsᴇ ᴋʀᴏ ᴛᴏ sᴛᴏᴘ ɪᴛ.</blockquote>" if running else ""),
        )

    try:
        await message.delete()
    except Exception:
        pass


async def cancel_handler(client: Client, message: Message):
    uid = message.from_user.id
    lock = get_batch_lock(uid)
    async with lock:
        running = uid in RUNNING_BATCHES
        items, waiting_status = await _clear_waiting_queue(uid)
        cancel_event = BATCH_CANCEL_EVENTS.get(uid)
        if running and cancel_event:
            cancel_event.set()
        active_status = ACTIVE_BATCH_STATUS.get(uid)

    if waiting_status and waiting_status is not active_status:
        await safe_edit_text(
            waiting_status,
            "<b>ɴᴇxᴛ ǫᴜᴇᴜᴇ ᴄʟᴇᴀʀᴇᴅ</b>\n\n"
            f"<b>ʀᴇᴍᴏᴠᴇᴅ:</b> <code>{len(items)} ғɪʟᴇs</code>",
            reply_markup=None,
        )

    if running:
        if active_status:
            await safe_edit_text(
                active_status,
                "<b>ᴄᴀɴᴄᴇʟ ʀᴇǫᴜᴇsᴛᴇᴅ</b>\n\n"
                "<blockquote>ᴄᴜʀʀᴇɴᴛ ᴛʀᴀɴsғᴇʀ ᴡɪʟʟ ғɪɴɪsʜ sᴀғᴇʟʏ. ᴀғᴛᴇʀ ᴛʜᴀᴛ ɴᴏ ɴᴇᴡ ғɪʟᴇ ᴡɪʟʟ ʙᴇ ᴜᴘʟᴏᴀᴅᴇᴅ.</blockquote>\n\n"
                "<b>ɴᴇxᴛ ǫᴜᴇᴜᴇ:</b> <code>ᴄʟᴇᴀʀᴇᴅ</code>",
                reply_markup=None,
            )
        else:
            await reply_status(message, "<b>ᴄᴀɴᴄᴇʟ ʀᴇǫᴜᴇsᴛᴇᴅ.</b>")
    else:
        target = waiting_status
        text = (
            "<b>ʙᴀᴛᴄʜ ᴄᴀɴᴄᴇʟʟᴇᴅ</b>\n\n"
            f"<b>ʀᴇᴍᴏᴠᴇᴅ:</b> <code>{len(items)} ғɪʟᴇs</code>"
        )
        if target:
            await safe_edit_text(target, text, reply_markup=None)
        else:
            await reply_status(message, text)

    try:
        await message.delete()
    except Exception:
        pass


async def batch_callback_handler(client: Client, query: CallbackQuery):
    uid = query.from_user.id
    action = query.data.split(":", 1)[1]
    try:
        await query.answer()
    except Exception:
        pass

    if action == "done":
        await _start_batch_for_user(client, uid, query.message, delete_trigger=False)
        return

    if action == "clear":
        lock = get_batch_lock(uid)
        async with lock:
            items, status = await _clear_waiting_queue(uid)
            running = uid in RUNNING_BATCHES
        target = status or query.message
        await safe_edit_text(
            target,
            "<b>ǫᴜᴇᴜᴇ ᴄʟᴇᴀʀᴇᴅ</b>\n\n"
            f"<b>ʀᴇᴍᴏᴠᴇᴅ:</b> <code>{len(items)} ғɪʟᴇs</code>\n"
            + ("<blockquote>ᴄᴜʀʀᴇɴᴛ ʀᴜɴɴɪɴɢ ʙᴀᴛᴄʜ ɪs ɴᴏᴛ ᴀғғᴇᴄᴛᴇᴅ.</blockquote>" if running else ""),
            reply_markup=None,
        )
        return

    # cancel
    lock = get_batch_lock(uid)
    async with lock:
        running = uid in RUNNING_BATCHES
        items, waiting_status = await _clear_waiting_queue(uid)
        event = BATCH_CANCEL_EVENTS.get(uid)
        if running and event:
            event.set()
        active_status = ACTIVE_BATCH_STATUS.get(uid)

    if waiting_status and waiting_status is not active_status:
        await safe_edit_text(
            waiting_status,
            "<b>ɴᴇxᴛ ǫᴜᴇᴜᴇ ᴄʟᴇᴀʀᴇᴅ</b>\n\n"
            f"<b>ʀᴇᴍᴏᴠᴇᴅ:</b> <code>{len(items)} ғɪʟᴇs</code>",
            reply_markup=None,
        )

    if running:
        target = active_status or query.message
        await safe_edit_text(
            target,
            "<b>ᴄᴀɴᴄᴇʟ ʀᴇǫᴜᴇsᴛᴇᴅ</b>\n\n"
            "<blockquote>ᴄᴜʀʀᴇɴᴛ ᴛʀᴀɴsғᴇʀ ᴡɪʟʟ ғɪɴɪsʜ sᴀғᴇʟʏ. ᴀғᴛᴇʀ ᴛʜᴀᴛ ɴᴏ ɴᴇᴡ ғɪʟᴇ ᴡɪʟʟ ʙᴇ ᴜᴘʟᴏᴀᴅᴇᴅ.</blockquote>\n\n"
            "<b>ɴᴇxᴛ ǫᴜᴇᴜᴇ:</b> <code>ᴄʟᴇᴀʀᴇᴅ</code>",
            reply_markup=None,
        )
    else:
        target = waiting_status or query.message
        await safe_edit_text(
            target,
            "<b>ʙᴀᴛᴄʜ ᴄᴀɴᴄᴇʟʟᴇᴅ</b>\n\n"
            f"<b>ʀᴇᴍᴏᴠᴇᴅ:</b> <code>{len(items)} ғɪʟᴇs</code>",
            reply_markup=None,
        )


