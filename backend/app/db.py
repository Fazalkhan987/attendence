"""Application database (admins, sessions, attendance). SQLite for development.

Migrations: ordered, idempotent steps tracked with PRAGMA user_version. To move to PostgreSQL later, keep SQL
in this module standard (no SQLite-only functions in queries) and replace this class / adopt Alembic.
People and face embeddings live in the face_engine database (data_dir/face_engine.sqlite3), not here.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS: list[str] = [
    # 1: initial schema
    """
    CREATE TABLE admin_users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        display_name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        failed_attempts INTEGER NOT NULL DEFAULT 0,
        locked_until REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL);
    CREATE TABLE sessions(
        token_hash TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
        created_at REAL NOT NULL, expires_at REAL NOT NULL, last_seen REAL NOT NULL, user_agent TEXT);
    CREATE INDEX idx_sessions_user ON sessions(user_id);
    CREATE TABLE attendance(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id TEXT NOT NULL,
        person_name TEXT NOT NULL,
        department TEXT,
        att_date TEXT NOT NULL,
        att_time TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('present','late','absent','excused')),
        source TEXT NOT NULL CHECK(source IN ('face','manual')),
        confidence REAL,
        note TEXT,
        marked_by TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(person_id, att_date));
    CREATE INDEX idx_att_date ON attendance(att_date);
    """,
]


class AppDatabase:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    def migrate(self) -> None:
        with self._lock:
            current = self.conn.execute("PRAGMA user_version").fetchone()[0]
            for version, sql in enumerate(MIGRATIONS, start=1):
                if version <= current:
                    continue
                self.conn.execute("BEGIN IMMEDIATE")
                try:
                    for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
                        self.conn.execute(stmt)
                    self.conn.execute(f"PRAGMA user_version={version}")
                    self.conn.execute("COMMIT")
                except BaseException:
                    self.conn.execute("ROLLBACK")
                    raise

    @contextmanager
    def tx(self):
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield self.conn
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
            else:
                self.conn.execute("COMMIT")

    def query(self, sql: str, params=()) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, params).fetchall()

    def one(self, sql: str, params=()):
        with self._lock:
            return self.conn.execute(sql, params).fetchone()

    def execute(self, sql: str, params=()) -> sqlite3.Cursor:
        with self._lock:
            return self.conn.execute(sql, params)

    def close(self) -> None:
        with self._lock:
            self.conn.close()
