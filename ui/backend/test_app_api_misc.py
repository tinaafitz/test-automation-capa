"""
Tests for miscellaneous API endpoints: health, root, user profile, build templates,
validate config, CLI versions, Jenkins trend, GitHub activity, single resource usage,
and resource details.
"""

import importlib
import json
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
# GET / and GET /api/health
# =============================================


class TestRootAndHealth:
    def test_root(self):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert "version" in data

    def test_health(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"


# =============================================
# GET /api/user/profile
# =============================================


class TestUserProfile:
    def test_get_profile(self):
        resp = client.get("/api/user/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert "identity" in data
        assert "permissions" in data
        assert "quotas" in data
        assert "recent_activity" in data

    def test_profile_has_permissions(self):
        resp = client.get("/api/user/profile")
        data = resp.json()
        perms = data["permissions"]
        assert "cluster_create" in perms
        assert "cluster_delete" in perms


# =============================================
# GET /api/build/templates
# =============================================


class TestBuildTemplates:
    def test_get_build_templates(self):
        resp = client.get("/api/build/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert "templates" in data
        assert len(data["templates"]) >= 3

    def test_templates_have_specs(self):
        resp = client.get("/api/build/templates")
        data = resp.json()
        for tmpl in data["templates"]:
            assert "id" in tmpl
            assert "name" in tmpl
            assert "specs" in tmpl
            assert "estimated_cost" in tmpl


# =============================================
# POST /api/validate
# =============================================


class TestValidateConfig:
    def test_valid_config(self):
        resp = client.post("/api/validate", json={
            "name": "my-cluster",
            "version": "4.20.12",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert len(data["errors"]) == 0

    def test_invalid_name_chars(self):
        resp = client.post("/api/validate", json={
            "name": "my_cluster!",
            "version": "4.20.12",
        })
        data = resp.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_long_name_warning(self):
        resp = client.post("/api/validate", json={
            "name": "very-long-cluster-name",
            "version": "4.20.12",
        })
        data = resp.json()
        assert len(data["warnings"]) > 0

    def test_min_greater_than_max(self):
        resp = client.post("/api/validate", json={
            "name": "test",
            "version": "4.20.12",
            "min_replicas": 5,
            "max_replicas": 2,
        })
        data = resp.json()
        assert data["valid"] is False

    def test_non_420_version_warning(self):
        resp = client.post("/api/validate", json={
            "name": "test",
            "version": "4.19.0",
        })
        data = resp.json()
        assert any("4.20" in w for w in data["warnings"])


# =============================================
# GET /api/capi/cli-versions
# =============================================


class TestCLIVersions:
    @patch("app.subprocess.run")
    def test_all_tools_installed(self, mock_run):
        def side_effect(cmd, **kwargs):
            if "clusterctl" in cmd:
                return MagicMock(returncode=0, stdout="v1.7.0")
            if "minikube" in cmd:
                return MagicMock(returncode=0, stdout="v1.33.0")
            if "kubectl" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps({
                    "clientVersion": {"gitVersion": "v1.30.0"}
                }))
            if "podman" in cmd:
                return MagicMock(returncode=0, stdout="4.9.0")
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = side_effect
        resp = client.get("/api/capi/cli-versions")
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data
        assert data["tools"]["clusterctl"]["installed"] is True
        assert data["tools"]["minikube"]["installed"] is True
        assert data["tools"]["kubectl"]["installed"] is True

    @patch("app.subprocess.run")
    def test_tools_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("not found")
        resp = client.get("/api/capi/cli-versions")
        assert resp.status_code == 200
        data = resp.json()
        for tool_info in data["tools"].values():
            assert tool_info["installed"] is False


# =============================================
# GET /api/jenkins/test-results-trend
# =============================================


class TestJenkinsTestResultsTrend:
    @patch("requests.get")
    def test_success(self, mock_get):
        builds_response = MagicMock()
        builds_response.status_code = 200
        builds_response.json.return_value = {
            "builds": [
                {"number": 100, "result": "SUCCESS", "timestamp": 1700000000000, "duration": 60000},
                {"number": 99, "result": "FAILURE", "timestamp": 1699900000000, "duration": 45000},
            ]
        }
        builds_response.raise_for_status = MagicMock()

        test_report = MagicMock()
        test_report.status_code = 200
        test_report.json.return_value = {
            "passCount": 40, "failCount": 2, "skipCount": 3,
        }

        mock_get.side_effect = [builds_response, test_report, test_report]
        resp = client.get("/api/jenkins/test-results-trend")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["trend"]) == 2
        assert data["trend"][0]["passCount"] == 40

    @patch("requests.get")
    def test_failure(self, mock_get):
        mock_get.side_effect = Exception("Connection refused")
        resp = client.get("/api/jenkins/test-results-trend")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["trend"] == []


# =============================================
# GET /api/github/repo-activity
# =============================================


class TestGitHubRepoActivity:
    @patch("requests.get")
    def test_success(self, mock_get):
        repo_resp = MagicMock()
        repo_resp.status_code = 200
        repo_resp.json.return_value = {
            "stargazers_count": 5,
            "forks_count": 2,
            "updated_at": "2026-04-01T00:00:00Z",
        }

        commits_resp = MagicMock()
        commits_resp.status_code = 200
        commits_resp.json.return_value = [{"sha": "abc"}, {"sha": "def"}]

        prs_resp = MagicMock()
        prs_resp.status_code = 200
        prs_resp.json.return_value = [{"number": 1}]

        merged_resp = MagicMock()
        merged_resp.status_code = 200
        merged_resp.json.return_value = []

        issues_resp = MagicMock()
        issues_resp.status_code = 200
        issues_resp.json.return_value = [{"number": 1}, {"number": 2}]

        # Two repos, 5 calls each
        mock_get.side_effect = [
            repo_resp, commits_resp, prs_resp, merged_resp, issues_resp,
            repo_resp, commits_resp, prs_resp, merged_resp, issues_resp,
        ]
        resp = client.get("/api/github/repo-activity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["repos"]) == 2

    @patch("requests.get")
    def test_failure(self, mock_get):
        mock_get.side_effect = Exception("Network error")
        resp = client.get("/api/github/repo-activity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    @patch("requests.get")
    def test_rate_limited(self, mock_get):
        rate_limited = MagicMock()
        rate_limited.status_code = 403
        rate_limited.json.return_value = {"message": "rate limit exceeded"}
        mock_get.return_value = rate_limited
        resp = client.get("/api/github/repo-activity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        for repo in data["repos"]:
            assert "error" in repo


# =============================================
# GET /api/aws/usage/{resource_key}
# =============================================


class TestSingleResourceUsage:
    @patch("app.subprocess.run")
    def test_nat_gateways(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "NatGateways": [
                    {"State": "available"},
                    {"State": "deleted"},
                ]
            }),
        )
        resp = client.get("/api/aws/usage/nat_gateways")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 1

    @patch("app.subprocess.run")
    def test_vpcs(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"Vpcs": [{}, {}]}),
        )
        resp = client.get("/api/aws/usage/vpcs")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 2

    @patch("app.subprocess.run")
    def test_unknown_resource(self, mock_run):
        resp = client.get("/api/aws/usage/unknown_thing")
        data = resp.json()
        assert data["success"] is False

    @patch("app.subprocess.run")
    def test_cloudformation_stacks(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "StackSummaries": [
                    {"StackStatus": "CREATE_COMPLETE"},
                    {"StackStatus": "DELETE_COMPLETE"},
                ]
            }),
        )
        resp = client.get("/api/aws/usage/cloudformation_stacks")
        data = resp.json()
        assert data["success"] is True
        assert data["count"] == 1  # Excludes DELETE_COMPLETE


