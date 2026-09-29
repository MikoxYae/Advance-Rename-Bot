from __future__ import annotations

import asyncio
import html
import logging
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Config
from helper.database import settings_db
from helper.utils import (
    duration_text,
    humanbytes,
    progress_for_pyrogram,
    safe_edit_text,
    safe_filename,
)

logger = logging.getLogger(__name__)

# Per-user batch collector. Files are only registered here when received;
# no Telegram download starts until the user sends /done.
PENDING_BATCHES: dict[int, list["QueuedItem"]] = {}
BATCH_LOCKS: dict[int, asyncio.Lock] = {}
USER_UPLOAD_LOCKS: dict[int, asyncio.Lock] = {}
BATCH_STATUS_MESSAGES: dict[int, Message] = {}
RUNNING_BATCHES: set[int] = set()
BATCH_TASKS: dict[int, asyncio.Task] = {}
BATCH_CANCEL_EVENTS: dict[int, asyncio.Event] = {}
ACTIVE_BATCH_STATUS: dict[int, Message] = {}
QUEUED_FILE_KEYS: set[tuple[int, str]] = set()

DOWNLOAD_SLOTS = asyncio.Semaphore(Config.DOWNLOAD_CONCURRENCY)
UPLOAD_SLOTS = asyncio.Semaphore(Config.UPLOAD_CONCURRENCY)

DOWNLOAD_STALL_SECONDS = 60
DOWNLOAD_ATTEMPTS = 3

SEASON_EPISODE_PATTERNS = [
    re.compile(r"(?i)\bS(?P<s>\d{1,3})[ ._-]*(?:E|EP)(?P<e>\d{1,4})\b"),
    re.compile(r"(?i)\bSeason[ ._-]*(?P<s>\d{1,3})[ ._-]*(?:Episode|Ep)[ ._-]*(?P<e>\d{1,4})\b"),
    re.compile(r"(?i)\[S(?P<s>\d{1,3})\][ ._-]*\[(?:E|EP)(?P<e>\d{1,4})\]"),
]
EPISODE_PATTERNS = [
    re.compile(r"(?i)(?:^|[ ._\-\[])E(?:P)?[ ._-]*(?P<e>\d{1,4})(?:\]|\b)"),
    re.compile(r"(?i)\bEpisode[ ._-]*(?P<e>\d{1,4})\b"),
]
SEASON_ONLY = re.compile(r"(?i)\bS(?:eason)?[ ._-]*(?P<s>\d{1,3})\b")
QUALITY_PATTERNS = [
    re.compile(r"(?i)\b(?P<q>2160p|1440p|1080p|720p|576p|540p|480p|360p|240p)\b"),
    re.compile(r"(?i)\b(?P<q>4k|2k|HDRip|HDTV|WEB[- .]?DL|WEBRip|BluRay)\b"),
]
MEDIA_EXTS = {
    ".mkv", ".mp4", ".m4v", ".mov", ".webm", ".avi", ".ts", ".m2ts",
    ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wav",
}
VIDEO_EXTS = {".mkv", ".mp4", ".m4v", ".mov", ".webm", ".avi", ".ts", ".m2ts"}

FONT_TAGS = {
    "normal": None,
    "bold": "b",
    "italic": "i",
    "underline": "u",
    "strike": "s",
    "code": "code",
    "spoiler": "__MARKDOWN_SPOILER__",
}


def extract_season_episode(filename: str):
    for pattern in SEASON_EPISODE_PATTERNS:
        match = pattern.search(filename)
        if match:
            return match.group("s"), match.group("e")

    season = None
    season_match = SEASON_ONLY.search(filename)
    if season_match:
        season = season_match.group("s")

    for pattern in EPISODE_PATTERNS:
        match = pattern.search(filename)
        if match:
            return season, match.group("e")

    candidates = re.findall(r"(?<!\d)(\d{1,4})(?!\d)", filename)
    ignored = {"2160", "1440", "1080", "720", "576", "540", "480", "360", "240", "264", "265"}
    filtered = [
        item for item in candidates
        if item not in ignored and not (len(item) == 4 and 1900 <= int(item) <= 2099)
    ]
    episode = filtered[-1] if filtered else None
    return season, episode


def extract_quality(filename: str):
    for pattern in QUALITY_PATTERNS:
        match = pattern.search(filename)
        if match:
            return match.group("q")
    return "Unknown"


def render_filename(template: str, original: str) -> str:
    season, episode = extract_season_episode(original)
    quality = extract_quality(original)
    values = {
        "{season}": season or "XX",
        "{episode}": episode or "XX",
        "{quality}": quality,
    }
    result = template
    for key, val in values.items():
        result = result.replace(key, val)
    return safe_filename(result, "renamed_file")


