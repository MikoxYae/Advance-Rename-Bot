# Advance Rename Bot

A Telegram batch auto-rename bot with a button-based `/settings` panel, strict FIFO upload ordering, self-hosted MediaInfo reports, configurable output container/media type, captions, thumbnails and FFmpeg metadata.

## Commands

The bot automatically synchronizes its Telegram command menu every time it starts. No BotFather command setup is required.

- `/start` — open the bot
- `/settings` — open all rename settings
- `/mediainfo` — reply to a media file to generate a self-hosted MediaInfo report
- `/done` — start the files currently collected in the batch queue
- `/clear` — clear waiting files without interrupting the running batch
- `/cancel` — safely stop the current batch after the active Telegram transfer completes

If commands are added or removed in `miko.py`, restarting the bot updates the Telegram menu automatically via `set_bot_commands()`.

## Batch workflow

1. Send all files in the exact order you want them uploaded.
2. The bot only collects them; it does not start downloading immediately.
3. The queue photo shows the received sequence and provides `ᴅᴏɴᴇ • sᴛᴀʀᴛ` and `ᴄʟᴇᴀʀ` controls.
4. Send `/done` or tap the Done button to start.
5. Upload order is strictly FIFO: `01 → 02 → 03 → ...`.
6. While file `N` is uploading, file `N+1` may download/prepare in parallel, but its upload cannot start until file `N` has completely finished uploading.

A per-user upload lock, one-item prepared queue and sequence guard prevent accidental reordering.

## Queue controls

- Before `/done`, `/clear` or the Clear button removes the entire waiting queue.
- During a running batch, `/clear` removes only the next/waiting batch and does not interrupt the active batch.
- `/cancel` or `ᴄᴀɴᴄᴇʟ ᴄᴜʀʀᴇɴᴛ ʙᴀᴛᴄʜ` requests a safe stop. The current Telegram transfer is allowed to finish, then no new upload is started.
- A second `/done` cannot start the same batch twice.

## Settings panel

All rename configuration is handled through `/settings` buttons and persisted in MongoDB.

Available controls include:

- Auto Rename format
- Media Type: Same / Document / Video / Audio
- File Format: Same / MKV / MP4
- Filename Font: Normal / Bold / Italic / Underline / Strike / Code / Spoiler
- Thumbnail: set/edit/view/delete
- Custom Caption
- Metadata On/Off
- Metadata Title / Author / Artist / Audio / Subtitle / Video fields

`{filename}` uses the selected Telegram filename style in captions. `{plain_filename}` always inserts a normal HTML-safe filename. Caption variables also include file size and duration where supported.

MKV/MP4 format conversion is a real FFmpeg stream-copy remux, not a fake extension change. MP4 uses compatible subtitle handling and can fall back to video+audio when an incompatible MKV-only stream would otherwise make the entire task fail.

## Status-picture UI

Queue, batch-start, download, metadata, upload, failure and completion states use `Config.STATUS_PIC`. The photo is sent once and its caption is edited for progress, avoiding repeated image spam.

## MediaInfo

Reply to a Telegram media file with `/mediainfo`.

- Files up to 50 MB can be downloaded normally for probing.
- Larger files use only the first Telegram stream chunks instead of downloading the full media.
- The server runs the `mediainfo` binary on the sample.
- The report is rendered as a responsive self-hosted HTML page with General / Video / Audio / Subtitle sections.
- Reports are served by the same aiohttp process and same `Config.PORT` (`1490` in the supplied private configuration).
- Reports expire automatically after 24 hours.

The website URL is generated from the VPS public IPv4 unless `Config.PUBLIC_BASE_URL` is set manually.

## Server port

Open the configured web port on Ubuntu:

```bash
sudo iptables -C INPUT -p tcp --dport 1490 -j ACCEPT 2>/dev/null || \
sudo iptables -I INPUT 5 -p tcp --dport 1490 -j ACCEPT
sudo netfilter-persistent save
```

If your VPS provider has an external firewall/security group, allow TCP port `1490` there too.

Health check:

```text
http://YOUR_VPS_IP:1490/health
```

## Requirements

- Python 3.10+
- FFmpeg / ffprobe
- MediaInfo CLI
- MongoDB
- Telegram Bot API credentials

Ubuntu packages:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip ffmpeg mediainfo unzip git iptables-persistent
```

Python setup:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -U pip
pip install -r requirements.txt
python3 miko.py
```

## Configuration

This configured test build keeps the supplied test values directly in `config.py`:

- Bot token
- API ID / API hash
- Owner ID
- MongoDB URI
- Port `1490`

No `.env` or `private_config.py` is required for this configured test repository. Because these values are committed with the source, anyone who can read the repository can read and use the test credentials.

## Deployment update

For an already-cloned repository:

```bash
cd /root/Advance-Rename-Bot
pkill -f "python3 miko.py" 2>/dev/null || true
unzip -o /root/Advance-Rename-Bot-Configured-v23.zip -d .
source venv/bin/activate
pip install -r requirements.txt
python3 -m compileall -q .
python3 miko.py
```
