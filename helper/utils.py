from __future__ import annotations

import asyncio
import math
import re
import time

from pyrogram.errors import FloodWait, MessageNotModified

from config import Config


INVALID_FILENAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_PROGRESS_LAST_EDIT: dict[tuple[int, int, str], float] = {}
_PROGRESS_TASKS: dict[tuple[int, int, str], asyncio.Task] = {}


def humanbytes(size: int | None) -> str:
    if not size:
        return "0 B"
    value = float(size)
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while value >= 1024 and index < len(units) - 1:
        value /= 1024
        index += 1
    return f"{value:.2f} {units[index]}"


def duration_text(seconds: int | float | None) -> str:
    if not seconds:
        return "00:00:00"
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def safe_filename(name: str, fallback: str = "renamed_file") -> str:
    name = INVALID_FILENAME.sub("_", name).replace("..", "_").strip(" .")
    name = re.sub(r"\s+", " ", name)
    if not name:
        name = fallback
    return name[:220]


async def safe_edit_text(message, text: str, reply_markup=None) -> bool:
    """Edit a text or photo-status message without killing the media job.

    Batch/progress UI uses photo messages.  For those messages Telegram requires
    edit_caption(), while normal messages use edit_text().  Keeping the choice
    here means download/upload callbacks can use one safe helper.
    """
    async def _edit():
        if getattr(message, "photo", None):
            await message.edit_caption(caption=text, reply_markup=reply_markup)
        else:
            await message.edit_text(text, reply_markup=reply_markup)

    try:
        await _edit()
        return True
    except MessageNotModified:
        return False
    except FloodWait as exc:
        # Do not block a media transfer for a long Telegram UI flood wait.
        wait = int(getattr(exc, "value", 0) or 0)
        if 0 < wait <= 3:
            await asyncio.sleep(wait)
            try:
                await _edit()
                return True
            except Exception:
                return False
        return False
    except Exception:
        return False


def _cleanup_progress_task(key, task):
    current = _PROGRESS_TASKS.get(key)
    if current is task:
        _PROGRESS_TASKS.pop(key, None)


async def progress_for_pyrogram(current, total, stage, message, start):
    """Non-blocking, Telegram-safe transfer progress.

    Pyrogram invokes progress callbacks very frequently. Awaiting a Telegram
    edit inside that callback pauses the transfer loop, so edits are dispatched
    as background tasks and throttled.
    """
    now = time.monotonic()
    key = (message.chat.id, message.id, str(stage))
    last = _PROGRESS_LAST_EDIT.get(key, 0.0)
    interval = float(getattr(Config, "PROGRESS_UPDATE_SECONDS", 4.0))
    if current != total and now - last < interval:
        return

    existing = _PROGRESS_TASKS.get(key)
    if existing and not existing.done():
        return

    _PROGRESS_LAST_EDIT[key] = now
    elapsed = max(time.time() - start, 0.001)
    percent = current * 100 / total if total else 0
    speed = current / elapsed
    remaining = max(total - current, 0) if total else 0
    eta = remaining / speed if speed and total else 0

    total_text = humanbytes(total) if total else "Unknown"
    percent_text = f"{percent:.1f}%" if total else "..."
    eta_text = f"{math.ceil(eta)}s" if total else "..."
    body = (
        f"<b>{stage}</b>\n\n"
        f"<b>ᴘʀᴏɢʀᴇss:</b> <code>{percent_text}</code>\n"
        f"<b>sɪᴢᴇ:</b> <code>{humanbytes(current)} / {total_text}</code>\n"
        f"<b>sᴘᴇᴇᴅ:</b> <code>{humanbytes(int(speed))}/s</code>\n"
        f"<b>ᴇᴛᴀ:</b> <code>{eta_text}</code>"
    )

    task = asyncio.create_task(safe_edit_text(message, body))
    _PROGRESS_TASKS[key] = task
    task.add_done_callback(lambda t, k=key: _cleanup_progress_task(k, t))

    if total and current >= total:
        _PROGRESS_LAST_EDIT.pop(key, None)
