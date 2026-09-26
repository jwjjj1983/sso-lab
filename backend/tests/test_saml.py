"""End-to-end SAML: the teaching IdP, App A in guided mode, App B in automatic mode."""

import html
import re

from lxml import etree
from starlette.requests import Request

from sso_lab.config import Actor
from sso_lab.rp.saml import SamlServiceProvider
from sso_lab.saml import NS, decode_post, parse
from tests.conftest import login_form_tx
from tests.test_oidc import sign_in_app_a, start_lab

FLOW_STEPS = [
    "saml.metadata",
    "saml.access",
    "saml.request",
    "saml.redirect",
    "saml.sso",
    "saml.authenticate",
    "saml.issue",
    "saml.post-form",
    "saml.acs",
    "saml.validate",
    "saml.session",
]


def auto_post_form(page: str) -> tuple[str, dict[str, str]]:
    """The IdP's self-submitting form: where it posts, and what."""
    action = html.unescape(re.search(r'<form method="post" action="([^"]+)"', page).group(1))
    fields = {
        name: html.unescape(value)
        for name, value in re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)"', page)
    }
    return action, fields


async def to_idp_login(browser, app: str, query: str):
    resp = await browser.get(browser.url(app, f"/rp/saml/login?{query}"))
    assert resp.status_code == 302
    return await browser.get(resp.headers["location"])


async def saml_sign_in_app_a(browser):
    """App A (guided) -> IdP login -> auto-post form -> App A's ACS."""
    login_page = await to_idp_login(browser, "app-a", "mode=guided")
    assert "Sign in to the lab IdP" in login_page.text
    posted = await browser.post(
        browser.url("idp", "/login"),
        data={"tx": login_form_tx(login_page.text), "username": "alice", "password": "wonderland"},
    )
    assert posted.status_code == 200
    action, fields = auto_post_form(posted.text)
    assert action == browser.url("app-a", "/rp/saml/acs")
    return await browser.post(action, data=fields)


async def test_metadata(browser):
    idp = parse((await browser.get(browser.url("idp", "/saml/metadata"))).content)
    assert idp.get("entityID") == browser.url("idp", "/saml")
    assert idp.findtext(".//ds:X509Certificate", namespaces=NS)
    sso = idp.find(".//md:SingleSignOnService", NS)
    assert sso.get("Location") == browser.url("idp", "/saml/sso")

    sp = parse((await browser.get(browser.url("app-a", "/rp/saml/metadata"))).content)
    acs = sp.find(".//md:AssertionConsumerService", NS)
    assert acs.get("Location") == browser.url("app-a", "/rp/saml/acs")


async def test_guided_flow_end_to_end(browser, lab):
    lab_id = await start_lab(browser)
    acs = await saml_sign_in_app_a(browser)
    assert acs.status_code == 200
    assert "SAML response received" in acs.text

    state = (await browser.get(browser.url("app-a", "/api/lab/saml/state"))).json()
    assert "<samlp:AuthnRequest" in state["request"]["xml"]
    assert "<ds:Signature" in state["response"]
    assert state["session"] is None

    result = (await browser.post(browser.url("app-a", "/api/lab/saml/validate"))).json()
    assert result["ok"], result
    assert len(result["checks"]) == 10 and all(c["ok"] for c in result["checks"])

    state = (await browser.get(browser.url("app-a", "/api/lab/saml/state"))).json()
    assert state["session"]["sub"] == "alice@example.com"
    assert state["session"]["name"] == "Alice Liddell"
    assert state["response"] is None  # consumed

    events = await lab.store.list_events(lab_id)
    seen = {e.step for e in events} | {e.response_step for e in events}
    assert set(FLOW_STEPS) <= seen, set(FLOW_STEPS) - seen
    acs_event = next(e for e in events if e.step == "saml.acs")
    assert acs_event.request.method == "POST" and "SAMLResponse=" in acs_event.request.body


async def test_sso_across_protocols(browser, lab):
    """Signed in through OIDC at App A; App B's SAML sign-in needs no password."""
    lab_id = await start_lab(browser)
    await sign_in_app_a(browser)  # OIDC

    sso = await to_idp_login(browser, "app-b", f"lab_session={lab_id}")
    assert "Sign in to the lab IdP" not in sso.text
    action, fields = auto_post_form(sso.text)
    assert action == browser.url("app-b", "/rp/saml/acs")
    done = await browser.follow(await browser.post(action, data=fields))
    assert "Signed in to App B as Alice Liddell" in done.text

    events = await lab.store.list_events(lab_id)
    assert any(e.step == "saml.sso" and e.note and "single sign-on" in e.note for e in events)


