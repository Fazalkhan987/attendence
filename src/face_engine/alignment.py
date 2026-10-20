"""5-point similarity alignment to the 112x112 ArcFace template (standard in the ArcFace/InsightFace family)."""
from __future__ import annotations

import cv2
import numpy as np

ARCFACE_TEMPLATE_112 = np.array(
    [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366], [41.5493, 92.3655], [70.7299, 92.2041]],
    dtype=np.float32)


def estimate_alignment_matrix(landmarks: np.ndarray, size: int = 112) -> np.ndarray:
    lm = np.asarray(landmarks, dtype=np.float32).reshape(5, 2)
    template = ARCFACE_TEMPLATE_112 * (size / 112.0)
    m, _ = cv2.estimateAffinePartial2D(lm, template, method=cv2.LMEDS)   # rotation + uniform scale + shift
    if m is None:
        raise ValueError("could not estimate alignment transform from landmarks")
    return m


def align_face(frame_bgr: np.ndarray, landmarks: np.ndarray, size: int = 112) -> np.ndarray:
    m = estimate_alignment_matrix(landmarks, size)
    return cv2.warpAffine(frame_bgr, m, (size, size), borderValue=0.0)
