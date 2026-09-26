"""The teaching IdP's OpenID Connect endpoints.

Written to be read: each check an OpenID Provider must make is spelled out in order, with the
reason next to it. Only what the lab needs is implemented: the authorization code flow with
PKCE (required for every client, as in OAuth 2.1), refresh tokens, UserInfo and logout.
"""

import base64
import hashlib
import hmac
import html
import secrets
import time
from datetime import timedelta
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Header, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from joserfc import jwt

from sso_lab.config import Actor, Settings
from sso_lab.demo import DEMO_USERS, Client, registered_clients
from sso_lab.idp.keys import public_jwks, signing_key
from sso_lab.lab.recorder import tag
from sso_lab.lab.session import session_from_public_id
from sso_lab.lab.store import Store
from sso_lab.pages import page

router = APIRouter(tags=["oidc"])

TX_COOKIE = "idp_tx"
SESSION_COOKIE = "idp_session"

CODE_TTL = timedelta(seconds=60)
TX_TTL = timedelta(minutes=10)
SESSION_TTL = timedelta(hours=8)
ACCESS_TOKEN_TTL = timedelta(minutes=10)
REFRESH_TOKEN_TTL = timedelta(hours=8)
ID_TOKEN_TTL = timedelta(minutes=5)

SCOPES = ("openid", "profile", "email")


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _store(request: Request) -> Store:
    return request.app.state.store


def _issuer(request: Request) -> str:
    return _settings(request).urls[Actor.IDP]


# --- Discovery ---------------------------------------------------------------------------


@router.get("/.well-known/openid-configuration")
async def discovery(request: Request) -> dict[str, Any]:
    issuer = _issuer(request)
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "userinfo_endpoint": f"{issuer}/userinfo",
        "jwks_uri": f"{issuer}/jwks",
        "end_session_endpoint": f"{issuer}/logout",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": list(SCOPES),
        "claims_supported": [
            "iss",
            "sub",
            "aud",
            "exp",
            "iat",
            "auth_time",
            "nonce",
            "name",
            "email",
            "email_verified",
        ],
        "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
        "code_challenge_methods_supported": ["S256"],
        "authorization_response_iss_parameter_supported": True,
    }


@router.get("/jwks")
async def jwks(request: Request) -> dict[str, Any]:
    return public_jwks(await signing_key(_store(request)))


# --- Authorization endpoint (front channel) ----------------------------------------------


@router.get("/authorize")
async def authorize(
    request: Request,
    client_id: str = "",
    redirect_uri: str = "",
    response_type: str = "",
    scope: str = "",
    state: str = "",
    nonce: str = "",
    code_challenge: str = "",
    code_challenge_method: str = "",
    prompt: str = "",
    lab_session: str = "",
) -> Response:
    settings = _settings(request)
    lab = await session_from_public_id(request, lab_session)
    if lab is not None:
        tag(request, lab.id, "oidc.authorize")

    # 1. The client must be registered, and the redirect URI must *exactly* match one of its
    #    registered URIs. Until both hold, never redirect anywhere: an error sent to an
    #    unverified redirect_uri is itself an open redirect.
    client = registered_clients(settings).get(client_id)
    if client is None:
        return _error_page("Unknown client", f"No app is registered as {client_id!r}.")
    if redirect_uri not in client.redirect_uris:
        return _error_page(
            "Unregistered redirect URI",
            f"{redirect_uri!r} is not registered for {client.name}. The IdP only ever sends "
            "authorization codes to exactly-matching registered URIs.",
        )

    # 2. From here on, errors go back to the (now trusted) redirect URI.
    def fail(error: str, description: str) -> Response:
        return _redirect_with(redirect_uri, error=error, error_description=description, state=state)

    requested = scope.split()
    if response_type != "code":
        return fail("unsupported_response_type", "Only the authorization code flow is supported.")
    if "openid" not in requested:
        return fail("invalid_scope", "scope must include openid.")
    if not code_challenge or code_challenge_method != "S256":
        return fail("invalid_request", "PKCE is required: send code_challenge with method S256.")

    request_data = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(s for s in requested if s in SCOPES),
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "lab_session": lab.id if lab else "",
    }

    # 3. Single sign-on: if this browser already has a session with the IdP, skip the login page.
    session = await _current_session(request)
    if session is not None and prompt != "login":
        if lab is not None:
            tag(
                request,
                lab.id,
                "oidc.authorize",
                response_step="oidc.issue-code",
                note=f"The IdP already has a session for {session['sub']}: no login page. "
                "This is single sign-on.",
            )
        return await _issue_code(request, request_data, session["sub"], session["auth_time"])

    # 4. Otherwise remember this request in a short-lived transaction and show the login page.
    #    The transaction id is also set as a cookie, so the login form cannot be submitted
    #    from another site (login CSRF against the IdP itself).
    tx = secrets.token_urlsafe(24)
    await _store(request).put_record("idpTx", tx, request_data, TX_TTL)
    response = _login_page(client, tx, requested)
    response.set_cookie(
        TX_COOKIE, tx, max_age=int(TX_TTL.total_seconds()), httponly=True,
        secure=settings.https, samesite="lax", path="/login",
    )  # fmt: skip
    return response


