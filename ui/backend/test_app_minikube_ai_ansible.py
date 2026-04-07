"""
Tests for minikube create/delete cluster, AI assistant chat (fallback mode),
ansible run-playbook, minikube get-active-resources, and get-resource-detail endpoints.
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
# POST /api/minikube/create-cluster
# =============================================


class TestMinikubeCreateCluster:
    def test_missing_name(self):
        resp = client.post("/api/minikube/create-cluster", json={"cluster_name": ""})
        data = resp.json()
        assert data["success"] is False
        assert "required" in data["message"].lower()

    def test_invalid_name(self):
        resp = client.post(
            "/api/minikube/create-cluster",
            json={"cluster_name": "Invalid_Name!"},
        )
        data = resp.json()
        assert data["success"] is False
        assert "invalid" in data["message"].lower()

    @patch("app.subprocess.run")
    def test_minikube_not_installed(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
        resp = client.post(
            "/api/minikube/create-cluster",
            json={"cluster_name": "test-cluster"},
        )
        data = resp.json()
        assert data["success"] is False
        assert "not installed" in data["message"].lower()

    @patch("app.asyncio.create_task")
    @patch("app.subprocess.run")
    def test_cluster_already_exists(self, mock_run, mock_task):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="v1.33.0"),  # minikube version
            MagicMock(returncode=0, stdout="Running"),  # minikube status (exists)
        ]
        resp = client.post(
            "/api/minikube/create-cluster",
            json={"cluster_name": "existing-cluster"},
        )
        data = resp.json()
        assert data["success"] is False
        assert "already exists" in data["message"].lower()

    @patch("app.asyncio.create_task")
    @patch("app.subprocess.run")
    def test_create_success(self, mock_run, mock_task):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="v1.33.0"),  # minikube version
            MagicMock(returncode=1, stdout="", stderr="not running"),  # minikube status
        ]
        resp = client.post(
            "/api/minikube/create-cluster",
            json={"cluster_name": "new-cluster"},
        )
        data = resp.json()
        assert data["success"] is True
        assert "job_id" in data


# =============================================
# POST /api/minikube/delete-cluster
# =============================================


class TestMinikubeDeleteCluster:
    def test_missing_name(self):
        resp = client.post("/api/minikube/delete-cluster", json={"cluster_name": ""})
        data = resp.json()
        assert data["success"] is False

    @patch("app.subprocess.run")
    def test_delete_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Deleting cluster...", stderr=""
        )
        resp = client.post(
            "/api/minikube/delete-cluster",
            json={"cluster_name": "old-cluster"},
        )
        data = resp.json()
        assert data["success"] is True

    @patch("app.subprocess.run")
    def test_delete_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="cluster not found"
        )
        resp = client.post(
            "/api/minikube/delete-cluster",
            json={"cluster_name": "nonexistent"},
        )
        data = resp.json()
        assert data["success"] is False

    @patch("app.subprocess.run")
    def test_delete_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="minikube", timeout=120)
        resp = client.post(
            "/api/minikube/delete-cluster",
            json={"cluster_name": "stuck-cluster"},
        )
        data = resp.json()
        assert data["success"] is False
        assert "timed out" in data["message"].lower()


# =============================================
# POST /api/ai-assistant/chat (fallback mode)
# =============================================


class TestAIAssistantChat:
    @patch.dict("os.environ", {}, clear=False)
    def test_cluster_query_with_data(self):
        # Remove ANTHROPIC_API_KEY if present
        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)

        resp = client.post("/api/ai-assistant/chat", json={
            "message": "what clusters are running?",
            "context": {
                "clusters": [
                    {"name": "e2e-test", "namespace": "ns-rosa-hcp", "status": "ready"},
                ]
            },
            "history": [],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data
        assert "e2e-test" in data["response"]

    @patch.dict("os.environ", {}, clear=False)
    def test_cluster_query_no_clusters(self):
        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)

        resp = client.post("/api/ai-assistant/chat", json={
            "message": "what clusters are running?",
            "context": {"clusters": []},
            "history": [],
        })
        data = resp.json()
        assert "response" in data

    @patch.dict("os.environ", {}, clear=False)
    def test_help_query(self):
        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)

        resp = client.post("/api/ai-assistant/chat", json={
            "message": "help",
            "context": {},
            "history": [],
        })
        data = resp.json()
        assert "response" in data

    @patch.dict("os.environ", {}, clear=False)
    def test_generic_query(self):
        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)

        resp = client.post("/api/ai-assistant/chat", json={
            "message": "how do I provision a cluster?",
            "context": {},
            "history": [],
        })
        data = resp.json()
        assert "response" in data


# =============================================
# POST /api/ansible/run-playbook
# =============================================


class TestAnsibleRunPlaybook:
    def test_missing_playbook(self):
        resp = client.post("/api/ansible/run-playbook", json={})
        assert resp.status_code in (400, 500)

    @patch("os.path.exists", return_value=False)
    def test_playbook_not_found(self, mock_exists):
        resp = client.post("/api/ansible/run-playbook", json={
            "playbook": "playbooks/nonexistent.yml",
        })
        assert resp.status_code in (404, 500)

    @patch("app.asyncio.create_task")
    @patch("app.init_ai_agents")
    @patch("os.path.exists", return_value=True)
    def test_playbook_queued(self, mock_exists, mock_init, mock_task):
        resp = client.post("/api/ansible/run-playbook", json={
            "playbook": "playbooks/verify.yml",
            "description": "Verify environment",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "job_id" in data


# =============================================
# POST /api/minikube/get-active-resources
# =============================================


class TestMinikubeGetActiveResources:
    @patch("app.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "items": [
                    {
                        "kind": "ROSAControlPlane",
                        "metadata": {
                            "name": "test-cp",
                            "namespace": "ns-rosa-hcp",
                            "creationTimestamp": "2026-04-01T10:00:00Z",
                        },
                        "spec": {"version": "4.20.12"},
                        "status": {"ready": True, "conditions": []},
                    }
                ]
            }),
            stderr="",
        )
        resp = client.post("/api/minikube/get-active-resources", json={
            "cluster_name": "sat-minikube",
            "namespace": "ns-rosa-hcp",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["resources"]) >= 1
        # Find our ROSAControlPlane in the results
        cp_resources = [r for r in data["resources"] if r.get("type") == "ROSAControlPlane"]
        assert len(cp_resources) >= 1
        assert cp_resources[0]["status"] == "Ready"

    def test_missing_cluster_name(self):
        resp = client.post("/api/minikube/get-active-resources", json={
            "cluster_name": "",
        })
        data = resp.json()
        assert data["success"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
