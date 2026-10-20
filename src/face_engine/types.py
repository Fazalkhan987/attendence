"""Plain data types shared between modules. All have to_dict() so a future API can serialise them."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np


@dataclass(frozen=True)
class Detection:
    bbox: tuple[float, float, float, float]      # x1, y1, x2, y2 in frame pixels
    score: float
    landmarks: np.ndarray | None = None          # (5, 2): L-eye, R-eye, nose, L-mouth, R-mouth (image coordinates)

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]

    @property
    def area(self) -> float:
        return max(self.width, 0.0) * max(self.height, 0.0)

    def to_dict(self) -> dict:
        d = {"bbox": [float(v) for v in self.bbox], "score": float(self.score)}
        if self.landmarks is not None:
            d["landmarks"] = np.asarray(self.landmarks).tolist()
        return d


@dataclass
class QualityReport:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "reasons": list(self.reasons), "metrics": dict(self.metrics)}


class MatchStatus(str, Enum):
    RECOGNIZED = "recognized"
    UNKNOWN = "unknown"
    UNCERTAIN = "uncertain"                  # close to threshold, or ambiguous between two people
    REJECTED_QUALITY = "rejected_quality"
    REJECTED_LIVENESS = "rejected_liveness"


@dataclass
class RecognitionResult:
    detection: Detection
    status: MatchStatus
    person_id: str | None = None             # only set when status == RECOGNIZED
    name: str | None = None
    similarity: float | None = None          # cosine similarity of the best candidate (NOT detection confidence)
    runner_up_similarity: float | None = None
    candidate_id: str | None = None          # best candidate even when not accepted (for debugging UIs)
    quality: QualityReport | None = None
    reasons: list[str] = field(default_factory=list)

    @property
    def det_confidence(self) -> float:
        return float(self.detection.score)

    def to_dict(self) -> dict:
        return {
            "detection": self.detection.to_dict(),
            "status": self.status.value,
            "person_id": self.person_id,
            "name": self.name,
            "similarity": self.similarity,
            "runner_up_similarity": self.runner_up_similarity,
            "candidate_id": self.candidate_id,
            "quality": self.quality.to_dict() if self.quality else None,
            "reasons": list(self.reasons),
        }
