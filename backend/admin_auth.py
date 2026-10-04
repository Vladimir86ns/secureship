"""Admin authentication (Epic E1/E3) — Auth0 access tokens, used ONLY by the /admin/* routes.

This is a separate identity system from the chat's conversational verification (Section 4.5, Epic E4): nothing here reads
the chat session cookie or touches chat_sessions, and nothing in the chat flow reads an Authorization header.

Token validation is done by Auth0's SDK (auth0-fastapi-api): RS256 signature against the tenant's JWKS, `iss`, `aud`,
`exp` and `iat`. On top of that, require_admin accepts only tokens issued to the admin SPA (`azp`) for a signed-in user —
a machine-to-machine (client-credentials) token for the same API is refused even though its signature is valid.
"""

import hashlib
import logging
from dataclasses import dataclass

from fastapi import HTTPException, Request
from fastapi_plugin import Auth0FastAPI

from config import settings

logger = logging.getLogger("secureship.admin")


def build_verifier(custom_fetch=None) -> Auth0FastAPI:
    # dpop_enabled=False: the admin SPA sends plain Bearer tokens. custom_fetch is only used by tests (no network).
    return Auth0FastAPI(
        domain=settings.auth0_domain,
        audience=settings.auth0_audience,
        custom_fetch=custom_fetch,
        dpop_enabled=False,
    )


verifier = build_verifier()


@dataclass(frozen=True)
class AdminPrincipal:
    sub: str

    @property
    def ref(self) -> str:
        """For logs: a short hash of the Auth0 user id, never the id or email itself."""
        return hashlib.sha256(self.sub.encode()).hexdigest()[:8]


def _not_admin() -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={"error": "not_admin", "error_description": "This token was not issued to the admin application."},
    )


async def require_admin(request: Request) -> AdminPrincipal:
    """The admin gate (Epic E3) — a dependency on the whole /admin router, so no admin route can skip it."""
    try:
        claims = await verifier.require_auth()(request)
    except HTTPException as exc:
        error = exc.detail.get("error") if isinstance(exc.detail, dict) else "-"
        logger.warning("admin DENIED status=%s error=%s path=%s", exc.status_code, error, request.url.path)
        raise

    sub = claims.get("sub")
    if (
        claims.get("azp") != settings.auth0_admin_client_id
        or claims.get("gty") == "client-credentials"
        or not isinstance(sub, str)
        or not sub
    ):
        logger.warning("admin DENIED status=403 error=not_admin path=%s", request.url.path)
        raise _not_admin()
    return AdminPrincipal(sub=sub)
