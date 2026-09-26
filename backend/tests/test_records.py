"""The expiring-records API, against the memory store and (if running) the Firestore emulator."""

import asyncio
import os
import uuid
from datetime import timedelta

import pytest

from sso_lab.lab.store import MemoryStore


@pytest.fixture(params=["memory", "firestore"])
async def store(request):
    if request.param == "memory":
        yield MemoryStore()
        return
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        pytest.skip("Firestore emulator not running")
    from sso_lab.lab.firestore_store import FirestoreStore

    s = FirestoreStore(project=f"test-{uuid.uuid4().hex[:8]}")
    yield s
    await s.close()


HOUR = timedelta(hours=1)


async def test_put_get_delete(store):
    await store.put_record("thing", "k1", {"a": "1", "nested": {"b": 2}}, HOUR)
    assert await store.get_record("thing", "k1") == {"a": "1", "nested": {"b": 2}}
    assert await store.get_record("other", "k1") is None
    await store.delete_record("thing", "k1")
    assert await store.get_record("thing", "k1") is None


async def test_expired_records_are_gone(store):
    await store.put_record("thing", "old", {"a": "1"}, timedelta(seconds=-1))
    assert await store.get_record("thing", "old") is None


async def test_records_without_ttl_never_expire(store):
    await store.put_record("thing", "forever", {"a": "1"}, None)
    assert await store.get_record("thing", "forever") == {"a": "1"}


async def test_take_is_single_use_even_under_concurrency(store):
    await store.put_record("code", "c1", {"sub": "alice"}, HOUR)
    results = await asyncio.gather(*(store.take_record("code", "c1") for _ in range(5)))
    assert [r for r in results if r is not None] == [{"sub": "alice"}]
    assert await store.get_record("code", "c1") is None


async def test_create_only_if_absent(store):
    assert await store.create_record("key", "current", {"v": "first"}, None) is True
    assert await store.create_record("key", "current", {"v": "second"}, None) is False
    assert await store.get_record("key", "current") == {"v": "first"}

    await store.put_record("key", "stale", {"v": "old"}, timedelta(seconds=-1))
    assert await store.create_record("key", "stale", {"v": "new"}, HOUR) is True
