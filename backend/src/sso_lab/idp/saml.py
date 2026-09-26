"""The teaching IdP's SAML 2.0 endpoints: metadata and SP-initiated single sign-on.

Requests arrive with the HTTP-Redirect binding; signed responses leave with the HTTP-POST
binding (an auto-submitting form). The IdP session is shared with OpenID Connect: sign in once
through either protocol and both kinds of app get single sign-on.
"""

import html
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import Response
from lxml import etree

from sso_lab.config import Actor, Settings
from sso_lab.demo import DEMO_USERS, SAML_IDP_ENTITY_PATH, registered_service_providers
from sso_lab.idp.oidc import TX_COOKIE, TX_TTL, current_session, error_page, login_page
from sso_lab.lab.recorder import Recorder, tag
from sso_lab.lab.session import session_from_public_id
from sso_lab.lab.store import Store
from sso_lab.pages import page
from sso_lab.saml import (
    AUTHN_CONTEXT_PPT,
    BINDING_POST,
    BINDING_REDIRECT,
    NAMEID_EMAIL,
    NS,
    STATUS_SUCCESS,
    UnsafeXml,
    cert_body,
    decode_redirect,
    encode_post,
    idp_credentials,
    instant,
    new_id,
    parse,
    pretty,
    sign,
)

router = APIRouter(prefix="/saml", tags=["saml"])

ASSERTION_TTL = timedelta(minutes=5)


def _q(prefix: str, name: str) -> str:
    return f"{{{NS[prefix]}}}{name}"


def idp_entity_id(settings: Settings) -> str:
    return settings.urls[Actor.IDP] + SAML_IDP_ENTITY_PATH


@router.get("/metadata")
async def metadata(request: Request) -> Response:
    """What an SP admin imports to trust this IdP: entity ID, SSO endpoint, signing certificate."""
    settings: Settings = request.app.state.settings
    _, cert_pem = await idp_credentials(request.app.state.store)
    root = etree.Element(_q("md", "EntityDescriptor"), nsmap={"md": NS["md"], "ds": NS["ds"]})
    root.set("entityID", idp_entity_id(settings))
    idp = etree.SubElement(root, _q("md", "IDPSSODescriptor"))
    idp.set("protocolSupportEnumeration", NS["samlp"])
    idp.set("WantAuthnRequestsSigned", "false")
    key = etree.SubElement(idp, _q("md", "KeyDescriptor"), use="signing")
    x509 = etree.SubElement(etree.SubElement(key, _q("ds", "KeyInfo")), _q("ds", "X509Data"))
    etree.SubElement(x509, _q("ds", "X509Certificate")).text = cert_body(cert_pem)
    etree.SubElement(idp, _q("md", "NameIDFormat")).text = NAMEID_EMAIL
    etree.SubElement(
        idp,
        _q("md", "SingleSignOnService"),
        Binding=BINDING_REDIRECT,
        Location=settings.urls[Actor.IDP] + "/saml/sso",
    )
    return Response(pretty(root), media_type="application/xml")


@router.get("/sso")
async def sso(
    request: Request,
    SAMLRequest: str = "",
    RelayState: str = "",
    lab_session: str = "",
) -> Response:
    settings: Settings = request.app.state.settings
    lab = await session_from_public_id(request, lab_session)
    if lab is not None:
        tag(request, lab.id, "saml.sso")

    # 1. Decode and parse the AuthnRequest safely (no DTDs or entities: XXE).
    try:
        root = parse(decode_redirect(SAMLRequest))
    except (UnsafeXml, ValueError, etree.XMLSyntaxError):
        return error_page("Bad SAML request", "SAMLRequest is not a valid, deflated AuthnRequest.")
    if root.tag != _q("samlp", "AuthnRequest"):
        return error_page("Bad SAML request", "Expected an AuthnRequest.")

    # 2. The SP must be registered, and the response may only ever be posted to the ACS URL
    #    registered for it: otherwise anyone could ask for alice's assertion to be sent to them.
    issuer = root.findtext("saml:Issuer", namespaces=NS) or ""
    sp = registered_service_providers(settings).get(issuer)
    if sp is None:
        return error_page("Unknown service provider", f"No app is registered as {issuer!r}.")
    acs_url = root.get("AssertionConsumerServiceURL") or sp.acs_url
    if acs_url != sp.acs_url:
        return error_page(
            "Unregistered ACS URL", f"{acs_url!r} is not the registered ACS URL for {sp.name}."
        )
    if root.get("ProtocolBinding", BINDING_POST) != BINDING_POST:
        return error_page("Unsupported binding", "Responses are only sent with HTTP-POST.")

    request_data: dict[str, Any] = {
        "protocol": "saml",
        "sp_entity_id": sp.entity_id,
        "acs_url": sp.acs_url,
        "request_id": root.get("ID", ""),
        "relay_state": RelayState,
        "lab_session": lab.id if lab else "",
        "app_name": sp.name,
        "consent": ["Know who you are (your email address)", "See your name"],
    }

    # 3. Single sign-on: an existing IdP session (from a SAML *or* OIDC sign-in) skips the login.
    session = await current_session(request)
    if session is not None and root.get("ForceAuthn") != "true":
        if lab is not None:
            tag(
                request,
                lab.id,
                "saml.sso",
                response_step="saml.post-form",
                note=f"The IdP already has a session for {session['sub']}: no login page. "
                "This is single sign-on.",
            )
        return await issue_response(request, request_data, session["sub"], session["auth_time"])

    # 4. Otherwise show the (shared) login page.
    tx = secrets.token_urlsafe(24)
    store: Store = request.app.state.store
    await store.put_record("idpTx", tx, request_data, TX_TTL)
    response = login_page(request_data, tx)
    response.set_cookie(
        TX_COOKIE, tx, max_age=int(TX_TTL.total_seconds()), httponly=True,
        secure=settings.https, samesite="lax", path="/login",
    )  # fmt: skip
    return response


