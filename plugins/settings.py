from __future__ import annotations

from typing import Dict, Any
import html

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Config
from helper.database import settings_db


# In-memory prompt state. A restart cancels unfinished prompts; saved settings stay in SQLite.
PENDING: Dict[int, Dict[str, Any]] = {}

META_FIELDS = {
    "title": ("meta_title", "ᴛɪᴛʟᴇ"),
    "author": ("meta_author", "ᴀᴜᴛʜᴏʀ"),
    "artist": ("meta_artist", "ᴀʀᴛɪsᴛ"),
    "audio": ("meta_audio", "ᴀᴜᴅɪᴏ"),
    "subtitle": ("meta_subtitle", "sᴜʙᴛɪᴛʟᴇ"),
    "video": ("meta_video", "ᴠɪᴅᴇᴏ"),
}

FONT_STYLES = {
    "normal": "ɴᴏʀᴍᴀʟ",
    "bold": "ʙᴏʟᴅ",
    "italic": "ɪᴛᴀʟɪᴄ",
    "underline": "ᴜɴᴅᴇʀʟɪɴᴇ",
    "strike": "sᴛʀɪᴋᴇ",
    "code": "ᴄᴏᴅᴇ",
    "spoiler": "sᴘᴏɪʟᴇʀ",
}


def kb(rows):
    return InlineKeyboardMarkup(rows)


def b(text, data):
    return InlineKeyboardButton(text, callback_data=data)


def value(v, empty="ɴᴏᴛ sᴇᴛ", limit=220):
    if v in (None, "", False):
        return empty
    raw = str(v)
    if len(raw) > limit:
        raw = raw[: max(0, limit - 3)] + "..."
    return html.escape(raw)


async def edit_panel(query: CallbackQuery, text: str, markup: InlineKeyboardMarkup):
    await query.answer()
    try:
        if query.message.photo:
            await query.message.edit_caption(caption=text, reply_markup=markup)
        else:
            await query.message.edit_text(text=text, reply_markup=markup)
    except Exception:
        await query.message.reply_photo(Config.SETTINGS_PIC, caption=text, reply_markup=markup)


async def send_settings(message: Message):
    user = await settings_db.get_user(message.from_user.id)
    fmt = value(user.get("format_template"))
    caption = "sᴀᴠᴇᴅ" if user.get("caption") else "ɴᴏᴛ sᴇᴛ"
    thumb = "sᴀᴠᴇᴅ" if user.get("thumbnail_file_id") else "ɴᴏᴛ sᴇᴛ"
    metadata = "ᴏɴ" if bool(user.get("metadata_enabled")) else "ᴏғғ"
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
        f"<b>ᴍᴇᴛᴀᴅᴀᴛᴀ:</b> <code>{metadata}</code>"
    )
    markup = kb([
        [b("ᴀᴜᴛᴏ ʀᴇɴᴀᴍᴇ", "settings:rename")],
        [b("ᴍᴇᴅɪᴀ ᴛʏᴘᴇ", "settings:media"), b("ғɪʟᴇ ғᴏʀᴍᴀᴛ", "settings:container")],
        [b("ғɪʟᴇɴᴀᴍᴇ ғᴏɴᴛ", "settings:font")],
        [b("ᴛʜᴜᴍʙɴᴀɪʟ", "settings:thumb"), b("ᴄᴀᴘᴛɪᴏɴ", "settings:caption")],
        [b("ᴍᴇᴛᴀᴅᴀᴛᴀ", "settings:metadata")],
        [b("ᴄʟᴏsᴇ", "settings:close")],
    ])
    await message.reply_photo(Config.SETTINGS_PIC, caption=text, reply_markup=markup)


