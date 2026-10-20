"""FastAPI application factory.

    uvicorn app.main:app --reload        (development)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from face_engine.exceptions import FaceEngineError

from .config import Settings
from .errors import AppError, map_engine_error
from .routers import attendance, auth, live_ws, people, system
from .services.container import Services

log = logging.getLogger("app")


def _load_engine(settings: Settings):
    from face_engine.config import load_config
    from face_engine.engine import FaceEngine
    cfg = load_config(settings.face_config)
    cfg.paths.data_dir = str(settings.data_dir)
    return FaceEngine.from_config(cfg)


class SPAStaticFiles(StaticFiles):
    """Serve the built React app; unknown paths fall back to index.html so client-side routes work on reload."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as ex:
            if ex.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


def create_app(settings: Settings | None = None, engine=None, clock=None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        eng = engine or _load_engine(settings)
        app.state.svc = Services(settings, eng, clock)
        log.info("Smart Attendance started (people with faces: %d)", eng.gallery.num_persons)
        try:
            yield
        finally:
            app.state.svc.close()

    app = FastAPI(title="Smart Attendance API", version="0.1.0", lifespan=lifespan)

    if settings.allowed_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True,
                           allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                           allow_headers=["Content-Type", "X-Requested-With"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Permissions-Policy", "camera=(self), microphone=()")
        if request.url.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(exc.to_dict(), status_code=exc.status)

    @app.exception_handler(FaceEngineError)
    async def _engine_error(_: Request, exc: FaceEngineError):
        mapped = map_engine_error(exc) or AppError(500, "engine_error", str(exc))
        return JSONResponse(mapped.to_dict(), status_code=mapped.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(x) for x in first.get("loc", []) if x not in ("body", "query"))
        err = AppError(422, "validation_error", f"Invalid {loc or 'request'}: {first.get('msg', 'bad value')}")
        return JSONResponse(err.to_dict(), status_code=422)

    for r in (system.router, auth.router, people.router, attendance.router, live_ws.router):
        app.include_router(r)

    if settings.frontend_dist and settings.frontend_dist.is_dir():
        app.mount("/", SPAStaticFiles(directory=str(settings.frontend_dist), html=True), name="frontend")
    return app


app = create_app()