@router.post("/login")
async def login(
    request: Request,
    tx: Annotated[str, Form()] = "",
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
) -> Response:
    settings = _settings(request)
    store = _store(request)
    request_data = await store.get_record("idpTx", tx) if tx else None
    if request_data is None or not hmac.compare_digest(request.cookies.get(TX_COOKIE, ""), tx):
        return _error_page("Sign-in expired", "Start again from the app.")
    lab_id = request_data.get("lab_session") or ""
    client = registered_clients(settings)[request_data["client_id"]]

    user = DEMO_USERS.get(username.strip().lower())
    # Demo passwords are compared in constant time; a real IdP stores only slow salted hashes.
    if user is None or not hmac.compare_digest(user.password, password):
        if lab_id:
            tag(request, lab_id, "oidc.authenticate", note="Wrong username or password.")
        return _login_page(
            client, tx, request_data["scope"].split(), error="Wrong username or password."
        )

    await store.delete_record("idpTx", tx)
    sid = secrets.token_urlsafe(32)
    auth_time = int(time.time())
    await store.put_record(
        "idpSession", sid, {"sub": user.sub, "auth_time": auth_time}, SESSION_TTL
    )
    if lab_id:
        tag(request, lab_id, "oidc.authenticate", response_step="oidc.issue-code")
    response = await _issue_code(request, request_data, user.sub, auth_time)
    response.set_cookie(
        SESSION_COOKIE, sid, max_age=int(SESSION_TTL.total_seconds()), httponly=True,
        secure=settings.https, samesite="lax", path="/",
    )  # fmt: skip
    response.delete_cookie(TX_COOKIE, path="/login")
    return response


async def _issue_code(
    request: Request, request_data: dict[str, Any], sub: str, auth_time: int
) -> Response:
    """Redirect back to the app with a single-use code bound to client, redirect URI and PKCE."""
    code = secrets.token_urlsafe(32)
    await _store(request).put_record(
        "authCode", code, {**request_data, "sub": sub, "auth_time": auth_time}, CODE_TTL
    )
    return _redirect_with(
        request_data["redirect_uri"],
        code=code,
        state=request_data["state"],
        # RFC 9207: tells the app which IdP sent this response (defends against mix-up attacks).
        iss=_issuer(request),
    )


# --- Token endpoint (back channel) --------------------------------------------------------


