"""
Tests for cluster listing/status, ROSA yaml path, log forwarding config,
test suites list/history, minikube active profile, and resource details endpoints.
"""

import importlib
import json
import os
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
# GET /api/clusters (kubectl-based)
# =============================================


class TestListClusters:
    @patch("app.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "items": [
                    {
                        "metadata": {
                            "name": "test-cluster",
                            "namespace": "ns-rosa-hcp",
                            "creationTimestamp": "2026-04-01T10:00:00Z",
                        },
                        "spec": {
                            "domainPrefix": "test",
                            "version": "4.20.12",
                            "region": "us-west-2",
                        },
                        "status": {
                            "ready": True,
                            "conditions": [],
                            "consoleURL": "https://console.test.com",
                        },
                    }
                ]
            }),
            stderr="",
        )
        resp = client.get("/api/clusters")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["clusters"]) == 1
        assert data["clusters"][0]["name"] == "test-cluster"
        assert data["clusters"][0]["status"] == "ready"

    @patch("app.subprocess.run")
    def test_kubectl_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="connection refused"
        )
        resp = client.get("/api/clusters")
        data = resp.json()
        assert data["success"] is False
        assert data["clusters"] == []

    @patch("app.subprocess.run")
    def test_deleting_cluster(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "items": [
                    {
                        "metadata": {
                            "name": "del-cluster",
                            "namespace": "ns-rosa-hcp",
                            "creationTimestamp": "2026-04-01T10:00:00Z",
                            "deletionTimestamp": "2026-04-02T10:00:00Z",
                        },
                        "spec": {"version": "4.20.12", "region": "us-west-2"},
                        "status": {"ready": False, "conditions": []},
                    }
                ]
            }),
            stderr="",
        )
        resp = client.get("/api/clusters")
        data = resp.json()
        assert data["clusters"][0]["status"] == "deleting"

    @patch("app.subprocess.run")
    def test_provisioning_cluster_with_progress(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "items": [
                    {
                        "metadata": {
                            "name": "prov-cluster",
                            "namespace": "ns-rosa-hcp",
                            "creationTimestamp": "2026-04-01T10:00:00Z",
                        },
                        "spec": {"version": "4.20.12", "region": "us-west-2"},
                        "status": {
                            "ready": False,
                            "conditions": [
                                {"type": "ROSANetworkReady", "status": "True"},
                                {"type": "ROSARoleConfigReady", "status": "True"},
                                {"type": "ROSAControlPlaneValid", "status": "False"},
                            ],
                        },
                    }
                ]
            }),
            stderr="",
        )
        resp = client.get("/api/clusters")
        data = resp.json()
        cluster = data["clusters"][0]
        assert cluster["status"] == "provisioning"
        assert cluster["progress"] == 50  # NetworkReady + RoleConfigReady


# =============================================
# GET /api/clusters/{cluster_name}/status
# =============================================


