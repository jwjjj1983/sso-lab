import pytest


@pytest.mark.parametrize("actor", ["idp", "app-a", "app-b"])
async def test_host_header_selects_actor(lab, actor):
    resp = await lab.get(actor, "/health")
    assert resp.json() == {"status": "ok", "actor": actor}


async def test_unknown_host_is_rejected(lab):
    resp = await lab.http.get("/health", headers={"Host": "evil.example"})
    assert resp.status_code == 404


async def test_bare_localhost_redirects_to_app_a(lab):
    resp = await lab.http.get("/", headers={"Host": f"localhost:{lab.port}"})
    assert resp.status_code == 307
    assert resp.headers["location"] == f"http://app-a.localhost:{lab.port}/"


async def test_lab_api_only_exists_on_app_a(lab):
    assert (await lab.get("app-a", "/api/lab/config")).status_code == 200
    assert (await lab.get("idp", "/api/lab/config")).status_code == 404
