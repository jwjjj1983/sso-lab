"""Storage for lab sessions, their trace events, and short-lived protocol records.

Records are what the IdP and apps need to remember between requests: IdP sessions,
authorization codes, tokens, an app's in-flight login (state, nonce, PKCE verifier), and the
IdP's signing key. Every record except the signing key expires.

``MemoryStore`` is used in local dev (``role=all`` runs every actor in one process) and tests.
``FirestoreStore`` is used on Cloud Run, where the IdP and apps are separate services that all
write into the same visitor's trace.
"""

import asyncio
import copy
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

from sso_lab.lab.models import LabSession, TraceEvent


class Store(ABC):
    def __init__(self, max_events_per_session: int) -> None:
        self.max_events_per_session = max_events_per_session

    @abstractmethod
    async def create_session(self, session: LabSession) -> None: ...

    @abstractmethod
    async def get_session(self, session_id: str) -> LabSession | None:
        """Return the session, or None if it does not exist or has expired."""

    @abstractmethod
    async def append(self, event: TraceEvent) -> bool:
        """Store an event. Returns False (and drops it) for an unknown session or a full trace."""

    @abstractmethod
    async def list_events(self, session_id: str) -> list[TraceEvent]: ...

    @abstractmethod
    def stream(self, session_id: str) -> AsyncIterator[TraceEvent]:
        """Yield every existing event of the session, then each new one as it is appended."""

    # --- Records ---------------------------------------------------------------------------
    # `data` must be JSON-like and Firestore-compatible (no lists nested directly in lists).

    @abstractmethod
    async def put_record(
        self, kind: str, key: str, data: dict[str, Any], ttl: timedelta | None
    ) -> None:
        """Create or replace a record. ``ttl=None`` means it never expires."""

    @abstractmethod
    async def create_record(
        self, kind: str, key: str, data: dict[str, Any], ttl: timedelta | None
    ) -> bool:
        """Create a record only if no live one exists. Returns whether it was created."""

    @abstractmethod
    async def get_record(self, kind: str, key: str) -> dict[str, Any] | None: ...

    @abstractmethod
    async def take_record(self, kind: str, key: str) -> dict[str, Any] | None:
        """Atomically read and delete a record: for single-use values like authorization codes."""

    @abstractmethod
    async def delete_record(self, kind: str, key: str) -> None: ...

    async def close(self) -> None:  # noqa: B027 - optional hook
        pass


def expiry(ttl: timedelta | None) -> datetime | None:
    return datetime.now(UTC) + ttl if ttl is not None else None


def is_live(expires_at: datetime | None) -> bool:
    return expires_at is None or datetime.now(UTC) < expires_at


class MemoryStore(Store):
    def __init__(self, max_events_per_session: int = 500) -> None:
        super().__init__(max_events_per_session)
        self._sessions: dict[str, LabSession] = {}
        self._events: dict[str, list[TraceEvent]] = defaultdict(list)
        self._subscribers: dict[str, set[asyncio.Queue[TraceEvent]]] = defaultdict(set)
        self._records: dict[tuple[str, str], tuple[dict[str, Any], datetime | None]] = {}

    async def create_session(self, session: LabSession) -> None:
        self._sessions[session.id] = session

    async def get_session(self, session_id: str) -> LabSession | None:
        session = self._sessions.get(session_id)
        if session is None or session.expired:
            return None
        return session

    async def append(self, event: TraceEvent) -> bool:
        if await self.get_session(event.lab_session_id) is None:
            return False
        events = self._events[event.lab_session_id]
        if len(events) >= self.max_events_per_session:
            return False
        events.append(event)
        for queue in self._subscribers.get(event.lab_session_id, ()):
            queue.put_nowait(event)
        return True

    async def list_events(self, session_id: str) -> list[TraceEvent]:
        return list(self._events.get(session_id, ()))

    async def stream(self, session_id: str) -> AsyncIterator[TraceEvent]:
        queue: asyncio.Queue[TraceEvent] = asyncio.Queue()
        self._subscribers[session_id].add(queue)
        try:
            seen: set[str] = set()
            for event in await self.list_events(session_id):
                seen.add(event.id)
                yield event
            while True:
                event = await queue.get()
                if event.id not in seen:
                    yield event
        finally:
            self._subscribers[session_id].discard(queue)

    async def put_record(
        self, kind: str, key: str, data: dict[str, Any], ttl: timedelta | None
    ) -> None:
        self._records[(kind, key)] = (copy.deepcopy(data), expiry(ttl))

    async def create_record(
        self, kind: str, key: str, data: dict[str, Any], ttl: timedelta | None
    ) -> bool:
        if await self.get_record(kind, key) is not None:
            return False
        await self.put_record(kind, key, data, ttl)
        return True

    async def get_record(self, kind: str, key: str) -> dict[str, Any] | None:
        entry = self._records.get((kind, key))
        if entry is None or not is_live(entry[1]):
            return None
        return copy.deepcopy(entry[0])

    async def take_record(self, kind: str, key: str) -> dict[str, Any] | None:
        data = await self.get_record(kind, key)
        self._records.pop((kind, key), None)
        return data

    async def delete_record(self, kind: str, key: str) -> None:
        self._records.pop((kind, key), None)
