from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from config import Config


class Database:
    DEFAULTS = {
        "format_template": None,
        "media_type": "same",
        "container_format": "same",
        "filename_font": "code",
        "thumbnail_file_id": None,
        "caption": None,
        "metadata_enabled": 0,
        "meta_title": None,
        "meta_author": None,
        "meta_artist": None,
        "meta_audio": None,
        "meta_subtitle": None,
        "meta_video": None,
        "ui_start_pic": None,
        "ui_settings_pic": None,
        "ui_status_pic": None,
    }

    def __init__(self, uri: str, database_name: str):
        self.client = AsyncIOMotorClient(
            uri,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
            retryWrites=True,
        )
        self.db = self.client[database_name]
        self.users = self.db["users"]

    async def ping(self) -> None:
        await self.client.admin.command("ping")

    async def ensure_user(self, user_id: int) -> None:
        uid = int(user_id)
        defaults = {"user_id": uid, **self.DEFAULTS}
        await self.users.update_one(
            {"user_id": uid},
            {"$setOnInsert": defaults},
            upsert=True,
        )

    async def get_user(self, user_id: int) -> dict[str, Any]:
        uid = int(user_id)
        await self.ensure_user(uid)
        doc = await self.users.find_one({"user_id": uid}, {"_id": 0})
        if not doc:
            return {"user_id": uid, **self.DEFAULTS}

        # Backfill newly-added fields without overwriting existing user settings.
        merged = {"user_id": uid, **self.DEFAULTS, **doc}
        missing = {
            key: value
            for key, value in self.DEFAULTS.items()
            if key not in doc
        }
        if missing:
            await self.users.update_one({"user_id": uid}, {"$set": missing})
        return merged

    async def get(self, user_id: int, field: str, default=None):
        if field not in self.DEFAULTS:
            raise ValueError(f"Unknown settings field: {field}")
        user = await self.get_user(user_id)
        value = user.get(field)
        return default if value is None else value

    async def set(self, user_id: int, field: str, value) -> None:
        if field not in self.DEFAULTS:
            raise ValueError(f"Unknown settings field: {field}")
        uid = int(user_id)
        await self.ensure_user(uid)
        await self.users.update_one(
            {"user_id": uid},
            {"$set": {field: value}},
        )

    async def clear(self, user_id: int, field: str) -> None:
        if field not in self.DEFAULTS:
            raise ValueError(f"Unknown settings field: {field}")
        await self.set(user_id, field, self.DEFAULTS[field])


settings_db = Database(Config.DATABASE_URL, Config.DATABASE_NAME)