async def show_home(query: CallbackQuery):
    user = await settings_db.get_user(query.from_user.id)
    fmt = value(user.get("format_template"))
    caption = "sᴀᴠᴇᴅ" if user.get("caption") else "ɴᴏᴛ sᴇᴛ"
    thumb = "sᴀᴠᴇᴅ" if user.get("thumbnail_file_id") else "ɴᴏᴛ sᴇᴛ"
    metadata = "ᴏɴ" if bool(user.get("metadata_enabled")) else "ᴏғғ"
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
        f"<b>ᴍᴇᴛᴀᴅᴀᴛᴀ:</b> <code>{metadata}</code>"
    )
    await edit_panel(query, text, kb([
        [b("ᴀᴜᴛᴏ ʀᴇɴᴀᴍᴇ", "settings:rename")],
        [b("ᴍᴇᴅɪᴀ ᴛʏᴘᴇ", "settings:media"), b("ғɪʟᴇ ғᴏʀᴍᴀᴛ", "settings:container")],
        [b("ғɪʟᴇɴᴀᴍᴇ ғᴏɴᴛ", "settings:font")],
        [b("ᴛʜᴜᴍʙɴᴀɪʟ", "settings:thumb"), b("ᴄᴀᴘᴛɪᴏɴ", "settings:caption")],
        [b("ᴍᴇᴛᴀᴅᴀᴛᴀ", "settings:metadata")],
        [b("ᴄʟᴏsᴇ", "settings:close")],
    ]))


async def show_rename(query: CallbackQuery):
    current = await settings_db.get(query.from_user.id, "format_template")
    text = (
        "<b>ᴀᴜᴛᴏ ʀᴇɴᴀᴍᴇ</b>\n\n"
        f"<b>ᴄᴜʀʀᴇɴᴛ ғᴏʀᴍᴀᴛ:</b> <code>{value(current)}</code>\n\n"
        "<b>ᴠᴀʀɪᴀʙʟᴇs</b>\n"
        "<code>{season}</code> - sᴇᴀsᴏɴ\n"
        "<code>{episode}</code> - ᴇᴘɪsᴏᴅᴇ\n"
        "<code>{quality}</code> - ǫᴜᴀʟɪᴛʏ\n\n"
        "<b>ᴇxᴀᴍᴘʟᴇ:</b>\n"
        "<code>Overflow [S{season}E{episode}] [Dual] {quality}</code>"
    )
    label = "ᴇᴅɪᴛ ғᴏʀᴍᴀᴛ" if current else "sᴇᴛ ғᴏʀᴍᴀᴛ"
    rows = [[b(label, "settings:ask:format")]]
    if current:
        rows.append([b("ᴅᴇʟᴇᴛᴇ", "settings:delete:format_template")])
    rows.append([b("ʙᴀᴄᴋ", "settings:home")])
    await edit_panel(query, text, kb(rows))


async def show_media(query: CallbackQuery):
    current = (await settings_db.get(query.from_user.id, "media_type", "same") or "same").lower()
    mark = lambda name: " ✓" if current == name else ""
    text = (
        "<b>ᴍᴇᴅɪᴀ ᴛʏᴘᴇ</b>\n\n"
        f"<b>ᴄᴜʀʀᴇɴᴛ:</b> <code>{current.upper()}</code>\n\n"
        "<blockquote>ᴄʜᴏᴏsᴇ ʜᴏᴡ ᴛʜᴇ ʀᴇɴᴀᴍᴇᴅ ғɪʟᴇ sʜᴏᴜʟᴅ ʙᴇ sᴇɴᴛ.\n"
        "ᴛʜɪs ɪs ɪɴᴅᴇᴘᴇɴᴅᴇɴᴛ ғʀᴏᴍ ғɪʟᴇ ғᴏʀᴍᴀᴛ, sᴏ ʏᴏᴜ ᴄᴀɴ ᴜsᴇ DOCUMENT + MKV ᴏʀ VIDEO + MP4.</blockquote>"
    )
    await edit_panel(query, text, kb([
        [b("sᴀᴍᴇ ᴀs ɪɴᴘᴜᴛ" + mark("same"), "settings:media:set:same")],
        [b("ᴅᴏᴄᴜᴍᴇɴᴛ" + mark("document"), "settings:media:set:document")],
        [b("ᴠɪᴅᴇᴏ" + mark("video"), "settings:media:set:video")],
        [b("ᴀᴜᴅɪᴏ" + mark("audio"), "settings:media:set:audio")],
        [b("ʙᴀᴄᴋ", "settings:home")],
    ]))


