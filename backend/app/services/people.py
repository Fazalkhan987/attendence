"""People management on top of face_engine. Every engine call happens under one lock (the gallery is rebuilt
in memory after each change, and ONNX sessions are shared)."""
from __future__ import annotations

import re

import cv2
import numpy as np

from face_engine.exceptions import PersonNotFoundError
from face_engine.frames import downscale_to_max_side
from face_engine.registration import ImageSample

from ..errors import AppError
from .attendance import AttendanceService

TYPES = ("student", "employee")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^[0-9+()\-.\s]{3,32}$")


def decode_image(data: bytes, max_side: int = 1920) -> np.ndarray | None:
    arr = np.frombuffer(data, dtype=np.uint8)
    if arr.size == 0:
        return None
    try:
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except cv2.error:
        return None
    if img is None:
        return None
    return downscale_to_max_side(img, max_side)[0]


def _clean(v, name: str, maxlen: int, required=False) -> str | None:
    v = (v or "").strip()
    if required and not v:
        raise AppError(422, "validation_error", f"{name} is required.")
    if len(v) > maxlen:
        raise AppError(422, "validation_error", f"{name} must be at most {maxlen} characters.")
    return v or None


class PeopleService:
    def __init__(self, engine, lock, attendance: AttendanceService):
        self.engine, self.lock, self.attendance = engine, lock, attendance

    # ---- serialisation ------------------------------------------------------
    def _dict(self, p) -> dict:
        x = p.extra or {}
        return {"person_id": p.person_id, "full_name": p.full_name, "type": x.get("type", "student"),
                "department": p.department or None, "class_name": p.class_name or None, "email": x.get("email"),
                "phone": x.get("phone"), "notes": x.get("notes"), "registered_at": p.registered_at,
                "updated_at": p.updated_at, "face_samples": p.sample_count,
                "face_status": "registered" if p.sample_count > 0 else "pending"}

    def _validated(self, data: dict) -> tuple[str, str | None, str | None, dict]:
        name = _clean(data.get("full_name"), "Full name", 120, required=True)
        if len(name) < 2:
            raise AppError(422, "validation_error", "Full name must be at least 2 characters.")
        typ = (data.get("type") or "student").strip().lower()
        if typ not in TYPES:
            raise AppError(422, "validation_error", "Type must be 'student' or 'employee'.")
        email, phone = _clean(data.get("email"), "Email", 254), _clean(data.get("phone"), "Phone", 32)
        if email and not _EMAIL.match(email):
            raise AppError(422, "validation_error", "Email address looks invalid.")
        if phone and not _PHONE.match(phone):
            raise AppError(422, "validation_error", "Phone number looks invalid.")
        extra = {"type": typ, "email": email, "phone": phone, "notes": _clean(data.get("notes"), "Notes", 500)}
        return name, _clean(data.get("department"), "Department", 80), _clean(data.get("class_name"), "Class", 80), extra

    # ---- CRUD ---------------------------------------------------------------
    def all(self) -> list[dict]:
        with self.lock:
            return [self._dict(p) for p in self.engine.registration.list_persons()]

    def list(self, q=None, type=None, department=None, face_status=None, page=1, page_size=20) -> dict:
        items = self.all()
        if q and q.strip():
            n = q.strip().lower()
            items = [i for i in items if n in i["person_id"].lower() or n in i["full_name"].lower()
                     or n in (i["department"] or "").lower() or n in (i["class_name"] or "").lower()
                     or n in (i["email"] or "").lower()]
        if type:
            items = [i for i in items if i["type"] == type]
        if department:
            items = [i for i in items if (i["department"] or "") == department]
        if face_status:
            items = [i for i in items if i["face_status"] == face_status]
        items.sort(key=lambda i: i["full_name"].lower())
        total = len(items)
        return {"items": items[(page - 1) * page_size: page * page_size], "total": total, "page": page, "page_size": page_size}

    def departments(self) -> list[str]:
        return sorted({i["department"] for i in self.all() if i["department"]})

    def get(self, person_id: str) -> dict:
        with self.lock:
            return self._dict(self.engine.registration.get_person(person_id))

    def lookup(self, person_id: str) -> tuple[str, str | None]:
        with self.lock:
            p = self.engine.registration.get_person(person_id)        # raises PersonNotFoundError
        return p.full_name, p.department

    def create(self, data: dict, actor: str) -> dict:
        name, dept, cls, extra = self._validated(data)
        with self.lock, self.engine.auth.trusted_session(actor) as s:
            p = self.engine.registration.create_person_record(s, (data.get("person_id") or "").strip(), name, dept, cls, extra)
        return self._dict(p)

    def update(self, person_id: str, data: dict, actor: str) -> dict:
        name, dept, cls, extra = self._validated(data)
        with self.lock, self.engine.auth.trusted_session(actor) as s:
            p = self.engine.registration.update_person(s, person_id, name, dept or "", cls or "", extra)
        self.attendance.sync_person(person_id, p.full_name, p.department or None)
        return self._dict(p)

    def delete(self, person_id: str, actor: str, purge_attendance: bool = False) -> dict:
        with self.lock, self.engine.auth.trusted_session(actor) as s:
            removed = self.engine.registration.delete_person(s, person_id)
        purged = self.attendance.delete_for_person(person_id) if purge_attendance else 0
        return {"deleted": person_id, "face_samples_removed": removed, "attendance_records_removed": purged}

    # ---- faces --------------------------------------------------------------
    def enroll(self, person_id: str, files: list[tuple[str, bytes]], actor: str, allow_possible_duplicate=False) -> dict:
        if not files:
            raise AppError(422, "no_images", "No images were uploaded.")
        samples = []
        for i, (name, data) in enumerate(files):
            img = decode_image(data, self.engine.cfg.enrollment.max_image_side)
            samples.append(ImageSample(name or f"image#{i + 1}", img, None if img is not None else "not a decodable image"))
        with self.lock, self.engine.auth.trusted_session(actor) as s:
            report = self.engine.registration.add_samples(s, person_id, samples, allow_possible_duplicate)
            person = self.engine.registration.get_person(person_id)
        return {"report": report.to_dict(), "person": self._dict(person)}

    def clear_faces(self, person_id: str, actor: str) -> dict:
        with self.lock, self.engine.auth.trusted_session(actor) as s:
            n = self.engine.registration.clear_samples(s, person_id)
            person = self.engine.registration.get_person(person_id)
        return {"removed": n, "person": self._dict(person)}

    def check_frame(self, data: bytes) -> dict:
        """Live feedback while capturing enrolment photos. Nothing is stored."""
        img = decode_image(data, self.engine.cfg.enrollment.max_image_side)
        if img is None:
            raise AppError(400, "invalid_image", "Could not decode the image.")
        with self.lock:
            rep, _ = self.engine.registration.analyze_image(img, "check")
        h, w = img.shape[:2]
        return {"ok": rep.accepted, "reasons": rep.reasons, "bbox": rep.bbox, "width": w, "height": h}
