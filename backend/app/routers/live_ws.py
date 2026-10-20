import logging
import time
from urllib.parse import urlparse

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from face_engine.exceptions import FaceEngineError, InvalidFrameError

from ..deps import COOKIE
from ..errors import map_engine_error
from ..services.live import LiveSession

log = logging.getLogger(__name__)
router = APIRouter()


def origin_allowed(origin: str | None, host: str | None, allowed: list[str]) -> bool:
    if not origin:
        return True                                  # non-browser client; the session cookie is still required
    return origin in allowed or (host is not None and urlparse(origin).netloc == host)


@router.websocket("/ws/live")
async def live(ws: WebSocket):
    svc = ws.app.state.svc
    await ws.accept()
    if not origin_allowed(ws.headers.get("origin"), ws.headers.get("host"), svc.settings.allowed_origins):
        await ws.close(code=4403)
        return
    token = ws.cookies.get(COOKIE)
    if svc.auth.user_for_token(token) is None:
        await ws.close(code=4401)
        return
    session = LiveSession(svc.engine, svc.lock, svc.attendance)
    last_auth = time.monotonic()
    await ws.send_json({"type": "ready", "date": svc.attendance.today()})
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if time.monotonic() - last_auth > 30:               # session may have been revoked / expired
                if svc.auth.user_for_token(token) is None:
                    await ws.close(code=4401)
                    return
                last_auth = time.monotonic()
            data = msg.get("bytes")
            if data is None:
                if msg.get("text") == "ping":
                    await ws.send_json({"type": "pong"})
                continue
            try:
                result = await run_in_threadpool(session.process_bytes, data)
            except InvalidFrameError as e:
                await ws.send_json({"type": "error", "message": str(e), "fatal": False})
                continue
            except FaceEngineError as e:
                mapped = map_engine_error(e)
                log.warning("live frame failed: %s", e)
                await ws.send_json({"type": "error", "message": mapped.message if mapped else str(e), "fatal": False})
                continue
            await ws.send_json(result)
    except WebSocketDisconnect:
        pass
