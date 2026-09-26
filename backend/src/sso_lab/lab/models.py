"""Trace data model.

A ``TraceEvent`` is either one HTTP exchange between two lab actors (front or back channel), or a
``local`` event: work done inside one party that sends no message, such as generating the PKCE
values or validating an ID token. Local events carry the values and check results to show.
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field

from sso_lab.config import Actor


class Channel(StrEnum):
    # Carried by the browser (redirects, form posts): visible to the user and to extensions.
    FRONT = "front"
    # Server to server (e.g. the OAuth token request): invisible to the browser.
    BACK = "back"
    # Inside one party: no message is sent.
    LOCAL = "local"


class Header(BaseModel):
    name: str
    value: str


class HttpRequestRecord(BaseModel):
    method: str
    url: str
    headers: list[Header] = []
    body: str | None = None


class HttpResponseRecord(BaseModel):
    status: int
    headers: list[Header] = []
    body: str | None = None


class Check(BaseModel):
    """One validation a party performed, e.g. "ID token `aud` contains app-a"."""

    label: str
    ok: bool
    detail: str | None = None


class TraceEvent(BaseModel):
    id: str = Field(default_factory=lambda: secrets.token_hex(8))
    lab_session_id: str
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    channel: Channel
    source: Actor
    target: Actor
    # Protocol step this exchange belongs to, e.g. "oidc.token"; matches the flow specs.
    step: str | None = None
    # Step the *response* belongs to, when it is a different one: e.g. GET /login (oidc.login)
    # answered by a redirect to the IdP (oidc.authorize-redirect).
    response_step: str | None = None
    request: HttpRequestRecord | None = None
    response: HttpResponseRecord | None = None
    duration_ms: float | None = None
    note: str | None = None
    # Local events: what was checked, and values worth showing (flat strings only).
    checks: list[Check] = []
    data: dict[str, str] = {}


class LabSession(BaseModel):
    """A visitor's lab session.

    ``id`` is public: it travels in URLs to the IdP and other apps so they can append to this
    visitor's trace. Reading the trace needs the secret, which only lives in the visitor's
    HttpOnly cookie on app-a (only its SHA-256 is stored).
    """

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(16))
    secret_hash: str
    created_at: datetime
    expires_at: datetime

    @classmethod
    def new(cls, ttl: timedelta) -> tuple["LabSession", str]:
        secret = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        session = cls(secret_hash=_hash(secret), created_at=now, expires_at=now + ttl)
        return session, f"{session.id}.{secret}"

    @property
    def expired(self) -> bool:
        return datetime.now(UTC) >= self.expires_at

    def verify(self, secret: str) -> bool:
        return hmac.compare_digest(self.secret_hash, _hash(secret))


def split_cookie(value: str) -> tuple[str, str] | None:
    session_id, sep, secret = value.partition(".")
    return (session_id, secret) if sep and session_id and secret else None


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()
