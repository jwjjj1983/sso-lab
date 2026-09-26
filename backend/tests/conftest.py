import asyncio
import socket
from collections.abc import AsyncIterator

import httpx
import pytest
import uvicorn

from sso_lab.config import Settings
from sso_lab.lab.store import MemoryStore
from sso_lab.main import create_app


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Lab:
    """A running dev server (role=all) plus a client that talks to it as a browser would."""

    def __init__(self, port: int, settings: Settings, store: MemoryStore) -> None:
        self.port = port
        self.settings = settings
        self.store = store
        # All actors listen on one loopback port; the Host header picks the actor, like the
        # browser's *.localhost names do. One cookie jar, keyed on 127.0.0.1, for everything.
        self.http = httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=5)

    def host(self, actor: str) -> dict[str, str]:
        return {"Host": f"{actor}.localhost:{self.port}"}

    async def get(self, actor: str, path: str, **kwargs) -> httpx.Response:
        return await self.http.get(path, headers=self.host(actor), **kwargs)

    async def post(self, actor: str, path: str, **kwargs) -> httpx.Response:
        return await self.http.post(path, headers=self.host(actor), **kwargs)

    async def follow(self, url: str) -> httpx.Response:
        """Follow an absolute redirect URL the way a browser would."""
        parsed = httpx.URL(url)
        path = parsed.raw_path.decode()
        return await self.http.get(path, headers={"Host": parsed.netloc.decode()})


def make_settings(port: int, **overrides) -> Settings:
    overrides.setdefault("role", "all")
    return Settings(
        idp_url=f"http://idp.localhost:{port}",
        app_a_url=f"http://app-a.localhost:{port}",
        app_b_url=f"http://app-b.localhost:{port}",
        backchannel_loopback=f"127.0.0.1:{port}",
        **overrides,
    )


@pytest.fixture
async def lab() -> AsyncIterator[Lab]:
    port = _free_port()
    settings = make_settings(port)
    store = MemoryStore()
    config = uvicorn.Config(
        create_app(settings, store), host="127.0.0.1", port=port, log_level="warning"
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    lab = Lab(port, settings, store)
    try:
        yield lab
    finally:
        await lab.http.aclose()
        server.should_exit = True
        await task
