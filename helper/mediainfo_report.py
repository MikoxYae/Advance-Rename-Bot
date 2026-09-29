from __future__ import annotations

import asyncio
import html
import re
import time
import uuid
from pathlib import Path

from config import Config
from helper.utils import humanbytes
from helper.web import get_public_base_url

PUBLIC_URL_TIMEOUT = 10


def _human_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def _parse_mediainfo_sections(output: str, filename: str, file_size: int) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    current_title = "General"
    current_lines: list[str] = []

    known = ("General", "Video", "Audio", "Text", "Menu", "Image", "Other")

    def flush():
        nonlocal current_lines
        if current_lines or not sections:
            sections.append((current_title, current_lines))
        current_lines = []

    for raw in output.splitlines():
        line = raw.rstrip("\r")
        stripped = line.strip()
        if any(stripped == k or stripped.startswith(k + " #") for k in known):
            if current_lines or sections:
                flush()
            current_title = stripped.replace("Text", "Subtitle", 1)
            continue

        if line.startswith("Complete name"):
            line = f"Complete name                             : {filename}"
        elif line.startswith("File size") and file_size:
            line = f"File size                                 : {humanbytes(file_size)}"
        current_lines.append(line)

    flush()
    return sections


def _split_mediainfo_field(line: str) -> tuple[str, str] | None:
    """Split one MediaInfo CLI row into field/value without relying on fixed columns."""
    match = re.match(r"^\s*(.*?)\s+:\s*(.*)\s*$", line)
    if not match:
        return None
    key = match.group(1).strip()
    value = match.group(2).strip()
    if not key:
        return None
    return key, value


def _render_section_rows(lines: list[str]) -> str:
    rows: list[str] = []
    long_keys = {
        "unique id",
        "complete name",
        "codec id/info",
        "format/info",
        "format settings",
        "encoding settings",
        "writing library",
        "writing application",
        "encoded date",
        "tagged date",
        "muxing mode",
        "internet media type",
    }

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        parsed = _split_mediainfo_field(line)
        if parsed is None:
            # Keep uncommon MediaInfo continuation/note lines instead of dropping them.
            rows.append(
                '<div class="kv-row note-row">'
                f'<div class="kv-value">{html.escape(line)}</div>'
                '</div>'
            )
            continue

        key, value = parsed
        value = value or "—"
        is_long = (
            key.casefold() in long_keys
            or len(value) >= 76
            or len(key) >= 30
        )
        classes = "kv-row kv-long" if is_long else "kv-row"
        rows.append(
            f'<div class="{classes}">'
            f'<div class="kv-key">{html.escape(key)}</div>'
            f'<div class="kv-value">{html.escape(value)}</div>'
            '</div>'
        )

    return "\n".join(rows)


def _build_report_html(output: str, filename: str, file_size: int, partial: bool, local_bytes: int) -> str:
    sections = _parse_mediainfo_sections(output, filename, file_size)
    escaped_name = html.escape(filename)
    generated = time.strftime("%d %b %Y %H:%M:%S UTC", time.gmtime())
    source_note = (
        f"Fast partial probe · {html.escape(humanbytes(local_bytes))} sampled from Telegram"
        if partial
        else "Full media probe"
    )

    cards = []
    for title, lines in sections:
        rows_html = _render_section_rows(lines)
        if not rows_html:
            continue
        cards.append(
            '<section class="card">'
            f'<div class="section-title">{html.escape(title)}</div>'
            f'<div class="kv-list">{rows_html}</div>'
            '</section>'
        )

    if not cards:
        cards.append(
            '<section class="card">'
            '<div class="section-title">MediaInfo</div>'
            f'<div class="raw-fallback">{html.escape(output)}</div>'
            '</section>'
        )
    cards_html = "\n".join(cards)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="dark">