# =============================================
# GET /api/aws/usage
# =============================================


class TestAWSUsageEndpoint:
    @patch("app._save_aws_usage_snapshot")
    @patch("app._collect_aws_usage_data")
    def test_success(self, mock_collect, mock_save):
        mock_collect.return_value = {"nat_gateways": 2, "vpcs": 3}
        resp = client.get("/api/aws/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["usage"]["nat_gateways"] == 2
        mock_save.assert_called_once()

    @patch("app._collect_aws_usage_data")
    def test_failure(self, mock_collect):
        mock_collect.side_effect = Exception("AWS error")
        resp = client.get("/api/aws/usage")
        data = resp.json()
        assert data["success"] is False


# =============================================
# GET /api/aws/usage-trend
# =============================================


class TestAWSUsageTrend:
    @patch("app.sqlite3")
    def test_no_data(self, mock_sqlite):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_sqlite.connect.return_value = mock_conn
        resp = client.get("/api/aws/usage-trend?days=7")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["trend"] == []

    @patch("app.sqlite3")
    def test_with_data(self, mock_sqlite):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ("2026-04-01T10:00:00", "nat_gateways", 2),
            ("2026-04-01T10:00:00", "vpcs", 3),
            ("2026-04-02T10:00:00", "nat_gateways", 3),
            ("2026-04-02T10:00:00", "vpcs", 3),
        ]
        mock_sqlite.connect.return_value = mock_conn
        resp = client.get("/api/aws/usage-trend?days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["trend"]) == 2
        assert "nat_gateways" in data["resource_keys"]


# =============================================
# GET /api/onboarding/tour
# =============================================


class TestOnboardingTour:
    def test_get_tour(self):
        resp = client.get("/api/onboarding/tour")
        assert resp.status_code == 200
        data = resp.json()
        assert "steps" in data
        assert len(data["steps"]) > 0

    def test_tour_steps_have_required_fields(self):
        resp = client.get("/api/onboarding/tour")
        data = resp.json()
        for step in data["steps"]:
            assert "title" in step
            assert "content" in step or "description" in step


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
