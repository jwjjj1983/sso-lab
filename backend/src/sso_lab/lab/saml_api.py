"""Playground controls for the SAML flow (served by App A, same origin as the SPA)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from sso_lab.lab.models import LabSession
from sso_lab.lab.session import require_session
from sso_lab.rp.oidc import SESSION_COOKIE, SESSION_TTL
from sso_lab.rp.saml import SamlServiceProvider
from sso_lab.saml import decode_post, pretty

router = APIRouter(prefix="/api/lab/saml", tags=["lab-saml"])

Session = Annotated[LabSession, Depends(require_session)]


@router.post("/metadata")
async def metadata(request: Request, lab: Session) -> dict[str, str]:
    """App A fetches the IdP's metadata (fresh), and shows its own."""
    sp = SamlServiceProvider(request)
    idp = await sp.idp_metadata(lab.id, force=True)
    return {"idp": idp["xml"], "sp": sp.metadata_xml()}


@router.get("/state")
async def state(request: Request, lab: Session) -> dict[str, Any]:
    sp = SamlServiceProvider(request)
    key = f"{sp.actor.value}:{lab.id}"
    latest = await sp.store.get_record("samlLatest", key)
    pending = await sp.store.get_record("samlPending", key)
    sid = request.cookies.get(SESSION_COOKIE, "")
    session = await sp.store.get_record("rpSession", sid) if sid else None
    if session is not None and (
        session.get("app") != sp.actor.value or session.get("protocol") != "saml"
    ):
        session = None
    return {
        "request": latest,
        "response": pretty(decode_post(pending["response"])) if pending else None,
        "session": {k: session.get(k) for k in ("sub", "name", "email", "claims", "assertion")}
        if session
        else None,
    }


@router.post("/validate")
async def validate(request: Request, response: Response, lab: Session) -> dict[str, Any]:
    """Run App A's checks on the response the IdP posted, and sign in if they all pass."""
    sp = SamlServiceProvider(request)
    pending = await sp.store.take_record("samlPending", f"{sp.actor.value}:{lab.id}")
    if pending is None:
        return {"ok": False, "error": "No SAML response is waiting. Sign in first.", "checks": []}
    result = await sp.validate(
        decode_post(pending["response"]), pending["request_id"], lab.id, guided=True
    )
    if result.ok and result.session_id:
        response.set_cookie(
            SESSION_COOKIE, result.session_id, max_age=int(SESSION_TTL.total_seconds()),
            httponly=True, secure=sp.settings.https, samesite="lax", path="/",
        )  # fmt: skip
    return {
        "ok": result.ok,
        "error": result.error,
        "checks": [c.model_dump() for c in result.checks],
    }
