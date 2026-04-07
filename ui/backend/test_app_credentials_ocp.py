"""
Tests for credentials POST, OCP connection status, and notification settings endpoints.
"""

import importlib
import json
import os
import subprocess
import sys
from datetime import datetime
from unittest.mock import MagicMock, mock_open, patch

import pytest

# ---------------------------------------------------------------------------
# Module-level mocking
# ---------------------------------------------------------------------------

if "app_extensions" in sys.modules:
    if isinstance(sys.modules["app_extensions"], MagicMock):
        del sys.modules["app_extensions"]

sys.modules.setdefault(
    "app_extensions",
    MagicMock(
        register_health_endpoints=MagicMock(),
        register_monitoring_endpoints=MagicMock(),
    ),
)
sys.modules.setdefault("anthropic", MagicMock())

from fastapi.testclient import TestClient

with patch("subprocess.run", return_value=MagicMock(returncode=1, stdout="", stderr="")):
    with patch("subprocess.Popen"):
        if "app" in sys.modules:
            importlib.reload(sys.modules["app"])
        import app as app_module

client = TestClient(app_module.app)


# =============================================
# POST /api/credentials
# =============================================


class TestSaveCredentials:
    def test_save_credentials_success(self):
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data="")), \
             patch("yaml.safe_load", return_value={}), \
             patch("yaml.dump"):
            resp = client.post(
                "/api/credentials",
                json={
                    "credentials": {
                        "OCP_HUB_API_URL": "https://api.test.com:6443",
                        "OCP_HUB_CLUSTER_USER": "kubeadmin",
                    }
                },
            )
            data = resp.json()
            assert data["success"] is True

    def test_save_credentials_new_file(self):
        with patch("os.path.exists", return_value=False), \
             patch("builtins.open", mock_open()), \
             patch("yaml.dump"):
            resp = client.post(
                "/api/credentials",
                json={"credentials": {"AWS_REGION": "us-west-2"}},
            )
            data = resp.json()
            assert data["success"] is True


# =============================================
# OCP connection status
# =============================================


class TestOcpConnectionStatus:
    @patch("os.path.exists", return_value=False)
    def test_config_missing(self, mock_exists):
        app_module.ocp_status_cache["data"] = None
        app_module.ocp_status_cache["timestamp"] = 0
        result = app_module._get_ocp_connection_status_sync()
        assert result["connected"] is False
        assert result["status"] == "config_missing"

    @patch("builtins.open", mock_open(read_data="OCP_HUB_API_URL: https://api.your-cluster.example.com:6443\nOCP_HUB_CLUSTER_USER: your-username\nOCP_HUB_CLUSTER_PASSWORD: your-password\n"))
    @patch("os.path.exists", return_value=True)
    def test_placeholder_credentials(self, mock_exists):
        app_module.ocp_status_cache["data"] = None
        app_module.ocp_status_cache["timestamp"] = 0
        result = app_module._get_ocp_connection_status_sync()
        assert result["connected"] is False
        assert result["status"] == "placeholder_credentials"

    @patch("builtins.open", mock_open(read_data="OCP_HUB_API_URL: ''\nOCP_HUB_CLUSTER_USER: kubeadmin\nOCP_HUB_CLUSTER_PASSWORD: secret\n"))
    @patch("os.path.exists", return_value=True)
    def test_missing_api_url(self, mock_exists):
        app_module.ocp_status_cache["data"] = None
        app_module.ocp_status_cache["timestamp"] = 0
        result = app_module._get_ocp_connection_status_sync()
        assert result["connected"] is False
        assert result["status"] == "missing_api_url"

    @patch("builtins.open", mock_open(read_data="OCP_HUB_API_URL: https://api.test.com:6443\nOCP_HUB_CLUSTER_USER: ''\nOCP_HUB_CLUSTER_PASSWORD: ''\n"))
    @patch("os.path.exists", return_value=True)
    def test_missing_credentials(self, mock_exists):
        app_module.ocp_status_cache["data"] = None
        app_module.ocp_status_cache["timestamp"] = 0
        result = app_module._get_ocp_connection_status_sync()
        assert result["connected"] is False
        assert result["status"] == "missing_credentials"

    @patch("app.subprocess.run")
    @patch("builtins.open", mock_open(read_data="OCP_HUB_API_URL: https://api.test.com:6443\nOCP_HUB_CLUSTER_USER: kubeadmin\nOCP_HUB_CLUSTER_PASSWORD: secret123\n"))
    @patch("os.path.exists", return_value=True)
    def test_login_success(self, mock_exists, mock_run):
        app_module.ocp_status_cache["data"] = None
        app_module.ocp_status_cache["timestamp"] = 0
        mock_run.return_value = MagicMock(returncode=0, stdout="Login successful", stderr="")
        result = app_module._get_ocp_connection_status_sync()
        assert result["connected"] is True
        assert result["status"] == "connected"

    @patch("app.subprocess.run")
    @patch("builtins.open", mock_open(read_data="OCP_HUB_API_URL: https://api.test.com:6443\nOCP_HUB_CLUSTER_USER: kubeadmin\nOCP_HUB_CLUSTER_PASSWORD: secret123\n"))
    @patch("os.path.exists", return_value=True)
    def test_login_failure(self, mock_exists, mock_run):
        app_module.ocp_status_cache["data"] = None
        app_module.ocp_status_cache["timestamp"] = 0
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Unauthorized")
        result = app_module._get_ocp_connection_status_sync()
        assert result["connected"] is False

    @patch("app.subprocess.run")
    @patch("builtins.open", mock_open(read_data="OCP_HUB_API_URL: https://api.test.com:6443\nOCP_HUB_CLUSTER_USER: kubeadmin\nOCP_HUB_CLUSTER_PASSWORD: secret123\n"))
    @patch("os.path.exists", return_value=True)
    def test_login_timeout(self, mock_exists, mock_run):
        app_module.ocp_status_cache["data"] = None
        app_module.ocp_status_cache["timestamp"] = 0
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="oc", timeout=30)
        result = app_module._get_ocp_connection_status_sync()
        assert result["connected"] is False
        assert "timed out" in result["message"].lower()

    def test_cache_hit(self):
        import time

        app_module.ocp_status_cache["data"] = {
            "connected": True,
            "status": "connected",
            "message": "cached",
        }
        app_module.ocp_status_cache["timestamp"] = time.time()
        app_module.ocp_status_cache["ttl"] = 60
        result = app_module._get_ocp_connection_status_sync()
        assert result["connected"] is True
        assert result["message"] == "cached"
        # Reset
        app_module.ocp_status_cache["data"] = None
        app_module.ocp_status_cache["timestamp"] = 0


# =============================================
# Notification settings
# =============================================


class TestNotificationSettings:
    def test_get_notification_settings(self):
        resp = client.get("/api/notification-settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "settings" in data

    def test_save_notification_settings(self):
        resp = client.post(
            "/api/notification-settings",
            json={
                "email_enabled": True,
                "smtp_server": "smtp.test.com",
                "smtp_port": 587,
                "from_email": "test@test.com",
                "to_emails": ["user@test.com"],
                "notify_on_failure": True,
            },
        )
        assert resp.status_code == 200


# =============================================
# /api/onboarding/status and /api/guided-setup
# =============================================


class TestOnboardingEndpoints:
    def test_guided_setup_status(self):
        resp = client.get("/api/guided-setup/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "steps" in data or "status" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
