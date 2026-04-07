"""Tests for config module."""

from unittest.mock import patch

import pytest

from config import Settings, get_settings, settings


class TestSettings:
    def test_defaults(self):
        s = Settings()
        assert s.APP_NAME == "ROSA Automation"
        assert s.HOST == "0.0.0.0"
        assert s.PORT == 8000
        assert isinstance(s.DEBUG, bool)
        assert isinstance(s.LOG_LEVEL, str)

    def test_cors_origins_list(self):
        s = Settings()
        origins = s.cors_origins_list
        assert isinstance(origins, list)
        assert "http://localhost:3000" in origins

    def test_cors_origins_list_multiple(self):
        s = Settings(CORS_ORIGINS="http://localhost:3000,http://localhost:8080")
        origins = s.cors_origins_list
        assert len(origins) == 2
        assert "http://localhost:3000" in origins
        assert "http://localhost:8080" in origins

    def test_security_defaults(self):
        s = Settings()
        assert s.SECRET_KEY is None
        assert s.JWT_ALGORITHM == "HS256"
        assert s.JWT_EXPIRATION_MINUTES == 60

    def test_env_override(self):
        with patch.dict("os.environ", {"APP_ENV": "production", "DEBUG": "true"}):
            s = Settings()
            assert s.APP_ENV == "production"
            assert s.DEBUG is True


class TestGetSettings:
    def test_returns_settings_instance(self):
        result = get_settings()
        assert isinstance(result, Settings)

    def test_returns_same_instance(self):
        result = get_settings()
        assert result is settings
