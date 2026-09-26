"""Relying-party routes shared by App A and App B. OIDC client flows arrive in M2."""

from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from sso_lab.config import Actor, Settings
from sso_lab.lab.recorder import Recorder
from sso_lab.lab.session import session_from_cookie
from sso_lab.pages import page, post_message_script

router = APIRouter(prefix="/rp", tags=["rp"])

_BADGE = {Actor.APP_A: "App A", Actor.APP_B: "App B"}


def _no_session(actor: Actor) -> Response:
    return page(
        badge=_BADGE[actor],
        title="No lab session",
        body_html="<p>Open this from the SSO Lab playground.</p>",
        status_code=401,
    )


@router.get("/diag/start")
async def diag_start(request: Request) -> Response:
    """First hop of the front-channel diagnostic, opened in the playground's popup."""
    settings: Settings = request.app.state.settings
    recorder: Recorder = request.app.state.recorder
    session = await session_from_cookie(request)
    if session is None:
        return _no_session(recorder.actor)

    query = urlencode(
        {
            "return_to": f"{settings.urls[recorder.actor]}/rp/diag/return",
            "lab_session": session.id,
        }
    )
    response = RedirectResponse(f"{settings.urls[Actor.IDP]}/diag/echo?{query}", status_code=302)
    await recorder.inbound(request, response, lab_session_id=session.id, step="diag.front-channel")
    return response


@router.get("/diag/return")
async def diag_return(request: Request) -> Response:
    """Last hop: tell the playground window the round trip finished, then close the popup."""
    settings: Settings = request.app.state.settings
    recorder: Recorder = request.app.state.recorder
    session = await session_from_cookie(request)
    if session is None:
        return _no_session(recorder.actor)

    response = page(
        badge=_BADGE[recorder.actor],
        title="Round trip complete",
        body_html="<p>Back at the app. This window will close.</p>",
        script=post_message_script(
            {"type": "sso-lab:diag", "ok": True}, settings.origins[Actor.APP_A]
        ),
    )
    await recorder.inbound(request, response, lab_session_id=session.id, step="diag.front-channel")
    return response
