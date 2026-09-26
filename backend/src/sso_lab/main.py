"""Application factory.

Run locally (all actors in one process, routed by Host header)::

    uv run uvicorn sso_lab.main:create_app --factory --port 8000

On Cloud Run each service sets ``SSO_LAB_ROLE`` to idp, app-a or app-b.
"""

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import ASGIApp

from sso_lab.config import Actor, Settings
from sso_lab.hosting import HostDispatcher
from sso_lab.idp.api import router as idp_router
from sso_lab.lab.api import router as lab_router
from sso_lab.lab.recorder import Recorder
from sso_lab.lab.store import MemoryStore, Store
from sso_lab.pages import page
from sso_lab.rp.api import router as rp_router
from sso_lab.security import (
    CanonicalHostMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)

logging.basicConfig(level=logging.INFO)


def create_app(settings: Settings | None = None, store: Store | None = None) -> ASGIApp:
    settings = settings or Settings()
    store = store or make_store(settings)

    if settings.role == "all":
        apps = {
            actor: build_actor_app(actor, settings, store)
            for actor in (Actor.IDP, Actor.APP_A, Actor.APP_B)
        }
        return HostDispatcher(apps, settings, on_shutdown=store.close)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
        yield
        await store.close()

    return build_actor_app(Actor(settings.role), settings, store, lifespan=lifespan)


def make_store(settings: Settings) -> Store:
    if settings.store == "firestore":
        from sso_lab.lab.firestore_store import FirestoreStore

        return FirestoreStore(settings.gcp_project, settings.max_events_per_session)
    return MemoryStore(settings.max_events_per_session)


def build_actor_app(
    actor: Actor, settings: Settings, store: Store, lifespan: object = None
) -> FastAPI:
    app = FastAPI(
        title=f"SSO Lab {actor.value}",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,  # type: ignore[arg-type]
    )
    app.state.settings = settings
    app.state.store = store
    app.state.recorder = Recorder(settings, store, actor)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "actor": actor.value}

    @app.get("/diag/ping")
    async def ping() -> dict[str, str]:
        """Target of the back-channel diagnostic."""
        return {"actor": actor.value, "time": datetime.now(UTC).isoformat()}

    if actor is Actor.IDP:
        app.include_router(idp_router)
    else:
        app.include_router(rp_router)

    if actor is Actor.APP_A:
        app.include_router(lab_router)
        if settings.static_dir:
            _mount_spa(app, settings.static_dir)
    elif actor is Actor.APP_B:

        @app.get("/")
        async def app_b_home():  # type: ignore[no-untyped-def]
            return page(
                badge="App B",
                title="App B",
                body_html="<p>A second relying party. Sign in to App A first, then come here "
                "to see single sign-on at work (coming in a later milestone).</p>",
            )

    app.add_middleware(RateLimitMiddleware, settings=settings)
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    if settings.role != "all":  # in dev, HostDispatcher already routes by host
        app.add_middleware(CanonicalHostMiddleware, settings=settings, actor=actor)
    return app


def _mount_spa(app: FastAPI, static_dir: Path) -> None:
    """Serve the built React app, falling back to index.html for client-side routes."""
    root = static_dir.resolve()
    index = root / "index.html"
    if (root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path.startswith(("api/", "rp/")):
            raise HTTPException(status_code=404)
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        # The playground opens login popups that must be able to report back via
        # window.opener, so allow popups rather than isolating this page completely.
        return FileResponse(
            index, headers={"Cross-Origin-Opener-Policy": "same-origin-allow-popups"}
        )
