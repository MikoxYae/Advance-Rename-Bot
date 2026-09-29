from __future__ import annotations

import asyncio

from pyrogram.types import Message

from config import Config
from helper.rename.models import QueuedItem

# Per-user batch collector. Files are only registered here when received;
# no Telegram download starts until the user sends /done.
PENDING_BATCHES: dict[int, list[QueuedItem]] = {}
BATCH_LOCKS: dict[int, asyncio.Lock] = {}
USER_UPLOAD_LOCKS: dict[int, asyncio.Lock] = {}
BATCH_STATUS_MESSAGES: dict[int, Message] = {}
RUNNING_BATCHES: set[int] = set()
BATCH_TASKS: dict[int, asyncio.Task] = {}
BATCH_CANCEL_EVENTS: dict[int, asyncio.Event] = {}
ACTIVE_BATCH_STATUS: dict[int, Message] = {}
QUEUED_FILE_KEYS: set[tuple[int, str]] = set()

DOWNLOAD_SLOTS = asyncio.Semaphore(Config.DOWNLOAD_CONCURRENCY)
UPLOAD_SLOTS = asyncio.Semaphore(Config.UPLOAD_CONCURRENCY)

DOWNLOAD_STALL_SECONDS = 45
DOWNLOAD_ATTEMPTS = 5
DOWNLOAD_RETRY_BASE_SECONDS = 2


def get_batch_lock(user_id: int) -> asyncio.Lock:
    lock = BATCH_LOCKS.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        BATCH_LOCKS[user_id] = lock
    return lock


def get_user_upload_lock(user_id: int) -> asyncio.Lock:
    """One upload at a time per user, regardless of global concurrency."""
    lock = USER_UPLOAD_LOCKS.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        USER_UPLOAD_LOCKS[user_id] = lock
    return lock
