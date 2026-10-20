"""Face-sample quality checks: size, sharpness, exposure, contrast, pose (landmark-based heuristics), clipping.

Pose values are cheap geometric proxies from 5 landmarks, not calibrated head-pose angles.
Thresholds are provisional; tune them on your own data.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

from .config import QualityConfig
from .types import Detection, QualityReport


def pose_proxies(landmarks: np.ndarray) -> dict[str, float]:
    le, re, nose, lm, rm = np.asarray(landmarks, dtype=np.float64).reshape(5, 2)
    eye_mid = (le + re) / 2
    mouth_mid = (lm + rm) / 2
    eye_dist = max(float(np.linalg.norm(re - le)), 1e-6)
    eye_to_mouth_y = max(float(mouth_mid[1] - eye_mid[1]), 1e-6)
    return {
        "yaw_proxy": float((nose[0] - eye_mid[0]) / eye_dist),
        "pitch_ratio": float((nose[1] - eye_mid[1]) / eye_to_mouth_y),
        "roll_deg": float(math.degrees(math.atan2(re[1] - le[1], re[0] - le[0]))),
    }


def assess_face_quality(frame_bgr: np.ndarray, det: Detection, cfg: QualityConfig) -> QualityReport:
    h, w = frame_bgr.shape[:2]
    x1, y1, x2, y2 = det.bbox
    bw, bh = x2 - x1, y2 - y1
    metrics: dict[str, float] = {"det_score": float(det.score), "face_px": float(min(bw, bh))}
    reasons: list[str] = []

    if bw <= 1 or bh <= 1:
        return QualityReport(False, ["degenerate bounding box"], metrics)

    clipped = 1.0 - (max(0, min(x2, w) - max(x1, 0)) * max(0, min(y2, h) - max(y1, 0))) / (bw * bh)
    metrics["border_clip"] = float(clipped)

    cx1, cy1, cx2, cy2 = max(int(x1), 0), max(int(y1), 0), min(int(x2), w), min(int(y2), h)
    if cx2 - cx1 < 8 or cy2 - cy1 < 8:
        return QualityReport(False, ["face crop outside frame"], metrics)
    gray = cv2.cvtColor(frame_bgr[cy1:cy2, cx1:cx2], cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (112, 112), interpolation=cv2.INTER_AREA)   # size-normalised sharpness measure
    metrics["blur"] = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    metrics["brightness"] = float(gray.mean())
    metrics["contrast"] = float(gray.std())

    if det.score < cfg.min_det_score:
        reasons.append(f"low detection confidence ({det.score:.2f} < {cfg.min_det_score})")
    if metrics["face_px"] < cfg.min_face_px:
        reasons.append(f"face too small ({metrics['face_px']:.0f}px < {cfg.min_face_px:.0f}px)")
    if metrics["border_clip"] > cfg.max_border_clip:
        reasons.append("face cut off by the frame edge")
    if metrics["blur"] < cfg.min_blur:
        reasons.append(f"image too blurry (sharpness {metrics['blur']:.0f} < {cfg.min_blur:.0f})")
    if metrics["brightness"] < cfg.min_brightness:
        reasons.append("too dark")
    elif metrics["brightness"] > cfg.max_brightness:
        reasons.append("too bright / overexposed")
    if metrics["contrast"] < cfg.min_contrast:
        reasons.append("low contrast")

    if det.landmarks is not None:
        p = pose_proxies(det.landmarks)
        metrics.update(p)
        if abs(p["yaw_proxy"]) > cfg.max_yaw_proxy:
            reasons.append("head turned too far sideways")
        if abs(p["roll_deg"]) > cfg.max_roll_deg:
            reasons.append("head tilted too far")
        if not cfg.min_pitch_ratio <= p["pitch_ratio"] <= cfg.max_pitch_ratio:
            reasons.append("head tilted up/down too far")

    return QualityReport(not reasons, reasons, metrics)
