"""
Tests for deeper coverage of app.py: ansible run-task, cluster deletion,
minikube initialize-capi, MCE features, notification settings CRUD,
and provisioning YAML generation validation.
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
# POST /api/ansible/run-task
# =============================================


class TestAnsibleRunTask:
    def test_missing_both_task_and_playbook(self):
        resp = client.post("/api/ansible/run-task", json={
            "description": "test task",
        })
        assert resp.status_code in (400, 500)

    @patch("app.asyncio.create_task")
    def test_with_task_file(self, mock_task):
        resp = client.post("/api/ansible/run-task", json={
            "task_file": "tasks/validate-capa-environment.yml",
            "description": "Validate CAPA",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "job_id" in data
        assert data["status"] == "running"

    @patch("app.asyncio.create_task")
    def test_with_playbook_file(self, mock_task):
        resp = client.post("/api/ansible/run-task", json={
            "playbook_file": "playbooks/verify.yml",
            "description": "Verify environment",
        })
        data = resp.json()
        assert data["success"] is True
        assert "job_id" in data

    @patch("app.asyncio.create_task")
    def test_with_extra_vars(self, mock_task):
        resp = client.post("/api/ansible/run-task", json={
            "task_file": "tasks/test.yml",
            "extra_vars": {"cluster_name": "test-cluster"},
            "kube_context": "minikube",
            "cluster_type": "minikube",
        })
        data = resp.json()
        assert data["success"] is True

    @patch("app.asyncio.create_task")
    def test_job_created_in_jobs_dict(self, mock_task):
        resp = client.post("/api/ansible/run-task", json={
            "task_file": "tasks/test.yml",
            "description": "Test task",
        })
        data = resp.json()
        job_id = data["job_id"]
        assert job_id in app_module.jobs
        assert app_module.jobs[job_id]["status"] == "running"
        assert app_module.jobs[job_id]["description"] == "Test task"
        # Clean up
        del app_module.jobs[job_id]


# =============================================
# DELETE /api/rosa/clusters/{cluster_name}
# =============================================


class TestDeleteRosaCluster:
    @patch("app.asyncio.create_task")
    @patch("app.init_ai_agents")
    def test_missing_namespace(self, mock_agents, mock_task):
        resp = client.request(
            "DELETE",
            "/api/rosa/clusters/test-cluster",
            content=json.dumps({"namespace": ""}),
        )
        data = resp.json()
        assert data["success"] is False
        assert "namespace" in data["message"].lower()

    @patch("app.asyncio.create_task")
    @patch("app.init_ai_agents")
    def test_delete_success(self, mock_agents, mock_task):
        resp = client.request(
            "DELETE",
            "/api/rosa/clusters/e2e-test",
            content=json.dumps({"namespace": "ns-rosa-hcp"}),
        )
        data = resp.json()
        assert data["success"] is True
        assert "job_id" in data
        assert "e2e-test" in data["message"]
        # Clean up job
        if data["job_id"] in app_module.jobs:
            del app_module.jobs[data["job_id"]]

    @patch("app.asyncio.create_task")
    @patch("app.init_ai_agents")
    def test_job_entry_created(self, mock_agents, mock_task):
        resp = client.request(
            "DELETE",
            "/api/rosa/clusters/test-del",
            content=json.dumps({"namespace": "ns-rosa-hcp"}),
        )
        data = resp.json()
        job_id = data["job_id"]
        assert job_id in app_module.jobs
        job = app_module.jobs[job_id]
        assert job["status"] == "running"
        assert "test-del" in job["description"]
        # Clean up
        del app_module.jobs[job_id]


# =============================================
# POST /api/minikube/initialize-capi
# =============================================


class TestMinikubeInitializeCapi:
    def test_missing_cluster_name(self):
        resp = client.post("/api/minikube/initialize-capi", json={
            "cluster_name": "",
        })
        data = resp.json()
        assert data["success"] is False
        assert "required" in data["message"].lower()

    def test_invalid_install_method(self):
        resp = client.post("/api/minikube/initialize-capi", json={
            "cluster_name": "test-cluster",
            "install_method": "invalid",
        })
        data = resp.json()
        assert data["success"] is False
        assert "invalid install method" in data["message"].lower()

    def test_custom_image_invalid_type(self):
        resp = client.post("/api/minikube/initialize-capi", json={
            "cluster_name": "test-cluster",
            "install_method": "clusterctl",
            "custom_capa_image": "not-a-dict",
        })
        data = resp.json()
        assert data["success"] is False
        assert "object" in data["message"].lower()

    def test_custom_image_missing_fields(self):
        resp = client.post("/api/minikube/initialize-capi", json={
            "cluster_name": "test-cluster",
            "install_method": "clusterctl",
            "custom_capa_image": {"repository": "quay.io/test"},
        })
        data = resp.json()
        assert data["success"] is False
        assert "tag" in data["message"].lower()

    @patch("app.asyncio.create_task")
    @patch("os.path.exists", return_value=True)
    def test_clusterctl_success(self, mock_exists, mock_task):
        resp = client.post("/api/minikube/initialize-capi", json={
            "cluster_name": "sat-minikube",
            "install_method": "clusterctl",
        })
        data = resp.json()
        assert data["success"] is True
        assert "job_id" in data
        assert "clusterctl" in data["message"].lower()
        # Clean up
        if data["job_id"] in app_module.jobs:
            del app_module.jobs[data["job_id"]]

    @patch("os.path.exists", return_value=False)
    def test_playbook_not_found(self, mock_exists):
        resp = client.post("/api/minikube/initialize-capi", json={
            "cluster_name": "sat-minikube",
            "install_method": "clusterctl",
        })
        data = resp.json()
        assert data["success"] is False
        assert "not found" in data["message"].lower()

    @patch("app.asyncio.create_task")
    @patch("os.path.exists", return_value=True)
    def test_custom_image_clusterctl(self, mock_exists, mock_task):
        resp = client.post("/api/minikube/initialize-capi", json={
            "cluster_name": "sat-minikube",
            "install_method": "clusterctl",
            "custom_capa_image": {
                "repository": "quay.io/test/capa",
                "tag": "pr-123",
            },
        })
        data = resp.json()
        assert data["success"] is True
        assert "Custom Image" in app_module.jobs[data["job_id"]]["description"]
        # Clean up
        del app_module.jobs[data["job_id"]]


# =============================================
# GET /api/mce/features
# =============================================


class TestMCEFeatures:
    @patch("app.subprocess.run")
    def test_success_with_features(self, mock_run):
        mce_json = json.dumps({
            "items": [{
                "metadata": {"name": "multiclusterengine"},
                "spec": {
                    "overrides": {
                        "components": [
                            {"name": "cluster-api", "enabled": True},
                            {"name": "cluster-api-provider-aws", "enabled": True},
                        ]
                    }
                },
                "status": {
                    "phase": "Available",
                    "currentVersion": "2.8.0",
                },
            }]
        })

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=mce_json, stderr=""),
            # CRD checks
            MagicMock(returncode=0, stdout="", stderr=""),  # ROSANetwork CRD
            MagicMock(returncode=0, stdout="", stderr=""),  # ROSARoleConfig CRD
        ]

        resp = client.get("/api/mce/features")
        assert resp.status_code == 200
        data = resp.json()
        assert "features" in data
        assert data["mce_info"]["status"] == "Available"
        assert data["mce_info"]["version"] == "2.8.0"

    @patch("app.subprocess.run")
    def test_mce_not_found(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="not found"
        )
        resp = client.get("/api/mce/features")
        assert resp.status_code in (200, 500)


# =============================================
# GET /api/notification-settings
# =============================================


class TestNotificationSettingsGet:
    def test_get_settings(self):
        resp = client.get("/api/notification-settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "settings" in data
        settings = data["settings"]
        # Check all expected keys exist
        for key in [
            "slack_enabled", "email_enabled", "smtp_port",
            "notify_on_complete", "notify_on_failure",
        ]:
            assert key in settings


# =============================================
# POST /api/notification-settings
# =============================================


class TestNotificationSettingsUpdate:
    @patch("builtins.open", mock_open())
    @patch("app.slack_service")
    @patch("app.email_service")
    def test_update_settings(self, mock_email, mock_slack):
        mock_slack.reload_config = MagicMock()
        mock_email.reload_config = MagicMock()

        resp = client.post("/api/notification-settings", json={
            "slack_enabled": True,
            "slack_webhook_url": "https://hooks.slack.com/test",
            "email_enabled": False,
            "smtp_server": "",
            "smtp_port": 587,
            "smtp_username": "",
            "smtp_password": "",
            "from_email": "",
            "to_emails": [],
            "use_tls": True,
            "app_url": "http://localhost:3000",
            "notify_on_start": False,
            "notify_on_complete": True,
            "notify_on_failure": True,
            "notify_provision_start": False,
            "notify_provision_success": True,
            "notify_provision_failure": True,
            "notify_delete_start": False,
            "notify_delete_success": True,
            "notify_delete_failure": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["settings"]["slack_enabled"] is True


# =============================================
# POST /api/provisioning/generate-yaml (validation)
# =============================================


class TestProvisioningGenerateYaml:
    def test_missing_cluster_name(self):
        resp = client.post("/api/provisioning/generate-yaml", json={
            "config": {},
        })
        data = resp.json()
        assert data["success"] is False
        # HTTPException detail appears in error traceback, not message
        error_text = json.dumps(data).lower()
        assert "cluster_name" in error_text

    def test_missing_domain_prefix(self):
        resp = client.post("/api/provisioning/generate-yaml", json={
            "config": {"clusterName": "test-cluster"},
        })
        data = resp.json()
        assert data["success"] is False
        error_text = json.dumps(data).lower()
        assert "domain_prefix" in error_text

    def test_domain_prefix_too_long(self):
        resp = client.post("/api/provisioning/generate-yaml", json={
            "config": {
                "clusterName": "test-cluster",
                "domainPrefix": "a" * 16,
            },
        })
        data = resp.json()
        assert data["success"] is False

    @patch("os.path.exists", return_value=False)
    def test_template_not_found_still_returns(self, mock_exists):
        resp = client.post("/api/provisioning/generate-yaml", json={
            "config": {
                "clusterName": "test-cluster",
                "domainPrefix": "test",
                "openShiftVersion": "4.20.12",
                "createRosaNetwork": False,
                "createRosaRoleConfig": False,
            },
        })
        assert resp.status_code == 200


# =============================================
# POST /api/test-suites/run
# =============================================


class TestTestSuiteRun:
    @patch("os.path.exists", return_value=False)
    def test_suite_not_found(self, mock_exists):
        resp = client.post("/api/test-suites/run", json={
            "suite_name": "nonexistent-suite",
        })
        assert resp.status_code in (404, 500)


# =============================================
# GET /api/jobs/{job_id}
# =============================================


class TestJobStatus:
    def test_job_not_found(self):
        resp = client.get("/api/jobs/nonexistent-job-id")
        assert resp.status_code in (200, 404)

    def test_job_found(self):
        # Create a test job
        test_id = "test-job-status-check"
        app_module.jobs[test_id] = {
            "id": test_id,
            "status": "completed",
            "progress": 100,
            "message": "Done",
            "logs": ["line 1"],
            "created_at": datetime.now().isoformat(),
        }
        try:
            resp = client.get(f"/api/jobs/{test_id}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "completed"
        finally:
            del app_module.jobs[test_id]


# =============================================
# GET /api/jobs/{job_id}/logs
# =============================================


class TestJobLogs:
    def test_logs_not_found(self):
        resp = client.get("/api/jobs/nonexistent/logs")
        assert resp.status_code in (200, 404)

    def test_logs_found(self):
        test_id = "test-job-logs-check"
        app_module.jobs[test_id] = {
            "id": test_id,
            "status": "running",
            "progress": 50,
            "message": "Running...",
            "logs": ["TASK [verify] ***", "ok: [localhost]"],
        }
        try:
            resp = client.get(f"/api/jobs/{test_id}/logs")
            assert resp.status_code == 200
            data = resp.json()
            assert "logs" in data
            assert len(data["logs"]) == 2
        finally:
            del app_module.jobs[test_id]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
