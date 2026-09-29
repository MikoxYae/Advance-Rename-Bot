from __future__ import annotations

from typing import Any

# In-memory prompt state. A restart cancels unfinished prompts; saved settings stay in MongoDB.
PENDING: dict[int, dict[str, Any]] = {}

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

PIC_FIELDS = {
    "start": ("ui_start_pic", "sᴛᴀʀᴛ ᴘɪᴄ", "START /start ᴘᴀɴᴇʟ"),
    "settings": ("ui_settings_pic", "sᴇᴛᴛɪɴɢs ᴘɪᴄ", "/settings ᴘᴀɴᴇʟ"),
    "status": ("ui_status_pic", "sᴛᴀᴛᴜs ᴘɪᴄ", "ǫᴜᴇᴜᴇ / ᴅᴏᴡɴʟᴏᴀᴅ / ᴜᴘʟᴏᴀᴅ"),
}
