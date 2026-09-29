from __future__ import annotations

import asyncio
import html
import logging
import shutil
import uuid
from pathlib import Path

from PIL import Image
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from pyrogram import Client
from pyrogram.types import Message

from config import Config
from helper.rename.models import PreparedItem, QueuedItem
from helper.rename.parser import MEDIA_EXTS, VIDEO_EXTS, render_filename, styled_filename, target_container_extension
from helper.rename.state import DOWNLOAD_SLOTS
from helper.rename.transfer import download_media_reliable
from helper.rename.ui import reply_status
from helper.utils import duration_text, humanbytes, safe_edit_text, safe_filename

logger = logging.getLogger(__name__)


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
