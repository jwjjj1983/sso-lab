"""End-to-end OIDC: the teaching IdP, App A in guided mode, App B in automatic mode."""

import base64
import hashlib
import json
import secrets
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from joserfc import jwt
from starlette.requests import Request

from sso_lab.config import Actor
from sso_lab.idp.keys import signing_key
from sso_lab.rp.oidc import OidcClient
from tests.conftest import login_form_tx

FLOW_STEPS = [
    "oidc.register",
    "oidc.login",
    "oidc.prepare",
    "oidc.authorize-redirect",
    "oidc.authorize",
    "oidc.authenticate",
    "oidc.issue-code",
    "oidc.callback",
    "oidc.token",
    "oidc.tokens",
    "oidc.validate",
    "oidc.session",
]


async def start_lab(browser) -> str:
    resp = await browser.post(browser.url("app-a", "/api/lab/sessions"))
    return resp.json()["id"]


async def sign_in_app_a(browser, password: str = "wonderland"):
    """Drive the popup: App A -> IdP login page -> submit -> back to App A's callback."""
    login_page = await browser.follow(
        await browser.get(browser.url("app-a", "/rp/oidc/login?mode=guided"))
    )
    assert "Sign in to the lab IdP" in login_page.text
    resp = await browser.post(
        browser.url("idp", "/login"),
        data={"tx": login_form_tx(login_page.text), "username": "alice", "password": password},
    )
    return await browser.follow(resp)


def _query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


# --- IdP metadata -------------------------------------------------------------------------


async def test_discovery_describes_the_idp(browser):
    doc = (await browser.get(browser.url("idp", "/.well-known/openid-configuration"))).json()
    issuer = browser.url("idp", "")
    assert doc["issuer"] == issuer
    assert doc["token_endpoint"] == f"{issuer}/token"
    assert doc["code_challenge_methods_supported"] == ["S256"]

    jwks = (await browser.get(doc["jwks_uri"])).json()
    [key] = jwks["keys"]
    assert key["kty"] == "RSA" and key["alg"] == "RS256" and key["kid"]
    assert "d" not in key  # never publish the private part


# --- Authorization endpoint ---------------------------------------------------------------


async def test_unregistered_redirect_uri_is_refused_without_redirecting(browser):
    resp = await browser.get(
        browser.url("idp", "/authorize"),
        params={
            "client_id": "app-a",
            "redirect_uri": "https://evil.example/callback",
            "response_type": "code",
            "scope": "openid",
            "code_challenge": "x",
            "code_challenge_method": "S256",
        },
    )
    assert resp.status_code == 400
    assert "location" not in resp.headers


async def test_pkce_is_required(browser):
    redirect_uri = browser.url("app-a", "/rp/oidc/callback")
    resp = await browser.get(
        browser.url("idp", "/authorize"),
        params={
            "client_id": "app-a",
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid",
            "state": "s1",
        },
    )
    assert resp.status_code == 302
    query = _query(resp.headers["location"])
    assert resp.headers["location"].startswith(redirect_uri)
    assert query["error"] == "invalid_request"
    assert query["state"] == "s1"


async def test_login_form_needs_the_transaction_cookie(browser):
    await start_lab(browser)
    login_page = await browser.follow(await browser.get(browser.url("app-a", "/rp/oidc/login")))
    tx = login_form_tx(login_page.text)
    browser.jars["idp.localhost"].clear()  # e.g. a form posted from another site
    resp = await browser.post(
        browser.url("idp", "/login"), data={"tx": tx, "username": "alice", "password": "wonderland"}
    )
    assert resp.status_code == 400
    assert "Sign-in expired" in resp.text


async def test_wrong_password_shows_the_form_again(browser):
    await start_lab(browser)
    resp = await sign_in_app_a(browser, password="nope")
    assert resp.status_code == 200
    assert "Wrong username or password" in resp.text


# --- The whole flow -----------------------------------------------------------------------


