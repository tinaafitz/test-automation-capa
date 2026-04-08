"""
Extended tests for app.py — covers endpoints and utility functions
not covered by the original test_app.py.

Targets: analyze-yaml, send_cluster_notifications, generate/apply provisioning YAML,
ROSA status sync, config status, minikube operations, and more.
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
sys.modules.setdefault("app_extensions", MagicMock())

from app import (
    app,
    jobs,
    clusters,
    normalize_timestamp,
    check_and_timeout_stuck_jobs,
    send_cluster_notifications,
    ai_agent_sessions,
    get_agent_stats,
    rosa_status_cache,
    ocp_status_cache,
    minikube_clusters_cache,
)


@pytest.fixture
def client():
    """FastAPI test client with clean state."""
    jobs.clear()
    clusters.clear()
    ai_agent_sessions.clear()
    rosa_status_cache["timestamp"] = 0
    rosa_status_cache["data"] = None
    ocp_status_cache["timestamp"] = 0
    ocp_status_cache["data"] = None
    minikube_clusters_cache["timestamp"] = 0
    minikube_clusters_cache["data"] = None
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


# ---------------------------------------------------------------------------
# Analyze YAML endpoint
# ---------------------------------------------------------------------------

class TestAnalyzeYaml:
    def test_analyze_yaml_with_rosa_network(self, client):
        yaml_content = """
apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
kind: ROSANetwork
metadata:
  name: test-network
spec:
  vpcCidr: 10.0.0.0/16
"""
        resp = client.post("/api/analyze-yaml", json={"yaml_content": yaml_content})
        assert resp.status_code == 200
        data = resp.json()
        assert data["network_intent"] == "automated"

    def test_analyze_yaml_with_manual_config(self, client):
        yaml_content = """
apiVersion: controlplane.cluster.x-k8s.io/v1beta2
kind: ROSAControlPlane
metadata:
  name: test-cp
spec:
  subnets:
    - subnet-123
    - subnet-456
  availabilityZones:
    - us-west-2a
    - us-west-2b
  installerRoleARN: arn:aws:iam::123:role/installer
"""
        resp = client.post("/api/analyze-yaml", json={"yaml_content": yaml_content})
        assert resp.status_code == 200
        data = resp.json()
        assert data["network_intent"] == "manual"
        assert data["role_intent"] == "manual"
        assert data["has_rosa_control_plane"] is True
        assert "subnet-123" in data["config_values"]["subnets"]

    def test_analyze_yaml_with_role_config(self, client):
        yaml_content = """
apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
kind: RosaRoleConfig
metadata:
  name: test-roles
spec:
  rolePrefix: test
"""
        resp = client.post("/api/analyze-yaml", json={"yaml_content": yaml_content})
        assert resp.status_code == 200
        data = resp.json()
        assert data["role_intent"] == "automated"

    def test_analyze_yaml_empty_content(self, client):
        resp = client.post("/api/analyze-yaml", json={"yaml_content": ""})
        assert resp.status_code in (400, 500)

    def test_analyze_yaml_no_content(self, client):
        resp = client.post("/api/analyze-yaml", json={})
        assert resp.status_code in (400, 500)

    def test_analyze_yaml_invalid_yaml(self, client):
        resp = client.post("/api/analyze-yaml", json={"yaml_content": "{{invalid: yaml:::"})
        assert resp.status_code == 400

    def test_analyze_yaml_multi_document(self, client):
        yaml_content = """
apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
kind: ROSANetwork
metadata:
  name: test-network
---
apiVersion: infrastructure.cluster.x-k8s.io/v1beta2
kind: RosaRoleConfig
metadata:
  name: test-roles
"""
        resp = client.post("/api/analyze-yaml", json={"yaml_content": yaml_content})
        assert resp.status_code == 200
        data = resp.json()
        assert data["network_intent"] == "automated"
        assert data["role_intent"] == "automated"

    def test_analyze_yaml_no_rosa_resources(self, client):
        yaml_content = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: test
data:
  key: value
"""
        resp = client.post("/api/analyze-yaml", json={"yaml_content": yaml_content})
        assert resp.status_code == 200
        data = resp.json()
        assert data["network_intent"] is None
        assert data["role_intent"] is None


