from __future__ import annotations

import logging

from aiohttp import web
from pyrogram import Client
from pyrogram.types import BotCommand

from config import Config
from helper.database import settings_db
from route import web_server
from helper.web import get_public_base_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")


class RenameBot(Client):
    def __init__(self):
        Config.validate()
        Config.WORK_DIR.mkdir(parents=True, exist_ok=True)
        super().__init__(
            name="advance_rename_bot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            workers=50,
            plugins={"root": "plugins"},
            sleep_threshold=30,
            max_concurrent_transmissions=4,
        )
        self.web_runner = None

    async def start(self):
        await super().start()
        await settings_db.ping()
        me = await self.get_me()
        try:
            await self.set_bot_commands([
                BotCommand("settings", "Open rename settings"),
                BotCommand("mediainfo", "Open self-hosted MediaInfo report"),
                BotCommand("done", "Start queued rename files"),
            ])
        except Exception as exc:
            logging.warning("Could not set bot command menu: %s", exc)

        if Config.WEB_SERVER:
            self.web_runner = web.AppRunner(await web_server())
            await self.web_runner.setup()
            await web.TCPSite(self.web_runner, "0.0.0.0", Config.PORT).start()
            try:
                public_url = await get_public_base_url()
                logging.info("MediaInfo website: %s", public_url)
            except Exception as exc:
                logging.warning("Could not auto-detect public MediaInfo URL: %s", exc)
        logging.info("@%s started", me.username)

    async def stop(self, *args):
        if self.web_runner:
            await self.web_runner.cleanup()
        await super().stop(*args)


RenameBot().run()
