"""Demo users and client registrations.

⚠️ Every credential here is a public, throwaway demo value, checked in on purpose so the lab
can show exactly what travels over the wire. None of them protect anything real.
"""

from dataclasses import dataclass

from sso_lab.config import Actor, Settings


@dataclass(frozen=True)
class DemoUser:
    sub: str
    password: str
    name: str
    email: str


DEMO_USERS: dict[str, DemoUser] = {
    user.sub: user
    for user in (
        DemoUser(
            sub="alice", password="wonderland", name="Alice Liddell", email="alice@example.com"
        ),
        DemoUser(sub="bob", password="builder", name="Bob Builder", email="bob@example.com"),
    )
}


@dataclass(frozen=True)
class Client:
    """An app registered with the IdP (OIDC "client registration")."""

    client_id: str
    client_secret: str
    name: str
    redirect_uris: tuple[str, ...]
    post_logout_redirect_uris: tuple[str, ...]


CLIENT_SECRETS = {
    Actor.APP_A: "app-a-demo-secret",
    Actor.APP_B: "app-b-demo-secret",
}

CALLBACK_PATH = "/rp/oidc/callback"
LOGGED_OUT_PATH = "/rp/oidc/logged-out"


def registered_clients(settings: Settings) -> dict[str, Client]:
    clients = {}
    for actor, name in ((Actor.APP_A, "App A"), (Actor.APP_B, "App B")):
        base = settings.urls[actor]
        clients[actor.value] = Client(
            client_id=actor.value,
            client_secret=CLIENT_SECRETS[actor],
            name=name,
            redirect_uris=(base + CALLBACK_PATH,),
            post_logout_redirect_uris=(base + LOGGED_OUT_PATH,),
        )
    return clients
