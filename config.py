from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    # Test bot configuration intentionally kept in code for this test repository.
    BOT_TOKEN = "8344259766:AAGoVsZAJKoDrTtXUKP8soPe3Rfp3_NkcO4"
    API_ID = 32947515
    API_HASH = "cc73af06049861e86e404ddd1fc6da35"
    OWNER_ID = 8217248864

    DATABASE_URL = "mongodb+srv://Test:Aloksingh@cluster0.gz80cgp.mongodb.net/?appName=Cluster0"
    DATABASE_NAME = "advance_rename_bot"

    SETTINGS_PIC = "https://graph.org/file/29a3acbbab9de5f45a5fe.jpg"
    STATUS_PIC = SETTINGS_PIC

    PORT = 1490
    WEB_SERVER = True
    WORK_DIR = BASE_DIR / "work"

    PUBLIC_BASE_URL = ""
    MEDIAINFO_REPORT_DIR = WORK_DIR / "mediainfo_pages"
    MEDIAINFO_REPORT_TTL = 24 * 60 * 60

    # Transfer tuning for a 4-core / 8 GB VPS.
    PER_USER_JOBS = 2
    DOWNLOAD_CONCURRENCY = 4
    UPLOAD_CONCURRENCY = 4
    PROGRESS_UPDATE_SECONDS = 4.0

    @classmethod
    def validate(cls) -> None:
        missing = []
        if not cls.BOT_TOKEN:
            missing.append("BOT_TOKEN")
        if not cls.API_ID:
            missing.append("API_ID")
        if not cls.API_HASH:
            missing.append("API_HASH")
        if not cls.DATABASE_URL:
            missing.append("DATABASE_URL")
        if not cls.OWNER_ID:
            missing.append("OWNER_ID")
        if not cls.PORT:
            missing.append("PORT")
        if missing:
            raise RuntimeError("Missing required config: " + ", ".join(missing))
