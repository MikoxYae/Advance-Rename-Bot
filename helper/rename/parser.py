from __future__ import annotations

import html
import re

from helper.utils import safe_filename

SEASON_EPISODE_PATTERNS = [
    # S01E02 / S01-EP02 / S01_EP-02
    re.compile(r"(?i)(?:^|[^A-Za-z0-9])S[ ._-]*(?P<s>\d{1,3})[ ._-]*(?:E|EP)[ ._-]*(?P<e>\d{1,4})(?=$|[^0-9])"),
    # Season 1 Episode 2 / Season-1-EP-02
    re.compile(r"(?i)(?:^|[^A-Za-z0-9])Season[ ._-]*(?P<s>\d{1,3})[ ._-]*(?:Episode|Ep)[ ._-]*(?P<e>\d{1,4})(?=$|[^0-9])"),
    # [S01] [EP-02] / [S01][E02]
    re.compile(r"(?i)\[S[ ._-]*(?P<s>\d{1,3})\][ ._-]*\[(?:E|EP)[ ._-]*(?P<e>\d{1,4})\]"),
]
EPISODE_PATTERNS = [
    # E02 / EP-02 / [EP-02]
    re.compile(r"(?i)(?:^|[ ._\-\[])E(?:P)?[ ._-]*(?P<e>\d{1,4})(?:\]|\b)"),
    re.compile(r"(?i)(?:^|[^A-Za-z0-9])Episode[ ._-]*(?P<e>\d{1,4})(?=$|[^0-9])"),
]
SEASON_ONLY = re.compile(r"(?i)(?:^|[^A-Za-z0-9])S(?:eason)?[ ._-]*(?P<s>\d{1,3})(?=$|[^0-9])")
QUALITY_PATTERNS = [
    re.compile(r"(?i)\b(?P<q>2160p|1440p|1080p|720p|576p|540p|480p|360p|240p)\b"),
    re.compile(r"(?i)\b(?P<q>4k|2k|HDRip|HDTV|WEB[- .]?DL|WEBRip|BluRay)\b"),
]
MEDIA_EXTS = {
    ".mkv", ".mp4", ".m4v", ".mov", ".webm", ".avi", ".ts", ".m2ts",
    ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wav",
}
VIDEO_EXTS = {".mkv", ".mp4", ".m4v", ".mov", ".webm", ".avi", ".ts", ".m2ts"}
FONT_TAGS = {
    "normal": None,
    "bold": "b",
    "italic": "i",
    "underline": "u",
    "strike": "s",
    "code": "code",
    "spoiler": "__MARKDOWN_SPOILER__",
}


def extract_season_episode(filename: str):
    for pattern in SEASON_EPISODE_PATTERNS:
        match = pattern.search(filename)
        if match:
            return match.group("s"), match.group("e")

    season = None
    season_match = SEASON_ONLY.search(filename)
    if season_match:
        season = season_match.group("s")

    for pattern in EPISODE_PATTERNS:
        match = pattern.search(filename)
        if match:
            return season, match.group("e")

    candidates = re.findall(r"(?<!\d)(\d{1,4})(?!\d)", filename)
    ignored = {"2160", "1440", "1080", "720", "576", "540", "480", "360", "240", "264", "265"}
    filtered = [
        item for item in candidates
        if item not in ignored and not (len(item) == 4 and 1900 <= int(item) <= 2099)
    ]
    episode = filtered[-1] if filtered else None
    return season, episode

def extract_quality(filename: str):
    for pattern in QUALITY_PATTERNS:
        match = pattern.search(filename)
        if match:
            return match.group("q")
    return "Unknown"


QUALITY_SORT_RANK = {
    "240p": 240,
    "360p": 360,
    "480p": 480,
    "540p": 540,
    "576p": 576,
    "720p": 720,
    "1080p": 1080,
    "2k": 1440,
    "1440p": 1440,
    "4k": 2160,
    "2160p": 2160,
}

def _safe_int(value: str | None, fallback: int = 10**9) -> int:
    try:
        return int(value) if value is not None else fallback
    except (TypeError, ValueError):
        return fallback

def queued_item_sort_key(item):
    """Natural batch order: quality -> season -> episode -> original arrival.

    Known numeric qualities are grouped low-to-high (480p, 720p, 1080p...).
    Inside each quality, season/episode are sorted numerically. Files whose
    season/episode/quality cannot be parsed stay deterministic and fall back
    to their original Telegram message order.
    """
    filename = getattr(item, "original_name", "") or ""
    season, episode = extract_season_episode(filename)
    quality = (extract_quality(filename) or "Unknown").lower()
    quality_rank = QUALITY_SORT_RANK.get(quality, 10**8)
    message_id = getattr(getattr(item, "message", None), "id", 10**9)
    return (
        quality_rank,
        _safe_int(season),
        _safe_int(episode),
        message_id,
    )

def sort_queued_items(items):
    return sorted(items, key=queued_item_sort_key)

def render_filename(template: str, original: str) -> str:
    season, episode = extract_season_episode(original)
    quality = extract_quality(original)
    values = {
        "{season}": season or "XX",
        "{episode}": episode or "XX",
        "{quality}": quality,
    }
    result = template
    for key, val in values.items():
        result = result.replace(key, val)
    return safe_filename(result, "renamed_file")

def styled_filename(filename: str, style: str | None) -> str:
    """Return an HTML-safe filename using the user's Telegram caption font."""
    escaped = html.escape(filename)
    tag = FONT_TAGS.get((style or "code").lower(), "code")
    if not tag:
        return escaped
    if tag == "__MARKDOWN_SPOILER__":
        return f"||{escaped}||"
    return f"<{tag}>{escaped}</{tag}>"

def target_container_extension(original_ext: str, user: dict) -> str:
    """Choose the real output container extension for video files."""
    ext = (original_ext or "").lower()
    requested = (user.get("container_format") or "same").lower()
    if ext not in VIDEO_EXTS or requested == "same":
        return original_ext
    if requested == "mkv":
        return ".mkv"
    if requested == "mp4":
        return ".mp4"
    return original_ext
