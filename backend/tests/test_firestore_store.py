"""Runs against the Firestore emulator: `docker compose up -d firestore` then
`FIRESTORE_EMULATOR_HOST=localhost:8080 uv run pytest -m firestore`."""

import asyncio
import os
import uuid
from datetime import timedelta

import pytest

from sso_lab.config import Actor
from sso_lab.lab.models import Channel, HttpRequestRecord, LabSession, TraceEvent

pytestmark = [
    pytest.mark.firestore,
    pytest.mark.skipif(
        not os.environ.get("FIRESTORE_EMULATOR_HOST"), reason="Firestore emulator not running"
    ),
]


@pytest.fixture
async def store():
    from sso_lab.lab.firestore_store import FirestoreStore

    store = FirestoreStore(project=f"test-{uuid.uuid4().hex[:8]}", max_events_per_session=3)
    yield store
    await store.close()


def _event(session_id: str, step: str) -> TraceEvent:
    return TraceEvent(
        lab_session_id=session_id,
        channel=Channel.BACK,
        source=Actor.APP_A,
        target=Actor.IDP,
        step=step,
        request=HttpRequestRecord(method="GET", url="http://idp/x"),
    )


async def test_session_round_trip_and_expiry(store):
    session, cookie = LabSession.new(timedelta(hours=1))
    await store.create_session(session)
    loaded = await store.get_session(session.id)
    assert loaded is not None
    assert loaded.verify(cookie.split(".", 1)[1])

    expired, _ = LabSession.new(timedelta(seconds=-1))
    await store.create_session(expired)
    assert await store.get_session(expired.id) is None
    assert await store.get_session("missing") is None


async def test_append_list_and_cap(store):
    session, _ = LabSession.new(timedelta(hours=1))
    await store.create_session(session)
    results = [await store.append(_event(session.id, f"s{i}")) for i in range(4)]
    assert results == [True, True, True, False]
    assert [e.step for e in await store.list_events(session.id)] == ["s0", "s1", "s2"]
    assert await store.append(_event("missing", "x")) is False


async def test_stream_replays_history_then_live(store):
    session, _ = LabSession.new(timedelta(hours=1))
    await store.create_session(session)
    await store.append(_event(session.id, "before"))

    stream = store.stream(session.id)
    first = await asyncio.wait_for(anext(stream), timeout=10)
    await store.append(_event(session.id, "after"))
    second = await asyncio.wait_for(anext(stream), timeout=10)
    await stream.aclose()

    assert (first.step, second.step) == ("before", "after")
