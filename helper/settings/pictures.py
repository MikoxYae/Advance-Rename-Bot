from __future__ import annotations

from pyrogram.types import CallbackQuery

from config import Config
from helper.database import settings_db
from helper.settings.common import b, edit_panel, kb
from helper.settings.state import PIC_FIELDS


def _pic_default(kind: str) -> str:
    if kind == "status":
        return Config.STATUS_PIC
    return Config.SETTINGS_PIC


async def show_ui_pics(query: CallbackQuery):
    user = await settings_db.get_user(query.from_user.id)

    def state(field: str) -> str:
        return "ᴄᴜsᴛᴏᴍ" if user.get(field) else "ᴅᴇғᴀᴜʟᴛ"

    text = (
        "<b>ᴜɪ ᴘɪᴄᴛᴜʀᴇs</b>\n\n"
        "<blockquote>ᴀᴘɴᴇ ʙᴏᴛ ᴜɪ ᴋᴇ ᴘɪᴄᴛᴜʀᴇs ʏᴀʜᴀɴ sᴇ ᴄʜᴀɴɢᴇ ᴋʀᴏ. "
        "ᴘʜᴏᴛᴏ ᴛᴇʟᴇɢʀᴀᴍ ғɪʟᴇ_ɪᴅ ᴀs ᴘᴇʀsɪsᴛᴇɴᴛ sᴇᴛᴛɪɴɢ ᴍᴇ sᴀᴠᴇ ʜᴏɢɪ.</blockquote>\n\n"
        f"<b>sᴛᴀʀᴛ ᴘɪᴄ:</b> <code>{state('ui_start_pic')}</code>\n"
        f"<b>sᴇᴛᴛɪɴɢs ᴘɪᴄ:</b> <code>{state('ui_settings_pic')}</code>\n"
        f"<b>sᴛᴀᴛᴜs ᴘɪᴄ:</b> <code>{state('ui_status_pic')}</code>"
    )
    await edit_panel(query, text, kb([
        [b("sᴛᴀʀᴛ ᴘɪᴄ", "settings:pic:start"), b("sᴇᴛᴛɪɴɢs ᴘɪᴄ", "settings:pic:settings")],
        [b("sᴛᴀᴛᴜs ᴘɪᴄ", "settings:pic:status")],
        [b("ʙᴀᴄᴋ", "settings:home")],
    ]))


async def show_ui_pic_field(query: CallbackQuery, kind: str):
    db_field, title, used_for = PIC_FIELDS[kind]
    current = await settings_db.get(query.from_user.id, db_field)
    state = "ᴄᴜsᴛᴏᴍ" if current else "ᴅᴇғᴀᴜʟᴛ"
    text = (
        f"<b>{title}</b>\n\n"
        f"<b>ᴄᴜʀʀᴇɴᴛ:</b> <code>{state}</code>\n"
        f"<b>ᴜsᴇᴅ ғᴏʀ:</b> <code>{used_for}</code>\n\n"
        "<blockquote>sᴇᴛ / ᴇᴅɪᴛ ᴘʀᴇss ᴋʀᴋᴇ ɴᴇᴡ ᴘʜᴏᴛᴏ sᴇɴᴅ ᴋʀᴏ. "
        "ʀᴇsᴇᴛ ᴛᴏ ᴅᴇғᴀᴜʟᴛ sᴇ ᴄᴏɴғɪɢ ᴡᴀʟɪ ᴘɪᴄ ᴡᴀᴘᴀs ᴀᴀ ᴊᴀʏᴇɢɪ.</blockquote>"
    )
    label = "ᴇᴅɪᴛ ᴘɪᴄ" if current else "sᴇᴛ ᴘɪᴄ"
    rows = [
        [b(label, f"settings:ask:pic:{kind}"), b("ᴠɪᴇᴡ", f"settings:pic:view:{kind}")],
    ]
    if current:
        rows.append([b("ʀᴇsᴇᴛ ᴛᴏ ᴅᴇғᴀᴜʟᴛ", f"settings:pic:reset:{kind}")])
    rows.append([b("ʙᴀᴄᴋ", "settings:pics")])
    await edit_panel(query, text, kb(rows))
