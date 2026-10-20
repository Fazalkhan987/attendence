"""Admin accounts, password hashing, lockout and server-side sessions (opaque token in an httpOnly cookie).

Only the SHA-256 of the session token is stored, so a database leak does not yield usable sessions.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timezone

from ..config import Settings
from ..db import AppDatabase
from ..errors import AppError

_SLIDE_AFTER_S = 300


def _hash_password(password: str, iterations: int, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        _, it, salt, h = stored.split("$")
        cand = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(cand.hex(), h)
    except Exception:
        return False


def _th(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public_user(row) -> dict:
    return {"id": row["id"], "username": row["username"], "display_name": row["display_name"]}


class AuthService:
    def __init__(self, db: AppDatabase, settings: Settings, clock=time.time):
        self.db, self.s, self.clock = db, settings, clock
        self._dummy = _hash_password("dummy-password", settings.pbkdf2_iterations)   # equalises timing for unknown users

    # ---- accounts -----------------------------------------------------------
    def _check_password_policy(self, password: str) -> None:
        if len(password) < self.s.min_password_length:
            raise AppError(422, "weak_password", f"Password must be at least {self.s.min_password_length} characters.")

    def create_admin(self, username: str, password: str, display_name: str | None = None) -> dict:
        username = username.strip()
        if not (3 <= len(username) <= 64) or not username.replace("_", "").replace(".", "").replace("-", "").isalnum():
            raise AppError(422, "invalid_username", "Username must be 3-64 characters (letters, digits, . _ -).")
        self._check_password_policy(password)
        if self.db.one("SELECT 1 FROM admin_users WHERE username=?", (username,)):
            raise AppError(409, "username_taken", "That username already exists.")
        self.db.execute(
            "INSERT INTO admin_users(username, display_name, password_hash, created_at) VALUES(?,?,?,?)",
            (username, (display_name or username).strip(), _hash_password(password, self.s.pbkdf2_iterations),
             datetime.now(timezone.utc).isoformat(timespec="seconds")))
        return public_user(self.db.one("SELECT * FROM admin_users WHERE username=?", (username,)))

    def has_admins(self) -> bool:
        return self.db.one("SELECT 1 FROM admin_users LIMIT 1") is not None

    def set_password(self, username: str, password: str) -> None:
        self._check_password_policy(password)
        n = self.db.execute("UPDATE admin_users SET password_hash=?, failed_attempts=0, locked_until=0 WHERE username=?",
                            (_hash_password(password, self.s.pbkdf2_iterations), username)).rowcount
        if not n:
            raise AppError(404, "user_not_found", "No such user.")
        self.db.execute("DELETE FROM sessions WHERE user_id=(SELECT id FROM admin_users WHERE username=?)", (username,))

    # ---- login / sessions ---------------------------------------------------
    def login(self, username: str, password: str, user_agent: str | None = None) -> tuple[str, dict]:
        now = self.clock()
        row = self.db.one("SELECT * FROM admin_users WHERE username=?", (username.strip(),))
        if row is None or not row["is_active"]:
            _verify_password(password, self._dummy)
            raise AppError(401, "invalid_credentials", "Invalid username or password.")
        if row["locked_until"] > now:
            raise AppError(429, "locked", f"Too many failed attempts. Try again in {int((row['locked_until'] - now) // 60) + 1} min.")
        if not _verify_password(password, row["password_hash"]):
            fails = row["failed_attempts"] + 1
            locked = now + self.s.lockout_minutes * 60 if fails >= self.s.max_failed_logins else 0
            self.db.execute("UPDATE admin_users SET failed_attempts=?, locked_until=? WHERE id=?",
                            (0 if locked else fails, locked, row["id"]))
            raise AppError(401, "invalid_credentials", "Invalid username or password.")
        if row["failed_attempts"] or row["locked_until"]:
            self.db.execute("UPDATE admin_users SET failed_attempts=0, locked_until=0 WHERE id=?", (row["id"],))
        token = secrets.token_urlsafe(32)
        self.db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))          # housekeeping
        self.db.execute("INSERT INTO sessions(token_hash,user_id,created_at,expires_at,last_seen,user_agent) VALUES(?,?,?,?,?,?)",
                        (_th(token), row["id"], now, now + self.s.session_ttl_hours * 3600, now, (user_agent or "")[:200]))
        return token, public_user(row)

    def user_for_token(self, token: str | None) -> dict | None:
        if not token:
            return None
        now = self.clock()
        r = self.db.one("""SELECT s.token_hash, s.expires_at, s.last_seen, u.* FROM sessions s
                           JOIN admin_users u ON u.id = s.user_id WHERE s.token_hash=?""", (_th(token),))
        if r is None or r["expires_at"] < now or not r["is_active"]:
            if r is not None:
                self.db.execute("DELETE FROM sessions WHERE token_hash=?", (r["token_hash"],))
            return None
        if now - r["last_seen"] > _SLIDE_AFTER_S:                                   # sliding expiry
            self.db.execute("UPDATE sessions SET last_seen=?, expires_at=? WHERE token_hash=?",
                            (now, now + self.s.session_ttl_hours * 3600, r["token_hash"]))
        return public_user(r)

    def logout(self, token: str | None) -> None:
        if token:
            self.db.execute("DELETE FROM sessions WHERE token_hash=?", (_th(token),))

    def change_password(self, user_id: int, current: str, new: str, keep_token: str | None = None) -> None:
        row = self.db.one("SELECT * FROM admin_users WHERE id=?", (user_id,))
        if row is None or not _verify_password(current, row["password_hash"]):
            raise AppError(403, "wrong_password", "Current password is incorrect.")
        self._check_password_policy(new)
        self.db.execute("UPDATE admin_users SET password_hash=? WHERE id=?",
                        (_hash_password(new, self.s.pbkdf2_iterations), user_id))
        self.db.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?", (user_id, _th(keep_token or "")))
