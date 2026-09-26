"""The apps' SAML 2.0 service provider (App A and App B).

Like the OIDC client: every value the SP creates and every check it makes is explicit and
recorded. ``guided`` mode (the playground) stops once the IdP's response arrives, so the
visitor can run the validation step by hand; ``auto`` mode validates straight away.
"""

import html
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response
from lxml import etree

from sso_lab.config import Actor, Settings
from sso_lab.demo import SAML_ACS_PATH, SAML_ENTITY_PATH
from sso_lab.lab.models import Check
from sso_lab.lab.recorder import Recorder, tag
from sso_lab.lab.session import session_from_cookie, session_from_public_id
from sso_lab.lab.store import Store
from sso_lab.pages import page, post_message_script
from sso_lab.rp.oidc import SESSION_COOKIE, SESSION_TTL
from sso_lab.saml import (
    BINDING_POST,
    BINDING_REDIRECT,
    NAMEID_EMAIL,
    NS,
    STATUS_SUCCESS,
    UnsafeXml,
    cert_pem_from_body,
    decode_post,
    encode_redirect,
    instant,
    new_id,
    parse,
    parse_instant,
    pretty,
    verify,
)

router = APIRouter(prefix="/rp/saml", tags=["rp-saml"])

REQUEST_TTL = timedelta(minutes=10)
CLOCK_SKEW = timedelta(seconds=60)
DONE_PATH = "/rp/saml/done"
_NAMES = {Actor.APP_A: "App A", Actor.APP_B: "App B"}


def _q(prefix: str, name: str) -> str:
    return f"{{{NS[prefix]}}}{name}"


@dataclass
class ValidationResult:
    ok: bool
    error: str | None = None
    session_id: str | None = None
    checks: list[Check] = field(default_factory=list)


