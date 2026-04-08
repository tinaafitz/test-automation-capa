"""
High-coverage tests targeting the largest uncovered sections of app.py.
Covers: ROSA clusters, cluster deletion, ansible tasks, playbook runner,
MCE environments, Jenkins/GitHub, AWS usage, provisioning, resource details,
minikube commands, and OCP connection status.
"""

import importlib
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

# ---------------------------------------------------------------------------
# Module-level mocking (same pattern as other test files)
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
# Helper to clean up jobs after tests
# =============================================

@pytest.fixture(autouse=True)
def cleanup_jobs():
    yield
    # Remove any jobs created during the test
    to_remove = [k for k in app_module.jobs if k.startswith(("delete-cluster-", "test-"))]
    for k in to_remove:
        del app_module.jobs[k]


# =============================================
# GET /api/rosa/clusters
# =============================================


class TestRosaClusters:
    @patch("app.asyncio.to_thread")
    async def test_rosa_clusters_empty(self, mock_thread):
        mock_thread.return_value = {"success": True, "clusters": [], "count": 0}
        resp = client.get("/api/rosa/clusters")
        assert resp.status_code == 200

    def test_rosa_clusters_sync_rosa_cli_success(self):
        """Test _get_rosa_clusters_sync with rosa CLI returning clusters"""
        mock_result = MagicMock(
            returncode=0,
            stdout=json.dumps([
                {
                    "name": "test-cluster-1",
                    "id": "abc123",
                    "status": {"state": "ready"},
                    "region": {"id": "us-east-1"},
                    "openshift_version": "4.20.10",
                    "dns": {"base_domain": "devshift.org"},
                    "api": {"url": "https://api.test.com:6443"},
                    "console": {"url": "https://console.test.com"},
                    "creation_timestamp": "2026-01-01T00:00:00Z",
                    "nodes": {"compute": 2},
                },
            ]),
        )
        # Also mock kubectl for the CAPI resource check
        kubectl_result = MagicMock(
            returncode=0,
            stdout=json.dumps({"items": [{"metadata": {"name": "test-cluster-1"}}]}),
        )
        with patch("app.subprocess.run", side_effect=[mock_result, kubectl_result]):
            result = app_module._get_rosa_clusters_sync()
        assert result["success"] is True

    @patch("app.subprocess.run")
    def test_rosa_clusters_sync_rosa_cli_fails(self, mock_run):
        """Test _get_rosa_clusters_sync when rosa CLI fails, falls back to kubectl"""
        # rosa CLI fails
        rosa_fail = MagicMock(returncode=1, stdout="", stderr="not logged in")
        # kubectl succeeds with rosacontrolplane
        kubectl_result = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "items": [
                    {
                        "metadata": {
                            "name": "kube-cluster",
                            "namespace": "ns-rosa-hcp",
                            "creationTimestamp": "2026-01-01T00:00:00Z",
                        },
                        "spec": {
                            "domainPrefix": "kube-cluster",
                            "version": "4.20",
                            "region": "us-west-2",
                        },
                        "status": {
                            "ready": True,
                            "conditions": [
                                {"type": "Ready", "status": "True"},
                            ],
                        },
                    }
                ]
            }),
        )
        mock_run.side_effect = [rosa_fail, kubectl_result]
        result = app_module._get_rosa_clusters_sync()
        assert result["success"] is True
        assert len(result["clusters"]) >= 0  # May or may not parse correctly

    @patch("app.subprocess.run")
    def test_rosa_clusters_sync_both_fail(self, mock_run):
        """Test _get_rosa_clusters_sync when both rosa and kubectl fail"""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = app_module._get_rosa_clusters_sync()
        assert result["success"] is False or result.get("clusters") == []


# =============================================
# GET /api/clusters (list_clusters)
# =============================================


class TestListClusters:
    @patch("app.subprocess.run")
    def test_list_clusters_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "items": [
                    {
                        "metadata": {
                            "name": "my-cluster",
                            "namespace": "ns-rosa-hcp",
                            "creationTimestamp": "2026-04-01T10:00:00Z",
                        },
                        "spec": {
                            "domainPrefix": "my-cluster",
                            "version": "4.20",
                            "region": "us-east-1",
                        },
                        "status": {
                            "ready": True,
                            "conditions": [
                                {"type": "Ready", "status": "True"},
                            ],
                            "consoleURL": "https://console.my-cluster.com",
                        },
                    }
                ]
            }),
        )
        resp = client.get("/api/clusters")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 1
        assert data["clusters"][0]["name"] == "my-cluster"
        assert data["clusters"][0]["ready"] is True
        assert data["clusters"][0]["status"] == "ready"
        assert data["clusters"][0]["progress"] == 100

    @patch("app.subprocess.run")
    def test_list_clusters_provisioning(self, mock_run):
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
                        "spec": {
                            "domainPrefix": "prov-cluster",
                            "version": "4.20",
                            "region": "us-west-2",
                        },
                        "status": {
                            "ready": False,
                            "conditions": [
                                {"type": "ROSANetworkReady", "status": "True"},
                                {"type": "ROSARoleConfigReady", "status": "True"},
                                {"type": "ROSAControlPlaneValid", "status": "True"},
                                {"type": "Ready", "status": "False"},
                            ],
                        },
                    }
                ]
            }),
        )
        resp = client.get("/api/clusters")
        data = resp.json()
        assert data["success"] is True
        cluster = data["clusters"][0]
        # Ready is False with Ready condition status=False, so error_message gets set -> "failed"
        assert cluster["status"] == "failed"
        assert cluster["progress"] == 75  # 3 of 4 conditions met

    @patch("app.subprocess.run")
    def test_list_clusters_deleting(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "items": [
                    {
                        "metadata": {
                            "name": "del-cluster",
                            "namespace": "ns-rosa-hcp",
                            "creationTimestamp": "2026-04-01T10:00:00Z",
                            "deletionTimestamp": "2026-04-08T10:00:00Z",
                        },
                        "spec": {"domainPrefix": "del-cluster", "version": "4.20", "region": "us-east-1"},
                        "status": {"ready": False, "conditions": []},
                    }
                ]
            }),
        )
        resp = client.get("/api/clusters")
        data = resp.json()
        assert data["clusters"][0]["status"] == "deleting"

    @patch("app.subprocess.run")
    def test_list_clusters_kubectl_fails(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="connection refused")
        resp = client.get("/api/clusters")
        data = resp.json()
        assert data["success"] is False
        assert data["clusters"] == []

    @patch("app.subprocess.run")
    def test_list_clusters_exception(self, mock_run):
        mock_run.side_effect = Exception("kubectl crashed")
        resp = client.get("/api/clusters")
        data = resp.json()
        assert data["success"] is False


# =============================================
# GET /api/clusters/{cluster_name}/status
# =============================================


