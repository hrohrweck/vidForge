"""Tests for config hardening: SECRET_KEY, admin password, CORS, token expiry."""

import os
import secrets
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from pydantic_settings import SettingsConfigDict

from app.config import Settings, get_settings


def _settings_no_env(**kwargs) -> Settings:
    """Create Settings without loading .env file, for isolated tests."""
    kwargs.setdefault("_env_file", None)
    return Settings(**kwargs)  # type: ignore[call-arg]


class TestSecretKeyHardening:
    """SECRET_KEY must be explicitly set and cannot use default values."""

    def test_default_secret_key_raises_on_startup(self):
        """App must refuse to start with the old default SECRET_KEY."""
        with patch.dict(os.environ, {}, clear=False):
            if "SECRET_KEY" in os.environ:
                del os.environ["SECRET_KEY"]
            with pytest.raises(ValidationError, match="secret_key"):
                _settings_no_env()

    def test_change_me_secret_key_raises_on_startup(self):
        """The literal 'change-me-in-production' must be rejected."""
        with pytest.raises(ValidationError, match="SECRET_KEY"):
            _settings_no_env(secret_key="change-me-in-production")

    def test_valid_secret_key_accepted(self):
        """A proper random secret key should work."""
        settings = _settings_no_env(secret_key=secrets.token_urlsafe(32))
        assert len(settings.secret_key) >= 16


class TestAdminPasswordHardening:
    """Admin seed password must be randomized, not hardcoded to 'admin'."""

    def test_default_admin_password_is_randomized(self):
        """When ADMIN_PASSWORD is not set, a random password is generated."""
        settings = _settings_no_env(secret_key=secrets.token_urlsafe(32))
        assert settings.admin_password != "admin"
        assert settings.admin_password is not None
        assert len(settings.admin_password) >= 16

    def test_explicit_admin_password_preserved(self):
        """When ADMIN_PASSWORD is explicitly set, it is used."""
        settings = _settings_no_env(
            secret_key=secrets.token_urlsafe(32),
            admin_password="my-explicit-password",
        )
        assert settings.admin_password == "my-explicit-password"


class TestTokenExpiry:
    """Access token expiry should default to 60 minutes."""

    def test_default_token_expiry_is_60_minutes(self):
        """Default access_token_expire_minutes must be 60."""
        settings = _settings_no_env(secret_key=secrets.token_urlsafe(32))
        assert settings.access_token_expire_minutes == 60


class TestCorsOrigins:
    """CORS origins must be configurable via environment."""

    def test_cors_origins_from_env_single(self):
        """Single CORS origin from env is parsed correctly."""
        settings = _settings_no_env(
            secret_key=secrets.token_urlsafe(32),
            cors_origins="http://localhost:3000",
        )
        assert settings.parsed_cors_origins == ["http://localhost:3000"]

    def test_cors_origins_from_env_multiple(self):
        """Multiple CORS origins from comma-separated env are parsed."""
        settings = _settings_no_env(
            secret_key=secrets.token_urlsafe(32),
            cors_origins="http://localhost:3000,http://localhost:5173,https://app.example.com",
        )
        assert settings.parsed_cors_origins == [
            "http://localhost:3000",
            "http://localhost:5173",
            "https://app.example.com",
        ]

    def test_cors_origins_defaults_to_localhost(self):
        """When CORS_ORIGINS is not set, default to common local dev origins."""
        settings = _settings_no_env(secret_key=secrets.token_urlsafe(32))
        assert "http://localhost:3000" in settings.parsed_cors_origins
        assert "http://localhost:5173" in settings.parsed_cors_origins
