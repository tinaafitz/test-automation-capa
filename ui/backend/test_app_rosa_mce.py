"""
Tests for ROSA clusters sync, validation, test suites list, and MCE environment endpoints.
"""

import importlib
import json
import os
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
# _get_rosa_clusters_sync
# =============================================


class TestGetRosaClustersSync:
    @patch("app.subprocess.run")
    def test_rosa_cli_success_with_clusters(self, mock_run):
        rosa_output = json.dumps([
            {
                "name": "my-cluster",
                "state": "ready",
                "region": {"id": "us-west-2"},
                "creation_timestamp": "2026-04-01T10:00:00Z",
                "openshift_version": "4.20.12",
            },
            {
                "name": "installing-cluster",
                "state": "installing",
                "region": {"id": "us-east-1"},
                "creation_timestamp": "2026-04-07T08:00:00Z",
                "openshift_version": "4.20.11",
            },
        ])
        mock_run.return_value = MagicMock(returncode=0, stdout=rosa_output, stderr="")
        result = app_module._get_rosa_clusters_sync()
        assert result["success"] is True
        assert len(result["clusters"]) == 2
        assert result["clusters"][0]["name"] == "my-cluster"
        assert result["clusters"][0]["status"] == "ready"
        assert result["clusters"][0]["region"] == "us-west-2"
        assert result["clusters"][1]["status"] == "installing"

    @patch("app.subprocess.run")
    def test_rosa_cli_empty_list(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
        result = app_module._get_rosa_clusters_sync()
        assert result["success"] is True
        assert result["clusters"] == []
        assert result["count"] == 0

    @patch("app.subprocess.run")
    def test_rosa_cli_invalid_json_fallback(self, mock_run):
        # First call (rosa CLI) returns invalid JSON, second call (oc fallback) returns empty
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="not json", stderr=""),
            MagicMock(returncode=0, stdout='{"items": []}', stderr=""),
        ]
        result = app_module._get_rosa_clusters_sync()
        assert result["success"] is True
        assert result["clusters"] == []

    @patch("app.subprocess.run")
    def test_rosa_cli_failure_oc_fallback(self, mock_run):
        # rosa CLI fails, oc fallback returns a RosaControlPlane
        rcp_data = {
            "items": [
                {
                    "metadata": {
                        "name": "fallback-cluster",
                        "namespace": "ns-rosa-hcp",
                        "creationTimestamp": "2026-04-01T10:00:00Z",
                    },
                    "spec": {"region": "us-west-2", "version": "4.20.12"},
                    "status": {"ready": True, "conditions": []},
                }
            ]
        }
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="not logged in"),
            MagicMock(returncode=0, stdout=json.dumps(rcp_data), stderr=""),
        ]
        result = app_module._get_rosa_clusters_sync()
        assert result["success"] is True
        assert len(result["clusters"]) == 1
        assert result["clusters"][0]["name"] == "fallback-cluster"
        assert result["clusters"][0]["status"] == "ready"

    @patch("app.subprocess.run")
    def test_rosa_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="rosa", timeout=5)
        result = app_module._get_rosa_clusters_sync()
        assert result["success"] is False
        assert "timed out" in result["message"].lower()

    @patch("app.subprocess.run")
    def test_rosa_region_as_string(self, mock_run):
        rosa_output = json.dumps([
            {
                "name": "string-region",
                "state": "ready",
                "region": "eu-west-1",
                "creation_timestamp": "2026-04-01T10:00:00Z",
                "openshift_version": "4.20.12",
            },
        ])
        mock_run.return_value = MagicMock(returncode=0, stdout=rosa_output, stderr="")
        result = app_module._get_rosa_clusters_sync()
        assert result["success"] is True
        assert result["clusters"][0]["region"] == "eu-west-1"

    @patch("app.subprocess.run")
    def test_oc_fallback_deleting_cluster(self, mock_run):
        rcp_data = {
            "items": [
                {
                    "metadata": {
                        "name": "deleting-cluster",
                        "namespace": "ns-rosa-hcp",
                        "creationTimestamp": "2026-04-01T10:00:00Z",
                        "deletionTimestamp": "2026-04-07T10:00:00Z",
                    },
                    "spec": {"region": "us-west-2", "version": "4.20.12"},
                    "status": {"ready": False, "conditions": []},
                }
            ]
        }
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="err"),
            MagicMock(returncode=0, stdout=json.dumps(rcp_data), stderr=""),
        ]
        result = app_module._get_rosa_clusters_sync()
        assert result["success"] is True
        # Deleting clusters are filtered out (only ready clusters returned)
        assert len(result["clusters"]) == 0

    @patch("app.subprocess.run")
    def test_oc_fallback_failed_cluster(self, mock_run):
        rcp_data = {
            "items": [
                {
                    "metadata": {
                        "name": "failed-cluster",
                        "namespace": "ns-rosa-hcp",
                        "creationTimestamp": "2026-04-01T10:00:00Z",
                    },
                    "spec": {"region": "us-west-2", "version": "4.20.12"},
                    "status": {
                        "ready": False,
                        "conditions": [
                            {
                                "type": "Ready",
                                "status": "False",
                                "reason": "ProvisioningFailed",
                                "message": "Cluster creation failed",
                            }
                        ],
                    },
                }
            ]
        }
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="err"),
            MagicMock(returncode=0, stdout=json.dumps(rcp_data), stderr=""),
        ]
        result = app_module._get_rosa_clusters_sync()
        assert result["success"] is True
        # Failed clusters are filtered out (only ready clusters returned)
        assert len(result["clusters"]) == 0


