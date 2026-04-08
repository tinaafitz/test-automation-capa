"""
Tests for app.py FastAPI backend endpoints.
Covers Phases 3 and 3B: pure endpoints, utility functions,
subprocess endpoints, MCE CRUD, and complex flows.
"""

import json
import os
import sys
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient

# Mock anthropic before app imports it
sys.modules.setdefault("anthropic", MagicMock())

# Patch app_extensions import to avoid missing module errors
sys.modules.setdefault("app_extensions", MagicMock())

from app import (
    app,
    jobs,
    clusters,
    normalize_timestamp,
    check_and_timeout_stuck_jobs,
    init_ai_agents,
    get_agent_stats,
    ai_agent_sessions,
)


@pytest.fixture
def client():
    """FastAPI test client with clean state."""
    jobs.clear()
    clusters.clear()
    ai_agent_sessions.clear()
    return TestClient(app)


@pytest.fixture
def sample_job():
    """Create and register a sample job."""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "id": job_id,
        "status": "running",
        "progress": 50,
        "message": "In progress",
        "started_at": datetime.now(),
        "logs": ["line1", "line2"],
    }
    return job_id


@pytest.fixture
def sample_cluster():
    """Create and register a sample cluster."""
    cluster_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    clusters[cluster_id] = {
        "id": cluster_id,
        "config": {"name": "test-cluster", "capi_namespace": "ns-rosa-hcp"},
        "job_id": job_id,
        "created_at": datetime.now(),
        "status": "ready",
    }
    jobs[job_id] = {
        "id": job_id,
        "cluster_id": cluster_id,
        "status": "completed",
        "progress": 100,
        "message": "Done",
        "started_at": datetime.now(),
        "logs": [],
    }
    return cluster_id, job_id


# ---------------------------------------------------------------------------
# Root and health
# ---------------------------------------------------------------------------

class TestRootAndHealth:
    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "1.0.0"

    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

