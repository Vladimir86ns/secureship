"""Epic E3: /admin/* is protected on the backend by Auth0 access-token validation (signature via JWKS, iss, aud, exp),
plus: only tokens issued to the admin SPA for a signed-in user. Fake tenant, no network (tests/admin_tokens.py)."""

import time

from authlib.jose import jwt
from fastapi.routing import APIRoute

from admin_auth import require_admin
from main import app
from tests.admin_tokens import ADMIN_CLIENT_ID, ISSUER, new_rsa_key

URL = "/admin/customers"


def _error(resp) -> str:
    return resp.json()["detail"]["error"]


async def test_no_token_is_refused(client, idp):
    resp = await client.get(URL)
    assert resp.status_code == 400
    assert _error(resp) == "invalid_request"
    assert idp.fetched == []  # refused before any key lookup


async def test_not_a_jwt_is_refused(client, idp):
    resp = await client.get(URL, headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401
    assert _error(resp) == "invalid_token"


async def test_wrong_audience_is_refused(client, idp):
    resp = await client.get(URL, headers=idp.headers(aud="https://some-other-api"))
    assert resp.status_code == 401
    assert _error(resp) == "invalid_token"


async def test_expired_token_is_refused(client, idp):
    now = int(time.time())
    resp = await client.get(URL, headers=idp.headers(iat=now - 7200, exp=now - 60))
    assert resp.status_code == 401
    assert _error(resp) == "invalid_token"


async def test_wrong_issuer_is_refused(client, idp):
    resp = await client.get(URL, headers=idp.headers(iss="https://evil-tenant.example/"))
    assert resp.status_code == 401


async def test_token_signed_with_another_key_is_refused(client, idp):
    resp = await client.get(URL, headers=idp.headers(key=new_rsa_key()))  # same kid, attacker's key
    assert resp.status_code == 401


async def test_symmetric_hs256_token_is_refused(client, idp):
    now = int(time.time())
    claims = {"iss": ISSUER, "sub": "auth0|x", "aud": "https://secureship-api.test", "azp": ADMIN_CLIENT_ID,
              "iat": now, "exp": now + 3600}
    token = jwt.encode({"alg": "HS256", "kid": "test-key-1"}, claims, b"guessable-secret").decode()
    resp = await client.get(URL, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_missing_exp_is_refused(client, idp):
    resp = await client.get(URL, headers=idp.headers(exp=None))
    assert resp.status_code == 401


async def test_valid_admin_token_is_accepted(client, idp):
    resp = await client.get(URL, headers=idp.headers())
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert set(idp.fetched) <= {"https://test-tenant.example/.well-known/openid-configuration",
                                "https://test-tenant.example/.well-known/jwks.json"}


async def test_token_for_another_application_is_refused(client, idp):
    resp = await client.get(URL, headers=idp.headers(azp="some-other-client"))
    assert resp.status_code == 403
    assert _error(resp) == "not_admin"


async def test_token_without_azp_is_refused(client, idp):
    resp = await client.get(URL, headers=idp.headers(azp=None))
    assert resp.status_code == 403


async def test_machine_to_machine_token_is_refused(client, idp):
    # Client-credentials token: valid signature/aud, but no user — e.g. the Dashboard's auto-created Test Application.
    resp = await client.get(URL, headers=idp.headers(gty="client-credentials", sub=f"{ADMIN_CLIENT_ID}@clients"))
    assert resp.status_code == 403
    assert _error(resp) == "not_admin"


def _depends_on(route: APIRoute, dependency) -> bool:
    stack = [route.dependant]
    while stack:
        dep = stack.pop()
        if dep.call is dependency:
            return True
        stack.extend(dep.dependencies)
    return False


def test_every_admin_route_requires_admin_and_no_other_route_does():
    routes = [r for r in app.routes if isinstance(r, APIRoute)]
    admin_routes = [r for r in routes if r.path.startswith("/admin")]
    assert admin_routes
    for route in admin_routes:
        assert _depends_on(route, require_admin), route.path
    for route in routes:
        if not route.path.startswith("/admin"):
            assert not _depends_on(route, require_admin), route.path