class SamlServiceProvider:
    def __init__(self, request: Request) -> None:
        self.request = request
        self.settings: Settings = request.app.state.settings
        self.store: Store = request.app.state.store
        self.recorder: Recorder = request.app.state.recorder
        self.actor: Actor = self.recorder.actor
        self.name = _NAMES[self.actor]
        self.base_url = self.settings.urls[self.actor]
        self.entity_id = self.base_url + SAML_ENTITY_PATH
        self.acs_url = self.base_url + SAML_ACS_PATH
        state = request.app.state
        if not hasattr(state, "saml_metadata"):
            state.saml_metadata = {}
        self._cache: dict[str, Any] = state.saml_metadata

    # --- Trust: the IdP's metadata --------------------------------------------------------

    async def idp_metadata(self, lab_id: str | None, *, force: bool = False) -> dict[str, str]:
        """Entity ID, SSO URL and signing certificate, from the IdP's metadata (cached)."""
        if not force and "idp" in self._cache:
            return self._cache["idp"]
        url = self.settings.urls[Actor.IDP] + "/saml/metadata"
        async with self.recorder.client(lab_session_id=lab_id, step="saml.metadata") as client:
            resp = await client.get(url)
        resp.raise_for_status()
        root = parse(resp.content)
        idp = root.find("md:IDPSSODescriptor", NS)
        cert = idp.findtext(
            ".//md:KeyDescriptor/ds:KeyInfo/ds:X509Data/ds:X509Certificate", namespaces=NS
        )
        sso = next(
            s.get("Location")
            for s in idp.findall("md:SingleSignOnService", NS)
            if s.get("Binding") == BINDING_REDIRECT
        )
        self._cache["idp"] = {
            "entity_id": root.get("entityID"),
            "sso_url": sso,
            "cert_pem": cert_pem_from_body(cert or ""),
            "xml": pretty(root),
        }
        return self._cache["idp"]

    def metadata_xml(self) -> str:
        """This app's own metadata, which an IdP admin would import."""
        root = etree.Element(_q("md", "EntityDescriptor"), nsmap={"md": NS["md"]})
        root.set("entityID", self.entity_id)
        sp = etree.SubElement(root, _q("md", "SPSSODescriptor"))
        sp.set("protocolSupportEnumeration", NS["samlp"])
        sp.set("AuthnRequestsSigned", "false")
        sp.set("WantAssertionsSigned", "true")
        etree.SubElement(sp, _q("md", "NameIDFormat")).text = NAMEID_EMAIL
        etree.SubElement(
            sp,
            _q("md", "AssertionConsumerService"),
            Binding=BINDING_POST,
            Location=self.acs_url,
            index="0",
        )
        return pretty(root)

    # --- Step: send the user to the IdP with an AuthnRequest ---------------------------------

    async def start_login(self, lab_id: str | None, mode: str) -> Response:
        idp = await self.idp_metadata(lab_id)
        request_id = new_id()
        authn = etree.Element(
            _q("samlp", "AuthnRequest"), nsmap={"samlp": NS["samlp"], "saml": NS["saml"]}
        )
        authn.set("ID", request_id)
        authn.set("Version", "2.0")
        authn.set("IssueInstant", instant())
        authn.set("Destination", idp["sso_url"])
        authn.set("AssertionConsumerServiceURL", self.acs_url)
        authn.set("ProtocolBinding", BINDING_POST)
        etree.SubElement(authn, _q("saml", "Issuer")).text = self.entity_id
        etree.SubElement(
            authn, _q("samlp", "NameIDPolicy"), Format=NAMEID_EMAIL, AllowCreate="true"
        )
        xml = etree.tostring(authn)
        encoded = encode_redirect(xml)

        # The response comes back as a cross-site POST, which carries no SameSite=Lax cookies,
        # so the app remembers its request server-side, keyed by the request ID.
        await self.store.put_record(
            "samlRequest",
            request_id,
            {"app": self.actor.value, "lab_session": lab_id or "", "mode": mode},
            REQUEST_TTL,
        )
        if lab_id:
            await self.store.put_record(
                "samlLatest",
                f"{self.actor.value}:{lab_id}",
                {"request_id": request_id, "xml": pretty(xml), "encoded": encoded},
                REQUEST_TTL,
            )
            tag(self.request, lab_id, "saml.access", response_step="saml.redirect")
            await self.recorder.local(
                lab_id,
                "saml.request",
                f"{self.name} built an AuthnRequest with a fresh ID ({request_id}) and remembered "
                "it, so it can match the response later.",
                data={"AuthnRequest": pretty(xml), "SAMLRequest (deflated, base64)": encoded},
            )

        params = {"SAMLRequest": encoded, "RelayState": DONE_PATH}
        if lab_id:
            params["lab_session"] = lab_id  # lab only: lets the IdP add to this visitor's trace
        return RedirectResponse(f"{idp['sso_url']}?{urlencode(params)}", status_code=302)

    # --- Step: the IdP posts the response to the Assertion Consumer Service ------------------

    async def acs(self, saml_response: str, relay_state: str) -> Response:
        try:
            xml = decode_post(saml_response)
            root = parse(xml)
        except (UnsafeXml, ValueError, etree.XMLSyntaxError):
            return self._page(
                "Rejected", "Not a well-formed SAML response (or it contained a DTD).", ok=False
            )

        # InResponseTo is unverified at this point: it is only used to find the pending request.
        request_id = root.get("InResponseTo", "")
        pending = await self.store.take_record("samlRequest", request_id) if request_id else None
        if pending is None or pending.get("app") != self.actor.value:
            return self._page(
                "Rejected",
                "This response does not answer a request this app sent (unsolicited, expired "
                "or replayed).",
                ok=False,
            )
        lab_id = pending["lab_session"] or None
        if lab_id:
            tag(self.request, lab_id, "saml.acs")

        if pending["mode"] == "guided" and lab_id:
            await self.store.put_record(
                "samlPending",
                f"{self.actor.value}:{lab_id}",
                {"response": saml_response, "request_id": request_id},
                REQUEST_TTL,
            )
            return self._page(
                "SAML response received",
                f"{self.name} has the IdP's response but has not trusted it yet. Go back to the "
                "playground to validate it.",
                ok=True,
                stage="response",
            )

        result = await self.validate(xml, request_id, lab_id, guided=False)
        if not result.ok or result.session_id is None:
            return self._page("Sign-in failed", result.error or "invalid response", ok=False)
        if lab_id:
            tag(self.request, lab_id, "saml.acs", response_step="saml.session")
        # Only ever redirect to a path on this app: an open redirect here would be a gift.
        target = (
            relay_state if relay_state.startswith("/") and not relay_state.startswith("//") else "/"
        )
        response = RedirectResponse(self.base_url + target, status_code=302)
        response.set_cookie(
            SESSION_COOKIE, result.session_id, max_age=int(SESSION_TTL.total_seconds()),
            httponly=True, secure=self.settings.https, samesite="lax", path="/",
        )  # fmt: skip
        return response

    # --- Step: validate the response ---------------------------------------------------------

    async def validate(
        self, xml: bytes, expected_request_id: str, lab_id: str | None, *, guided: bool
    ) -> ValidationResult:
        """Everything an SP must check before trusting an assertion, in order."""
        idp = await self.idp_metadata(lab_id)
        now = datetime.now(UTC)
        checks: list[Check] = []

        try:
            root = parse(xml)
            checks.append(Check(label="the XML has no DTD or entities (XXE defense)", ok=True))
        except (UnsafeXml, etree.XMLSyntaxError) as exc:
            checks.append(
                Check(
                    label="the XML has no DTD or entities (XXE defense)", ok=False, detail=str(exc)
                )
            )
            return await self._finish(checks, None, lab_id, guided)

        try:
            signed = verify(xml, idp["cert_pem"])
            checks.append(
                Check(
                    label="the signature is valid, using the certificate from the IdP's metadata",
                    ok=True,
                )
            )
        except Exception as exc:
            signed = None
            checks.append(
                Check(
                    label="the signature is valid, using the certificate from the IdP's metadata",
                    ok=False,
                    detail=type(exc).__name__,
                )
            )

        all_assertions = root.findall(".//saml:Assertion", NS)
        checks.append(
            Check(
                label="the signature covers the one and only Assertion (no signature wrapping)",
                ok=signed is not None
                and signed.tag == _q("saml", "Assertion")
                and len(all_assertions) == 1,
                detail=f"{len(all_assertions)} assertion(s) in the document",
            )
        )
        # From here on, read ONLY from the element the signature covers.
        assertion = (
            signed if signed is not None else (all_assertions[0] if all_assertions else None)
        )
        if assertion is None:
            return await self._finish(checks, None, lab_id, guided)

        status = root.find("samlp:Status/samlp:StatusCode", NS)
        confirmation = assertion.find(".//saml:SubjectConfirmationData", NS)
        conditions = assertion.find("saml:Conditions", NS)
        audience = assertion.findtext(".//saml:AudienceRestriction/saml:Audience", namespaces=NS)
        issuer = assertion.findtext("saml:Issuer", namespaces=NS)
        not_before = parse_instant(conditions.get("NotBefore") if conditions is not None else None)
        not_after = parse_instant(
            conditions.get("NotOnOrAfter") if conditions is not None else None
        )
        confirm_after = parse_instant(
            confirmation.get("NotOnOrAfter") if confirmation is not None else None
        )
        recipient = confirmation.get("Recipient") if confirmation is not None else None
        in_response_to = confirmation.get("InResponseTo") if confirmation is not None else None

        checks += [
            Check(
                label="Status is Success",
                ok=status is not None and status.get("Value") == STATUS_SUCCESS,
            ),
            Check(
                label="Issuer is the IdP's entity ID",
                ok=issuer == idp["entity_id"],
                detail=f"Issuer = {issuer!r}",
            ),
            Check(
                label="Destination and Recipient are this app's ACS URL",
                ok=root.get("Destination") == self.acs_url and recipient == self.acs_url,
                detail=f"Recipient = {recipient!r}",
            ),
            Check(
                label="Audience is this app's entity ID",
                ok=audience == self.entity_id,
                detail=f"Audience = {audience!r}",
            ),
            Check(
                label="InResponseTo matches the AuthnRequest this app sent",
                ok=bool(expected_request_id) and in_response_to == expected_request_id,
                detail=f"InResponseTo = {in_response_to!r}",
            ),
            Check(
                label="now is within NotBefore and NotOnOrAfter",
                ok=not_before is not None
                and not_after is not None
                and confirm_after is not None
                and not_before - CLOCK_SKEW <= now < min(not_after, confirm_after) + CLOCK_SKEW,
                detail=f"valid until {instant(not_after) if not_after else '?'}",
            ),
        ]
        # Replay cache: remember each assertion ID until it expires anyway.
        assertion_id = assertion.get("ID", "")
        fresh = bool(assertion_id) and await self.store.create_record(
            "samlSeen",
            f"{self.actor.value}:{assertion_id}",
            {},
            max((not_after or now) - now, timedelta(seconds=1)) + CLOCK_SKEW,
        )
        checks.append(Check(label="the assertion ID has not been used before (replay)", ok=fresh))
        return await self._finish(checks, assertion, lab_id, guided)

    async def _finish(
        self,
        checks: list[Check],
        assertion: etree._Element | None,
        lab_id: str | None,
        guided: bool,
    ) -> ValidationResult:
        ok = assertion is not None and all(c.ok for c in checks)
        if lab_id:
            await self.recorder.local(
                lab_id,
                "saml.validate",
                f"{self.name} {'accepted' if ok else 'rejected'} the SAML response.",
                checks=checks,
                data={"Assertion (as signed)": pretty(assertion)} if assertion is not None else {},
            )
        if not ok or assertion is None:
            return ValidationResult(
                ok=False, error="The SAML response failed validation.", checks=checks
            )

        name_id = assertion.findtext("saml:Subject/saml:NameID", namespaces=NS) or ""
        attributes = {
            a.get("Name", ""): a.findtext("saml:AttributeValue", namespaces=NS) or ""
            for a in assertion.findall(".//saml:Attribute", NS)
        }
        sid = secrets.token_urlsafe(32)
        await self.store.put_record(
            "rpSession",
            sid,
            {
                "app": self.actor.value,
                "protocol": "saml",
                "sub": name_id,
                "name": attributes.get("name", ""),
                "email": attributes.get("email", name_id),
                "claims": {"NameID": name_id, **attributes},
                "assertion": pretty(assertion),
                "id_token": "",
                "access_token": "",
                "refresh_token": "",
                "lab_session": lab_id or "",
            },
            SESSION_TTL,
        )
        if lab_id and guided:
            await self.recorder.local(
                lab_id,
                "saml.session",
                f"{self.name} created its own session for {name_id}. The assertion has done its "
                "job and is not used again.",
            )
        return ValidationResult(ok=True, session_id=sid, checks=checks)

    def _page(self, title: str, message: str, *, ok: bool, stage: str | None = None) -> Response:
        script = None
        if stage or not ok:
            script = post_message_script(
                {
                    "type": "sso-lab:saml",
                    "app": self.actor.value,
                    "stage": stage or "error",
                    "message": message,
                },
                self.settings.origins[Actor.APP_A],
            )
        return page(
            badge=self.name,
            title=title,
            body_html=f'<p class="{"ok" if ok else "error"}">{html.escape(message)}</p>',
            script=script,
            status_code=200 if ok else 400,
        )