async def test_a_response_can_only_be_used_once(browser):
    await start_lab(browser)
    await sign_in_app_a(browser)
    sso = await to_idp_login(browser, "app-b", "")
    action, fields = auto_post_form(sso.text)
    assert (await browser.post(action, data=fields)).status_code == 302
    replay = await browser.post(action, data=fields)
    assert replay.status_code == 400
    assert "does not answer a request" in replay.text


async def test_idp_only_posts_to_the_registered_acs(browser):
    from sso_lab.saml import encode_redirect

    evil = (
        f'<samlp:AuthnRequest xmlns:samlp="{NS["samlp"]}" xmlns:saml="{NS["saml"]}" ID="_x" '
        'Version="2.0" AssertionConsumerServiceURL="https://evil.example/acs">'
        f"<saml:Issuer>{browser.url('app-a', '/rp/saml')}</saml:Issuer></samlp:AuthnRequest>"
    )
    resp = await browser.get(
        browser.url("idp", "/saml/sso"), params={"SAMLRequest": encode_redirect(evil.encode())}
    )
    assert resp.status_code == 400
    assert "Unregistered ACS URL" in resp.text


# --- What App A checks ----------------------------------------------------------------------


async def _genuine_response(browser, lab) -> tuple[bytes, str]:
    lab_id = await start_lab(browser)
    await saml_sign_in_app_a(browser)
    pending = await lab.store.get_record("samlPending", f"app-a:{lab_id}")
    return decode_post(pending["response"]), pending["request_id"]


def _sp(lab) -> SamlServiceProvider:
    app = lab.app.apps[Actor.APP_A]
    return SamlServiceProvider(
        Request({"type": "http", "app": app, "headers": [], "method": "GET", "path": "/"})
    )


def _failed(result) -> list[str]:
    return [c.label for c in result.checks if not c.ok]


async def test_genuine_response_passes_and_replay_fails(browser, lab):
    xml, request_id = await _genuine_response(browser, lab)
    first = await _sp(lab).validate(xml, request_id, None, guided=False)
    assert first.ok, _failed(first)
    again = await _sp(lab).validate(xml, request_id, None, guided=False)
    assert _failed(again) == ["the assertion ID has not been used before (replay)"]


async def test_edited_assertion_breaks_the_signature(browser, lab):
    xml, request_id = await _genuine_response(browser, lab)
    forged = xml.replace(b"alice@example.com", b"admin@example.com")
    result = await _sp(lab).validate(forged, request_id, None, guided=False)
    assert not result.ok
    assert "the signature is valid, using the certificate from the IdP's metadata" in _failed(
        result
    )


async def test_signature_wrapping_is_detected(browser, lab):
    """XSW: keep the signed assertion, but add a forged one where naive code looks first."""
    xml, request_id = await _genuine_response(browser, lab)
    root = etree.fromstring(xml)
    signed = root.find("saml:Assertion", NS)
    evil = etree.fromstring(etree.tostring(signed))
    evil.set("ID", "_evil")
    evil.remove(evil.find("ds:Signature", NS))
    evil.find("saml:Subject/saml:NameID", NS).text = "admin@example.com"
    signed.addprevious(evil)

    result = await _sp(lab).validate(etree.tostring(root), request_id, None, guided=False)
    assert not result.ok
    assert _failed(result) == [
        "the signature covers the one and only Assertion (no signature wrapping)"
    ]


async def test_response_to_someone_elses_request_is_rejected(browser, lab):
    xml, _ = await _genuine_response(browser, lab)
    result = await _sp(lab).validate(xml, "_a-different-request", None, guided=False)
    assert _failed(result) == ["InResponseTo matches the AuthnRequest this app sent"]


async def test_xml_with_a_dtd_is_refused(browser, lab):
    await start_lab(browser)
    xxe = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><r>&x;</r>'
    result = await _sp(lab).validate(xxe, "_r", None, guided=False)
    assert _failed(result) == ["the XML has no DTD or entities (XXE defense)"]
