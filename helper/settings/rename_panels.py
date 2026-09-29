from __future__ import annotations

from pyrogram.types import CallbackQuery

from helper.database import settings_db
from helper.settings.common import b, edit_panel, kb, value
from helper.settings.state import FONT_STYLES


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
    rows.append([b("ʙᴀᴄᴋ", "settings:page:1")])
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
        [b("ʙᴀᴄᴋ", "settings:page:1")],
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
        [b("ʙᴀᴄᴋ", "settings:page:1")],
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
        [b("ʙᴀᴄᴋ", "settings:page:1")],
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
    rows.append([b("ʙᴀᴄᴋ", "settings:page:2")])
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
    rows.append([b("ʙᴀᴄᴋ", "settings:page:2")])
    await edit_panel(query, text, kb(rows))
