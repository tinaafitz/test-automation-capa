"""
Tests for app_extensions.py — production health and monitoring endpoints.
"""

import importlib
import sys
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Mock dependencies
sys.modules.setdefault("anthropic", MagicMock())

# If app_extensions was previously mocked (e.g. by test_app.py),
# remove the mock so we can import the real module
if "app_extensions" in sys.modules and isinstance(sys.modules["app_extensions"], MagicMock):
    del sys.modules["app_extensions"]

import app_extensions
importlib.reload(app_extensions)
from app_extensions import add_production_endpoints


@pytest.fixture
def ext_app():
    """Create a FastAPI app with production endpoints added."""
    test_app = FastAPI()
    with patch("app_extensions.init_sentry", return_value=False):
        add_production_endpoints(test_app)
    return TestClient(test_app)


class TestProductionEndpoints:
    def test_health_basic(self, ext_app):
        resp = ext_app.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    @patch("app_extensions.check_system_health", new_callable=AsyncMock)
    def test_health_detailed_healthy(self, mock_health, ext_app):
        mock_health.return_value = {"status": "healthy", "components": {}}
        resp = ext_app.get("/health/detailed")
        assert resp.status_code == 200

    @patch("app_extensions.check_system_health", new_callable=AsyncMock)
    def test_health_detailed_unhealthy(self, mock_health, ext_app):
        mock_health.return_value = {"status": "unhealthy", "components": {}}
        resp = ext_app.get("/health/detailed")
        assert resp.status_code == 503

    @patch("app_extensions.check_readiness", new_callable=AsyncMock)
    def test_readiness_ready(self, mock_ready, ext_app):
        mock_ready.return_value = {"ready": True}
        resp = ext_app.get("/health/ready")
        assert resp.status_code == 200

    @patch("app_extensions.check_readiness", new_callable=AsyncMock)
    def test_readiness_not_ready(self, mock_ready, ext_app):
        mock_ready.return_value = {"ready": False}
        resp = ext_app.get("/health/ready")
        assert resp.status_code == 503

    @patch("app_extensions.check_liveness", new_callable=AsyncMock)
    def test_liveness(self, mock_live, ext_app):
        mock_live.return_value = {"alive": True}
        resp = ext_app.get("/health/live")
        assert resp.status_code == 200

    @patch("app_extensions.get_metrics", new_callable=AsyncMock)
    def test_metrics(self, mock_metrics, ext_app):
        mock_metrics.return_value = {"cpu": 0.5, "memory": 100}
        resp = ext_app.get("/metrics")
        assert resp.status_code == 200

    def test_version(self, ext_app):
        resp = ext_app.get("/api/version")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "environment" in data


class TestAddProductionEndpointsReturnValue:
    def test_returns_app(self):
        test_app = FastAPI()
        with patch("app_extensions.init_sentry", return_value=False):
            result = add_production_endpoints(test_app)
        assert result is test_app
