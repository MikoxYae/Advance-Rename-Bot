from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from pyrogram import Client
from pyrogram.types import Message

from helper.rename.models import BatchCancelled
from helper.rename.state import (
    DOWNLOAD_ATTEMPTS,
    DOWNLOAD_RETRY_BASE_SECONDS,
    DOWNLOAD_STALL_SECONDS,
    UPLOAD_SLOTS,
)
from helper.rename.ui import reply_status
from helper.utils import progress_for_pyrogram, safe_edit_text

logger = logging.getLogger(__name__)


async def _download_progress(current, total, stage, status, started, state):
    """Track real byte movement, not merely callback activity.

    Pyrogram can occasionally invoke the progress callback repeatedly with the
    same byte count while a DC/network connection is stuck.  Updating the
    watchdog timestamp for those duplicate callbacks makes a stalled transfer
    look alive forever.  Only genuine forward byte movement resets the stall
    timer.
    """
    current = int(current or 0)
    previous = int(state.get("current", 0) or 0)

    if current > previous:
        now = time.monotonic()
        state["last_progress_at"] = now
        state["last_progress_bytes"] = current
        state["current"] = current
    elif current < previous:
        # Defensive reset if Pyrogram restarts the transfer internally.
        state["last_progress_at"] = time.monotonic()
        state["last_progress_bytes"] = current
        state["current"] = current

    effective_total = int(total or state.get("total") or 0)
    if effective_total:
        state["total"] = effective_total

    await progress_for_pyrogram(current, effective_total, stage, status, started)


def _download_source(source_message: Message, media, attempt: int):
    """Alternate between Message and file_id across retries.

    Message mode is preferred because it carries full media metadata.  A fresh
    file-id request can recover from an occasional stale message/DC transfer.
    """
    file_id = getattr(media, "file_id", None)
    if attempt % 2 == 0 and file_id:
        return file_id, "file_id"
    return source_message, "message"


async def download_media_reliable(
    client: Client,
    source_message: Message,
    media,
    destination: Path,
    status: Message,
) -> str:
    """Download a Telegram file with byte-based stall detection and retries."""
    last_error: Exception | None = None
    expected_size = int(getattr(media, "file_size", 0) or 0)

    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            destination.unlink(missing_ok=True)
        except Exception:
            pass

        state = {
            "last_progress_at": time.monotonic(),
            "last_progress_bytes": 0,
            "current": 0,
            "total": expected_size,
        }
        started = time.time()
        source, source_mode = _download_source(source_message, media, attempt)

        if attempt > 1:
            reason = str(last_error or "connection stalled")
            await safe_edit_text(
                status,
                f"<b>ᴅᴏᴡɴʟᴏᴀᴅ ʀᴇᴛʀʏ {attempt}/{DOWNLOAD_ATTEMPTS}</b>\n\n"
                f"<b>ᴍᴏᴅᴇ:</b> <code>{source_mode}</code>\n"
                f"<b>ʀᴇᴀsᴏɴ:</b> <code>{reason[:180]}</code>\n\n"
                "<code>ʀᴇᴄᴏɴɴᴇᴄᴛɪɴɢ ᴛᴏ ᴛᴇʟᴇɢʀᴀᴍ...</code>",
            )

        logger.info(
            "Download attempt %s/%s mode=%s file=%s size=%s destination=%s",
            attempt,
            DOWNLOAD_ATTEMPTS,
            source_mode,
            getattr(media, "file_name", None) or str(getattr(media, "file_id", ""))[:24],
            expected_size,
            destination,
        )

        task = asyncio.create_task(
            client.download_media(
                source,
                file_name=str(destination),
                progress=_download_progress,
                progress_args=("ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ", status, started, state),
            )
        )

        try:
            while True:
                done, _ = await asyncio.wait({task}, timeout=3)
                if task in done:
                    result = await task
                    if not result:
                        raise RuntimeError("Telegram returned no downloaded file")

                    result_path = Path(result)
                    if not result_path.exists():
                        raise RuntimeError("Downloaded file was not created")

                    actual_size = result_path.stat().st_size
                    if actual_size <= 0:
                        raise RuntimeError("Downloaded file is empty")
                    if expected_size and actual_size < expected_size:
                        raise RuntimeError(
                            f"Incomplete download: {actual_size}/{expected_size} bytes"
                        )

                    logger.info(
                        "Download complete attempt=%s mode=%s path=%s bytes=%s",
                        attempt,
                        source_mode,
                        result_path,
                        actual_size,
                    )
                    return str(result_path)

                idle = time.monotonic() - float(state["last_progress_at"])
                if idle >= DOWNLOAD_STALL_SECONDS:
                    bytes_done = int(state.get("current", 0) or 0)
                    task.cancel()
                    try:
                        await task
                    except BaseException:
                        pass
                    raise TimeoutError(
                        "Telegram download stalled: no new bytes for "
                        f"{DOWNLOAD_STALL_SECONDS}s (received {bytes_done} bytes)"
                    )

        except Exception as exc:
            last_error = exc
            if not task.done():
                task.cancel()
                try:
                    await task
                except BaseException:
                    pass

            try:
                destination.unlink(missing_ok=True)
            except Exception:
                pass

            logger.warning(
                "Download attempt %s/%s failed mode=%s: %s",
                attempt,
                DOWNLOAD_ATTEMPTS,
                source_mode,
                exc,
            )

            if attempt < DOWNLOAD_ATTEMPTS:
                # Short bounded backoff: enough to let a bad DC socket reset,
                # without leaving a user staring at a stuck status for minutes.
                await asyncio.sleep(min(DOWNLOAD_RETRY_BASE_SECONDS * attempt, 8))

    raise RuntimeError(f"Download failed after {DOWNLOAD_ATTEMPTS} attempts: {last_error}")


async def send_output(
    client: Client,
    message: Message,
    path: str,
    output_type: str,
    caption: str,
    thumb: str | None,
    upload_started_event: asyncio.Event | None = None,
    cancel_event: asyncio.Event | None = None,
):
    if cancel_event is not None and cancel_event.is_set():
        if upload_started_event is not None:
            upload_started_event.set()
        raise BatchCancelled("Batch cancelled before upload started")

    progress_message = await reply_status(message, "<b>ᴘʀᴇᴘᴀʀɪɴɢ ᴜᴘʟᴏᴀᴅ...</b>")

    async def send_as(kind: str):
        started = time.time()
        common = {
            "chat_id": message.chat.id,
            "caption": caption,
            "progress": progress_for_pyrogram,
            "progress_args": ("ᴜᴘʟᴏᴀᴅɪɴɢ", progress_message, started),
        }
        if kind == "video":
            return await client.send_video(
                video=path,
                thumb=thumb,
                supports_streaming=True,
                **common,
            )
        if kind == "audio":
            return await client.send_audio(audio=path, thumb=thumb, **common)
        return await client.send_document(document=path, thumb=thumb, **common)

    try:
        async with UPLOAD_SLOTS:
            if cancel_event is not None and cancel_event.is_set():
                if upload_started_event is not None:
                    upload_started_event.set()
                raise BatchCancelled("Batch cancelled before upload slot was used")

            if upload_started_event is not None:
                upload_started_event.set()
            try:
                await send_as(output_type)
            except Exception:
                if output_type == "document":
                    raise
                await safe_edit_text(
                    progress_message,
                    "<b>ᴍᴇᴅɪᴀ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ. sᴇɴᴅɪɴɢ ᴀs ᴅᴏᴄᴜᴍᴇɴᴛ...</b>",
                )
                await send_as("document")
    finally:
        try:
            await progress_message.delete()
        except Exception:
            pass
