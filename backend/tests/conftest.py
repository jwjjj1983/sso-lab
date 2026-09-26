import asyncio
import os
import re
import socket
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from http.cookies import SimpleCookie

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
    # SSO_LAB_TEST_STORE=firestore (with the emulator) runs the end-to-end tests on Firestore.
    if os.environ.get("SSO_LAB_TEST_STORE") == "firestore":
        from sso_lab.lab.firestore_store import FirestoreStore

        store = FirestoreStore(project=f"test-{uuid.uuid4().hex[:8]}")
    else:
        store = MemoryStore()
    app = create_app(settings, store)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    lab = Lab(port, settings, store)
    lab.app = app
    try:
        yield lab
    finally:
        await lab.http.aclose()
        server.should_exit = True
        await task


class Browser:
    """A tiny browser: one cookie jar per host, and it follows redirects across hosts.

    Every actor listens on the same loopback port, so a plain HTTP client would share one
    cookie jar between App A, App B and the IdP. Real browsers keep cookies per site, and
    single sign-on depends on it.
    """

    def __init__(self, lab: Lab) -> None:
        self.lab = lab
        self.jars: dict[str, dict[str, str]] = defaultdict(dict)
        self.client = httpx.AsyncClient(base_url=f"http://127.0.0.1:{lab.port}", timeout=10)

    def url(self, actor: str, path: str) -> str:
        return f"http://{actor}.localhost:{self.lab.port}{path}"

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        parsed = httpx.URL(url)
        jar = self.jars[parsed.host]
        headers = {"Host": parsed.netloc.decode(), **kwargs.pop("headers", {})}
        if jar:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in jar.items())
        self.client.cookies.clear()
        resp = await self.client.request(
            method, parsed.raw_path.decode(), headers=headers, **kwargs
        )
        for header in resp.headers.get_list("set-cookie"):
            cookie = SimpleCookie()
            cookie.load(header)
            for name, morsel in cookie.items():
                if morsel["max-age"] == "0" or morsel.value in ("", '""'):
                    jar.pop(name, None)
                else:
                    jar[name] = morsel.value
        return resp

    async def get(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def follow(self, resp: httpx.Response, limit: int = 10) -> httpx.Response:
        """Follow redirects, the way the browser does in the login popup."""
        for _ in range(limit):
            if resp.status_code not in (301, 302, 303, 307, 308):
                return resp
            resp = await self.get(resp.headers["location"])
        raise AssertionError("too many redirects")

    async def aclose(self) -> None:
        await self.client.aclose()


def login_form_tx(html: str) -> str:
    match = re.search(r'name="tx" value="([^"]+)"', html)
    assert match, "no login form on the page"
    return match.group(1)


@pytest.fixture
async def browser(lab) -> AsyncIterator[Browser]:
    b = Browser(lab)
    yield b
    await b.aclose()