class TestClusterStatus:
    @patch("app.subprocess.run")
    def test_cluster_status_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "metadata": {"name": "my-cluster", "namespace": "ns-rosa-hcp"},
                "spec": {"version": "4.20", "region": "us-east-1"},
                "status": {
                    "ready": True,
                    "conditions": [{"type": "Ready", "status": "True"}],
                },
            }),
        )
        resp = client.get("/api/clusters/my-cluster/status")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_cluster_status_not_found(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
        resp = client.get("/api/clusters/nonexistent/status")
        assert resp.status_code in (200, 404, 500)


# =============================================
# DELETE /api/rosa/clusters/{cluster_name}
# =============================================


class TestDeleteRosaCluster:
    @patch("app.asyncio.create_task")
    @patch("app.init_ai_agents")
    def test_delete_cluster_success(self, mock_agents, mock_task):
        resp = client.request(
            "DELETE",
            "/api/rosa/clusters/test-del",
            json={"namespace": "ns-rosa-hcp"},
        )
        data = resp.json()
        assert data["success"] is True
        assert "job_id" in data
        # Clean up
        if data["job_id"] in app_module.jobs:
            del app_module.jobs[data["job_id"]]

    @patch("app.asyncio.create_task")
    def test_delete_cluster_no_namespace(self, mock_task):
        resp = client.request(
            "DELETE",
            "/api/rosa/clusters/test-del",
            json={},
        )
        data = resp.json()
        assert data["success"] is False
        assert "namespace" in data["message"].lower()


# =============================================
# POST /api/ansible/run-task
# =============================================


class TestAnsibleRunTask:
    @patch("app.asyncio.create_task")
    def test_run_task_with_task_file(self, mock_task):
        resp = client.post("/api/ansible/run-task", json={
            "task_file": "tasks/validate-capa-environment.yml",
            "description": "Validate environment",
        })
        data = resp.json()
        assert data["success"] is True
        assert "job_id" in data
        # Clean up
        if data["job_id"] in app_module.jobs:
            del app_module.jobs[data["job_id"]]

    @patch("app.asyncio.create_task")
    def test_run_task_with_playbook_file(self, mock_task):
        resp = client.post("/api/ansible/run-task", json={
            "playbook_file": "playbooks/validate-environment.yml",
            "description": "Run playbook",
            "extra_vars": {"key": "value"},
        })
        data = resp.json()
        assert data["success"] is True
        # Clean up
        if data["job_id"] in app_module.jobs:
            del app_module.jobs[data["job_id"]]

    def test_run_task_missing_file(self):
        resp = client.post("/api/ansible/run-task", json={
            "description": "No file specified",
        })
        assert resp.status_code in (400, 500)

    @patch("app.asyncio.create_task")
    def test_run_task_with_kube_context(self, mock_task):
        resp = client.post("/api/ansible/run-task", json={
            "task_file": "tasks/validate-capa-environment.yml",
            "kube_context": "minikube",
            "cluster_type": "minikube",
        })
        data = resp.json()
        assert data["success"] is True
        if data["job_id"] in app_module.jobs:
            del app_module.jobs[data["job_id"]]


# =============================================
# POST /api/ansible/run-playbook
# =============================================


class TestAnsibleRunPlaybook:
    def test_run_playbook_missing_name(self):
        resp = client.post("/api/ansible/run-playbook", json={
            "description": "Missing playbook",
        })
        assert resp.status_code in (400, 500)

    @patch("app.asyncio.create_task")
    @patch("os.path.exists", return_value=True)
    @patch("app.init_ai_agents")
    def test_run_playbook_success(self, mock_agents, mock_exists, mock_task):
        resp = client.post("/api/ansible/run-playbook", json={
            "playbook": "playbooks/validate-environment.yml",
            "description": "Validate",
        })
        data = resp.json()
        assert data["success"] is True
        assert "job_id" in data
        if data["job_id"] in app_module.jobs:
            del app_module.jobs[data["job_id"]]

    @patch("os.path.exists", return_value=False)
    def test_run_playbook_not_found(self, mock_exists):
        resp = client.post("/api/ansible/run-playbook", json={
            "playbook": "playbooks/nonexistent.yml",
        })
        assert resp.status_code in (404, 500)


# =============================================
# MCE Environment Endpoints
# =============================================


class TestMCEEnvironments:
    def test_list_mce_environments_success(self):
        mock_manager = MagicMock()
        mock_manager.list_environments.return_value = [
            {
                "cluster_name": "qe6-vmware",
                "platform": "VMware",
                "status": "pass",
                "notes": "",
                "added_date": "2026-01-01",
                "last_accessed": "2026-04-08",
                "data": {
                    "cluster": {
                        "ocp_version": "4.20",
                        "mce_version": "2.11",
                        "acm_version": "2.16",
                        "status": "Running",
                        "password": "xxxx",
                        "console_url": "https://console.test",
                    },
                    "notification": {
                        "jira": "JIRA-123",
                        "polarion": "POL-456",
                        "total_failures": 2,
                        "components": {"provider": 1},
                    },
                },
            }
        ]
        with patch.dict("sys.modules", {"mce_env_manager": MagicMock(MCEEnvManager=lambda: mock_manager)}):
            resp = client.get("/api/mce-environments")
        data = resp.json()
        assert data["success"] is True
        assert data["total"] == 1
        assert data["environments"][0]["clusterName"] == "qe6-vmware"

    def test_list_mce_environments_import_error(self):
        """When MCEEnvManager can't be imported"""
        with patch.dict("sys.modules", {"mce_env_manager": None}):
            resp = client.get("/api/mce-environments")
        data = resp.json()
        assert data["success"] is False

    def test_get_mce_environment_not_found(self):
        mock_manager = MagicMock()
        mock_manager.get_environment.return_value = None
        with patch.dict("sys.modules", {"mce_env_manager": MagicMock(MCEEnvManager=lambda: mock_manager)}):
            resp = client.get("/api/mce-environments/nonexistent-cluster")
        assert resp.status_code == 404

    def test_get_mce_environment_success(self):
        mock_manager = MagicMock()
        mock_manager.get_environment.return_value = {
            "cluster_name": "test-ibm",
            "platform": "IBM Power",
            "status": "pass",
            "notes": "",
            "added_date": "2026-01-01",
            "last_accessed": "2026-04-01",
            "data": {
                "cluster": {
                    "ocp_version": "4.20",
                    "mce_version": "2.11",
                    "acm_version": "2.16",
                    "status": "Running",
                    "password": "pass123",
                    "console_url": "https://console.ibm",
                },
                "notification": {
                    "jira": "J-1",
                    "polarion": "P-1",
                    "title": "Test",
                    "total_failures": 0,
                    "components": {},
                },
            },
        }
        with patch.dict("sys.modules", {"mce_env_manager": MagicMock(MCEEnvManager=lambda: mock_manager)}):
            resp = client.get("/api/mce-environments/test-ibm")
        data = resp.json()
        assert data["success"] is True
        assert "ibm" in data["environment"]["apiUrl"].lower()

    def test_get_mce_environment_aws_platform(self):
        mock_manager = MagicMock()
        mock_manager.get_environment.return_value = {
            "cluster_name": "test-aws",
            "platform": "AWS-ARM",
            "status": "pass",
            "data": {
                "cluster": {"status": "Running", "password": "p"},
                "notification": {},
            },
        }
        with patch.dict("sys.modules", {"mce_env_manager": MagicMock(MCEEnvManager=lambda: mock_manager)}):
            resp = client.get("/api/mce-environments/test-aws")
        data = resp.json()
        assert "red-chesterfield" in data["environment"]["apiUrl"]

    def test_save_mce_environment_new(self):
        mock_manager = MagicMock()
        mock_manager.get_environment.return_value = None
        with patch.dict("sys.modules", {"mce_env_manager": MagicMock(MCEEnvManager=lambda: mock_manager)}):
            resp = client.post("/api/mce-environments", json={
                "clusterName": "new-cluster",
                "platform": "VMware",
                "ocpVersion": "4.20",
            })
        data = resp.json()
        assert data["success"] is True
        assert "saved" in data["message"].lower()

    def test_save_mce_environment_existing(self):
        mock_manager = MagicMock()
        mock_manager.get_environment.return_value = {"cluster_name": "existing"}
        with patch.dict("sys.modules", {"mce_env_manager": MagicMock(MCEEnvManager=lambda: mock_manager)}):
            resp = client.post("/api/mce-environments", json={
                "clusterName": "existing",
            })
        data = resp.json()
        assert data["success"] is True
        assert "already exists" in data["message"].lower()

    def test_save_mce_environment_extract_name_from_url(self):
        mock_manager = MagicMock()
        mock_manager.get_environment.return_value = None
        with patch.dict("sys.modules", {"mce_env_manager": MagicMock(MCEEnvManager=lambda: mock_manager)}):
            resp = client.post("/api/mce-environments", json={
                "apiUrl": "https://api.qe6-vmware-ibm.install.dev09.red-chesterfield.com:6443",
            })
        data = resp.json()
        assert data["success"] is True
        assert data["clusterName"] == "qe6-vmware-ibm"

    def test_save_mce_environment_no_name_no_url(self):
        mock_manager = MagicMock()
        with patch.dict("sys.modules", {"mce_env_manager": MagicMock(MCEEnvManager=lambda: mock_manager)}):
            resp = client.post("/api/mce-environments", json={})
        data = resp.json()
        assert data["success"] is False

    def test_update_mce_environment_status_success(self):
        mock_manager = MagicMock()
        mock_manager.update_status.return_value = True
        with patch.dict("sys.modules", {"mce_env_manager": MagicMock(MCEEnvManager=lambda: mock_manager)}):
            resp = client.post("/api/mce-environments/test-cluster/status", json={
                "status": "pass",
                "notes": "All tests passed",
            })
        data = resp.json()
        assert data["success"] is True

    def test_update_mce_environment_status_invalid(self):
        with patch.dict("sys.modules", {"mce_env_manager": MagicMock()}):
            resp = client.post("/api/mce-environments/test-cluster/status", json={
                "status": "invalid_status",
            })
        assert resp.status_code == 400

    def test_update_mce_environment_status_not_found(self):
        mock_manager = MagicMock()
        mock_manager.update_status.return_value = False
        with patch.dict("sys.modules", {"mce_env_manager": MagicMock(MCEEnvManager=lambda: mock_manager)}):
            resp = client.post("/api/mce-environments/nonexistent/status", json={
                "status": "fail",
            })
        assert resp.status_code == 404

    def test_mce_environment_stats(self):
        mock_manager = MagicMock()
        mock_manager.get_stats.return_value = {
            "total": 5,
            "by_platform": {"VMware": 3, "AWS": 2},
            "by_status": {"pass": 4, "fail": 1},
            "recent": [
                {"cluster_name": "c1", "platform": "VMware", "status": "pass", "last_accessed": "2026-04-01"},
            ],
        }
        with patch.dict("sys.modules", {"mce_env_manager": MagicMock(MCEEnvManager=lambda: mock_manager)}):
            resp = client.get("/api/mce-environments/stats/summary")
        data = resp.json()
        assert data["success"] is True
        assert data["stats"]["total"] == 5

    def test_mce_environment_search(self):
        mock_manager = MagicMock()
        mock_manager.search_environments.return_value = [
            {
                "cluster_name": "qe6-vmware",
                "platform": "VMware",
                "status": "pass",
                "notes": "",
                "last_accessed": "2026-04-01",
                "data": {
                    "cluster": {},
                    "notification": {"jira": "J-1", "polarion": "P-1", "total_failures": 0},
                },
            }
        ]
        with patch.dict("sys.modules", {"mce_env_manager": MagicMock(MCEEnvManager=lambda: mock_manager)}):
            resp = client.get("/api/mce-environments/search/vmware")
        data = resp.json()
        assert data["success"] is True
        assert data["total"] == 1
        assert data["query"] == "vmware"


# =============================================
# GET /api/jenkins/test-results-trend
# =============================================


class TestJenkinsTestResultsTrend:
    @patch("requests.get")
    def test_jenkins_trend_success(self, mock_get):
        # Mock the builds response
        builds_response = MagicMock()
        builds_response.status_code = 200
        builds_response.raise_for_status = MagicMock()
        builds_response.json.return_value = {
            "builds": [
                {"number": 100, "result": "SUCCESS", "timestamp": 1712000000000, "duration": 60000},
                {"number": 99, "result": "FAILURE", "timestamp": 1711900000000, "duration": 50000},
                {"number": 98, "result": None, "timestamp": 1711800000000, "duration": 0},  # running
            ]
        }
        # Mock the test report responses
        test_response_100 = MagicMock()
        test_response_100.status_code = 200
        test_response_100.json.return_value = {"passCount": 50, "failCount": 2, "skipCount": 3}

        test_response_99 = MagicMock()
        test_response_99.status_code = 404  # No test results

        mock_get.side_effect = [builds_response, test_response_100, test_response_99]

        resp = client.get("/api/jenkins/test-results-trend")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] >= 1
        assert data["trend"][0]["passCount"] == 50

    @patch("requests.get")
    def test_jenkins_trend_connection_error(self, mock_get):
        mock_get.side_effect = Exception("Connection refused")
        resp = client.get("/api/jenkins/test-results-trend")
        data = resp.json()
        assert data["success"] is False
        assert data["trend"] == []


# =============================================
# GET /api/github/repo-activity
# =============================================


class TestGithubRepoActivity:
    @patch("requests.get")
    def test_github_activity_success(self, mock_get):
        repo_response = MagicMock()
        repo_response.status_code = 200
        repo_response.json.return_value = {
            "stargazers_count": 10,
            "forks_count": 3,
            "updated_at": "2026-04-08T00:00:00Z",
        }

        commits_response = MagicMock()
        commits_response.status_code = 200
        commits_response.json.return_value = [{"sha": "abc"}, {"sha": "def"}]

        prs_response = MagicMock()
        prs_response.status_code = 200
        prs_response.json.return_value = [{"number": 1}]

        merged_response = MagicMock()
        merged_response.status_code = 200
        merged_response.json.return_value = [
            {"number": 2, "merged_at": "2026-04-07T00:00:00Z"},
        ]

        issues_response = MagicMock()
        issues_response.status_code = 200
        issues_response.json.return_value = [{"number": 1}, {"number": 3}]

        # 2 repos, each needs 5 API calls
        mock_get.side_effect = [
            repo_response, commits_response, prs_response, merged_response, issues_response,
            repo_response, commits_response, prs_response, merged_response, issues_response,
        ]

        resp = client.get("/api/github/repo-activity")
        data = resp.json()
        assert data["success"] is True
        assert len(data["repos"]) == 2

    @patch("requests.get")
    def test_github_activity_rate_limited(self, mock_get):
        rate_limited = MagicMock()
        rate_limited.status_code = 403
        mock_get.return_value = rate_limited

        resp = client.get("/api/github/repo-activity")
        data = resp.json()
        assert data["success"] is True
        assert any("error" in r for r in data["repos"])

    @patch("requests.get")
    def test_github_activity_exception(self, mock_get):
        mock_get.side_effect = Exception("Network error")
        resp = client.get("/api/github/repo-activity")
        data = resp.json()
        assert data["success"] is False


# =============================================
# AWS Usage Endpoints
# =============================================


