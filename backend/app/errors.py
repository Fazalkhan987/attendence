"""Application errors + mapping from face_engine exceptions to HTTP semantics."""
from __future__ import annotations

from face_engine import exceptions as fe


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


def map_engine_error(exc: Exception) -> AppError | None:
    if isinstance(exc, fe.PersonNotFoundError):
        return AppError(404, "person_not_found", str(exc))
    if isinstance(exc, fe.DuplicatePersonError):
        return AppError(409, "duplicate_id", str(exc))
    if isinstance(exc, fe.PossibleDuplicateIdentityError):
        cands = [{"person_id": p, "name": n, "similarity": round(float(s), 3)} for p, n, s in exc.candidates]
        return AppError(409, "possible_duplicate_identity", str(exc), {"candidates": cands})
    if isinstance(exc, fe.InsufficientSamplesError):
        return AppError(422, "insufficient_samples", str(exc),
                        {"report": exc.report.to_dict() if exc.report else None})
    if isinstance(exc, fe.ValidationError):
        return AppError(422, "validation_error", str(exc))
    if isinstance(exc, (fe.InvalidFrameError, fe.ImageLoadError)):
        return AppError(400, "invalid_image", str(exc))
    if isinstance(exc, fe.BackendError):
        return AppError(503, "recognition_unavailable", "The recognition engine is unavailable: " + str(exc))
    if isinstance(exc, fe.FaceEngineError):
        return AppError(500, "engine_error", str(exc))
    return None
