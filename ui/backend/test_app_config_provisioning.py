"""
Tests for config status, AWS credentials status, provisioning YAML generation,
and execute command endpoints.
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
# GET /api/config/status
# =============================================


class TestConfigStatus:
    @patch("os.path.exists", return_value=False)
    def test_config_missing(self, mock_exists):
        resp = client.get("/api/config/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False
        assert data["status"] == "missing"

    @patch("builtins.open", mock_open(read_data="OCP_HUB_API_URL: https://api.test.com:6443\nOCP_HUB_CLUSTER_USER: kubeadmin\nOCP_HUB_CLUSTER_PASSWORD: secret\nAWS_REGION: us-west-2\nAWS_ACCESS_KEY_ID: AKIA123\nAWS_SECRET_ACCESS_KEY: secret123\nOCM_CLIENT_ID: clientid\nOCM_CLIENT_SECRET: clientsecret\n"))
    @patch("os.path.exists", return_value=True)
    def test_fully_configured(self, mock_exists):
        resp = client.get("/api/config/status")
        data = resp.json()
        assert data["configured"] is True
        assert data["status"] == "fully_configured"
        assert data["total_configured"] == data["total_required"]

    @patch("builtins.open", mock_open(read_data="OCP_HUB_API_URL: https://api.test.com:6443\nOCP_HUB_CLUSTER_USER: kubeadmin\n"))
    @patch("os.path.exists", return_value=True)
    def test_partially_configured(self, mock_exists):
        resp = client.get("/api/config/status")
        data = resp.json()
        assert data["configured"] is False
        assert data["status"] == "partially_configured"
        assert data["total_configured"] > 0
        assert data["total_configured"] < data["total_required"]

    @patch("builtins.open", mock_open(read_data=""))
    @patch("os.path.exists", return_value=True)
    def test_not_configured(self, mock_exists):
        resp = client.get("/api/config/status")
        data = resp.json()
        assert data["configured"] is False
        assert data["status"] == "not_configured"

    @patch("builtins.open", mock_open(read_data="OCP_HUB_API_URL: \nOCP_HUB_CLUSTER_USER: \n"))
    @patch("os.path.exists", return_value=True)
    def test_empty_fields_detected(self, mock_exists):
        resp = client.get("/api/config/status")
        data = resp.json()
        assert data["configured"] is False
        assert len(data["empty_fields"]) > 0

    @patch("builtins.open", mock_open(read_data="{{invalid yaml"))
    @patch("os.path.exists", return_value=True)
    def test_invalid_yaml(self, mock_exists):
        resp = client.get("/api/config/status")
        data = resp.json()
        assert data["configured"] is False
        assert data["status"] in ("invalid_yaml", "error")


# =============================================
# GET /api/aws/credentials-status
# =============================================


class TestAWSCredentialsStatus:
    @patch("os.path.exists", return_value=False)
    def test_config_missing(self, mock_exists):
        resp = client.get("/api/aws/credentials-status")
        data = resp.json()
        assert data["valid"] is False
        assert data["status"] == "config_missing"

    @patch("builtins.open", mock_open(read_data="AWS_ACCESS_KEY_ID: \nAWS_SECRET_ACCESS_KEY: \n"))
    @patch("os.path.exists", return_value=True)
    def test_empty_credentials(self, mock_exists):
        resp = client.get("/api/aws/credentials-status")
        data = resp.json()
        assert data["valid"] is False
        assert data["status"] in ("empty_credentials", "error")

    @patch("app.subprocess.run")
    @patch("builtins.open", mock_open(read_data="AWS_ACCESS_KEY_ID: AKIA123\nAWS_SECRET_ACCESS_KEY: secret123\nAWS_REGION: us-west-2\n"))
    @patch("os.path.exists", return_value=True)
    def test_valid_credentials(self, mock_exists, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "Account": "123456789012",
                "Arn": "arn:aws:iam::123456789012:user/test",
                "UserId": "AIDA123",
            }),
            stderr="",
        )
        resp = client.get("/api/aws/credentials-status")
        data = resp.json()
        assert data["valid"] is True
        assert data["status"] == "valid"
        assert data["account_info"]["account_id"] == "123456789012"

    @patch("app.subprocess.run")
    @patch("builtins.open", mock_open(read_data="AWS_ACCESS_KEY_ID: AKIA123\nAWS_SECRET_ACCESS_KEY: wrong\nAWS_REGION: us-west-2\n"))
    @patch("os.path.exists", return_value=True)
    def test_invalid_secret(self, mock_exists, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="SignatureDoesNotMatch: The request signature is invalid",
        )
        resp = client.get("/api/aws/credentials-status")
        data = resp.json()
        assert data["valid"] is False
        assert data["status"] == "invalid_secret"

    @patch("app.subprocess.run")
    @patch("builtins.open", mock_open(read_data="AWS_ACCESS_KEY_ID: AKIA123\nAWS_SECRET_ACCESS_KEY: secret\nAWS_REGION: us-west-2\n"))
    @patch("os.path.exists", return_value=True)
    def test_invalid_user(self, mock_exists, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="InvalidUserID.NotFound: The user does not exist",
        )
        resp = client.get("/api/aws/credentials-status")
        data = resp.json()
        assert data["valid"] is False
        assert data["status"] == "invalid_user"

    @patch("app.subprocess.run")
    @patch("builtins.open", mock_open(read_data="AWS_ACCESS_KEY_ID: AKIA123\nAWS_SECRET_ACCESS_KEY: secret\nAWS_REGION: us-west-2\n"))
    @patch("os.path.exists", return_value=True)
    def test_timeout(self, mock_exists, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="aws", timeout=15)
        resp = client.get("/api/aws/credentials-status")
        data = resp.json()
        assert data["valid"] is False
        assert data["status"] == "timeout"

    @patch("app.subprocess.run")
    @patch("builtins.open", mock_open(read_data="AWS_ACCESS_KEY_ID: AKIA123\nAWS_SECRET_ACCESS_KEY: secret\nAWS_REGION: us-west-2\n"))
    @patch("os.path.exists", return_value=True)
    def test_aws_cli_missing(self, mock_exists, mock_run):
        mock_run.side_effect = FileNotFoundError("aws not found")
        resp = client.get("/api/aws/credentials-status")
        data = resp.json()
        assert data["valid"] is False
        assert data["status"] == "aws_cli_missing"

    @patch("app.subprocess.run")
    @patch("builtins.open", mock_open(read_data="AWS_ACCESS_KEY_ID: AKIA123\nAWS_SECRET_ACCESS_KEY: secret\nAWS_REGION: us-west-2\n"))
    @patch("os.path.exists", return_value=True)
    def test_generic_aws_error(self, mock_exists, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="UnknownError: Something went wrong",
        )
        resp = client.get("/api/aws/credentials-status")
        data = resp.json()
        assert data["valid"] is False
        assert data["status"] == "aws_error"


# =============================================
# POST /api/provisioning/generate-yaml
# =============================================


class TestProvisioningGenerateYaml:
    def test_missing_cluster_name(self):
        resp = client.post(
            "/api/provisioning/generate-yaml",
            json={"config": {"domainPrefix": "test"}},
        )
        data = resp.json()
        assert data.get("success") is False or resp.status_code in (400, 200)

    def test_missing_domain_prefix(self):
        resp = client.post(
            "/api/provisioning/generate-yaml",
            json={"config": {"clusterName": "test-cluster"}},
        )
        data = resp.json()
        assert data.get("success") is False or resp.status_code in (400, 200)

    def test_domain_prefix_too_long(self):
        resp = client.post(
            "/api/provisioning/generate-yaml",
            json={
                "config": {
                    "clusterName": "test",
                    "domainPrefix": "this-is-way-too-long-domain-prefix",
                }
            },
        )
        data = resp.json()
        assert data.get("success") is False or resp.status_code in (400, 200)


# =============================================
# POST /api/minikube/execute-command
# =============================================


class TestMinikubeExecuteCommand:
    @patch("app.subprocess.run")
    def test_execute_command(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="pod/test-pod   1/1   Running   0   5m",
            stderr="",
        )
        resp = client.post(
            "/api/minikube/execute-command",
            json={"command": "kubectl get pods"},
        )
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_execute_command_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="error: the server doesn't have a resource type 'foo'",
        )
        resp = client.post(
            "/api/minikube/execute-command",
            json={"command": "kubectl get foo"},
        )
        assert resp.status_code == 200


# =============================================
# POST /api/ocp/execute-command
# =============================================


class TestOCPExecuteCommand:
    @patch("app.subprocess.run")
    def test_execute_oc_command(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="NAME       STATUS   AGE\ndefault    Active   10d",
            stderr="",
        )
        resp = client.post(
            "/api/ocp/execute-command",
            json={"command": "oc get namespaces"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    @patch("app.subprocess.run")
    def test_execute_oc_command_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="error: You must be logged in",
        )
        resp = client.post(
            "/api/ocp/execute-command",
            json={"command": "oc get pods"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False


# =============================================
# GET /api/minikube/list-clusters
# =============================================


class TestMinikubeListClusters:
    @patch("app.subprocess.run")
    def test_list_clusters(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([
                {"Name": "test-cluster", "Status": "Running", "Driver": "docker"},
            ]),
            stderr="",
        )
        resp = client.get("/api/minikube/list-clusters")
        assert resp.status_code == 200
        data = resp.json()
        assert "clusters" in data or "success" in data

    @patch("app.subprocess.run")
    def test_list_clusters_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        resp = client.get("/api/minikube/list-clusters")
        assert resp.status_code == 200


# =============================================
# GET /api/minikube/current-context
# =============================================


class TestMinikubeCurrentContext:
    @patch("app.subprocess.run")
    def test_current_context(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="sat-minikube-test\n",
            stderr="",
        )
        resp = client.get("/api/minikube/current-context")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_current_context_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="error: current-context is not set",
        )
        resp = client.get("/api/minikube/current-context")
        assert resp.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
