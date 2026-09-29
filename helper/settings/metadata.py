from __future__ import annotations

from pyrogram.types import CallbackQuery

from helper.database import settings_db
from helper.settings.common import b, edit_panel, kb, value
from helper.settings.state import META_FIELDS


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
        [b("ʙᴀᴄᴋ", "settings:page:2")],
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