async def show_container(query: CallbackQuery):
    current = (await settings_db.get(query.from_user.id, "container_format", "same") or "same").lower()
    mark = lambda name: " ✓" if current == name else ""
    text = (
        "<b>ғɪʟᴇ ғᴏʀᴍᴀᴛ</b>\n\n"
        f"<b>ᴄᴜʀʀᴇɴᴛ:</b> <code>{current.upper()}</code>\n\n"
        "<blockquote>ᴛʜɪs ɪs ᴀ ʀᴇᴀʟ ᴄᴏɴᴛᴀɪɴᴇʀ ʀᴇᴍᴜx, ɴᴏᴛ ᴊᴜsᴛ ᴀ ғɪʟᴇ ᴇxᴛᴇɴsɪᴏɴ ʀᴇɴᴀᴍᴇ.\n"
        "SAME = ᴋᴇᴇᴘ ᴏʀɪɢɪɴᴀʟ. MKV = ʀᴇᴍᴜx ᴛᴏ ᴍᴀᴛʀᴏsᴋᴀ. MP4 = ʀᴇᴍᴜx ᴛᴏ ᴍᴘ4.</blockquote>\n\n"
        "<i>MP4 ᴄᴀɴɴᴏᴛ ᴄᴀʀʀʏ ᴇᴠᴇʀʏ MKV ᴀᴛᴛᴀᴄʜᴍᴇɴᴛ/sᴜʙᴛɪᴛʟᴇ ᴛʏᴘᴇ; ᴜɴsᴜᴘᴘᴏʀᴛᴇᴅ sᴛʀᴇᴀᴍs ᴍᴀʏ ʙᴇ sᴋɪᴘᴘᴇᴅ ᴅᴜʀɪɴɢ MP4 ʀᴇᴍᴜx.</i>"
    )
    await edit_panel(query, text, kb([
        [b("sᴀᴍᴇ" + mark("same"), "settings:container:set:same")],
        [b("ᴍᴋᴠ" + mark("mkv"), "settings:container:set:mkv"), b("ᴍᴘ4" + mark("mp4"), "settings:container:set:mp4")],
        [b("ʙᴀᴄᴋ", "settings:home")],
    ]))


async def show_font(query: CallbackQuery):
    current = (await settings_db.get(query.from_user.id, "filename_font", "code") or "code").lower()
    mark = lambda name: " ✓" if current == name else ""
    text = (
        "<b>ғɪʟᴇɴᴀᴍᴇ ғᴏɴᴛ</b>\n\n"
        f"<b>ᴄᴜʀʀᴇɴᴛ:</b> <code>{FONT_STYLES.get(current, 'ᴄᴏᴅᴇ')}</code>\n\n"
        "<blockquote>ᴛʜɪs sᴛʏʟᴇ ɪs ᴜsᴇᴅ ғᴏʀ ᴛʜᴇ ғɪʟᴇɴᴀᴍᴇ ɪɴ ᴛᴇʟᴇɢʀᴀᴍ ᴄᴀᴘᴛɪᴏɴ. ᴛʜᴇ ʀᴇᴀʟ ғɪʟᴇɴᴀᴍᴇ ʀᴇᴍᴀɪɴs ᴄʟᴇᴀɴ ᴘʟᴀɪɴ ᴛᴇxᴛ.</blockquote>\n\n"
        "<b>ᴄᴜsᴛᴏᴍ ᴄᴀᴘᴛɪᴏɴ:</b> <code>{filename}</code> ᴡɪʟʟ ᴜsᴇ ᴛʜɪs sᴛʏʟᴇ."
    )
    await edit_panel(query, text, kb([
        [b("ɴᴏʀᴍᴀʟ" + mark("normal"), "settings:font:set:normal"), b("ʙᴏʟᴅ" + mark("bold"), "settings:font:set:bold")],
        [b("ɪᴛᴀʟɪᴄ" + mark("italic"), "settings:font:set:italic"), b("ᴜɴᴅᴇʀʟɪɴᴇ" + mark("underline"), "settings:font:set:underline")],
        [b("sᴛʀɪᴋᴇ" + mark("strike"), "settings:font:set:strike"), b("ᴄᴏᴅᴇ" + mark("code"), "settings:font:set:code")],
        [b("sᴘᴏɪʟᴇʀ" + mark("spoiler"), "settings:font:set:spoiler")],
        [b("ʙᴀᴄᴋ", "settings:home")],
    ]))


