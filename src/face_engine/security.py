"""Administrator authentication: salted PBKDF2 passcode, lockout after repeated failures, expiring sessions.

This protects the *service layer* (every mutating operation requires a valid AdminSession). It is not a
substitute for OS-level protection of the data directory, disk encryption and network controls.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .config import SecurityConfig
from .exceptions import AuthError, AuthorizationError


@dataclass(frozen=True)
class AdminSession:
    token: str
    actor: str
    expires_at: float


def restrict_permissions(path: Path, is_dir: bool = False) -> None:
    """Owner-only permissions where the OS supports it (no-op semantics on Windows)."""
    try:
        os.chmod(path, 0o700 if is_dir else 0o600)
    except OSError:
        pass


class AdminAuth:
    def __init__(self, path: Path, cfg: SecurityConfig, clock=time.time):
        self.path = Path(path)
        self.cfg = cfg
        self._clock = clock
        self._lock = threading.RLock()
        self._sessions: dict[str, AdminSession] = {}

    # ---- persistence ----------------------------------------------------
    def _read(self) -> dict | None:
        if not self.path.exists():
            return None
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        restrict_permissions(tmp)
        os.replace(tmp, self.path)

    def _hash(self, passcode: str, salt: bytes, iterations: int) -> str:
        return hashlib.pbkdf2_hmac("sha256", passcode.encode("utf-8"), salt, iterations).hex()

    # ---- public API -----------------------------------------------------
    def is_initialized(self) -> bool:
        return self.path.exists()

    def set_passcode(self, new_passcode: str, current_passcode: str | None = None) -> None:
        with self._lock:
            if len(new_passcode) < self.cfg.min_passcode_length:
                raise AuthError(f"passcode must be at least {self.cfg.min_passcode_length} characters")
            if self.is_initialized():
                self._verify(current_passcode or "")
            salt = secrets.token_bytes(16)
            it = self.cfg.pbkdf2_iterations
            self._write({"salt": salt.hex(), "iterations": it, "hash": self._hash(new_passcode, salt, it),
                         "failed": 0, "locked_until": 0})
            self._sessions.clear()

    def _verify(self, passcode: str) -> None:
        data = self._read()
        if data is None:
            raise AuthError("admin passcode has not been set (run init-admin)")
        now = self._clock()
        if data.get("locked_until", 0) > now:
            raise AuthError(f"locked out; try again in {int(data['locked_until'] - now) + 1}s")
        cand = self._hash(passcode, bytes.fromhex(data["salt"]), data["iterations"])
        if hmac.compare_digest(cand, data["hash"]):
            if data.get("failed"):
                data["failed"] = 0
                self._write(data)
            return
        data["failed"] = data.get("failed", 0) + 1
        if data["failed"] >= self.cfg.max_failed_attempts:
            data["locked_until"] = now + self.cfg.lockout_s
            data["failed"] = 0
        self._write(data)
        raise AuthError("invalid passcode")

    def authenticate(self, passcode: str, actor: str = "admin") -> AdminSession:
        with self._lock:
            self._verify(passcode)
            s = AdminSession(secrets.token_urlsafe(32), actor, self._clock() + self.cfg.session_ttl_s)
            self._sessions[s.token] = s
            return s

    @contextmanager
    def trusted_session(self, actor: str = "internal"):
        """Create a short-lived session for an already-authenticated trusted caller."""
        with self._lock:
            session = AdminSession(secrets.token_urlsafe(32), actor, self._clock() + self.cfg.session_ttl_s)
            self._sessions[session.token] = session
        try:
            yield session
        finally:
            self.logout(session)

    def require(self, session: AdminSession | None) -> AdminSession:
        with self._lock:
            known = self._sessions.get(getattr(session, "token", ""))
            if known is None or not hmac.compare_digest(known.token, session.token):
                raise AuthorizationError("administrator authentication required")
            if known.expires_at < self._clock():
                self._sessions.pop(known.token, None)
                raise AuthorizationError("administrator session expired")
            return known

    def logout(self, session: AdminSession) -> None:
        with self._lock:
            self._sessions.pop(session.token, None)
