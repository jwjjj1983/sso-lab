"""IdP routes. M0 has only the diagnostics round trip; OIDC endpoints arrive in M2."""

import html
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from sso_lab.config import Actor, Settings
from sso_lab.lab.recorder import Recorder
from sso_lab.lab.session import session_from_public_id
from sso_lab.pages import page

router = APIRouter(tags=["idp"])


@router.get("/")
async def home(request: Request) -> Response:
    return page(
        badge="Identity Provider",
        title="SSO Lab teaching IdP",
        body_html="<p>This service plays the Identity Provider in the SSO Lab. "
        "Start from the playground in App A.</p>",
    )


@router.get("/diag/echo")
async def diag_echo(
    request: Request, return_to: str = "", lab_session: str | None = None
) -> Response:
    """Front-channel diagnostic hop: receive the browser, send it straight back.

    ``return_to`` must *exactly* match a registered URL. Prefix or pattern matching here is
    the classic open-redirect / code-theft bug the OIDC playground will demonstrate later.
    """
    settings: Settings = request.app.state.settings
    allowed = {f"{settings.urls[app]}/rp/diag/return" for app in (Actor.APP_A, Actor.APP_B)}
    if return_to not in allowed:
        return page(
            badge="Identity Provider",
            title="Unregistered return URL",
            body_html=f"<p>Refusing to redirect to <code>{html.escape(return_to)}</code>: "
            "it is not a registered return URL.</p>",
            status_code=400,
        )

    response = RedirectResponse(f"{return_to}?{urlencode({'from': 'idp'})}", status_code=302)
    session = await session_from_public_id(request, lab_session)
    if session is not None:
        recorder: Recorder = request.app.state.recorder
        await recorder.inbound(
            request, response, lab_session_id=session.id, step="diag.front-channel"
        )
    return response
