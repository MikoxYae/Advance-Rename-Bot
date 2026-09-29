# Advance Rename Bot

A Telegram batch auto-rename bot with a button-based `/settings` panel, strict FIFO upload ordering, self-hosted MediaInfo reports, configurable output container/media type, captions, thumbnails and FFmpeg metadata.

## Commands

The bot automatically synchronizes its Telegram command menu every time it starts. No BotFather command setup is required.

- `/start` — open the bot
- `/settings` — open the paginated rename settings panel
- `/mediainfo` — reply to a media file to generate a self-hosted MediaInfo report
- `/done` — start the files currently collected in the batch queue
- Natural batch auto-sorting: quality groups (480p → 720p → 1080p → …), then season/episode ascending. Unparsed files remain deterministic by Telegram arrival order.
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

All rename configuration is handled through `/settings` buttons and persisted in MongoDB. The panel is split into two pages so the interface stays compact on mobile.

**Page 1 — Rename & Output**

- Auto Rename format
- Media Type: Same / Document / Video / Audio
- File Format: Same / MKV / MP4
- Filename Font: Normal / Bold / Italic / Underline / Strike / Code / Spoiler

**Page 2 — Advanced & UI**


- Thumbnail: set/edit/view/delete
- Custom Caption
- Metadata On/Off
- Metadata Title / Author / Artist / Audio / Subtitle / Video fields
- UI Pictures: Start Pic / Settings Pic / Status Pic, with Set/Edit/View/Reset-to-default controls

`{filename}` uses the selected Telegram filename style in captions. `{plain_filename}` always inserts a normal HTML-safe filename. Caption variables also include file size and duration where supported.

MKV/MP4 format conversion is a real FFmpeg stream-copy remux, not a fake extension change. MP4 uses compatible subtitle handling and can fall back to video+audio when an incompatible MKV-only stream would otherwise make the entire task fail.

## Status-picture UI

Queue, batch-start, download, metadata, upload, failure and completion states use the user's saved **Status Pic** when configured, otherwise `Config.STATUS_PIC`. `/start` and `/settings` can also use separate user-configured pictures. Pictures are stored as Telegram `file_id` values in MongoDB, so changing them does not require editing the source code. The status photo is sent once and its caption is edited for progress, avoiding repeated image spam.

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
unzip -o /root/Advance-Rename-Bot-Configured-v27.zip -d .
source venv/bin/activate
pip install -r requirements.txt
python3 -m compileall -q .
python3 miko.py
```

## Native Colored Buttons

The bot applies Telegram's native inline-button styles automatically:

- **Green / Success** — Done/Start, Set/Edit/Save, enabled/selected options.
- **Red / Danger** — Cancel, Clear, Delete, Close, Reset, Off.
- **Blue / Primary** — Settings, Back, Open/View, UI Pictures and navigation actions.
- Neutral choices keep the Telegram client default style until selected.

Colored keyboards are now included in the **same Bot API send/edit request** as the message/caption. The old two-step `send neutral → edit keyboard colour` flow has been removed, so supported Telegram clients should render the colour on the first frame instead of showing it late. Telegram controls the exact shade and only semantic native styles are used; arbitrary HEX/RGB backgrounds are not supported.


## Project structure

The codebase is split by responsibility so future fixes do not require editing one very large plugin file.

```text
miko.py                         # app startup + Telegram command sync
config.py                       # configured test values
plugins/
  start.py                      # /start handler
  settings.py                   # settings callbacks/input handlers only
  file_rename.py                # batch command/message handlers only
  mediainfo.py                  # /mediainfo handler only
helper/
  buttons.py                    # styled Telegram buttons/messages
  database.py                   # MongoDB settings layer
  settings/
    state.py                    # settings constants + prompt state
    common.py                   # common keyboard/panel helpers
    home.py                     # settings home panel
    rename_panels.py            # rename/media/container/font/caption panels
    metadata.py                 # metadata panels
    pictures.py                 # Start/Settings/Status picture panels
  rename/
    models.py                   # queue/prepared dataclasses
    state.py                    # batch state, semaphores and locks
    parser.py                   # season/episode/quality parsing
    transfer.py                 # Telegram download/upload
    processing.py               # remux, metadata, thumbnail and preparation
    ui.py                       # queue/status picture UI
    batch.py                    # strict FIFO producer/uploader pipeline
  mediainfo_probe.py            # partial Telegram sample + mediainfo CLI
  mediainfo_report.py           # responsive HTML report generation
```

The v27 interface keeps the modular structure, converts all user-facing instructions to English, and adds a two-page settings panel while preserving the queue, strict upload order, MediaInfo, picture controls and colored-button behavior.

## Handler Registration Note

All Telegram features are explicitly registered as Pyrogram handlers. The modular layout keeps implementation code separate, but the plugin entry modules retain the decorators required for runtime dispatch:

- `/start`
- `/settings` and all `settings:*` callbacks
- `/mediainfo`
- `/done`, `/clear`, `/cancel`
- `batch:*` callbacks
- incoming private document/video/audio queue collection
- pending settings text/photo input

This prevents a command from appearing in Telegram's command menu without having a runtime handler attached.

### v30 settings pagination fix
- Page 1 / Page 2 navigation has a dedicated callback route.
- Settings pagination falls back to recreating the panel if Telegram cannot edit the existing message.


## Runtime reliability

- Incoming Telegram documents/videos/audio are collected into the batch queue immediately.
- Queue model objects are validated data classes; failed intake now reports an explicit Telegram error instead of failing silently.
- `/done` starts download → rename/remux/metadata → strict-sequence upload.

## Transfer Reliability (v32)

- Download watchdog resets only when the received byte count actually increases.
- A transfer with no new bytes for 45 seconds is treated as stalled and retried.
- Up to 5 download attempts are made with short bounded backoff.
- Retries alternate between the Telegram message and direct `file_id` source.
- Partial/incomplete files are rejected and cleaned before retrying.
- Slow but still-moving downloads are never cancelled just because the speed is low.
- Global transfer pressure is limited to 2 downloads and 2 uploads at a time for better stability on the configured 4-core / 8 GB VPS.

## v34 sequence-order fix

- Queue preview and processing now use the same natural sort order.
- Added robust parsing for bracket/hyphen episode names such as `[S01] [EP-07]`.
- Quality order remains 480p -> 720p -> 1080p, with season/episode ascending inside each quality.
