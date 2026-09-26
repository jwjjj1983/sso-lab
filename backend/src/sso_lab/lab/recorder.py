"""The flight recorder: turns HTTP exchanges into ``TraceEvent``s.

Every exchange is recorded exactly once, by the party that can see all of it:

* Front channel (browser -> actor): the receiving actor records the request and the response
  it sends back (often a 302 that moves the browser to the next hop). See ``Recorder.inbound``.
* Back channel (actor -> actor): the calling actor records it with a recording httpx client.
  See ``Recorder.client``. The receiving actor does not record it again.

Recording is best-effort: a failure to store a trace never breaks the protocol flow.
"""

import logging
import time
from collections.abc import Iterable
from urllib.parse import urlsplit

import httpx
from starlette.requests import Request
from starlette.responses import Response

from sso_lab.config import Actor, Settings
from sso_lab.lab.models import (
    Channel,
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

    async def inbound(
        self,
        request: Request,
        response: Response,
        *,
        lab_session_id: str,
        step: str | None = None,
        note: str | None = None,
        source: Actor = Actor.BROWSER,
    ) -> None:
        """Record a front-channel request this actor received and the response it returns."""
        await self.record(
            TraceEvent(
                lab_session_id=lab_session_id,
                channel=Channel.FRONT,
                source=source,
                target=self.actor,
                step=step,
                note=note,
                request=HttpRequestRecord(
                    method=request.method,
                    url=self._public_url(request),
                    headers=self._headers(request.headers.items()),
                    body=self._body(await request.body()),
                ),
                response=HttpResponseRecord(
                    status=response.status_code,
                    headers=self._headers(response.headers.items()),
                    body=self._body(bytes(response.body)) if hasattr(response, "body") else None,
                ),
            )
        )

    def client(self, *, lab_session_id: str, step: str | None = None) -> httpx.AsyncClient:
        """An httpx client whose every request is recorded as a back-channel event."""
        transport = _RecordingTransport(self, lab_session_id=lab_session_id, step=step)
        return httpx.AsyncClient(transport=transport, timeout=10.0, follow_redirects=False)

    def actor_for_url(self, url: str) -> Actor:
        host = urlsplit(url).netloc
        return self.settings.actor_for_host(host) or Actor.EXTERNAL

    def _public_url(self, request: Request) -> str:
        # Behind Cloud Run the app sees http://; show the URL the browser actually used.
        base = self.settings.urls.get(self.actor)
        path = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        return f"{base}{path}" if base else str(request.url)

    def _headers(self, items: Iterable[tuple[str, str]]) -> list[Header]:
        return [
            Header(name=name, value=value)
            for name, value in items
            if not name.lower().startswith(_DROP_HEADER_PREFIXES)
        ]

    def _body(self, raw: bytes) -> str | None:
        if not raw:
            return None
        limit = self.settings.max_body_bytes
        text = raw[:limit].decode("utf-8", errors="replace")
        return text + "\n…[truncated]" if len(raw) > limit else text


class _RecordingTransport(httpx.AsyncBaseTransport):
    def __init__(self, recorder: Recorder, *, lab_session_id: str, step: str | None) -> None:
        self._recorder = recorder
        self._lab_session_id = lab_session_id
        self._step = step
        self._inner = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        started = time.perf_counter()
        response = await self._inner.handle_async_request(self._route(request, body))
        await response.aread()
        elapsed_ms = (time.perf_counter() - started) * 1000
        recorder = self._recorder
        await recorder.record(
            TraceEvent(
                lab_session_id=self._lab_session_id,
                channel=Channel.BACK,
                source=recorder.actor,
                target=recorder.actor_for_url(str(request.url)),
                step=self._step,
                duration_ms=round(elapsed_ms, 1),
                request=HttpRequestRecord(
                    method=request.method,
                    url=str(request.url),
                    headers=recorder._headers(request.headers.items()),
                    body=recorder._body(body),
                ),
                response=HttpResponseRecord(
                    status=response.status_code,
                    headers=recorder._headers(response.headers.items()),
                    body=recorder._body(response.content),
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
