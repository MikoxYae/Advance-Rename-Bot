from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from pyrogram.types import Message


class QueuedItem:
    message: Message
    media: object
    unique: str
    original_name: str


class PreparedItem:
    queued: QueuedItem
    sequence: int
    workdir: Path
    final_path: Path
    output_type: str
    caption: str
    thumb: str | None
    upload_started: asyncio.Event = field(default_factory=asyncio.Event)


class BatchCancelled(Exception):
    pass
