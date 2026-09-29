from __future__ import annotations

import asyncio
import logging
import mimetypes
import shutil
from pathlib import Path

from pyrogram import Client
from pyrogram.types import Message

from helper.utils import humanbytes, safe_filename

logger = logging.getLogger(__name__)

FULL_DOWNLOAD_LIMIT = 50_000_000
STREAM_CHUNK_LIMIT = 5
STREAM_FIRST_CHUNK_TIMEOUT = 20
STREAM_NEXT_CHUNK_TIMEOUT = 12
MEDIAINFO_PROCESS_TIMEOUT = 20


def _media_from_message(message: Message | None):
    if not message:
        return None, None
    for name in ("document", "video", "audio", "voice", "animation", "video_note"):
        media = getattr(message, name, None)
        if media:
            return name, media
    return None, None


def _filename(media_type: str, media, message_id: int) -> str:
    name = getattr(media, "file_name", None)
    if name:
        return safe_filename(name, "media.bin")
    mime = getattr(media, "mime_type", None)
    ext = mimetypes.guess_extension(mime or "") or ""
    return safe_filename(f"{media_type}_{message_id}{ext}", "media.bin")


async def _download_probe_sample(
    client: Client,
    replied: Message,
    media,
    destination: Path,
) -> tuple[int, bool, int]:
    telegram_size = int(getattr(media, "file_size", 0) or 0)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if telegram_size and telegram_size <= FULL_DOWNLOAD_LIMIT:
        # Small media can be downloaded normally, but never allow it to hang forever.
        try:
            result = await asyncio.wait_for(
                client.download_media(replied, file_name=str(destination)),
                timeout=max(60, min(300, int(telegram_size / (256 * 1024)) + 30)),
            )
        except asyncio.TimeoutError as exc:
            raise RuntimeError("Telegram download timed out while reading this media") from exc

        actual = Path(result) if result else destination
        if actual != destination and actual.exists():
            shutil.move(str(actual), str(destination))
        written = destination.stat().st_size if destination.exists() else 0
        return telegram_size, False, written

    # Large Telegram media: WZML-style partial streaming, but with explicit
    # per-chunk timeouts so /mediainfo can never remain stuck indefinitely.
    written = 0
    chunks = 0
    stream = client.stream_media(replied, limit=STREAM_CHUNK_LIMIT)
    iterator = stream.__aiter__()

    try:
        with destination.open("wb") as output:
            for index in range(STREAM_CHUNK_LIMIT):
                timeout = STREAM_FIRST_CHUNK_TIMEOUT if index == 0 else STREAM_NEXT_CHUNK_TIMEOUT
                try:
                    chunk = await asyncio.wait_for(iterator.__anext__(), timeout=timeout)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    # If some bytes are already available, they are often enough for
                    # Matroska/EBML MediaInfo. Continue with that partial sample.
                    if written > 0:
                        logger.warning(
                            "MediaInfo stream timed out after %s chunk(s); using %s already sampled",
                            chunks,
                            humanbytes(written),
                        )
                        break
                    raise RuntimeError(
                        "Telegram did not return the first MediaInfo sample chunk in time"
                    )

                if not chunk:
                    continue
                output.write(chunk)
                output.flush()
                written += len(chunk)
                chunks += 1
    finally:
        close = getattr(stream, "aclose", None)
        if close:
            try:
                await close()
            except Exception:
                pass

    return telegram_size, True, written


async def _run_mediainfo_text(path: Path) -> str:
    binary = shutil.which("mediainfo")
    if not binary:
        raise RuntimeError("mediainfo is not installed. Run: sudo apt-get install -y mediainfo")

    proc = await asyncio.create_subprocess_exec(
        binary,
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=MEDIAINFO_PROCESS_TIMEOUT)
    except asyncio.TimeoutError as exc:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        try:
            await proc.wait()
        except Exception:
            pass
        raise RuntimeError("mediainfo process timed out while reading the sample") from exc

    text = stdout.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0 and not text:
        reason = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(reason[-1200:] or "mediainfo could not read the media sample")
    if not text:
        raise RuntimeError("mediainfo returned no information for this media")
    return text