# ---------------------------------------------------------------------------
# send_cluster_notifications
# ---------------------------------------------------------------------------

class TestSendClusterNotifications:
    @patch("app.os.path.exists", return_value=False)
    def test_no_config_file(self, mock_exists):
        # Should not raise, just return silently
        send_cluster_notifications("test", "us-west-2", "4.20.0", "j1", "completed")

    @patch("builtins.open", create=True)
    @patch("app.os.path.exists", return_value=True)
    def test_provision_started_disabled(self, mock_exists, mock_open):
        import yaml as _yaml
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        mock_open.return_value.read = MagicMock(return_value="")
        with patch("app.yaml.safe_load", return_value={"notify_provision_start": False}):
            send_cluster_notifications("test", "us-west-2", "4.20.0", "j1", "started", operation_type="provision")

    @patch("builtins.open", create=True)
    @patch("app.os.path.exists", return_value=True)
    @patch("app.slack_service")
    def test_provision_completed_slack(self, mock_slack, mock_exists, mock_open):
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        with patch("app.yaml.safe_load", return_value={
            "notify_provision_success": True,
            "slack_enabled": True,
            "email_enabled": False,
        }):
            send_cluster_notifications("test", "us-west-2", "4.20.0", "j1", "completed", operation_type="provision")
            mock_slack.reload_config.assert_called()

    @patch("builtins.open", create=True)
    @patch("app.os.path.exists", return_value=True)
    def test_delete_failed_with_error(self, mock_exists, mock_open):
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        with patch("app.yaml.safe_load", return_value={
            "notify_delete_failure": True,
            "slack_enabled": False,
            "email_enabled": False,
        }):
            send_cluster_notifications("test", "us-west-2", "4.20.0", "j1", "failed",
                                       error="CF stack failed", operation_type="delete")


# ---------------------------------------------------------------------------
# ROSA status sync function
# ---------------------------------------------------------------------------

