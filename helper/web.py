from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from typing import Optional

import aiohttp

from config import Config

logger = logging.getLogger(__name__)

_PUBLIC_BASE_URL: Optional[str] = None
_PUBLIC_LOCK = asyncio.Lock()


def _valid_public_ipv4(value: str) -> str | None:
    value = (value or "").strip()
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return None
    if ip.version != 4 or not ip.is_global:
        return None
    return str(ip)


async def _fetch_public_ip() -> str | None:
    # Keep this bounded. One slow external IP service must never block /mediainfo.
    endpoints = (
        "https://api.ipify.org",
        "https://checkip.amazonaws.com",
        "https://ipv4.icanhazip.com",
    )
    timeout = aiohttp.ClientTimeout(total=3.5, connect=2.0, sock_read=2.0)
    for endpoint in endpoints:
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(endpoint, headers={"User-Agent": "AdvanceRenameBot/1.0"}) as response:
                    if response.status != 200:
                        continue
                    candidate = _valid_public_ipv4(await response.text())
                    if candidate:
                        return candidate
        except Exception as exc:
            logger.debug("Public IP lookup failed at %s: %s", endpoint, exc)
    return None

def _fallback_host_ip() -> str | None:
    candidates: list[str] = []
    try:
        candidates.append(socket.gethostbyname(socket.gethostname()))
    except Exception:
        pass
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1)
        sock.connect(("8.8.8.8", 80))
        candidates.append(sock.getsockname()[0])
        sock.close()
    except Exception:
        pass
    for candidate in candidates:
        valid = _valid_public_ipv4(candidate)
        if valid:
            return valid
    return None


async def get_public_base_url(force_refresh: bool = False) -> str:
    global _PUBLIC_BASE_URL

    configured = (getattr(Config, "PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
    if configured:
        return configured

    if _PUBLIC_BASE_URL and not force_refresh:
        return _PUBLIC_BASE_URL

    async with _PUBLIC_LOCK:
        if _PUBLIC_BASE_URL and not force_refresh:
            return _PUBLIC_BASE_URL

        ip = await _fetch_public_ip()
        if not ip:
            ip = _fallback_host_ip()
        if not ip:
            raise RuntimeError(
                "Could not auto-detect the VPS public IPv4 address. "
                "Set Config.PUBLIC_BASE_URL once if this VPS is behind NAT/proxy."
            )

        _PUBLIC_BASE_URL = f"http://{ip}:{Config.PORT}"
        logger.info("Public MediaInfo base URL detected: %s", _PUBLIC_BASE_URL)
        return _PUBLIC_BASE_URL
