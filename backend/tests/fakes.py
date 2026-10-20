"""Deterministic synthetic detector/embedder so the WHOLE pipeline (storage, registration, recognition,
tracking, evaluation) is tested without model files. These say nothing about real-world accuracy."""
from __future__ import annotations

import numpy as np

from face_engine.config import AppConfig
from face_engine.engine import FaceEngine
from face_engine.interfaces import (FaceDetector, FaceEmbedder, LivenessChecker, LivenessResult, LivenessStatus)
from face_engine.types import Detection

W, H, SLOTS, DIM = 380, 240, 3, 64


def make_frame(identities, brightness=125, blur=False, yaw=0.0, seed=0, face_px=90):
    """identities: list of ints (one face per slot, max 3). Marker pixels at each face centre encode identity+yaw."""
    rng = np.random.default_rng(seed)
    img = np.full((H, W, 3), 30, dtype=np.uint8)
    for slot, ident in enumerate(identities):
        x1, y1 = 15 + 120 * slot, 60
        std = 0.5 if blur else 45.0
        tex = np.clip(brightness + rng.normal(0, std, (face_px, face_px, 1)), 0, 255).astype(np.uint8)
        img[y1:y1 + face_px, x1:x1 + face_px] = np.repeat(tex, 3, axis=2)
        cx, cy = x1 + face_px // 2, y1 + face_px // 2
        img[cy, cx] = (7, 7, ident + 1)
        img[cy, cx + 1] = (7, 8, 128 + int(round(yaw * 100)))
    return img


class FakeDetector(FaceDetector):
    def __init__(self, face_px=90):
        self.face_px = face_px

    def detect(self, frame):
        out = []
        for slot in range(SLOTS):
            x1, y1 = 15 + 120 * slot, 60
            cx, cy = x1 + self.face_px // 2, y1 + self.face_px // 2
            if cy >= frame.shape[0] or cx + 1 >= frame.shape[1]:
                continue
            p, q = frame[cy, cx], frame[cy, cx + 1]
            if p[0] == 7 and p[1] == 7 and p[2] > 0 and q[0] == 7 and q[1] == 8:
                yaw = (int(q[2]) - 128) / 100.0
                s = self.face_px
                eye_d = 0.4 * s
                lm = np.array([[x1 + 0.3 * s, y1 + 0.35 * s], [x1 + 0.7 * s, y1 + 0.35 * s],
                               [x1 + 0.5 * s + yaw * eye_d, y1 + 0.55 * s],
                               [x1 + 0.35 * s, y1 + 0.78 * s], [x1 + 0.65 * s, y1 + 0.78 * s]], dtype=np.float32)
                out.append(Detection((x1, y1, x1 + s, y1 + s), 0.9, lm))
        return out


class FakeEmbedder(FaceEmbedder):
    model_id = "fake-v1"
    embedding_dim = DIM

    def embed(self, frame, det):
        x1, y1, x2, y2 = (int(v) for v in det.bbox)
        ident = int(frame[(y1 + y2) // 2, (x1 + x2) // 2, 2]) - 1
        rng = np.random.default_rng(int(frame[y1:y2, x1:x2].sum()) % (2**32))
        v = np.zeros(DIM, dtype=np.float32)
        v[ident % DIM] = 1.0
        v += 0.05 * rng.standard_normal(DIM).astype(np.float32)
        return (v / np.linalg.norm(v)).astype(np.float32)


class FakeLiveness(LivenessChecker):
    def __init__(self, status):
        self.status = status

    def check(self, frame, det):
        return LivenessResult(self.status, 0.9)


def make_engine(tmp_path, liveness=None, **overrides) -> tuple[FaceEngine, object]:
    cfg = AppConfig()
    cfg.paths.data_dir = str(tmp_path)
    cfg.security.pbkdf2_iterations = 1000
    for k, v in overrides.items():
        section, key = k.split("__")
        setattr(getattr(cfg, section), key, v)
    eng = FaceEngine(cfg, FakeDetector(), FakeEmbedder(), liveness)
    eng.auth.set_passcode("correct horse battery")
    return eng, eng.auth.authenticate("correct horse battery")


def samples(ident, n=6, **kw):
    from face_engine.registration import samples_from_frames
    base = ident * 1000
    return samples_from_frames([make_frame([ident], seed=base + i, **kw) for i in range(n)], prefix=f"id{ident}")
