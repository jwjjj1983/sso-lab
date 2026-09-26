"""The lab API used by the playground UI (served by app-a, same origin as the SPA)."""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sse_starlette import EventSourceResponse, ServerSentEvent

from sso_lab.config import Actor, Settings
from sso_lab.lab.models import LabSession
from sso_lab.lab.recorder import Recorder
from sso_lab.lab.session import require_session, set_session_cookie
from sso_lab.lab.store import Store

router = APIRouter(prefix="/api/lab", tags=["lab"])

Session = Annotated[LabSession, Depends(require_session)]


class SessionOut(BaseModel):
    id: str
    expires_at: str


class PingResult(BaseModel):
    target: Actor
    status: int | None
    error: str | None = None


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _out(session: LabSession) -> SessionOut:
    return SessionOut(id=session.id, expires_at=session.expires_at.isoformat())


@router.get("/config")
async def config(request: Request) -> dict[str, dict[str, str]]:
    """Public URLs of every actor, so the UI can label and link them."""
    return {"actors": {actor.value: url for actor, url in _settings(request).urls.items()}}


@router.post("/sessions", status_code=201)
async def create_session(request: Request, response: Response) -> SessionOut:
    """Start a fresh lab session (and an empty trace)."""
    settings = _settings(request)
    store: Store = request.app.state.store
    ttl = timedelta(hours=settings.trace_ttl_hours)
    session, cookie_value = LabSession.new(ttl)
    await store.create_session(session)
    set_session_cookie(response, settings, cookie_value, max_age=int(ttl.total_seconds()))
    return _out(session)


@router.get("/session")
async def current_session(session: Session) -> SessionOut:
    return _out(session)


@router.get("/events")
async def events(request: Request, session: Session) -> EventSourceResponse:
    """Server-Sent Events: the whole trace so far, then each new event live.

    On reconnect the full trace is replayed; the client de-duplicates by event id.
    """
    store: Store = request.app.state.store

    async def stream():  # type: ignore[no-untyped-def]
        async for event in store.stream(session.id):
            yield ServerSentEvent(data=event.model_dump_json(), event="trace", id=event.id)

    return EventSourceResponse(stream(), ping=15, headers={"X-Accel-Buffering": "no"})


@router.post("/diagnostics/back-channel")
async def back_channel_diagnostic(request: Request, session: Session) -> list[PingResult]:
    """app-a calls the IdP and app-b server-to-server; both calls appear in the trace."""
    settings = _settings(request)
    recorder: Recorder = request.app.state.recorder
    results = []
    async with recorder.client(lab_session_id=session.id, step="diag.back-channel") as client:
        for target in (Actor.IDP, Actor.APP_B):
            try:
                resp = await client.get(f"{settings.urls[target]}/diag/ping")
                results.append(PingResult(target=target, status=resp.status_code))
            except Exception as exc:
                results.append(PingResult(target=target, status=None, error=type(exc).__name__))
    return results
