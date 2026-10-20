"""Attendance records. One record per person per day (UNIQUE(person_id, att_date)) enforced by the database,
so concurrent detections can never create duplicates."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ..config import Settings
from ..db import AppDatabase
from ..errors import AppError

STATUSES = ("present", "late", "absent", "excused")
COUNTED_PRESENT = ("present", "late")


@dataclass
class AttendanceFilter:
    date_from: str | None = None
    date_to: str | None = None
    q: str | None = None
    status: str | None = None
    person_id: str | None = None


def _check_date(v: str | None, field: str) -> str | None:
    if v in (None, ""):
        return None
    try:
        return date.fromisoformat(v).isoformat()
    except ValueError as e:
        raise AppError(422, "invalid_date", f"{field} must be YYYY-MM-DD.") from e


def _row(r) -> dict:
    return {k: r[k] for k in ("id", "person_id", "person_name", "department", "att_date", "att_time", "status",
                              "source", "confidence", "note", "marked_by")}


class AttendanceService:
    def __init__(self, db: AppDatabase, settings: Settings, person_lookup, clock=None):
        """person_lookup(person_id) -> (full_name, department) or raises PersonNotFoundError."""
        self.db, self.s, self.person_lookup = db, settings, person_lookup
        self._tz = ZoneInfo(settings.timezone) if settings.timezone else None
        self._clock = clock
        self._late_after = settings.late_after_time()

    # ---- time ---------------------------------------------------------------
    def now(self) -> datetime:
        if self._clock:
            return self._clock()
        return datetime.now(self._tz) if self._tz else datetime.now().astimezone()

    def today(self) -> str:
        return self.now().date().isoformat()

    def _auto_status(self, now: datetime) -> str:
        return "late" if self._late_after and now.time() > self._late_after else "present"

    # ---- automatic marking (face recognition) -------------------------------------
    def mark_from_face(self, person_id: str, name: str, department: str | None, confidence: float | None) -> dict:
        """Returns {"outcome": created|updated|already_marked, "record": {...}}. Never creates a second row."""
        now = self.now()
        d, t, status = now.date().isoformat(), now.strftime("%H:%M:%S"), self._auto_status(now)
        try:
            with self.db.tx() as c:
                existing = c.execute("SELECT * FROM attendance WHERE person_id=? AND att_date=?", (person_id, d)).fetchone()
                if existing is None:
                    c.execute("""INSERT INTO attendance(person_id,person_name,department,att_date,att_time,status,source,
                                 confidence,marked_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                              (person_id, name, department, d, t, status, "face", confidence, "face-recognition",
                               datetime.now(timezone.utc).isoformat(timespec="seconds")))
                    outcome = "created"
                elif existing["status"] == "absent":          # face evidence overrides a pending 'absent' mark
                    c.execute("UPDATE attendance SET status=?, att_time=?, source='face', confidence=?, marked_by=? WHERE id=?",
                              (status, t, confidence, "face-recognition", existing["id"]))
                    outcome = "updated"
                else:
                    outcome = "already_marked"
        except sqlite3.IntegrityError:                          # lost a race: another writer inserted first
            outcome = "already_marked"
        rec = self.db.one("SELECT * FROM attendance WHERE person_id=? AND att_date=?", (person_id, d))
        return {"outcome": outcome, "record": _row(rec)}

    # ---- manual management ------------------------------------------------------
    def create_manual(self, person_id: str, status: str, att_date: str | None, att_time: str | None,
                      note: str | None, actor: str) -> dict:
        if status not in STATUSES:
            raise AppError(422, "invalid_status", f"status must be one of {', '.join(STATUSES)}.")
        name, dept = self.person_lookup(person_id)
        d = _check_date(att_date, "date") or self.today()
        t = self._check_time(att_time) if att_time else self.now().strftime("%H:%M:%S")
        try:
            with self.db.tx() as c:
                c.execute("""INSERT INTO attendance(person_id,person_name,department,att_date,att_time,status,source,
                             note,marked_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                          (person_id, name, dept, d, t, status, "manual", (note or "")[:300] or None, actor,
                           datetime.now(timezone.utc).isoformat(timespec="seconds")))
        except sqlite3.IntegrityError as e:
            raise AppError(409, "duplicate_attendance", f"{person_id} already has an attendance record for {d}.") from e
        return _row(self.db.one("SELECT * FROM attendance WHERE person_id=? AND att_date=?", (person_id, d)))

    @staticmethod
    def _check_time(v: str) -> str:
        try:
            return datetime.strptime(v, "%H:%M:%S" if v.count(":") == 2 else "%H:%M").strftime("%H:%M:%S")
        except ValueError as e:
            raise AppError(422, "invalid_time", "time must be HH:MM or HH:MM:SS.") from e

    def update(self, record_id: int, status: str | None, att_time: str | None, note: str | None, actor: str) -> dict:
        row = self.db.one("SELECT * FROM attendance WHERE id=?", (record_id,))
        if row is None:
            raise AppError(404, "attendance_not_found", "Attendance record not found.")
        if status is not None and status not in STATUSES:
            raise AppError(422, "invalid_status", f"status must be one of {', '.join(STATUSES)}.")
        self.db.execute("UPDATE attendance SET status=?, att_time=?, note=?, marked_by=? WHERE id=?",
                        (status or row["status"], self._check_time(att_time) if att_time else row["att_time"],
                         row["note"] if note is None else (note[:300] or None), actor, record_id))
        return _row(self.db.one("SELECT * FROM attendance WHERE id=?", (record_id,)))

    def delete(self, record_id: int) -> None:
        if not self.db.execute("DELETE FROM attendance WHERE id=?", (record_id,)).rowcount:
            raise AppError(404, "attendance_not_found", "Attendance record not found.")

    # ---- person sync ----------------------------------------------------------
    def sync_person(self, person_id: str, name: str, department: str | None) -> None:
        self.db.execute("UPDATE attendance SET person_name=?, department=? WHERE person_id=?", (name, department, person_id))

    def delete_for_person(self, person_id: str) -> int:
        return self.db.execute("DELETE FROM attendance WHERE person_id=?", (person_id,)).rowcount

    # ---- queries ----------------------------------------------------------------
    def _where(self, f: AttendanceFilter) -> tuple[str, list]:
        cond, args = [], []
        df, dt = _check_date(f.date_from, "date_from"), _check_date(f.date_to, "date_to")
        if df and dt and df > dt:
            raise AppError(422, "invalid_range", "date_from must not be after date_to.")
        if df:
            cond.append("att_date >= ?"); args.append(df)
        if dt:
            cond.append("att_date <= ?"); args.append(dt)
        if f.status:
            if f.status not in STATUSES:
                raise AppError(422, "invalid_status", "Unknown status filter.")
            cond.append("status = ?"); args.append(f.status)
        if f.person_id:
            cond.append("person_id = ?"); args.append(f.person_id)
        if f.q and f.q.strip():
            like = "%" + f.q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            cond.append("(person_id LIKE ? ESCAPE '\\' OR person_name LIKE ? ESCAPE '\\' OR COALESCE(department,'') LIKE ? ESCAPE '\\')")
            args += [like, like, like]
        return (" WHERE " + " AND ".join(cond)) if cond else "", args

    def list(self, f: AttendanceFilter, page: int = 1, page_size: int = 25) -> dict:
        where, args = self._where(f)
        total = self.db.one("SELECT COUNT(*) AS n FROM attendance" + where, args)["n"]
        rows = self.db.query("SELECT * FROM attendance" + where + " ORDER BY att_date DESC, att_time DESC, id DESC LIMIT ? OFFSET ?",
                             args + [page_size, (page - 1) * page_size])
        return {"items": [_row(r) for r in rows], "total": total, "page": page, "page_size": page_size}

    def export_rows(self, f: AttendanceFilter, limit: int = 100_000) -> list[dict]:
        where, args = self._where(f)
        rows = self.db.query("SELECT * FROM attendance" + where + " ORDER BY att_date DESC, att_time DESC, id DESC LIMIT ?",
                             args + [limit])
        return [_row(r) for r in rows]

    def counts_for_date(self, d: str) -> dict[str, int]:
        out = {s: 0 for s in STATUSES}
        for r in self.db.query("SELECT status, COUNT(*) AS n FROM attendance WHERE att_date=? GROUP BY status", (d,)):
            out[r["status"]] = r["n"]
        return out

    def present_ids_for_date(self, d: str) -> set[str]:
        return {r["person_id"] for r in self.db.query(
            "SELECT person_id FROM attendance WHERE att_date=? AND status IN ('present','late')", (d,))}

    def trend(self, days: int = 7) -> list[dict]:
        end = self.now().date()
        start = end - timedelta(days=days - 1)
        got = {r["att_date"]: r for r in self.db.query(
            """SELECT att_date, SUM(status='present') AS present, SUM(status='late') AS late FROM attendance
               WHERE att_date BETWEEN ? AND ? GROUP BY att_date""", (start.isoformat(), end.isoformat()))}
        out = []
        for i in range(days):
            d = (start + timedelta(days=i)).isoformat()
            r = got.get(d)
            out.append({"date": d, "present": int(r["present"] or 0) if r else 0, "late": int(r["late"] or 0) if r else 0})
        return out

    def recent(self, limit: int = 10) -> list[dict]:
        return [_row(r) for r in self.db.query("SELECT * FROM attendance ORDER BY att_date DESC, att_time DESC, id DESC LIMIT ?", (limit,))]
