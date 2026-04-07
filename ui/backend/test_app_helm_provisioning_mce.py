"""
Tests for provisioning apply-yaml and MCE environment save/status endpoints.
"""

import importlib
import json
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
# POST /api/provisioning/apply-yaml
# =============================================


class TestProvisioningApplyYaml:
    def test_missing_yaml_content(self):
        resp = client.post("/api/provisioning/apply-yaml", json={
            "cluster_name": "test-cluster",
        })
        # HTTPException raised — returns 400 or 500
        assert resp.status_code in (400, 500)

    def test_missing_cluster_name(self):
        resp = client.post("/api/provisioning/apply-yaml", json={
            "yaml_content": "apiVersion: v1\nkind: ConfigMap\n",
        })
        assert resp.status_code in (400, 500)

    @patch("app.asyncio.create_task")
    @patch("app.init_ai_agents")
    @patch("os.makedirs")
    @patch("builtins.open", mock_open())
    def test_apply_success(self, mock_makedirs, mock_agents, mock_task):
        yaml_content = "apiVersion: v1\nkind: RosaControlPlane\nmetadata:\n  name: test\n"
        resp = client.post("/api/provisioning/apply-yaml", json={
            "yaml_content": yaml_content,
            "cluster_name": "test-cluster",
            "feature_type": "combined",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "pending"
        # Clean up
        if data.get("job_id") and data["job_id"] in app_module.jobs:
            del app_module.jobs[data["job_id"]]

    @patch("app.asyncio.create_task")
    @patch("app.init_ai_agents")
    @patch("os.makedirs")
    @patch("builtins.open", mock_open())
    def test_apply_with_cluster_context(self, mock_makedirs, mock_agents, mock_task):
        resp = client.post("/api/provisioning/apply-yaml", json={
            "yaml_content": "apiVersion: v1\nkind: ConfigMap\n",
            "cluster_name": "test-cluster",
            "cluster_context": "sat-minikube",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        # Clean up
        if data.get("job_id") and data["job_id"] in app_module.jobs:
            del app_module.jobs[data["job_id"]]

    @patch("app.asyncio.create_task")
    @patch("app.init_ai_agents")
    @patch("os.makedirs")
    @patch("builtins.open", mock_open())
    def test_apply_job_entry_created(self, mock_makedirs, mock_agents, mock_task):
        resp = client.post("/api/provisioning/apply-yaml", json={
            "yaml_content": "apiVersion: v1\nkind: ConfigMap\n",
            "cluster_name": "apply-test",
        })
        data = resp.json()
        job_id = data["job_id"]
        assert job_id in app_module.jobs
        job = app_module.jobs[job_id]
        assert "apply-test" in job["description"]
        del app_module.jobs[job_id]


# =============================================
# POST /api/mce-environments (save)
# =============================================


class TestMCEEnvironmentSave:
    def test_save_new_environment(self):
        mock_manager = MagicMock()
        mock_manager.get_environment.return_value = None
        mock_manager.add_environment.return_value = True

        with patch.dict("sys.modules", {"mce_env_manager": MagicMock(
            MCEEnvManager=MagicMock(return_value=mock_manager)
        )}):
            resp = client.post("/api/mce-environments", json={
                "clusterName": "test-cluster",
                "apiUrl": "https://api.test-cluster.example.com:6443",
                "platform": "AWS",
                "ocpVersion": "4.20.12",
                "mceVersion": "2.8.0",
            })
        data = resp.json()
        assert data["success"] is True
        assert data["clusterName"] == "test-cluster"

    def test_save_existing_environment(self):
        mock_manager = MagicMock()
        mock_manager.get_environment.return_value = {"name": "test-cluster"}

        with patch.dict("sys.modules", {"mce_env_manager": MagicMock(
            MCEEnvManager=MagicMock(return_value=mock_manager)
        )}):
            resp = client.post("/api/mce-environments", json={
                "clusterName": "test-cluster",
                "apiUrl": "https://api.test-cluster.example.com:6443",
            })
        data = resp.json()
        assert data["success"] is True
        assert "already exists" in data["message"]

    def test_save_extracts_name_from_url(self):
        mock_manager = MagicMock()
        mock_manager.get_environment.return_value = None
        mock_manager.add_environment.return_value = True

        with patch.dict("sys.modules", {"mce_env_manager": MagicMock(
            MCEEnvManager=MagicMock(return_value=mock_manager)
        )}):
            resp = client.post("/api/mce-environments", json={
                "apiUrl": "https://api.qe6-vmware.install.dev09.com:6443",
            })
        data = resp.json()
        assert data["success"] is True
        assert data["clusterName"] == "qe6-vmware"

    def test_save_no_name_no_url(self):
        mock_manager = MagicMock()
        mock_manager.get_environment.return_value = None

        with patch.dict("sys.modules", {"mce_env_manager": MagicMock(
            MCEEnvManager=MagicMock(return_value=mock_manager)
        )}):
            resp = client.post("/api/mce-environments", json={
                "apiUrl": "invalid-url",
            })
        data = resp.json()
        assert data["success"] is False


# =============================================
# POST /api/mce-environments/{cluster_name}/status
# =============================================


class TestMCEEnvironmentStatus:
    def test_invalid_status(self):
        with patch.dict("sys.modules", {"mce_env_manager": MagicMock(
            MCEEnvManager=MagicMock(return_value=MagicMock())
        )}):
            resp = client.post("/api/mce-environments/test-cluster/status", json={
                "status": "invalid_status",
            })
        assert resp.status_code == 400

    def test_valid_status_update(self):
        mock_manager = MagicMock()
        mock_manager.update_status.return_value = True

        with patch.dict("sys.modules", {"mce_env_manager": MagicMock(
            MCEEnvManager=MagicMock(return_value=mock_manager)
        )}):
            resp = client.post("/api/mce-environments/test-cluster/status", json={
                "status": "pass",
                "notes": "All tests passed",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_environment_not_found(self):
        mock_manager = MagicMock()
        mock_manager.update_status.return_value = False

        with patch.dict("sys.modules", {"mce_env_manager": MagicMock(
            MCEEnvManager=MagicMock(return_value=mock_manager)
        )}):
            resp = client.post("/api/mce-environments/nonexistent/status", json={
                "status": "fail",
            })
        assert resp.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
