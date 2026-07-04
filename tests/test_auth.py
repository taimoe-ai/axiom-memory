"""Auth wiring: OAuth + service token composition from settings, the email
allowlist on Google logins, and the no-auth stdio default."""

import pytest
from fastmcp.server.auth import AccessToken, MultiAuth
from fastmcp.server.auth.providers.google import GoogleProvider

from axiom.auth import RestrictedGoogleProvider, build_auth
from axiom.config import Settings

TOKEN = "test-secret-token"

GOOGLE_KWARGS = {
    "google_client_id": "000000000000-test.apps.googleusercontent.com",
    "google_client_secret": "GOCSPX-test",
    "base_url": "http://localhost:8080",
    "allowed_emails": "me@example.com",
}


def make_settings(**kwargs) -> Settings:
    # _env_file=None so a developer's real .env can't leak into tests.
    return Settings(_env_file=None, **kwargs)  # pyright: ignore[reportCallIssue]


def test_no_auth_when_nothing_configured():
    assert build_auth(make_settings()) is None


async def test_service_token_only_accepts_configured_token():
    verifier = build_auth(make_settings(service_token=TOKEN))
    assert verifier is not None

    valid = await verifier.verify_token(TOKEN)
    assert valid is not None
    assert "memory" in valid.scopes

    assert await verifier.verify_token("wrong-token") is None
    assert await verifier.verify_token("") is None


def test_partial_google_config_raises():
    with pytest.raises(ValueError, match="AXIOM_GOOGLE_CLIENT_SECRET"):
        build_auth(
            make_settings(
                google_client_id="id.apps.googleusercontent.com",
                base_url="http://localhost:8080",
            )
        )


def test_google_without_allowed_emails_raises():
    with pytest.raises(ValueError, match="ALLOWED_EMAILS"):
        build_auth(make_settings(**{**GOOGLE_KWARGS, "allowed_emails": " "}))


def test_google_only_builds_restricted_provider():
    auth = build_auth(make_settings(**GOOGLE_KWARGS))
    assert isinstance(auth, RestrictedGoogleProvider)


async def test_google_plus_service_token_composes_multiauth():
    auth = build_auth(make_settings(**GOOGLE_KWARGS, service_token=TOKEN))
    assert isinstance(auth, MultiAuth)

    # The static token verifies even though the OAuth provider is tried first.
    valid = await auth.verify_token(TOKEN)
    assert valid is not None
    assert "memory" in valid.scopes

    assert await auth.verify_token("wrong-token") is None


def _google_token(email: str | None) -> AccessToken:
    return AccessToken(
        token="upstream",
        client_id="google-user",
        scopes=["openid"],
        claims={"email": email},
    )


@pytest.mark.parametrize(
    ("email", "admitted"),
    [
        ("me@example.com", True),
        ("ME@Example.COM", True),  # case-insensitive
        ("intruder@example.com", False),
        (None, False),  # no email claim at all
    ],
)
async def test_google_email_allowlist(monkeypatch, email, admitted):
    async def fake_load(self, token):
        return _google_token(email)

    monkeypatch.setattr(GoogleProvider, "load_access_token", fake_load)

    provider = build_auth(make_settings(**GOOGLE_KWARGS))
    assert isinstance(provider, RestrictedGoogleProvider)
    result = await provider.load_access_token("any-fastmcp-jwt")
    assert (result is not None) == admitted


async def test_allowlist_rejection_does_not_leak_to_service_path(monkeypatch):
    """A denied Google login must not accidentally verify via the static
    verifier when both are configured."""

    async def fake_load(self, token):
        return _google_token("intruder@example.com")

    monkeypatch.setattr(GoogleProvider, "load_access_token", fake_load)

    auth = build_auth(make_settings(**GOOGLE_KWARGS, service_token=TOKEN))
    assert auth is not None
    assert await auth.verify_token("some-google-jwt") is None
