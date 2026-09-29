from __future__ import annotations

import html

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

from config import Config
from helper.buttons import edit_message_styled, send_photo_styled
from helper.database import settings_db
from helper.settings.common import b, edit_panel, kb
from helper.settings.home import send_settings, show_home, show_page
from helper.settings.metadata import show_meta_field, show_metadata
from helper.settings.pictures import _pic_default, show_ui_pic_field, show_ui_pics
from helper.settings.rename_panels import (
    show_caption, show_container, show_font, show_media, show_rename, show_thumb,
)
from helper.settings.state import FONT_STYLES, META_FIELDS, PIC_FIELDS, PENDING


async def settings_command(client: Client, message: Message):
    PENDING.pop(message.from_user.id, None)
    await settings_db.ensure_user(message.from_user.id)
    await send_settings(client, message)


async def settings_page_callback(client: Client, query: CallbackQuery):
    """Dedicated Page 1/Page 2 router.

    Keeping pagination out of the generic settings callback avoids navigation
    being affected by unrelated pending-state/settings branches.
    """
    uid = query.from_user.id
    await settings_db.ensure_user(uid)
    PENDING.pop(uid, None)
    try:
        await query.answer()
    except Exception:
        pass
    page = 2 if query.data.endswith(":2") else 1
    await show_page(query, page, answered=True)
    # Explicitly stop this callback from reaching the generic settings router.
    try:
        query.stop_propagation()
    except Exception:
        pass


async def settings_callback(client: Client, query: CallbackQuery):
    uid = query.from_user.id
    data = query.data
    await settings_db.ensure_user(uid)

    if data in {"settings:home", "settings:cancel"}:
        PENDING.pop(uid, None)
        return await show_page(query, 1)
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
    if data == "settings:pics":
        PENDING.pop(uid, None)
        return await show_ui_pics(query)
    if data.startswith("settings:pic:view:"):
        kind = data.rsplit(":", 1)[1]
        if kind in PIC_FIELDS:
            db_field, title, _ = PIC_FIELDS[kind]
            custom = await settings_db.get(uid, db_field)
            await query.answer()
            await client.send_photo(uid, custom or _pic_default(kind), caption=f"<b>{title}</b>")
        return
    if data.startswith("settings:pic:reset:"):
        kind = data.rsplit(":", 1)[1]
        if kind in PIC_FIELDS:
            db_field, _, _ = PIC_FIELDS[kind]
            await settings_db.clear(uid, db_field)
            PENDING.pop(uid, None)
            return await show_ui_pic_field(query, kind)
        return
    if data.startswith("settings:pic:"):
        kind = data.rsplit(":", 1)[1]
        if kind in PIC_FIELDS:
            PENDING.pop(uid, None)
            return await show_ui_pic_field(query, kind)
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
        elif action.startswith("pic:"):
            kind = action.split(":", 1)[1]
            if kind not in PIC_FIELDS:
                PENDING.pop(uid, None)
                return await show_ui_pics(query)
            _, title, _ = PIC_FIELDS[kind]
            prompt = f"<b>sᴇɴᴅ ɴᴇᴡ {title} ᴀs ᴀ ᴘʜᴏᴛᴏ.</b>\n\n<blockquote>sᴇɴᴅ ᴀ ᴘʜᴏᴛᴏ ᴏɴʟʏ. ᴅᴏ ɴᴏᴛ sᴇɴᴅ ɪᴛ ᴀs ᴀ ғɪʟᴇ ᴏʀ ᴅᴏᴄᴜᴍᴇɴᴛ.</blockquote>"
            back = f"settings:pic:{kind}"
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


async def pending_text_handler(client: Client, message: Message):
    uid = message.from_user.id
    # Commands must always be handled by their dedicated command handlers.
    if (message.text or "").lstrip().startswith("/"):
        return
    state = PENDING.get(uid)
    if not state:
        return
    action = state["action"]
    text = (message.text or "").strip()
    if not text:
        return

    async def finish(text_out, markup):
        try:
            target = await client.get_messages(state["chat_id"], state["message_id"])
            await edit_message_styled(target, text_out, markup)
        except Exception:
            user = await settings_db.get_user(uid)
            panel_pic = user.get("ui_settings_pic") or Config.SETTINGS_PIC
            try:
                await send_photo_styled(client, message, panel_pic, text_out, markup)
            except Exception:
                await message.reply_photo(panel_pic, caption=text_out, reply_markup=markup)
        try:
            await message.delete()
        except Exception:
            pass

    if action == "thumbnail" or action.startswith("pic:"):
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


async def pending_photo_handler(client: Client, message: Message):
    uid = message.from_user.id
    state = PENDING.get(uid)
    if not state:
        return

    action = state.get("action", "")
    if action == "thumbnail":
        field = "thumbnail_file_id"
        success_text = "<b>ᴛʜᴜᴍʙɴᴀɪʟ sᴀᴠᴇᴅ</b>"
        back = "settings:thumb"
        back_text = "ʙᴀᴄᴋ ᴛᴏ ᴛʜᴜᴍʙɴᴀɪʟ"
    elif action.startswith("pic:"):
        kind = action.split(":", 1)[1]
        if kind not in PIC_FIELDS:
            PENDING.pop(uid, None)
            return
        field, title, _ = PIC_FIELDS[kind]
        success_text = f"<b>{title} sᴀᴠᴇᴅ</b>\n\n<blockquote>ᴛʜᴇ ɴᴇᴡ ᴘɪᴄᴛᴜʀᴇ ᴡɪʟʟ ʙᴇ ᴜsᴇᴅ ᴛʜᴇ ɴᴇxᴛ ᴛɪᴍᴇ ᴛʜᴀᴛ ᴘᴀɴᴇʟ ᴏʀ sᴛᴀᴛᴜs ᴍᴇssᴀɢᴇ ɪs sᴇɴᴛ.</blockquote>"
        back = f"settings:pic:{kind}"
        back_text = "ʙᴀᴄᴋ ᴛᴏ ᴜɪ ᴘɪᴄᴛᴜʀᴇ"
    else:
        return

    await settings_db.set(uid, field, message.photo.file_id)
    PENDING.pop(uid, None)
    markup = kb([[b(back_text, back)]])

    target = None
    try:
        target = await client.get_messages(state["chat_id"], state["message_id"])
        await edit_message_styled(target, success_text, markup)
    except Exception:
        user = await settings_db.get_user(uid)
        panel_pic = user.get("ui_settings_pic") or Config.SETTINGS_PIC
        try:
            await send_photo_styled(client, message, panel_pic, success_text, markup)
        except Exception:
            await message.reply_photo(panel_pic, caption=success_text, reply_markup=markup)
    try:
        await message.delete()
    except Exception:
        pass