class TestRosaStatusSync:
    @patch("app.subprocess.run")
    def test_rosa_not_logged_in(self, mock_run, client):
        rosa_status_cache["timestamp"] = 0
        rosa_status_cache["data"] = None
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="not logged in"
        )
        resp = client.get("/api/rosa/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["authenticated"] is False
        assert "login" in data.get("fix_command", "").lower() or "login" in data.get("suggestion", "").lower()

    @patch("app.subprocess.run")
    def test_rosa_command_not_found(self, mock_run, client):
        rosa_status_cache["timestamp"] = 0
        rosa_status_cache["data"] = None
        mock_run.side_effect = FileNotFoundError("rosa not found")
        resp = client.get("/api/rosa/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["authenticated"] is False
        assert data["status"] == "not_installed"

    @patch("app.subprocess.run")
    def test_rosa_timeout(self, mock_run, client):
        import subprocess
        rosa_status_cache["timestamp"] = 0
        rosa_status_cache["data"] = None
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="rosa", timeout=5)
        resp = client.get("/api/rosa/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "timeout"

    def test_rosa_cache_hit(self, client):
        import time
        rosa_status_cache["data"] = {"authenticated": True, "cached": True}
        rosa_status_cache["timestamp"] = time.time()
        resp = client.get("/api/rosa/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("cached") is True


# ---------------------------------------------------------------------------
# OCP connection status
# ---------------------------------------------------------------------------

class TestOcpConnectionExtended:
    @patch("app.subprocess.run")
    def test_ocp_not_connected(self, mock_run, client):
        ocp_status_cache["timestamp"] = 0
        ocp_status_cache["data"] = None
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="error: You must be logged in"
        )
        resp = client.get("/api/ocp/connection-status")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_ocp_timeout(self, mock_run, client):
        import subprocess
        ocp_status_cache["timestamp"] = 0
        ocp_status_cache["data"] = None
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="oc", timeout=5)
        resp = client.get("/api/ocp/connection-status")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# get_agent_stats with events
# ---------------------------------------------------------------------------

class TestGetAgentStatsExtended:
    def test_with_events(self):
        jobs.clear()
        ai_agent_sessions.clear()
        job_id = "test-stats"
        jobs[job_id] = {
            "id": job_id,
            "status": "completed",
            "agent_events": [
                {
                    "type": "issue_detected",
                    "issue_type": "rosanetwork_stuck_deletion",
                    "resource_key": "my-net",
                    "diagnosis": "Stuck finalizer",
                    "fix_applied": "remove_finalizers",
                    "remediation_result": "Success",
                    "confidence": 0.95,
                    "timestamp": datetime.now().isoformat(),
                }
            ],
        }
        # Create mock session
        mock_monitor = MagicMock()
        mock_monitor.patterns_detected = ["rosanetwork_stuck_deletion"]
        mock_monitor._tracked_issues = {}
        mock_remediation = MagicMock()
        mock_remediation.interventions = [
            {"type": "remove_finalizers", "details": {"message": "Success"}}
        ]
        mock_learning = MagicMock()
        mock_learning.end_of_run_summary.return_value = {"outcomes": 1}
        ai_agent_sessions[job_id] = {
            "monitor": mock_monitor,
            "diagnostic": MagicMock(),
            "remediation": mock_remediation,
            "learning": mock_learning,
        }
        stats = get_agent_stats(job_id)
        assert stats["enabled"] is True
        assert stats["issues_detected"] == 1
        assert len(stats["resource_details"]) == 1
        assert stats["resource_details"][0]["resource_key"] == "my-net"

    def test_learning_summary_error(self):
        jobs.clear()
        ai_agent_sessions.clear()
        job_id = "test-learn-err"
        jobs[job_id] = {"id": job_id, "status": "completed", "agent_events": []}
        mock_learning = MagicMock()
        mock_learning.end_of_run_summary.side_effect = RuntimeError("boom")
        ai_agent_sessions[job_id] = {
            "monitor": MagicMock(patterns_detected=[], _tracked_issues={}),
            "diagnostic": MagicMock(),
            "remediation": MagicMock(interventions=[]),
            "learning": mock_learning,
        }
        stats = get_agent_stats(job_id)
        assert stats["enabled"] is True
        assert stats["learning"] == {}


# ---------------------------------------------------------------------------
# Minikube list clusters extended
# ---------------------------------------------------------------------------

class TestMinikubeExtended:
    @patch("app.subprocess.run")
    def test_minikube_no_clusters(self, mock_run, client):
        minikube_clusters_cache["timestamp"] = 0
        minikube_clusters_cache["data"] = None
        mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
        resp = client.get("/api/minikube/list-clusters")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_minikube_command_failure(self, mock_run, client):
        minikube_clusters_cache["timestamp"] = 0
        minikube_clusters_cache["data"] = None
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="minikube not found")
        resp = client.get("/api/minikube/list-clusters")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Config status endpoint
# ---------------------------------------------------------------------------

class TestConfigStatusExtended:
    @patch("app.os.path.exists", return_value=False)
    def test_config_missing(self, mock_exists, client):
        resp = client.get("/api/config/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False or data.get("status") == "missing"

    @patch("builtins.open", create=True)
    @patch("app.os.path.exists", return_value=True)
    def test_config_empty(self, mock_exists, mock_open, client):
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        with patch("app.yaml.safe_load", return_value={}):
            resp = client.get("/api/config/status")
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Credentials endpoint
# ---------------------------------------------------------------------------

class TestCredentialsExtended:
    @patch("app.subprocess.run")
    def test_credentials_with_aws(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"Account":"123456789012"}',
            stderr="",
        )
        resp = client.get("/api/credentials")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Guided setup status
# ---------------------------------------------------------------------------

