"""
Tests for MCE resources, MCE YAML, ROSA clusters, minikube resource detail,
OCP resource detail, and CAPI component versions endpoints.
"""

import importlib
import json
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
# GET /api/mce/yaml
# =============================================


class TestMCEYaml:
    @patch("app.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="apiVersion: multicluster.openshift.io/v1\nkind: MultiClusterEngine\n",
            stderr="",
        )
        resp = client.get("/api/mce/yaml")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "MultiClusterEngine" in data["yaml"]

    @patch("app.subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="not connected"
        )
        resp = client.get("/api/mce/yaml")
        data = resp.json()
        assert data["success"] is False
        assert data["yaml"] is None

    @patch("app.subprocess.run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="oc", timeout=30)
        resp = client.get("/api/mce/yaml")
        data = resp.json()
        assert data["success"] is False
        assert "timed out" in data["message"]


# =============================================
# GET /api/mce/resources
# =============================================


class TestMCEResources:
    @patch("app.subprocess.run")
    def test_success_with_resources(self, mock_run):
        resource_json = json.dumps({
            "items": [
                {
                    "metadata": {"name": "test-identity", "namespace": "capa-system"},
                    "spec": {},
                }
            ]
        })
        yaml_content = "apiVersion: v1\nkind: AWSClusterControllerIdentity\n"
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=resource_json, stderr=""),
            MagicMock(returncode=0, stdout=yaml_content, stderr=""),
            # Remaining resource types return empty
            MagicMock(returncode=0, stdout=json.dumps({"items": []}), stderr=""),
            MagicMock(returncode=0, stdout=json.dumps({"items": []}), stderr=""),
            MagicMock(returncode=0, stdout=json.dumps({"items": []}), stderr=""),
            MagicMock(returncode=0, stdout=json.dumps({"items": []}), stderr=""),
        ]
        resp = client.get("/api/mce/resources")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["count"] >= 1

    @patch("app.subprocess.run")
    def test_all_fail(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        resp = client.get("/api/mce/resources")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 0


# =============================================
# GET /api/rosa/clusters
# =============================================


class TestROSAClusters:
    @patch("app.subprocess.run")
    def test_rosa_cli_success(self, mock_run):
        rosa_json = json.dumps([
            {
                "name": "e2e-test",
                "state": "ready",
                "region": {"id": "us-west-2"},
                "creation_timestamp": "2026-04-01T10:00:00Z",
                "openshift_version": "4.20.12",
            }
        ])
        mock_run.return_value = MagicMock(
            returncode=0, stdout=rosa_json, stderr=""
        )
        resp = client.get("/api/rosa/clusters")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["clusters"]) == 1
        assert data["clusters"][0]["name"] == "e2e-test"
        assert data["clusters"][0]["status"] == "ready"
        assert data["clusters"][0]["progress"] == 100

    @patch("app.subprocess.run")
    def test_rosa_cli_fails_fallback_to_oc(self, mock_run):
        oc_json = json.dumps({
            "items": [
                {
                    "metadata": {
                        "name": "fallback-cluster",
                        "namespace": "ns-rosa-hcp",
                        "creationTimestamp": "2026-04-01T10:00:00Z",
                    },
                    "spec": {"version": "4.20.12", "region": "us-west-2"},
                    "status": {"ready": True, "conditions": []},
                }
            ]
        })
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="rosa not found"),
            MagicMock(returncode=0, stdout=oc_json, stderr=""),
        ]
        resp = client.get("/api/rosa/clusters")
        data = resp.json()
        assert data["success"] is True
        assert len(data["clusters"]) >= 1

    @patch("app.subprocess.run")
    def test_both_fail(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        resp = client.get("/api/rosa/clusters")
        data = resp.json()
        assert data["success"] is False
        assert data["clusters"] == []


# =============================================
# POST /api/minikube/get-resource-detail
# =============================================


class TestMinikubeResourceDetail:
    @patch("app.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="apiVersion: v1\nkind: ROSAControlPlane\nmetadata:\n  name: test\n",
            stderr="",
        )
        resp = client.post("/api/minikube/get-resource-detail", json={
            "cluster_name": "sat-minikube",
            "resource_type": "RosaControlPlane",
            "resource_name": "test-cp",
            "namespace": "ns-rosa-hcp",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "ROSAControlPlane" in data["data"]

    @patch("app.subprocess.run")
    def test_missing_fields(self, mock_run):
        resp = client.post("/api/minikube/get-resource-detail", json={
            "cluster_name": "",
            "resource_type": "",
            "resource_name": "",
        })
        data = resp.json()
        assert data["success"] is False

    @patch("app.subprocess.run")
    def test_resource_not_found(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="not found"
        )
        resp = client.post("/api/minikube/get-resource-detail", json={
            "cluster_name": "sat-minikube",
            "resource_type": "RosaControlPlane",
            "resource_name": "nonexistent",
        })
        data = resp.json()
        assert data["success"] is False

    @patch("app.subprocess.run")
    def test_cluster_scoped_resource(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="apiVersion: v1\nkind: AWSClusterControllerIdentity\n",
            stderr="",
        )
        resp = client.post("/api/minikube/get-resource-detail", json={
            "cluster_name": "sat-minikube",
            "resource_type": "AWSClusterControllerIdentity",
            "resource_name": "default",
        })
        data = resp.json()
        assert data["success"] is True


# =============================================
# POST /api/ocp/get-resource-detail
# =============================================


class TestOCPResourceDetail:
    @patch("app.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="apiVersion: v1\nkind: ROSANetwork\n",
            stderr="",
        )
        resp = client.post("/api/ocp/get-resource-detail", json={
            "resource_type": "ROSANetwork",
            "resource_name": "test-network",
            "namespace": "ns-rosa-hcp",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    @patch("app.subprocess.run")
    def test_missing_fields(self, mock_run):
        resp = client.post("/api/ocp/get-resource-detail", json={
            "resource_type": "",
            "resource_name": "",
        })
        data = resp.json()
        assert data["success"] is False


# =============================================
# GET /api/capi/component-versions
# =============================================


class TestCAPIComponentVersions:
    @patch("app.subprocess.run")
    def test_all_found(self, mock_run):
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
            if "cert-manager" in cmd_str and "jsonpath" in cmd_str:
                return MagicMock(returncode=0, stdout="quay.io/cert-manager:v1.14.0")
            if "cert-manager" in cmd_str and "yaml" in cmd_str:
                return MagicMock(returncode=0, stdout="kind: Deployment\n")
            if "capi-controller-manager" in cmd_str and "jsonpath" in cmd_str:
                return MagicMock(returncode=0, stdout="registry.k8s.io/capi:v1.7.0")
            if "capi-controller-manager" in cmd_str and "yaml" in cmd_str:
                return MagicMock(returncode=0, stdout="kind: Deployment\n")
            if "capa-controller-manager" in cmd_str and "jsonpath" in cmd_str:
                return MagicMock(returncode=0, stdout="registry.k8s.io/capa:v2.6.0")
            if "capa-controller-manager" in cmd_str and "yaml" in cmd_str:
                return MagicMock(returncode=0, stdout="kind: Deployment\n")
            return MagicMock(returncode=1, stdout="", stderr="not found")

        mock_run.side_effect = side_effect
        resp = client.get("/api/capi/component-versions")
        assert resp.status_code == 200
        data = resp.json()
        assert "components" in data
        assert len(data["components"]) >= 1

    @patch("app.subprocess.run")
    def test_none_found(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
        resp = client.get("/api/capi/component-versions")
        assert resp.status_code == 200
        data = resp.json()
        assert "components" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