<title>MediaInfo · {escaped_name}</title>
<style>
:root{{color-scheme:dark;--bg:#090b10;--panel:#11151d;--panel2:#151b25;--line:#273141;--line-soft:rgba(148,163,184,.12);--text:#f5f7fb;--value:#dce4ef;--muted:#93a1b5}}
*{{box-sizing:border-box}}
html{{-webkit-text-size-adjust:100%}}
body{{margin:0;background:radial-gradient(circle at 12% 0,#1a2230 0,transparent 32%),var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
.wrap{{width:min(980px,calc(100% - 24px));margin:0 auto;padding:26px 0 52px}}
.hero{{border:1px solid var(--line);background:linear-gradient(145deg,rgba(24,31,43,.98),rgba(13,17,24,.98));border-radius:22px;padding:24px;box-shadow:0 18px 60px rgba(0,0,0,.28);margin-bottom:16px}}
.eyebrow{{font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:var(--muted);font-weight:800}}
h1{{font-size:clamp(23px,5vw,36px);line-height:1.17;margin:10px 0 16px;overflow-wrap:anywhere;word-break:break-word}}
.meta{{display:flex;gap:9px;flex-wrap:wrap}}
.pill{{border:1px solid var(--line);background:#0d1118;border-radius:999px;padding:8px 11px;color:#cbd5e1;font-size:12px;line-height:1.35}}
.card{{border:1px solid var(--line);background:linear-gradient(180deg,var(--panel2),var(--panel));border-radius:18px;margin-top:14px;overflow:hidden;box-shadow:0 10px 30px rgba(0,0,0,.12)}}
.section-title{{padding:15px 18px;border-bottom:1px solid var(--line);font-weight:900;letter-spacing:.12em;text-transform:uppercase;font-size:14px}}
.kv-list{{width:100%}}
.kv-row{{display:grid;grid-template-columns:minmax(118px,38%) minmax(0,1fr);gap:16px;align-items:start;padding:10px 16px;border-bottom:1px solid var(--line-soft)}}
.kv-row:last-child{{border-bottom:0}}
.kv-key{{color:var(--muted);font-size:13px;font-weight:650;line-height:1.45;overflow-wrap:anywhere}}
.kv-value{{min-width:0;color:var(--value);font:13px/1.52 ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;overflow-wrap:anywhere;word-break:break-word;white-space:normal}}
.kv-long{{grid-template-columns:1fr;gap:6px;padding-top:12px;padding-bottom:13px}}
.kv-long .kv-key{{font-size:12px;text-transform:none;letter-spacing:.01em}}
.kv-long .kv-value{{background:rgba(7,10,15,.34);border:1px solid rgba(148,163,184,.10);border-radius:10px;padding:10px 11px}}
.note-row{{grid-template-columns:1fr}}
.note-row .kv-value{{color:#aab5c5;font-style:italic}}
.raw-fallback{{padding:16px;color:var(--value);font:12.5px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}}
.footer{{text-align:center;color:#69788e;font-size:11px;padding-top:20px}}
@media(min-width:760px){{.kv-row{{grid-template-columns:250px minmax(0,1fr);padding:11px 20px}}.kv-long{{grid-template-columns:250px minmax(0,1fr);gap:16px}}.kv-long .kv-value{{padding:0;background:none;border:0;border-radius:0}}}}
@media(max-width:520px){{.wrap{{width:calc(100% - 16px);padding-top:12px}}.hero{{padding:18px 16px;border-radius:17px}}.card{{border-radius:16px}}.section-title{{padding:14px 15px}}.kv-row{{grid-template-columns:minmax(105px,40%) minmax(0,1fr);gap:10px;padding:9px 14px}}.kv-key{{font-size:12px}}.kv-value{{font-size:12.5px}}.kv-long{{grid-template-columns:1fr;gap:6px;padding:11px 14px}}.pill{{font-size:11.5px}}}}
@media(max-width:350px){{.kv-row:not(.kv-long):not(.note-row){{grid-template-columns:1fr;gap:4px}}}}
</style>
</head>
<body>
<main class="wrap">
<header class="hero">
<div class="eyebrow">MediaInfo Report</div>
<h1>{escaped_name}</h1>
<div class="meta">
<span class="pill">Size: {html.escape(humanbytes(file_size)) if file_size else 'Unknown'}</span>
<span class="pill">{source_note}</span>
<span class="pill">Expires in {_human_duration(Config.MEDIAINFO_REPORT_TTL)}</span>
</div>
</header>
{cards_html}
<div class="footer">Generated {html.escape(generated)} · Advance Rename Bot</div>
</main>
</body>
</html>"""


async def _save_report(page_html: str) -> tuple[str, Path]:
    Config.MEDIAINFO_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    path = Config.MEDIAINFO_REPORT_DIR / f"{token}.html"
    await asyncio.to_thread(path.write_text, page_html, encoding="utf-8")
    try:
        base_url = await asyncio.wait_for(get_public_base_url(), timeout=PUBLIC_URL_TIMEOUT)
    except asyncio.TimeoutError as exc:
        raise RuntimeError("VPS public IP detection timed out. Check outbound internet access.") from exc
    return f"{base_url}/mediainfo/{token}", path
