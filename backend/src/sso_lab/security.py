"""Canonical host, security headers and per-IP rate limiting.

All pure ASGI, so streaming responses are untouched.
"""

import time
from collections import defaultdict

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import PlainTextResponse, RedirectResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sso_lab.config import Actor, Settings


class CanonicalHostMiddleware:
    """Redirect to the actor's configured URL when reached under another hostname.

    Cloud Run answers on two hostnames per service. Cookies, redirect URIs and postMessage
    origins are all tied to one origin, so everything must happen on the configured one.
    """

    def __init__(self, app: ASGIApp, settings: Settings, actor: Actor) -> None:
        self.app = app
        self.base = settings.urls[actor]
        self.actor = actor
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] == "/healthz":
            await self.app(scope, receive, send)
            return
        host = Headers(scope=scope).get("host", "")
        if self.settings.actor_for_host(host) is self.actor:
            await self.app(scope, receive, send)
            return
        query = scope.get("query_string", b"").decode()
        target = self.base + scope["path"] + (f"?{query}" if query else "")
        await RedirectResponse(target, status_code=308)(scope, receive, send)


class SecurityHeadersMiddleware:
    """Baseline headers for every response. A route can override CSP by setting its own."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings
        lab_origins = " ".join(settings.origins.values())
        self.csp = "; ".join(
            [
                "default-src 'self'",
                "script-src 'self'",
                "style-src 'self' 'unsafe-inline'",
                "img-src 'self' data:",
                "font-src 'self'",
                "connect-src 'self'",
                "object-src 'none'",
                "base-uri 'none'",
                # Protocol forms (login, SAML POST binding) may only post to lab actors.
                f"form-action 'self' {lab_origins}",
                "frame-ancestors 'none'",
            ]
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("Content-Security-Policy", self.csp)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                # Never leak authorization codes or tokens in URLs to other sites via Referer.
                headers.setdefault("Referrer-Policy", "no-referrer")
                if not path.startswith("/assets/"):
                    # Protocol responses carry codes and tokens: never cache them.
                    headers.setdefault("Cache-Control", "no-store")
                if self.settings.https:
                    headers.setdefault("Strict-Transport-Security", "max-age=31536000")
                # Note: no Cross-Origin-Opener-Policy on protocol pages. The login popup
                # travels app -> IdP -> app and must keep window.opener to report back.
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RateLimitMiddleware:
    """Fixed-window per-IP limits. Per instance only; Cloud Run max-instances bounds the total."""

    WINDOW_SECONDS = 60

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings
        self._window = 0
        self._counts: dict[tuple[str, str], int] = defaultdict(int)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in ("/healthz",):
            await self.app(scope, receive, send)
            return

        window = int(time.time() // self.WINDOW_SECONDS)
        if window != self._window:
            self._window = window
            self._counts.clear()

        ip = self._client_ip(scope)
        limits = [("all", self.settings.rate_limit_per_minute)]
        if scope["method"] == "POST" and scope["path"] == "/api/lab/sessions":
            limits.append(("session", self.settings.session_create_limit_per_minute))

        for bucket, limit in limits:
            self._counts[(ip, bucket)] += 1
            if self._counts[(ip, bucket)] > limit:
                retry_after = str(self.WINDOW_SECONDS - int(time.time()) % self.WINDOW_SECONDS)
                response = PlainTextResponse(
                    "Too many requests. Slow down a little.",
                    status_code=429,
                    headers={"Retry-After": retry_after},
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)

    def _client_ip(self, scope: Scope) -> str:
        if self.settings.trust_proxy:
            forwarded = Headers(scope=scope).get("x-forwarded-for", "")
            # Google's front end appends the real client IP; earlier entries can be spoofed.
            last = forwarded.rsplit(",", 1)[-1].strip()
            if last:
                return last
        client = scope.get("client")
        return client[0] if client else "unknown"
