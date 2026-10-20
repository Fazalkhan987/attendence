"""Webcam front-ends: live recognition and guided enrolment capture. Thin layer over the engine services."""
from __future__ import annotations

import logging
import time

import cv2
import numpy as np

from .engine import FaceEngine
from .exceptions import CameraError, InvalidFrameError
from .frames import downscale_to_max_side, validate_frame
from .tracking import SimpleTracker
from .types import Detection, MatchStatus

log = logging.getLogger(__name__)
GREEN, RED, ORANGE, GRAY = (60, 200, 60), (60, 60, 230), (0, 165, 255), (160, 160, 160)


def open_camera(index: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        cap.release()
        raise CameraError(f"cannot open camera {index}. Check that it is connected, not used by another app, "
                          f"and that this terminal/app has camera permission (macOS: System Settings > Privacy; "
                          f"Windows: Settings > Privacy > Camera; Linux: membership of the 'video' group).")
    return cap


def _scale_det(d: Detection, inv: float) -> Detection:
    if inv == 1.0:
        return d
    lm = None if d.landmarks is None else np.asarray(d.landmarks) * inv
    return Detection(tuple(v * inv for v in d.bbox), d.score, lm)


def _show(window: str, frame) -> int:
    try:
        cv2.imshow(window, frame)
    except cv2.error as e:
        raise CameraError("OpenCV was built without GUI support. Install `opencv-python` "
                          "(not `opencv-python-headless`) for the live window.") from e
    return cv2.waitKey(1) & 0xFF


def _label(img, text, org, color, scale=0.55):
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


def run_live(engine: FaceEngine, camera_index: int | None = None, window: str = "face-engine live (q to quit)") -> None:
    cfg = engine.cfg.live
    cap = open_camera(cfg.camera_index if camera_index is None else camera_index)
    tracker = SimpleTracker(cfg.window, cfg.min_votes, cfg.max_track_missed)
    failures, t_prev, fps = 0, time.perf_counter(), 0.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                failures += 1
                if failures > cfg.max_read_failures:
                    raise CameraError("camera stream interrupted (too many consecutive read failures)")
                time.sleep(0.05)
                continue
            failures = 0
            try:
                validate_frame(frame)
                small, s = downscale_to_max_side(frame, cfg.detect_max_side)
                dets = [_scale_det(d, 1.0 / s) for d in engine.detector.detect(small)]
            except InvalidFrameError as e:
                log.warning("skipping invalid frame: %s", e)
                continue

            for track, det in tracker.update(dets):
                if track.last_result is None or track.age - track.last_embedded_age >= cfg.recognition_interval:
                    track.add_result(engine.recognition.identify(frame, det))
                    track.last_embedded_age = track.age
                dec = track.decision()
                x1, y1, x2, y2 = (int(v) for v in det.bbox)
                sim = f"{track.last_result.similarity:.2f}" if track.last_result and track.last_result.similarity is not None else "-"
                if dec.status == MatchStatus.RECOGNIZED:
                    color, title = GREEN, f"{dec.name} ({dec.person_id})"
                elif dec.status == MatchStatus.UNKNOWN:
                    color, title = RED, "Unknown"
                elif dec.status in (MatchStatus.REJECTED_QUALITY, MatchStatus.REJECTED_LIVENESS):
                    why = track.last_result.reasons[0] if track.last_result and track.last_result.reasons else "rejected"
                    color, title = GRAY, f"Rejected: {why}"
                else:
                    color, title = ORANGE, "Verifying..."
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                _label(frame, title, (x1, max(y1 - 24, 14)), color)
                _label(frame, f"det {det.score:.2f} | sim {sim}", (x1, max(y1 - 6, 30)), color, 0.45)

            now = time.perf_counter()
            fps = 0.9 * fps + 0.1 / max(now - t_prev, 1e-6)
            t_prev = now
            _label(frame, f"{fps:.1f} FPS | faces: {len(dets)}", (8, 20), (255, 255, 255))
            if _show(window, frame) in (ord("q"), 27):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


PROMPTS = ["look straight at the camera", "turn slightly left", "turn slightly right",
           "tilt chin slightly up", "tilt chin slightly down", "neutral expression", "slight smile"]


def capture_samples(engine: FaceEngine, camera_index: int | None = None, target: int = 8,
                    min_interval_s: float = 0.7, window: str = "enrolment (SPACE=capture, q=finish)") -> list[np.ndarray]:
    """Guided capture. Frames stay in memory only; auto-captures when quality checks pass."""
    cap = open_camera(engine.cfg.live.camera_index if camera_index is None else camera_index)
    frames: list[np.ndarray] = []
    last_cap, n, failures, msg = 0.0, 0, 0, "waiting for a face"
    try:
        while len(frames) < target:
            ok, frame = cap.read()
            if not ok or frame is None:
                failures += 1
                if failures > engine.cfg.live.max_read_failures:
                    raise CameraError("camera stream interrupted")
                time.sleep(0.05)
                continue
            failures, n = 0, n + 1
            raw = frame.copy()
            good = False
            if n % 3 == 0:
                rep, emb = engine.registration.analyze_image(raw, f"webcam#{len(frames) + 1}")
                good, msg = emb is not None, "good - hold still" if emb is not None else "; ".join(rep.reasons)
            now = time.time()
            if good and now - last_cap >= min_interval_s:
                frames.append(raw)
                last_cap = now
            _label(frame, f"{len(frames)}/{target}  next: {PROMPTS[len(frames) % len(PROMPTS)]}", (8, 22), (255, 255, 255))
            _label(frame, msg, (8, 44), GREEN if good else ORANGE, 0.5)
            key = _show(window, frame)
            if key in (ord("q"), 27):
                break
            if key == ord(" "):
                frames.append(raw)
                last_cap = now
    finally:
        cap.release()
        cv2.destroyAllWindows()
    return frames
