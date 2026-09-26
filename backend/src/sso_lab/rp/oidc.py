"""The relying parties' OpenID Connect client (App A and App B).

Like the IdP, written to be read: every value an app must generate and every check it must
make is explicit, and each one is recorded to the visitor's trace.

Two modes:

* ``guided`` (the playground): after the IdP redirects back with a code, the app stops and
  the playground triggers each following step (token exchange, UserInfo, refresh) by hand.
* ``auto``: a normal app. The callback exchanges the code straight away and signs the user in.
  App B always works this way, to show single sign-on.
"""

import base64
import hashlib
import hmac
import html
import json
import secrets
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response
from joserfc import jwt
from joserfc.jwk import KeySet

from sso_lab.config import Actor, Settings
from sso_lab.demo import CALLBACK_PATH, CLIENT_SECRETS, LOGGED_OUT_PATH
from sso_lab.lab.models import Check
from sso_lab.lab.recorder import Recorder, tag
from sso_lab.lab.session import session_from_cookie, session_from_public_id
from sso_lab.lab.store import Store
from sso_lab.pages import page, post_message_script

router = APIRouter(prefix="/rp/oidc", tags=["rp-oidc"])

LOGIN_COOKIE = "rp_login"
SESSION_COOKIE = "rp_session"
LOGIN_TTL = timedelta(minutes=10)
SESSION_TTL = timedelta(hours=8)
CLOCK_SKEW = 60  # seconds
SCOPE = "openid profile email"

_NAMES = {Actor.APP_A: "App A", Actor.APP_B: "App B"}


@dataclass
class ExchangeResult:
    ok: bool
    error: str | None = None
    session_id: str | None = None
    checks: list[Check] = field(default_factory=list)


