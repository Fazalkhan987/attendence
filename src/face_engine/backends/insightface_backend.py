"""SCRFD detector + ArcFace (w600k_r50) embedder through InsightFace's ONNX model zoo.

NOTE: written against insightface==0.7.3's `insightface.model_zoo.get_model` API (SCRFD.detect / ArcFaceONNX.get_feat).
It could NOT be executed in the authoring environment (no network / no model files). Run `face-engine check`
after installation; if an API differs in your installed version, only this file needs adjusting.

LICENSING: the InsightFace *code* is MIT, but the pretrained model packs (e.g. buffalo_l) are published for
non-commercial research use. Obtain a commercial licence or use differently-licensed weights before any
commercial deployment.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from ..alignment import align_face
from ..config import DetectorConfig, EmbedderConfig
from ..exceptions import BackendError
from ..gallery import l2_normalize
from ..interfaces import FaceDetector, FaceEmbedder
from ..types import Detection

log = logging.getLogger(__name__)


def _load_model(model_path: str, providers: list[str]):
    p = Path(model_path).expanduser()
    if not p.is_file():
        raise BackendError(f"model file not found: {p}. Run `face-engine init-models` (needs internet) "
                           f"or place the ONNX file there manually.")
    try:
        from insightface.model_zoo import get_model
    except ImportError as e:
        raise BackendError("insightface / onnxruntime not installed (pip install insightface==0.7.3 onnxruntime)") from e
    try:
        return get_model(str(p), providers=providers)
    except Exception as e:
        raise BackendError(f"failed to load {p.name}: {e}") from e


class InsightFaceSCRFDDetector(FaceDetector):
    def __init__(self, cfg: DetectorConfig):
        self.cfg = cfg
        self._model = _load_model(cfg.model_path, cfg.providers)
        if not hasattr(self._model, "detect"):
            raise BackendError(f"{cfg.model_path} is not a detection model")
        self._model.prepare(0, input_size=tuple(cfg.det_size), det_thresh=cfg.min_confidence)

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        try:
            bboxes, kpss = self._model.detect(frame_bgr, max_num=0, metric="default")
        except Exception as e:
            raise BackendError(f"detector inference failed: {e}") from e
        out: list[Detection] = []
        for i in range(len(bboxes)):
            score = float(bboxes[i, 4])
            if score < self.cfg.min_confidence:
                continue
            lm = None if kpss is None else np.asarray(kpss[i], dtype=np.float32).reshape(5, 2)
            out.append(Detection(tuple(float(v) for v in bboxes[i, :4]), score, lm))
        return out


class InsightFaceArcFaceEmbedder(FaceEmbedder):
    def __init__(self, cfg: EmbedderConfig):
        self.model_id = cfg.model_id
        self._model = _load_model(cfg.model_path, cfg.providers)
        if not hasattr(self._model, "get_feat"):
            raise BackendError(f"{cfg.model_path} is not a recognition model")
        probe = self._model.get_feat([np.zeros((112, 112, 3), dtype=np.uint8)])
        self.embedding_dim = int(np.asarray(probe).reshape(1, -1).shape[1])

    def embed(self, frame_bgr: np.ndarray, detection: Detection) -> np.ndarray:
        if detection.landmarks is None:
            raise BackendError("ArcFace alignment requires 5-point landmarks")
        aligned = align_face(frame_bgr, detection.landmarks, 112)      # BGR; get_feat swaps to RGB internally
        try:
            feat = self._model.get_feat([aligned])
        except Exception as e:
            raise BackendError(f"embedding inference failed: {e}") from e
        return l2_normalize(np.asarray(feat, dtype=np.float32).reshape(-1))


def download_models(model_pack: str = "buffalo_l", providers=("CPUExecutionProvider",)) -> str:
    """Trigger InsightFace's own downloader (needs internet). Returns the directory holding the models."""
    try:
        from insightface.app import FaceAnalysis
    except ImportError as e:
        raise BackendError("insightface not installed") from e
    FaceAnalysis(name=model_pack, allowed_modules=["detection", "recognition"], providers=list(providers))
    return str(Path("~/.insightface/models").expanduser() / model_pack)