async def show_thumb(query: CallbackQuery):
    current = await settings_db.get(query.from_user.id, "thumbnail_file_id")
    text = (
        "<b>ᴛʜᴜᴍʙɴᴀɪʟ</b>\n\n"
        f"<b>sᴛᴀᴛᴜs:</b> <code>{'sᴀᴠᴇᴅ' if current else 'ɴᴏᴛ sᴇᴛ'}</code>\n\n"
        "<blockquote>sᴇᴛ ᴀ ᴘʜᴏᴛᴏ ᴛᴏ ᴜsᴇ ᴀs ᴛʜᴇ ᴄᴜsᴛᴏᴍ ᴛʜᴜᴍʙɴᴀɪʟ.</blockquote>"
    )
    label = "ᴇᴅɪᴛ ᴛʜᴜᴍʙɴᴀɪʟ" if current else "sᴇᴛ ᴛʜᴜᴍʙɴᴀɪʟ"
    rows = [[b(label, "settings:ask:thumbnail")]]
    if current:
        rows.append([b("ᴠɪᴇᴡ", "settings:thumb:view"), b("ᴅᴇʟᴇᴛᴇ", "settings:delete:thumbnail_file_id")])
    rows.append([b("ʙᴀᴄᴋ", "settings:home")])
    await edit_panel(query, text, kb(rows))


async def show_caption(query: CallbackQuery):
    current = await settings_db.get(query.from_user.id, "caption")
    text = (
        "<b>ᴄᴜsᴛᴏᴍ ᴄᴀᴘᴛɪᴏɴ</b>\n\n"
        f"<b>ᴄᴜʀʀᴇɴᴛ:</b> <code>{value(current)}</code>\n\n"
        "<b>ᴠᴀʀɪᴀʙʟᴇs</b>\n"
        "<code>{filename}</code> - sᴇʟᴇᴄᴛᴇᴅ ғᴏɴᴛ sᴛʏʟᴇ\n"
        "<code>{plain_filename}</code> - ᴘʟᴀɪɴ ғɪʟᴇɴᴀᴍᴇ\n"
        "<code>{filesize}</code>\n<code>{duration}</code>\n\n"
        "<i>HTML ɪs ᴀʟʟᴏᴡᴇᴅ, ᴇ.ɢ. &lt;b&gt;ᴛᴇxᴛ&lt;/b&gt;.</i>"
    )
    label = "ᴇᴅɪᴛ ᴄᴀᴘᴛɪᴏɴ" if current else "sᴇᴛ ᴄᴀᴘᴛɪᴏɴ"
    rows = [[b(label, "settings:ask:caption")]]
    if current:
        rows.append([b("ᴅᴇʟᴇᴛᴇ", "settings:delete:caption")])
    rows.append([b("ʙᴀᴄᴋ", "settings:home")])
    await edit_panel(query, text, kb(rows))


