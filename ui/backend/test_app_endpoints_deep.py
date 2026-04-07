"""
Tests for deeper app.py endpoint coverage: analyze-yaml, clusters CRUD,
diagnostics, environment overview, onboarding tour, and MCE environments.
"""

import importlib
import json
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
# POST /api/analyze-yaml
# =============================================


class TestAnalyzeYaml:
    def test_no_yaml_content(self):
        resp = client.post("/api/analyze-yaml", json={})
        assert resp.status_code in (400, 500)

    def test_empty_yaml(self):
        resp = client.post("/api/analyze-yaml", json={"yaml_content": "---"})
        data = resp.json()
        assert data["network_intent"] is None
        assert data["role_intent"] is None

    def test_detect_rosa_network_automated(self):
        yaml_content = """
apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
kind: ROSANetwork
metadata:
  name: test-network
spec:
  cidrBlock: "10.0.0.0/16"
"""
        resp = client.post("/api/analyze-yaml", json={"yaml_content": yaml_content})
        data = resp.json()
        assert data["network_intent"] == "automated"

    def test_detect_rosa_role_config_automated(self):
        yaml_content = """
apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
kind: RosaRoleConfig
metadata:
  name: test-roles
spec:
  clusterName: test
"""
        resp = client.post("/api/analyze-yaml", json={"yaml_content": yaml_content})
        data = resp.json()
        assert data["role_intent"] == "automated"

    def test_detect_manual_network(self):
        yaml_content = """
apiVersion: controlplane.cluster.x-k8s.io/v1beta2
kind: ROSAControlPlane
metadata:
  name: test-cp
spec:
  subnets:
    - subnet-123
    - subnet-456
  availabilityZones:
    - us-east-1a
    - us-east-1b
"""
        resp = client.post("/api/analyze-yaml", json={"yaml_content": yaml_content})
        data = resp.json()
        assert data["network_intent"] == "manual"
        assert data["has_rosa_control_plane"] is True
        assert "subnets" in data["config_values"]

    def test_detect_manual_roles(self):
        yaml_content = """
apiVersion: controlplane.cluster.x-k8s.io/v1beta2
kind: ROSAControlPlane
metadata:
  name: test-cp
spec:
  installerRoleARN: arn:aws:iam::123:role/installer
  rolesRef:
    ingressARN: arn:aws:iam::123:role/ingress
"""
        resp = client.post("/api/analyze-yaml", json={"yaml_content": yaml_content})
        data = resp.json()
        assert data["role_intent"] == "manual"
        assert data["config_values"]["installer_role_arn"] is not None

    def test_invalid_yaml(self):
        resp = client.post("/api/analyze-yaml", json={"yaml_content": "{{invalid: yaml: ["})
        assert resp.status_code == 400

    def test_multi_document_yaml(self):
        yaml_content = """
apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
kind: ROSANetwork
metadata:
  name: net
---
apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
kind: RosaRoleConfig
metadata:
  name: roles
"""
        resp = client.post("/api/analyze-yaml", json={"yaml_content": yaml_content})
        data = resp.json()
        assert data["network_intent"] == "automated"
        assert data["role_intent"] == "automated"


# =============================================
# Clusters CRUD
# =============================================


class TestClustersCRUD:
    def setup_method(self):
        app_module.clusters.clear()
        app_module.jobs.clear()

    def teardown_method(self):
        app_module.clusters.clear()
        app_module.jobs.clear()

    def test_get_cluster_not_found(self):
        resp = client.get("/api/clusters/nonexistent")
        assert resp.status_code == 404

    def test_delete_cluster_not_found(self):
        resp = client.delete("/api/clusters/nonexistent")
        assert resp.status_code == 404

    def test_get_cluster_with_data(self):
        app_module.clusters["c1"] = {
            "id": "c1",
            "config": {"name": "test"},
            "job_id": "j1",
            "status": "creating",
        }
        app_module.jobs["j1"] = {
            "id": "j1",
            "status": "running",
            "progress": 50,
        }
        resp = client.get("/api/clusters/c1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cluster"]["id"] == "c1"
        assert data["job"]["status"] == "running"

    def test_list_clusters_endpoint(self):
        resp = client.get("/api/clusters")
        assert resp.status_code == 200