@router.post("/token")
async def token(
    request: Request,
    grant_type: Annotated[str, Form()] = "",
    code: Annotated[str, Form()] = "",
    redirect_uri: Annotated[str, Form()] = "",
    code_verifier: Annotated[str, Form()] = "",
    refresh_token: Annotated[str, Form()] = "",
    client_id: Annotated[str, Form()] = "",
    client_secret: Annotated[str, Form()] = "",
    authorization: Annotated[str, Header()] = "",
) -> Response:
    client = _authenticate_client(request, authorization, client_id, client_secret)
    if client is None:
        return _token_error("invalid_client", "Client authentication failed.", status=401)
    store = _store(request)

    if grant_type == "authorization_code":
        # The code is consumed atomically: a second attempt to redeem it finds nothing.
        grant = await store.take_record("authCode", code) if code else None
        if grant is None:
            return _token_error("invalid_grant", "Unknown, expired or already used code.")
        if grant["client_id"] != client.client_id:
            return _token_error("invalid_grant", "This code was issued to a different client.")
        if grant["redirect_uri"] != redirect_uri:
            return _token_error(
                "invalid_grant", "redirect_uri does not match the authorization request."
            )
        if not _pkce_matches(code_verifier, grant["code_challenge"]):
            return _token_error("invalid_grant", "PKCE verification failed: wrong code_verifier.")
        return await _token_response(request, client, grant, nonce=grant.get("nonce") or None)

    if grant_type == "refresh_token":
        # Refresh tokens rotate: each one can be used once, and returns a new one.
        grant = await store.take_record("refreshToken", refresh_token) if refresh_token else None
        if grant is None or grant["client_id"] != client.client_id:
            return _token_error("invalid_grant", "Unknown, expired or already used refresh token.")
        return await _token_response(request, client, grant, nonce=None)

    return _token_error("unsupported_grant_type", f"grant_type {grant_type!r} is not supported.")


def _authenticate_client(
    request: Request, authorization: str, client_id: str, client_secret: str
) -> Client | None:
    if authorization.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(authorization[6:]).decode()
        except ValueError:
            return None
        client_id, _, client_secret = decoded.partition(":")
    client = registered_clients(_settings(request)).get(client_id)
    if client is None or not hmac.compare_digest(client.client_secret, client_secret):
        return None
    return client


def _pkce_matches(verifier: str, challenge: str) -> bool:
    if not verifier:
        return False
    digest = hashlib.sha256(verifier.encode("ascii", errors="replace")).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return hmac.compare_digest(computed, challenge)


