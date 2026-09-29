from __future__ import annotations

import logging
from dataclasses import is_dataclass

from aiohttp import web
from pyrogram import Client, filters
from pyrogram.handlers import CallbackQueryHandler, MessageHandler
from pyrogram.types import BotCommand

from config import Config
from helper.database import settings_db
from helper.rename.models import QueuedItem, PreparedItem
from helper.web import get_public_base_url
from route import web_server

# Import callbacks explicitly. We do not rely on Pyrogram Smart Plugins anymore.
from plugins.start import start_handler
from plugins.file_rename import (
    batch_collect_handler,
    done_handler,
    clear_handler,
    cancel_handler,
    batch_callback_handler,
)
from plugins.mediainfo import mediainfo_handler
from plugins.settings import (
    settings_command,
    settings_page_callback,
    settings_callback,
    pending_text_handler,
    pending_photo_handler,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


class RenameBot(Client):
    def __init__(self):
        Config.validate()
        Config.WORK_DIR.mkdir(parents=True, exist_ok=True)

        # Fail fast if a future refactor breaks the queue model constructors.
        if not is_dataclass(QueuedItem) or not is_dataclass(PreparedItem):
            raise RuntimeError("Rename queue models are not valid dataclasses")
        logger.info("Rename queue model validation passed")

        # Smart Plugins are intentionally disabled. Every handler is registered
        # explicitly below, which prevents silent partial-plugin loading.
        super().__init__(
            name="advance_rename_bot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            workers=50,
            sleep_threshold=30,
            max_concurrent_transmissions=4,  # 2 downloads + 2 uploads max via semaphores
        )
        self.web_runner = None
        self._register_handlers()

    def _register_handlers(self) -> None:
        registrations = [
            (MessageHandler(start_handler, filters.private & filters.command("start")), 0, "start_handler"),
            (MessageHandler(settings_command, filters.private & filters.command("settings")), 0, "settings_command"),
            (MessageHandler(mediainfo_handler, filters.private & filters.command("mediainfo")), 0, "mediainfo_handler"),
            (MessageHandler(done_handler, filters.private & filters.command("done")), 0, "done_handler"),
            (MessageHandler(clear_handler, filters.private & filters.command("clear")), 0, "clear_handler"),
            (MessageHandler(cancel_handler, filters.private & filters.command("cancel")), 0, "cancel_handler"),

            # File intake: collect only, never download until /done.
            (MessageHandler(
                batch_collect_handler,
                filters.private & (filters.document | filters.video | filters.audio),
            ), 0, "batch_collect_handler"),

            # Page navigation gets an earlier group so it is always isolated.
            (CallbackQueryHandler(
                settings_page_callback,
                filters.regex(r"^settings:page:[12]$"),
            ), -1, "settings_page_callback"),
            (CallbackQueryHandler(
                settings_callback,
                filters.regex(r"^settings:(?!page:[12]$)"),
            ), 0, "settings_callback"),
            (CallbackQueryHandler(
                batch_callback_handler,
                filters.regex(r"^batch:(done|clear|cancel)$"),
            ), 0, "batch_callback_handler"),

            # Pending settings input runs after command/media handlers.
            (MessageHandler(pending_text_handler, filters.private & filters.text), 2, "pending_text_handler"),
            (MessageHandler(pending_photo_handler, filters.private & filters.photo), 2, "pending_photo_handler"),
        ]

        for handler, group, name in registrations:
            self.add_handler(handler, group=group)
            logger.info("Registered handler: %s (group %s)", name, group)

        logger.info("Registered %d handlers explicitly", len(registrations))

    async def start(self):
        await super().start()
        await settings_db.ping()
        me = await self.get_me()

        try:
            commands = [
                BotCommand("start", "Start the bot"),
                BotCommand("settings", "Open rename settings"),
                BotCommand("mediainfo", "Generate MediaInfo report"),
                BotCommand("done", "Start queued rename files"),
                BotCommand("clear", "Clear waiting rename queue"),
                BotCommand("cancel", "Cancel current rename batch"),
            ]
            await self.set_bot_commands(commands)
            logger.info(
                "Telegram command menu synced: %s",
                ", ".join(f"/{command.command}" for command in commands),
            )
        except Exception as exc:
            logger.warning("Could not sync Telegram command menu: %s", exc)

        if Config.WEB_SERVER:
            self.web_runner = web.AppRunner(await web_server())
            await self.web_runner.setup()
            await web.TCPSite(self.web_runner, "0.0.0.0", Config.PORT).start()
            try:
                public_url = await get_public_base_url()
                logger.info("MediaInfo website: %s", public_url)
            except Exception as exc:
                logger.warning("Could not auto-detect public MediaInfo URL: %s", exc)

        logger.info("@%s started", me.username)

    async def stop(self, *args):
        if self.web_runner:
            await self.web_runner.cleanup()
        await super().stop(*args)


RenameBot().run()
