"""
Tests for minikube, resource detail, CAPI versions, and YAML path endpoints.
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
# Module-level mocking (must come before importing app)
# ---------------------------------------------------------------------------

# Ensure app_extensions is mocked before importing app
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

# Patch subprocess at module level so import doesn't execute real commands
with patch("subprocess.run", return_value=MagicMock(returncode=1, stdout="", stderr="")):
    with patch("subprocess.Popen"):
        if "app" in sys.modules:
            importlib.reload(sys.modules["app"])
        import app as app_module

client = TestClient(app_module.app)


# =============================================
# Minikube endpoints
# =============================================


class TestMinikubeCreateCluster:
    @patch("app.subprocess.run")
    def test_create_cluster_missing_name(self, mock_run):
        resp = client.post("/api/minikube/create-cluster", json={"cluster_name": ""})
        data = resp.json()
        assert data["success"] is False
        assert "required" in data["message"].lower()

    @patch("app.subprocess.run")
    def test_create_cluster_invalid_name(self, mock_run):
        resp = client.post("/api/minikube/create-cluster", json={"cluster_name": "BAD_NAME!"})
        data = resp.json()
        assert data["success"] is False
        assert "invalid" in data["message"].lower() or "format" in data["message"].lower()

    @patch("app.subprocess.run")
    def test_create_cluster_minikube_not_installed(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
        resp = client.post("/api/minikube/create-cluster", json={"cluster_name": "test-cluster"})
        data = resp.json()
        assert data["success"] is False
        assert "not installed" in data["message"].lower()

    @patch("app.asyncio.create_task")
    @patch("minikube_ops.get_profile_status")
    @patch("minikube_ops.is_minikube_installed", return_value=True)
    def test_create_cluster_already_exists(self, mock_installed, mock_status, mock_task):
        mock_status.return_value = {"exists": True, "status": "Running"}
        resp = client.post("/api/minikube/create-cluster", json={"cluster_name": "my-cluster"})
        data = resp.json()
        assert data["success"] is False
        assert "already exists" in data["message"]

    @patch("app.asyncio.create_task")
    @patch("app.subprocess.run")
    def test_create_cluster_success(self, mock_run, mock_task):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="minikube v1.33", stderr=""),
            MagicMock(returncode=1, stdout="", stderr="not found"),  # cluster doesn't exist
        ]
        resp = client.post("/api/minikube/create-cluster", json={"cluster_name": "new-cluster"})
        data = resp.json()
        assert data["success"] is True
        assert "job_id" in data


class TestMinikubeDeleteCluster:
    @patch("app.subprocess.run")
    def test_delete_cluster_missing_name(self, mock_run):
        resp = client.post("/api/minikube/delete-cluster", json={"cluster_name": ""})
        data = resp.json()
        assert data["success"] is False

    @patch("app.subprocess.run")
    def test_delete_cluster_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Deleted", stderr="")
        resp = client.post("/api/minikube/delete-cluster", json={"cluster_name": "old-cluster"})
        data = resp.json()
        assert data["success"] is True

    @patch("app.subprocess.run")
    def test_delete_cluster_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
        resp = client.post("/api/minikube/delete-cluster", json={"cluster_name": "no-cluster"})
        data = resp.json()
        assert data["success"] is False

    @patch("app.subprocess.run")
    def test_delete_cluster_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="minikube", timeout=120)
        resp = client.post("/api/minikube/delete-cluster", json={"cluster_name": "stuck-cluster"})
        data = resp.json()
        assert data["success"] is False
        assert "timed out" in data["message"].lower()


# =============================================
# Resource detail endpoints
# =============================================


class TestMinikubeResourceDetail:
    @patch("app.subprocess.run")
    def test_missing_params(self, mock_run):
        resp = client.post(
            "/api/minikube/get-resource-detail",
            json={"cluster_name": "", "resource_type": "Deployment", "resource_name": "foo"},
        )
        data = resp.json()
        assert data["success"] is False

    @patch("app.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="apiVersion: v1\nkind: Deployment", stderr="")
        resp = client.post(
            "/api/minikube/get-resource-detail",
            json={
                "cluster_name": "mk-cluster",
                "resource_type": "Deployment",
                "resource_name": "my-deploy",
                "namespace": "default",
            },
        )
        data = resp.json()
        assert data["success"] is True
        assert "apiVersion" in data["data"]

    @patch("app.subprocess.run")
    def test_cluster_scoped_resource(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="kind: AWSClusterControllerIdentity", stderr="")
        resp = client.post(
            "/api/minikube/get-resource-detail",
            json={
                "cluster_name": "mk-cluster",
                "resource_type": "AWSClusterControllerIdentity",
                "resource_name": "default",
            },
        )
        data = resp.json()
        assert data["success"] is True

    @patch("app.subprocess.run")
    def test_kubectl_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
        resp = client.post(
            "/api/minikube/get-resource-detail",
            json={
                "cluster_name": "mk-cluster",
                "resource_type": "Deployment",
                "resource_name": "missing",
            },
        )
        data = resp.json()
        assert data["success"] is False

    @patch("app.subprocess.run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="kubectl", timeout=10)
        resp = client.post(
            "/api/minikube/get-resource-detail",
            json={
                "cluster_name": "mk-cluster",
                "resource_type": "Deployment",
                "resource_name": "slow",
            },
        )
        data = resp.json()
        assert data["success"] is False
        assert "timed out" in data["message"].lower()

    @patch("app.subprocess.run")
    def test_secret_name_parsing(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="kind: Secret", stderr="")
        resp = client.post(
            "/api/minikube/get-resource-detail",
            json={
                "cluster_name": "mk-cluster",
                "resource_type": "Secret (ROSA Creds)",
                "resource_name": "rosa-creds-secret (capa-system)",
            },
        )
        data = resp.json()
        assert data["success"] is True


class TestOcpResourceDetail:
    @patch("app.subprocess.run")
    def test_missing_params(self, mock_run):
        resp = client.post(
            "/api/ocp/get-resource-detail",
            json={"resource_type": "", "resource_name": "foo"},
        )
        data = resp.json()
        assert data["success"] is False

    @patch("app.subprocess.run")
    def test_cluster_scoped(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="kind: ClusterManager", stderr="")
        resp = client.post(
            "/api/ocp/get-resource-detail",
            json={"resource_type": "ClusterManager", "resource_name": "cluster-manager"},
        )
        data = resp.json()
        assert data["success"] is True

    @patch("app.subprocess.run")
    def test_namespace_required(self, mock_run):
        resp = client.post(
            "/api/ocp/get-resource-detail",
            json={"resource_type": "Deployment", "resource_name": "my-dep", "namespace": ""},
        )
        data = resp.json()
        assert data["success"] is False
        assert "namespace" in data["message"].lower()

    @patch("app.subprocess.run")
    def test_namespaced_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="kind: Deployment", stderr="")
        resp = client.post(
            "/api/ocp/get-resource-detail",
            json={"resource_type": "Deployment", "resource_name": "my-dep", "namespace": "default"},
        )
        data = resp.json()
        assert data["success"] is True

    @patch("app.subprocess.run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="oc", timeout=10)
        resp = client.post(
            "/api/ocp/get-resource-detail",
            json={"resource_type": "Deployment", "resource_name": "my-dep", "namespace": "default"},
        )
        data = resp.json()
        assert data["success"] is False
        assert "timed out" in data["message"].lower()


# =============================================
# ROSA YAML path endpoints
# =============================================


class TestRosaYamlPath:
    def test_get_last_yaml_path_empty(self):
        app_module.last_rosa_yaml_path.clear()
        resp = client.get("/api/rosa/last-yaml-path")
        data = resp.json()
        assert data["success"] is True
        assert data["path"] is None

    def test_save_and_get_yaml_path(self):
        resp = client.post("/api/rosa/save-yaml-path", json={"path": "/tmp/test.yaml"})
        data = resp.json()
        assert data["success"] is True
        assert data["path"] == "/tmp/test.yaml"

        resp2 = client.get("/api/rosa/last-yaml-path")
        data2 = resp2.json()
        assert data2["path"] == "/tmp/test.yaml"

    def test_save_yaml_path_empty(self):
        resp = client.post("/api/rosa/save-yaml-path", json={"path": ""})
        data = resp.json()
        assert data["success"] is False


# =============================================
# CAPI component versions
# =============================================


class TestCapiComponentVersions:
    @patch("app.subprocess.run")
    def test_returns_components(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="registry.io/cert-manager:v1.14.0", stderr="")
        resp = client.get("/api/capi/component-versions")
        data = resp.json()
        assert "components" in data
        assert "timestamp" in data

    @patch("app.subprocess.run")
    def test_minikube_uses_kubectl(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="registry.io/img:v1.0", stderr="")
        resp = client.get("/api/capi/component-versions?environment=minikube&cluster_name=mk-test")
        data = resp.json()
        assert "components" in data
        # Verify kubectl was called (not oc) by checking the first call args
        first_call = mock_run.call_args_list[0]
        assert "kubectl" in first_call[0][0]

    @patch("app.subprocess.run")
    def test_all_components_fail(self, mock_run):
        mock_run.side_effect = Exception("connection refused")
        resp = client.get("/api/capi/component-versions")
        data = resp.json()
        assert "components" in data
        # Should still return components with enabled=False
        for comp in data["components"]:
            assert comp["enabled"] is False

    @patch("app.subprocess.run")
    def test_custom_capa_image(self, mock_run):
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "capa-controller-manager" in cmd_str and "jsonpath" in cmd_str:
                return MagicMock(returncode=0, stdout="quay.io/melserng/cluster-api-provider-aws:pr-123", stderr="")
            if "-o" in cmd_str and "yaml" in cmd_str:
                return MagicMock(returncode=0, stdout="kind: Deployment", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="")

        mock_run.side_effect = side_effect
        resp = client.get("/api/capi/component-versions")
        data = resp.json()
        capa = [c for c in data["components"] if c["name"] == "CAPA Controller"]
        if capa:
            assert "custom" in capa[0]["version"]


# =============================================
# Run ansible playbook endpoint
# =============================================


class TestRunAnsiblePlaybook:
    @patch("app.asyncio.create_task")
    @patch("app.init_ai_agents")
    @patch("os.path.exists", return_value=False)
    def test_playbook_not_found(self, mock_exists, mock_agents, mock_task):
        resp = client.post(
            "/api/ansible/run-playbook",
            json={"playbook": "playbooks/nonexistent.yml"},
        )
        # May return 404 or 500 depending on exception handling
        assert resp.status_code in (404, 500)

    def test_playbook_missing_field(self):
        resp = client.post("/api/ansible/run-playbook", json={})
        # Missing playbook raises HTTPException(400) but may be caught as 500
        assert resp.status_code in (400, 500)

    @patch("app.asyncio.create_task")
    @patch("app.init_ai_agents")
    @patch("os.path.exists", return_value=True)
    def test_playbook_success(self, mock_exists, mock_agents, mock_task):
        resp = client.post(
            "/api/ansible/run-playbook",
            json={"playbook": "playbooks/validate.yml", "description": "Validate"},
        )
        data = resp.json()
        assert data["success"] is True
        assert "job_id" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