async def _token_response(
    request: Request, client: Client, grant: dict[str, Any], nonce: str | None
) -> Response:
    store = _store(request)
    user = DEMO_USERS[grant["sub"]]
    scope = grant["scope"]
    now = int(time.time())
    carried = {
        "sub": user.sub,
        "scope": scope,
        "client_id": client.client_id,
        "auth_time": grant["auth_time"],
    }

    access_token = secrets.token_urlsafe(32)
    await store.put_record("accessToken", access_token, carried, ACCESS_TOKEN_TTL)
    new_refresh = secrets.token_urlsafe(32)
    await store.put_record("refreshToken", new_refresh, carried, REFRESH_TOKEN_TTL)

    claims: dict[str, Any] = {
        "iss": _issuer(request),
        "sub": user.sub,
        "aud": client.client_id,
        "iat": now,
        "exp": now + int(ID_TOKEN_TTL.total_seconds()),
        "auth_time": grant["auth_time"],
        **_user_claims(user.sub, scope),
    }
    if nonce:
        claims["nonce"] = nonce
    key = await signing_key(store)
    id_token = jwt.encode({"alg": "RS256", "kid": key.kid, "typ": "JWT"}, claims, key)

    return JSONResponse(
        {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": int(ACCESS_TOKEN_TTL.total_seconds()),
            "refresh_token": new_refresh,
            "id_token": id_token,
            "scope": scope,
        },
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def _token_error(error: str, description: str, status: int = 400) -> Response:
    headers = {"Cache-Control": "no-store"}
    if status == 401:
        headers["WWW-Authenticate"] = 'Basic realm="token"'
    return JSONResponse({"error": error, "error_description": description}, status, headers)


def _user_claims(sub: str, scope: str) -> dict[str, Any]:
    user = DEMO_USERS[sub]
    scopes = scope.split()
    claims: dict[str, Any] = {}
    if "profile" in scopes:
        claims["name"] = user.name
    if "email" in scopes:
        claims["email"] = user.email
        claims["email_verified"] = True
    return claims


# --- UserInfo (a protected API) -----------------------------------------------------------


@router.get("/userinfo")
async def userinfo(request: Request, authorization: Annotated[str, Header()] = "") -> Response:
    token_value = authorization[7:] if authorization.lower().startswith("bearer ") else ""
    grant = await _store(request).get_record("accessToken", token_value) if token_value else None
    if grant is None:
        return JSONResponse(
            {"error": "invalid_token"},
            401,
            {"WWW-Authenticate": 'Bearer error="invalid_token"', "Cache-Control": "no-store"},
        )
    return JSONResponse(
        {"sub": grant["sub"], **_user_claims(grant["sub"], grant["scope"])},
        headers={"Cache-Control": "no-store"},
    )


# --- Logout (RP-initiated) ----------------------------------------------------------------


@router.get("/logout")
async def logout(
    request: Request,
    client_id: str = "",
    post_logout_redirect_uri: str = "",
    state: str = "",
    lab_session: str = "",
) -> Response:
    lab = await session_from_public_id(request, lab_session)
    if lab is not None:
        tag(request, lab.id, "oidc.logout")
    sid = request.cookies.get(SESSION_COOKIE)
    if sid:
        await _store(request).delete_record("idpSession", sid)

    client = registered_clients(_settings(request)).get(client_id)
    if client is not None and post_logout_redirect_uri in client.post_logout_redirect_uris:
        response: Response = _redirect_with(post_logout_redirect_uri, state=state)
    else:
        response = page(
            badge="Identity Provider",
            title="Signed out",
            body_html="<p>You are signed out of the IdP. Apps you signed in to still have "
            "their own sessions until they sign you out too.</p>",
        )
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


# --- Helpers ------------------------------------------------------------------------------


async def _current_session(request: Request) -> dict[str, Any] | None:
    sid = request.cookies.get(SESSION_COOKIE)
    return await _store(request).get_record("idpSession", sid) if sid else None


def _redirect_with(url: str, **params: str) -> RedirectResponse:
    query = urlencode({k: v for k, v in params.items() if v})
    separator = "&" if "?" in url else "?"
    return RedirectResponse(f"{url}{separator}{query}", status_code=302)


def _error_page(title: str, message: str) -> Response:
    return page(
        badge="Identity Provider",
        title=title,
        body_html=f"<p>{html.escape(message)}</p>",
        status_code=400,
    )


_SCOPE_TEXT = {
    "openid": "Confirm who you are",
    "profile": "See your name",
    "email": "See your email address",
}


def _login_page(client: Client, tx: str, scopes: list[str], error: str | None = None) -> Response:
    consent = "".join(f"<li>{html.escape(_SCOPE_TEXT[s])}</li>" for s in scopes if s in _SCOPE_TEXT)
    error_html = f'<p class="error" role="alert">{html.escape(error)}</p>' if error else ""
    body = f"""
<p>Sign in to continue to <strong>{html.escape(client.name)}</strong>. It will be able to:</p>
<ul class="scopes">{consent}</ul>
{error_html}
<form method="post" action="/login">
  <input type="hidden" name="tx" value="{html.escape(tx)}">
  <label>Username
    <input name="username" autocomplete="off" autocapitalize="off" required autofocus></label>
  <label>Password <input name="password" type="password" autocomplete="off" required></label>
  <button type="submit">Sign in</button>
</form>
<div class="hint">
  <strong>Demo accounts</strong> (never use a real password here)
  <div><code>alice</code> / <code>wonderland</code></div>
  <div><code>bob</code> / <code>builder</code></div>
</div>"""
    return page(badge="Identity Provider", title="Sign in to the lab IdP", body_html=body)
