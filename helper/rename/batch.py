from __future__ import annotations

import asyncio
import html
import logging
import shutil

from pyrogram import Client
from pyrogram.types import Message

from helper.database import settings_db
from helper.rename.processing import prepare_batch_item
from helper.rename.transfer import send_output
from helper.rename.models import BatchCancelled, PreparedItem, QueuedItem
from helper.rename.parser import sort_queued_items
from helper.rename.state import (
    ACTIVE_BATCH_STATUS, BATCH_CANCEL_EVENTS, BATCH_STATUS_MESSAGES, BATCH_TASKS,
    PENDING_BATCHES, QUEUED_FILE_KEYS, RUNNING_BATCHES, get_batch_lock,
    get_user_upload_lock,
)
from helper.rename.ui import active_batch_markup, batch_queue_markup, reply_status, _queue_text
from helper.utils import safe_edit_text

logger = logging.getLogger(__name__)


async def process_batch(
    client: Client,
    uid: int,
    items: list[QueuedItem],
    batch_status: Message | None,
    cancel_event: asyncio.Event,
) -> None:
    items = sort_queued_items(items)
    total = len(items)
    stats = {"uploaded": 0, "failed": 0, "cancelled": 0}
    # Size 1 guarantees only the immediate next prepared file can wait.
    # It prevents later items from overtaking the queue under any future concurrency changes.
    prepared_queue: asyncio.Queue[PreparedItem | None] = asyncio.Queue(maxsize=1)
    user = await settings_db.get_user(uid)

    if batch_status:
        ACTIVE_BATCH_STATUS[uid] = batch_status
        await safe_edit_text(
            batch_status,
            "<b>ʙᴀᴛᴄʜ sᴛᴀʀᴛᴇᴅ</b>\n\n"
            f"<b>ᴛᴏᴛᴀʟ ғɪʟᴇs:</b> <code>{total}</code>\n"
            "<blockquote>ᴘɪᴘᴇʟɪɴᴇ: 1 ᴜᴘʟᴏᴀᴅ + ɴᴇxᴛ 1 ᴅᴏᴡɴʟᴏᴀᴅ.\n"
            "ᴛʜᴇ ɴᴇxᴛ ᴅᴏᴡɴʟᴏᴀᴅ sᴛᴀʀᴛs ᴏɴʟʏ ᴀғᴛᴇʀ ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ᴜᴘʟᴏᴀᴅ ʜᴀs ᴀᴄᴛᴜᴀʟʟʏ sᴛᴀʀᴛᴇᴅ.\n"
            "ᴜᴘʟᴏᴀᴅ ᴏʀᴅᴇʀ sᴛʀɪᴄᴛ: 01 → 02 → 03 → ...</blockquote>",
            reply_markup=active_batch_markup(),
        )

    async def producer():
        for index, item in enumerate(items, 1):
            if cancel_event.is_set():
                stats["cancelled"] += total - index + 1
                break

            try:
                prepared = await prepare_batch_item(client, uid, item, user, index, total)
            except Exception as exc:
                stats["failed"] += 1
                logger.exception("Batch prepare failed: %s", item.original_name)
                QUEUED_FILE_KEYS.discard((uid, item.unique))
                try:
                    await reply_status(
                        item.message,
                        f"<b>ғɪʟᴇ {index}/{total} ғᴀɪʟᴇᴅ</b>\n\n"
                        f"<code>{html.escape(str(exc)[:700])}</code>",
                    )
                except Exception:
                    pass
                continue

            # If cancel was requested while this file was downloading/remuxing,
            # do not start its upload. Clean it and stop the producer.
            if cancel_event.is_set():
                stats["cancelled"] += total - index + 1
                QUEUED_FILE_KEYS.discard((uid, item.unique))
                shutil.rmtree(prepared.workdir, ignore_errors=True)
                break

            await prepared_queue.put(prepared)
            # Strict pipeline gate: the next download starts only after this
            # file has acquired a real Telegram upload slot.
            await prepared.upload_started.wait()

        await prepared_queue.put(None)

    async def uploader():
        # A dedicated per-user lock makes the ordering guarantee explicit even
        # if this pipeline is refactored to have more upload workers later.
        upload_lock = get_user_upload_lock(uid)
        last_sequence = 0

        while True:
            prepared = await prepared_queue.get()
            if prepared is None:
                prepared_queue.task_done()
                break

            item = prepared.queued
            try:
                if cancel_event.is_set():
                    if not prepared.upload_started.is_set():
                        prepared.upload_started.set()
                    stats["cancelled"] += 1
                    continue

                # FIFO safety check: a lower/equal sequence can never upload
                # after a later item. Producer + maxsize=1 already preserve FIFO;
                # this guard makes accidental reordering fail closed.
                if prepared.sequence <= last_sequence:
                    raise RuntimeError(
                        f"Upload sequence violation: got {prepared.sequence} after {last_sequence}"
                    )

                async with upload_lock:
                    await send_output(
                        client,
                        item.message,
                        str(prepared.final_path),
                        prepared.output_type,
                        prepared.caption,
                        prepared.thumb,
                        upload_started_event=prepared.upload_started,
                        cancel_event=cancel_event,
                    )

                last_sequence = prepared.sequence
                stats["uploaded"] += 1
            except BatchCancelled:
                if not prepared.upload_started.is_set():
                    prepared.upload_started.set()
                stats["cancelled"] += 1
                last_sequence = max(last_sequence, prepared.sequence)
            except Exception as exc:
                # Never deadlock the producer if upload setup failed before a
                # global upload slot was acquired. The failed item is considered
                # consumed and the next queued sequence may proceed.
                if not prepared.upload_started.is_set():
                    prepared.upload_started.set()
                last_sequence = max(last_sequence, prepared.sequence)
                stats["failed"] += 1
                logger.exception("Batch upload failed: %s", item.original_name)
                try:
                    await reply_status(
                        item.message,
                        "<b>ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ</b>\n\n"
                        f"<code>{html.escape(str(exc)[:700])}</code>",
                    )
                except Exception:
                    pass
            finally:
                QUEUED_FILE_KEYS.discard((uid, item.unique))
                shutil.rmtree(prepared.workdir, ignore_errors=True)
                prepared_queue.task_done()

    try:
        await asyncio.gather(producer(), uploader())
    finally:
        RUNNING_BATCHES.discard(uid)
        BATCH_TASKS.pop(uid, None)
        BATCH_CANCEL_EVENTS.pop(uid, None)
        ACTIVE_BATCH_STATUS.pop(uid, None)
        for item in items:
            QUEUED_FILE_KEYS.discard((uid, item.unique))

        if batch_status:
            if cancel_event.is_set():
                await safe_edit_text(
                    batch_status,
                    "<b>ʙᴀᴛᴄʜ ᴄᴀɴᴄᴇʟʟᴇᴅ</b>\n\n"
                    f"<b>ᴛᴏᴛᴀʟ:</b> <code>{total}</code>\n"
                    f"<b>ᴜᴘʟᴏᴀᴅᴇᴅ:</b> <code>{stats['uploaded']}</code>\n"
                    f"<b>ғᴀɪʟᴇᴅ:</b> <code>{stats['failed']}</code>\n"
                    f"<b>ᴄᴀɴᴄᴇʟʟᴇᴅ/sᴋɪᴘᴘᴇᴅ:</b> <code>{max(stats['cancelled'], total - stats['uploaded'] - stats['failed'])}</code>\n\n"
                    "<blockquote>ᴄᴜʀʀᴇɴᴛ ᴛʀᴀɴsғᴇʀ ᴡᴀs ᴀʟʟᴏᴡᴇᴅ ᴛᴏ ғɪɴɪsʜ sᴀғᴇʟʏ. ɴᴏ ɴᴇᴡ ᴜᴘʟᴏᴀᴅ ᴡᴀs sᴛᴀʀᴛᴇᴅ ᴀғᴛᴇʀ ᴄᴀɴᴄᴇʟ.</blockquote>",
                    reply_markup=None,
                )
            else:
                await safe_edit_text(
                    batch_status,
                    "<b>ʙᴀᴛᴄʜ ᴄᴏᴍᴘʟᴇᴛᴇ</b>\n\n"
                    f"<b>ᴛᴏᴛᴀʟ:</b> <code>{total}</code>\n"
                    f"<b>ᴜᴘʟᴏᴀᴅᴇᴅ:</b> <code>{stats['uploaded']}</code>\n"
                    f"<b>ғᴀɪʟᴇᴅ:</b> <code>{stats['failed']}</code>",
                    reply_markup=None,
                )

        # If the user sent more files while this batch was running, remind
        # them that those files are safely waiting for the next /done.
        lock = get_batch_lock(uid)
        async with lock:
            waiting = PENDING_BATCHES.get(uid, [])
            if waiting:
                status = BATCH_STATUS_MESSAGES.get(uid)
                text = _queue_text(waiting, next_batch=False)
                if status:
                    await safe_edit_text(status, text, reply_markup=batch_queue_markup(running=False))
                else:
                    try:
                        BATCH_STATUS_MESSAGES[uid] = await reply_status(
                            waiting[-1].message, text, reply_markup=batch_queue_markup(running=False)
                        )
                    except Exception:
                        pass


