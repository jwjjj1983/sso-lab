"""The IdP's token signing key.

Every IdP instance must sign with the same key, and publish it at /jwks, so the key lives in the
shared store. The first instance to start creates it; the rest load it. A production IdP would
keep it in an HSM or KMS and rotate it; publishing keys by URL (JWKS) is what makes rotation
possible without touching the apps.
"""

import secrets
import weakref

from joserfc.jwk import RSAKey

from sso_lab.lab.store import Store

_KIND = "signingKeys"
_KEY = "current"

_cached: weakref.WeakKeyDictionary[Store, RSAKey] = weakref.WeakKeyDictionary()


async def signing_key(store: Store) -> RSAKey:
    cached = _cached.get(store)
    if cached is not None:
        return cached

    record = await store.get_record(_KIND, _KEY)
    if record is None:
        candidate = RSAKey.generate_key(
            2048,
            parameters={"kid": secrets.token_hex(4), "alg": "RS256", "use": "sig"},
            private=True,
        )
        await store.create_record(_KIND, _KEY, {"jwk": candidate.as_dict(private=True)}, ttl=None)
        # Another instance may have won the race: always use what the store holds.
        record = await store.get_record(_KIND, _KEY)
        assert record is not None

    key = RSAKey.import_key(record["jwk"])
    _cached[store] = key
    return key


def public_jwks(key: RSAKey) -> dict[str, list[dict[str, str]]]:
    return {"keys": [key.as_dict(private=False)]}  # type: ignore[list-item]