class OidcClient:
    """The OIDC logic of one app. Created per request from the app's state."""

    def __init__(self, request: Request) -> None:
        self.request = request
        self.settings: Settings = request.app.state.settings
        self.store: Store = request.app.state.store
        self.recorder: Recorder = request.app.state.recorder
        self.actor: Actor = self.recorder.actor
        self.name = _NAMES[self.actor]
        self.client_id = self.actor.value
        self.client_secret = CLIENT_SECRETS[self.actor]
        self.base_url = self.settings.urls[self.actor]
        self.redirect_uri = self.base_url + CALLBACK_PATH
        self.issuer = self.settings.urls[Actor.IDP]
        cache = request.app.state
        if not hasattr(cache, "oidc_metadata"):
            cache.oidc_metadata = {}
        self._cache: dict[str, Any] = cache.oidc_metadata

    # --- IdP metadata (discovery document and signing keys), cached like a real app would ---

    async def discovery(self, lab_id: str | None, *, force: bool = False) -> dict[str, Any]:
        if not force and "discovery" in self._cache:
            return self._cache["discovery"]
        async with self.recorder.client(lab_session_id=lab_id, step="oidc.register") as client:
            resp = await client.get(f"{self.issuer}/.well-known/openid-configuration")
        resp.raise_for_status()
        doc = resp.json()
        # The discovery document must describe the IdP we meant to talk to.
        if doc.get("issuer") != self.issuer:
            raise ValueError(f"discovery issuer {doc.get('issuer')!r} != {self.issuer!r}")
        self._cache["discovery"] = doc
        return doc

    async def jwks(
        self, lab_id: str | None, *, force: bool = False, step: str = "oidc.validate"
    ) -> dict[str, Any]:
        """The IdP's public keys; fetched at setup, or during validation if not cached."""
        if not force and "jwks" in self._cache:
            return self._cache["jwks"]
        jwks_uri = (await self.discovery(lab_id))["jwks_uri"]
        async with self.recorder.client(lab_session_id=lab_id, step=step) as client:
            resp = await client.get(jwks_uri)
        resp.raise_for_status()
        self._cache["jwks"] = resp.json()
        return self._cache["jwks"]

    # --- Records ------------------------------------------------------------------------------

    async def current_login(self) -> tuple[str, dict[str, Any]] | None:
        login_id = self.request.cookies.get(LOGIN_COOKIE, "")
        login = await self.store.get_record("rpLogin", login_id) if login_id else None
        if login is None or login.get("app") != self.actor.value:
            return None
        return login_id, login

    async def current_session(self) -> tuple[str, dict[str, Any]] | None:
        sid = self.request.cookies.get(SESSION_COOKIE, "")
        session = await self.store.get_record("rpSession", sid) if sid else None
        if session is None or session.get("app") != self.actor.value:
            return None
        return sid, session

    # --- Step: start the login ----------------------------------------------------------------

    async def start_login(self, lab_id: str | None, mode: str, prompt: str) -> Response:
        # Three one-time values, remembered for this browser only (in a cookie-bound record).
        state = secrets.token_urlsafe(16)
        nonce = secrets.token_urlsafe(16)
        code_verifier = secrets.token_urlsafe(48)
        code_challenge = _s256(code_verifier)
        login_id = secrets.token_urlsafe(24)
        await self.store.put_record(
            "rpLogin",
            login_id,
            {
                "app": self.actor.value,
                "state": state,
                "nonce": nonce,
                "code_verifier": code_verifier,
                "code_challenge": code_challenge,
                "mode": mode,
                "lab_session": lab_id or "",
            },
            LOGIN_TTL,
        )
        if lab_id:
            tag(self.request, lab_id, "oidc.login", response_step="oidc.authorize-redirect")
            await self.recorder.local(
                lab_id,
                "oidc.prepare",
                f"{self.name} generated state, nonce and a PKCE verifier, and stored them for "
                "this browser. Only the SHA-256 of the verifier (the challenge) leaves the app.",
                data={
                    "state": state,
                    "nonce": nonce,
                    "code_verifier": code_verifier,
                    "code_challenge": code_challenge,
                },
            )

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": SCOPE,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if prompt:
            params["prompt"] = prompt
        if lab_id:
            params["lab_session"] = lab_id  # lab only: lets the IdP add to this visitor's trace
        authorize = (await self.discovery(lab_id))["authorization_endpoint"]
        response = RedirectResponse(f"{authorize}?{urlencode(params)}", status_code=302)
        self._set_cookie(response, LOGIN_COOKIE, login_id, LOGIN_TTL)
        return response

    # --- Step: the callback ---------------------------------------------------------------

    async def callback(self, code: str, state: str, iss: str, error: str) -> Response:
        current = await self.current_login()
        if current is None:
            return self._page(
                "No sign-in in progress", "Start again from the playground.", ok=False
            )
        login_id, login = current
        lab_id = login["lab_session"] or None
        if lab_id:
            tag(self.request, lab_id, "oidc.callback")

        if error:
            return self._page("The IdP returned an error", error, ok=False, stage="error")

        checks = [
            Check(
                label="state matches the value stored for this browser",
                ok=hmac.compare_digest(state, login["state"]),
                detail=f"received {state!r}, expected {login['state']!r}",
            ),
            Check(
                label="iss is the IdP this login was started with (RFC 9207)",
                ok=iss == self.issuer,
                detail=f"iss = {iss!r}",
            ),
            Check(label="an authorization code is present", ok=bool(code)),
        ]
        if lab_id:
            await self.recorder.local(
                lab_id, "oidc.callback", f"{self.name} checked the callback.", checks=checks
            )
        if not all(c.ok for c in checks):
            failed = next(c.label for c in checks if not c.ok)
            return self._page(
                "Callback rejected", f"Failed check: {failed}.", ok=False, stage="error"
            )

        await self.store.put_record("rpLogin", login_id, {**login, "code": code}, LOGIN_TTL)
        if login["mode"] == "guided":
            return self._page(
                "Authorization code received",
                f"{self.name} has the code but has not used it yet. Go back to the playground "
                "for the next step.",
                ok=True,
                stage="code",
            )

        result = await self.exchange()
        if not result.ok or result.session_id is None:
            return self._page(
                "Sign-in failed", result.error or "unknown error", ok=False, stage="error"
            )
        if lab_id:
            tag(self.request, lab_id, "oidc.callback", response_step="oidc.session")
        response = RedirectResponse(f"{self.base_url}/rp/oidc/done", status_code=302)
        self._set_cookie(response, SESSION_COOKIE, result.session_id, SESSION_TTL)
        response.delete_cookie(LOGIN_COOKIE, path="/")
        return response

    # --- Step: redeem the code, validate the ID token, start the app's own session ---------

    async def exchange(self) -> ExchangeResult:
        current = await self.current_login()
        if current is None or not current[1].get("code"):
            return ExchangeResult(ok=False, error="No authorization code to exchange.")
        login_id, login = current
        await self.store.delete_record("rpLogin", login_id)  # a login is used once
        lab_id = login["lab_session"] or None

        token_endpoint = (await self.discovery(lab_id))["token_endpoint"]
        async with self.recorder.client(
            lab_session_id=lab_id, step="oidc.token", response_step="oidc.tokens"
        ) as client:
            resp = await client.post(
                token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": login["code"],
                    "redirect_uri": self.redirect_uri,
                    "code_verifier": login["code_verifier"],
                },
                auth=(self.client_id, self.client_secret),  # client_secret_basic
            )
        if resp.status_code != 200:
            return ExchangeResult(ok=False, error=f"Token request failed: {resp.text}")
        tokens = resp.json()

        checks, claims = await self.validate_id_token(
            tokens.get("id_token", ""), login["nonce"], lab_id
        )
        if not all(c.ok for c in checks) or claims is None:
            return ExchangeResult(ok=False, error="The ID token failed validation.", checks=checks)

        sid = secrets.token_urlsafe(32)
        await self.store.put_record(
            "rpSession",
            sid,
            {
                "app": self.actor.value,
                "sub": claims["sub"],
                "name": claims.get("name", ""),
                "email": claims.get("email", ""),
                "claims": claims,
                "id_token": tokens["id_token"],
                "access_token": tokens.get("access_token", ""),
                "refresh_token": tokens.get("refresh_token", ""),
                "lab_session": lab_id or "",
                "signed_in_at": int(time.time()),
            },
            SESSION_TTL,
        )
        if lab_id and login["mode"] == "guided":
            await self.recorder.local(
                lab_id,
                "oidc.session",
                f"{self.name} created its own session for {claims['sub']}. From now on it relies "
                "on that session, not on the IdP.",
            )
        return ExchangeResult(ok=True, session_id=sid, checks=checks)

    async def validate_id_token(
        self, id_token: str, nonce: str | None, lab_id: str | None
    ) -> tuple[list[Check], dict[str, Any] | None]:
        """Check an ID token the way OpenID Connect Core section 3.1.3.7 requires."""
        try:
            header_b64, payload_b64, _ = id_token.split(".")
            header = json.loads(_b64url_decode(header_b64))
            claims = json.loads(_b64url_decode(payload_b64))
        except ValueError:
            checks = [Check(label="the ID token is a well-formed JWT", ok=False)]
            if lab_id:
                await self.recorder.local(
                    lab_id, "oidc.validate", "ID token rejected.", checks=checks
                )
            return checks, None

        now = int(time.time())
        alg = header.get("alg")
        jwks = await self.jwks(lab_id)
        key = _find_key(jwks, header.get("kid"))
        if key is None:  # keys may have rotated since we cached them: fetch once more
            jwks = await self.jwks(lab_id, force=True)
            key = _find_key(jwks, header.get("kid"))

        signature_ok = False
        if alg == "RS256" and key is not None:
            try:
                jwt.decode(id_token, KeySet.import_key_set({"keys": [key]}), algorithms=["RS256"])
                signature_ok = True
            except Exception:  # noqa: S110 - any failure means "not verified"
                pass

        aud = claims.get("aud")
        audiences = aud if isinstance(aud, list) else [aud]
        checks = [
            Check(
                label="alg is RS256, the algorithm this IdP signs with",
                ok=alg == "RS256",
                detail=f"alg = {alg!r}",
            ),
            Check(
                label="the signing key (kid) is in the IdP's published JWKS",
                ok=key is not None,
                detail=f"kid = {header.get('kid')!r}",
            ),
            Check(label="the signature verifies with that public key", ok=signature_ok),
            Check(
                label="iss is the expected IdP",
                ok=claims.get("iss") == self.issuer,
                detail=f"iss = {claims.get('iss')!r}",
            ),
            Check(
                label=f"aud contains this app's client_id ({self.client_id})",
                ok=self.client_id in audiences,
                detail=f"aud = {aud!r}",
            ),
            Check(
                label="exp is in the future",
                ok=isinstance(claims.get("exp"), int) and claims["exp"] + CLOCK_SKEW > now,
                detail=f"expires in {claims.get('exp', 0) - now} s"
                if isinstance(claims.get("exp"), int)
                else None,
            ),
            Check(
                label="iat is not in the future",
                ok=isinstance(claims.get("iat"), int) and claims["iat"] <= now + CLOCK_SKEW,
            ),
        ]
        if nonce is not None:
            checks.append(
                Check(
                    label="nonce matches the value stored for this login",
                    ok=hmac.compare_digest(str(claims.get("nonce", "")), nonce),
                    detail=f"nonce = {claims.get('nonce')!r}",
                )
            )
        if lab_id:
            ok = all(c.ok for c in checks)
            await self.recorder.local(
                lab_id,
                "oidc.validate",
                f"{self.name} {'accepted' if ok else 'rejected'} the ID token.",
                checks=checks,
                data={
                    "id_token_header": json.dumps(header, indent=2),
                    "id_token_payload": json.dumps(claims, indent=2),
                },
            )
        return checks, claims

    # --- After sign-in: call an API, refresh tokens ------------------------------------------

    async def userinfo(self, session: dict[str, Any]) -> tuple[int, Any]:
        lab_id = session.get("lab_session") or None
        endpoint = (await self.discovery(lab_id))["userinfo_endpoint"]
        async with self.recorder.client(lab_session_id=lab_id, step="oidc.userinfo") as client:
            resp = await client.get(
                endpoint, headers={"Authorization": f"Bearer {session['access_token']}"}
            )
        return resp.status_code, resp.json()

    async def refresh(self, sid: str, session: dict[str, Any]) -> tuple[bool, str | None]:
        lab_id = session.get("lab_session") or None
        endpoint = (await self.discovery(lab_id))["token_endpoint"]
        async with self.recorder.client(lab_session_id=lab_id, step="oidc.refresh") as client:
            resp = await client.post(
                endpoint,
                data={"grant_type": "refresh_token", "refresh_token": session["refresh_token"]},
                auth=(self.client_id, self.client_secret),
            )
        if resp.status_code != 200:
            return False, resp.json().get("error_description", resp.text)
        tokens = resp.json()
        updated = {
            **session,
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token", session["refresh_token"]),
            "id_token": tokens.get("id_token", session["id_token"]),
        }
        await self.store.put_record("rpSession", sid, updated, SESSION_TTL)
        return True, None

    # --- Pages --------------------------------------------------------------------------------

    def _set_cookie(self, response: Response, name: str, value: str, ttl: timedelta) -> None:
        response.set_cookie(
            name, value, max_age=int(ttl.total_seconds()), httponly=True,
            secure=self.settings.https, samesite="lax", path="/",
        )  # fmt: skip

    def _page(self, title: str, message: str, *, ok: bool, stage: str | None = None) -> Response:
        script = None
        if stage:
            script = post_message_script(
                {
                    "type": "sso-lab:oidc",
                    "app": self.actor.value,
                    "stage": stage,
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


def _s256(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _find_key(jwks: dict[str, Any], kid: str | None) -> dict[str, Any] | None:
    return next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)


# --- Routes -------------------------------------------------------------------------------


@router.get("/login")
async def login(
    request: Request, mode: str = "auto", prompt: str = "", lab_session: str = ""
) -> Response:
    """Start signing in. The playground passes its lab session so every hop is traced."""
    lab = await session_from_public_id(request, lab_session) or await session_from_cookie(request)
    return await OidcClient(request).start_login(
        lab.id if lab else None,
        "guided" if mode == "guided" else "auto",
        "login" if prompt == "login" else "",
    )


@router.get("/callback")
async def callback(
    request: Request, code: str = "", state: str = "", iss: str = "", error: str = "",
    error_description: str = "",
) -> Response:  # fmt: skip
    message = f"{error}: {error_description}" if error else ""
    return await OidcClient(request).callback(code, state, iss, message)


@router.get("/done")
async def done(request: Request) -> Response:
    """Where an automatic sign-in lands: shows who is signed in and tells the playground."""
    oidc = OidcClient(request)
    current = await oidc.current_session()
    if current is None:
        return oidc._page("Not signed in", "No session found.", ok=False, stage="error")
    _, session = current
    return oidc._page(
        f"Signed in to {oidc.name} as {session['name'] or session['sub']}",
        f"{oidc.name} trusted the IdP's ID token and started its own session.",
        ok=True,
        stage="signed-in",
    )


@router.get("/logout")
async def logout(request: Request, everywhere: bool = False) -> Response:
    """Sign out of this app, and optionally of the IdP too (RP-initiated logout)."""
    oidc = OidcClient(request)
    current = await oidc.current_session()
    lab_id = current[1].get("lab_session") if current else ""
    if current:
        await oidc.store.delete_record("rpSession", current[0])
    if everywhere:
        params = {
            "client_id": oidc.client_id,
            "post_logout_redirect_uri": oidc.base_url + LOGGED_OUT_PATH,
        }
        if lab_id:
            params["lab_session"] = lab_id
        response: Response = RedirectResponse(
            f"{oidc.issuer}/logout?{urlencode(params)}", status_code=302
        )
    else:
        response = oidc._page(
            f"Signed out of {oidc.name}",
            "The IdP session is untouched.",
            ok=True,
            stage="signed-out",
        )
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/logged-out")
async def logged_out(request: Request) -> Response:
    return OidcClient(request)._page(
        "Signed out everywhere",
        "You are signed out of this app and of the IdP. The next sign-in will ask for a password.",
        ok=True,
        stage="signed-out",
    )
