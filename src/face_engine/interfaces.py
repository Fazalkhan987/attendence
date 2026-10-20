"""Abstract interfaces. Detector, embedder and liveness checker are independently replaceable."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

import numpy as np

from .types import Detection


class FaceDetector(ABC):
    """Finds faces. Knows nothing about identities."""

    @abstractmethod
    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        """Return detections (>= configured confidence) for a validated BGR uint8 frame."""


class FaceEmbedder(ABC):
    """Turns one detected face into an L2-normalised embedding. Knows nothing about people."""

    model_id: str          # persisted with the gallery; embeddings from different models are never compared
    embedding_dim: int

    @abstractmethod
    def embed(self, frame_bgr: np.ndarray, detection: Detection) -> np.ndarray:
        """Return a float32 unit-norm vector of length embedding_dim."""


class LivenessStatus(str, Enum):
    LIVE = "live"
    SPOOF = "spoof"
    NOT_CHECKED = "not_checked"
    UNCERTAIN = "uncertain"


@dataclass
class LivenessResult:
    status: LivenessStatus
    score: float | None = None
    detail: str = ""


class LivenessChecker(ABC):
    """Presentation-attack detection hook. NOT implemented by any shipped model (see README)."""

    is_real: bool = True   # False for placeholders

    @abstractmethod
    def check(self, frame_bgr: np.ndarray, detection: Detection) -> LivenessResult: ...


class NullLivenessChecker(LivenessChecker):
    """Placeholder: performs NO anti-spoofing and says so."""

    is_real = False

    def check(self, frame_bgr, detection) -> LivenessResult:
        return LivenessResult(LivenessStatus.NOT_CHECKED, None, "no anti-spoofing model installed")
