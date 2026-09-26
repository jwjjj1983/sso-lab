"""The flight recorder: turns protocol activity into ``TraceEvent``s.

Every exchange is recorded exactly once, by the party that can see all of it:

* Front channel (browser -> actor): the receiving actor's route *tags* the request with the lab
  session and protocol step (``tag``); ``RecordingMiddleware`` then records the request and
  the final response, exactly as sent (including the headers other middleware adds).
* Back channel (actor -> actor): the calling actor records it with a recording httpx client
  (``Recorder.client``). The receiving actor does not record it again.
* Local work (no message): ``Recorder.local``, e.g. "App A validated the ID token", with the
  individual checks and values to show.

Recording is best-effort: a failure to store a trace never breaks the protocol flow.
"""

import logging
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sso_lab.config import Actor, Settings
from sso_lab.lab.models import (
    Channel,
    Check,
    Header,
    HttpRequestRecord,
    HttpResponseRecord,
    TraceEvent,
)
from sso_lab.lab.store import Store

log = logging.getLogger(__name__)

# Infrastructure headers added by proxies/browsers that carry no protocol meaning (and some,
# like X-Forwarded-For, carry the visitor's IP address, which we do not want to store).
_DROP_HEADER_PREFIXES = (
    "x-cloud-",
    "x-appengine-",
    "x-google-",
    "x-forwarded-",
    "forwarded",
    "traceparent",
    "via",
    "sec-ch-",
    "x-client-data",
    "priority",
)

# Form fields whose values never enter a trace. Demo client secrets and tokens are shown on
# purpose; a password is not, because people sometimes type real ones despite the warnings.
_REDACTED_FIELDS = re.compile(r"(^|&)(password)=[^&]*")

_STATE_KEY = "sso_lab_trace"


@dataclass
class TraceTag:
    lab_session_id: str
    step: str | None
    response_step: str | None = None
    note: str | None = None


def tag(
    request: Request,
    lab_session_id: str,
    step: str | None,
    *,
    response_step: str | None = None,
    note: str | None = None,
) -> None:
    """Mark this front-channel request for recording (by ``RecordingMiddleware``)."""
    setattr(request.state, _STATE_KEY, TraceTag(lab_session_id, step, response_step, note))


class Recorder:
    def __init__(self, settings: Settings, store: Store, actor: Actor) -> None:
        self.settings = settings
        self.store = store
        self.actor = actor

    async def record(self, event: TraceEvent) -> None:
        try:
            if not await self.store.append(event):
                log.info("trace event dropped for session %s", event.lab_session_id)
        except Exception:
            log.exception("failed to record trace event")

    async def local(
        self,
        lab_session_id: str,
        step: str,
        note: str,
        *,
        checks: list[Check] | None = None,
        data: dict[str, str] | None = None,
    ) -> None:
        """Record work done inside this actor, e.g. generating PKCE values or validating a token."""
        await self.record(
            TraceEvent(
                lab_session_id=lab_session_id,
                channel=Channel.LOCAL,
                source=self.actor,
                target=self.actor,
                step=step,
                note=note,
                checks=checks or [],
                data=data or {},
            )
        )

    def client(
        self,
        *,
        lab_session_id: str | None,
        step: str | None = None,
        response_step: str | None = None,
    ) -> httpx.AsyncClient:
        """An httpx client whose every request is recorded as a back-channel event.

        With no lab session (an app used outside the playground), nothing is recorded.
        """
        transport = _RecordingTransport(
            self, lab_session_id=lab_session_id, step=step, response_step=response_step
        )
        return httpx.AsyncClient(transport=transport, timeout=10.0, follow_redirects=False)

    def actor_for_url(self, url: str) -> Actor:
        host = urlsplit(url).netloc
        return self.settings.actor_for_host(host) or Actor.EXTERNAL

    def public_url(self, path: str, query: str) -> str:
        # Behind Cloud Run the app sees http://; show the URL the browser actually used.
        base = self.settings.urls.get(self.actor, "")
        return f"{base}{path}" + (f"?{query}" if query else "")

    def headers(self, items: Iterable[tuple[str, str]]) -> list[Header]:
        return [
            Header(name=name, value=value)
            for name, value in items
            if not name.lower().startswith(_DROP_HEADER_PREFIXES)
        ]

    def body(self, raw: bytes, content_type: str | None = None) -> str | None:
        if not raw:
            return None
        limit = self.settings.max_body_bytes
        text = raw[:limit].decode("utf-8", errors="replace")
        if content_type and content_type.startswith("application/x-www-form-urlencoded"):
            text = _REDACTED_FIELDS.sub(r"\1\2=[redacted]", text)
        return text + "\n…[truncated]" if len(raw) > limit else text