async def test_guided_flow_end_to_end(browser, lab):
    lab_id = await start_lab(browser)

    callback = await sign_in_app_a(browser)
    assert callback.status_code == 200
    assert "Authorization code received" in callback.text
    assert "sso-lab:oidc" in callback.text  # tells the playground

    state = (await browser.get(browser.url("app-a", "/api/lab/oidc/state"))).json()
    assert state["login"]["code"] and state["session"] is None

    exchange = (await browser.post(browser.url("app-a", "/api/lab/oidc/exchange"))).json()
    assert exchange["ok"], exchange
    assert all(c["ok"] for c in exchange["checks"])
    assert {c["label"].split()[0] for c in exchange["checks"]} >= {
        "alg",
        "iss",
        "aud",
        "exp",
        "nonce",
    }

    state = (await browser.get(browser.url("app-a", "/api/lab/oidc/state"))).json()
    assert state["login"] is None
    assert state["session"]["sub"] == "alice"
    assert state["session"]["claims"]["email"] == "alice@example.com"

    info = (await browser.post(browser.url("app-a", "/api/lab/oidc/userinfo"))).json()
    assert info == {
        "status": 200,
        "body": {
            "sub": "alice",
            "name": "Alice Liddell",
            "email": "alice@example.com",
            "email_verified": True,
        },
    }

    old_access = state["session"]["access_token"]
    assert (await browser.post(browser.url("app-a", "/api/lab/oidc/refresh"))).json()["ok"]
    state = (await browser.get(browser.url("app-a", "/api/lab/oidc/state"))).json()
    assert state["session"]["access_token"] != old_access

    events = await lab.store.list_events(lab_id)
    seen = {e.step for e in events} | {e.response_step for e in events}
    assert set(FLOW_STEPS) <= seen, set(FLOW_STEPS) - seen
    assert {"oidc.userinfo", "oidc.refresh"} <= seen

    # Every check App A made is in the trace, and all passed.
    validate = next(e for e in events if e.channel == "local" and e.step == "oidc.validate")
    assert validate.checks and all(c.ok for c in validate.checks)
    assert json.loads(validate.data["id_token_payload"])["sub"] == "alice"

    # The password never reaches the trace; the recorded response shows the real headers.
    login_post = next(e for e in events if e.step == "oidc.authenticate")
    assert "wonderland" not in (login_post.request.body or "")
    assert "password=[redacted]" in login_post.request.body
    set_cookies = [h.value for h in login_post.response.headers if h.name.lower() == "set-cookie"]
    assert any(c.startswith("idp_session=") and "HttpOnly" in c for c in set_cookies)
    csp = next(
        h.value for h in login_post.response.headers if h.name.lower() == "content-security-policy"
    )
    assert "frame-ancestors 'none'" in csp


async def test_second_app_signs_in_without_a_password(browser, lab):
    """Single sign-on: App B's login goes straight through on the IdP's existing session."""
    lab_id = await start_lab(browser)
    await sign_in_app_a(browser)

    to_idp = await browser.get(browser.url("app-b", f"/rp/oidc/login?lab_session={lab_id}"))
    authorize = await browser.get(to_idp.headers["location"])
    assert authorize.status_code == 302, "the IdP should skip the login page"
    done = await browser.follow(authorize)
    assert done.status_code == 200
    assert "Signed in to App B as Alice Liddell" in done.text
    home = await browser.get(browser.url("app-b", "/"))
    assert "Welcome, Alice Liddell" in home.text

    events = await lab.store.list_events(lab_id)
    sso = [e for e in events if e.target == "idp" and e.note and "single sign-on" in e.note]
    assert len(sso) == 1


async def test_sign_out_everywhere_ends_single_sign_on(browser, lab):
    lab_id = await start_lab(browser)
    await sign_in_app_a(browser)

    out = await browser.follow(
        await browser.get(browser.url("app-a", "/rp/oidc/logout?everywhere=true"))
    )
    assert "Signed out everywhere" in out.text

    to_idp = await browser.get(browser.url("app-b", f"/rp/oidc/login?lab_session={lab_id}"))
    assert "Sign in to the lab IdP" in (await browser.follow(to_idp)).text


# --- Token endpoint rules -----------------------------------------------------------------


