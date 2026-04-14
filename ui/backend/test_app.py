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
    _validate_cluster_name,
    _validate_feature_value,
    _find_feature,
    _load_feature_registry_full,
    _get_registry,
    _get_feature_index,
    _load_action_history,
    _save_action_history,
    _record_action,
    CLUSTER_FEATURE_REGISTRY,
    _FEATURE_INDEX,
    ACTION_HISTORY_FILE,
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


# ---------------------------------------------------------------------------
# Cluster Actions: Feature Registry endpoints
# ---------------------------------------------------------------------------

class TestClusterActionsRegistry:
    """Tests for /api/cluster-actions/features endpoints."""

    def test_get_feature_registry(self, client):
        resp = client.get("/api/cluster-actions/features")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "registry" in data
        assert "suites" in data["registry"]
        assert len(data["registry"]["suites"]) > 0

    def test_registry_has_expected_suites(self, client):
        resp = client.get("/api/cluster-actions/features")
        data = resp.json()
        suite_ids = [s["id"] for s in data["registry"]["suites"]]
        assert "cluster-config" in suite_ids
        assert "security-auth" in suite_ids
        assert "version-lifecycle" in suite_ids

    def test_each_suite_has_features(self, client):
        resp = client.get("/api/cluster-actions/features")
        data = resp.json()
        for suite in data["registry"]["suites"]:
            assert "features" in suite
            assert len(suite["features"]) > 0
            for feat in suite["features"]:
                assert "id" in feat
                assert "name" in feat
                assert "type" in feat
                assert "applies_to" in feat

    def test_get_suite_by_id(self, client):
        resp = client.get("/api/cluster-actions/features/cluster-config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["suite"]["id"] == "cluster-config"

    def test_get_suite_not_found(self, client):
        resp = client.get("/api/cluster-actions/features/nonexistent")
        assert resp.status_code == 404


class TestClusterActionsExecute:
    """Tests for /api/cluster-actions/execute endpoint."""

    def test_execute_unknown_feature(self, client):
        resp = client.post("/api/cluster-actions/execute", json={
            "cluster_name": "test-cluster",
            "namespace": "ns-rosa-hcp",
            "actions": [{"feature_id": "nonexistent_feature", "target_value": "foo"}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"][0]["status"] == "error"
        assert "Unknown feature" in data["results"][0]["message"]

    def test_execute_immutable_feature(self, client):
        resp = client.post("/api/cluster-actions/execute", json={
            "cluster_name": "test-cluster",
            "namespace": "ns-rosa-hcp",
            "actions": [{"feature_id": "private_network", "target_value": True}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"][0]["status"] == "error"
        assert "immutable" in data["results"][0]["message"]

    @patch("app.subprocess.run")
    def test_execute_patch_action(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=0, stdout="patched", stderr="")
        resp = client.post("/api/cluster-actions/execute", json={
            "cluster_name": "test-cluster",
            "namespace": "ns-rosa-hcp",
            "actions": [{"feature_id": "channel_group", "target_value": "fast"}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"][0]["status"] == "completed"
        assert "Patched" in data["results"][0]["message"]

    @patch("app.subprocess.run")
    def test_execute_patch_failure(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="resource not found")
        resp = client.post("/api/cluster-actions/execute", json={
            "cluster_name": "test-cluster",
            "namespace": "ns-rosa-hcp",
            "actions": [{"feature_id": "channel_group", "target_value": "fast"}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"][0]["status"] == "error"

    @patch("app.subprocess.run")
    def test_execute_patch_timeout(self, mock_run, client):
        import subprocess as sp
        mock_run.side_effect = sp.TimeoutExpired(cmd="oc", timeout=15)
        resp = client.post("/api/cluster-actions/execute", json={
            "cluster_name": "test-cluster",
            "namespace": "ns-rosa-hcp",
            "actions": [{"feature_id": "channel_group", "target_value": "fast"}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"][0]["status"] == "error"
        assert "Timeout" in data["results"][0]["message"]

    def test_execute_multiple_actions(self, client):
        resp = client.post("/api/cluster-actions/execute", json={
            "cluster_name": "test-cluster",
            "namespace": "ns-rosa-hcp",
            "actions": [
                {"feature_id": "nonexistent_1", "target_value": "a"},
                {"feature_id": "nonexistent_2", "target_value": "b"},
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["action_count"] == 2

    def test_execute_returns_cluster_info(self, client):
        resp = client.post("/api/cluster-actions/execute", json={
            "cluster_name": "my-cluster",
            "namespace": "custom-ns",
            "actions": [],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["cluster_name"] == "my-cluster"
        assert data["namespace"] == "custom-ns"

    def test_execute_rejects_invalid_cluster_name(self, client):
        resp = client.post("/api/cluster-actions/execute", json={
            "cluster_name": "INVALID",
            "namespace": "ns-rosa-hcp",
            "actions": [],
        })
        assert resp.status_code == 400

    def test_execute_rejects_empty_cluster_name(self, client):
        resp = client.post("/api/cluster-actions/execute", json={
            "cluster_name": "",
            "namespace": "ns-rosa-hcp",
            "actions": [],
        })
        assert resp.status_code == 400

    @patch("app.subprocess.run")
    def test_execute_rejects_invalid_select_value(self, mock_run, client):
        resp = client.post("/api/cluster-actions/execute", json={
            "cluster_name": "test-cluster",
            "namespace": "ns-rosa-hcp",
            "actions": [{"feature_id": "channel_group", "target_value": "invalid-channel"}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"][0]["status"] == "error"
        assert "expects one of" in data["results"][0]["message"]

    @patch("app.subprocess.run")
    def test_execute_rejects_wrong_type_value(self, mock_run, client):
        resp = client.post("/api/cluster-actions/execute", json={
            "cluster_name": "test-cluster",
            "namespace": "ns-rosa-hcp",
            "actions": [{"feature_id": "proxy_enabled", "target_value": "not-a-bool"}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"][0]["status"] == "error"
        assert "expects boolean" in data["results"][0]["message"]


class TestClusterActionsProvision:
    """Tests for /api/cluster-actions/provision endpoint."""

    def test_provision_requires_name(self, client):
        resp = client.post("/api/cluster-actions/provision", json={})
        assert resp.status_code == 400

    def test_provision_validates_cluster_name(self, client):
        resp = client.post("/api/cluster-actions/provision", json={
            "cluster_name": "INVALID_NAME",
        })
        assert resp.status_code == 400

    def test_provision_rejects_too_long_name(self, client):
        resp = client.post("/api/cluster-actions/provision", json={
            "cluster_name": "a" * 55,
        })
        assert resp.status_code == 400

    def test_provision_rejects_name_starting_with_number(self, client):
        resp = client.post("/api/cluster-actions/provision", json={
            "cluster_name": "1bad-name",
        })
        assert resp.status_code == 400

    @patch("app.os.path.exists", return_value=True)
    @patch("app.asyncio.create_task")
    def test_provision_with_features(self, mock_task, mock_exists, client):
        resp = client.post("/api/cluster-actions/provision", json={
            "name_prefix": "test1",
            "features": {"private_network": True, "availability_zones": "3"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "job_id" in data
        assert "private_network" in data["features_applied"]
        assert "availability_zones" in data["features_applied"]

    @patch("app.os.path.exists", return_value=True)
    @patch("app.asyncio.create_task")
    def test_provision_with_name_prefix(self, mock_task, mock_exists, client):
        resp = client.post("/api/cluster-actions/provision", json={
            "name_prefix": "mytest",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["cluster_name"] == "mytest-rosa-hcp"


class TestClusterActionsHistory:
    """Tests for /api/cluster-actions/history endpoint."""

    @patch("app._load_action_history", return_value=[])
    def test_history_empty(self, mock_load, client):
        resp = client.get("/api/cluster-actions/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["history"] == []
        assert data["count"] == 0

    @patch("app._load_action_history")
    def test_history_filter_by_cluster(self, mock_load, client):
        mock_load.return_value = [
            {"cluster_name": "c1", "feature_id": "f1"},
            {"cluster_name": "c2", "feature_id": "f2"},
            {"cluster_name": "c1", "feature_id": "f3"},
        ]
        resp = client.get("/api/cluster-actions/history?cluster_name=c1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2

    @patch("app._load_action_history")
    def test_history_returns_reversed(self, mock_load, client):
        mock_load.return_value = [
            {"cluster_name": "c1", "feature_id": "first"},
            {"cluster_name": "c1", "feature_id": "second"},
        ]
        resp = client.get("/api/cluster-actions/history")
        data = resp.json()
        assert data["history"][0]["feature_id"] == "second"


class TestClusterActionsDiscover:
    """Tests for /api/cluster-actions/discover endpoint."""

    @patch("app.subprocess.run")
    def test_discover_clusters(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"items": [{
                "metadata": {"name": "test-cluster", "namespace": "ns-rosa-hcp", "creationTimestamp": "2026-01-01"},
                "spec": {"version": "4.20.11", "channelGroup": "stable"},
                "status": {"ready": True, "availableUpgrades": ["4.20.12"]},
            }]}),
        )
        resp = client.get("/api/cluster-actions/discover")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 1
        assert data["clusters"][0]["name"] == "test-cluster"
        assert data["clusters"][0]["version"] == "4.20.11"

    @patch("app.subprocess.run")
    def test_discover_with_namespace(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({"items": []}))
        resp = client.get("/api/cluster-actions/discover?namespace=custom-ns")
        assert resp.status_code == 200
        # Verify namespace flag was passed
        call_args = mock_run.call_args[0][0]
        assert "-n" in call_args
        assert "custom-ns" in call_args

    @patch("app.subprocess.run")
    def test_discover_oc_failure(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=1, stderr="connection refused")
        resp = client.get("/api/cluster-actions/discover")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    @patch("app.subprocess.run")
    def test_discover_timeout(self, mock_run, client):
        import subprocess as sp
        mock_run.side_effect = sp.TimeoutExpired(cmd="oc", timeout=15)
        resp = client.get("/api/cluster-actions/discover")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "Timeout" in data["error"]


class TestClusterActionsStatus:
    """Tests for /api/cluster-actions/cluster/{name}/status endpoint."""

    @patch("app.subprocess.run")
    def test_cluster_status_found(self, mock_run, client):
        cp_json = json.dumps({
            "spec": {"version": "4.20.11", "endpointAccess": "public", "channelGroup": "stable"},
            "status": {"ready": True, "availableUpgrades": ["4.20.12"]},
        })
        mp_json = json.dumps({"items": [{
            "metadata": {"name": "default"},
            "spec": {"version": "4.20.11", "instanceType": "m5.xlarge"},
            "status": {"ready": True},
        }]})
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=cp_json, stderr=""),
            MagicMock(returncode=0, stdout=mp_json, stderr=""),
        ]
        resp = client.get("/api/cluster-actions/cluster/test-cluster/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"]["cluster_found"] is True
        assert data["status"]["version"] == "4.20.11"
        assert len(data["status"]["machine_pools"]) == 1

    @patch("app.subprocess.run")
    def test_cluster_status_not_found(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=1, stderr="not found")
        resp = client.get("/api/cluster-actions/cluster/missing/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"]["cluster_found"] is False

    @patch("app.subprocess.run")
    def test_cluster_status_timeout(self, mock_run, client):
        import subprocess as sp
        mock_run.side_effect = sp.TimeoutExpired(cmd="oc", timeout=15)
        resp = client.get("/api/cluster-actions/cluster/test/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"]["cluster_found"] is False


class TestClusterNameValidation:
    """Tests for _validate_cluster_name helper."""

    def test_valid_name(self):
        assert _validate_cluster_name("my-cluster") is None

    def test_valid_short_name(self):
        assert _validate_cluster_name("a") is None

    def test_valid_long_name(self):
        assert _validate_cluster_name("a" * 54) is None

    def test_empty_name(self):
        assert _validate_cluster_name("") is not None

    def test_too_long(self):
        assert _validate_cluster_name("a" * 55) is not None

    def test_uppercase(self):
        assert _validate_cluster_name("MyCluster") is not None

    def test_starts_with_number(self):
        assert _validate_cluster_name("1cluster") is not None

    def test_starts_with_hyphen(self):
        assert _validate_cluster_name("-cluster") is not None

    def test_special_chars(self):
        assert _validate_cluster_name("my_cluster") is not None

    def test_spaces(self):
        assert _validate_cluster_name("my cluster") is not None


class TestFindFeature:
    """Tests for _find_feature helper."""

    def test_find_known_feature(self):
        feat = _find_feature("private_network")
        assert feat is not None
        assert feat["id"] == "private_network"
        assert feat["type"] == "boolean"

    def test_find_unknown_feature(self):
        assert _find_feature("nonexistent") is None

    def test_all_features_indexed(self):
        registry = _load_feature_registry_full()
        for suite in registry.get("suites", []):
            for feat in suite.get("features", []):
                assert _find_feature(feat["id"]) is not None, f"Feature {feat['id']} not in index"


class TestFeatureRegistryLoading:
    """Tests for registry loading functions."""

    def test_load_full_registry(self):
        data = _load_feature_registry_full()
        assert "suites" in data
        assert "var_map" in data
        assert "dependencies" in data
        assert "sequences" in data

    def test_var_map_has_provision_features(self):
        data = _load_feature_registry_full()
        var_map = data["var_map"]
        assert var_map["private_network"] == "private"
        assert var_map["byon"] == "byon_vpc"
        assert var_map["etcd_kms"] == "etcd_encryption_kms_arn"

    def test_cluster_delete_is_immutable(self):
        feat = _find_feature("cluster_delete")
        assert feat is not None
        assert feat["mutable"] is False

    def test_registry_feature_types(self):
        """All features have valid types."""
        valid_types = {"boolean", "select", "number", "string", "key_value",
                       "list", "range", "version", "action"}
        data = _load_feature_registry_full()
        for suite in data["suites"]:
            for feat in suite["features"]:
                assert feat["type"] in valid_types, f"Feature {feat['id']} has invalid type: {feat['type']}"

    def test_get_registry_returns_fresh_data(self):
        """_get_registry returns valid registry data."""
        registry = _get_registry()
        assert "suites" in registry
        assert len(registry["suites"]) > 0

    def test_get_feature_index_returns_fresh_data(self):
        """_get_feature_index returns a dict with all features."""
        index = _get_feature_index()
        assert "private_network" in index
        assert "channel_group" in index


class TestFeatureValueValidation:
    """Tests for _validate_feature_value helper."""

    def test_boolean_valid(self):
        feat = {"id": "test", "type": "boolean"}
        assert _validate_feature_value(feat, True) is None
        assert _validate_feature_value(feat, False) is None

    def test_boolean_invalid(self):
        feat = {"id": "test", "type": "boolean"}
        assert _validate_feature_value(feat, "true") is not None
        assert _validate_feature_value(feat, 1) is not None

    def test_select_valid(self):
        feat = {"id": "test", "type": "select", "options": ["stable", "fast", "candidate"]}
        assert _validate_feature_value(feat, "fast") is None

    def test_select_invalid(self):
        feat = {"id": "test", "type": "select", "options": ["stable", "fast", "candidate"]}
        assert _validate_feature_value(feat, "nightly") is not None

    def test_number_valid(self):
        feat = {"id": "test", "type": "number"}
        assert _validate_feature_value(feat, 42) is None
        assert _validate_feature_value(feat, 3.14) is None

    def test_number_invalid(self):
        feat = {"id": "test", "type": "number"}
        assert _validate_feature_value(feat, "42") is not None

    def test_string_max_length(self):
        feat = {"id": "test", "type": "string", "max_length": 5}
        assert _validate_feature_value(feat, "abc") is None
        assert _validate_feature_value(feat, "toolong") is not None

    def test_version_valid(self):
        feat = {"id": "test", "type": "version"}
        assert _validate_feature_value(feat, "4.20.11") is None

    def test_version_invalid(self):
        feat = {"id": "test", "type": "version"}
        assert _validate_feature_value(feat, "not-semver") is not None
        assert _validate_feature_value(feat, "4.20") is not None

    def test_key_value_valid(self):
        feat = {"id": "test", "type": "key_value"}
        assert _validate_feature_value(feat, {"key": "val"}) is None

    def test_key_value_invalid(self):
        feat = {"id": "test", "type": "key_value"}
        assert _validate_feature_value(feat, "not-a-dict") is not None

    def test_list_valid(self):
        feat = {"id": "test", "type": "list"}
        assert _validate_feature_value(feat, ["a", "b"]) is None

    def test_list_invalid(self):
        feat = {"id": "test", "type": "list"}
        assert _validate_feature_value(feat, "not-a-list") is not None

    def test_range_valid(self):
        feat = {"id": "test", "type": "range"}
        assert _validate_feature_value(feat, {"min": 1, "max": 5}) is None

    def test_range_missing_fields(self):
        feat = {"id": "test", "type": "range"}
        assert _validate_feature_value(feat, {"min": 1}) is not None

    def test_range_invalid_type(self):
        feat = {"id": "test", "type": "range"}
        assert _validate_feature_value(feat, 42) is not None

    def test_action_type_passes(self):
        feat = {"id": "test", "type": "action"}
        assert _validate_feature_value(feat, None) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
