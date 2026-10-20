"""Composition root: wires config -> db -> detector/embedder -> services. A future FastAPI app creates ONE
FaceEngine at start-up and calls engine.registration / engine.recognition; nothing here touches the webcam."""
from __future__ import annotations

import os

from .backends import build_detector, build_embedder
from .config import AppConfig
from .exceptions import ConfigError
from .gallery import Gallery
from .interfaces import FaceDetector, FaceEmbedder, LivenessChecker
from .logging_setup import setup_logging
from .recognition import RecognitionService
from .registration import RegistrationService
from .security import AdminAuth
from .storage.crypto import VectorCipher
from .storage.db import Database


class FaceEngine:
    def __init__(self, cfg: AppConfig, detector: FaceDetector, embedder: FaceEmbedder,
                 liveness: LivenessChecker | None = None, db: Database | None = None):
        self.cfg = cfg
        cipher = None
        if cfg.security.encrypt_embeddings:
            key = os.environ.get(cfg.security.key_env)
            if not key:
                raise ConfigError(f"encrypt_embeddings=true but env var {cfg.security.key_env} is not set")
            cipher = VectorCipher(key)
        self.db = db or Database(cfg.db_path, cipher)
        self.auth = AdminAuth(cfg.admin_path, cfg.security)
        self.detector, self.embedder = detector, embedder
        self.gallery = Gallery(cfg.recognition.score_mode, cfg.recognition.topk)
        self.registration = RegistrationService(self.db, detector, embedder, self.gallery, self.auth,
                                                cfg.enrollment, cfg.quality_enroll)
        self.recognition = RecognitionService(detector, embedder, self.gallery, cfg.recognition,
                                              cfg.quality_live, liveness)

    @classmethod
    def from_config(cls, cfg: AppConfig, liveness: LivenessChecker | None = None) -> "FaceEngine":
        setup_logging(cfg.logging.level, cfg.data_dir / "logs" / "face_engine.log")
        return cls(cfg, build_detector(cfg.detector), build_embedder(cfg.embedder), liveness)

    def close(self) -> None:
        self.db.close()