async def _clear_waiting_queue(uid: int) -> tuple[list[QueuedItem], Message | None]:
    items = PENDING_BATCHES.pop(uid, [])
    for item in items:
        QUEUED_FILE_KEYS.discard((uid, item.unique))
    status = BATCH_STATUS_MESSAGES.pop(uid, None)
    return items, status


async def _start_batch_for_user(client: Client, uid: int, trigger: Message, *, delete_trigger: bool = False):
    lock = get_batch_lock(uid)
    async with lock:
        if uid in RUNNING_BATCHES:
            waiting = PENDING_BATCHES.get(uid, [])
            if waiting:
                await reply_status(
                    trigger,
                    "<b>ᴄᴜʀʀᴇɴᴛ ʙᴀᴛᴄʜ ᴀʟʀᴇᴀᴅʏ ᴘʀᴏᴄᴇssɪɴɢ.</b>\n\n"
                    f"<b>ɴᴇxᴛ ʙᴀᴛᴄʜ:</b> <code>{len(waiting)} ғɪʟᴇs</code>\n"
                    "sᴇɴᴅ /done ᴀғᴛᴇʀ ᴛʜᴇ ᴄᴜʀʀᴇɴᴛ ʙᴀᴛᴄʜ ʜᴀs ᴄᴏᴍᴘʟᴇᴛᴇᴅ.",
                )
            else:
                await reply_status(trigger, "<b>ʙᴀᴛᴄʜ ᴀʟʀᴇᴀᴅʏ ᴘʀᴏᴄᴇssɪɴɢ.</b>")
            return False

        queue = PENDING_BATCHES.get(uid, [])
        if not queue:
            await reply_status(
                trigger,
                "<b>ǫᴜᴇᴜᴇ ᴇᴍᴘᴛʏ.</b>\n\n"
                "sᴇɴᴅ ʏᴏᴜʀ ғɪʟᴇs ғɪʀsᴛ, ᴛʜᴇɴ sᴇɴᴅ <code>/done</code>.",
            )
            return False

        user = await settings_db.get_user(uid)
        if not user.get("format_template"):
            await reply_status(
                trigger,
                "<b>ᴀᴜᴛᴏ ʀᴇɴᴀᴍᴇ ғᴏʀᴍᴀᴛ ɪs ɴᴏᴛ sᴇᴛ.</b>\n\n"
                "ʏᴏᴜʀ ǫᴜᴇᴜᴇᴅ ғɪʟᴇs ᴀʀᴇ sᴀғᴇ. sᴇᴛ ᴛʜᴇ ʀᴇɴᴀᴍᴇ ғᴏʀᴍᴀᴛ ɪɴ /settings, ᴛʜᴇɴ sᴇɴᴅ /done.",
            )
            return False

        items = sort_queued_items(queue)
        PENDING_BATCHES[uid] = []
        batch_status = BATCH_STATUS_MESSAGES.pop(uid, None)
        if batch_status is None:
            batch_status = await reply_status(trigger, "<b>ʙᴀᴛᴄʜ sᴛᴀʀᴛɪɴɢ...</b>")
        RUNNING_BATCHES.add(uid)
        cancel_event = asyncio.Event()
        BATCH_CANCEL_EVENTS[uid] = cancel_event
        ACTIVE_BATCH_STATUS[uid] = batch_status

        task = asyncio.create_task(process_batch(client, uid, items, batch_status, cancel_event))
        BATCH_TASKS[uid] = task
        task.add_done_callback(
            lambda t: logger.error("Batch task crashed: %r", t.exception())
            if not t.cancelled() and t.exception() else None
        )

    if delete_trigger:
        try:
            await trigger.delete()
        except Exception:
            pass
    return True
