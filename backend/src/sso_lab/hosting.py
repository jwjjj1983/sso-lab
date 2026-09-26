"""Local-dev host routing: one process serves idp/app-a/app-b on separate *.localhost names."""

from collections.abc import Awaitable, Callable

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse, RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from sso_lab.config import Actor, Settings


class HostDispatcher:
    def __init__(
        self,
        apps: dict[Actor, ASGIApp],
        settings: Settings,
        on_shutdown: Callable[[], Awaitable[None]],
    ) -> None:
        self.apps = apps
        self.settings = settings
        self.on_shutdown = on_shutdown

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self._lifespan(receive, send)
            return

        host = Headers(scope=scope).get("host", "")
        actor = self.settings.actor_for_host(host)
        if actor in self.apps:
            await self.apps[actor](scope, receive, send)
            return

        if host.split(":")[0] in ("localhost", "127.0.0.1"):
            # Friendly redirect for people who open http://localhost:8000 directly.
            response = RedirectResponse(self.settings.urls[Actor.APP_A] + "/")
        else:
            response = PlainTextResponse(f"Unknown host {host!r}", status_code=404)
        await response(scope, receive, send)

    async def _lifespan(self, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await self.on_shutdown()
                await send({"type": "lifespan.shutdown.complete"})
                return
