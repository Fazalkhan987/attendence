"""Frame / image validation and safe image loading."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .exceptions import ImageLoadError, InvalidFrameError

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


def validate_frame(frame, min_side: int = 32) -> np.ndarray:
    if frame is None or not isinstance(frame, np.ndarray):
        raise InvalidFrameError("frame is None or not a numpy array")
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise InvalidFrameError(f"expected HxWx3 BGR frame, got shape {frame.shape}")
    if frame.dtype != np.uint8:
        raise InvalidFrameError(f"expected uint8 frame, got {frame.dtype}")
    if min(frame.shape[:2]) < min_side:
        raise InvalidFrameError(f"frame too small: {frame.shape[:2]}")
    return frame


def downscale_to_max_side(img: np.ndarray, max_side: int) -> tuple[np.ndarray, float]:
    """Return (image, scale) with scale <= 1 so that max(h, w) <= max_side."""
    h, w = img.shape[:2]
    m = max(h, w)
    if m <= max_side:
        return img, 1.0
    s = max_side / m
    return cv2.resize(img, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA), s


def load_image(path: str | Path, max_file_mb: float = 20, max_side: int = 1920) -> np.ndarray:
    """Load an image as BGR uint8. Raises ImageLoadError for missing, oversized or corrupt files."""
    p = Path(path)
    try:
        size = p.stat().st_size
    except OSError as e:
        raise ImageLoadError(f"cannot access {p.name}: {e.strerror}") from e
    if size == 0:
        raise ImageLoadError(f"{p.name}: empty file")
    if size > max_file_mb * 1024 * 1024:
        raise ImageLoadError(f"{p.name}: file larger than {max_file_mb} MB")
    try:
        data = np.fromfile(str(p), dtype=np.uint8)           # unicode-safe on Windows
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception as e:  # cv2.error and friends
        raise ImageLoadError(f"{p.name}: decode failed ({type(e).__name__})") from e
    if img is None:
        raise ImageLoadError(f"{p.name}: not a decodable image (corrupt or unsupported)")
    img, _ = downscale_to_max_side(img, max_side)
    return img


def iter_image_files(directory: str | Path) -> list[Path]:
    d = Path(directory)
    if not d.is_dir():
        raise ImageLoadError(f"not a directory: {d}")
    return sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)