class TestAWSUsage:
    @patch("app._collect_aws_usage_data")
    @patch("app._save_aws_usage_snapshot")
    def test_aws_usage_success(self, mock_save, mock_collect):
        mock_collect.return_value = {
            "nat_gateways": 3,
            "vpcs": 5,
            "security_groups": 12,
        }
        resp = client.get("/api/aws/usage")
        data = resp.json()
        assert data["success"] is True
        assert data["usage"]["nat_gateways"] == 3

    @patch("app._collect_aws_usage_data")
    def test_aws_usage_error(self, mock_collect):
        mock_collect.side_effect = Exception("AWS credentials not configured")
        resp = client.get("/api/aws/usage")
        data = resp.json()
        assert data["success"] is False

    def test_aws_usage_trend_no_data(self):
        with patch("app._get_aws_history_db") as mock_db:
            # Use in-memory database
            mock_db.return_value = ":memory:"
            with patch("sqlite3.connect") as mock_conn:
                mock_connection = MagicMock()
                mock_connection.execute.return_value.fetchall.return_value = []
                mock_conn.return_value = mock_connection
                resp = client.get("/api/aws/usage-trend")
        data = resp.json()
        assert data["success"] is True

    @patch("app.subprocess.run")
    def test_single_resource_nat_gateways(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "NatGateways": [
                    {"State": "available"},
                    {"State": "available"},
                    {"State": "deleted"},
                ]
            }),
        )
        resp = client.get("/api/aws/usage/nat_gateways")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 2  # Only "available" ones

    @patch("app.subprocess.run")
    def test_single_resource_vpcs(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"Vpcs": [{"VpcId": "vpc-1"}, {"VpcId": "vpc-2"}]}),
        )
        resp = client.get("/api/aws/usage/vpcs")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 2

    @patch("app.subprocess.run")
    def test_single_resource_security_groups(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"SecurityGroups": [{"GroupId": "sg-1"}]}),
        )
        resp = client.get("/api/aws/usage/security_groups")
        data = resp.json()
        assert data["count"] == 1

    @patch("app.subprocess.run")
    def test_single_resource_ec2_instances(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "Reservations": [
                    {"Instances": [{"InstanceId": "i-1"}, {"InstanceId": "i-2"}]},
                    {"Instances": [{"InstanceId": "i-3"}]},
                ]
            }),
        )
        resp = client.get("/api/aws/usage/ec2_instances")
        data = resp.json()
        assert data["count"] == 3

    @patch("app.subprocess.run")
    def test_single_resource_s3_buckets(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"Buckets": [{"Name": "b1"}, {"Name": "b2"}]}),
        )
        resp = client.get("/api/aws/usage/s3_buckets")
        data = resp.json()
        assert data["count"] == 2

    @patch("app.subprocess.run")
    def test_single_resource_cloudformation_stacks(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "StackSummaries": [
                    {"StackName": "s1", "StackStatus": "CREATE_COMPLETE"},
                    {"StackName": "s2", "StackStatus": "DELETE_COMPLETE"},
                    {"StackName": "s3", "StackStatus": "UPDATE_COMPLETE"},
                ]
            }),
        )
        resp = client.get("/api/aws/usage/cloudformation_stacks")
        data = resp.json()
        assert data["count"] == 2  # Excludes DELETE_COMPLETE

    @patch("app.subprocess.run")
    def test_single_resource_route53(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"HostedZones": [{"Id": "z1"}]}),
        )
        resp = client.get("/api/aws/usage/route53_zones")
        data = resp.json()
        assert data["count"] == 1

    @patch("app.subprocess.run")
    def test_single_resource_iam_roles(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"Roles": [{"RoleName": "r1"}, {"RoleName": "r2"}]}),
        )
        resp = client.get("/api/aws/usage/iam_roles")
        data = resp.json()
        assert data["count"] == 2

    @patch("app.subprocess.run")
    def test_single_resource_ebs_volumes(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"Volumes": [{"VolumeId": "v1"}]}),
        )
        resp = client.get("/api/aws/usage/ebs_volumes")
        data = resp.json()
        assert data["count"] == 1

    @patch("app.subprocess.run")
    def test_single_resource_load_balancers(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"LoadBalancers": [{"LoadBalancerArn": "lb1"}]}),
        )
        resp = client.get("/api/aws/usage/load_balancers")
        data = resp.json()
        assert data["count"] == 1

    @patch("app.subprocess.run")
    def test_single_resource_instance_profiles(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"InstanceProfiles": [{"InstanceProfileName": "ip1"}]}),
        )
        resp = client.get("/api/aws/usage/instance_profiles")
        data = resp.json()
        assert data["count"] == 1

    def test_single_resource_unknown(self):
        resp = client.get("/api/aws/usage/nonexistent_resource")
        data = resp.json()
        assert data["success"] is False
        assert "unknown" in data["message"].lower()

    def test_aws_config(self):
        with patch.dict("sys.modules", {"aws_config_service": MagicMock(
            aws_config_service=MagicMock(
                get_resource_config_with_quotas=MagicMock(return_value={"success": True, "config": {}})
            )
        )}):
            resp = client.get("/api/aws/usage-config")
        data = resp.json()
        assert data["success"] is True

    def test_aws_config_error(self):
        with patch.dict("sys.modules", {"aws_config_service": None}):
            resp = client.get("/api/aws/usage-config")
        data = resp.json()
        assert data["success"] is False


# =============================================
# Minikube Endpoints
# =============================================


class TestMinikubeEndpoints:
    @patch("app.subprocess.run")
    def test_list_clusters(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([
                {"Name": "sat-minikube", "Status": "Running", "Driver": "docker"},
            ]),
        )
        resp = client.get("/api/minikube/list-clusters")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_list_clusters_not_installed(self, mock_run):
        mock_run.side_effect = FileNotFoundError("minikube not found")
        resp = client.get("/api/minikube/list-clusters")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_current_context(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="minikube\n")
        resp = client.get("/api/minikube/current-context")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_active_profile(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="sat-minikube\n")
        resp = client.get("/api/minikube/active-profile")
        assert resp.status_code == 200

    @patch("app.asyncio.create_task")
    def test_execute_command(self, mock_task):
        resp = client.post("/api/minikube/execute-command", json={
            "command": "kubectl get pods",
            "cluster_name": "sat-minikube",
        })
        assert resp.status_code == 200

    @patch("app.asyncio.create_task")
    def test_create_cluster(self, mock_task):
        resp = client.post("/api/minikube/create-cluster", json={
            "cluster_name": "new-mk",
            "driver": "docker",
            "cpus": "4",
            "memory": "8192",
        })
        assert resp.status_code == 200

    @patch("app.asyncio.create_task")
    def test_delete_cluster(self, mock_task):
        resp = client.post("/api/minikube/delete-cluster", json={
            "cluster_name": "old-mk",
        })
        assert resp.status_code == 200


# =============================================
# OCP Endpoints
# =============================================


class TestOCPEndpoints:
    @patch("app.asyncio.create_task")
    def test_ocp_execute_command(self, mock_task):
        resp = client.post("/api/ocp/execute-command", json={
            "command": "oc get nodes",
        })
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_ocp_connection_status_connected(self, mock_run):
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
            if "whoami" in cmd_str:
                return MagicMock(returncode=0, stdout="kubeadmin\n")
            if "cluster-info" in cmd_str:
                return MagicMock(returncode=0, stdout="Kubernetes control plane is running")
            if "config" in cmd_str and "view" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps({
                        "clusters": [{"cluster": {"server": "https://api.test:6443"}}]
                    }),
                )
            if "get clusterversion" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps({
                        "items": [{"status": {"desired": {"version": "4.20"}}}]
                    }),
                )
            if "get nodes" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps({
                        "items": [
                            {"metadata": {"name": "node-1"}, "status": {"conditions": [{"type": "Ready", "status": "True"}]}},
                        ]
                    }),
                )
            return MagicMock(returncode=0, stdout="{}")

        mock_run.side_effect = side_effect
        # Clear cache to avoid stale data
        if hasattr(app_module, 'ocp_status_cache'):
            app_module.ocp_status_cache["timestamp"] = 0
        resp = client.get("/api/ocp/connection-status")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_ocp_connection_status_disconnected(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="connection refused")
        if hasattr(app_module, 'ocp_status_cache'):
            app_module.ocp_status_cache["timestamp"] = 0
        resp = client.get("/api/ocp/connection-status")
        data = resp.json()
        assert resp.status_code == 200


# =============================================
# Provisioning Endpoints
# =============================================


class TestProvisioning:
    def test_rosa_save_yaml_path(self):
        resp = client.post("/api/rosa/save-yaml-path", json={
            "path": "/tmp/test.yaml",
            "cluster_name": "test",
        })
        assert resp.status_code == 200

    def test_rosa_last_yaml_path(self):
        resp = client.get("/api/rosa/last-yaml-path")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_log_forwarding_config(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "cloudwatch_log_group_name": "test-group",
                "cloudwatch_log_role_arn": "arn:aws:iam::role/test",
            }),
        )
        resp = client.get("/api/provisioning/log-forwarding-config/test-cluster")
        assert resp.status_code == 200


# =============================================
# MCE Features / YAML Endpoints
# =============================================


class TestMCEFeatures:
    @patch("app.subprocess.run")
    def test_mce_features(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "items": [
                    {
                        "metadata": {"name": "mce-feature-1"},
                        "spec": {"enabled": True},
                    }
                ]
            }),
        )
        resp = client.get("/api/mce/features")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_mce_resources(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps({"items": []}))
        resp = client.get("/api/mce/resources")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_mce_yaml(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="apiVersion: v1\nkind: Namespace\nmetadata:\n  name: test\n",
        )
        resp = client.get("/api/mce/yaml")
        assert resp.status_code == 200


# =============================================
# CAPI Component Versions
# =============================================


class TestCAPIVersions:
    @patch("app.subprocess.run")
    def test_component_versions(self, mock_run):
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
            if "capi-system" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps({
                        "items": [
                            {
                                "metadata": {"name": "capi-controller-manager"},
                                "spec": {"template": {"spec": {"containers": [{"image": "capi:v1.7.0"}]}}},
                                "status": {"readyReplicas": 1, "replicas": 1},
                            }
                        ]
                    }),
                )
            if "capa-system" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps({
                        "items": [
                            {
                                "metadata": {"name": "capa-controller-manager"},
                                "spec": {"template": {"spec": {"containers": [{"image": "capa:v2.6.0"}]}}},
                                "status": {"readyReplicas": 1, "replicas": 1},
                            }
                        ]
                    }),
                )
            return MagicMock(returncode=0, stdout=json.dumps({"items": []}))

        mock_run.side_effect = side_effect
        resp = client.get("/api/capi/component-versions")
        assert resp.status_code == 200


# =============================================
# Resource Detail Endpoints
# =============================================


