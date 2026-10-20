from __future__ import annotations

from fastapi import Depends, Request, UploadFile

from .errors import AppError

COOKIE = "sa_session"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_svc(request: Request):
    return request.app.state.svc


def csrf_guard(request: Request) -> None:
    """Cross-site requests cannot add custom headers without a CORS pre-flight (which we do not allow)."""
    if request.method not in SAFE_METHODS and request.headers.get("x-requested-with") != "XMLHttpRequest":
        raise AppError(403, "csrf", "Missing X-Requested-With header.")


def current_user(request: Request) -> dict:
    user = request.app.state.svc.auth.user_for_token(request.cookies.get(COOKIE))
    if user is None:
        raise AppError(401, "not_authenticated", "Please sign in.")
    return user


def actor_of(user: dict) -> str:
    return f"web:{user['username']}"


def read_upload(f: UploadFile, max_mb: float) -> bytes:
    limit = int(max_mb * 1024 * 1024)
    data = f.file.read(limit + 1)
    if len(data) > limit:
        raise AppError(413, "file_too_large", f"{f.filename or 'file'} is larger than {max_mb:g} MB.")
    return data
