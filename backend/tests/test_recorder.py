import asyncio
import json
from urllib.parse import parse_qs, urlsplit


async def _start_session(lab) -> str:
    return (await lab.post("app-a", "/api/lab/sessions")).json()["id"]


async def test_back_channel_calls_are_recorded(lab):
    session_id = await _start_session(lab)

    resp = await lab.post("app-a", "/api/lab/diagnostics/back-channel")
    assert resp.json() == [
        {"target": "idp", "status": 200, "error": None},
        {"target": "app-b", "status": 200, "error": None},
    ]

    events = await lab.store.list_events(session_id)
    assert [(e.channel, e.source, e.target) for e in events] == [
        ("back", "app-a", "idp"),
        ("back", "app-a", "app-b"),
    ]
    first = events[0]
    assert first.step == "diag.back-channel"
    # The trace shows the configured URL, not the dev loopback address it was routed to.
    assert first.request.url == f"http://idp.localhost:{lab.port}/diag/ping"
    assert first.response.status == 200
    assert json.loads(first.response.body)["actor"] == "idp"
    assert first.duration_ms is not None


async def test_front_channel_round_trip_is_recorded_hop_by_hop(lab):
    session_id = await _start_session(lab)

    start = await lab.get("app-a", "/rp/diag/start")
    assert start.status_code == 302
    to_idp = start.headers["location"]
    assert urlsplit(to_idp).netloc == f"idp.localhost:{lab.port}"
    assert parse_qs(urlsplit(to_idp).query)["lab_session"] == [session_id]

    echo = await lab.follow(to_idp)
    assert echo.status_code == 302
    back = await lab.follow(echo.headers["location"])
    assert back.status_code == 200
    assert "postMessage" in back.text
    csp = back.headers["content-security-policy"]
    assert "script-src 'nonce-" in csp

    events = await lab.store.list_events(session_id)
    assert [(e.channel, e.source, e.target, e.response.status) for e in events] == [
        ("front", "browser", "app-a", 302),
        ("front", "browser", "idp", 302),
        ("front", "browser", "app-a", 200),
    ]
    assert all(e.step == "diag.front-channel" for e in events)


async def test_idp_rejects_unregistered_return_url(lab):
    session_id = await _start_session(lab)
    evil = f"http://app-a.localhost:{lab.port}/rp/diag/return.evil.example"
    resp = await lab.get("idp", "/diag/echo", params={"return_to": evil, "lab_session": session_id})
    assert resp.status_code == 400
    assert "location" not in resp.headers


async def test_infrastructure_headers_are_not_recorded(lab):
    session_id = await _start_session(lab)
    await lab.http.get(
        "/rp/diag/start",
        headers={**lab.host("app-a"), "X-Forwarded-For": "203.0.113.9", "X-Custom": "kept"},
    )
    names = {h.name.lower() for h in (await lab.store.list_events(session_id))[0].request.headers}
    assert "x-forwarded-for" not in names
    assert "x-custom" in names


async def test_event_stream_replays_history_then_goes_live(lab):
    await _start_session(lab)
    await lab.post("app-a", "/api/lab/diagnostics/back-channel")  # 2 events before connecting

    received: list[dict] = []

    async def read_stream():
        async with lab.http.stream("GET", "/api/lab/events", headers=lab.host("app-a")) as resp:
            assert resp.headers["content-type"].startswith("text/event-stream")
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    received.append(json.loads(line.removeprefix("data:").strip()))
                    if len(received) == 4:
                        return

    reader = asyncio.create_task(read_stream())
    while len(received) < 2:
        await asyncio.sleep(0.02)
    await lab.post("app-a", "/api/lab/diagnostics/back-channel")  # 2 live events
    await asyncio.wait_for(reader, timeout=5)

    assert [e["target"] for e in received] == ["idp", "app-b", "idp", "app-b"]
    assert len({e["id"] for e in received}) == 4
