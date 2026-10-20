"""Backend registry. Heavy libraries (onnxruntime, insightface) are imported lazily inside the factories."""
from __future__ import annotations

from typing import Callable

from ..config import DetectorConfig, EmbedderConfig
from ..exceptions import ConfigError
from ..interfaces import FaceDetector, FaceEmbedder

_DETECTORS: dict[str, Callable[[DetectorConfig], FaceDetector]] = {}
_EMBEDDERS: dict[str, Callable[[EmbedderConfig], FaceEmbedder]] = {}


def register_detector(name: str, factory) -> None:
    _DETECTORS[name] = factory


def register_embedder(name: str, factory) -> None:
    _EMBEDDERS[name] = factory


def build_detector(cfg: DetectorConfig) -> FaceDetector:
    if cfg.backend == "insightface_scrfd":
        from .insightface_backend import InsightFaceSCRFDDetector
        return InsightFaceSCRFDDetector(cfg)
    if cfg.backend in _DETECTORS:
        return _DETECTORS[cfg.backend](cfg)
    raise ConfigError(f"unknown detector backend '{cfg.backend}'")


def build_embedder(cfg: EmbedderConfig) -> FaceEmbedder:
    if cfg.backend == "insightface_arcface":
        from .insightface_backend import InsightFaceArcFaceEmbedder
        return InsightFaceArcFaceEmbedder(cfg)
    if cfg.backend in _EMBEDDERS:
        return _EMBEDDERS[cfg.backend](cfg)
    raise ConfigError(f"unknown embedder backend '{cfg.backend}'")
