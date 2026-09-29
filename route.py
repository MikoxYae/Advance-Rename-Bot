from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path

from aiohttp import web

from config import Config

TOKEN_RE = re.compile(r"^[a-f0-9]{24,64}$")


def _report_dir() -> Path:
    path = Config.MEDIAINFO_REPORT_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _report_path(token: str) -> Path:
    return _report_dir() / f"{token}.html"


def _cleanup_reports_sync() -> int:
    now = time.time()
    removed = 0
    ttl = int(Config.MEDIAINFO_REPORT_TTL)
    for path in _report_dir().glob("*.html"):
        try:
            if now - path.stat().st_mtime > ttl:
                path.unlink(missing_ok=True)
                removed += 1
        except OSError:
            continue
    return removed


async def cleanup_reports() -> int:
    return await asyncio.to_thread(_cleanup_reports_sync)


async def health(request: web.Request):
    return web.json_response(
        {
            "status": "ok",
            "service": "advance-rename-bot",
            "port": Config.PORT,
        }
    )


async def mediainfo_page(request: web.Request):
    token = request.match_info.get("token", "")
    if not TOKEN_RE.fullmatch(token):
        raise web.HTTPNotFound(text="MediaInfo report not found")

    path = _report_path(token)
    try:
        stat = path.stat()
    except FileNotFoundError:
        raise web.HTTPNotFound(text="MediaInfo report not found")

    if time.time() - stat.st_mtime > int(Config.MEDIAINFO_REPORT_TTL):
        path.unlink(missing_ok=True)
        raise web.HTTPGone(text="This MediaInfo report has expired")

    return web.FileResponse(
        path,
        headers={
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "SAMEORIGIN",
            "Referrer-Policy": "no-referrer",
        },
    )


async def web_server():
    _report_dir()
    await cleanup_reports()

    app = web.Application(client_max_size=1024 * 1024)
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_get("/mediainfo/{token}", mediainfo_page)
    return app