# --- Routes -------------------------------------------------------------------------------


@router.get("/metadata")
async def metadata(request: Request) -> Response:
    return Response(SamlServiceProvider(request).metadata_xml(), media_type="application/xml")


@router.get("/login")
async def login(request: Request, mode: str = "auto", lab_session: str = "") -> Response:
    lab = await session_from_public_id(request, lab_session) or await session_from_cookie(request)
    return await SamlServiceProvider(request).start_login(
        lab.id if lab else None, "guided" if mode == "guided" else "auto"
    )


@router.post("/acs")
async def acs(
    request: Request,
    SAMLResponse: Annotated[str, Form()] = "",
    RelayState: Annotated[str, Form()] = "",
) -> Response:
    return await SamlServiceProvider(request).acs(SAMLResponse, RelayState)


@router.get("/done")
async def done(request: Request) -> Response:
    sp = SamlServiceProvider(request)
    sid = request.cookies.get(SESSION_COOKIE, "")
    session = await sp.store.get_record("rpSession", sid) if sid else None
    if session is None or session.get("app") != sp.actor.value:
        return sp._page("Not signed in", "No session found.", ok=False)
    return sp._page(
        f"Signed in to {sp.name} as {session['name'] or session['sub']}",
        f"{sp.name} trusted the IdP's signed assertion and started its own session.",
        ok=True,
        stage="signed-in",
    )