class RecordingMiddleware:
    """Records tagged front-channel exchanges, with the response exactly as it was sent.

    A tagged response is held back until it has been recorded, then released. So by the time
    the browser acts on it (say, follows the redirect to the next hop), this hop is already in
    the trace, and the trace can never show hops out of order. Untagged responses, including
    the trace's own event stream, pass straight through.
    """

    def __init__(self, app: ASGIApp, recorder: Recorder) -> None:
        self.app = app
        self.recorder = recorder

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started_at = datetime.now(UTC)
        request_body: list[bytes] = []
        held: list[Message] = []

        async def receive_and_keep() -> Message:
            message = await receive()
            if message["type"] == "http.request":
                request_body.append(message.get("body", b""))
            return message

        async def send_after_recording(message: Message) -> None:
            trace: TraceTag | None = scope.get("state", {}).get(_STATE_KEY)
            if trace is None:
                await send(message)
                return
            held.append(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                await self._record(scope, trace, started_at, b"".join(request_body), held)
                for m in held:
                    await send(m)
                held.clear()

        await self.app(scope, receive_and_keep, send_after_recording)

    async def _record(
        self,
        scope: Scope,
        trace: TraceTag,
        started_at: datetime,
        request_body: bytes,
        messages: list[Message],
    ) -> None:
        start = messages[0]
        response_body = b"".join(m.get("body", b"") for m in messages[1:])
        recorder = self.recorder
        request_headers = Headers(scope=scope)
        response_headers = Headers(raw=start.get("headers", []))
        await recorder.record(
            TraceEvent(
                lab_session_id=trace.lab_session_id,
                ts=started_at,
                channel=Channel.FRONT,
                source=Actor.BROWSER,
                target=recorder.actor,
                step=trace.step,
                response_step=trace.response_step,
                note=trace.note,
                request=HttpRequestRecord(
                    method=scope["method"],
                    url=recorder.public_url(scope["path"], scope.get("query_string", b"").decode()),
                    headers=recorder.headers(request_headers.items()),
                    body=recorder.body(request_body, request_headers.get("content-type")),
                ),
                response=HttpResponseRecord(
                    status=start["status"],
                    headers=recorder.headers(response_headers.items()),
                    body=recorder.body(response_body),
                ),
            )
        )


class _RecordingTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        recorder: Recorder,
        *,
        lab_session_id: str | None,
        step: str | None,
        response_step: str | None,
    ) -> None:
        self._recorder = recorder
        self._lab_session_id = lab_session_id
        self._step = step
        self._response_step = response_step
        self._inner = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        started_at = datetime.now(UTC)
        started = time.perf_counter()
        response = await self._inner.handle_async_request(self._route(request, body))
        await response.aread()
        elapsed_ms = (time.perf_counter() - started) * 1000
        if self._lab_session_id is None:
            return response
        recorder = self._recorder
        await recorder.record(
            TraceEvent(
                lab_session_id=self._lab_session_id,
                ts=started_at,
                channel=Channel.BACK,
                source=recorder.actor,
                target=recorder.actor_for_url(str(request.url)),
                step=self._step,
                response_step=self._response_step,
                duration_ms=round(elapsed_ms, 1),
                request=HttpRequestRecord(
                    method=request.method,
                    url=str(request.url),
                    headers=recorder.headers(request.headers.items()),
                    body=recorder.body(body, request.headers.get("content-type")),
                ),
                response=HttpResponseRecord(
                    status=response.status_code,
                    headers=recorder.headers(response.headers.items()),
                    body=recorder.body(response.content),
                ),
            )
        )
        return response

    def _route(self, request: httpx.Request, body: bytes) -> httpx.Request:
        """In local dev, send *.localhost back-channel calls to the dev server's loopback address.

        The Host header keeps the original name, so the dev server still routes it to the right
        actor, and the trace shows the URL the RP was configured with.
        """
        loopback = self._recorder.settings.backchannel_loopback
        host = request.url.host
        if not loopback or not (host == "localhost" or host.endswith(".localhost")):
            return request
        lb_host, _, lb_port = loopback.partition(":")
        url = request.url.copy_with(host=lb_host, port=int(lb_port) if lb_port else None)
        return httpx.Request(request.method, url, headers=request.headers, content=body)

    async def aclose(self) -> None:
        await self._inner.aclose()
