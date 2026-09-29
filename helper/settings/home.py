from __future__ import annotations

from pyrogram import Client
from pyrogram.types import CallbackQuery, Message

from config import Config
from helper.buttons import send_photo_styled
from helper.database import settings_db
from helper.settings.common import b, edit_panel, kb, value
from helper.settings.state import FONT_STYLES


def _page_one_text(user: dict) -> str:
    fmt = value(user.get("format_template"))
    media = (user.get("media_type") or "same").upper()
    container = (user.get("container_format") or "same").upper()
    font = FONT_STYLES.get((user.get("filename_font") or "code").lower(), "ᴄᴏᴅᴇ")
    return (
        "<b>ʀᴇɴᴀᴍᴇ sᴇᴛᴛɪɴɢs • ᴘᴀɢᴇ 1/2</b>\n\n"
        "<blockquote>ʀᴇɴᴀᴍᴇ ᴀɴᴅ ᴏᴜᴛᴘᴜᴛ ᴄᴏɴᴛʀᴏʟs. ᴜsᴇ ɴᴇxᴛ ᴛᴏ ᴏᴘᴇɴ ᴀᴅᴠᴀɴᴄᴇᴅ sᴇᴛᴛɪɴɢs.</blockquote>\n\n"
        f"<b>ᴀᴜᴛᴏ ʀᴇɴᴀᴍᴇ:</b> <code>{fmt}</code>\n"
        f"<b>ᴍᴇᴅɪᴀ ᴛʏᴘᴇ:</b> <code>{media}</code>\n"
        f"<b>ғɪʟᴇ ғᴏʀᴍᴀᴛ:</b> <code>{container}</code>\n"
        f"<b>ғɪʟᴇɴᴀᴍᴇ ғᴏɴᴛ:</b> <code>{font}</code>"
    )


def _page_two_text(user: dict) -> str:
    caption = "sᴀᴠᴇᴅ" if user.get("caption") else "ɴᴏᴛ sᴇᴛ"
    thumb = "sᴀᴠᴇᴅ" if user.get("thumbnail_file_id") else "ɴᴏᴛ sᴇᴛ"
    metadata = "ᴏɴ" if bool(user.get("metadata_enabled")) else "ᴏғғ"
    ui_pics = "ᴄᴜsᴛᴏᴍ" if any(
        user.get(k) for k in ("ui_start_pic", "ui_settings_pic", "ui_status_pic")
    ) else "ᴅᴇғᴀᴜʟᴛ"
    return (
        "<b>ʀᴇɴᴀᴍᴇ sᴇᴛᴛɪɴɢs • ᴘᴀɢᴇ 2/2</b>\n\n"
        "<blockquote>ᴘʀᴇsᴇɴᴛᴀᴛɪᴏɴ, ᴍᴇᴛᴀᴅᴀᴛᴀ, ᴀɴᴅ ɪɴᴛᴇʀғᴀᴄᴇ ᴄᴏɴᴛʀᴏʟs.</blockquote>\n\n"
        f"<b>ᴛʜᴜᴍʙɴᴀɪʟ:</b> <code>{thumb}</code>\n"
        f"<b>ᴄᴀᴘᴛɪᴏɴ:</b> <code>{caption}</code>\n"
        f"<b>ᴍᴇᴛᴀᴅᴀᴛᴀ:</b> <code>{metadata}</code>\n"
        f"<b>ᴜɪ ᴘɪᴄᴛᴜʀᴇs:</b> <code>{ui_pics}</code>"
    )


def _page_one_markup():
    return kb([
        [b("ᴀᴜᴛᴏ ʀᴇɴᴀᴍᴇ", "settings:rename")],
        [b("ᴍᴇᴅɪᴀ ᴛʏᴘᴇ", "settings:media"), b("ғɪʟᴇ ғᴏʀᴍᴀᴛ", "settings:container")],
        [b("ғɪʟᴇɴᴀᴍᴇ ғᴏɴᴛ", "settings:font")],
        [b("ɴᴇxᴛ • ᴘᴀɢᴇ 2", "settings:page:2")],
        [b("ᴄʟᴏsᴇ", "settings:close")],
    ])


def _page_two_markup():
    return kb([
        [b("ᴛʜᴜᴍʙɴᴀɪʟ", "settings:thumb"), b("ᴄᴀᴘᴛɪᴏɴ", "settings:caption")],
        [b("ᴍᴇᴛᴀᴅᴀᴛᴀ", "settings:metadata")],
        [b("ᴜɪ ᴘɪᴄᴛᴜʀᴇs", "settings:pics")],
        [b("ᴘʀᴇᴠɪᴏᴜs • ᴘᴀɢᴇ 1", "settings:page:1")],
        [b("ᴄʟᴏsᴇ", "settings:close")],
    ])


async def send_settings(client: Client, message: Message):
    user = await settings_db.get_user(message.from_user.id)
    photo = user.get("ui_settings_pic") or Config.SETTINGS_PIC
    text = _page_one_text(user)
    markup = _page_one_markup()
    try:
        await send_photo_styled(client, message, photo, text, markup)
    except Exception:
        await message.reply_photo(photo, caption=text, reply_markup=markup)


async def show_page(query: CallbackQuery, page: int = 1, *, answered: bool = False):
    """Render a settings page reliably on the current panel.

    Page navigation is intentionally isolated from the generic settings router.
    If an in-place edit fails (old Telegram client/message edge case), we replace
    the panel with a fresh photo message instead of leaving the user stuck.
    """
    user = await settings_db.get_user(query.from_user.id)
    text = _page_two_text(user) if page == 2 else _page_one_text(user)
    markup = _page_two_markup() if page == 2 else _page_one_markup()

    if not answered:
        try:
            await query.answer()
        except Exception:
            pass

    # Fast path: keep the same settings photo-message and only edit caption/keyboard.
    try:
        from helper.buttons import edit_message_styled
        await edit_message_styled(query.message, text, markup)
        return
    except Exception:
        pass

    # Native Pyrogram fallback for older Bot API/client combinations.
    try:
        if query.message.photo:
            await query.message.edit_caption(caption=text, reply_markup=markup)
        else:
            await query.message.edit_text(text=text, reply_markup=markup)
        return
    except Exception:
        pass

    # Last-resort recovery: send a fresh settings panel so navigation can never
    # become a dead button. Keep only one visible panel when deletion succeeds.
    photo = user.get("ui_settings_pic") or Config.SETTINGS_PIC
    try:
        fresh = await send_photo_styled(query._client, query.message, photo, text, markup)
    except Exception:
        fresh = await query.message.reply_photo(photo, caption=text, reply_markup=markup)
    try:
        await query.message.delete()
    except Exception:
        pass
    return fresh


async def show_home(query: CallbackQuery):
    """Backward-compatible alias for the first settings page."""
    await show_page(query, 1)
