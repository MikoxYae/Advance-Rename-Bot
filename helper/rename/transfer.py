from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from pyrogram import Client
from pyrogram.types import Message

from helper.rename.models import BatchCancelled
from helper.rename.state import DOWNLOAD_ATTEMPTS, DOWNLOAD_STALL_SECONDS, UPLOAD_SLOTS
from helper.rename.ui import reply_status
from helper.utils import progress_for_pyrogram, safe_edit_text

logger = logging.getLogger(__name__)


async def _download_progress(current, total, stage, status, started, state):
    state["last_activity"] = time.monotonic()
    state["current"] = current
    # file_id-only downloads can report total=0. We keep the size from the
    # Telegram media object as a reliable fallback.
    effective_total = int(total or state.get("total") or 0)
    if effective_total:
        state["total"] = effective_total
    await progress_for_pyrogram(current, effective_total, stage, status, started)


async def download_media_reliable(
    client: Client,
    source_message: Message,
    media,
    destination: Path,
    status: Message,
) -> str:
    """Download with accurate size, stall detection and retry."""
    last_error: Exception | None = None

    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            if destination.exists():
                destination.unlink()
        except Exception:
            pass

        state = {
            "last_activity": time.monotonic(),
            "current": 0,
            "total": int(getattr(media, "file_size", 0) or 0),
        }
        started = time.time()

        if attempt > 1:
            await safe_edit_text(
                status,
                f"<b>ᴅᴏᴡɴʟᴏᴀᴅ ʀᴇᴛʀʏ {attempt}/{DOWNLOAD_ATTEMPTS}...</b>\n\n"
                "<code>ʀᴇᴄᴏɴɴᴇᴄᴛɪɴɢ ᴛᴏ ᴛᴇʟᴇɢʀᴀᴍ...</code>",
            )

        logger.info(
            "Download attempt %s/%s file=%s size=%s destination=%s",
            attempt,
            DOWNLOAD_ATTEMPTS,
            getattr(media, "file_name", None) or getattr(media, "file_id", "")[:24],
            getattr(media, "file_size", 0),
            destination,
        )

        # Passing the Message gives Pyrogram the media size as well as file_id,
        # fixing the old '/ 0 B' progress output.
        task = asyncio.create_task(
            client.download_media(
                source_message,
                file_name=str(destination),
                progress=_download_progress,
                progress_args=("ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ", status, started, state),
            )
        )

        try:
            while True:
                done, _ = await asyncio.wait({task}, timeout=5)
                if task in done:
                    result = await task
                    if not result:
                        raise RuntimeError("Telegram returned no downloaded file")
                    result_path = Path(result)
                    if not result_path.exists() or result_path.stat().st_size <= 0:
                        raise RuntimeError("Downloaded file is empty")
                    logger.info("Download complete: %s (%s bytes)", result_path, result_path.stat().st_size)
                    return str(result_path)

                idle = time.monotonic() - state["last_activity"]
                if idle >= DOWNLOAD_STALL_SECONDS:
                    task.cancel()
                    try:
                        await task
                    except BaseException:
                        pass
                    raise TimeoutError(
                        f"No Telegram download data received for {DOWNLOAD_STALL_SECONDS} seconds"
                    )
        except Exception as exc:
            last_error = exc
            if not task.done():
                task.cancel()
                try:
                    await task
                except BaseException:
                    pass
            logger.warning("Download attempt %s failed: %s", attempt, exc)
            if attempt < DOWNLOAD_ATTEMPTS:
                await asyncio.sleep(2 * attempt)

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
            # A cancel request that arrived while waiting for a global upload
            # slot must stop this file before any new Telegram upload begins.
            if cancel_event is not None and cancel_event.is_set():
                if upload_started_event is not None:
                    upload_started_event.set()
                raise BatchCancelled("Batch cancelled before upload slot was used")

            # Signal only after a real global Telegram upload slot is acquired.
            # The producer uses this to start preparing/downloading the next file.
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
