"""Storage for lab sessions and their trace events.

``MemoryStore`` is used in local dev (``role=all`` runs every actor in one process) and tests.
``FirestoreStore`` is used on Cloud Run, where the IdP and apps are separate services that all
write into the same visitor's trace.
"""

import asyncio
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import AsyncIterator

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

    async def close(self) -> None:  # noqa: B027 - optional hook
        pass


class MemoryStore(Store):
    def __init__(self, max_events_per_session: int = 500) -> None:
        super().__init__(max_events_per_session)
        self._sessions: dict[str, LabSession] = {}
        self._events: dict[str, list[TraceEvent]] = defaultdict(list)
        self._subscribers: dict[str, set[asyncio.Queue[TraceEvent]]] = defaultdict(set)

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
