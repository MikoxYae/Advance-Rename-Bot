from __future__ import annotations

import asyncio
import html
import logging
import shutil
import uuid
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Config
from helper.mediainfo_probe import _download_probe_sample, _filename, _media_from_message, _run_mediainfo_text
from helper.mediainfo_report import _build_report_html, _save_report
from helper.buttons import edit_message_styled
from helper.utils import humanbytes, safe_edit_text
from route import cleanup_reports

logger = logging.getLogger(__name__)


async def _safe_edit(message: Message, text: str, reply_markup=None) -> None:
    try:
        if reply_markup is not None:
            await edit_message_styled(message, text, reply_markup, disable_preview=True)
        else:
            await message.edit_text(text, disable_web_page_preview=True)
    except MessageNotModified:
        pass
    except FloodWait as exc:
        wait = int(getattr(exc, "value", 0) or 0)
        if 0 < wait <= 5:
            await asyncio.sleep(wait)
            try:
                if reply_markup is not None:
                    await edit_message_styled(message, text, reply_markup, disable_preview=True)
                else:
                    await message.edit_text(text, disable_web_page_preview=True)
            except Exception:
                pass
    except Exception:
        logger.exception("Could not edit MediaInfo status message")


async def mediainfo_handler(client: Client, message: Message):
    replied = message.reply_to_message
    media_type, media = _media_from_message(replied)
    if not replied or not media:
        return await message.reply_text(
            "<b>ᴍᴇᴅɪᴀɪɴғᴏ</b>\n\n"
            "<blockquote>ʀᴇᴘʟʏ ᴛᴏ ᴀ ᴍᴇᴅɪᴀ ғɪʟᴇ ᴡɪᴛʜ <code>/mediainfo</code>.</blockquote>"
        )

    filename = _filename(media_type, media, replied.id)
    uid = message.from_user.id
    workdir = Config.WORK_DIR / "mediainfo_probe" / str(uid) / f"{message.id}_{uuid.uuid4().hex[:8]}"
    workdir.mkdir(parents=True, exist_ok=True)
    local_path = workdir / filename

    status = await message.reply_text(
        "<b>ᴍᴇᴅɪᴀɪɴғᴏ</b>\n\n<code>ᴀɴᴀʟʏᴢɪɴɢ ᴍᴇᴅɪᴀ...</code>"
    )

    try:
        await _safe_edit(
            status,
            "<b>ᴍᴇᴅɪᴀɪɴғᴏ</b>\n\n<code>ʀᴇᴀᴅɪɴɢ ᴍᴇᴅɪᴀ sᴀᴍᴘʟᴇ...</code>",
        )
        file_size, partial, local_bytes = await _download_probe_sample(client, replied, media, local_path)
        if not local_path.exists() or local_bytes <= 0:
            raise RuntimeError("Telegram returned no media data")

        logger.info(
            "MediaInfo probe prepared: %s | source=%s | local=%s | partial=%s",
            filename,
            humanbytes(file_size),
            humanbytes(local_bytes),
            partial,
        )

        await _safe_edit(
            status,
            "<b>ᴍᴇᴅɪᴀɪɴғᴏ</b>\n\n"
            f"<code>sᴀᴍᴘʟᴇ ʀᴇᴀᴅʏ: {html.escape(humanbytes(local_bytes))}</code>\n"
            "<code>ʀᴜɴɴɪɴɢ ᴍᴇᴅɪᴀɪɴғᴏ...</code>",
        )
        output = await _run_mediainfo_text(local_path)

        await _safe_edit(
            status,
            "<b>ᴍᴇᴅɪᴀɪɴғᴏ</b>\n\n<code>ʙᴜɪʟᴅɪɴɢ ʀᴇᴘᴏʀᴛ...</code>",
        )
        page_html = _build_report_html(output, filename, file_size, partial, local_bytes)
        page_url, _ = await _save_report(page_html)
        await cleanup_reports()

        result = (
            "<b>ᴍᴇᴅɪᴀɪɴғᴏ</b>\n\n"
            f"<blockquote><b>ғɪʟᴇ:</b> <code>{html.escape(filename)}</code>\n"
            f"<b>sɪᴢᴇ:</b> <code>{html.escape(humanbytes(file_size)) if file_size else 'Unknown'}</code>\n"
            f"<b>ᴘʀᴏʙᴇ:</b> <code>{'Partial stream' if partial else 'Full file'}</code></blockquote>\n\n"
            "<b>ʀᴇᴘᴏʀᴛ ʀᴇᴀᴅʏ.</b>"
        )
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("ᴏᴘᴇɴ ᴍᴇᴅɪᴀɪɴғᴏ", url=page_url)]]
        )
        await _safe_edit(status, result, keyboard)

    except Exception as exc:
        logger.exception("MediaInfo failed for %s", filename)
        await _safe_edit(
            status,
            "<b>ᴍᴇᴅɪᴀɪɴғᴏ ғᴀɪʟᴇᴅ</b>\n\n"
            f"<code>{html.escape(str(exc)[:1200])}</code>",
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