async def _code_for(browser, client_id: str = "app-a") -> tuple[str, str, str]:
    """Get a real authorization code the way a client would, returning (code, verifier, uri)."""
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    redirect_uri = browser.url(client_id, "/rp/oidc/callback")
    login_page = await browser.get(
        browser.url("idp", "/authorize"),
        params={
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email",
            "state": "st",
            "nonce": "n",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
    )
    if login_page.status_code == 200:
        resp = await browser.post(
            browser.url("idp", "/login"),
            data={
                "tx": login_form_tx(login_page.text),
                "username": "alice",
                "password": "wonderland",
            },
        )
    else:
        resp = login_page
    return _query(resp.headers["location"])["code"], verifier, redirect_uri


async def _redeem(browser, code, verifier, redirect_uri, auth=("app-a", "app-a-demo-secret")):
    return await browser.post(
        browser.url("idp", "/token"),
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
        auth=auth,
    )


async def test_codes_are_single_use(browser):
    code, verifier, uri = await _code_for(browser)
    first = await _redeem(browser, code, verifier, uri)
    assert first.status_code == 200
    assert first.headers["cache-control"] == "no-store"
    second = await _redeem(browser, code, verifier, uri)
    assert second.status_code == 400 and second.json()["error"] == "invalid_grant"


async def test_wrong_pkce_verifier_is_rejected(browser):
    code, _, uri = await _code_for(browser)
    resp = await _redeem(browser, code, "not-the-verifier", uri)
    assert resp.json() == {
        "error": "invalid_grant",
        "error_description": "PKCE verification failed: wrong code_verifier.",
    }


@pytest.mark.parametrize(
    ("auth", "uri_suffix", "status", "error"),
    [
        (("app-a", "wrong-secret"), "", 401, "invalid_client"),
        (("app-b", "app-b-demo-secret"), "", 400, "invalid_grant"),  # code was issued to app-a
        (("app-a", "app-a-demo-secret"), "/other", 400, "invalid_grant"),  # redirect_uri differs
    ],
)
async def test_token_request_must_match_the_code(browser, auth, uri_suffix, status, error):
    code, verifier, uri = await _code_for(browser)
    resp = await _redeem(browser, code, verifier, uri + uri_suffix, auth=auth)
    assert (resp.status_code, resp.json()["error"]) == (status, error)


async def test_userinfo_needs_a_valid_access_token(browser):
    resp = await browser.get(
        browser.url("idp", "/userinfo"), headers={"Authorization": "Bearer nope"}
    )
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == 'Bearer error="invalid_token"'


# --- ID token validation (what App A checks) ------------------------------------------------


def _app_a_client(lab) -> OidcClient:
    app = lab.app.apps[Actor.APP_A]
    return OidcClient(
        Request({"type": "http", "app": app, "headers": [], "method": "GET", "path": "/"})
    )


async def _token(lab, **overrides) -> str:
    key = await signing_key(lab.store)
    now = int(time.time())
    claims = {
        "iss": lab.settings.urls[Actor.IDP],
        "sub": "alice",
        "aud": "app-a",
        "iat": now,
        "exp": now + 300,
        "nonce": "n-1",
        **overrides,
    }
    return jwt.encode({"alg": "RS256", "kid": key.kid}, claims, key)


def _failed(checks) -> list[str]:
    return [c.label.split()[0] for c in checks if not c.ok]


async def test_a_genuine_id_token_passes_every_check(lab):
    checks, claims = await _app_a_client(lab).validate_id_token(await _token(lab), "n-1", None)
    assert _failed(checks) == []
    assert claims["sub"] == "alice"


@pytest.mark.parametrize(
    ("overrides", "nonce", "failed"),
    [
        ({"aud": "app-b"}, "n-1", ["aud"]),  # token confusion: issued to another app
        ({"iss": "https://evil.example"}, "n-1", ["iss"]),
        ({"exp": int(time.time()) - 3600}, "n-1", ["exp"]),
        ({}, "other-nonce", ["nonce"]),  # replayed from another login
    ],
)
async def test_id_token_claim_checks(lab, overrides, nonce, failed):
    checks, _ = await _app_a_client(lab).validate_id_token(
        await _token(lab, **overrides), nonce, None
    )
    assert _failed(checks) == failed


async def test_forged_tokens_fail_signature_checks(lab):
    client = _app_a_client(lab)
    header, payload, signature = (await _token(lab)).split(".")

    # Edited claims with the original signature.
    forged_payload = (
        base64.urlsafe_b64encode(json.dumps({"sub": "admin", "aud": "app-a"}).encode())
        .rstrip(b"=")
        .decode()
    )
    checks, _ = await client.validate_id_token(
        f"{header}.{forged_payload}.{signature}", "n-1", None
    )
    assert "the" in _failed(checks)  # "the signature verifies ..."

    # alg: none, no signature at all.
    none_header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    checks, _ = await client.validate_id_token(f"{none_header}.{payload}.", "n-1", None)
    assert _failed(checks)[:2] == ["alg", "the"]
