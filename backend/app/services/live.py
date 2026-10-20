"""Per-connection live recognition session used by the WebSocket endpoint.

Flow per frame: detect -> track -> (re)identify -> temporal vote decision -> attendance (ONLY for a smoothed
RECOGNIZED decision; unknown / uncertain / low-quality faces never create attendance).
"""
from __future__ import annotations

import logging
import time

import cv2
import numpy as np

from face_engine.exceptions import InvalidFrameError, PersonNotFoundError
from face_engine.frames import validate_frame
from face_engine.tracking import SimpleTracker
from face_engine.types import MatchStatus

from .attendance import AttendanceService

log = logging.getLogger(__name__)
MAX_FRAME_BYTES = 3 * 1024 * 1024

_STATUS = {MatchStatus.RECOGNIZED: "recognized", MatchStatus.UNKNOWN: "unknown", MatchStatus.UNCERTAIN: "verifying",
           MatchStatus.REJECTED_QUALITY: "low_quality", MatchStatus.REJECTED_LIVENESS: "low_quality"}


class LiveSession:
    def __init__(self, engine, lock, attendance: AttendanceService):
        c = engine.cfg.live
        self.engine, self.lock, self.attendance = engine, lock, attendance
        self.interval = max(1, c.recognition_interval)
        self.tracker = SimpleTracker(c.window, c.min_votes, c.max_track_missed)
        self.marked: dict[str, dict] = {}              # person_id -> {date, outcome, time, status}

    def process_bytes(self, data: bytes) -> dict:
        if len(data) > MAX_FRAME_BYTES:
            raise InvalidFrameError("frame too large")
        frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise InvalidFrameError("could not decode frame")
        return self.process(frame)

    def process(self, frame: np.ndarray) -> dict:
        t0 = time.perf_counter()
        validate_frame(frame)
        h, w = frame.shape[:2]
        faces, events = [], []
        with self.lock:
            dets = self.engine.detector.detect(frame)
            for track, det in self.tracker.update(dets):
                dec = track.decision()
                due = (track.last_result is None or dec.status != MatchStatus.RECOGNIZED
                       or track.age - track.last_embedded_age >= self.interval)
                if due:
                    track.add_result(self.engine.recognition.identify(frame, det))
                    track.last_embedded_age = track.age
                    dec = track.decision()
                lr = track.last_result
                face = {"id": track.track_id, "bbox": [int(v) for v in det.bbox], "det_score": round(float(det.score), 3),
                        "status": _STATUS.get(dec.status, "verifying"), "person_id": None, "name": None,
                        "similarity": None, "message": None, "attendance": None}
                if dec.status == MatchStatus.RECOGNIZED:
                    face.update(person_id=dec.person_id, name=dec.name,
                                similarity=round(float(dec.similarity), 3) if dec.similarity is not None else None)
                    ev = self._mark(dec.person_id, face["similarity"])
                    if ev:
                        events.append(ev)
                    face["attendance"] = self.marked.get(dec.person_id)
                elif lr is not None:
                    if lr.similarity is not None:
                        face["similarity"] = round(float(lr.similarity), 3)
                    if dec.status in (MatchStatus.REJECTED_QUALITY, MatchStatus.REJECTED_LIVENESS) and lr.reasons:
                        face["message"] = lr.reasons[0]
                faces.append(face)
        return {"type": "result", "width": w, "height": h, "faces": faces, "events": events,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}

    def _mark(self, person_id: str, similarity: float | None) -> dict | None:
        today = self.attendance.today()
        cached = self.marked.get(person_id)
        if cached and cached["date"] == today:
            return None                                  # already handled in this session today
        try:
            name, dept = self.attendance.person_lookup(person_id)
            res = self.attendance.mark_from_face(person_id, name, dept, similarity)
        except PersonNotFoundError:
            return None
        except Exception:                                # DB trouble must not kill the video loop
            log.exception("attendance marking failed for %s", person_id)
            return None
        rec = res["record"]
        info = {"date": today, "outcome": res["outcome"], "time": rec["att_time"], "status": rec["status"]}
        self.marked[person_id] = info
        return {"type": "attendance", "outcome": res["outcome"], "person_id": person_id, "name": name,
                "time": rec["att_time"], "date": today, "status": rec["status"]}
