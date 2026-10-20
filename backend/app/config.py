from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path

from .errors import AppError


def _bool(v: str | None, default=False) -> bool:
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    data_dir: Path = Path("./data")
    face_config: str | None = None
    allowed_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])
    cookie_secure: bool = False
    session_ttl_hours: int = 12
    timezone: str | None = None
    late_after: str | None = None            # "HH:MM"
    frontend_dist: Path | None = None
    max_upload_mb: float = 8.0
    max_files_per_upload: int = 30
    pbkdf2_iterations: int = 600_000
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    min_password_length: int = 10
    admin_username: str | None = None
    admin_password: str | None = None

    @property
    def app_db_path(self) -> Path:
        return Path(self.data_dir) / "app.sqlite3"

    def late_after_time(self) -> time | None:
        if not self.late_after:
            return None
        try:
            h, m = self.late_after.split(":")
            return time(int(h), int(m))
        except Exception as e:
            raise ValueError(f"LATE_AFTER must be HH:MM, got {self.late_after!r}") from e

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ.get
        s = cls(
            data_dir=Path(e("DATA_DIR", "./data")),
            face_config=e("FACE_CONFIG") or None,
            allowed_origins=[o.strip() for o in e("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()],
            cookie_secure=_bool(e("COOKIE_SECURE")),
            session_ttl_hours=int(e("SESSION_TTL_HOURS", "12")),
            timezone=e("TIMEZONE") or None,
            late_after=e("LATE_AFTER") or None,
            frontend_dist=Path(e("FRONTEND_DIST")) if e("FRONTEND_DIST") else None,
            admin_username=e("ADMIN_USERNAME") or None,
            admin_password=e("ADMIN_PASSWORD") or None,
        )
        s.late_after_time()          # validate early
        return s
