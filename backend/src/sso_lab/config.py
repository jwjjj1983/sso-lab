"""Runtime configuration.

One container image plays every part of the lab. ``SSO_LAB_ROLE`` picks which one:

* ``idp`` / ``app-a`` / ``app-b`` - one Cloud Run service each, on its own run.app hostname.
* ``all`` - local development: a single process serves all three, routed by the Host header
  (``idp.localhost``, ``app-a.localhost``, ``app-b.localhost``). Browsers treat each
  ``*.localhost`` name as a separate site, so cookie and cross-site behaviour stays realistic.
"""

from enum import StrEnum
from functools import cached_property
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


class Actor(StrEnum):
    """A party that sends or receives protocol messages."""

    BROWSER = "browser"
    IDP = "idp"
    APP_A = "app-a"
    APP_B = "app-b"
    EXTERNAL = "external"


Role = Literal["all", "idp", "app-a", "app-b"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SSO_LAB_", env_file=".env", extra="ignore")

    role: Role = "all"

    # Public base URLs as the browser sees them (no trailing slash).
    idp_url: str = "http://idp.localhost:8000"
    app_a_url: str = "http://app-a.localhost:8000"
    app_b_url: str = "http://app-b.localhost:8000"

    store: Literal["memory", "firestore"] = "memory"
    gcp_project: str | None = None

    # Local dev only: back-channel calls to *.localhost hosts are sent to this address
    # (keeping the original Host header), e.g. "127.0.0.1:8000".
    backchannel_loopback: str | None = None

    # Built SPA to serve from app-a; unset in dev (Vite serves it instead).
    static_dir: Path | None = None

    trace_ttl_hours: int = 24
    max_events_per_session: int = 500
    max_body_bytes: int = 64 * 1024

    # Behind Cloud Run's front end: take the client IP from the right-most X-Forwarded-For entry.
    trust_proxy: bool = False
    rate_limit_per_minute: int = 300
    session_create_limit_per_minute: int = 10

    @cached_property
    def urls(self) -> dict[Actor, str]:
        return {
            Actor.IDP: self.idp_url.rstrip("/"),
            Actor.APP_A: self.app_a_url.rstrip("/"),
            Actor.APP_B: self.app_b_url.rstrip("/"),
        }

    @cached_property
    def origins(self) -> dict[Actor, str]:
        return {actor: origin_of(url) for actor, url in self.urls.items()}

    @cached_property
    def https(self) -> bool:
        return all(url.startswith("https://") for url in self.urls.values())

    def actor_for_host(self, host: str) -> Actor | None:
        """Map a Host header (port ignored) to the lab actor served there."""
        hostname = urlsplit(f"//{host}").hostname
        for actor, url in self.urls.items():
            if urlsplit(url).hostname == hostname:
                return actor
        return None


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"
