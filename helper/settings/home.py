from __future__ import annotations

from pyrogram import Client
from pyrogram.types import CallbackQuery, Message

from config import Config
from helper.buttons import send_photo_styled
from helper.database import settings_db
from helper.settings.common import b, edit_panel, kb, value
from helper.settings.state import FONT_STYLES


async def send_settings(client: Client, message: Message):
    user = await settings_db.get_user(message.from_user.id)
    fmt = value(user.get("format_template"))
    caption = "sᴀᴠᴇᴅ" if user.get("caption") else "ɴᴏᴛ sᴇᴛ"
    thumb = "sᴀᴠᴇᴅ" if user.get("thumbnail_file_id") else "ɴᴏᴛ sᴇᴛ"
    metadata = "ᴏɴ" if bool(user.get("metadata_enabled")) else "ᴏғғ"
    ui_pics = "ᴄᴜsᴛᴏᴍ" if any(user.get(k) for k in ("ui_start_pic", "ui_settings_pic", "ui_status_pic")) else "ᴅᴇғᴀᴜʟᴛ"
    media = (user.get("media_type") or "same").upper()
    container = (user.get("container_format") or "same").upper()
    font = FONT_STYLES.get((user.get("filename_font") or "code").lower(), "ᴄᴏᴅᴇ")
    text = (
        "<b>ʀᴇɴᴀᴍᴇ sᴇᴛᴛɪɴɢs</b>\n\n"
        "<blockquote>ᴀʟʟ ʀᴇɴᴀᴍᴇ ᴏᴘᴛɪᴏɴs ᴀʀᴇ ᴍᴀɴᴀɢᴇᴅ ғʀᴏᴍ ᴛʜɪs ᴘᴀɴᴇʟ.</blockquote>\n\n"
        f"<b>ᴀᴜᴛᴏ ʀᴇɴᴀᴍᴇ:</b> <code>{fmt}</code>\n"
        f"<b>ᴍᴇᴅɪᴀ ᴛʏᴘᴇ:</b> <code>{media}</code>\n"
        f"<b>ғɪʟᴇ ғᴏʀᴍᴀᴛ:</b> <code>{container}</code>\n"
        f"<b>ғɪʟᴇɴᴀᴍᴇ ғᴏɴᴛ:</b> <code>{font}</code>\n"
        f"<b>ᴛʜᴜᴍʙɴᴀɪʟ:</b> <code>{thumb}</code>\n"
        f"<b>ᴄᴀᴘᴛɪᴏɴ:</b> <code>{caption}</code>\n"
        f"<b>ᴍᴇᴛᴀᴅᴀᴛᴀ:</b> <code>{metadata}</code>\n"
        f"<b>ᴜɪ ᴘɪᴄᴛᴜʀᴇs:</b> <code>{ui_pics}</code>"
    )
    markup = kb([
        [b("ᴀᴜᴛᴏ ʀᴇɴᴀᴍᴇ", "settings:rename")],
        [b("ᴍᴇᴅɪᴀ ᴛʏᴘᴇ", "settings:media"), b("ғɪʟᴇ ғᴏʀᴍᴀᴛ", "settings:container")],
        [b("ғɪʟᴇɴᴀᴍᴇ ғᴏɴᴛ", "settings:font")],
        [b("ᴛʜᴜᴍʙɴᴀɪʟ", "settings:thumb"), b("ᴄᴀᴘᴛɪᴏɴ", "settings:caption")],
        [b("ᴍᴇᴛᴀᴅᴀᴛᴀ", "settings:metadata")],
        [b("ᴜɪ ᴘɪᴄᴛᴜʀᴇs", "settings:pics")],
        [b("ᴄʟᴏsᴇ", "settings:close")],
    ])
    photo = user.get("ui_settings_pic") or Config.SETTINGS_PIC
    try:
        await send_photo_styled(client, message, photo, text, markup)
    except Exception:
        await message.reply_photo(photo, caption=text, reply_markup=markup)


async def show_home(query: CallbackQuery):
    user = await settings_db.get_user(query.from_user.id)
    fmt = value(user.get("format_template"))
    caption = "sᴀᴠᴇᴅ" if user.get("caption") else "ɴᴏᴛ sᴇᴛ"
    thumb = "sᴀᴠᴇᴅ" if user.get("thumbnail_file_id") else "ɴᴏᴛ sᴇᴛ"
    metadata = "ᴏɴ" if bool(user.get("metadata_enabled")) else "ᴏғғ"
    ui_pics = "ᴄᴜsᴛᴏᴍ" if any(user.get(k) for k in ("ui_start_pic", "ui_settings_pic", "ui_status_pic")) else "ᴅᴇғᴀᴜʟᴛ"
    media = (user.get("media_type") or "same").upper()
    container = (user.get("container_format") or "same").upper()
    font = FONT_STYLES.get((user.get("filename_font") or "code").lower(), "ᴄᴏᴅᴇ")
    text = (
        "<b>ʀᴇɴᴀᴍᴇ sᴇᴛᴛɪɴɢs</b>\n\n"
        "<blockquote>ᴀʟʟ ʀᴇɴᴀᴍᴇ ᴏᴘᴛɪᴏɴs ᴀʀᴇ ᴍᴀɴᴀɢᴇᴅ ғʀᴏᴍ ᴛʜɪs ᴘᴀɴᴇʟ.</blockquote>\n\n"
        f"<b>ᴀᴜᴛᴏ ʀᴇɴᴀᴍᴇ:</b> <code>{fmt}</code>\n"
        f"<b>ᴍᴇᴅɪᴀ ᴛʏᴘᴇ:</b> <code>{media}</code>\n"
        f"<b>ғɪʟᴇ ғᴏʀᴍᴀᴛ:</b> <code>{container}</code>\n"
        f"<b>ғɪʟᴇɴᴀᴍᴇ ғᴏɴᴛ:</b> <code>{font}</code>\n"
        f"<b>ᴛʜᴜᴍʙɴᴀɪʟ:</b> <code>{thumb}</code>\n"
        f"<b>ᴄᴀᴘᴛɪᴏɴ:</b> <code>{caption}</code>\n"
        f"<b>ᴍᴇᴛᴀᴅᴀᴛᴀ:</b> <code>{metadata}</code>\n"
        f"<b>ᴜɪ ᴘɪᴄᴛᴜʀᴇs:</b> <code>{ui_pics}</code>"
    )
    await edit_panel(query, text, kb([
        [b("ᴀᴜᴛᴏ ʀᴇɴᴀᴍᴇ", "settings:rename")],
        [b("ᴍᴇᴅɪᴀ ᴛʏᴘᴇ", "settings:media"), b("ғɪʟᴇ ғᴏʀᴍᴀᴛ", "settings:container")],
        [b("ғɪʟᴇɴᴀᴍᴇ ғᴏɴᴛ", "settings:font")],
        [b("ᴛʜᴜᴍʙɴᴀɪʟ", "settings:thumb"), b("ᴄᴀᴘᴛɪᴏɴ", "settings:caption")],
        [b("ᴍᴇᴛᴀᴅᴀᴛᴀ", "settings:metadata")],
        [b("ᴜɪ ᴘɪᴄᴛᴜʀᴇs", "settings:pics")],
        [b("ᴄʟᴏsᴇ", "settings:close")],
    ]))