async def show_metadata(query: CallbackQuery):
    user = await settings_db.get_user(query.from_user.id)
    enabled = bool(user.get("metadata_enabled"))
    text = (
        "<b>ᴍᴇᴛᴀᴅᴀᴛᴀ</b>\n\n"
        f"<b>sᴛᴀᴛᴜs:</b> <code>{'ᴏɴ' if enabled else 'ᴏғғ'}</code>\n\n"
        f"<b>ᴛɪᴛʟᴇ:</b> <code>{value(user.get('meta_title'), limit=70)}</code>\n"
        f"<b>ᴀᴜᴛʜᴏʀ:</b> <code>{value(user.get('meta_author'), limit=70)}</code>\n"
        f"<b>ᴀʀᴛɪsᴛ:</b> <code>{value(user.get('meta_artist'), limit=70)}</code>\n"
        f"<b>ᴀᴜᴅɪᴏ:</b> <code>{value(user.get('meta_audio'), limit=70)}</code>\n"
        f"<b>sᴜʙᴛɪᴛʟᴇ:</b> <code>{value(user.get('meta_subtitle'), limit=70)}</code>\n"
        f"<b>ᴠɪᴅᴇᴏ:</b> <code>{value(user.get('meta_video'), limit=70)}</code>"
    )
    await edit_panel(query, text, kb([
        [b("ᴏɴ" + (" ✓" if enabled else ""), "settings:meta:toggle:on"), b("ᴏғғ" + (" ✓" if not enabled else ""), "settings:meta:toggle:off")],
        [b("ᴛɪᴛʟᴇ", "settings:meta:title"), b("ᴀᴜᴛʜᴏʀ", "settings:meta:author")],
        [b("ᴀʀᴛɪsᴛ", "settings:meta:artist"), b("ᴀᴜᴅɪᴏ", "settings:meta:audio")],
        [b("sᴜʙᴛɪᴛʟᴇ", "settings:meta:subtitle"), b("ᴠɪᴅᴇᴏ", "settings:meta:video")],
        [b("ʙᴀᴄᴋ", "settings:home")],
    ]))


async def show_meta_field(query: CallbackQuery, key: str):
    db_field, title = META_FIELDS[key]
    current = await settings_db.get(query.from_user.id, db_field)
    text = (
        f"<b>{title} ᴍᴇᴛᴀᴅᴀᴛᴀ</b>\n\n"
        f"<b>ᴄᴜʀʀᴇɴᴛ:</b> <code>{value(current)}</code>"
    )
    label = "ᴇᴅɪᴛ" if current else "sᴇᴛ"
    rows = [[b(label, f"settings:ask:meta:{key}")]]
    if current:
        rows.append([b("ᴅᴇʟᴇᴛᴇ", f"settings:delete:{db_field}")])
    rows.append([b("ʙᴀᴄᴋ", "settings:metadata")])
    await edit_panel(query, text, kb(rows))


@Client.on_message(filters.private & filters.command("settings"))
async def settings_command(client: Client, message: Message):
    PENDING.pop(message.from_user.id, None)
    await settings_db.ensure_user(message.from_user.id)
    await send_settings(message)


