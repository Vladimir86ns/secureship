"""A fake Auth0 tenant for the admin tests: a local RSA key, its JWKS and OIDC discovery document, served through the
SDK's official `custom_fetch` hook. The SDK still really validates every token (signature, iss, aud, exp) — only the
two HTTP fetches are replaced. Any other URL fails the test: no test ever talks to the network or the real tenant."""

import time
from typing import Any

from authlib.jose import JsonWebKey, jwt

TEST_DOMAIN = "test-tenant.example"
ISSUER = f"https://{TEST_DOMAIN}/"
AUDIENCE = "https://secureship-api.test"
ADMIN_CLIENT_ID = "test-admin-spa-client"
KID = "test-key-1"
DISCOVERY_URL = f"https://{TEST_DOMAIN}/.well-known/openid-configuration"
JWKS_URL = f"https://{TEST_DOMAIN}/.well-known/jwks.json"


def new_rsa_key(kid: str = KID):
    return JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": kid})


class FakeIdP:
    def __init__(self) -> None:
        self.key = new_rsa_key()
        self.fetched: list[str] = []

    async def fetch(self, url: str, **_: Any) -> dict[str, Any]:
        self.fetched.append(url)
        if url == DISCOVERY_URL:
            return {"issuer": ISSUER, "jwks_uri": JWKS_URL}
        if url == JWKS_URL:
            return {"keys": [self.key.as_dict(is_private=False)]}
        raise AssertionError(f"unexpected network fetch in a test: {url}")

    def token(self, *, key: Any = None, alg: str = "RS256", kid: str = KID, **overrides: Any) -> str:
        """A user access token for the admin SPA, as Auth0 issues it. overrides: claim=value, or claim=None to drop it."""
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": ISSUER,
            "sub": "auth0|admin-test-user",
            "aud": [AUDIENCE, f"{ISSUER}userinfo"],
            "azp": ADMIN_CLIENT_ID,
            "iat": now,
            "exp": now + 3600,
            "scope": "openid profile email",
        }
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode({"alg": alg, "kid": kid, "typ": "JWT"}, claims, self.key if key is None else key).decode()

    def headers(self, **overrides: Any) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token(**overrides)}"}
