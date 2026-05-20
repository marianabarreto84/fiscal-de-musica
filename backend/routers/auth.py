import hashlib
import os

from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel

router = APIRouter()

COOKIE_NAME = "fiscal_musica_auth"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 dias


def _site_password() -> str:
    return os.getenv("SITE_PASSWORD", "")


def _auth_token() -> str:
    pw = _site_password()
    if not pw:
        return ""
    return hashlib.sha256(f"fiscal-musica:{pw}".encode("utf-8")).hexdigest()


def _is_authenticated(cookie_value: str | None) -> bool:
    if not _site_password():
        return True
    return cookie_value == _auth_token()


class LoginIn(BaseModel):
    password: str


@router.get("/check")
def check(fiscal_musica_auth: str | None = Cookie(default=None)):
    return {"authenticated": _is_authenticated(fiscal_musica_auth), "required": bool(_site_password())}


@router.post("/login")
def login(body: LoginIn, response: Response):
    if not _site_password():
        return {"authenticated": True, "required": False}
    if body.password != _site_password():
        raise HTTPException(status_code=401, detail="senha incorreta")
    response.set_cookie(
        key=COOKIE_NAME,
        value=_auth_token(),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return {"authenticated": True, "required": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"authenticated": False, "required": bool(_site_password())}
