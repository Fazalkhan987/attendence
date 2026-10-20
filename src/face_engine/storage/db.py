"""SQLite persistence for people and embeddings.

* Embeddings are stored as raw little-endian float32 bytes (optionally Fernet-encrypted). No pickle anywhere.
* No face images are stored by this layer.
* secure_delete is ON and deletions are followed by VACUUM so removed biometric rows do not linger in the file.
* The audit log records who did what to which person_id - never embeddings or images.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ..exceptions import (DuplicatePersonError, ModelMismatchError, PersonNotFoundError, ValidationError)
from ..security import restrict_permissions
from .crypto import VectorCipher

SCHEMA_VERSION = "1"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$")


def validate_person_id(person_id: str) -> str:
    if not isinstance(person_id, str) or not _ID_RE.match(person_id):
        raise ValidationError("person_id must be 1-64 chars: letters, digits, '_', '-', '.' (not starting with a symbol)")
    return person_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class PersonRecord:
    person_id: str
    full_name: str
    department: str | None = None
    class_name: str | None = None
    extra: dict = field(default_factory=dict)
    registered_at: str = ""
    updated_at: str = ""
    sample_count: int = 0

    def to_dict(self) -> dict:
        return dict(self.__dict__)


class Database:
    def __init__(self, path: str | Path, cipher: VectorCipher | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        restrict_permissions(self.path.parent, is_dir=True)
        self._cipher = cipher
        self._lock = threading.RLock()
        self._depth = 0
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA secure_delete=ON")
        self._init_schema()
        restrict_permissions(self.path)

    # ---- plumbing --------------------------------------------------------
    @contextmanager
    def transaction(self):
        with self._lock:
            outer = self._depth == 0
            if outer:
                self._conn.execute("BEGIN IMMEDIATE")
            self._depth += 1
            try:
                yield
            except BaseException:
                if outer:
                    self._conn.execute("ROLLBACK")
                raise
            else:
                if outer:
                    self._conn.execute("COMMIT")
            finally:
                self._depth -= 1

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _init_schema(self) -> None:
        # executescript() issues its own COMMIT, so it must run outside our transaction (statements are idempotent)
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS persons(
                person_id TEXT PRIMARY KEY, full_name TEXT NOT NULL, department TEXT, class_name TEXT,
                extra_json TEXT NOT NULL DEFAULT '{}', registered_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS embeddings(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id TEXT NOT NULL REFERENCES persons(person_id) ON DELETE CASCADE,
                vector BLOB NOT NULL, dim INTEGER NOT NULL, created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_emb_person ON embeddings(person_id);
            CREATE TABLE IF NOT EXISTS audit_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, actor TEXT NOT NULL,
                action TEXT NOT NULL, person_id TEXT, detail TEXT);
            """)
        with self.transaction():
            enc = "1" if self._cipher else "0"
            if self.get_meta("schema_version") is None:
                self.set_meta("schema_version", SCHEMA_VERSION)
                self.set_meta("encrypted", enc)
            elif self.get_meta("encrypted") != enc:
                raise ModelMismatchError("database encryption setting does not match how it was created")

    # ---- meta / model binding -------------------------------------------
    def get_meta(self, key: str) -> str | None:
        r = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r["value"] if r else None

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                           (key, value))

    def bind_model(self, model_id: str, dim: int) -> None:
        """First use records the model; later uses must match (prevents mixing incomparable embeddings)."""
        with self.transaction():
            cur = self.get_meta("model_id")
            if cur is None:
                self.set_meta("model_id", model_id)
                self.set_meta("embedding_dim", str(dim))
            elif cur != model_id or int(self.get_meta("embedding_dim")) != dim:
                raise ModelMismatchError(
                    f"database was built with model '{cur}' (dim {self.get_meta('embedding_dim')}); "
                    f"current model is '{model_id}' (dim {dim}). Re-enroll everyone or use a new database.")

    # ---- persons ---------------------------------------------------------
    def create_person(self, person_id: str, full_name: str, department=None, class_name=None, extra=None) -> None:
        validate_person_id(person_id)
        if not full_name or not full_name.strip():
            raise ValidationError("full_name is required")
        ts = _now()
        with self.transaction():
            try:
                self._conn.execute(
                    "INSERT INTO persons(person_id,full_name,department,class_name,extra_json,registered_at,updated_at)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (person_id, full_name.strip(), department, class_name, json.dumps(extra or {}), ts, ts))
            except sqlite3.IntegrityError as e:
                raise DuplicatePersonError(f"person_id '{person_id}' already exists") from e

    def _row_to_person(self, r) -> PersonRecord:
        return PersonRecord(r["person_id"], r["full_name"], r["department"], r["class_name"],
                            json.loads(r["extra_json"]), r["registered_at"], r["updated_at"], r["n"])

    _SELECT = ("SELECT p.*, (SELECT COUNT(*) FROM embeddings e WHERE e.person_id=p.person_id) AS n FROM persons p")

    def get_person(self, person_id: str) -> PersonRecord:
        with self._lock:
            r = self._conn.execute(self._SELECT + " WHERE p.person_id=?", (person_id,)).fetchone()
        if r is None:
            raise PersonNotFoundError(f"no person with id '{person_id}'")
        return self._row_to_person(r)

    def person_exists(self, person_id: str) -> bool:
        with self._lock:
            return self._conn.execute("SELECT 1 FROM persons WHERE person_id=?", (person_id,)).fetchone() is not None

    def list_persons(self) -> list[PersonRecord]:
        with self._lock:
            rows = self._conn.execute(self._SELECT + " ORDER BY p.person_id").fetchall()
        return [self._row_to_person(r) for r in rows]

    def update_person(self, person_id: str, full_name=None, department=None, class_name=None, extra=None) -> None:
        cur = self.get_person(person_id)
        if full_name is not None and not full_name.strip():
            raise ValidationError("full_name cannot be empty")
        with self.transaction():
            self._conn.execute(
                "UPDATE persons SET full_name=?, department=?, class_name=?, extra_json=?, updated_at=? WHERE person_id=?",
                (full_name.strip() if full_name is not None else cur.full_name,
                 department if department is not None else cur.department,
                 class_name if class_name is not None else cur.class_name,
                 json.dumps(extra if extra is not None else cur.extra), _now(), person_id))

    def delete_person(self, person_id: str) -> int:
        """Delete the person and all their embeddings. Returns number of embeddings removed."""
        n = self.get_person(person_id).sample_count
        with self.transaction():
            self._conn.execute("DELETE FROM persons WHERE person_id=?", (person_id,))
        with self._lock:
            self._conn.execute("VACUUM")          # rewrite file so freed pages are not left behind
        return n

    # ---- embeddings ------------------------------------------------------
    def _encode(self, vec: np.ndarray) -> bytes:
        raw = np.asarray(vec, dtype="<f4").tobytes()
        return self._cipher.encrypt(raw) if self._cipher else raw

    def _decode(self, blob: bytes, dim: int) -> np.ndarray:
        raw = self._cipher.decrypt(blob) if self._cipher else blob
        arr = np.frombuffer(raw, dtype="<f4")
        if arr.size != dim:
            raise ValidationError("corrupt embedding blob")
        return arr.astype(np.float32)

    def add_embeddings(self, person_id: str, vectors: list[np.ndarray]) -> None:
        self.get_person(person_id)
        ts = _now()
        with self.transaction():
            for v in vectors:
                self._conn.execute("INSERT INTO embeddings(person_id,vector,dim,created_at) VALUES(?,?,?,?)",
                                   (person_id, self._encode(v), int(v.size), ts))

    def get_person_embeddings(self, person_id: str) -> np.ndarray:
        with self._lock:
            rows = self._conn.execute("SELECT vector, dim FROM embeddings WHERE person_id=? ORDER BY id",
                                      (person_id,)).fetchall()
        if not rows:
            return np.zeros((0, int(self.get_meta("embedding_dim") or 0)), dtype=np.float32)
        return np.stack([self._decode(r["vector"], r["dim"]) for r in rows])

    def load_all_embeddings(self) -> tuple[list[str], np.ndarray]:
        with self._lock:
            rows = self._conn.execute("SELECT person_id, vector, dim FROM embeddings ORDER BY person_id, id").fetchall()
        if not rows:
            return [], np.zeros((0, 0), dtype=np.float32)
        return [r["person_id"] for r in rows], np.stack([self._decode(r["vector"], r["dim"]) for r in rows])

    # ---- audit -----------------------------------------------------------
    def audit(self, actor: str, action: str, person_id: str | None = None, detail: str | None = None) -> None:
        with self._lock:
            self._conn.execute("INSERT INTO audit_log(ts,actor,action,person_id,detail) VALUES(?,?,?,?,?)",
                               (_now(), actor, action, person_id, detail))

    def audit_entries(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT ts,actor,action,person_id,detail FROM audit_log ORDER BY id DESC LIMIT ?",
                                      (limit,)).fetchall()
        return [dict(r) for r in rows]
