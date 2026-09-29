from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import aiohttp

from config import Config

logger = logging.getLogger(__name__)


def _get_attr(obj: Any, name: str):
    try:
        return getattr(obj, name, None)
    except Exception:
        return None


def resolve_button_style(button: Any) -> str | None:
    """Return Telegram's native semantic button style.

    Inline buttons support semantic styles only; the Telegram client decides the
    exact shade.  We deliberately do not fake arbitrary HEX colours.
    """
    text = str(_get_attr(button, "text") or "")
    data = str(_get_attr(button, "callback_data") or "").lower()
    url = _get_attr(button, "url")
    low = text.lower()

    destructive_words = (
        "cancel", "ᴄᴀɴᴄᴇʟ", "clear", "ᴄʟᴇᴀʀ", "delete", "ᴅᴇʟᴇᴛᴇ",
        "close", "ᴄʟᴏsᴇ", "remove", "ʀᴇᴍᴏᴠᴇ", "reset", "ʀᴇsᴇᴛ",
    )
    if any(word in low for word in destructive_words):
        return "danger"
    if data.endswith(":off") or data.endswith(":toggle:off"):
        return "danger"

    if "✓" in text:
        return "success"

    positive_words = (
        "done", "ᴅᴏɴᴇ", "start", "sᴛᴀʀᴛ", "save", "sᴀᴠᴇ",
        "set ", "sᴇᴛ ", "edit", "ᴇᴅɪᴛ", "enable", "ᴇɴᴀʙʟᴇ",
    )
    if any(word in low for word in positive_words):
        return "success"
    if ":ask:" in data or data.endswith(":on") or data.endswith(":toggle:on"):
        return "success"

    primary_words = (
        "back", "ʙᴀᴄᴋ", "settings", "sᴇᴛᴛɪɴɢs", "open", "ᴏᴘᴇɴ",
        "view", "ᴠɪᴇᴡ", "home", "ʜᴏᴍᴇ", "picture", "ᴘɪᴄᴛᴜʀᴇ",
        "pics", "ᴘɪᴄs",
    )
    if url or any(word in low for word in primary_words):
        return "primary"
    if data in {
        "settings:home", "settings:rename", "settings:media", "settings:container",
        "settings:font", "settings:thumb", "settings:caption", "settings:metadata",
        "settings:pics",
    }:
        return "primary"

    return None


def _button_payload(button: Any, *, styled: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {"text": str(_get_attr(button, "text") or "")}
    mapping = {
        "callback_data": "callback_data",
        "url": "url",
        "switch_inline_query": "switch_inline_query",
        "switch_inline_query_current_chat": "switch_inline_query_current_chat",
    }
    for attr, key in mapping.items():
        value = _get_attr(button, attr)
        if value is not None:
            payload[key] = value

    web_app = _get_attr(button, "web_app")
    if web_app is not None and _get_attr(web_app, "url"):
        payload["web_app"] = {"url": _get_attr(web_app, "url")}

    if styled:
        style = resolve_button_style(button)
        if style:
            payload["style"] = style
    return payload


def markup_payload(markup: Any, *, styled: bool = True) -> dict[str, Any]:
    rows = _get_attr(markup, "inline_keyboard") or []
    return {
        "inline_keyboard": [
            [_button_payload(button, styled=styled) for button in row]
            for row in rows
        ]
    }


async def _bot_api(method: str, payload: dict[str, Any], *, retry_without_style: bool = True) -> dict[str, Any]:
    """Call Bot API directly.

    Styled keyboards are included in the *same* send/edit request.  This avoids
    the old visible flash where Pyrogram first rendered neutral buttons and a
    second HTTP request coloured them afterwards.
    """
    url = f"https://api.telegram.org/bot{Config.BOT_TOKEN}/{method}"
    timeout = aiohttp.ClientTimeout(total=12)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload) as response:
            data = await response.json(content_type=None)
            if response.status == 200 and isinstance(data, dict) and data.get("ok"):
                return data

            description = str(data.get("description", "") if isinstance(data, dict) else data)
            # Graceful compatibility fallback for a Bot API/client combination
            # that does not yet recognise `style`.  The message is still sent
            # once (unstyled) instead of sending then recolouring it later.
            if retry_without_style and "reply_markup" in payload:
                markup = payload.get("reply_markup")
                if isinstance(markup, dict):
                    has_style = any(
                        isinstance(button, dict) and "style" in button
                        for row in markup.get("inline_keyboard", [])
                        for button in row
                    )
                    if has_style:
                        clean = dict(payload)
                        clean["reply_markup"] = {
                            "inline_keyboard": [
                                [
                                    {k: v for k, v in button.items() if k != "style"}
                                    for button in row
                                ]
                                for row in markup.get("inline_keyboard", [])
                            ]
                        }
                        return await _bot_api(method, clean, retry_without_style=False)

            raise RuntimeError(f"Bot API {method} failed: {description or response.status}")


