import httpx
import pytest

from sso_lab.config import Actor
from sso_lab.lab.store import MemoryStore
from sso_lab.main import build_actor_app
from tests.conftest import make_settings


@pytest.fixture
def spa_client(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('hi')")
    (tmp_path / "index.html").write_text("<!doctype html><title>SSO Lab</title>")
    (tmp_path.parent / "secret.txt").write_text("do not serve")
    settings = make_settings(0, static_dir=tmp_path)
    app = build_actor_app(Actor.APP_A, settings, MemoryStore())
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app-a.localhost"
    )


async def test_client_routes_fall_back_to_index_with_popup_friendly_coop(spa_client):
    resp = await spa_client.get("/lab/diagnostics")
    assert "SSO Lab" in resp.text
    assert resp.headers["cross-origin-opener-policy"] == "same-origin-allow-popups"


async def test_assets_are_served_and_cacheable(spa_client):
    resp = await spa_client.get("/assets/app.js")
    assert resp.text == "console.log('hi')"
    assert "no-store" not in resp.headers.get("cache-control", "")


async def test_no_files_outside_the_static_dir(spa_client):
    resp = await spa_client.get("/%2e%2e/secret.txt")
    assert "do not serve" not in resp.text


async def test_unknown_api_paths_are_404_not_the_spa(spa_client):
    assert (await spa_client.get("/api/nope")).status_code == 404
    assert (await spa_client.get("/rp/nope")).status_code == 404
