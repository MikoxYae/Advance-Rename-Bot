from __future__ import annotations

import html

from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from helper.buttons import edit_message_styled


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
        await edit_message_styled(query.message, text, markup)
    except Exception:
        # Rare fallback (deleted/inaccessible source message). New panels use the
        # one-request styled sender so normal navigation never flashes neutral colours.
        try:
            await query.message.edit_caption(caption=text, reply_markup=markup)
        except Exception:
            await query.message.edit_text(text=text, reply_markup=markup)