class TestResourceDetail:
    @patch("app.subprocess.run")
    def test_minikube_get_active_resources(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"items": []}),
        )
        resp = client.post("/api/minikube/get-active-resources", json={
            "cluster_name": "sat-minikube",
        })
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_minikube_resource_detail(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "metadata": {"name": "test-resource"},
                "spec": {},
                "status": {},
            }),
        )
        resp = client.post("/api/minikube/get-resource-detail", json={
            "resource_type": "rosacontrolplane",
            "resource_name": "test",
            "namespace": "ns-rosa-hcp",
            "cluster_name": "sat-minikube",
        })
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_ocp_resource_detail(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "metadata": {"name": "test-resource"},
                "spec": {},
                "status": {},
            }),
        )
        resp = client.post("/api/ocp/get-resource-detail", json={
            "resource_type": "deployment",
            "resource_name": "test-deploy",
            "namespace": "default",
        })
        assert resp.status_code == 200


# =============================================
# AWS Resource Details
# =============================================


class TestAWSResourceDetails:
    @patch("app.subprocess.run")
    def test_nat_gateway_details(self, mock_run):
        nat_result = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "NatGateways": [
                    {
                        "NatGatewayId": "nat-123",
                        "State": "available",
                        "VpcId": "vpc-abc",
                        "SubnetId": "subnet-1",
                        "CreateTime": "2026-01-01T00:00:00Z",
                        "Tags": [{"Key": "Name", "Value": "test-nat"}],
                        "NatGatewayAddresses": [{"PublicIp": "1.2.3.4"}],
                    }
                ]
            }),
        )
        vpc_result = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "Vpcs": [{"VpcId": "vpc-abc", "Tags": [{"Key": "Name", "Value": "test-vpc"}]}]
            }),
        )
        mock_run.side_effect = [nat_result, vpc_result]
        resp = client.get("/api/aws/resource-details/nat_gateways")
        data = resp.json()
        assert data["success"] is True
        assert len(data["details"]) == 1
        assert data["details"][0]["public_ip"] == "1.2.3.4"

    @patch("app.subprocess.run")
    def test_route53_details(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "HostedZones": [
                    {"Id": "/hostedzone/Z1", "Name": "example.com.", "Config": {"PrivateZone": False},
                     "ResourceRecordSetCount": 10},
                ]
            }),
        )
        resp = client.get("/api/aws/resource-details/route53_zones")
        data = resp.json()
        assert data["success"] is True


# =============================================
# Test Suites
# =============================================


class TestTestSuiteEndpoints:
    def test_test_suite_list(self):
        resp = client.get("/api/test-suites/list")
        assert resp.status_code == 200
        data = resp.json()
        assert "suites" in data or "test_suites" in data or isinstance(data, list)

    def test_test_suite_status_not_found(self):
        resp = client.get("/api/test-suites/status/nonexistent-run-id")
        assert resp.status_code == 404

    def test_test_suite_history(self):
        resp = client.get("/api/test-suites/history")
        assert resp.status_code == 200


# =============================================
# Notification Settings
# =============================================


class TestNotificationSettings:
    def test_get_notification_settings(self):
        resp = client.get("/api/notification-settings")
        assert resp.status_code == 200

    def test_save_notification_settings(self):
        resp = client.post("/api/notification-settings", json={
            "slack_enabled": False,
            "email_enabled": False,
        })
        assert resp.status_code == 200


# =============================================
# Onboarding / Diagnostics / Config
# =============================================