# =============================================
# /api/validate
# =============================================


class TestValidateConfig:
    def test_valid_config(self):
        resp = client.post(
            "/api/validate",
            json={"name": "test-cluster", "version": "4.20.12", "min_replicas": 1, "max_replicas": 3},
        )
        data = resp.json()
        assert data["valid"] is True
        assert len(data["errors"]) == 0

    def test_invalid_name(self):
        resp = client.post(
            "/api/validate",
            json={"name": "bad name!", "version": "4.20.12", "min_replicas": 1, "max_replicas": 3},
        )
        data = resp.json()
        assert data["valid"] is False
        assert any("alphanumeric" in e for e in data["errors"])

    def test_long_name_warning(self):
        resp = client.post(
            "/api/validate",
            json={"name": "a-very-long-cluster-name", "version": "4.20.12", "min_replicas": 1, "max_replicas": 3},
        )
        data = resp.json()
        assert data["valid"] is True
        assert any("15 characters" in w for w in data["warnings"])

    def test_min_greater_than_max(self):
        resp = client.post(
            "/api/validate",
            json={"name": "test", "version": "4.20.12", "min_replicas": 5, "max_replicas": 2},
        )
        data = resp.json()
        assert data["valid"] is False
        assert any("Min replicas" in e for e in data["errors"])

    def test_non_420_version_warning(self):
        resp = client.post(
            "/api/validate",
            json={"name": "test", "version": "4.19.5", "min_replicas": 1, "max_replicas": 3},
        )
        data = resp.json()
        assert data["valid"] is True
        assert any("4.20" in w for w in data["warnings"])


# =============================================
# /api/test-suites/list
# =============================================


class TestTestSuitesList:
    @patch("os.path.exists", return_value=False)
    def test_no_directory(self, mock_exists):
        resp = client.get("/api/test-suites/list")
        data = resp.json()
        assert data["success"] is True
        assert data["suites"] == []

    @patch("os.listdir", return_value=["01-validate.json", "02-provision.json"])
    @patch("os.path.exists", return_value=True)
    @patch(
        "builtins.open",
        side_effect=[
            MagicMock(
                __enter__=lambda s: s,
                __exit__=lambda *a: None,
                read=lambda: '{"name": "Validate", "description": "Validate env"}',
            ),
            MagicMock(
                __enter__=lambda s: s,
                __exit__=lambda *a: None,
                read=lambda: '{"name": "Provision", "description": "Provision cluster"}',
            ),
        ],
    )
    def test_lists_suites(self, mock_open, mock_exists, mock_listdir):
        # Use a simpler approach - test the endpoint directly
        resp = client.get("/api/test-suites/list")
        data = resp.json()
        assert data["success"] is True


# =============================================
# /api/build/templates and /api/user/profile
# =============================================


class TestStaticEndpoints:
    def test_build_templates(self):
        resp = client.get("/api/build/templates")
        data = resp.json()
        assert "templates" in data
        assert len(data["templates"]) == 3
        template_ids = [t["id"] for t in data["templates"]]
        assert "development" in template_ids
        assert "production" in template_ids
        assert "learning" in template_ids

    def test_user_profile(self):
        resp = client.get("/api/user/profile")
        data = resp.json()
        assert "permissions" in data
        assert "quotas" in data
        assert "recent_activity" in data


# =============================================
# MCE environment endpoints
# =============================================


class TestMceEnvironments:
    @patch("app.subprocess.run")
    def test_get_mce_yaml_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="apiVersion: v1\nkind: Deployment", stderr=""
        )
        resp = client.get("/api/mce/yaml")
        data = resp.json()
        assert data["success"] is True
        assert "apiVersion" in data["yaml"]

    @patch("app.subprocess.run")
    def test_get_mce_yaml_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
        resp = client.get("/api/mce/yaml")
        data = resp.json()
        assert data["success"] is False

    @patch("app.subprocess.run")
    def test_get_mce_yaml_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="oc", timeout=30)
        resp = client.get("/api/mce/yaml")
        data = resp.json()
        assert data["success"] is False
        assert "timed out" in data["message"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
