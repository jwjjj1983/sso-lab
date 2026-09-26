"""Playground controls for the OIDC flow (served by App A, same origin as the SPA).

These endpoints are the lab's remote control, not part of OIDC: each one makes App A perform
one protocol step, which is then recorded to the trace like any other traffic.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from sso_lab.lab.models import LabSession
from sso_lab.lab.session import require_session
from sso_lab.rp.oidc import LOGIN_COOKIE, SESSION_COOKIE, SESSION_TTL, OidcClient

router = APIRouter(prefix="/api/lab/oidc", tags=["lab-oidc"])

Session = Annotated[LabSession, Depends(require_session)]


@router.post("/discovery")
async def discovery(request: Request, lab: Session) -> dict[str, Any]:
    """App A fetches the IdP's discovery document and signing keys (fresh, not from cache)."""
    oidc = OidcClient(request)
    return {
        "discovery": await oidc.discovery(lab.id, force=True),
        "jwks": await oidc.jwks(lab.id, force=True, step="oidc.register"),
    }


@router.get("/state")
async def state(request: Request, lab: Session) -> dict[str, Any]:
    """What App A currently holds for this browser: an in-flight login and/or a session."""
    oidc = OidcClient(request)
    login = await oidc.current_login()
    session = await oidc.current_session()
    return {
        "login": _public_login(login[1]) if login else None,
        "session": _public_session(session[1]) if session else None,
    }


@router.post("/exchange")
async def exchange(request: Request, response: Response, lab: Session) -> dict[str, Any]:
    oidc = OidcClient(request)
    result = await oidc.exchange()
    response.delete_cookie(LOGIN_COOKIE, path="/")
    if result.ok and result.session_id:
        oidc._set_cookie(response, SESSION_COOKIE, result.session_id, SESSION_TTL)
    return {
        "ok": result.ok,
        "error": result.error,
        "checks": [c.model_dump() for c in result.checks],
    }


@router.post("/userinfo")
async def userinfo(request: Request, lab: Session) -> dict[str, Any]:
    oidc = OidcClient(request)
    current = await oidc.current_session()
    if current is None:
        raise HTTPException(status_code=409, detail="App A has no session. Sign in first.")
    status, body = await oidc.userinfo(current[1])
    return {"status": status, "body": body}


@router.post("/refresh")
async def refresh(request: Request, lab: Session) -> dict[str, Any]:
    oidc = OidcClient(request)
    current = await oidc.current_session()
    if current is None:
        raise HTTPException(status_code=409, detail="App A has no session. Sign in first.")
    ok, error = await oidc.refresh(*current)
    return {"ok": ok, "error": error}


@router.post("/logout")
async def logout(request: Request, response: Response, lab: Session) -> dict[str, bool]:
    """Sign out of App A only: the IdP session (and so single sign-on) survives."""
    oidc = OidcClient(request)
    current = await oidc.current_session()
    if current:
        await oidc.store.delete_record("rpSession", current[0])
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


def _public_login(login: dict[str, Any]) -> dict[str, Any]:
    keys = ("state", "nonce", "code_verifier", "code_challenge", "mode", "code")
    return {k: login.get(k) for k in keys}


def _public_session(session: dict[str, Any]) -> dict[str, Any]:
    keys = ("sub", "name", "email", "claims", "id_token", "access_token", "refresh_token")
    return {k: session.get(k) for k in keys}