def styled_filename(filename: str, style: str | None) -> str:
    """Return an HTML-safe filename using the user's Telegram caption font."""
    escaped = html.escape(filename)
    tag = FONT_TAGS.get((style or "code").lower(), "code")
    if not tag:
        return escaped
    if tag == "__MARKDOWN_SPOILER__":
        return f"||{escaped}||"
    return f"<{tag}>{escaped}</{tag}>"


def target_container_extension(original_ext: str, user: dict) -> str:
    """Choose the real output container extension for video files."""
    ext = (original_ext or "").lower()
    requested = (user.get("container_format") or "same").lower()
    if ext not in VIDEO_EXTS or requested == "same":
        return original_ext
    if requested == "mkv":
        return ".mkv"
    if requested == "mp4":
        return ".mp4"
    return original_ext


async def remux_container(input_path: Path, output_path: Path, target: str) -> None:
    """Remux media without re-encoding. MP4 falls back to A/V-only if a subtitle/attachment is incompatible."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg not installed")

    target = target.lower()
    if target == "mkv":
        attempts = [
            [
                ffmpeg, "-y", "-i", str(input_path), "-map", "0", "-c", "copy",
                "-loglevel", "error", str(output_path),
            ],
            [
                ffmpeg, "-y", "-i", str(input_path),
                "-map", "0:v?", "-map", "0:a?", "-map", "0:s?",
                "-c:v", "copy", "-c:a", "copy", "-c:s", "srt",
                "-loglevel", "error", str(output_path),
            ],
            [
                ffmpeg, "-y", "-i", str(input_path),
                "-map", "0:v?", "-map", "0:a?", "-c", "copy",
                "-loglevel", "error", str(output_path),
            ],
        ]
    elif target == "mp4":
        # First preserve video/audio and compatible text subtitles. Attachments are
        # intentionally excluded because MP4 does not support MKV attachments.
        attempts = [
            [
                ffmpeg, "-y", "-i", str(input_path),
                "-map", "0:v?", "-map", "0:a?", "-map", "0:s?",
                "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
                "-movflags", "+faststart", "-loglevel", "error", str(output_path),
            ],
            [
                ffmpeg, "-y", "-i", str(input_path),
                "-map", "0:v?", "-map", "0:a?",
                "-c", "copy", "-movflags", "+faststart",
                "-loglevel", "error", str(output_path),
            ],
        ]
    else:
        raise RuntimeError(f"Unsupported container: {target}")

    errors = []
    for cmd in attempts:
        output_path.unlink(missing_ok=True)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
            return
        errors.append(stderr.decode(errors="ignore")[-500:])

    raise RuntimeError("Container remux failed: " + (errors[-1] if errors else "unknown ffmpeg error"))


async def media_duration(path: str, message: Message) -> int:
    if message.video and message.video.duration:
        return int(message.video.duration)
    if message.audio and message.audio.duration:
        return int(message.audio.duration)
    try:
        parser = createParser(path)
        if not parser:
            return 0
        with parser:
            metadata = extractMetadata(parser)
            if metadata and metadata.has("duration"):
                return int(metadata.get("duration").total_seconds())
    except Exception:
        pass
    return 0


async def prepare_thumbnail(client: Client, file_id: str | None, workdir: Path):
    if not file_id:
        return None
    raw = workdir / "thumb_source"
    out = workdir / "thumb.jpg"
    try:
        downloaded = await client.download_media(file_id, file_name=str(raw))
        with Image.open(downloaded) as image:
            image = image.convert("RGB")
            image.thumbnail((320, 320))
            image.save(out, "JPEG", quality=85, optimize=True)
        return str(out)
    except Exception as exc:
        logger.warning("Thumbnail failed: %s", exc)
        return None


async def apply_metadata(input_path: Path, output_path: Path, user: dict):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg not installed")

    cmd = [ffmpeg, "-y", "-i", str(input_path), "-map", "0", "-c", "copy"]
    global_fields = {
        "title": user.get("meta_title"),
        "artist": user.get("meta_artist"),
        "author": user.get("meta_author"),
    }
    for key, value in global_fields.items():
        if value:
            cmd += ["-metadata", f"{key}={value}"]
    if user.get("meta_video"):
        cmd += ["-metadata:s:v", f"title={user['meta_video']}"]
    if user.get("meta_audio"):
        cmd += ["-metadata:s:a", f"title={user['meta_audio']}"]
    if user.get("meta_subtitle"):
        cmd += ["-metadata:s:s", f"title={user['meta_subtitle']}"]
    cmd += ["-loglevel", "error", str(output_path)]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(stderr.decode(errors="ignore")[-600:] or "FFmpeg metadata failed")


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


@dataclass
class QueuedItem:
    message: Message
    media: object
    unique: str
    original_name: str


@dataclass
class PreparedItem:
    queued: QueuedItem
    sequence: int
    workdir: Path
    final_path: Path
    output_type: str
    caption: str
    thumb: str | None
    upload_started: asyncio.Event = field(default_factory=asyncio.Event)


def get_batch_lock(user_id: int) -> asyncio.Lock:
    lock = BATCH_LOCKS.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        BATCH_LOCKS[user_id] = lock
    return lock


def get_user_upload_lock(user_id: int) -> asyncio.Lock:
    """One upload at a time per user, regardless of global concurrency."""
    lock = USER_UPLOAD_LOCKS.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        USER_UPLOAD_LOCKS[user_id] = lock
    return lock


async def reply_status(message: Message, caption: str, reply_markup=None) -> Message:
    """Send one branded status photo; later stages only edit its caption."""
    try:
        return await message.reply_photo(Config.STATUS_PIC, caption=caption, reply_markup=reply_markup)
    except Exception:
        # Never make processing depend on a decorative image being reachable.
        return await message.reply_text(caption, reply_markup=reply_markup)


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
        "<b>ᴀʟʟ ғɪʟᴇs sᴇɴᴅ ʜᴏ ɢᴀʏᴇ ʜᴀɪɴ ᴛᴏ /done sᴇɴᴅ ᴋʀᴏ.</b>",
        "<code>/done</code> → ᴘʀᴏᴄᴇssɪɴɢ sᴛᴀʀᴛ",
        "<code>/clear</code> → ᴡᴀɪᴛɪɴɢ ǫᴜᴇᴜᴇ ᴄʟᴇᴀʀ",
        "<code>/cancel</code> → ʙᴀᴛᴄʜ ᴄᴀɴᴄᴇʟ",
    ]
    if next_batch:
        lines += ["", "<blockquote>ᴄᴜʀʀᴇɴᴛ ʙᴀᴛᴄʜ ᴄʜᴀʟ ʀᴀʜᴀ ʜᴀɪ. ʏᴇ ғɪʟᴇs ɴᴇxᴛ ʙᴀᴛᴄʜ ᴍᴇ ʀᴀʜᴇɴɢɪ.</blockquote>"]
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


class BatchCancelled(Exception):
    pass


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


async def prepare_batch_item(
    client: Client,
    uid: int,
    item: QueuedItem,
    user: dict,
    index: int,
    total: int,
) -> PreparedItem:
    message = item.message
    media = item.media
    original_name = item.original_name
    template = user.get("format_template")
    if not template:
        raise RuntimeError("Auto rename format is not set")

    ext = Path(original_name).suffix
    target_ext = target_container_extension(ext, user)
    renamed_stem = render_filename(template, original_name)
    new_name = safe_filename(renamed_stem + target_ext, "renamed" + (target_ext or ext or ".bin"))
    workdir = Config.WORK_DIR / str(uid) / f"batch_{message.id}_{uuid.uuid4().hex[:8]}"
    source_path = workdir / ("source" + (ext or ".bin"))
    renamed_path = workdir / new_name
    workdir.mkdir(parents=True, exist_ok=True)

    status = await reply_status(
        message,
        f"<b>ғɪʟᴇ {index}/{total}</b>\n\n"
        "<b>ᴄᴏɴɴᴇᴄᴛɪɴɢ ᴛᴏ ᴛᴇʟᴇɢʀᴀᴍ...</b>",
    )

    try:
        async with DOWNLOAD_SLOTS:
            path = await download_media_reliable(client, message, media, source_path, status)

        source = Path(path)
        final_path = renamed_path
        processing_source = source

        if target_ext.lower() != ext.lower() and ext.lower() in VIDEO_EXTS:
            await safe_edit_text(
                status,
                f"<b>ғɪʟᴇ {index}/{total}</b>\n\n"
                f"<b>ʀᴇᴍᴜxɪɴɢ ᴛᴏ {target_ext.lstrip('.').upper()}...</b>\n"
                "<code>ᴄᴏᴘʏ sᴛʀᴇᴀᴍs • ɴᴏ ʀᴇ-ᴇɴᴄᴏᴅᴇ</code>",
            )
            remuxed = workdir / ("container" + target_ext)
            await remux_container(source, remuxed, target_ext.lstrip("."))
            processing_source = remuxed

        if bool(user.get("metadata_enabled")) and target_ext.lower() in MEDIA_EXTS:
            await safe_edit_text(
                status,
                f"<b>ғɪʟᴇ {index}/{total}</b>\n\n<b>ᴘʀᴏᴄᴇssɪɴɢ ᴍᴇᴛᴀᴅᴀᴛᴀ...</b>",
            )
            try:
                await apply_metadata(processing_source, renamed_path, user)
            except Exception as exc:
                logger.warning("Metadata skipped for %s: %s", original_name, exc)
                renamed_path.unlink(missing_ok=True)
                processing_source.replace(renamed_path)
        else:
            processing_source.replace(renamed_path)

        caption_template = user.get("caption")
        duration = 0
        if caption_template and "{duration}" in caption_template:
            duration = await media_duration(str(final_path), message)

        filename_html = styled_filename(new_name, user.get("filename_font"))
        plain_filename = html.escape(new_name)
        if caption_template:
            caption = (
                caption_template
                .replace("{filename}", filename_html)
                .replace("{plain_filename}", plain_filename)
                .replace("{filesize}", humanbytes(final_path.stat().st_size if final_path.exists() else getattr(media, "file_size", 0)))
                .replace("{duration}", duration_text(duration))
            )
        else:
            caption = filename_html

        thumb = await prepare_thumbnail(client, user.get("thumbnail_file_id"), workdir)
        input_type = "document" if message.document else "video" if message.video else "audio"
        preference = (user.get("media_type") or "same").lower()
        output_type = input_type if preference == "same" else preference

        try:
            await status.delete()
        except Exception:
            pass

        return PreparedItem(
            queued=item,
            sequence=index,
            workdir=workdir,
            final_path=final_path,
            output_type=output_type,
            caption=caption,
            thumb=thumb,
        )
    except Exception as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        await safe_edit_text(
            status,
            f"<b>ғɪʟᴇ {index}/{total} ғᴀɪʟᴇᴅ</b>\n\n"
            f"<code>{html.escape(str(exc)[:700])}</code>",
        )
        raise


async def process_batch(
    client: Client,
    uid: int,
    items: list[QueuedItem],
    batch_status: Message | None,
    cancel_event: asyncio.Event,
) -> None:
    items = sorted(items, key=lambda item: item.message.id)
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
            "ɴᴇxᴛ ᴅᴏᴡɴʟᴏᴀᴅ ᴄᴜʀʀᴇɴᴛ ᴜᴘʟᴏᴀᴅ sᴛᴀʀᴛ ʜᴏɴᴇ ᴋᴇ ʙᴀᴀᴅ ʜɪ sᴛᴀʀᴛ ʜᴏɢᴀ.\n"
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


@Client.on_message(filters.private & (filters.document | filters.video | filters.audio), group=5)
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
                    "ᴄᴜʀʀᴇɴᴛ ʙᴀᴛᴄʜ ᴄᴏᴍᴘʟᴇᴛᴇ ʜᴏɴᴇ ᴋᴇ ʙᴀᴀᴅ /done sᴇɴᴅ ᴋʀᴏ.",
                )
            else:
                await reply_status(trigger, "<b>ʙᴀᴛᴄʜ ᴀʟʀᴇᴀᴅʏ ᴘʀᴏᴄᴇssɪɴɢ.</b>")
            return False

        queue = PENDING_BATCHES.get(uid, [])
        if not queue:
            await reply_status(
                trigger,
                "<b>ǫᴜᴇᴜᴇ ᴇᴍᴘᴛʏ.</b>\n\n"
                "ғɪʟᴇs sᴇɴᴅ ᴋʀᴏ, ᴘʜɪʀ <code>/done</code> sᴇɴᴅ ᴋʀᴏ.",
            )
            return False

        user = await settings_db.get_user(uid)
        if not user.get("format_template"):
            await reply_status(
                trigger,
                "<b>ᴀᴜᴛᴏ ʀᴇɴᴀᴍᴇ ғᴏʀᴍᴀᴛ ɪs ɴᴏᴛ sᴇᴛ.</b>\n\n"
                "ǫᴜᴇᴜᴇ sᴀғᴇ ʜᴀɪ. /settings ᴍᴇ ғᴏʀᴍᴀᴛ sᴇᴛ ᴋʀᴋᴇ /done sᴇɴᴅ ᴋʀᴏ.",
            )
            return False

        items = sorted(queue, key=lambda item: item.message.id)
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


@Client.on_message(filters.private & filters.command("done"), group=4)
async def done_handler(client: Client, message: Message):
    await _start_batch_for_user(client, message.from_user.id, message, delete_trigger=True)


@Client.on_message(filters.private & filters.command("clear"), group=4)
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


@Client.on_message(filters.private & filters.command("cancel"), group=4)
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


@Client.on_callback_query(filters.regex(r"^batch:(done|clear|cancel)$"), group=3)
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