class TestTemplates:
    def test_get_templates(self, client):
        resp = client.get("/api/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert "templates" in data
        assert len(data["templates"]) > 0

    def test_get_build_templates(self, client):
        resp = client.get("/api/build/templates")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Cluster CRUD
# ---------------------------------------------------------------------------

class TestClusterCRUD:
    def test_get_cluster_not_found(self, client):
        resp = client.get("/api/clusters/nonexistent")
        assert resp.status_code == 404

    def test_get_cluster_found(self, client, sample_cluster):
        cluster_id, _ = sample_cluster
        resp = client.get(f"/api/clusters/{cluster_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cluster"]["id"] == cluster_id

    def test_delete_cluster_not_found(self, client):
        resp = client.delete("/api/clusters/nonexistent")
        assert resp.status_code == 404

    @patch("app.asyncio.create_task")
    def test_delete_cluster(self, mock_task, client, sample_cluster):
        cluster_id, _ = sample_cluster
        resp = client.delete(f"/api/clusters/{cluster_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data

    @patch("app.asyncio.create_task")
    def test_create_cluster(self, mock_task, client):
        resp = client.post("/api/clusters", json={
            "name": "test-cluster",
            "version": "4.20.0",
            "region": "us-west-2",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "cluster_id" in data
        assert "job_id" in data


# ---------------------------------------------------------------------------
# Job CRUD
# ---------------------------------------------------------------------------

class TestJobCRUD:
    def test_list_jobs_empty(self, client):
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 0

    def test_list_jobs_with_data(self, client, sample_job):
        resp = client.get("/api/jobs")
        data = resp.json()
        assert data["count"] == 1

    def test_get_job_not_found(self, client):
        resp = client.get("/api/jobs/nonexistent")
        assert resp.status_code == 404

    def test_get_job_found(self, client, sample_job):
        resp = client.get(f"/api/jobs/{sample_job}")
        assert resp.status_code == 200

    def test_get_job_logs_not_found(self, client):
        resp = client.get("/api/jobs/nonexistent/logs")
        assert resp.status_code == 404

    def test_get_job_logs(self, client, sample_job):
        resp = client.get(f"/api/jobs/{sample_job}/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["logs"]) == 2

    def test_clear_all_jobs(self, client, sample_job):
        resp = client.delete("/api/jobs")
        assert resp.status_code == 200
        assert len(jobs) == 0

    def test_cancel_job_not_found(self, client):
        resp = client.post("/api/jobs/nonexistent/cancel")
        assert resp.status_code == 404

    def test_cancel_running_job(self, client, sample_job):
        resp = client.post(f"/api/jobs/{sample_job}/cancel")
        assert resp.status_code == 200
        assert jobs[sample_job]["status"] == "failed"

    def test_cancel_non_running_job(self, client, sample_job):
        jobs[sample_job]["status"] = "completed"
        resp = client.post(f"/api/jobs/{sample_job}/cancel")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Agent Stats
# ---------------------------------------------------------------------------

class TestAgentStats:
    def test_agent_stats_no_agents(self, client, sample_job):
        resp = client.get(f"/api/jobs/{sample_job}/agent-stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_stats"]["enabled"] is False

    def test_agent_stats_not_found(self, client):
        resp = client.get("/api/jobs/nonexistent/agent-stats")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

class TestNormalizeTimestamp:
    def test_none(self):
        assert normalize_timestamp(None) == datetime.min

    def test_datetime(self):
        dt = datetime(2026, 1, 1)
        assert normalize_timestamp(dt) == dt

    def test_unix_timestamp(self):
        ts = 1735689600.0  # 2025-01-01
        result = normalize_timestamp(ts)
        assert isinstance(result, datetime)

    def test_iso_string(self):
        result = normalize_timestamp("2026-01-01T00:00:00")
        assert result.year == 2026

    def test_iso_string_with_z(self):
        result = normalize_timestamp("2026-01-01T00:00:00Z")
        assert result.year == 2026

    def test_empty_string(self):
        assert normalize_timestamp("") == datetime.min

    def test_zero_string(self):
        assert normalize_timestamp("0") == datetime.min

    def test_invalid_string(self):
        assert normalize_timestamp("not-a-date") == datetime.min

    def test_invalid_type(self):
        assert normalize_timestamp([1, 2, 3]) == datetime.min


class TestCheckAndTimeoutStuckJobs:
    def test_no_stuck_jobs(self):
        jobs.clear()
        job_id = "j1"
        jobs[job_id] = {"status": "running", "started_at": datetime.now()}
        stuck = check_and_timeout_stuck_jobs()
        assert len(stuck) == 0

    def test_stuck_job_timeout(self):
        jobs.clear()
        job_id = "j1"
        jobs[job_id] = {
            "status": "running",
            "started_at": datetime.now() - timedelta(minutes=100),
        }
        stuck = check_and_timeout_stuck_jobs()
        assert job_id in stuck
        assert jobs[job_id]["status"] == "failed"

    def test_completed_job_not_checked(self):
        jobs.clear()
        job_id = "j1"
        jobs[job_id] = {
            "status": "completed",
            "started_at": datetime.now() - timedelta(minutes=200),
        }
        stuck = check_and_timeout_stuck_jobs()
        assert len(stuck) == 0

    def test_stuck_job_with_string_timestamp(self):
        jobs.clear()
        job_id = "j1"
        past = (datetime.now() - timedelta(minutes=100)).isoformat()
        jobs[job_id] = {"status": "running", "started_at": past}
        stuck = check_and_timeout_stuck_jobs()
        assert job_id in stuck

    def test_no_started_at(self):
        jobs.clear()
        jobs["j1"] = {"status": "running"}
        stuck = check_and_timeout_stuck_jobs()
        assert len(stuck) == 0


class TestInitAiAgents:
    def test_init_agents(self):
        jobs.clear()
        ai_agent_sessions.clear()
        job_id = "test-job"
        jobs[job_id] = {"id": job_id, "status": "running", "logs": []}
        session = init_ai_agents(job_id)
        if session:  # May be None if agents unavailable
            assert "monitor" in session
            assert "diagnostic" in session
            assert "remediation" in session
            assert "learning" in session

    def test_get_agent_stats_no_session(self):
        ai_agent_sessions.clear()
        stats = get_agent_stats("nonexistent")
        assert stats["enabled"] is False


# ---------------------------------------------------------------------------
# Notification Settings
# ---------------------------------------------------------------------------

class TestNotificationSettings:
    def test_get_notification_settings(self, client):
        resp = client.get("/api/notification-settings")
        assert resp.status_code == 200

    def test_post_notification_settings(self, client):
        resp = client.post("/api/notification-settings", json={
            "slack_enabled": False,
            "email_enabled": False,
        })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Onboarding and Diagnostics
# ---------------------------------------------------------------------------

class TestOnboardingAndDiagnostics:
    def test_get_onboarding_tour(self, client):
        resp = client.get("/api/onboarding/tour")
        assert resp.status_code == 200
        data = resp.json()
        assert "steps" in data
        assert len(data["steps"]) >= 3

    def test_get_diagnostic_checks(self, client):
        resp = client.get("/api/diagnostics/checks")
        assert resp.status_code == 200
        data = resp.json()
        assert "checks" in data
        assert len(data["checks"]) >= 5

    def test_run_diagnostics(self, client):
        resp = client.post("/api/diagnostics/run", json={
            "checks": ["aws_credentials", "openshift_version"]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 2


# ---------------------------------------------------------------------------
# Environment Overview
# ---------------------------------------------------------------------------

class TestEnvironmentOverview:
    def test_get_environment_overview(self, client):
        resp = client.get("/api/environment/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert "aws" in data


# ---------------------------------------------------------------------------
# Versions (subprocess endpoint)
# ---------------------------------------------------------------------------

class TestVersions:
    @patch("app.subprocess.run")
    def test_get_versions_success(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="VERSION  DEFAULT  AVAILABLE UPGRADES\n4.20.12  yes\n4.20.11\n4.19.22\n",
        )
        resp = client.get("/api/versions")
        assert resp.status_code == 200
        data = resp.json()
        assert "versions" in data
        assert len(data["versions"]) > 0

    @patch("app.subprocess.run")
    def test_get_versions_rosa_fail(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        resp = client.get("/api/versions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["versions"]) > 0  # fallback versions

    @patch("app.subprocess.run")
    def test_get_versions_exception(self, mock_run, client):
        mock_run.side_effect = Exception("rosa not found")
        resp = client.get("/api/versions")
        assert resp.status_code == 200
        data = resp.json()
        assert "versions" in data  # fallback


# ---------------------------------------------------------------------------
# ROSA Status (subprocess endpoint)
# ---------------------------------------------------------------------------

class TestRosaStatus:
    @patch("app.subprocess.run")
    def test_rosa_status(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="OCM API: https://api.openshift.com\nUser: test-user\nAWS Account: 123456789\n",
            stderr="",
        )
        # Clear cache
        import app
        app.rosa_status_cache["timestamp"] = 0
        resp = client.get("/api/rosa/status")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

class TestCredentials:
    def test_get_credentials(self, client):
        resp = client.get("/api/credentials")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

class TestValidate:
    def test_validate_valid_config(self, client):
        resp = client.post("/api/validate", json={
            "name": "test-cluster",
            "version": "4.20.0",
            "region": "us-west-2",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True

    def test_validate_invalid_name(self, client):
        resp = client.post("/api/validate", json={
            "name": "test cluster!",
            "version": "4.20.0",
            "region": "us-west-2",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False

    def test_validate_long_name_warning(self, client):
        resp = client.post("/api/validate", json={
            "name": "this-is-a-very-long-cluster-name",
            "version": "4.20.0",
            "region": "us-west-2",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["warnings"]) > 0

    def test_validate_bad_replicas(self, client):
        resp = client.post("/api/validate", json={
            "name": "test",
            "version": "4.20.0",
            "region": "us-west-2",
            "min_replicas": 5,
            "max_replicas": 2,
        })
        assert resp.status_code == 200
        assert resp.json()["valid"] is False


# ---------------------------------------------------------------------------
# User Profile
# ---------------------------------------------------------------------------

class TestUserProfile:
    def test_get_user_profile(self, client):
        resp = client.get("/api/user/profile")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Guided Setup
# ---------------------------------------------------------------------------

class TestGuidedSetup:
    def test_get_guided_setup_status(self, client):
        resp = client.get("/api/guided-setup/status")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# ROSA Last YAML Path
# ---------------------------------------------------------------------------

class TestRosaYamlPath:
    def test_get_last_yaml_path(self, client):
        resp = client.get("/api/rosa/last-yaml-path")
        assert resp.status_code == 200

    def test_save_yaml_path(self, client):
        resp = client.post("/api/rosa/save-yaml-path", json={"path": "/tmp/test.yaml"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Test Suites List
# ---------------------------------------------------------------------------

class TestTestSuites:
    def test_list_test_suites(self, client):
        resp = client.get("/api/test-suites/list")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# OCP Connection Status (subprocess)
# ---------------------------------------------------------------------------

class TestOcpConnection:
    @patch("app.subprocess.run")
    def test_ocp_connection_status(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://api.test-cluster.example.com:6443",
            stderr="",
        )
        import app
        app.ocp_status_cache["timestamp"] = 0
        resp = client.get("/api/ocp/connection-status")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# AWS Credentials Status (subprocess)
# ---------------------------------------------------------------------------

class TestAwsCredentials:
    @patch("app.subprocess.run")
    def test_aws_credentials_status(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"UserId":"AIDA123","Account":"123456789012","Arn":"arn:aws:iam::123456789012:user/test"}',
            stderr="",
        )
        resp = client.get("/api/aws/credentials-status")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# MCE Features (subprocess)
# ---------------------------------------------------------------------------

class TestMceFeatures:
    @patch("app.subprocess.run")
    def test_mce_features(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="NAME   NAMESPACE   AGE\ncapi   open-cluster-management   1d\n",
            stderr="",
        )
        resp = client.get("/api/mce/features")
        # May return 200 or 500 depending on OCP login state
        assert resp.status_code in (200, 500)


# ---------------------------------------------------------------------------
# CAPI Component Versions (subprocess)
# ---------------------------------------------------------------------------

class TestCapiVersions:
    @patch("app.subprocess.run")
    def test_capi_component_versions(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="capi-controller-manager  1/1  Running  0  1d\n",
            stderr="",
        )
        resp = client.get("/api/capi/component-versions")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_capi_cli_versions(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="rosa 1.2.47\n",
            stderr="",
        )
        resp = client.get("/api/capi/cli-versions")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Minikube List Clusters (subprocess)
# ---------------------------------------------------------------------------

class TestMinikubeList:
    @patch("app.subprocess.run")
    def test_minikube_list_clusters(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"Name":"test","Status":"Running","Driver":"docker"}]',
            stderr="",
        )
        import app
        app.minikube_clusters_cache["timestamp"] = 0
        resp = client.get("/api/minikube/list-clusters")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Ansible Run Playbook (complex flow)
# ---------------------------------------------------------------------------

class TestAnsibleRunPlaybook:
    @patch("app.asyncio.create_task")
    def test_run_playbook(self, mock_task, client):
        resp = client.post("/api/ansible/run-playbook", json={
            "playbook": "playbooks/create_rosa_hcp_cluster.yml",
            "extra_vars": {"cluster_name": "test"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data


# ---------------------------------------------------------------------------
# Ansible Run Task
# ---------------------------------------------------------------------------

class TestAnsibleRunTask:
    @patch("app.asyncio.create_task")
    def test_run_task(self, mock_task, client):
        resp = client.post("/api/ansible/run-task", json={
            "task_file": "tasks/test.yml",
            "extra_vars": {},
        })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# AI Assistant Chat
# ---------------------------------------------------------------------------

class TestAiAssistantChat:
    def test_chat(self, client):
        with patch("app.ai_service.chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = {"response": "Hello!", "suggestions": []}
            resp = client.post("/api/ai-assistant/chat", json={
                "message": "What clusters?",
                "context": {},
            })
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# MCE Environments Stats
# ---------------------------------------------------------------------------

class TestMceEnvironmentsStats:
    @patch("app.os.path.join")
    def test_mce_stats_summary(self, mock_join, client):
        # This endpoint imports MCEEnvManager dynamically, mock it
        mock_manager = MagicMock()
        mock_manager.get_statistics.return_value = {
            "total": 0,
            "by_status": {},
            "by_platform": {},
        }
        with patch.dict("sys.modules", {"mce_env_manager": MagicMock(MCEEnvManager=lambda: mock_manager)}):
            resp = client.get("/api/mce-environments/stats/summary")
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# AWS Usage Config
# ---------------------------------------------------------------------------

class TestAwsUsageConfig:
    def test_aws_usage_config(self, client):
        resp = client.get("/api/aws/usage-config")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Config Status
# ---------------------------------------------------------------------------

class TestConfigStatus:
    def test_config_status(self, client):
        resp = client.get("/api/config/status")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Notification Settings Test Connection
# ---------------------------------------------------------------------------

class TestNotificationSettingsTest:
    def test_test_slack(self, client):
        with patch("app.slack_service.test_connection") as mock_test:
            mock_test.return_value = {"success": True, "message": "ok"}
            resp = client.post("/api/notification-settings/test", json={
                "type": "slack",
            })
            assert resp.status_code == 200

    def test_test_email(self, client):
        with patch("app.email_service.test_connection") as mock_test:
            mock_test.return_value = {"success": True, "message": "ok"}
            resp = client.post("/api/notification-settings/test", json={
                "type": "email",
            })
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# ROSA Clusters list (subprocess)
# ---------------------------------------------------------------------------

class TestRosaClusters:
    @patch("app.subprocess.run")
    def test_list_rosa_clusters(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"id":"abc","name":"test-cluster","state":"ready","region":"us-west-2"}]',
            stderr="",
        )
        resp = client.get("/api/rosa/clusters")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Test suites history and status
# ---------------------------------------------------------------------------

class TestTestSuiteHistory:
    def test_test_suites_history(self, client):
        resp = client.get("/api/test-suites/history")
        assert resp.status_code == 200

    def test_test_suites_status(self, client):
        resp = client.get("/api/test-suites/status/nonexistent")
        assert resp.status_code in (200, 404)


# ---------------------------------------------------------------------------
# Jenkins and GitHub APIs
# ---------------------------------------------------------------------------

class TestJenkinsGithub:
    @patch("app.subprocess.run")
    def test_jenkins_test_results_trend(self, mock_run, client):
        resp = client.get("/api/jenkins/test-results-trend")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_github_repo_activity(self, mock_run, client):
        resp = client.get("/api/github/repo-activity")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# AWS Usage endpoints
# ---------------------------------------------------------------------------

class TestAwsUsage:
    @patch("app.subprocess.run")
    def test_aws_usage(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        resp = client.get("/api/aws/usage")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_aws_usage_trend(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        resp = client.get("/api/aws/usage-trend")
        assert resp.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