async def issue_response(
    request: Request, request_data: dict[str, Any], sub: str, auth_time: int
) -> Response:
    """Build and sign the assertion, and hand the browser a form that posts it to the app."""
    settings: Settings = request.app.state.settings
    recorder: Recorder = request.app.state.recorder
    key_pem, cert_pem = await idp_credentials(request.app.state.store)
    user = DEMO_USERS[sub]
    issuer = idp_entity_id(settings)
    now = datetime.now(UTC)
    not_after = instant(now + ASSERTION_TTL)
    acs_url = request_data["acs_url"]
    in_response_to = request_data["request_id"]

    assertion = etree.Element(_q("saml", "Assertion"), nsmap={"saml": NS["saml"], "ds": NS["ds"]})
    assertion.set("ID", new_id())
    assertion.set("Version", "2.0")
    assertion.set("IssueInstant", instant(now))
    etree.SubElement(assertion, _q("saml", "Issuer")).text = issuer
    # The schema wants the signature right after Issuer; signxml fills in this placeholder.
    etree.SubElement(assertion, _q("ds", "Signature"), Id="placeholder")

    subject = etree.SubElement(assertion, _q("saml", "Subject"))
    etree.SubElement(subject, _q("saml", "NameID"), Format=NAMEID_EMAIL).text = user.email
    confirmation = etree.SubElement(
        subject, _q("saml", "SubjectConfirmation"), Method="urn:oasis:names:tc:SAML:2.0:cm:bearer"
    )
    etree.SubElement(
        confirmation,
        _q("saml", "SubjectConfirmationData"),
        InResponseTo=in_response_to,
        Recipient=acs_url,
        NotOnOrAfter=not_after,
    )

    conditions = etree.SubElement(
        assertion, _q("saml", "Conditions"), NotBefore=instant(now), NotOnOrAfter=not_after
    )
    restriction = etree.SubElement(conditions, _q("saml", "AudienceRestriction"))
    etree.SubElement(restriction, _q("saml", "Audience")).text = request_data["sp_entity_id"]

    authn = etree.SubElement(
        assertion,
        _q("saml", "AuthnStatement"),
        AuthnInstant=instant(datetime.fromtimestamp(auth_time, UTC)),
        SessionIndex=new_id(),
    )
    context = etree.SubElement(authn, _q("saml", "AuthnContext"))
    etree.SubElement(context, _q("saml", "AuthnContextClassRef")).text = AUTHN_CONTEXT_PPT

    attributes = etree.SubElement(assertion, _q("saml", "AttributeStatement"))
    for name, value in (("email", user.email), ("name", user.name)):
        attribute = etree.SubElement(attributes, _q("saml", "Attribute"), Name=name)
        etree.SubElement(attribute, _q("saml", "AttributeValue")).text = value

    signed_assertion = sign(assertion, key_pem, cert_pem)

    response = etree.Element(
        _q("samlp", "Response"), nsmap={"samlp": NS["samlp"], "saml": NS["saml"]}
    )
    response.set("ID", new_id())
    response.set("Version", "2.0")
    response.set("IssueInstant", instant(now))
    response.set("Destination", acs_url)
    response.set("InResponseTo", in_response_to)
    etree.SubElement(response, _q("saml", "Issuer")).text = issuer
    status = etree.SubElement(response, _q("samlp", "Status"))
    etree.SubElement(status, _q("samlp", "StatusCode"), Value=STATUS_SUCCESS)
    response.append(signed_assertion)
    xml = etree.tostring(response)

    lab_id = request_data.get("lab_session")
    if lab_id:
        await recorder.local(
            lab_id,
            "saml.issue",
            f"The IdP built an assertion about {user.email} for {request_data['app_name']} "
            "and signed it with its private key.",
            data={"Response": pretty(xml)},
        )

    acs_origin = "{0.scheme}://{0.netloc}".format(urlsplit(acs_url))
    relay = request_data.get("relay_state") or ""
    return page(
        badge="Identity Provider",
        title="Sending you back",
        body_html=f"""
<p>Posting the signed SAML response to {html.escape(request_data["app_name"])}…</p>
<form method="post" action="{html.escape(acs_url)}">
  <input type="hidden" name="SAMLResponse" value="{html.escape(encode_post(xml))}">
  <input type="hidden" name="RelayState" value="{html.escape(relay)}">
  <noscript><button type="submit">Continue</button></noscript>
</form>""",
        script="document.forms[0].submit()",
        form_action=acs_origin,
    )