class TestGuidedSetupExtended:
    def test_guided_setup_returns_steps(self, client):
        resp = client.get("/api/guided-setup/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "steps" in data or "setup" in data or "configured" in data


# ---------------------------------------------------------------------------
# Build templates
# ---------------------------------------------------------------------------

class TestBuildTemplatesExtended:
    def test_build_templates_structure(self, client):
        resp = client.get("/api/build/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert "templates" in data or "builds" in data


# ---------------------------------------------------------------------------
# ROSA clusters with various outputs
# ---------------------------------------------------------------------------

class TestRosaClustersExtended:
    @patch("app.subprocess.run")
    def test_rosa_clusters_empty(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
        resp = client.get("/api/rosa/clusters")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_rosa_clusters_error(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="auth error")
        resp = client.get("/api/rosa/clusters")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_rosa_clusters_multiple(self, mock_run, client):
        clusters_json = json.dumps([
            {"id": "abc", "name": "cluster-1", "state": "ready", "region": "us-west-2"},
            {"id": "def", "name": "cluster-2", "state": "installing", "region": "us-east-1"},
        ])
        mock_run.return_value = MagicMock(returncode=0, stdout=clusters_json, stderr="")
        resp = client.get("/api/rosa/clusters")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# AWS usage endpoints extended
# ---------------------------------------------------------------------------

class TestAwsUsageExtended:
    @patch("app.subprocess.run")
    def test_aws_usage_success(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"Reservations":[]}',
            stderr="",
        )
        resp = client.get("/api/aws/usage")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_aws_usage_trend_success(self, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"ResultsByTime":[]}',
            stderr="",
        )
        resp = client.get("/api/aws/usage-trend")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Test suites extended
# ---------------------------------------------------------------------------

class TestTestSuitesExtended:
    def test_test_suites_list_structure(self, client):
        resp = client.get("/api/test-suites/list")
        assert resp.status_code == 200
        data = resp.json()
        assert "suites" in data or "test_suites" in data or isinstance(data, list)

    def test_test_suites_history_structure(self, client):
        resp = client.get("/api/test-suites/history")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Jenkins and GitHub extended
# ---------------------------------------------------------------------------

class TestJenkinsGithubExtended:
    def test_jenkins_trend_structure(self, client):
        resp = client.get("/api/jenkins/test-results-trend")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_github_activity_structure(self, client):
        resp = client.get("/api/github/repo-activity")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# Job lifecycle edge cases
# ---------------------------------------------------------------------------

class TestJobLifecycleEdgeCases:
    def test_cancel_pending_job(self, client):
        job_id = str(uuid.uuid4())
        jobs[job_id] = {"id": job_id, "status": "pending", "started_at": datetime.now()}
        resp = client.post(f"/api/jobs/{job_id}/cancel")
        # pending is not "running" so should return 400
        assert resp.status_code == 400

    def test_list_jobs_sorted(self, client):
        j1 = str(uuid.uuid4())
        j2 = str(uuid.uuid4())
        jobs[j1] = {
            "id": j1, "status": "completed",
            "created_at": (datetime.now() - timedelta(hours=1)).isoformat(),
            "started_at": datetime.now(),
        }
        jobs[j2] = {
            "id": j2, "status": "running",
            "created_at": datetime.now().isoformat(),
            "started_at": datetime.now(),
        }
        resp = client.get("/api/jobs")
        data = resp.json()
        assert data["count"] == 2
        # Newest first
        assert data["jobs"][0]["id"] == j2

    def test_get_job_logs_empty(self, client):
        job_id = str(uuid.uuid4())
        jobs[job_id] = {"id": job_id, "status": "running", "started_at": datetime.now()}
        resp = client.get(f"/api/jobs/{job_id}/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["logs"] == []


# ---------------------------------------------------------------------------
# Cluster edge cases
# ---------------------------------------------------------------------------

class TestClusterEdgeCases:
    def test_get_cluster_with_missing_job(self, client):
        cluster_id = str(uuid.uuid4())
        clusters[cluster_id] = {
            "id": cluster_id,
            "config": {"name": "orphan"},
            "job_id": "nonexistent-job",
            "created_at": datetime.now(),
            "status": "ready",
        }
        resp = client.get(f"/api/clusters/{cluster_id}")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Normalize timestamp edge cases
# ---------------------------------------------------------------------------

class TestNormalizeTimestampExtended:
    def test_large_unix_timestamp(self):
        # Year 2100
        result = normalize_timestamp(4102444800.0)
        assert isinstance(result, datetime)

    def test_negative_value(self):
        result = normalize_timestamp(-1)
        assert isinstance(result, datetime)

    def test_dict_value(self):
        assert normalize_timestamp({"ts": 123}) == datetime.min

    def test_bool_value(self):
        # bool is subclass of int in Python
        result = normalize_timestamp(True)
        assert isinstance(result, datetime)

    def test_iso_with_timezone(self):
        result = normalize_timestamp("2026-01-01T00:00:00+05:00")
        assert result.year == 2026


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
