from fastapi import APIRouter, Depends

from ..deps import current_user, get_svc

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/dashboard", dependencies=[Depends(current_user)])
def dashboard(svc=Depends(get_svc)):
    return svc.dashboard.summary()


@router.get("/system/status", dependencies=[Depends(current_user)])
def system_status(svc=Depends(get_svc)):
    e = svc.engine
    return {"detector": type(e.detector).__name__, "embedder": e.embedder.model_id, "embedding_dim": e.embedder.embedding_dim,
            "people_with_faces": e.gallery.num_persons, "face_samples": e.gallery.num_samples,
            "recognition_threshold": e.cfg.recognition.threshold, "min_enrollment_samples": e.cfg.enrollment.min_samples,
            "late_after": svc.settings.late_after, "timezone": svc.settings.timezone or "server local time",
            "liveness_check": "not implemented (a printed photo or a screen may be accepted as a face)"}
