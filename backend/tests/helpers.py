from datetime import datetime, timezone
from pathlib import Path

import cv2

from app.config import Settings
from app.services.container import Services
from fakes import make_engine, make_frame


class Clock:
    def __init__(self, dt=None):
        self.dt = dt or datetime(2026, 3, 2, 8, 30, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.dt


def make_settings(tmp_path, **kw) -> Settings:
    return Settings(data_dir=Path(tmp_path), pbkdf2_iterations=1000, **kw)


def make_services(tmp_path, clock=None, **kw):
    eng, _ = make_engine(Path(tmp_path) / "engine")
    clock = clock or Clock()
    return Services(make_settings(tmp_path, **kw), eng, clock), clock


def png(ident, seed=0, **kw) -> bytes:
    ok, buf = cv2.imencode(".png", make_frame([ident] if not isinstance(ident, list) else ident, seed=seed, **kw))
    assert ok
    return buf.tobytes()


def jpg_of(frame) -> bytes:
    """Lossless PNG despite the name: the synthetic detector reads exact marker pixels, which JPEG would destroy.
    (The browser sends JPEG; a real detector is unaffected.)"""
    return cv2.imencode(".png", frame)[1].tobytes()


def faces_png(ident, n=6):
    return [(f"f{i}.png", png(ident, seed=ident * 1000 + i)) for i in range(n)]


def person(svc, pid="S1", name="Ada Lovelace", **extra):
    d = {"person_id": pid, "full_name": name, "type": "student", "department": "CS"}
    d.update(extra)
    return svc.people.create(d, "web:test")


def enrolled(svc, pid="S1", ident=1, name="Ada Lovelace", **extra):
    person(svc, pid, name, **extra)
    return svc.people.enroll(pid, faces_png(ident), "web:test")