@Client.on_callback_query(filters.regex(r"^settings:"))
async def settings_callback(client: Client, query: CallbackQuery):
    uid = query.from_user.id
    data = query.data
    await settings_db.ensure_user(uid)

    if data in {"settings:home", "settings:cancel"}:
        PENDING.pop(uid, None)
        return await show_home(query)
    if data == "settings:close":
        PENDING.pop(uid, None)
        await query.answer()
        return await query.message.delete()
    if data == "settings:rename":
        PENDING.pop(uid, None)
        return await show_rename(query)
    if data == "settings:media":
        PENDING.pop(uid, None)
        return await show_media(query)
    if data.startswith("settings:media:set:"):
        media = data.rsplit(":", 1)[1]
        await settings_db.set(uid, "media_type", media)
        return await show_media(query)
    if data == "settings:container":
        PENDING.pop(uid, None)
        return await show_container(query)
    if data.startswith("settings:container:set:"):
        container = data.rsplit(":", 1)[1]
        if container in {"same", "mkv", "mp4"}:
            await settings_db.set(uid, "container_format", container)
        return await show_container(query)
    if data == "settings:font":
        PENDING.pop(uid, None)
        return await show_font(query)
    if data.startswith("settings:font:set:"):
        font = data.rsplit(":", 1)[1]
        if font in FONT_STYLES:
            await settings_db.set(uid, "filename_font", font)
        return await show_font(query)
    if data == "settings:thumb":
        PENDING.pop(uid, None)
        return await show_thumb(query)
    if data == "settings:thumb:view":
        file_id = await settings_db.get(uid, "thumbnail_file_id")
        await query.answer()
        if file_id:
            await client.send_photo(uid, file_id, caption="<b>ᴄᴜʀʀᴇɴᴛ ᴛʜᴜᴍʙɴᴀɪʟ</b>")
        return
    if data == "settings:caption":
        PENDING.pop(uid, None)
        return await show_caption(query)
    if data == "settings:metadata":
        PENDING.pop(uid, None)
        return await show_metadata(query)
    if data.startswith("settings:meta:toggle:"):
        enabled = data.endswith(":on")
        await settings_db.set(uid, "metadata_enabled", 1 if enabled else 0)
        return await show_metadata(query)
    if data.startswith("settings:meta:"):
        key = data.rsplit(":", 1)[1]
        if key in META_FIELDS:
            PENDING.pop(uid, None)
            return await show_meta_field(query, key)
    if data.startswith("settings:ask:"):
        action = data[len("settings:ask:"):]
        PENDING[uid] = {"action": action, "chat_id": query.message.chat.id, "message_id": query.message.id, "is_photo": bool(query.message.photo)}
        if action == "format":
            prompt = (
                "<b>sᴇɴᴅ ᴀᴜᴛᴏ ʀᴇɴᴀᴍᴇ ғᴏʀᴍᴀᴛ</b>\n\n"
                "<blockquote>sᴇɴᴅ ᴏɴʟʏ ᴛʜᴇ ғᴏʀᴍᴀᴛ ᴛᴇxᴛ ɴᴏᴡ.</blockquote>\n\n"
                "<code>Overflow [S{season}E{episode}] [Dual] {quality}</code>"
            )
            back = "settings:rename"
        elif action == "thumbnail":
            prompt = "<b>sᴇɴᴅ ᴛʜᴇ ᴘʜᴏᴛᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴜsᴇ ᴀs ᴛʜᴜᴍʙɴᴀɪʟ.</b>"
            back = "settings:thumb"
        elif action == "caption":
            prompt = (
                "<b>sᴇɴᴅ ʏᴏᴜʀ ᴄᴜsᴛᴏᴍ ᴄᴀᴘᴛɪᴏɴ</b>\n\n"
                "<code>{filename}</code>  <code>{plain_filename}</code>  <code>{filesize}</code>  <code>{duration}</code>\n\n"
                "<i>HTML ᴀʟʟᴏᴡᴇᴅ. ᴇxᴀᴍᴘʟᴇ: &lt;b&gt;ᴍʏ ᴄʜᴀɴɴᴇʟ&lt;/b&gt;</i>"
            )
            back = "settings:caption"
        elif action.startswith("meta:"):
            key = action.split(":", 1)[1]
            _, title = META_FIELDS[key]
            prompt = f"<b>sᴇɴᴅ ᴛʜᴇ ɴᴇᴡ {title} ᴍᴇᴛᴀᴅᴀᴛᴀ ᴛᴇxᴛ.</b>"
            back = f"settings:meta:{key}"
        else:
            PENDING.pop(uid, None)
            return await show_home(query)
        return await edit_panel(query, prompt, kb([[b("ᴄᴀɴᴄᴇʟ", back)], [b("ʙᴀᴄᴋ", back)]]))
    if data.startswith("settings:delete:"):
        field = data[len("settings:delete:"):]
        if field in settings_db.DEFAULTS:
            await settings_db.clear(uid, field)
        PENDING.pop(uid, None)
        if field == "format_template":
            return await show_rename(query)
        if field == "thumbnail_file_id":
            return await show_thumb(query)
        if field == "caption":
            return await show_caption(query)
        for key, (db_field, _) in META_FIELDS.items():
            if field == db_field:
                return await show_meta_field(query, key)
        return await show_home(query)

    await query.answer("ɪɴᴠᴀʟɪᴅ sᴇᴛᴛɪɴɢ", show_alert=False)


