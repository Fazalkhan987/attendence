"""Recognition service: detect -> quality -> (liveness) -> embed -> match -> decision. No webcam code here."""
from __future__ import annotations

import logging

import numpy as np

from .config import QualityConfig, RecognitionConfig
from .exceptions import ConfigError
from .frames import validate_frame
from .gallery import Gallery
from .interfaces import (FaceDetector, FaceEmbedder, LivenessChecker, LivenessStatus, NullLivenessChecker)
from .quality import assess_face_quality
from .types import Detection, MatchStatus, RecognitionResult

log = logging.getLogger(__name__)


class RecognitionService:
    def __init__(self, detector: FaceDetector, embedder: FaceEmbedder, gallery: Gallery,
                 cfg: RecognitionConfig, quality_cfg: QualityConfig, liveness: LivenessChecker | None = None):
        self.detector, self.embedder, self.gallery = detector, embedder, gallery
        self.cfg, self.quality_cfg = cfg, quality_cfg
        self.liveness = liveness or NullLivenessChecker()
        if cfg.require_liveness and not self.liveness.is_real:
            raise ConfigError("recognition.require_liveness=true but no real anti-spoofing checker is configured "
                              "(refusing to start rather than silently skipping the check)")

    def detect(self, frame: np.ndarray) -> list[Detection]:
        return self.detector.detect(validate_frame(frame))

    def identify(self, frame: np.ndarray, det: Detection) -> RecognitionResult:
        """Decide for ONE detected face. Never raises for ordinary bad input; returns a rejected status instead."""
        q = assess_face_quality(frame, det, self.quality_cfg)
        if not q.ok:
            return RecognitionResult(det, MatchStatus.REJECTED_QUALITY, quality=q, reasons=list(q.reasons))

        if self.cfg.require_liveness:
            lv = self.liveness.check(frame, det)
            if lv.status != LivenessStatus.LIVE:
                return RecognitionResult(det, MatchStatus.REJECTED_LIVENESS, quality=q,
                                         reasons=[f"liveness: {lv.status.value} {lv.detail}".strip()])

        emb = self.embedder.embed(frame, det)
        top = self.gallery.top2(emb)
        if not top:
            return RecognitionResult(det, MatchStatus.UNKNOWN, quality=q, reasons=["gallery is empty"])

        best_id, best = top[0]
        runner = top[1][1] if len(top) > 1 else None
        c = self.cfg
        base = dict(detection=det, similarity=best, runner_up_similarity=runner, candidate_id=best_id, quality=q)

        if best >= c.threshold:
            if runner is not None and best - runner < c.margin:
                return RecognitionResult(status=MatchStatus.UNCERTAIN, **base,
                                         reasons=[f"ambiguous: runner-up within margin {c.margin}"])
            return RecognitionResult(status=MatchStatus.RECOGNIZED, person_id=best_id,
                                     name=self.gallery.names.get(best_id), **base)
        if best >= c.threshold - c.uncertain_band:
            return RecognitionResult(status=MatchStatus.UNCERTAIN, **base, reasons=["similarity just below threshold"])
        return RecognitionResult(status=MatchStatus.UNKNOWN, **base)

    def recognize_frame(self, frame: np.ndarray) -> list[RecognitionResult]:
        """All faces in a frame, each decided independently (so a stranger next to a student stays Unknown)."""
        dets = self.detect(frame)
        return [self.identify(frame, d) for d in dets]
