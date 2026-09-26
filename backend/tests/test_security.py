import httpx

from sso_lab.config import Actor
from sso_lab.lab.store import MemoryStore
from sso_lab.main import build_actor_app
from tests.conftest import make_settings


async def test_baseline_security_headers(lab):
    resp = await lab.get("idp", "/")
    csp = resp.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert resp.headers["cache-control"] == "no-store"
    # Plain http in dev: no HSTS.
    assert "strict-transport-security" not in resp.headers


async def test_hsts_when_served_over_https():
    settings = make_settings(0).model_copy(
        update={
            "idp_url": "https://idp.example",
            "app_a_url": "https://a.example",
            "app_b_url": "https://b.example",
        }
    )
    app = build_actor_app(Actor.IDP, settings, MemoryStore())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://idp.example"
    ) as client:
        resp = await client.get("/health")
    assert resp.headers["strict-transport-security"] == "max-age=31536000"


async def test_session_creation_is_rate_limited():
    settings = make_settings(0, session_create_limit_per_minute=2)
    app = build_actor_app(Actor.APP_A, settings, MemoryStore())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app-a.localhost"
    ) as client:
        codes = [(await client.post("/api/lab/sessions")).status_code for _ in range(3)]
        assert (await client.get("/api/lab/config")).status_code == 200
    assert codes == [201, 201, 429]


async def test_rate_limit_uses_rightmost_forwarded_ip_when_behind_proxy():
    settings = make_settings(0, session_create_limit_per_minute=1, trust_proxy=True)
    app = build_actor_app(Actor.APP_A, settings, MemoryStore())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://app-a.localhost"
    ) as client:
        # Spoofed left-most entries must not buy a fresh quota.
        first = await client.post(
            "/api/lab/sessions", headers={"X-Forwarded-For": "1.1.1.1, 198.51.100.7"}
        )
        spoofed = await client.post(
            "/api/lab/sessions", headers={"X-Forwarded-For": "2.2.2.2, 198.51.100.7"}
        )
        other = await client.post("/api/lab/sessions", headers={"X-Forwarded-For": "198.51.100.8"})
    assert (first.status_code, spoofed.status_code, other.status_code) == (201, 429, 201)


async def test_other_hostnames_redirect_to_the_canonical_url():
    settings = make_settings(0, role="idp").model_copy(
        update={"idp_url": "https://sso-lab-idp-123.us-central1.run.app"}
    )
    app = build_actor_app(Actor.IDP, settings, MemoryStore())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport) as client:
        legacy = "https://sso-lab-idp-abc-uc.a.run.app"
        resp = await client.get(f"{legacy}/diag/echo?x=1")
        assert resp.status_code == 308
        assert resp.headers["location"] == (
            "https://sso-lab-idp-123.us-central1.run.app/diag/echo?x=1"
        )
        # Health checks answer on any hostname.
        assert (await client.get(f"{legacy}/health")).status_code == 200
        canonical = await client.get("https://sso-lab-idp-123.us-central1.run.app/health")
        assert canonical.status_code == 200
