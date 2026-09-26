from sso_lab.lab.session import COOKIE


async def test_create_session_sets_httponly_cookie(lab):
    resp = await lab.post("app-a", "/api/lab/sessions")
    assert resp.status_code == 201
    set_cookie = resp.headers["set-cookie"]
    assert set_cookie.startswith(f"{COOKIE}=")
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie

    current = await lab.get("app-a", "/api/lab/session")
    assert current.json()["id"] == resp.json()["id"]


async def test_session_requires_cookie(lab):
    assert (await lab.get("app-a", "/api/lab/session")).status_code == 401


async def test_public_id_alone_does_not_grant_read_access(lab):
    session_id = (await lab.post("app-a", "/api/lab/sessions")).json()["id"]
    lab.http.cookies.clear()
    lab.http.cookies.set(COOKIE, f"{session_id}.not-the-secret")
    assert (await lab.get("app-a", "/api/lab/session")).status_code == 401
    assert (await lab.get("app-a", "/api/lab/events")).status_code == 401


async def test_events_for_unknown_session_are_dropped(lab):
    from sso_lab.config import Actor
    from sso_lab.lab.models import Channel, HttpRequestRecord, TraceEvent

    event = TraceEvent(
        lab_session_id="nope",
        channel=Channel.FRONT,
        source=Actor.BROWSER,
        target=Actor.IDP,
        request=HttpRequestRecord(method="GET", url="http://x"),
    )
    assert await lab.store.append(event) is False
