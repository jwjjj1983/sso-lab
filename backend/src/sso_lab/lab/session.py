"""Resolving the visitor's lab session from a request."""

from fastapi import HTTPException, Request, Response

from sso_lab.config import Settings
from sso_lab.lab.models import LabSession, split_cookie
from sso_lab.lab.store import Store

COOKIE = "lab_sid"


async def session_from_cookie(request: Request) -> LabSession | None:
    """The lab session proven by the visitor's cookie (read access to the trace)."""
    store: Store = request.app.state.store
    parsed = split_cookie(request.cookies.get(COOKIE, ""))
    if parsed is None:
        return None
    session_id, secret = parsed
    session = await store.get_session(session_id)
    if session is None or not session.verify(secret):
        return None
    return session


async def require_session(request: Request) -> LabSession:
    session = await session_from_cookie(request)
    if session is None:
        raise HTTPException(status_code=401, detail="No lab session. Start one first.")
    return session


async def session_from_public_id(request: Request, session_id: str | None) -> LabSession | None:
    """A lab session named by its public id, e.g. passed to the IdP in a URL.

    This only authorizes *appending* to that session's trace, never reading it.
    """
    if not session_id or len(session_id) > 64:
        return None
    store: Store = request.app.state.store
    return await store.get_session(session_id)


def set_session_cookie(response: Response, settings: Settings, value: str, max_age: int) -> None:
    response.set_cookie(
        COOKIE,
        value,
        max_age=max_age,
        httponly=True,
        secure=settings.https,
        samesite="lax",
        path="/",
    )