class TestClusterStatus:
    @patch("app.subprocess.run")
    def test_cluster_found(self, mock_run):
        cp_json = json.dumps({
            "metadata": {"name": "test"},
            "spec": {"version": "4.20.12"},
            "status": {"ready": True},
        })
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=cp_json, stderr=""),
            MagicMock(returncode=1, stdout="", stderr="not found"),  # network
            MagicMock(returncode=1, stdout="", stderr="not found"),  # role
        ]
        resp = client.get("/api/clusters/test/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["network"] is None

    @patch("app.subprocess.run")
    def test_cluster_not_found(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
        resp = client.get("/api/clusters/nonexistent/status")
        assert resp.status_code == 404


# =============================================
# GET /api/rosa/last-yaml-path
# POST /api/rosa/save-yaml-path
# =============================================


class TestRosaYamlPath:
    def test_get_last_yaml_path(self):
        resp = client.get("/api/rosa/last-yaml-path")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_save_yaml_path(self):
        resp = client.post(
            "/api/rosa/save-yaml-path",
            json={"path": "/tmp/test.yaml"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["path"] == "/tmp/test.yaml"

    def test_save_empty_path(self):
        resp = client.post(
            "/api/rosa/save-yaml-path",
            json={"path": ""},
        )
        data = resp.json()
        assert data["success"] is False


# =============================================
# GET /api/provisioning/log-forwarding-config/{cluster_name}
# =============================================


class TestLogForwardingConfig:
    @patch("os.path.exists", return_value=False)
    def test_config_not_found(self, mock_exists):
        resp = client.get("/api/provisioning/log-forwarding-config/my-cluster")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is False

    @patch("builtins.open", mock_open(read_data="cloudwatch_log_group_name: my-log-group\ncloudwatch_log_role_arn: arn:aws:iam::123:role/log\n"))
    @patch("os.path.exists", return_value=True)
    def test_config_found(self, mock_exists):
        resp = client.get("/api/provisioning/log-forwarding-config/my-cluster")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["cloudwatch_log_group_name"] == "my-log-group"


# =============================================
# GET /api/test-suites/list
# =============================================


class TestTestSuitesList:
    @patch("os.listdir")
    @patch("os.path.exists", return_value=True)
    def test_list_suites(self, mock_exists, mock_listdir):
        mock_listdir.return_value = ["01-verify.json", "02-provision.json"]
        suite_data = json.dumps({"name": "Verify", "playbooks": []})
        with patch("builtins.open", mock_open(read_data=suite_data)):
            resp = client.get("/api/test-suites/list")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 2

    @patch("os.path.exists", return_value=False)
    def test_no_suites_directory(self, mock_exists):
        resp = client.get("/api/test-suites/list")
        data = resp.json()
        assert data["success"] is True
        assert data["suites"] == []


# =============================================
# GET /api/test-suites/history
# =============================================


class TestTestSuiteHistory:
    def test_empty_history(self):
        resp = client.get("/api/test-suites/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["runs"], list)


# =============================================
# GET /api/minikube/active-profile
# =============================================


class TestMinikubeActiveProfile:
    @patch("app.subprocess.run")
    def test_active_profile_found(self, mock_run):
        profiles_json = json.dumps({
            "valid": [{"Name": "sat-minikube"}],
        })
        status_json = json.dumps({"Host": "Running"})
        cluster_info = "Kubernetes control plane is running at https://192.168.49.2:8443"

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=profiles_json, stderr=""),
            MagicMock(returncode=0, stdout=status_json, stderr=""),
            MagicMock(returncode=0, stdout=cluster_info, stderr=""),
        ]
        resp = client.get("/api/minikube/active-profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["profile"]["name"] == "sat-minikube"

    @patch("app.subprocess.run")
    def test_no_profiles(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="no profiles")
        resp = client.get("/api/minikube/active-profile")
        data = resp.json()
        assert data["success"] is False
        assert data["profile"] is None

    @patch("app.subprocess.run")
    def test_no_running_profile(self, mock_run):
        profiles_json = json.dumps({"valid": [{"Name": "stopped-cluster"}]})
        status_json = json.dumps({"Host": "Stopped"})
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=profiles_json, stderr=""),
            MagicMock(returncode=0, stdout=status_json, stderr=""),
        ]
        resp = client.get("/api/minikube/active-profile")
        data = resp.json()
        assert data["success"] is False


# =============================================
# GET /api/aws/resource-details/{resource_type}
# =============================================


class TestAWSResourceDetails:
    @patch("app.subprocess.run")
    def test_nat_gateways_details(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "NatGateways": [
                    {
                        "NatGatewayId": "nat-123",
                        "State": "available",
                        "VpcId": "vpc-abc",
                        "CreateTime": "2026-04-01T00:00:00Z",
                        "Tags": [{"Key": "Name", "Value": "test-nat"}],
                        "NatGatewayAddresses": [{"PublicIp": "1.2.3.4"}],
                    }
                ]
            }),
            stderr="",
        )
        resp = client.get("/api/aws/resource-details/nat_gateways")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    @patch("app.subprocess.run")
    def test_resource_command_fails(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        resp = client.get("/api/aws/resource-details/nat_gateways")
        assert resp.status_code == 200
        data = resp.json()
        # Should still return, possibly with empty details or error
        assert "success" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