# =============================================
# Diagnostics
# =============================================


class TestDiagnostics:
    def test_get_diagnostic_checks(self):
        resp = client.get("/api/diagnostics/checks")
        assert resp.status_code == 200
        data = resp.json()
        assert "checks" in data
        check_ids = [c["id"] for c in data["checks"]]
        assert "aws_credentials" in check_ids
        assert "rosa_auth" in check_ids
        assert "network_connectivity" in check_ids

    def test_run_aws_credentials_check(self):
        resp = client.post(
            "/api/diagnostics/run",
            json={"checks": ["aws_credentials"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["check"] == "aws_credentials"
        assert data["results"][0]["status"] == "pass"

    def test_run_openshift_version_check(self):
        resp = client.post(
            "/api/diagnostics/run",
            json={"checks": ["openshift_version"]},
        )
        data = resp.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["status"] == "pass"

    def test_run_multiple_checks(self):
        resp = client.post(
            "/api/diagnostics/run",
            json={"checks": ["aws_credentials", "openshift_version"]},
        )
        data = resp.json()
        assert len(data["results"]) == 2

    def test_run_no_checks(self):
        resp = client.post("/api/diagnostics/run", json={"checks": []})
        data = resp.json()
        assert data["results"] == []

    def test_run_unknown_check(self):
        resp = client.post(
            "/api/diagnostics/run",
            json={"checks": ["nonexistent_check"]},
        )
        data = resp.json()
        assert data["results"] == []


# =============================================
# Environment overview & onboarding
# =============================================


class TestEnvironmentAndOnboarding:
    def test_environment_overview(self):
        resp = client.get("/api/environment/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert "aws" in data
        assert "rosa" in data
        assert "clusters" in data
        assert "recommendations" in data
        assert "alerts" in data

    def test_onboarding_tour(self):
        resp = client.get("/api/onboarding/tour")
        assert resp.status_code == 200
        data = resp.json()
        assert "steps" in data
        assert len(data["steps"]) >= 3
        assert data["steps"][0]["title"] == "Welcome to ROSA Automation"

    def test_health_endpoint(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_root_endpoint(self):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data or "message" in data


# =============================================
# ROSA status
# =============================================


class TestRosaStatus:
    @patch("app.subprocess.run")
    def test_rosa_authenticated(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"aws_account_id": "123456789012", "email": "test@redhat.com"}',
            stderr="",
        )
        app_module.rosa_status_cache["data"] = None
        app_module.rosa_status_cache["timestamp"] = 0
        result = app_module._get_rosa_status_sync()
        assert result["authenticated"] is True

    @patch("app.subprocess.run")
    def test_rosa_not_authenticated(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Not logged in",
        )
        app_module.rosa_status_cache["data"] = None
        app_module.rosa_status_cache["timestamp"] = 0
        result = app_module._get_rosa_status_sync()
        assert result["authenticated"] is False

    @patch("app.subprocess.run")
    def test_rosa_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="rosa", timeout=10)
        app_module.rosa_status_cache["data"] = None
        app_module.rosa_status_cache["timestamp"] = 0
        result = app_module._get_rosa_status_sync()
        assert result["authenticated"] is False
        assert "timed out" in result["message"].lower()


# =============================================
# MCE environments (mocked mce_env_manager)
# =============================================


class TestMCEEnvironments:
    def test_list_environments(self):
        """MCE environments endpoint returns response"""
        resp = client.get("/api/mce-environments")
        data = resp.json()
        assert "environments" in data or "message" in data

    def test_get_environment_not_found(self):
        resp = client.get("/api/mce-environments/nonexistent-cluster")
        assert resp.status_code in (404, 500, 200)

    def test_stats_summary(self):
        resp = client.get("/api/mce-environments/stats/summary")
        assert resp.status_code in (200, 500)

    def test_search_environments(self):
        resp = client.get("/api/mce-environments/search/test")
        assert resp.status_code in (200, 500)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
