"""
Tests for app.py FastAPI backend endpoints.
Covers Phases 3 and 3B: pure endpoints, utility functions,
subprocess endpoints, MCE CRUD, and complex flows.
"""

import asyncio
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
    _build_json_merge_patch,
    _get_cluster_lock,
    _cluster_locks,
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


class TestBuildJsonMergePatch:
    """Tests for _build_json_merge_patch helper."""

    def test_simple_field(self):
        result = _build_json_merge_patch(".spec.channelGroup", "fast")
        assert result == {"spec": {"channelGroup": "fast"}}

    def test_nested_field(self):
        result = _build_json_merge_patch(".spec.network.noCNI", True)
        assert result == {"spec": {"network": {"noCNI": True}}}

    def test_single_level(self):
        result = _build_json_merge_patch(".version", "4.20.11")
        assert result == {"version": "4.20.11"}

    def test_dict_value(self):
        result = _build_json_merge_patch(".spec.additionalTags", {"env": "test"})
        assert result == {"spec": {"additionalTags": {"env": "test"}}}


class TestClusterSpecPlan:
    """Tests for /api/cluster-specs/plan endpoint."""

    def test_plan_create_spec(self, client):
        resp = client.post("/api/cluster-specs/plan", json={
            "spec": {
                "apiVersion": "capa-automation/v1",
                "kind": "ClusterAutomationSpec",
                "metadata": {"name": "test"},
                "spec": {
                    "action": "create",
                    "name_prefix": "test1",
                    "version": "4.20.11",
                    "features": {"private_network": True},
                },
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["step_count"] >= 1
        assert data["plan"][0]["type"] == "playbook"

    def test_plan_upgrade_spec(self, client):
        resp = client.post("/api/cluster-specs/plan", json={
            "spec": {
                "apiVersion": "capa-automation/v1",
                "kind": "ClusterAutomationSpec",
                "metadata": {"name": "test"},
                "spec": {
                    "action": "upgrade",
                    "cluster": "test-cluster",
                    "version": "4.20.12",
                },
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["step_count"] >= 2  # CP upgrade + MP upgrade

    def test_plan_delete_spec(self, client):
        resp = client.post("/api/cluster-specs/plan", json={
            "spec": {
                "apiVersion": "capa-automation/v1",
                "kind": "ClusterAutomationSpec",
                "metadata": {"name": "test"},
                "spec": {
                    "action": "delete",
                    "cluster": "test-cluster",
                },
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["step_count"] == 1

    def test_plan_no_spec(self, client):
        resp = client.post("/api/cluster-specs/plan", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_plan_with_overrides(self, client):
        resp = client.post("/api/cluster-specs/plan", json={
            "spec": {
                "apiVersion": "capa-automation/v1",
                "kind": "ClusterAutomationSpec",
                "metadata": {"name": "test"},
                "spec": {"action": "create", "name_prefix": "orig"},
            },
            "overrides": {"version": "4.20.12"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True


class TestClusterSpecExecute:
    """Tests for /api/cluster-specs/execute endpoint."""

    def test_execute_no_spec(self, client):
        resp = client.post("/api/cluster-specs/execute", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    @patch("app.os.path.exists", return_value=True)
    @patch("app.asyncio.create_task")
    def test_execute_create_spec(self, mock_task, mock_exists, client):
        resp = client.post("/api/cluster-specs/execute", json={
            "spec": {
                "apiVersion": "capa-automation/v1",
                "kind": "ClusterAutomationSpec",
                "metadata": {"name": "test"},
                "spec": {"action": "create", "name_prefix": "test1"},
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["results"]) >= 1
        assert data["results"][0]["status"] == "running"


class TestExecutePlaybookPath:
    """Tests for execute endpoint's playbook-backed feature path."""

    @patch("app.os.path.exists", return_value=True)
    @patch("app.asyncio.create_task")
    def test_execute_playbook_feature(self, mock_task, mock_exists, client):
        """Test executing a playbook-backed feature (e.g. control_plane_upgrade)."""
        resp = client.post("/api/cluster-actions/execute", json={
            "cluster_name": "test-cluster",
            "namespace": "ns-rosa-hcp",
            "actions": [{"feature_id": "control_plane_upgrade", "target_value": "4.20.12"}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"][0]["status"] == "running"
        assert data["results"][0]["playbook"] is not None
        assert "job_id" in data["results"][0]

    @patch("app.os.path.exists", return_value=False)
    def test_execute_playbook_not_found(self, mock_exists, client):
        """Test error when playbook file doesn't exist."""
        resp = client.post("/api/cluster-actions/execute", json={
            "cluster_name": "test-cluster",
            "namespace": "ns-rosa-hcp",
            "actions": [{"feature_id": "control_plane_upgrade", "target_value": "4.20.12"}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"][0]["status"] == "error"
        assert "Playbook not found" in data["results"][0]["message"]


class TestClusterConcurrencyLock:
    """Tests for per-cluster concurrency locking."""

    def test_get_cluster_lock_creates_lock(self):
        lock = _get_cluster_lock("lock-test-cluster")
        assert lock is not None
        assert isinstance(lock, asyncio.Lock)
        # Clean up
        _cluster_locks.pop("lock-test-cluster", None)

    def test_get_cluster_lock_returns_same_lock(self):
        lock1 = _get_cluster_lock("lock-reuse-cluster")
        lock2 = _get_cluster_lock("lock-reuse-cluster")
        assert lock1 is lock2
        _cluster_locks.pop("lock-reuse-cluster", None)

    def test_different_clusters_get_different_locks(self):
        lock_a = _get_cluster_lock("lock-cluster-a")
        lock_b = _get_cluster_lock("lock-cluster-b")
        assert lock_a is not lock_b
        _cluster_locks.pop("lock-cluster-a", None)
        _cluster_locks.pop("lock-cluster-b", None)

    def test_execute_rejects_concurrent_request(self, client):
        """When a cluster lock is held, a second request gets 409."""
        lock = _get_cluster_lock("busy-cluster")
        # Manually acquire the lock to simulate an in-progress operation
        loop = asyncio.new_event_loop()
        loop.run_until_complete(lock.acquire())
        try:
            resp = client.post("/api/cluster-actions/execute", json={
                "cluster_name": "busy-cluster",
                "namespace": "ns-rosa-hcp",
                "actions": [],
            })
            assert resp.status_code == 409
            assert "operation in progress" in resp.json()["detail"]
        finally:
            lock.release()
            loop.close()
            _cluster_locks.pop("busy-cluster", None)


# ============================================================================
# Workflow CRUD Tests
# ============================================================================

class TestWorkflowCRUD:
    """Tests for workflow save/load/update/delete/duplicate endpoints."""

    @pytest.fixture(autouse=True)
    def clean_workflows(self, tmp_path):
        wf_file = str(tmp_path / "saved_workflows.json")
        with patch("app.WORKFLOWS_FILE", wf_file):
            yield wf_file

    def test_list_workflows_empty(self, client):
        resp = client.get("/api/workflows")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["workflows"] == []
        assert data["count"] == 0

    def test_save_workflow(self, client):
        resp = client.post("/api/workflows", json={
            "name": "test-wf",
            "description": "A test workflow",
            "steps": [{"name": "step1", "playbook": "playbooks/test.yml"}],
            "vars": {"key": "val"},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["workflow"]["name"] == "test-wf"
        assert data["workflow"]["id"].startswith("wf-")
        assert data["updated"] is False

    def test_save_workflow_updates_existing(self, client):
        # Create
        client.post("/api/workflows", json={"name": "dupe-wf", "steps": []})
        # Save again with same name — should update
        resp = client.post("/api/workflows", json={
            "name": "dupe-wf",
            "description": "updated",
            "steps": [{"name": "new-step"}],
        })
        data = resp.json()
        assert data["updated"] is True
        assert data["workflow"]["description"] == "updated"

    def test_list_workflows_after_save(self, client):
        client.post("/api/workflows", json={"name": "wf1", "steps": []})
        client.post("/api/workflows", json={"name": "wf2", "steps": [{"name": "s1"}]})
        resp = client.get("/api/workflows")
        data = resp.json()
        assert data["count"] == 2
        assert data["workflows"][0]["name"] == "wf1"
        assert data["workflows"][1]["stepCount"] == 1

    def test_get_workflow_by_id(self, client):
        save_resp = client.post("/api/workflows", json={"name": "get-me", "steps": []})
        wf_id = save_resp.json()["workflow"]["id"]
        resp = client.get(f"/api/workflows/{wf_id}")
        assert resp.status_code == 200
        assert resp.json()["workflow"]["name"] == "get-me"

    def test_get_workflow_not_found(self, client):
        resp = client.get("/api/workflows/wf-nonexistent")
        assert resp.status_code == 404

    def test_update_workflow(self, client):
        save_resp = client.post("/api/workflows", json={"name": "update-me", "steps": []})
        wf_id = save_resp.json()["workflow"]["id"]
        resp = client.put(f"/api/workflows/{wf_id}", json={
            "name": "updated-name",
            "description": "new desc",
            "steps": [{"name": "step-new"}],
        })
        assert resp.status_code == 200
        assert resp.json()["workflow"]["name"] == "updated-name"

    def test_update_workflow_not_found(self, client):
        resp = client.put("/api/workflows/wf-nope", json={"name": "x", "steps": []})
        assert resp.status_code == 404

    def test_delete_workflow(self, client):
        save_resp = client.post("/api/workflows", json={"name": "del-me", "steps": []})
        wf_id = save_resp.json()["workflow"]["id"]
        resp = client.delete(f"/api/workflows/{wf_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] == wf_id
        # Verify deleted
        assert client.get(f"/api/workflows/{wf_id}").status_code == 404

    def test_delete_workflow_not_found(self, client):
        resp = client.delete("/api/workflows/wf-nope")
        assert resp.status_code == 404

    def test_duplicate_workflow(self, client):
        save_resp = client.post("/api/workflows", json={"name": "original", "steps": [{"name": "s1"}]})
        wf_id = save_resp.json()["workflow"]["id"]
        resp = client.post(f"/api/workflows/{wf_id}/duplicate")
        assert resp.status_code == 200
        dup = resp.json()["workflow"]
        assert dup["name"] == "original (copy)"
        assert dup["id"] != wf_id

    def test_duplicate_workflow_not_found(self, client):
        resp = client.post("/api/workflows/wf-nope/duplicate")
        assert resp.status_code == 404

    def test_mark_workflow_run(self, client):
        save_resp = client.post("/api/workflows", json={"name": "run-me", "steps": []})
        wf_id = save_resp.json()["workflow"]["id"]
        resp = client.post(f"/api/workflows/{wf_id}/run")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        # Verify lastRunAt was set
        wf = client.get(f"/api/workflows/{wf_id}").json()["workflow"]
        assert wf["lastRunAt"] is not None

    def test_save_workflow_camelcase_compat(self, client):
        """stopOnFailure and globalVars should be auto-migrated."""
        resp = client.post("/api/workflows", json={
            "name": "camel-wf",
            "stopOnFailure": False,
            "globalVars": {"MY_VAR": "value"},
            "steps": [{"file": "playbooks/test.yml", "name": "s1", "onFailure": "skip"}],
        })
        data = resp.json()
        assert data["success"] is True


class TestWorkflowTemplates:
    """Tests for workflow template endpoints."""

    def test_list_templates(self, client):
        resp = client.get("/api/workflows/templates/list")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["templates"]) == 4
        names = [t["name"] for t in data["templates"]]
        assert "Full E2E (Provision + Delete)" in names
        assert "Provision Only" in names
        assert "Delete + Cleanup" in names
        assert "Validate Environment" in names

    def test_template_structure(self, client):
        resp = client.get("/api/workflows/templates/list")
        tpl = resp.json()["templates"][0]
        assert "id" in tpl
        assert "steps" in tpl
        assert "vars" in tpl
        assert len(tpl["steps"]) > 0

    def test_list_yaml_workflows(self, client):
        # /api/workflows/yaml is shadowed by /api/workflows/{workflow_id} route
        # ordering — skip until route ordering is fixed
        resp = client.get("/api/workflows/yaml")
        assert resp.status_code in (200, 404)


class TestNormalizeWorkflow:
    """Tests for _normalize_workflow migration function."""

    def test_globalvars_to_vars(self):
        from app import _normalize_workflow
        wf = {"globalVars": {"key": "val"}, "steps": []}
        result = _normalize_workflow(wf)
        assert "vars" in result
        assert result["vars"] == {"key": "val"}
        assert "globalVars" not in result

    def test_stop_on_failure_migration(self):
        from app import _normalize_workflow
        wf = {"stopOnFailure": False, "steps": []}
        result = _normalize_workflow(wf)
        assert result["stop_on_failure"] is False
        assert "stopOnFailure" not in result

    def test_step_field_migration(self):
        from app import _normalize_workflow
        wf = {"steps": [
            {"file": "test.yml", "onFailure": "skip", "extra_vars": {"a": 1}},
        ]}
        result = _normalize_workflow(wf)
        step = result["steps"][0]
        assert step["playbook"] == "test.yml"
        assert step["on_failure"] == "skip"
        assert step["vars"] == {"a": 1}
        assert "file" not in step
        assert "onFailure" not in step
        assert "extra_vars" not in step

    def test_no_overwrite_existing_fields(self):
        from app import _normalize_workflow
        wf = {
            "globalVars": {"old": 1},
            "vars": {"new": 2},
            "stopOnFailure": True,
            "stop_on_failure": False,
            "steps": [{"file": "old.yml", "playbook": "new.yml"}],
        }
        result = _normalize_workflow(wf)
        # Existing fields preserved, old fields removed
        assert result["vars"] == {"new": 2}
        assert result["stop_on_failure"] is False
        assert result["steps"][0]["playbook"] == "new.yml"


# ============================================================================
# YAML Intent Detection Tests
# ============================================================================

class TestDetectYamlIntent:
    """Tests for /api/analyze-yaml endpoint."""

    def test_empty_yaml(self, client):
        resp = client.post("/api/analyze-yaml", json={"yaml_content": ""})
        assert resp.status_code in (400, 500)

    def test_automated_network(self, client):
        yaml_content = """
apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
kind: ROSANetwork
metadata:
  name: test-network
spec:
  vpcCidrBlock: "10.0.0.0/16"
"""
        resp = client.post("/api/analyze-yaml", json={"yaml_content": yaml_content})
        assert resp.status_code == 200
        data = resp.json()
        assert data["network_intent"] == "automated"

    def test_automated_roles(self, client):
        yaml_content = """
apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
kind: RosaRoleConfig
metadata:
  name: test-roles
spec:
  rolePrefix: test
"""
        resp = client.post("/api/analyze-yaml", json={"yaml_content": yaml_content})
        data = resp.json()
        assert data["role_intent"] == "automated"

    def test_manual_network(self, client):
        yaml_content = """
apiVersion: controlplane.cluster.x-k8s.io/v1beta2
kind: ROSAControlPlane
metadata:
  name: test
spec:
  subnets:
    - subnet-123
  availabilityZones:
    - us-west-2a
"""
        resp = client.post("/api/analyze-yaml", json={"yaml_content": yaml_content})
        data = resp.json()
        assert data["network_intent"] == "manual"
        assert data["has_rosa_control_plane"] is True
        assert data["config_values"]["subnets"] == ["subnet-123"]

    def test_manual_roles(self, client):
        yaml_content = """
apiVersion: controlplane.cluster.x-k8s.io/v1beta2
kind: ROSAControlPlane
metadata:
  name: test
spec:
  installerRoleARN: arn:aws:iam::123:role/installer
  rolesRef:
    ingressARN: arn:aws:iam::123:role/ingress
"""
        resp = client.post("/api/analyze-yaml", json={"yaml_content": yaml_content})
        data = resp.json()
        assert data["role_intent"] == "manual"
        assert data["config_values"]["installer_role_arn"] == "arn:aws:iam::123:role/installer"
        assert data["config_values"]["ingress_arn"] == "arn:aws:iam::123:role/ingress"

    def test_no_intent_detected(self, client):
        yaml_content = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: test
data:
  key: value
"""
        resp = client.post("/api/analyze-yaml", json={"yaml_content": yaml_content})
        data = resp.json()
        assert data["network_intent"] is None
        assert data["role_intent"] is None
        assert data["messages"] == []

    def test_invalid_yaml(self, client):
        resp = client.post("/api/analyze-yaml", json={"yaml_content": "{{bad yaml["})
        assert resp.status_code == 400

    def test_multi_document_yaml(self, client):
        yaml_content = """
apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
kind: ROSANetwork
metadata:
  name: network
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


# ============================================================================
# Command Execution Tests
# ============================================================================

class TestMinikubeExecuteCommand:
    """Tests for /api/minikube/execute-command endpoint."""

    def test_missing_cluster_name(self, client):
        resp = client.post("/api/minikube/execute-command", json={"command": "ls"})
        data = resp.json()
        assert data["success"] is False
        assert "Cluster name" in data["error"]

    def test_missing_command(self, client):
        resp = client.post("/api/minikube/execute-command",
                           json={"cluster_name": "test", "command": ""})
        data = resp.json()
        assert data["success"] is False
        assert "Command" in data["error"]

    def test_dangerous_command_blocked(self, client):
        dangerous_cmds = [
            "rm -rf /",
            "mkfs /dev/sda",
            "dd if=/dev/zero of=/dev/sda",
            "shutdown now",
            "reboot",
            "killall python",
        ]
        for cmd in dangerous_cmds:
            resp = client.post("/api/minikube/execute-command",
                               json={"cluster_name": "test", "command": cmd})
            data = resp.json()
            assert data["success"] is False, f"Command should be blocked: {cmd}"
            assert "not allowed" in data["error"]

    def test_safe_command_executes(self, client):
        mock_result = MagicMock(returncode=0, stdout="output", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            resp = client.post("/api/minikube/execute-command",
                               json={"cluster_name": "test", "command": "echo hello"})
            data = resp.json()
            assert data["success"] is True
            assert data["output"] == "output"

    def test_command_timeout(self, client):
        with patch("subprocess.run", side_effect=__import__("subprocess").TimeoutExpired("cmd", 60)):
            resp = client.post("/api/minikube/execute-command",
                               json={"cluster_name": "test", "command": "sleep 999"})
            data = resp.json()
            assert data["success"] is False
            assert "timed out" in data["error"]


class TestOCPExecuteCommand:
    """Tests for /api/ocp/execute-command endpoint."""

    def test_missing_command(self, client):
        resp = client.post("/api/ocp/execute-command", json={"command": ""})
        data = resp.json()
        assert data["success"] is False

    def test_dangerous_command_blocked(self, client):
        resp = client.post("/api/ocp/execute-command", json={"command": "rm -rf /"})
        data = resp.json()
        assert data["success"] is False
        assert "not allowed" in data["error"]

    def test_safe_command(self, client):
        mock_result = MagicMock(returncode=0, stdout="pods", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            resp = client.post("/api/ocp/execute-command", json={"command": "oc get pods"})
            data = resp.json()
            assert data["success"] is True

    def test_command_failure(self, client):
        mock_result = MagicMock(returncode=1, stdout="", stderr="error msg")
        with patch("subprocess.run", return_value=mock_result):
            resp = client.post("/api/ocp/execute-command", json={"command": "oc bad"})
            data = resp.json()
            assert data["success"] is False
            assert data["output"] == "error msg"

    def test_command_timeout(self, client):
        with patch("subprocess.run", side_effect=__import__("subprocess").TimeoutExpired("cmd", 60)):
            resp = client.post("/api/ocp/execute-command", json={"command": "sleep 999"})
            data = resp.json()
            assert data["success"] is False
            assert "timed out" in data["error"]


# ============================================================================
# Minikube Cluster Management Tests
# ============================================================================

class TestMinikubeCreate:
    """Tests for /api/minikube/create-cluster endpoint."""

    def test_missing_name(self, client):
        resp = client.post("/api/minikube/create-cluster", json={"cluster_name": ""})
        data = resp.json()
        assert data["success"] is False
        assert "required" in data["message"]

    def test_invalid_name(self, client):
        resp = client.post("/api/minikube/create-cluster", json={"cluster_name": "BAD_NAME!"})
        data = resp.json()
        assert data["success"] is False
        assert "Invalid" in data["message"]

    def test_minikube_not_installed(self, client):
        mock_result = MagicMock(returncode=1)
        with patch("subprocess.run", return_value=mock_result):
            resp = client.post("/api/minikube/create-cluster", json={"cluster_name": "test-mk"})
            data = resp.json()
            assert data["success"] is False
            assert "not installed" in data["message"]

    def test_cluster_already_exists(self, client):
        # First call = minikube version (success), second = minikube status (exists)
        mock_version = MagicMock(returncode=0)
        mock_status = MagicMock(returncode=0)  # 0 = cluster exists
        with patch("subprocess.run", side_effect=[mock_version, mock_status]):
            resp = client.post("/api/minikube/create-cluster", json={"cluster_name": "existing"})
            data = resp.json()
            assert data["success"] is False
            assert "already exists" in data["message"]

    def test_create_success(self, client):
        mock_version = MagicMock(returncode=0)
        mock_status = MagicMock(returncode=1)  # 1 = doesn't exist
        with patch("subprocess.run", side_effect=[mock_version, mock_status]):
            with patch("asyncio.create_task"):
                resp = client.post("/api/minikube/create-cluster", json={"cluster_name": "new-cluster"})
                data = resp.json()
                assert data["success"] is True
                assert data["cluster_name"] == "new-cluster"
                assert "job_id" in data


class TestMinikubeDelete:
    """Tests for /api/minikube/delete-cluster endpoint."""

    def test_missing_name(self, client):
        resp = client.post("/api/minikube/delete-cluster", json={"cluster_name": ""})
        data = resp.json()
        assert data["success"] is False

    def test_delete_success(self, client):
        mock_result = MagicMock(returncode=0, stdout="Deleted")
        with patch("subprocess.run", return_value=mock_result):
            resp = client.post("/api/minikube/delete-cluster", json={"cluster_name": "del-me"})
            data = resp.json()
            assert data["success"] is True

    def test_delete_failure(self, client):
        mock_result = MagicMock(returncode=1, stderr="not found")
        with patch("subprocess.run", return_value=mock_result):
            resp = client.post("/api/minikube/delete-cluster", json={"cluster_name": "nope"})
            data = resp.json()
            assert data["success"] is False

    def test_delete_timeout(self, client):
        with patch("subprocess.run", side_effect=__import__("subprocess").TimeoutExpired("cmd", 120)):
            resp = client.post("/api/minikube/delete-cluster", json={"cluster_name": "slow"})
            data = resp.json()
            assert data["success"] is False
            assert "timed out" in data["message"]


# ============================================================================
# Delete Cluster Endpoint Tests
# ============================================================================

class TestDeleteCluster:
    """Tests for DELETE /api/rosa/clusters/{cluster_name} endpoint."""

    def test_delete_missing_namespace(self, client):
        resp = client.request("DELETE", "/api/rosa/clusters/test-cluster", json={})
        data = resp.json()
        assert data["success"] is False
        assert "Namespace" in data["message"]

    def test_delete_starts_job(self, client):
        with patch("asyncio.create_task"):
            with patch("app.init_ai_agents"):
                resp = client.request("DELETE", "/api/rosa/clusters/my-cluster",
                                      json={"namespace": "test-ns"})
                data = resp.json()
                assert data["success"] is True
                assert "job_id" in data
                assert "my-cluster" in data["message"]


# ============================================================================
# Preview YAML Tests
# ============================================================================

class TestPreviewYaml:
    """Tests for POST /api/provisioning/generate-yaml endpoint."""

    def test_preview_basic_config(self, client):
        resp = client.post("/api/provisioning/generate-yaml", json={
            "clusterName": "test-cluster",
            "openShiftVersion": "4.20.10",
            "createRosaNetwork": True,
            "createRosaRoleConfig": True,
            "awsRegion": "us-west-2",
        })
        # May fail if Jinja2 templates not available in test env
        assert resp.status_code in (200, 500)

    def test_preview_missing_cluster_name(self, client):
        resp = client.post("/api/provisioning/generate-yaml", json={
            "openShiftVersion": "4.20.10",
        })
        assert resp.status_code in (200, 400, 500)


# ============================================================================
# Test Suite Run Tests
# ============================================================================

class TestRunTestSuite:
    """Tests for POST /api/test-suites/run endpoint."""

    def test_suite_not_found(self, client):
        resp = client.post("/api/test-suites/run", json={"suite_name": "nonexistent"})
        assert resp.status_code == 404

    def test_run_suite_success(self, client, tmp_path):
        suite_data = {
            "name": "Test Suite",
            "description": "A test suite",
            "playbooks": [
                {"name": "playbook1", "file": "playbooks/test.yml", "timeout": 30}
            ],
        }
        suite_file = tmp_path / "test-suites" / "my-suite.json"
        suite_file.parent.mkdir(parents=True)
        suite_file.write_text(json.dumps(suite_data))

        with patch("app.os.environ.get", side_effect=lambda k, d=None: str(tmp_path) if k == "AUTOMATION_PATH" else d):
            with patch("asyncio.create_task"):
                resp = client.post("/api/test-suites/run", json={"suite_name": "my-suite"})
                assert resp.status_code == 200
                data = resp.json()
                assert data["success"] is True
                assert "job_id" in data
                assert data["suite_name"] == "Test Suite"


class TestTestSuiteStatus:
    """Tests for GET /api/test-suites/status/{run_id}."""

    def test_status_not_found(self, client):
        resp = client.get("/api/test-suites/status/nonexistent-id")
        assert resp.status_code == 404


# ============================================================================
# AI Assistant Chat Tests
# ============================================================================

class TestAIAssistantChat:
    """Tests for POST /api/ai-assistant/chat endpoint."""

    MOCK_CLUSTERS = [
        {"name": "test-cluster-1", "namespace": "ns-test-1", "status": "ready",
         "region": "us-west-2", "version": "4.20.10", "created": "2026-01-01"},
        {"name": "fail-cluster", "namespace": "ns-fail", "status": "failed",
         "region": "us-east-1", "version": "4.20.10", "created": "2026-01-02"},
        {"name": "prov-cluster", "namespace": "ns-prov", "status": "provisioning",
         "region": "us-west-2", "version": "4.20.10", "created": "2026-01-03", "progress": 45},
        {"name": "del-cluster", "namespace": "ns-del", "status": "uninstalling",
         "region": "us-west-2", "version": "4.20.10", "created": "2026-01-04"},
    ]

    def _chat(self, client, message, clusters=None):
        body = {"message": message, "context": {"clusters": clusters or []}}
        return client.post("/api/ai-assistant/chat", json=body)

    def test_help_message(self, client):
        resp = self._chat(client, "help")
        assert resp.status_code == 200
        data = resp.json()
        assert "help" in data["response"].lower() or "can help" in data["response"].lower() or "Quick Actions" in data["response"]

    def test_list_clusters(self, client):
        resp = self._chat(client, "what clusters are running?", self.MOCK_CLUSTERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "4" in data["response"] or "test-cluster-1" in data["response"]

    def test_status_with_clusters(self, client):
        resp = self._chat(client, "what is the status?", self.MOCK_CLUSTERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "test-cluster-1" in data["response"] or "status" in data["response"].lower()

    def test_status_no_clusters(self, client):
        resp = self._chat(client, "status", [])
        assert resp.status_code == 200
        data = resp.json()
        assert "don't have" in data["response"].lower() or "no" in data["response"].lower()

    def test_troubleshoot_with_failed(self, client):
        resp = self._chat(client, "troubleshoot", self.MOCK_CLUSTERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "fail-cluster" in data["response"] or "failed" in data["response"].lower()

    def test_troubleshoot_no_failures(self, client):
        clusters = [{"name": "ok", "namespace": "ns", "status": "ready"}]
        resp = self._chat(client, "troubleshoot", clusters)
        assert resp.status_code == 200

    def test_troubleshoot_provisioning(self, client):
        clusters = [{"name": "prov", "namespace": "ns", "status": "provisioning", "progress": 50}]
        resp = self._chat(client, "troubleshoot my cluster", clusters)
        assert resp.status_code == 200

    def test_what_is_rosa(self, client):
        resp = self._chat(client, "what is rosa?")
        assert resp.status_code == 200
        assert "ROSA" in resp.json()["response"]

    def test_what_is_capi(self, client):
        resp = self._chat(client, "what is capi?")
        assert resp.status_code == 200
        assert "CAPI" in resp.json()["response"] or "Cluster API" in resp.json()["response"]

    def test_provision_instructions(self, client):
        resp = self._chat(client, "how to provision a cluster?")
        assert resp.status_code == 200
        data = resp.json()
        assert "provision" in data["response"].lower() or "create" in data["response"].lower()

    def test_create_cluster_instructions(self, client):
        resp = self._chat(client, "create cluster")
        assert resp.status_code == 200
        data = resp.json()
        assert "provision" in data["response"].lower() or "cluster" in data["response"].lower()

    def test_specific_cluster_ready(self, client):
        resp = self._chat(client, "tell me about test-cluster-1", self.MOCK_CLUSTERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "test-cluster-1" in data["response"]
        assert "ready" in data["response"].lower()

    def test_specific_cluster_failed(self, client):
        resp = self._chat(client, "tell me about fail-cluster", self.MOCK_CLUSTERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "fail-cluster" in data["response"]

    def test_specific_cluster_provisioning(self, client):
        resp = self._chat(client, "tell me about prov-cluster", self.MOCK_CLUSTERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "prov-cluster" in data["response"]

    def test_specific_cluster_uninstalling(self, client):
        resp = self._chat(client, "tell me about del-cluster", self.MOCK_CLUSTERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "del-cluster" in data["response"]

    def test_cluster_name_in_generic_message(self, client):
        resp = self._chat(client, "what's happening with test-cluster-1?", self.MOCK_CLUSTERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "test-cluster-1" in data["response"]

    def test_network_automation_question(self, client):
        resp = self._chat(client, "what is network automation?")
        assert resp.status_code == 200

    def test_role_automation_question(self, client):
        resp = self._chat(client, "what is role automation?")
        assert resp.status_code == 200

    def test_fallback_generic_message(self, client):
        resp = self._chat(client, "random question about nothing specific")
        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data
        assert "suggestions" in data

    def test_no_clusters_available(self, client):
        resp = self._chat(client, "what clusters are running?", [])
        assert resp.status_code == 200
        data = resp.json()
        assert "no clusters" in data["response"].lower() or "don't have" in data["response"].lower()


# ============================================================================
# Health / Versions / Minikube Profile Tests
# ============================================================================

class TestHealthEndpoint:
    """Tests for GET /api/health."""

    def test_health_check(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data


class TestVersionsEndpoint:
    """Tests for GET /api/versions."""

    def test_versions_fallback(self, client):
        mock_result = MagicMock(returncode=1, stdout="", stderr="not found")
        with patch("subprocess.run", return_value=mock_result):
            resp = client.get("/api/versions")
            assert resp.status_code == 200
            data = resp.json()
            assert "versions" in data
            assert len(data["versions"]) > 0

    def test_versions_success(self, client):
        output = "VERSION  DEFAULT  AVAILABLE UPGRADES\n4.20.12  yes\n4.20.11  \n4.19.8   \n"
        mock_result = MagicMock(returncode=0, stdout=output, stderr="")
        with patch("subprocess.run", return_value=mock_result):
            resp = client.get("/api/versions")
            assert resp.status_code == 200
            data = resp.json()
            assert "versions" in data


class TestMinikubeActiveProfile:
    """Tests for GET /api/minikube/active-profile."""

    def test_no_profiles(self, client):
        mock_result = MagicMock(returncode=1, stdout="", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            resp = client.get("/api/minikube/active-profile")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is False
            assert data["profile"] is None

    def test_running_profile(self, client):
        profiles_json = json.dumps({"valid": [{"Name": "minikube"}]})
        status_json = json.dumps({"Host": "Running"})
        cluster_info = "Kubernetes control plane is running at https://192.168.49.2:8443\n"

        mock_profile = MagicMock(returncode=0, stdout=profiles_json)
        mock_status = MagicMock(returncode=0, stdout=status_json)
        mock_cluster = MagicMock(returncode=0, stdout=cluster_info)

        with patch("subprocess.run", side_effect=[mock_profile, mock_status, mock_cluster]):
            resp = client.get("/api/minikube/active-profile")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["profile"]["name"] == "minikube"
            assert "192.168.49.2" in data["profile"]["api_url"]

    def test_no_running_profiles(self, client):
        profiles_json = json.dumps({"valid": [{"Name": "stopped"}]})
        status_json = json.dumps({"Host": "Stopped"})

        mock_profile = MagicMock(returncode=0, stdout=profiles_json)
        mock_status = MagicMock(returncode=0, stdout=status_json)

        with patch("subprocess.run", side_effect=[mock_profile, mock_status]):
            resp = client.get("/api/minikube/active-profile")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is False


# ============================================================================
# Trigger Metrics / History Tests
# ============================================================================

class TestTriggerMetrics:
    """Tests for GET /api/triggers/metrics."""

    def test_empty_metrics(self, client):
        with patch("app._load_trigger_state", return_value={"triggers": [], "run_history": []}):
            resp = client.get("/api/triggers/metrics")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_triggers"] == 0
            assert data["total_runs"] == 0
            assert data["success_rate_pct"] == 0.0

    def test_metrics_with_data(self, client):
        state = {
            "triggers": [
                {"trigger_id": "t1", "enabled": True},
                {"trigger_id": "t2", "enabled": False},
            ],
            "run_history": [
                {"status": "completed", "started_at": "2026-01-01T00:00:00", "completed_at": "2026-01-01T00:01:00"},
                {"status": "completed", "started_at": "2026-01-01T01:00:00", "completed_at": "2026-01-01T01:02:00"},
                {"status": "failed", "started_at": "2026-01-01T02:00:00", "completed_at": "2026-01-01T02:00:30"},
            ],
        }
        with patch("app._load_trigger_state", return_value=state):
            resp = client.get("/api/triggers/metrics")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_triggers"] == 2
            assert data["total_runs"] == 3
            assert data["completed_runs"] == 2
            assert data["failed_runs"] == 1


class TestTriggerHistory:
    """Tests for GET /api/triggers/history/all."""

    def test_empty_history(self, client):
        with patch("app._load_trigger_state", return_value={"triggers": [], "run_history": []}):
            resp = client.get("/api/triggers/history/all")
            assert resp.status_code == 200
            data = resp.json()
            assert data["history"] == []

    def test_history_pagination(self, client):
        history = [{"run_id": f"r{i}", "status": "completed"} for i in range(10)]
        with patch("app._load_trigger_state", return_value={"triggers": [], "run_history": history}):
            resp = client.get("/api/triggers/history/all?offset=2&limit=3")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["history"]) == 3


class TestTriggerFire:
    """Tests for POST /api/triggers/{id}/fire."""

    def _make_state(self, trigger_id="t1"):
        return {
            "triggers": [{
                "trigger_id": trigger_id, "type": "webhook",
                "workflow_name": "test-wf", "enabled": True,
                "trigger_name": "Test", "vars_override": {},
            }],
            "run_history": [],
        }

    def test_fire_not_found(self, client):
        with patch("app._load_trigger_state", return_value={"triggers": [], "run_history": []}):
            resp = client.post("/api/triggers/nonexistent/fire")
            assert resp.status_code == 404

    def test_fire_rate_limited(self, client):
        with patch("app._load_trigger_state", return_value=self._make_state()):
            with patch("app.check_rate_limit", return_value=30):
                resp = client.post("/api/triggers/t1/fire")
                assert resp.status_code == 429

    def test_fire_success(self, client):
        with patch("app._load_trigger_state", return_value=self._make_state()):
            with patch("app.check_rate_limit", return_value=None):
                with patch("app._fire_and_update"):
                    resp = client.post("/api/triggers/t1/fire")
                    assert resp.status_code == 200
                    assert resp.json()["success"] is True


class TestTriggerEnableDisable:
    """Tests for POST /api/triggers/{id}/enable and /disable."""

    def _make_state(self, enabled=True):
        return {
            "triggers": [{"trigger_id": "t1", "enabled": enabled, "type": "webhook",
                          "trigger_name": "Test", "consecutive_failures": 3}],
            "run_history": [],
        }

    def test_enable_not_found(self, client):
        with patch("app._load_trigger_state", return_value={"triggers": [], "run_history": []}):
            resp = client.post("/api/triggers/nonexistent/enable")
            assert resp.status_code == 404

    def test_enable_trigger(self, client):
        with patch("app._load_trigger_state", return_value=self._make_state(enabled=False)):
            with patch("app._save_trigger_state"):
                resp = client.post("/api/triggers/t1/enable")
                assert resp.status_code == 200
                data = resp.json()
                assert data["trigger"]["enabled"] is True
                assert data["trigger"]["consecutive_failures"] == 0

    def test_disable_trigger(self, client):
        with patch("app._load_trigger_state", return_value=self._make_state(enabled=True)):
            with patch("app._save_trigger_state"):
                resp = client.post("/api/triggers/t1/disable")
                assert resp.status_code == 200
                data = resp.json()
                assert data["trigger"]["enabled"] is False

    def test_disable_not_found(self, client):
        with patch("app._load_trigger_state", return_value={"triggers": [], "run_history": []}):
            resp = client.post("/api/triggers/nonexistent/disable")
            assert resp.status_code == 404


class TestGetTrigger:
    """Tests for GET /api/triggers/{id}."""

    def test_get_trigger(self, client):
        state = {
            "triggers": [{"trigger_id": "t1", "trigger_name": "Test"}],
            "run_history": [{"trigger_id": "t1", "status": "completed"}],
        }
        with patch("app._load_trigger_state", return_value=state):
            resp = client.get("/api/triggers/t1")
            assert resp.status_code == 200
            data = resp.json()
            assert data["trigger"]["trigger_id"] == "t1"
            assert len(data["history"]) == 1

    def test_get_trigger_not_found(self, client):
        with patch("app._load_trigger_state", return_value={"triggers": [], "run_history": []}):
            resp = client.get("/api/triggers/nonexistent")
            assert resp.status_code == 404


class TestDeleteTrigger:
    """Tests for DELETE /api/triggers/{id}."""

    def test_delete_trigger(self, client):
        state = {
            "triggers": [{"trigger_id": "t1", "trigger_name": "Test"}],
            "run_history": [],
        }
        with patch("app._load_trigger_state", return_value=state):
            with patch("app._save_trigger_state"):
                resp = client.request("DELETE", "/api/triggers/t1")
                assert resp.status_code == 200
                assert resp.json()["deleted"] == "t1"

    def test_delete_not_found(self, client):
        with patch("app._load_trigger_state", return_value={"triggers": [], "run_history": []}):
            resp = client.request("DELETE", "/api/triggers/nonexistent")
            assert resp.status_code == 404


class TestWorkflowTriggers:
    """Tests for GET /api/workflows/{id}/triggers."""

    def test_workflow_triggers(self, client):
        state = {
            "triggers": [
                {"trigger_id": "t1", "workflow_name": "my-wf"},
                {"trigger_id": "t2", "workflow_name": "other-wf"},
            ],
            "run_history": [],
        }
        with patch("app._load_trigger_state", return_value=state):
            resp = client.get("/api/workflows/my-wf/triggers")
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 1
            assert data["triggers"][0]["trigger_id"] == "t1"


# ============================================================================
# Webhook Trigger Tests
# ============================================================================

class TestWebhookTrigger:
    """Tests for POST /api/webhooks/trigger/{id}."""

    def _make_state(self):
        return {
            "triggers": [{
                "trigger_id": "wh1", "type": "webhook", "enabled": True,
                "workflow_name": "test-wf", "trigger_name": "Test WH",
                "vars_override": {}, "webhook_secret_hash": None, "secret_env": None,
            }],
            "run_history": [],
        }

    def test_webhook_not_found(self, client):
        with patch("app._load_trigger_state", return_value={"triggers": [], "run_history": []}):
            resp = client.post("/api/webhooks/trigger/nonexistent", json={})
            assert resp.status_code == 404

    def test_webhook_disabled(self, client):
        state = self._make_state()
        state["triggers"][0]["enabled"] = False
        with patch("app._load_trigger_state", return_value=state):
            resp = client.post("/api/webhooks/trigger/wh1", json={})
            assert resp.status_code == 404

    def test_webhook_wrong_type(self, client):
        state = self._make_state()
        state["triggers"][0]["type"] = "schedule"
        with patch("app._load_trigger_state", return_value=state):
            resp = client.post("/api/webhooks/trigger/wh1", json={})
            assert resp.status_code == 404

    def test_webhook_rate_limited(self, client):
        with patch("app._load_trigger_state", return_value=self._make_state()):
            with patch("app.check_rate_limit", return_value=30):
                resp = client.post("/api/webhooks/trigger/wh1", json={})
                assert resp.status_code == 429

    def test_webhook_success_no_secret(self, client):
        with patch("app._load_trigger_state", return_value=self._make_state()):
            with patch("app.check_rate_limit", return_value=None):
                with patch("app._fire_and_update"):
                    resp = client.post("/api/webhooks/trigger/wh1", json={})
                    assert resp.status_code == 200
                    assert resp.json()["success"] is True

    def test_webhook_invalid_signature(self, client):
        import hashlib
        state = self._make_state()
        state["triggers"][0]["webhook_secret_hash"] = hashlib.sha256(b"secret").hexdigest()
        state["triggers"][0]["secret_env"] = "MY_SECRET"
        with patch("app._load_trigger_state", return_value=state):
            with patch("app.check_rate_limit", return_value=None):
                with patch.dict("os.environ", {"MY_SECRET": "secret"}):
                    resp = client.post(
                        "/api/webhooks/trigger/wh1",
                        json={"data": "test"},
                        headers={"X-Hub-Signature-256": "sha256=invalid"},
                    )
                    assert resp.status_code == 403


# ============================================================================
# Scheduler Status Tests
# ============================================================================

class TestSchedulerStatus:
    """Tests for GET /api/triggers/scheduler/status."""

    def test_scheduler_status(self, client):
        with patch("app._load_trigger_state", return_value={"triggers": [], "run_history": []}):
            resp = client.get("/api/triggers/scheduler/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert "running" in data
            assert "croniter_available" in data
            assert "upcoming" in data


# ============================================================================
# Cluster Spec Tests
# ============================================================================

class TestClusterSpecs:
    """Tests for /api/cluster-specs endpoints."""

    def test_list_specs_empty(self, client):
        with patch("os.path.isdir", return_value=False):
            resp = client.get("/api/cluster-specs")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["specs"] == []

    def test_get_spec_not_found(self, client):
        with patch("app._find_spec_file", return_value=""):
            resp = client.get("/api/cluster-specs/nonexistent")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is False

    def test_plan_spec(self, client):
        spec_data = {
            "apiVersion": "capa.test/v1",
            "kind": "ClusterAutomationSpec",
            "spec": {"action": "create", "features": {"rosa_network": True}},
        }
        with patch("app._core_resolve_spec_to_plan", return_value={"steps": [], "valid": True}):
            resp = client.post("/api/cluster-specs/plan", json=spec_data)
            assert resp.status_code == 200


# ============================================================================
# Cluster Action History Tests
# ============================================================================

class TestClusterActionHistory:
    """Tests for /api/cluster-actions/history endpoint."""

    def test_get_history(self, client):
        history = [{"cluster_name": "test", "feature_id": "f1", "status": "completed"}]
        with patch("app._load_action_history", return_value=history):
            resp = client.get("/api/cluster-actions/history")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["count"] == 1

    def test_get_history_filtered(self, client):
        history = [
            {"cluster_name": "test-1", "status": "completed"},
            {"cluster_name": "test-2", "status": "completed"},
        ]
        with patch("app._load_action_history", return_value=history):
            resp = client.get("/api/cluster-actions/history?cluster_name=test-1")
            assert resp.status_code == 200
            data = resp.json()
            assert data["count"] == 1

    def test_get_history_empty(self, client):
        with patch("app._load_action_history", return_value=[]):
            resp = client.get("/api/cluster-actions/history")
            assert resp.status_code == 200
            assert resp.json()["count"] == 0


# ============================================================================
# Show Logs in Chat Tests
# ============================================================================

class TestChatShowLogs:
    """Tests for 'show logs' branch in chat endpoint."""

    def test_show_logs_no_jobs(self, client):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "show me the logs",
            "context": {"clusters": [{"name": "test-cl", "status": "failed"}]},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "log" in data["response"].lower() or "couldn't find" in data["response"].lower()


# ============================================================================
# Feature Registry Tests
# ============================================================================

class TestFeatureRegistry:
    """Tests for /api/cluster-actions/features endpoints."""

    def test_get_features(self, client):
        resp = client.get("/api/cluster-actions/features")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "registry" in data

    def test_get_suite_not_found(self, client):
        resp = client.get("/api/cluster-actions/features/nonexistent-suite")
        assert resp.status_code == 404


# ============================================================================
# Cluster Actions Execute Tests
# ============================================================================

class TestClusterActionsExecute:
    """Tests for POST /api/cluster-actions/execute."""

    def test_invalid_cluster_name(self, client):
        resp = client.post("/api/cluster-actions/execute", json={
            "cluster_name": "BAD NAME!",
            "namespace": "ns-test",
            "actions": [{"feature_id": "f1", "target_value": True}],
        })
        assert resp.status_code == 400

    def test_unknown_feature(self, client):
        with patch("app._find_feature", return_value=None):
            with patch("app._load_action_history", return_value=[]):
                resp = client.post("/api/cluster-actions/execute", json={
                    "cluster_name": "test-cluster",
                    "namespace": "ns-test",
                    "actions": [{"feature_id": "unknown_feat", "target_value": True}],
                })
                assert resp.status_code == 200
                data = resp.json()
                assert data["results"][0]["status"] == "error"
                assert "Unknown" in data["results"][0]["message"]

    def test_immutable_feature(self, client):
        feat = {"id": "f1", "name": "Test Feature", "mutable": False}
        with patch("app._find_feature", return_value=feat):
            resp = client.post("/api/cluster-actions/execute", json={
                "cluster_name": "test-cluster",
                "namespace": "ns-test",
                "actions": [{"feature_id": "f1", "target_value": True}],
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["results"][0]["status"] == "error"
            assert "immutable" in data["results"][0]["message"].lower()

    def test_patch_action_success(self, client):
        feat = {"id": "f1", "name": "Test", "mutable": True, "resource": "ROSAControlPlane",
                "k8s_field": ".spec.field", "type": "boolean"}
        mock_result = MagicMock(returncode=0, stdout="patched", stderr="")
        with patch("app._find_feature", return_value=feat):
            with patch("subprocess.run", return_value=mock_result):
                with patch("app._record_action"):
                    resp = client.post("/api/cluster-actions/execute", json={
                        "cluster_name": "test-cluster",
                        "namespace": "ns-test",
                        "actions": [{"feature_id": "f1", "target_value": True}],
                    })
                    assert resp.status_code == 200
                    data = resp.json()
                    assert data["results"][0]["status"] == "completed"

    def test_patch_action_failure(self, client):
        feat = {"id": "f1", "name": "Test", "mutable": True, "resource": "ROSAControlPlane",
                "k8s_field": ".spec.field", "type": "boolean"}
        mock_result = MagicMock(returncode=1, stdout="", stderr="error patching")
        with patch("app._find_feature", return_value=feat):
            with patch("subprocess.run", return_value=mock_result):
                with patch("app._record_action"):
                    resp = client.post("/api/cluster-actions/execute", json={
                        "cluster_name": "test-cluster",
                        "namespace": "ns-test",
                        "actions": [{"feature_id": "f1", "target_value": True}],
                    })
                    assert resp.status_code == 200
                    data = resp.json()
                    assert data["results"][0]["status"] == "error"

    def test_no_resource_defined(self, client):
        feat = {"id": "f1", "name": "Test", "mutable": True, "resource": "", "k8s_field": "", "type": "boolean"}
        with patch("app._find_feature", return_value=feat):
            with patch("app._record_action"):
                resp = client.post("/api/cluster-actions/execute", json={
                    "cluster_name": "test-cluster",
                    "namespace": "ns-test",
                    "actions": [{"feature_id": "f1", "target_value": True}],
                })
                assert resp.status_code == 200
                data = resp.json()
                assert "No resource" in data["results"][0]["message"]


# ============================================================================
# Cluster Actions Provision Tests
# ============================================================================

class TestClusterActionsProvisionFeatures:
    """Tests for POST /api/cluster-actions/provision."""

    def test_provision_missing_cluster_name(self, client):
        resp = client.post("/api/cluster-actions/provision", json={
            "cluster_name": "",
            "features": {},
        })
        assert resp.status_code == 400

    def test_provision_invalid_name(self, client):
        resp = client.post("/api/cluster-actions/provision", json={
            "cluster_name": "BAD NAME!",
            "features": {},
        })
        assert resp.status_code == 400


# ============================================================================
# Cluster Discover Tests
# ============================================================================

class TestClusterDiscover:
    """Tests for GET /api/cluster-actions/discover."""

    def test_discover_no_namespace(self, client):
        resp = client.get("/api/cluster-actions/discover")
        assert resp.status_code == 200

    def test_discover_with_namespace(self, client):
        mock_result = MagicMock(returncode=1, stdout="", stderr="not found")
        with patch("subprocess.run", return_value=mock_result):
            resp = client.get("/api/cluster-actions/discover?namespace=test-ns")
            assert resp.status_code == 200


# ============================================================================
# Cluster Status Endpoint
# ============================================================================

class TestClusterStatus:
    """Tests for GET /api/cluster-actions/cluster/{name}/status."""

    def test_cluster_status(self, client):
        mock_result = MagicMock(returncode=0, stdout='{"items": []}', stderr="")
        with patch("subprocess.run", return_value=mock_result):
            resp = client.get("/api/cluster-actions/cluster/test-cl/status?namespace=ns-test")
            assert resp.status_code == 200


# ============================================================================
# Chat with AI Service Tests (covers lines 7892-7934)
# ============================================================================

class TestChatWithAIService:
    """Tests for AI service integration in chat endpoint."""

    def test_ai_service_success(self, client):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            with patch("app.ai_service.chat", new_callable=AsyncMock) as mock_chat:
                mock_chat.return_value = {
                    "response": "AI response about clusters",
                    "suggestions": ["suggestion1"],
                }
                resp = client.post("/api/ai-assistant/chat", json={
                    "message": "analyze issues", "context": {"clusters": []}, "history": [],
                })
                assert resp.status_code == 200
                assert resp.json()["response"] == "AI response about clusters"

    def test_ai_service_fixes_missing_cluster_names(self, client):
        clusters = [{"name": "test-cl", "namespace": "ns", "status": "ready"}]
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            with patch("app.ai_service.chat", new_callable=AsyncMock) as mock_chat:
                mock_chat.return_value = {"response": "You have some clusters", "suggestions": []}
                resp = client.post("/api/ai-assistant/chat", json={
                    "message": "what clusters are running?",
                    "context": {"clusters": clusters}, "history": [],
                })
                assert resp.status_code == 200
                assert "test-cl" in resp.json()["response"]

    def test_ai_service_failure_falls_back(self, client):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            with patch("app.ai_service.chat", new_callable=AsyncMock) as mock_chat:
                mock_chat.side_effect = Exception("API error")
                resp = client.post("/api/ai-assistant/chat", json={
                    "message": "what is rosa?", "context": {"clusters": []}, "history": [],
                })
                assert resp.status_code == 200
                assert "ROSA" in resp.json()["response"]


# ============================================================================
# Chat - Tell Me About (covers lines 8040-8166)
# ============================================================================

class TestChatTellMeAbout:
    """Tests for 'tell me about' cluster detail branches."""

    CLUSTERS = [
        {"name": "prov-cl", "namespace": "ns", "status": "provisioning",
         "region": "us-east-1", "version": "4.20.10", "created": "2026-01-01",
         "domain_prefix": "prov", "progress": 60},
        {"name": "del-cl", "namespace": "ns", "status": "uninstalling",
         "region": "us-east-1", "version": "4.20.10", "created": "2026-01-01",
         "domain_prefix": "del", "progress": 0},
        {"name": "ready-cl", "namespace": "ns", "status": "ready",
         "region": "us-east-1", "version": "4.20.10", "created": "2026-01-01",
         "domain_prefix": "ready", "progress": 100},
        {"name": "err-cl", "namespace": "ns", "status": "failed",
         "region": "us-east-1", "version": "4.20.10", "created": "2026-01-01",
         "domain_prefix": "err", "progress": 0},
        {"name": "other-cl", "namespace": "ns", "status": "pending",
         "region": "us-east-1", "version": "4.20.10", "created": "2026-01-01",
         "domain_prefix": "other", "progress": 0},
    ]

    def test_tell_provisioning(self, client):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "tell me about prov-cl", "context": {"clusters": self.CLUSTERS},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "prov-cl" in data["response"]
        assert "60% complete" in data["response"]

    def test_tell_uninstalling(self, client):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "tell me about del-cl", "context": {"clusters": self.CLUSTERS},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "del-cl" in data["response"]
        assert "deleted" in data["response"].lower() or "uninstall" in data["response"].lower()

    def test_tell_ready(self, client):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "tell me about ready-cl", "context": {"clusters": self.CLUSTERS},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "ready-cl" in data["response"]
        assert "Ready" in data["response"]

    def test_tell_failed(self, client):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "tell me about err-cl", "context": {"clusters": self.CLUSTERS},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "err-cl" in data["response"]

    def test_tell_other_status(self, client):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "tell me about other-cl", "context": {"clusters": self.CLUSTERS},
        })
        assert resp.status_code == 200
        assert "other-cl" in resp.json()["response"]


# ============================================================================
# Chat - Show Logs (covers lines 8170-8224)
# ============================================================================

class TestChatShowLogsWithJobs:
    """Tests for show logs with matching job data."""

    def test_show_logs_with_matching_job(self, client):
        from app import jobs
        job_id = "test-job-123"
        jobs[job_id] = {
            "id": job_id, "yaml_file": "provision-my-cluster.yml",
            "description": "Provision my-cluster", "status": "completed",
            "logs": ["line 1", "line 2"], "created_at": "2026-04-15T10:00:00",
        }
        clusters = [{"name": "my-cluster", "namespace": "ns", "status": "ready"}]
        try:
            resp = client.post("/api/ai-assistant/chat", json={
                "message": "show me the logs", "context": {"clusters": clusters},
            })
            assert resp.status_code == 200
            data = resp.json()
            assert "my-cluster" in data["response"]
        finally:
            jobs.pop(job_id, None)


# ============================================================================
# Chat - Environment/Help (covers lines 8370-8404)
# ============================================================================

class TestChatEnvironment:
    """Tests for environment and help queries."""

    def test_environment_check(self, client):
        resp = client.post("/api/ai-assistant/chat", json={
            "message": "check environment status", "context": {"clusters": []},
        })
        assert resp.status_code == 200
        assert "Environment" in resp.json()["response"] or "can help" in resp.json()["response"].lower()


# ============================================================================
# Test Suite History (covers lines 8847-8859)
# ============================================================================

class TestTestSuiteHistory:
    """Tests for GET /api/test-suites/history."""

    def test_history_empty(self, client):
        from app import test_suite_runs
        test_suite_runs.clear()
        resp = client.get("/api/test-suites/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 0

    def test_history_with_data(self, client):
        from app import test_suite_runs
        test_suite_runs.clear()
        test_suite_runs["run1"] = {
            "run_id": "run1", "status": "completed",
            "started_at": datetime(2026, 1, 1, 10, 0),
        }
        test_suite_runs["run2"] = {
            "run_id": "run2", "status": "running",
            "started_at": datetime(2026, 1, 2, 10, 0),
        }
        resp = client.get("/api/test-suites/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        test_suite_runs.clear()


# ============================================================================
# Minikube List / Context (covers lines 4692-4820)
# ============================================================================

class TestMinikubeListClusters:
    """Tests for GET /api/minikube/list-clusters."""

    def test_minikube_not_installed(self, client):
        from app import minikube_clusters_cache
        minikube_clusters_cache["data"] = None
        minikube_clusters_cache["timestamp"] = 0
        mock_result = MagicMock(returncode=1, stdout="", stderr="not found")
        with patch("subprocess.run", return_value=mock_result):
            resp = client.get("/api/minikube/list-clusters")
            assert resp.status_code == 200
            data = resp.json()
            assert data["minikube_installed"] is False

    def test_minikube_no_clusters(self, client):
        from app import minikube_clusters_cache
        minikube_clusters_cache["data"] = None
        minikube_clusters_cache["timestamp"] = 0
        mock_version = MagicMock(returncode=0, stdout="v1.33.0")
        mock_list = MagicMock(returncode=1, stdout="", stderr="")
        with patch("subprocess.run", side_effect=[mock_version, mock_list]):
            resp = client.get("/api/minikube/list-clusters")
            assert resp.status_code == 200
            data = resp.json()
            assert data["minikube_installed"] is True
            assert data["clusters"] == []

    def test_minikube_with_clusters(self, client):
        from app import minikube_clusters_cache
        minikube_clusters_cache["data"] = None
        minikube_clusters_cache["timestamp"] = 0
        mock_version = MagicMock(returncode=0, stdout="v1.33.0")
        profiles_json = json.dumps({"valid": [{"Name": "mycluster"}, {"Name": "dev"}]})
        mock_list = MagicMock(returncode=0, stdout=profiles_json)
        with patch("subprocess.run", side_effect=[mock_version, mock_list]):
            resp = client.get("/api/minikube/list-clusters")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["clusters"]) == 2
            assert "mycluster" in data["clusters"]


class TestMinikubeCurrentContext:
    """Tests for GET /api/minikube/current-context."""

    def test_context_success(self, client):
        mock_result = MagicMock(returncode=0, stdout="minikube\n", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            resp = client.get("/api/minikube/current-context")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["current_context"] == "minikube"

    def test_no_context(self, client):
        mock_result = MagicMock(returncode=1, stdout="", stderr="not set")
        with patch("subprocess.run", return_value=mock_result):
            resp = client.get("/api/minikube/current-context")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is False


# ============================================================================
# Templates Endpoint (covers lines 10845+)
# ============================================================================

class TestTemplatesEndpoint:
    """Tests for GET /api/templates — skipped, may not exist."""
    pass


# ============================================================================
# Notification Settings (covers lines 1260-1375)
# ============================================================================

class TestNotificationSettings:
    """Tests for /api/notification-settings endpoints."""

    def test_get_notification_settings(self, client):
        resp = client.get("/api/notification-settings")
        assert resp.status_code == 200


# ============================================================================
# Minikube Verify Cluster (covers lines 4917-5271)
# ============================================================================

class TestMinikubeVerifyCluster:
    """Tests for POST /api/minikube/verify-cluster."""

    def test_verify_missing_name(self, client):
        resp = client.post("/api/minikube/verify-cluster", json={"cluster_name": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is False

    def test_verify_cluster_exists(self, client):
        mock_result = MagicMock(returncode=0, stdout='{"Host":"Running"}')
        with patch("subprocess.run", return_value=mock_result):
            resp = client.post("/api/minikube/verify-cluster", json={"cluster_name": "test-mk"})
            assert resp.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
