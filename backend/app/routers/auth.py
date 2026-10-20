from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from ..deps import COOKIE, csrf_guard, current_user, get_svc

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class PasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


@router.post("/login", dependencies=[Depends(csrf_guard)])
def login(body: LoginIn, request: Request, response: Response, svc=Depends(get_svc)):
    token, user = svc.auth.login(body.username, body.password, request.headers.get("user-agent"))
    response.set_cookie(COOKIE, token, httponly=True, secure=svc.settings.cookie_secure, samesite="lax",
                        max_age=svc.settings.session_ttl_hours * 3600, path="/")
    return {"user": user}


@router.post("/logout", dependencies=[Depends(csrf_guard)])
def logout(request: Request, response: Response, svc=Depends(get_svc)):
    svc.auth.logout(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user=Depends(current_user)):
    return {"user": user}


@router.post("/change-password", dependencies=[Depends(csrf_guard)])
def change_password(body: PasswordIn, request: Request, user=Depends(current_user), svc=Depends(get_svc)):
    svc.auth.change_password(user["id"], body.current_password, body.new_password, request.cookies.get(COOKIE))
    return {"ok": True}