@Client.on_message(filters.private & filters.text & ~filters.command(["start", "settings", "mediainfo", "done", "clear", "cancel"]), group=-10)
async def pending_text_handler(client: Client, message: Message):
    uid = message.from_user.id
    state = PENDING.get(uid)
    if not state:
        return
    action = state["action"]
    text = (message.text or "").strip()
    if not text:
        return

    async def finish(text_out, markup):
        try:
            if state.get("is_photo"):
                await client.edit_message_caption(state["chat_id"], state["message_id"], caption=text_out, reply_markup=markup)
            else:
                await client.edit_message_text(state["chat_id"], state["message_id"], text=text_out, reply_markup=markup)
        except Exception:
            await message.reply_photo(Config.SETTINGS_PIC, caption=text_out, reply_markup=markup)
        try:
            await message.delete()
        except Exception:
            pass

    if action == "thumbnail":
        return await message.reply_text("<b>sᴇɴᴅ ᴀ ᴘʜᴏᴛᴏ, ɴᴏᴛ ᴛᴇxᴛ. ᴜsᴇ ᴄᴀɴᴄᴇʟ ᴛᴏ sᴛᴏᴘ.</b>")

    if action == "format":
        if len(text) > 220:
            return await message.reply_text("<b>ғᴏʀᴍᴀᴛ ɪs ᴛᴏᴏ ʟᴏɴɢ. ᴍᴀx 220 ᴄʜᴀʀᴀᴄᴛᴇʀs.</b>")
        await settings_db.set(uid, "format_template", text)
        PENDING.pop(uid, None)
        await finish(
            f"<b>ғᴏʀᴍᴀᴛ sᴀᴠᴇᴅ</b>\n\n<code>{html.escape(text)}</code>",
            kb([[b("ʙᴀᴄᴋ ᴛᴏ ᴀᴜᴛᴏ ʀᴇɴᴀᴍᴇ", "settings:rename")]])
        )
        return
    if action == "caption":
        if len(text) > 900:
            return await message.reply_text("<b>ᴄᴀᴘᴛɪᴏɴ ɪs ᴛᴏᴏ ʟᴏɴɢ. ᴍᴀx 900 ᴄʜᴀʀᴀᴄᴛᴇʀs.</b>")
        await settings_db.set(uid, "caption", text)
        PENDING.pop(uid, None)
        await finish(
            "<b>ᴄᴀᴘᴛɪᴏɴ sᴀᴠᴇᴅ</b>",
            kb([[b("ʙᴀᴄᴋ ᴛᴏ ᴄᴀᴘᴛɪᴏɴ", "settings:caption")]])
        )
        return
    if action.startswith("meta:"):
        key = action.split(":", 1)[1]
        db_field, title = META_FIELDS[key]
        await settings_db.set(uid, db_field, text[:250])
        PENDING.pop(uid, None)
        await finish(
            f"<b>{title} sᴀᴠᴇᴅ</b>",
            kb([[b("ʙᴀᴄᴋ ᴛᴏ ᴍᴇᴛᴀᴅᴀᴛᴀ", "settings:metadata")]])
        )


@Client.on_message(filters.private & filters.photo, group=-10)
async def pending_photo_handler(client: Client, message: Message):
    uid = message.from_user.id
    state = PENDING.get(uid)
    if not state or state.get("action") != "thumbnail":
        return
    await settings_db.set(uid, "thumbnail_file_id", message.photo.file_id)
    PENDING.pop(uid, None)
    text = "<b>ᴛʜᴜᴍʙɴᴀɪʟ sᴀᴠᴇᴅ</b>"
    markup = kb([[b("ʙᴀᴄᴋ ᴛᴏ ᴛʜᴜᴍʙɴᴀɪʟ", "settings:thumb")]])
    try:
        if state.get("is_photo"):
            await client.edit_message_caption(state["chat_id"], state["message_id"], caption=text, reply_markup=markup)
        else:
            await client.edit_message_text(state["chat_id"], state["message_id"], text=text, reply_markup=markup)
    except Exception:
        await message.reply_photo(Config.SETTINGS_PIC, caption=text, reply_markup=markup)
    try:
        await message.delete()
    except Exception:
        pass
