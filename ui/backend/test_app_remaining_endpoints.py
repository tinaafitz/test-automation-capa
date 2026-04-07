"""
Tests for remaining untested endpoints: ansible run-role, minikube verify-cluster,
helm test logs, and helm test status.
"""

import importlib
import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

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
# POST /api/ansible/run-role
# =============================================


class TestAnsibleRunRole:
    def test_missing_role_name(self):
        resp = client.post("/api/ansible/run-role", json={})
        assert resp.status_code in (400, 500)

    @patch("os.path.exists", return_value=False)
    def test_role_not_found(self, mock_exists):
        resp = client.post("/api/ansible/run-role", json={
            "role_name": "nonexistent-role",
        })
        assert resp.status_code in (404, 500)


# =============================================
# POST /api/minikube/verify-cluster
# =============================================


class TestMinikubeVerifyCluster:
    def test_missing_name(self):
        resp = client.post("/api/minikube/verify-cluster", json={"cluster_name": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is False
        assert data["accessible"] is False

    @patch("app.subprocess.run")
    def test_minikube_not_installed(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
        resp = client.post("/api/minikube/verify-cluster", json={
            "cluster_name": "test-cluster",
        })
        data = resp.json()
        assert data["exists"] is False
        assert "not installed" in data["message"].lower()

    @patch("app.subprocess.run")
    def test_cluster_does_not_exist(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="v1.33.0"),  # minikube version
            MagicMock(returncode=1, stdout="", stderr="not found"),  # minikube status
        ]
        resp = client.post("/api/minikube/verify-cluster", json={
            "cluster_name": "nonexistent",
        })
        data = resp.json()
        assert data["exists"] is False

    @patch("app.subprocess.run")
    def test_cluster_exists_not_running(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="v1.33.0"),  # minikube version
            MagicMock(returncode=0, stdout=json.dumps({"Host": "Stopped", "Driver": "docker"})),
        ]
        resp = client.post("/api/minikube/verify-cluster", json={
            "cluster_name": "stopped-cluster",
        })
        data = resp.json()
        assert data["exists"] is True
        assert data["accessible"] is False

    @patch("app.subprocess.run")
    def test_cluster_running_accessible(self, mock_run):
        version_json = json.dumps({
            "serverVersion": {"gitVersion": "v1.30.0"},
        })

        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
            if "minikube" in cmd_str and "version" in cmd_str:
                return MagicMock(returncode=0, stdout="v1.33.0")
            if "minikube" in cmd_str and "status" in cmd_str:
                return MagicMock(returncode=0, stdout=json.dumps({"Host": "Running", "Driver": "docker"}))
            if "cluster-info" in cmd_str:
                return MagicMock(returncode=0, stdout="Kubernetes control plane is running")
            if "kubectl" in cmd_str and "version" in cmd_str:
                return MagicMock(returncode=0, stdout=version_json)
            return MagicMock(returncode=1, stdout="", stderr="not found")

        mock_run.side_effect = side_effect
        resp = client.post("/api/minikube/verify-cluster", json={
            "cluster_name": "sat-minikube",
        })
        data = resp.json()
        assert data["exists"] is True
        assert data["accessible"] is True


# =============================================
# GET /api/helm-tests/status
# =============================================


class TestHelmTestStatus:
    @patch("app.sqlite3.connect")
    def test_empty_database(self, mock_connect):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        resp = client.get("/api/helm-tests/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "matrix" in data

    @patch("app.sqlite3.connect")
    def test_with_results(self, mock_connect):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("capi", "OpenShift", "install", "passed", 120, 100, "2026-04-01T10:00:00", "helm_repo", None, "helm_repo"),
        ]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        resp = client.get("/api/helm-tests/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        matrix = data["matrix"]
        assert "capi" in matrix


# =============================================
# GET /api/helm-tests/logs/{provider}/{environment}/{test_type}
# =============================================


class TestHelmTestLogs:
    @patch("app.sqlite3.connect")
    def test_logs_found(self, mock_connect):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            "passed", 120, 100, None, "All tests passed", "2026-04-01T10:00:00"
        )
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        resp = client.get("/api/helm-tests/logs/capi/OpenShift/install")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["status"] == "passed"

    @patch("app.sqlite3.connect")
    def test_logs_not_found(self, mock_connect):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        resp = client.get("/api/helm-tests/logs/capi/OpenShift/install")
        data = resp.json()
        assert data["success"] is False


# =============================================
# GET /api/test-suites/status/{run_id}
# =============================================


class TestTestSuiteStatus:
    def test_run_not_found(self):
        resp = client.get("/api/test-suites/status/nonexistent-id")
        assert resp.status_code == 404


# =============================================
# POST /api/notification-settings/test
# =============================================


class TestNotificationTest:
    def test_test_notification_email(self):
        resp = client.post("/api/notification-settings/test", json={
            "type": "email",
            "config": {
                "smtp_server": "smtp.example.com",
                "smtp_port": 587,
                "sender_email": "test@example.com",
                "recipient_email": "user@example.com",
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        # May succeed or fail depending on config, but should not crash
        assert "success" in data or "message" in data

    def test_test_notification_slack(self):
        resp = client.post("/api/notification-settings/test", json={
            "type": "slack",
            "config": {
                "webhook_url": "https://hooks.slack.com/test",
            },
        })
        assert resp.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