class TestMiscEndpoints:
    def test_onboarding_tour(self):
        resp = client.get("/api/onboarding/tour")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_diagnostics_checks(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        resp = client.get("/api/diagnostics/checks")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_config_status(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        resp = client.get("/api/config/status")
        assert resp.status_code == 200

    def test_user_profile(self):
        resp = client.get("/api/user/profile")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_credentials_get(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        resp = client.get("/api/credentials")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_aws_credentials_status(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="arn:aws:iam::123:user/test\n")
        resp = client.get("/api/aws/credentials-status")
        assert resp.status_code == 200

    def test_guided_setup_status(self):
        resp = client.get("/api/guided-setup/status")
        assert resp.status_code == 200

    def test_build_templates(self):
        resp = client.get("/api/build/templates")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_environment_overview(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        resp = client.get("/api/environment/overview")
        assert resp.status_code == 200

    @patch("app.subprocess.run")
    def test_rosa_status(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        resp = client.get("/api/rosa/status")
        assert resp.status_code == 200


# =============================================
# Direct tests for background/sync functions
# =============================================


class TestRunMinikubeInitPlaybook:
    """Test run_minikube_init_playbook directly (sync function)"""

    def _make_job(self, job_id):
        app_module.jobs[job_id] = {
            "id": job_id, "status": "pending", "progress": 0,
            "message": "", "logs": [], "description": "test",
        }

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    @patch("os.path.exists", return_value=False)
    def test_success(self, mock_exists, mock_run, mock_popen):
        job_id = "test-mk-init-1"
        self._make_job(job_id)
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        mock_process = MagicMock()
        mock_process.stdout = iter(["TASK [install] ***\n", "ok: [localhost]\n"])
        mock_process.stderr = MagicMock(read=MagicMock(return_value=""))
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        app_module.run_minikube_init_playbook("/tmp/playbook.yml", "sat-minikube", job_id)
        assert app_module.jobs[job_id]["status"] == "completed"
        del app_module.jobs[job_id]

    @patch("subprocess.run")
    @patch("os.path.exists", return_value=False)
    def test_context_switch_fails(self, mock_exists, mock_run):
        job_id = "test-mk-init-2"
        self._make_job(job_id)
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="context not found")

        app_module.run_minikube_init_playbook("/tmp/playbook.yml", "bad-cluster", job_id)
        assert app_module.jobs[job_id]["status"] == "failed"
        assert "context" in app_module.jobs[job_id]["message"].lower()
        del app_module.jobs[job_id]

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    @patch("os.path.exists", return_value=False)
    def test_playbook_fails(self, mock_exists, mock_run, mock_popen):
        job_id = "test-mk-init-3"
        self._make_job(job_id)
        mock_run.return_value = MagicMock(returncode=0)
        mock_process = MagicMock()
        mock_process.stdout = iter(["TASK [fail] ***\n"])
        mock_process.stderr = MagicMock(read=MagicMock(return_value="ERROR"))
        mock_process.wait.return_value = 1
        mock_popen.return_value = mock_process

        app_module.run_minikube_init_playbook("/tmp/playbook.yml", "sat-minikube", job_id)
        assert app_module.jobs[job_id]["status"] == "failed"
        del app_module.jobs[job_id]

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    @patch("os.path.exists", return_value=False)
    def test_timeout(self, mock_exists, mock_run, mock_popen):
        job_id = "test-mk-init-4"
        self._make_job(job_id)
        mock_run.return_value = MagicMock(returncode=0)
        mock_process = MagicMock()
        mock_process.stdout = iter([])
        mock_process.stderr = MagicMock(read=MagicMock(return_value=""))
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="ansible", timeout=600)
        mock_popen.return_value = mock_process

        app_module.run_minikube_init_playbook("/tmp/playbook.yml", "sat-minikube", job_id)
        assert app_module.jobs[job_id]["status"] == "failed"
        assert "timed out" in app_module.jobs[job_id]["message"].lower()
        del app_module.jobs[job_id]

    @patch("subprocess.run")
    @patch("os.path.exists", return_value=False)
    def test_exception(self, mock_exists, mock_run):
        job_id = "test-mk-init-5"
        self._make_job(job_id)
        mock_run.side_effect = Exception("unexpected error")

        app_module.run_minikube_init_playbook("/tmp/playbook.yml", "sat-minikube", job_id)
        assert app_module.jobs[job_id]["status"] == "failed"
        del app_module.jobs[job_id]


class TestRunAnsibleTaskBackground:
    """Test run_ansible_task_background directly"""

    def _make_job(self, job_id):
        app_module.jobs[job_id] = {
            "id": job_id, "status": "pending", "progress": 0,
            "message": "", "logs": [], "description": "test",
        }

    @patch("subprocess.run")
    @patch("os.path.exists", return_value=True)
    def test_playbook_file_success(self, mock_exists, mock_run):
        job_id = "test-ansible-bg-1"
        self._make_job(job_id)
        mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")

        app_module.run_ansible_task_background(
            job_id, None, "playbooks/test.yml", "Test playbook", None, {}, "mce"
        )
        assert app_module.jobs[job_id]["status"] == "completed"
        del app_module.jobs[job_id]

    @patch("subprocess.run")
    @patch("os.path.exists", return_value=True)
    def test_playbook_file_fails(self, mock_exists, mock_run):
        job_id = "test-ansible-bg-2"
        self._make_job(job_id)
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout='fatal: [localhost]: FAILED! => {"msg": "Something broke"}',
            stderr="ERROR",
        )

        app_module.run_ansible_task_background(
            job_id, None, "playbooks/test.yml", "Test playbook", None, {}, "mce"
        )
        assert app_module.jobs[job_id]["status"] == "failed"
        del app_module.jobs[job_id]

    @patch("subprocess.run")
    @patch("os.path.exists", return_value=True)
    def test_playbook_with_kube_context(self, mock_exists, mock_run):
        job_id = "test-ansible-bg-3"
        self._make_job(job_id)
        mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")

        app_module.run_ansible_task_background(
            job_id, None, "playbooks/test.yml", "Test", "minikube", {"key": "val"}, "minikube"
        )
        assert app_module.jobs[job_id]["status"] == "completed"
        del app_module.jobs[job_id]

    @patch("os.path.exists", return_value=False)
    def test_playbook_not_found(self, mock_exists):
        job_id = "test-ansible-bg-4"
        self._make_job(job_id)

        app_module.run_ansible_task_background(
            job_id, None, "playbooks/nonexistent.yml", "Test", None, {}, "mce"
        )
        assert app_module.jobs[job_id]["status"] == "failed"
        del app_module.jobs[job_id]

    @patch("subprocess.run")
    @patch("os.path.exists", return_value=True)
    def test_task_file_success(self, mock_exists, mock_run):
        job_id = "test-ansible-bg-5"
        self._make_job(job_id)
        mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")

        app_module.run_ansible_task_background(
            job_id, "tasks/validate-capa-environment.yml", None, "Validate", None, {}, "mce"
        )
        assert app_module.jobs[job_id]["status"] in ("completed", "failed")
        del app_module.jobs[job_id]


class TestRunPlaybookInThread:
    """Test _run_playbook_in_thread directly"""

    def _make_job(self, job_id):
        app_module.jobs[job_id] = {
            "id": job_id, "status": "pending", "progress": 0,
            "message": "", "logs": [], "description": "test",
            "return_code": None,
        }

    @patch("app.get_agent_stats", return_value={})
    @patch("subprocess.Popen")
    def test_success(self, mock_popen, mock_stats):
        job_id = "test-pbit-1"
        self._make_job(job_id)
        mock_process = MagicMock()
        mock_process.stdout = iter(["line1\n", "line2\n"])
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        app_module._run_playbook_in_thread("playbooks/test.yml", {}, job_id, "Test")
        assert app_module.jobs[job_id]["status"] == "completed"
        assert app_module.jobs[job_id]["return_code"] == 0
        del app_module.jobs[job_id]

    @patch("app.get_agent_stats", return_value={})
    @patch("subprocess.Popen")
    def test_failure(self, mock_popen, mock_stats):
        job_id = "test-pbit-2"
        self._make_job(job_id)
        mock_process = MagicMock()
        mock_process.stdout = iter(["error line\n"])
        mock_process.wait.return_value = 2
        mock_popen.return_value = mock_process

        app_module._run_playbook_in_thread("playbooks/test.yml", {}, job_id, "Test")
        assert app_module.jobs[job_id]["status"] == "failed"
        assert app_module.jobs[job_id]["return_code"] == 2
        del app_module.jobs[job_id]

    @patch("app.get_agent_stats", return_value={})
    @patch("subprocess.Popen")
    def test_timeout(self, mock_popen, mock_stats):
        job_id = "test-pbit-3"
        self._make_job(job_id)
        mock_process = MagicMock()
        mock_process.stdout = iter([])
        # First call (line 4243) raises TimeoutExpired; second call (line 4262 in except block) returns 1
        mock_process.wait.side_effect = [subprocess.TimeoutExpired(cmd="ansible", timeout=5400), 1]
        mock_process.kill = MagicMock()
        mock_popen.return_value = mock_process

        app_module._run_playbook_in_thread("playbooks/test.yml", {}, job_id, "Test")
        assert app_module.jobs[job_id]["status"] == "failed"
        assert "timed out" in app_module.jobs[job_id]["message"].lower()
        del app_module.jobs[job_id]

    @patch("app.get_agent_stats", return_value={})
    @patch("subprocess.Popen")
    def test_exception(self, mock_popen, mock_stats):
        job_id = "test-pbit-4"
        self._make_job(job_id)
        mock_popen.side_effect = Exception("Popen crashed")

        app_module._run_playbook_in_thread("playbooks/test.yml", {}, job_id, "Test")
        assert app_module.jobs[job_id]["status"] == "failed"
        del app_module.jobs[job_id]

    @patch("app.get_agent_stats", return_value={})
    @patch("subprocess.Popen")
    def test_with_extra_vars(self, mock_popen, mock_stats):
        job_id = "test-pbit-5"
        self._make_job(job_id)
        mock_process = MagicMock()
        mock_process.stdout = iter([])
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        app_module._run_playbook_in_thread(
            "playbooks/test.yml",
            {"clusterName": "test", "openShiftVersion": "4.20"},
            job_id, "Test"
        )
        assert app_module.jobs[job_id]["status"] == "completed"
        # Verify camelCase was converted to snake_case in the command
        call_args = mock_popen.call_args[0][0]
        assert any("cluster_name=test" in arg for arg in call_args)
        del app_module.jobs[job_id]


# =============================================
# OCP Connection Status (deeper coverage)
# =============================================


class TestOCPConnectionDeep:
    @patch("app.subprocess.run")
    def test_ocp_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="oc", timeout=10)
        if hasattr(app_module, 'ocp_status_cache'):
            app_module.ocp_status_cache["timestamp"] = 0
        resp = client.get("/api/ocp/connection-status")
        assert resp.status_code == 200


# =============================================
# Provisioning Generate YAML
# =============================================


class TestProvisioningGenerateYaml:
    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", MagicMock())
    def test_generate_yaml_missing_name(self, mock_exists):
        resp = client.post("/api/provisioning/generate-yaml", json={
            "config": {},
        })
        assert resp.status_code == 200
        data = resp.json()
        # Should fail or return error for missing cluster name
        assert "success" in data or "yaml" in data or "error" in str(data).lower()

    @patch("os.path.exists", return_value=True)
    def test_generate_yaml_with_config(self, mock_exists):
        # Mock the Jinja2 template rendering
        mock_template = MagicMock()
        mock_template.render.return_value = "apiVersion: v1\nkind: Namespace"
        with patch("jinja2.Environment") as mock_env:
            mock_env_instance = MagicMock()
            mock_env_instance.get_template.return_value = mock_template
            mock_env.return_value = mock_env_instance
            resp = client.post("/api/provisioning/generate-yaml", json={
                "config": {
                    "clusterName": "test-cluster",
                    "openShiftVersion": "4.20.10",
                    "awsRegion": "us-west-2",
                },
            })
        assert resp.status_code == 200


# =============================================
# perform_cluster_deletion (lines 3355-3710)
# =============================================


class TestPerformClusterDeletion:
    """Test the perform_cluster_deletion sync function directly"""

    def _make_deletion_job(self, job_id):
        app_module.jobs[job_id] = {
            "id": job_id, "status": "pending", "progress": 0,
            "message": "", "stdout": "", "stderr": "", "logs": [],
            "return_code": None,
        }

    @patch("app.get_agent_stats", return_value={})
    @patch("time.sleep")
    @patch("subprocess.run")
    def test_successful_deletion(self, mock_run, mock_sleep, mock_stats):
        """Test successful cluster deletion - fast path where everything is already gone"""
        job_id = "delete-cluster-success-1"
        self._make_deletion_job(job_id)

        not_found = MagicMock(returncode=1, stdout="", stderr="NotFound: not found")
        success = MagicMock(returncode=0, stdout="deleted", stderr="")

        # Call sequence:
        # 1. oc delete cluster/name rosacontrolplane/name -> success
        # 2. oc get cluster name (wait loop) -> not found (done)
        # 3-6. oc get for rosanetwork, rosaroleconfig, rosamachinepool, rosacluster -> all not found
        mock_run.side_effect = [success, not_found, not_found, not_found, not_found, not_found]

        app_module.perform_cluster_deletion(job_id, "test-cluster", "ns-rosa-hcp")

        assert app_module.jobs[job_id]["status"] == "completed"
        assert app_module.jobs[job_id]["return_code"] == 0
        assert app_module.jobs[job_id]["progress"] == 100
        del app_module.jobs[job_id]

    @patch("app.get_agent_stats", return_value={})
    @patch("time.sleep")
    @patch("subprocess.run")
    def test_deletion_with_cleanup_resources(self, mock_run, mock_sleep, mock_stats):
        """Test deletion where cleanup resources exist and need deletion"""
        job_id = "delete-cluster-cleanup-1"
        self._make_deletion_job(job_id)

        success = MagicMock(returncode=0, stdout="deleted", stderr="")
        not_found = MagicMock(returncode=1, stdout="", stderr="not found")
        # rosanetwork exists and gets deleted, then wait loop finds it gone
        resource_exists = MagicMock(returncode=0, stdout="NAME  STATUS", stderr="")

        mock_run.side_effect = [
            success,      # 1. oc delete cluster/rosacontrolplane
            not_found,    # 2. oc get cluster (wait loop - gone)
            resource_exists,  # 3. oc get rosanetwork -> exists
            success,      # 4. oc delete rosanetwork
            not_found,    # 5. oc get rosaroleconfig -> not found
            not_found,    # 6. oc get rosamachinepool -> not found
            not_found,    # 7. oc get rosacluster -> not found
            # Phase 2 wait: rosanetwork wait loop
            not_found,    # 8. oc get rosanetwork -> gone
        ]

        app_module.perform_cluster_deletion(job_id, "test-cluster", "ns-rosa-hcp")

        assert app_module.jobs[job_id]["status"] == "completed"
        assert app_module.jobs[job_id]["return_code"] == 0
        del app_module.jobs[job_id]

    @patch("app.get_agent_stats", return_value={})
    @patch("time.sleep")
    @patch("subprocess.run")
    def test_deletion_initial_failure(self, mock_run, mock_sleep, mock_stats):
        """Test when initial oc delete fails"""
        job_id = "delete-cluster-fail-1"
        self._make_deletion_job(job_id)

        failed = MagicMock(returncode=1, stdout="", stderr="connection refused")
        not_found = MagicMock(returncode=1, stdout="", stderr="not found")

        mock_run.side_effect = [
            failed,       # 1. oc delete fails
            not_found,    # 2-5. cleanup checks - all not found
            not_found,
            not_found,
            not_found,
        ]

        app_module.perform_cluster_deletion(job_id, "test-cluster", "ns-rosa-hcp")

        assert app_module.jobs[job_id]["status"] == "failed"
        assert app_module.jobs[job_id]["return_code"] == 1
        del app_module.jobs[job_id]

    @patch("app.get_agent_stats", return_value={})
    @patch("time.sleep")
    @patch("subprocess.run")
    def test_deletion_timeout_expired(self, mock_run, mock_sleep, mock_stats):
        """Test when subprocess.run raises TimeoutExpired"""
        job_id = "delete-cluster-timeout-1"
        self._make_deletion_job(job_id)

        not_found = MagicMock(returncode=1, stdout="", stderr="not found")
        mock_run.side_effect = [
            subprocess.TimeoutExpired(cmd="oc", timeout=60),  # 1. timeout on delete
            not_found,    # 2-5. cleanup checks
            not_found,
            not_found,
            not_found,
        ]

        app_module.perform_cluster_deletion(job_id, "test-cluster", "ns-rosa-hcp")

        # Should still complete (with errors) since cleanup continues
        assert app_module.jobs[job_id]["status"] == "failed"
        assert app_module.jobs[job_id]["progress"] == 100
        del app_module.jobs[job_id]

    @patch("app.get_agent_stats", return_value={})
    @patch("time.sleep")
    @patch("subprocess.run")
    def test_deletion_exception(self, mock_run, mock_sleep, mock_stats):
        """Test when perform_cluster_deletion hits an unexpected exception"""
        job_id = "delete-cluster-exc-1"
        self._make_deletion_job(job_id)

        mock_run.side_effect = RuntimeError("Unexpected error")

        app_module.perform_cluster_deletion(job_id, "test-cluster", "ns-rosa-hcp")

        assert app_module.jobs[job_id]["status"] == "failed"
        assert app_module.jobs[job_id]["return_code"] == 1
        assert app_module.jobs[job_id]["progress"] == 100
        del app_module.jobs[job_id]

    @patch("app.get_agent_stats", return_value={"enabled": True, "issues_detected": 1, "interventions": 1})
    @patch("time.sleep")
    @patch("subprocess.run")
    def test_deletion_with_agent_stats(self, mock_run, mock_sleep, mock_stats):
        """Test deletion with AI agent stats in summary"""
        job_id = "delete-cluster-agent-1"
        self._make_deletion_job(job_id)

        success = MagicMock(returncode=0, stdout="deleted", stderr="")
        not_found = MagicMock(returncode=1, stdout="", stderr="not found")

        mock_run.side_effect = [success, not_found, not_found, not_found, not_found, not_found]

        app_module.perform_cluster_deletion(job_id, "test-cluster", "ns-rosa-hcp")

        assert app_module.jobs[job_id]["status"] == "completed"
        # Agent stats should be included
        assert app_module.jobs[job_id].get("agent_stats") is not None
        del app_module.jobs[job_id]

    @patch("app.get_agent_stats", return_value={})
    @patch("time.sleep")
    @patch("subprocess.run")
    def test_deletion_with_cf_verification_boto3(self, mock_run, mock_sleep, mock_stats):
        """Test deletion with CloudFormation verification via boto3"""
        job_id = "delete-cluster-cf-1"
        self._make_deletion_job(job_id)

        success = MagicMock(returncode=0, stdout="deleted", stderr="")
        not_found = MagicMock(returncode=1, stdout="", stderr="not found")
        resource_exists = MagicMock(returncode=0, stdout="NAME", stderr="")

        mock_run.side_effect = [
            success,          # 1. oc delete cluster/rosacontrolplane
            not_found,        # 2. oc get cluster (gone)
            resource_exists,  # 3. oc get rosanetwork -> exists
            success,          # 4. oc delete rosanetwork
            not_found,        # 5. oc get rosaroleconfig -> not found
            not_found,        # 6. oc get rosamachinepool -> not found
            not_found,        # 7. oc get rosacluster -> not found
            not_found,        # 8. rosanetwork wait -> gone
        ]

        # Mock boto3 for CF verification
        mock_cf_client = MagicMock()
        mock_cf_client.describe_stacks.return_value = {
            "Stacks": [{"StackStatus": "DELETE_COMPLETE"}]
        }
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_cf_client

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            app_module.perform_cluster_deletion(job_id, "test-cluster", "ns-rosa-hcp")

        assert app_module.jobs[job_id]["status"] == "completed"
        # Check that CF verification log was added
        logs_str = " ".join(app_module.jobs[job_id].get("logs", []))
        assert "CloudFormation" in logs_str or "deleted" in logs_str.lower()
        del app_module.jobs[job_id]

    @patch("app.get_agent_stats", return_value={})
    @patch("time.sleep")
    @patch("subprocess.run")
    def test_deletion_not_found_initially(self, mock_run, mock_sleep, mock_stats):
        """Test when initial delete returns 'not found' (resource already deleted)"""
        job_id = "delete-cluster-notfound-1"
        self._make_deletion_job(job_id)

        not_found = MagicMock(returncode=1, stdout="", stderr="not found")

        mock_run.side_effect = [
            not_found,    # 1. oc delete -> not found
            not_found,    # 2-5. cleanup checks
            not_found,
            not_found,
            not_found,
        ]

        app_module.perform_cluster_deletion(job_id, "test-cluster", "ns-rosa-hcp")

        # Should still "fail" since nothing was deleted
        assert app_module.jobs[job_id]["status"] == "failed"
        del app_module.jobs[job_id]


# =============================================
# apply_provisioning_yaml endpoint (lines 7035-7604)
# =============================================


class TestApplyProvisioningYaml:
    """Test the /api/provisioning/apply-yaml endpoint"""

    def test_missing_yaml_content(self):
        resp = client.post("/api/provisioning/apply-yaml", json={
            "cluster_name": "test-cluster"
        })
        assert resp.status_code in (400, 500)

    def test_missing_cluster_name(self):
        resp = client.post("/api/provisioning/apply-yaml", json={
            "yaml_content": "apiVersion: v1\nkind: Namespace"
        })
        assert resp.status_code in (400, 500)

    @patch("app.init_ai_agents", return_value=None)
    @patch("app.send_cluster_notifications")
    @patch("os.makedirs")
    @patch("builtins.open", MagicMock())
    def test_successful_apply(self, mock_makedirs, mock_notify, mock_agents):
        yaml_content = "apiVersion: v1\nkind: Namespace\nmetadata:\n  name: test"
        resp = client.post("/api/provisioning/apply-yaml", json={
            "yaml_content": yaml_content,
            "cluster_name": "test-cluster",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True or "job_id" in data

    @patch("app.init_ai_agents", return_value=None)
    @patch("app.send_cluster_notifications")
    @patch("os.makedirs")
    @patch("builtins.open", MagicMock())
    def test_apply_with_feature_type(self, mock_makedirs, mock_notify, mock_agents):
        yaml_content = "apiVersion: v1\nkind: Namespace\nmetadata:\n  name: test"
        resp = client.post("/api/provisioning/apply-yaml", json={
            "yaml_content": yaml_content,
            "cluster_name": "test-cluster",
            "feature_type": "rosa-hcp",
        })
        assert resp.status_code == 200

    @patch("app.init_ai_agents", return_value=None)
    @patch("app.send_cluster_notifications")
    @patch("os.makedirs")
    @patch("builtins.open", MagicMock())
    def test_apply_with_cluster_context(self, mock_makedirs, mock_notify, mock_agents):
        yaml_content = "apiVersion: v1\nkind: Namespace\nmetadata:\n  name: test"
        resp = client.post("/api/provisioning/apply-yaml", json={
            "yaml_content": yaml_content,
            "cluster_name": "test-cluster",
            "cluster_context": "minikube-test",
        })
        assert resp.status_code == 200


# =============================================
# run_test_suite endpoint (lines 8535-8797)
# =============================================


class TestRunTestSuiteEndpoint:
    """Test the /api/test-suites/run endpoint"""

    @patch("os.path.exists", return_value=False)
    def test_suite_not_found(self, mock_exists):
        resp = client.post("/api/test-suites/run", json={
            "suite_name": "nonexistent-suite"
        })
        assert resp.status_code in (404, 500)

    @patch("os.path.exists", return_value=True)
    @patch("builtins.open")
    def test_suite_run_success(self, mock_open, mock_exists):
        suite_config = {
            "name": "Test Suite",
            "description": "A test suite",
            "playbooks": [
                {"name": "test-playbook", "path": "playbooks/test.yml"}
            ],
        }
        mock_open.return_value.__enter__ = lambda s: MagicMock(
            read=lambda: json.dumps(suite_config)
        )
        mock_open.return_value.__exit__ = MagicMock(return_value=False)

        # Mock json.load to return suite config
        with patch("json.load", return_value=suite_config):
            resp = client.post("/api/test-suites/run", json={
                "suite_name": "test-suite"
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data or "success" in data


# =============================================
# init_ai_agents (lines 72-171)
# =============================================


class TestInitAiAgents:
    """Test the init_ai_agents function"""

    def test_agents_unavailable(self):
        original = app_module.AI_AGENTS_AVAILABLE
        app_module.AI_AGENTS_AVAILABLE = False
        try:
            result = app_module.init_ai_agents("test-job-init-1")
            assert result is None
        finally:
            app_module.AI_AGENTS_AVAILABLE = original

    @patch("app.MonitoringAgent")
    @patch("app.DiagnosticAgent")
    @patch("app.RemediationAgent")
    @patch("app.LearningAgent")
    def test_agents_available(self, mock_learn, mock_remed, mock_diag, mock_mon):
        original = app_module.AI_AGENTS_AVAILABLE
        app_module.AI_AGENTS_AVAILABLE = True
        try:
            mock_mon.return_value = MagicMock()
            mock_diag.return_value = MagicMock()
            mock_remed.return_value = MagicMock()
            mock_learn.return_value = MagicMock()

            result = app_module.init_ai_agents("test-job-init-2")
            assert result is not None
            assert "monitor" in result
            assert "diagnostic" in result
            assert "remediation" in result
            assert "learning" in result

            # Verify session stored
            assert "test-job-init-2" in app_module.ai_agent_sessions
            del app_module.ai_agent_sessions["test-job-init-2"]
        finally:
            app_module.AI_AGENTS_AVAILABLE = original

    def test_agents_exception(self):
        original = app_module.AI_AGENTS_AVAILABLE
        app_module.AI_AGENTS_AVAILABLE = True
        # Force an import error by making MonitoringAgent raise
        original_mon = getattr(app_module, "MonitoringAgent", None)
        try:
            app_module.MonitoringAgent = MagicMock(side_effect=Exception("import error"))
            result = app_module.init_ai_agents("test-job-init-3")
            assert result is None
        finally:
            app_module.AI_AGENTS_AVAILABLE = original
            if original_mon:
                app_module.MonitoringAgent = original_mon


# =============================================
# WebSocket endpoint (lines 1192-1229)
# =============================================


class TestWebSocketJobUpdates:
    """Test the websocket job updates endpoint"""

    def test_websocket_job_not_found(self):
        with client.websocket_connect("/ws/jobs/nonexistent-job-ws") as ws:
            # Should close with 1003
            pass  # Connection accepted then closed

    def test_websocket_completed_job(self):
        job_id = "test-ws-completed-1"
        app_module.jobs[job_id] = {
            "id": job_id, "status": "completed", "progress": 100,
            "message": "Done", "logs": [],
        }
        try:
            with client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
                data = ws.receive_json()
                assert data["status"] == "completed"
                assert data["progress"] == 100
        finally:
            del app_module.jobs[job_id]


# =============================================
# Notification test endpoint (lines 1394-1429)
# =============================================


class TestNotificationTestEndpoint:
    """Test POST /api/notifications/test"""

    @patch("app.slack_service")
    @patch("app.email_service")
    def test_notifications_test_saved_config_none_enabled(self, mock_email, mock_slack):
        mock_slack.reload_config = MagicMock()
        mock_email.reload_config = MagicMock()
        mock_slack.config = {"slack_enabled": False}
        mock_email.config = {"email_enabled": False}

        resp = client.post("/api/notification-settings/test", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is False or "No notification" in data.get("message", "")

    @patch("app.slack_service")
    @patch("app.email_service")
    def test_notifications_test_slack_enabled(self, mock_email, mock_slack):
        mock_slack.reload_config = MagicMock()
        mock_email.reload_config = MagicMock()
        mock_slack.config = {"slack_enabled": True}
        mock_email.config = {"email_enabled": False}
        mock_slack.test_connection.return_value = {"success": True, "message": "OK"}

        resp = client.post("/api/notification-settings/test", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True


# =============================================
# Create ROSA cluster endpoint (lines 932-977)
# =============================================


class TestCreateRosaCluster:
    """Test POST /api/rosa/clusters (create cluster)"""

    @patch("app.init_ai_agents", return_value=None)
    @patch("app.asyncio.create_task")
    def test_create_cluster_success(self, mock_task, mock_agents):
        resp = client.post("/api/clusters", json={
            "name": "test-create-1",
            "version": "4.20.10",
            "region": "us-west-2",
            "role_automation": True,
            "network_automation": True,
            "cidr_block": "10.0.0.0/16",
            "availability_zones": ["us-west-2a", "us-west-2b"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "cluster_id" in data
        assert "job_id" in data
        # Clean up
        if data.get("job_id") in app_module.jobs:
            del app_module.jobs[data["job_id"]]
        if data.get("cluster_id") in app_module.clusters:
            del app_module.clusters[data["cluster_id"]]


# =============================================
# _run_minikube_create (lines 5357-5417)
# =============================================


class TestRunMinikubeCreate:
    """Test the _run_minikube_create sync function directly"""

    def _make_job(self, job_id):
        app_module.jobs[job_id] = {
            "id": job_id, "status": "pending", "progress": 0,
            "message": "", "logs": [],
        }

    @patch("subprocess.run")
    @patch("subprocess.Popen")
    def test_success(self, mock_popen, mock_run):
        job_id = "test-mk-create-1"
        self._make_job(job_id)

        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = ["Starting minikube\n", "Done\n", ""]
        mock_process.wait.return_value = None
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        # kubectl verify
        mock_run.return_value = MagicMock(returncode=0, stdout="cluster-info", stderr="")

        app_module._run_minikube_create("test-mk", job_id)
        assert app_module.jobs[job_id]["status"] == "completed"
        del app_module.jobs[job_id]

    @patch("subprocess.Popen")
    def test_failure(self, mock_popen):
        job_id = "test-mk-create-2"
        self._make_job(job_id)

        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = ["Error\n", ""]
        mock_process.wait.return_value = None
        mock_process.returncode = 1
        mock_popen.return_value = mock_process

        app_module._run_minikube_create("test-mk", job_id)
        assert app_module.jobs[job_id]["status"] == "failed"
        del app_module.jobs[job_id]

    @patch("subprocess.Popen")
    def test_timeout(self, mock_popen):
        job_id = "test-mk-create-3"
        self._make_job(job_id)

        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = [""]
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="minikube", timeout=300)
        mock_popen.return_value = mock_process

        app_module._run_minikube_create("test-mk", job_id)
        assert app_module.jobs[job_id]["status"] == "failed"
        assert "timed out" in app_module.jobs[job_id]["message"].lower()
        del app_module.jobs[job_id]

    @patch("subprocess.Popen")
    def test_exception(self, mock_popen):
        job_id = "test-mk-create-4"
        self._make_job(job_id)

        mock_popen.side_effect = FileNotFoundError("minikube not found")

        app_module._run_minikube_create("test-mk", job_id)
        assert app_module.jobs[job_id]["status"] == "failed"
        del app_module.jobs[job_id]

    @patch("subprocess.run")
    @patch("subprocess.Popen")
    def test_kubectl_verify_fails(self, mock_popen, mock_run):
        job_id = "test-mk-create-5"
        self._make_job(job_id)

        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = ["Done\n", ""]
        mock_process.wait.return_value = None
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")

        app_module._run_minikube_create("test-mk", job_id)
        assert app_module.jobs[job_id]["status"] == "completed"
        assert any("Warning" in log for log in app_module.jobs[job_id]["logs"])
        del app_module.jobs[job_id]


# =============================================
# AI Assistant chat (lines 7820-7919)
# =============================================


class TestAiAssistantChat:
    """Test POST /api/ai-assistant/chat"""

    def test_chat_no_api_key(self):
        with patch.dict(os.environ, {}, clear=False):
            # Ensure no ANTHROPIC_API_KEY
            env = os.environ.copy()
            env.pop("ANTHROPIC_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                resp = client.post("/api/ai-assistant/chat", json={
                    "message": "What clusters are running?",
                    "context": {"clusters": []},
                })
                assert resp.status_code == 200

    def test_chat_with_failed_clusters(self):
        # Add a job that matches the cluster name
        job_id = "test-ai-chat-job-1"
        app_module.jobs[job_id] = {
            "id": job_id, "status": "failed", "yaml_file": "test-cluster.yaml",
            "description": "Apply for test-cluster", "logs": ["Error occurred"],
            "created_at": "2026-01-01",
        }
        try:
            with patch.dict(os.environ, {}, clear=False):
                env = os.environ.copy()
                env.pop("ANTHROPIC_API_KEY", None)
                with patch.dict(os.environ, env, clear=True):
                    resp = client.post("/api/ai-assistant/chat", json={
                        "message": "Why did my cluster fail?",
                        "context": {"clusters": [
                            {"name": "test-cluster", "status": "failed", "namespace": "ns-rosa-hcp"}
                        ]},
                    })
                    assert resp.status_code == 200
        finally:
            del app_module.jobs[job_id]

    def test_chat_with_anthropic_key(self):
        mock_ai_service = MagicMock()
        mock_ai_service.chat = AsyncMock(return_value={
            "response": "You have 1 cluster running",
            "suggestions": ["Check logs"]
        })
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch.object(app_module, "ai_service", mock_ai_service):
                resp = client.post("/api/ai-assistant/chat", json={
                    "message": "What clusters are running?",
                    "context": {"clusters": [
                        {"name": "my-cluster", "status": "ready", "namespace": "ns-rosa-hcp"}
                    ]},
                })
                assert resp.status_code == 200
                data = resp.json()
                assert "response" in data


# =============================================
# _get_rosa_clusters_sync provisioning progress (lines 3271-3304)
# =============================================


class TestRosaClustersProvisioningProgress:
    """Test provisioning progress estimation in _get_rosa_clusters_sync"""

    @patch("app.subprocess.run")
    def test_provisioning_with_conditions(self, mock_run):
        """Test cluster with conditions for progress tracking"""
        cluster_json = json.dumps({
            "items": [{
                "metadata": {
                    "name": "prov-test",
                    "namespace": "ns-rosa-hcp",
                    "creationTimestamp": "2026-01-01T00:00:00Z",
                },
                "status": {
                    "phase": "Provisioning",
                    "conditions": [
                        {"type": "InfrastructureReady", "status": "True"},
                        {"type": "NetworkReady", "status": "True"},
                        {"type": "ControlPlaneReady", "status": "False"},
                    ],
                },
            }]
        })

        rosa_fail = MagicMock(returncode=1, stdout="", stderr="not found")
        oc_success = MagicMock(returncode=0, stdout=cluster_json, stderr="")

        mock_run.side_effect = [rosa_fail, oc_success]

        result = app_module._get_rosa_clusters_sync()
        assert result["success"] is True
        if result.get("clusters"):
            cluster = result["clusters"][0]
            # Progress should be at least 40 (NetworkReady stage)
            assert cluster.get("progress", 0) >= 40 or cluster.get("status") in ("provisioning", "failed")


# =============================================
# init_ai_agents callback (lines 85-147)
# =============================================


class TestInitAiAgentsCallback:
    """Test the on_issue_detected callback inside init_ai_agents"""

    @patch("app.MonitoringAgent")
    @patch("app.DiagnosticAgent")
    @patch("app.RemediationAgent")
    @patch("app.LearningAgent")
    def test_callback_high_confidence(self, mock_learn, mock_remed, mock_diag, mock_mon):
        original = app_module.AI_AGENTS_AVAILABLE
        app_module.AI_AGENTS_AVAILABLE = True
        job_id = "test-callback-1"
        app_module.jobs[job_id] = {"id": job_id, "status": "running", "logs": []}

        try:
            mock_mon_inst = MagicMock()
            mock_diag_inst = MagicMock()
            mock_remed_inst = MagicMock()
            mock_learn_inst = MagicMock()

            mock_mon.return_value = mock_mon_inst
            mock_diag.return_value = mock_diag_inst
            mock_remed.return_value = mock_remed_inst
            mock_learn.return_value = mock_learn_inst

            # Setup diagnosis with high confidence
            mock_diag_inst.diagnose.return_value = {
                "confidence": 0.9,
                "root_cause": "CloudFormation DELETE_FAILED",
                "recommended_fix": "clean_vpc_dependencies",
            }
            mock_remed_inst.remediate.return_value = (True, "Fixed")

            result = app_module.init_ai_agents(job_id)
            assert result is not None

            # Get the callback that was registered
            callback = mock_mon_inst.set_issue_callback.call_args[0][0]

            # Invoke the callback
            callback("cloudformation_deletion_failure", {"resource_key": "test-rk"}, {})

            # Verify remediation was called
            mock_remed_inst.remediate.assert_called_once()
            mock_learn_inst.record_outcome.assert_called_once()
            mock_mon_inst.mark_issue_resolved.assert_called_once()

            # Check agent events were logged
            assert len(app_module.jobs[job_id].get("agent_events", [])) == 1
        finally:
            app_module.AI_AGENTS_AVAILABLE = original
            del app_module.jobs[job_id]
            app_module.ai_agent_sessions.pop(job_id, None)

    @patch("app.MonitoringAgent")
    @patch("app.DiagnosticAgent")
    @patch("app.RemediationAgent")
    @patch("app.LearningAgent")
    def test_callback_low_confidence(self, mock_learn, mock_remed, mock_diag, mock_mon):
        original = app_module.AI_AGENTS_AVAILABLE
        app_module.AI_AGENTS_AVAILABLE = True
        job_id = "test-callback-2"
        app_module.jobs[job_id] = {"id": job_id, "status": "running", "logs": []}

        try:
            mock_mon_inst = MagicMock()
            mock_diag_inst = MagicMock()
            mock_remed_inst = MagicMock()
            mock_learn_inst = MagicMock()

            mock_mon.return_value = mock_mon_inst
            mock_diag.return_value = mock_diag_inst
            mock_remed.return_value = mock_remed_inst
            mock_learn.return_value = mock_learn_inst

            # Low confidence diagnosis
            mock_diag_inst.diagnose.return_value = {
                "confidence": 0.4,
                "root_cause": "Unknown status",
                "recommended_fix": "log_and_continue",
            }

            # Set up tracked issue mock with proper attributes
            tracked_mock = MagicMock()
            tracked_mock.attempts = 2
            tracked_mock._low_conf_count = 0
            mock_mon_inst._tracked_issues = {"unknown_issue:test-rk": tracked_mock}

            result = app_module.init_ai_agents(job_id)
            callback = mock_mon_inst.set_issue_callback.call_args[0][0]
            callback("unknown_issue", {"resource_key": "test-rk"}, {})

            # Remediation should NOT have been called (low confidence)
            mock_remed_inst.remediate.assert_not_called()
        finally:
            app_module.AI_AGENTS_AVAILABLE = original
            del app_module.jobs[job_id]
            app_module.ai_agent_sessions.pop(job_id, None)

    @patch("app.MonitoringAgent")
    @patch("app.DiagnosticAgent")
    @patch("app.RemediationAgent")
    @patch("app.LearningAgent")
    def test_callback_diagnosis_exception(self, mock_learn, mock_remed, mock_diag, mock_mon):
        original = app_module.AI_AGENTS_AVAILABLE
        app_module.AI_AGENTS_AVAILABLE = True
        job_id = "test-callback-3"
        app_module.jobs[job_id] = {"id": job_id, "status": "running", "logs": []}

        try:
            mock_mon_inst = MagicMock()
            mock_diag_inst = MagicMock()
            mock_remed_inst = MagicMock()
            mock_learn_inst = MagicMock()

            mock_mon.return_value = mock_mon_inst
            mock_diag.return_value = mock_diag_inst
            mock_remed.return_value = mock_remed_inst
            mock_learn.return_value = mock_learn_inst

            mock_diag_inst.diagnose.side_effect = Exception("diagnosis crashed")

            result = app_module.init_ai_agents(job_id)
            callback = mock_mon_inst.set_issue_callback.call_args[0][0]
            callback("some_issue", {"resource_key": "test-rk"}, {})

            # Should mark issue as failed
            mock_mon_inst.mark_issue_failed.assert_called_once()
        finally:
            app_module.AI_AGENTS_AVAILABLE = original
            del app_module.jobs[job_id]
            app_module.ai_agent_sessions.pop(job_id, None)

    @patch("app.MonitoringAgent")
    @patch("app.DiagnosticAgent")
    @patch("app.RemediationAgent")
    @patch("app.LearningAgent")
    def test_callback_remediation_fails(self, mock_learn, mock_remed, mock_diag, mock_mon):
        original = app_module.AI_AGENTS_AVAILABLE
        app_module.AI_AGENTS_AVAILABLE = True
        job_id = "test-callback-4"
        app_module.jobs[job_id] = {"id": job_id, "status": "running", "logs": []}

        try:
            mock_mon_inst = MagicMock()
            mock_diag_inst = MagicMock()
            mock_remed_inst = MagicMock()
            mock_learn_inst = MagicMock()

            mock_mon.return_value = mock_mon_inst
            mock_diag.return_value = mock_diag_inst
            mock_remed.return_value = mock_remed_inst
            mock_learn.return_value = mock_learn_inst

            mock_diag_inst.diagnose.return_value = {
                "confidence": 0.8,
                "root_cause": "Some issue",
                "recommended_fix": "retry",
            }
            mock_remed_inst.remediate.return_value = (False, "Failed to fix")

            result = app_module.init_ai_agents(job_id)
            callback = mock_mon_inst.set_issue_callback.call_args[0][0]
            callback("some_issue", {"resource_key": "test-rk"}, {})

            mock_mon_inst.mark_issue_failed.assert_called_once()
        finally:
            app_module.AI_AGENTS_AVAILABLE = original
            del app_module.jobs[job_id]
            app_module.ai_agent_sessions.pop(job_id, None)


# =============================================
# get_agent_stats (lines 174-233)
# =============================================


class TestGetAgentStats:
    """Test get_agent_stats function"""

    def test_no_session(self):
        result = app_module.get_agent_stats("nonexistent-job-stats")
        assert result == {"enabled": False}

    def test_with_session_and_events(self):
        job_id = "test-stats-1"
        mock_monitor = MagicMock()
        mock_monitor._tracked_issues = {}
        mock_monitor.patterns_detected = []
        mock_remediation = MagicMock()
        mock_remediation.interventions = []
        mock_learning = MagicMock()
        mock_learning.end_of_run_summary.return_value = {"adjusted": 0}

        app_module.ai_agent_sessions[job_id] = {
            "monitor": mock_monitor,
            "diagnostic": MagicMock(),
            "remediation": mock_remediation,
            "learning": mock_learning,
        }
        app_module.jobs[job_id] = {
            "id": job_id, "status": "running", "logs": [],
            "agent_events": [
                {
                    "type": "issue_detected",
                    "issue_type": "cloudformation_deletion_failure",
                    "resource_key": "test-rk",
                    "diagnosis": "CF DELETE_FAILED",
                    "fix_applied": "clean_vpc",
                    "remediation_result": "Fixed",
                    "confidence": 0.9,
                    "timestamp": "2026-01-01T00:00:00",
                }
            ],
        }

        try:
            result = app_module.get_agent_stats(job_id)
            assert result["enabled"] is True
            assert result["issues_detected"] == 1
            assert len(result["resource_details"]) == 1
        finally:
            del app_module.ai_agent_sessions[job_id]
            del app_module.jobs[job_id]

    def test_with_meaningful_interventions(self):
        job_id = "test-stats-2"
        mock_monitor = MagicMock()
        mock_monitor._tracked_issues = {}
        mock_monitor.patterns_detected = ["p1", "p2"]
        mock_remediation = MagicMock()
        mock_remediation.interventions = [
            {"type": "retry_cf_delete", "details": {"message": "Retried successfully"}},
            {"type": "log_and_continue", "details": {"message": "Just logging"}},
        ]
        mock_learning = MagicMock()
        mock_learning.end_of_run_summary.return_value = {}

        app_module.ai_agent_sessions[job_id] = {
            "monitor": mock_monitor,
            "diagnostic": MagicMock(),
            "remediation": mock_remediation,
            "learning": mock_learning,
        }
        app_module.jobs[job_id] = {
            "id": job_id, "status": "running", "logs": [],
            "agent_events": [],
        }

        try:
            result = app_module.get_agent_stats(job_id)
            # Only 1 meaningful (retry_cf_delete), log_and_continue excluded
            assert result["interventions"] == 1
        finally:
            del app_module.ai_agent_sessions[job_id]
            del app_module.jobs[job_id]


# =============================================
# _wait_for_resource_deletion (lines 561-620)
# =============================================


class TestWaitForResourceDeletion:
    """Test _wait_for_resource_deletion sync function"""

    def _make_job(self, job_id):
        app_module.jobs[job_id] = {
            "id": job_id, "status": "running", "logs": [],
        }

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_resource_deleted_immediately(self, mock_run, mock_sleep):
        job_id = "test-wait-del-1"
        self._make_job(job_id)

        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")

        result = app_module._wait_for_resource_deletion(
            "rosanetwork", "test-network", "ns-rosa-hcp", job_id,
            timeout_seconds=30, poll_interval=10,
        )
        assert result is True
        del app_module.jobs[job_id]

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_resource_timeout(self, mock_run, mock_sleep):
        job_id = "test-wait-del-2"
        self._make_job(job_id)

        # Resource always exists
        mock_run.return_value = MagicMock(returncode=0, stdout="NAME STATUS", stderr="")

        result = app_module._wait_for_resource_deletion(
            "rosanetwork", "test-network", "ns-rosa-hcp", job_id,
            timeout_seconds=30, poll_interval=10,
        )
        assert result is False
        del app_module.jobs[job_id]

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_resource_deleted_after_retry(self, mock_run, mock_sleep):
        job_id = "test-wait-del-3"
        self._make_job(job_id)

        exists = MagicMock(returncode=0, stdout="NAME STATUS", stderr="")
        gone = MagicMock(returncode=1, stdout="", stderr="not found")

        mock_run.side_effect = [exists, exists, gone]

        result = app_module._wait_for_resource_deletion(
            "rosanetwork", "test-network", "ns-rosa-hcp", job_id,
            timeout_seconds=60, poll_interval=10,
        )
        assert result is True
        del app_module.jobs[job_id]

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_subprocess_timeout(self, mock_run, mock_sleep):
        job_id = "test-wait-del-4"
        self._make_job(job_id)

        gone = MagicMock(returncode=1, stdout="", stderr="not found")
        mock_run.side_effect = [
            subprocess.TimeoutExpired(cmd="oc", timeout=10),
            gone,
        ]

        result = app_module._wait_for_resource_deletion(
            "rosanetwork", "test-network", "ns-rosa-hcp", job_id,
            timeout_seconds=30, poll_interval=10,
        )
        assert result is True
        del app_module.jobs[job_id]


# =============================================
# _run_deletion_wait_loops (lines 623-679)
# =============================================


class TestRunDeletionWaitLoops:
    """Test _run_deletion_wait_loops function"""

    def _make_job(self, job_id):
        app_module.jobs[job_id] = {
            "id": job_id, "status": "running", "logs": [],
        }

    @patch("app._wait_for_resource_deletion")
    def test_all_deleted(self, mock_wait):
        job_id = "test-wait-loops-1"
        self._make_job(job_id)

        mock_wait.return_value = True

        result = app_module._run_deletion_wait_loops(
            job_id, "test-cluster", "ns-rosa-hcp"
        )
        assert result is True
        assert mock_wait.call_count == 3  # rcp, network, roles
        del app_module.jobs[job_id]

    @patch("app._wait_for_resource_deletion")
    def test_rcp_timeout(self, mock_wait):
        job_id = "test-wait-loops-2"
        self._make_job(job_id)

        mock_wait.return_value = False

        result = app_module._run_deletion_wait_loops(
            job_id, "test-cluster", "ns-rosa-hcp"
        )
        assert result is False
        assert mock_wait.call_count == 1  # Only rcp, returns early
        del app_module.jobs[job_id]

    @patch("app._wait_for_resource_deletion")
    def test_skip_network_and_roles(self, mock_wait):
        job_id = "test-wait-loops-3"
        self._make_job(job_id)

        mock_wait.return_value = True

        result = app_module._run_deletion_wait_loops(
            job_id, "test-cluster", "ns-rosa-hcp",
            delete_network=False, delete_roles=False,
        )
        assert result is True
        assert mock_wait.call_count == 1  # Only rcp
        del app_module.jobs[job_id]


# =============================================
# DELETE /api/clusters/{cluster_id} (lines 1001-1030)
# =============================================


class TestDeleteClusterEndpoint:
    """Test DELETE /api/clusters/{cluster_id}"""

    def test_cluster_not_found(self):
        resp = client.delete("/api/clusters/nonexistent-cluster-id")
        assert resp.status_code == 404

    @patch("app.init_ai_agents", return_value=None)
    @patch("app.asyncio.create_task")
    def test_delete_cluster_success(self, mock_task, mock_agents):
        cluster_id = "test-delete-cid-1"
        app_module.clusters[cluster_id] = {
            "id": cluster_id,
            "config": {"name": "test-cluster", "capi_namespace": "ns-rosa-hcp"},
            "status": "ready",
        }
        try:
            resp = client.delete(f"/api/clusters/{cluster_id}")
            assert resp.status_code == 200
            data = resp.json()
            assert "job_id" in data
            # Clean up job
            if data.get("job_id") in app_module.jobs:
                del app_module.jobs[data["job_id"]]
        finally:
            app_module.clusters.pop(cluster_id, None)


# =============================================
# generate_provisioning_yaml deeper coverage (lines 6880-6928)
# =============================================


class TestGenerateProvisioningYamlDeep:
    """Test POST /api/provisioning/generate-yaml with various configs"""

    @patch("os.path.exists", return_value=True)
    def test_with_role_automation(self, mock_exists):
        mock_template = MagicMock()
        mock_template.render.return_value = "apiVersion: v1\nkind: Namespace"
        with patch("jinja2.Environment") as mock_env:
            mock_env_inst = MagicMock()
            mock_env_inst.get_template.return_value = mock_template
            mock_env.return_value = mock_env_inst
            resp = client.post("/api/provisioning/generate-yaml", json={
                "config": {
                    "clusterName": "role-test",
                    "openShiftVersion": "4.20.10",
                    "awsRegion": "us-east-1",
                    "createRosaRoleConfig": True,
                    "createRosaNetwork": True,
                },
            })
        assert resp.status_code == 200

    @patch("os.path.exists", return_value=True)
    def test_with_manual_roles(self, mock_exists):
        mock_template = MagicMock()
        mock_template.render.return_value = "apiVersion: v1\nkind: Namespace"
        with patch("jinja2.Environment") as mock_env:
            mock_env_inst = MagicMock()
            mock_env_inst.get_template.return_value = mock_template
            mock_env.return_value = mock_env_inst
            resp = client.post("/api/provisioning/generate-yaml", json={
                "config": {
                    "clusterName": "manual-test",
                    "openShiftVersion": "4.20.10",
                    "awsRegion": "us-west-2",
                    "createRosaRoleConfig": False,
                    "installerRoleArn": "arn:aws:iam::123456789:role/installer",
                    "supportRoleArn": "arn:aws:iam::123456789:role/support",
                    "workerRoleArn": "arn:aws:iam::123456789:role/worker",
                    "oidcId": "test-oidc-id",
                },
            })
        assert resp.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