class StyledMessageRef:
    """Minimal message reference for Bot-API-created UI messages.

    It is used only when Pyrogram cannot immediately hydrate the just-created
    message.  Progress/status code still gets `.chat.id`, `.id`, `.photo` and
    edit/delete methods, so a successful styled send never causes a duplicate
    fallback message.
    """

    def __init__(self, chat_id: int, message_id: int, *, photo: bool):
        self.chat = SimpleNamespace(id=chat_id)
        self.id = message_id
        self.photo = True if photo else None

    async def edit_caption(self, caption: str, reply_markup: Any = None):
        payload: dict[str, Any] = {
            "chat_id": self.chat.id,
            "message_id": self.id,
            "caption": caption,
            "parse_mode": "HTML",
        }
        if reply_markup is not None:
            payload["reply_markup"] = markup_payload(reply_markup, styled=True)
        await _bot_api("editMessageCaption", payload)
        return self

    async def edit_text(self, text: str, reply_markup: Any = None, **kwargs):
        payload: dict[str, Any] = {
            "chat_id": self.chat.id,
            "message_id": self.id,
            "text": text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": bool(kwargs.get("disable_web_page_preview", True))},
        }
        if reply_markup is not None:
            payload["reply_markup"] = markup_payload(reply_markup, styled=True)
        await _bot_api("editMessageText", payload)
        return self

    async def delete(self):
        await _bot_api("deleteMessage", {"chat_id": self.chat.id, "message_id": self.id})
        return True


async def send_photo_styled(client: Any, source_message: Any, photo: str, caption: str, markup: Any = None):
    payload: dict[str, Any] = {
        "chat_id": source_message.chat.id,
        "photo": photo,
        "caption": caption,
        "parse_mode": "HTML",
        "reply_parameters": {
            "message_id": source_message.id,
            "allow_sending_without_reply": True,
        },
    }
    if markup is not None:
        payload["reply_markup"] = markup_payload(markup, styled=True)
    data = await _bot_api("sendPhoto", payload)
    message_id = int(data["result"]["message_id"])
    if client is not None:
        try:
            return await client.get_messages(source_message.chat.id, message_id)
        except Exception:
            pass
    return StyledMessageRef(source_message.chat.id, message_id, photo=True)


async def send_text_styled(client: Any, source_message: Any, text: str, markup: Any = None):
    payload: dict[str, Any] = {
        "chat_id": source_message.chat.id,
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
        "reply_parameters": {
            "message_id": source_message.id,
            "allow_sending_without_reply": True,
        },
    }
    if markup is not None:
        payload["reply_markup"] = markup_payload(markup, styled=True)
    data = await _bot_api("sendMessage", payload)
    message_id = int(data["result"]["message_id"])
    if client is not None:
        try:
            return await client.get_messages(source_message.chat.id, message_id)
        except Exception:
            pass
    return StyledMessageRef(source_message.chat.id, message_id, photo=False)


async def edit_message_styled(message: Any, text: str, markup: Any = None, *, disable_preview: bool = True) -> bool:
    payload: dict[str, Any] = {
        "chat_id": message.chat.id,
        "message_id": message.id,
        "parse_mode": "HTML",
    }
    if markup is not None:
        payload["reply_markup"] = markup_payload(markup, styled=True)

    if _get_attr(message, "photo"):
        method = "editMessageCaption"
        payload["caption"] = text
    else:
        method = "editMessageText"
        payload["text"] = text
        payload["link_preview_options"] = {"is_disabled": bool(disable_preview)}

    try:
        await _bot_api(method, payload)
        return True
    except RuntimeError as exc:
        if "message is not modified" in str(exc).lower():
            return False
        raise


async def apply_button_styles(message: Any, markup: Any) -> bool:
    """Compatibility helper for old call sites.

    New code should use send/edit helpers above so colours are present on the
    first render.  This function is kept only for backward compatibility.
    """
    if message is None or markup is None:
        return False
    payload = {
        "chat_id": message.chat.id,
        "message_id": message.id,
        "reply_markup": markup_payload(markup, styled=True),
    }
    try:
        await _bot_api("editMessageReplyMarkup", payload)
        return True
    except Exception as exc:
        logger.warning("Native button styling failed: %s", exc)
        return False
