"""Authentication.

Two token sources coexist on the HTTP transport:

1. Google OAuth (for humans and for clients that require a full OAuth flow —
   ChatGPT and claude.ai custom connectors). FastMCP's GoogleProvider is an
   OAuthProxy: it presents Dynamic Client Registration to MCP clients while
   using our single fixed Google OAuth app upstream, and issues its own JWTs
   to clients. Access is restricted to AXIOM_ALLOWED_EMAILS — this server
   holds one person's memory, so a successful Google login is not enough.

2. A static service token (AXIOM_SERVICE_TOKEN) for headless callers: curl
   smoke tests, CI, cron. Sent as `Authorization: Bearer <token>`.

MultiAuth tries the OAuth provider first, then the static verifier. It is
built with required_scopes=[] because the global RequireAuthMiddleware check
would otherwise demand one provider's scopes from the other's tokens; each
verifier still enforces its own scopes internally.

Local stdio development needs none of this: build_auth returns None when
nothing is configured, and the transport is already private.
"""

import logging

from fastmcp.server.auth import AuthProvider, MultiAuth, TokenVerifier
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from mcp.server.auth.provider import AccessToken

from axiom.config import Settings

logger = logging.getLogger(__name__)


class RestrictedGoogleProvider(GoogleProvider):
    """GoogleProvider that only admits an allowlist of email addresses.

    The allowlist check runs after the full token swap (FastMCP JWT →
    upstream Google token → tokeninfo/userinfo), so `claims["email"]` is the
    Google-verified address, not anything the client asserted.
    """

    def __init__(self, *, allowed_emails: frozenset[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self._allowed_emails = allowed_emails

    async def load_access_token(self, token: str) -> AccessToken | None:  # type: ignore[override]
        access = await super().load_access_token(token)
        if access is None:
            return None
        email = ((access.claims or {}).get("email") or "").lower()
        if email not in self._allowed_emails:
            logger.warning("Rejected Google login for non-allowlisted email: %r", email)
            return None
        return access


def _service_verifier(token: str) -> TokenVerifier:
    return StaticTokenVerifier(
        tokens={token: {"client_id": "axiom-service", "scopes": ["memory"]}},
        required_scopes=["memory"],
    )


def build_auth(settings: Settings) -> AuthProvider | None:
    """Build the auth provider from settings.

    Returns None when nothing is configured (local stdio development).
    Raises ValueError on partial OAuth configuration rather than starting
    in a state the operator did not intend.
    """
    google_fields = {
        "AXIOM_GOOGLE_CLIENT_ID": settings.google_client_id,
        "AXIOM_GOOGLE_CLIENT_SECRET": settings.google_client_secret,
        "AXIOM_BASE_URL": settings.base_url,
    }
    configured = {name for name, value in google_fields.items() if value}

    google: AuthProvider | None = None
    if configured == set(google_fields):
        allowed = frozenset(
            email.strip().lower() for email in settings.allowed_emails.split(",") if email.strip()
        )
        if not allowed:
            raise ValueError(
                "Google OAuth is configured but AXIOM_ALLOWED_EMAILS is empty — "
                "every login would be rejected. Set it to your email address."
            )
        google = RestrictedGoogleProvider(
            allowed_emails=allowed,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            base_url=settings.base_url,
            # "email" is required so tokeninfo returns the address the
            # allowlist checks; the shorthand is normalized to the full URI.
            required_scopes=["openid", "email"],
        )
    elif configured:
        missing = ", ".join(sorted(set(google_fields) - configured))
        raise ValueError(f"Partial Google OAuth config: missing {missing}")

    service = _service_verifier(settings.service_token) if settings.service_token else None

    if google and service:
        return MultiAuth(server=google, verifiers=[service], required_scopes=[])
    return google or service
