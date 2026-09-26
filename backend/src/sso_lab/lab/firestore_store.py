"""Firestore-backed store.

Layout::

    labSessions/{sessionId}                 LabSession + event_count + expires_at
    labSessions/{sessionId}/events/{eventId} TraceEvent + expires_at

Both collections carry an ``expires_at`` timestamp with a Firestore TTL policy
(see infra/terraform), so visitor data is deleted automatically.

Live updates use a snapshot listener, which is billed per changed document rather than
per poll. The listener runs on a background thread owned by the sync client; events are
handed to the asyncio loop through a queue.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from google.cloud import firestore

from sso_lab.lab.models import LabSession, TraceEvent
from sso_lab.lab.store import Store

SESSIONS = "labSessions"
EVENTS = "events"


class FirestoreStore(Store):
    def __init__(self, project: str | None, max_events_per_session: int = 500) -> None:
        super().__init__(max_events_per_session)
        self._db = firestore.AsyncClient(project=project)
        self._sync_db = firestore.Client(project=project)

    async def create_session(self, session: LabSession) -> None:
        data = session.model_dump()
        data["event_count"] = 0
        await self._db.collection(SESSIONS).document(session.id).set(data)

    async def get_session(self, session_id: str) -> LabSession | None:
        snap = await self._db.collection(SESSIONS).document(session_id).get()
        if not snap.exists:
            return None
        session = LabSession.model_validate(snap.to_dict())
        return None if session.expired else session

    async def append(self, event: TraceEvent) -> bool:
        session_ref = self._db.collection(SESSIONS).document(event.lab_session_id)
        snap = await session_ref.get()
        if not snap.exists:
            return False
        data: dict[str, Any] = snap.to_dict() or {}
        session = LabSession.model_validate(data)
        # Soft cap: concurrent appends may overshoot slightly, which is fine for abuse control.
        if session.expired or data.get("event_count", 0) >= self.max_events_per_session:
            return False
        doc = event.model_dump(mode="json")
        doc["ts"] = event.ts  # keep a native timestamp for ordering
        doc["expires_at"] = session.expires_at
        await session_ref.collection(EVENTS).document(event.id).set(doc)
        await session_ref.update({"event_count": firestore.Increment(1)})
        return True

    async def list_events(self, session_id: str) -> list[TraceEvent]:
        query = self._db.collection(SESSIONS).document(session_id).collection(EVENTS).order_by("ts")
        return [_to_event(snap.to_dict()) async for snap in query.stream()]

    async def stream(self, session_id: str) -> AsyncIterator[TraceEvent]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[TraceEvent] = asyncio.Queue()

        def on_snapshot(_docs: Any, changes: Any, _read_time: Any) -> None:
            # The first callback delivers every existing doc as ADDED, so this covers history too.
            for change in sorted(changes, key=lambda c: c.document.get("ts")):
                if change.type.name == "ADDED":
                    event = _to_event(change.document.to_dict())
                    loop.call_soon_threadsafe(queue.put_nowait, event)

        watch = (
            self._sync_db.collection(SESSIONS)
            .document(session_id)
            .collection(EVENTS)
            .order_by("ts")
            .on_snapshot(on_snapshot)
        )
        try:
            while True:
                yield await queue.get()
        finally:
            watch.unsubscribe()

    async def close(self) -> None:
        self._db.close()
        self._sync_db.close()


def _to_event(data: dict[str, Any] | None) -> TraceEvent:
    data = dict(data or {})
    data.pop("expires_at", None)
    return TraceEvent.model_validate(data)
