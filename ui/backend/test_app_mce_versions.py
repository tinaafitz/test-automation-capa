"""
Tests for MCE features, ROSA versions, AWS usage collection, and GitHub activity endpoints.
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
# _get_supported_versions_sync
# =============================================


from static_routes import _get_supported_versions_sync  # noqa: E402


def _stub_ocm(versions, err=None):
    """Patch the OCM client so these tests never depend on ambient credentials.

    Patching subprocess.run only exercised the rosa CLI path, and only when the
    machine happened to have no usable OCM credentials.
    """
    client = MagicMock()
    client.list_versions.return_value = (versions, err)
    return patch("agents.ocm_client.get_ocm_client", return_value=client)


class TestSupportedVersions:
    def test_ocm_versions_success(self):
        with _stub_ocm(["4.21.0", "4.20.12", "4.20.11", "4.19.22"]):
            result = _get_supported_versions_sync()
        assert "4.21.0" in result["versions"]
        assert "4.20.12" in result["versions"]
        assert result["latest_version"] == "4.21.0"
        assert result["source"] == "ocm"

    def test_default_is_newest_not_second_newest(self):
        # Regression: default_version used to be versions[1], making the newest
        # release unreachable as a default.
        with _stub_ocm(["4.22.13", "4.22.12", "4.22.11"]):
            result = _get_supported_versions_sync("stable")
        assert result["default_version"] == "4.22.13"

    def test_ocm_error_falls_back(self):
        with _stub_ocm([], err="connection refused"):
            result = _get_supported_versions_sync()
        assert len(result["versions"]) > 0
        assert result["source"] == "fallback"
        assert result["error"] == "connection refused"

    def test_ocm_empty_falls_back(self):
        with _stub_ocm([]):
            result = _get_supported_versions_sync()
        assert len(result["versions"]) > 0
        assert result["source"] == "fallback"

    def test_ocm_exception_falls_back(self):
        with patch("agents.ocm_client.get_ocm_client", side_effect=Exception("boom")):
            result = _get_supported_versions_sync()
        assert len(result["versions"]) > 0
        assert result["source"] == "fallback"

    def test_candidate_offers_pinned_prerelease(self):
        # 5.0.0-rc.0 provisions but is not enumerated by OCM's HCP-filtered
        # version list, so it must be merged in for the UI to offer it.
        with _stub_ocm(["4.22.13", "4.22.12"]):
            result = _get_supported_versions_sync("candidate")
        assert "5.0.0-rc.0" in result["versions"]
        assert "5.0.0-rc.0" in result["pinned_versions"]
        # Sorted newest-first, so the pre-release leads the list...
        assert result["versions"][0] == "5.0.0-rc.0"
        # ...but the default stays on what OCM actually enumerated.
        assert result["default_version"] == "4.22.13"

    def test_stable_does_not_default_to_prerelease(self):
        with _stub_ocm(["5.0.0-rc.1", "4.22.13"]):
            result = _get_supported_versions_sync("stable")
        assert result["default_version"] == "4.22.13"

    def test_stable_has_no_pinned_versions(self):
        with _stub_ocm(["4.22.13"]):
            result = _get_supported_versions_sync("stable")
        assert result["pinned_versions"] == []
        assert "5.0.0-rc.0" not in result["versions"]


# =============================================
# _get_mce_features_sync
# =============================================


class TestMCEFeatures:
    @patch("app.subprocess.run")
    def test_mce_features_success(self, mock_run):
        mce_json = json.dumps({
            "items": [{
                "metadata": {"name": "multiclusterengine"},
                "status": {"phase": "Available", "currentVersion": "2.7.0"},
                "spec": {
                    "overrides": {
                        "components": [
                            {"name": "cluster-api", "enabled": True},
                            {"name": "cluster-api-provider-aws", "enabled": True},
                            {"name": "hypershift", "enabled": True},
                            {"name": "hive", "enabled": False},
                        ]
                    }
                }
            }]
        })
        # First call: oc get mce, subsequent calls: CRD checks
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=mce_json, stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),  # ROSANetwork CRD
            MagicMock(returncode=1, stdout="", stderr="not found"),  # ROSARoleConfig CRD
            MagicMock(returncode=1, stdout="", stderr="not found"),  # ROSARoleConfig alt
        ]
        result = app_module._get_mce_features_sync()
        assert "features" in result
        assert result["count"] == 4
        assert result["mce_info"]["version"] == "2.7.0"
        assert result["mce_info"]["available"] is True
        # Check feature names
        names = [f["name"] for f in result["features"]]
        assert "cluster-api" in names
        assert "hive" in names

    @patch("app.subprocess.run")
    def test_mce_features_command_fails(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not connected")
        with pytest.raises(Exception):
            app_module._get_mce_features_sync()

    @patch("app.subprocess.run")
    def test_mce_features_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="oc", timeout=30)
        with pytest.raises(Exception):
            app_module._get_mce_features_sync()

    @patch("app.subprocess.run")
    def test_mce_features_empty_items(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"items": []}),
            stderr="",
        )
        result = app_module._get_mce_features_sync()
        assert result["features"] == []
        assert result["count"] == 0
        assert result["mce_info"] is None


# =============================================
# _collect_aws_usage_data
# =============================================


class TestCollectAWSUsageData:
    @patch("app.subprocess.run")
    def test_all_resources_success(self, mock_run):
        def side_effect(cmd, **kwargs):
            if "list-instance-profiles" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps({"InstanceProfiles": [{"a": 1}]}))
            if "list-stacks" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps({
                    "StackSummaries": [
                        {"StackStatus": "CREATE_COMPLETE"},
                        {"StackStatus": "DELETE_COMPLETE"},
                    ]
                }))
            if "describe-nat-gateways" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps({
                    "NatGateways": [{"State": "available"}, {"State": "deleted"}]
                }))
            if "list-hosted-zones" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps({"HostedZones": [{}, {}]}))
            if "list-roles" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps({"Roles": [{}, {}, {}]}))
            if "describe-vpcs" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps({"Vpcs": [{}]}))
            if "describe-instances" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps({"Reservations": [{"Instances": [{}, {}]}]}))
            if "describe-volumes" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps({"Volumes": [{}, {}, {}]}))
            if "describe-load-balancers" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps({"LoadBalancerDescriptions": [{}]}))
            if "describe-security-groups" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps({"SecurityGroups": [{}, {}]}))
            if "list-buckets" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps({"Buckets": [{}]}))
            return MagicMock(returncode=0, stdout="{}")

        mock_run.side_effect = side_effect
        result = app_module._collect_aws_usage_data()
        assert result["instance_profiles"] == 1
        assert result["cloudformation_stacks"] == 1  # Excludes DELETE_COMPLETE
        assert result["nat_gateways"] == 1  # Only "available"
        assert result["route53_zones"] == 2
        assert result["iam_roles"] == 3
        assert result["vpcs"] == 1

    @patch("app.subprocess.run")
    def test_all_resources_fail(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = app_module._collect_aws_usage_data()
        assert result["instance_profiles"] == "error"
        assert result["nat_gateways"] == "error"

    @patch("app.subprocess.run")
    def test_timeout_returns_error(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="aws", timeout=30)
        result = app_module._collect_aws_usage_data()
        assert result["instance_profiles"] == "error"


# =============================================
# /api/templates
# =============================================


class TestTemplatesEndpoint:
    def test_get_templates(self):
        resp = client.get("/api/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert "templates" in data

    def test_templates_have_required_fields(self):
        resp = client.get("/api/templates")
        data = resp.json()
        for template in data["templates"]:
            assert "name" in template
            assert "description" in template


# =============================================
# /api/aws/usage-config
# =============================================


class TestAWSUsageConfig:
    def test_get_usage_config(self):
        resp = client.get("/api/aws/usage-config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "billedResources" in data
        assert "freeResources" in data

    def test_billed_resources_have_cost(self):
        resp = client.get("/api/aws/usage-config")
        data = resp.json()
        for resource in data["billedResources"]:
            assert "key" in resource
            assert "label" in resource
            assert "costPerMonth" in resource

    def test_free_resources_have_no_cost(self):
        resp = client.get("/api/aws/usage-config")
        data = resp.json()
        for resource in data["freeResources"]:
            assert "key" in resource
            assert "costPerMonth" not in resource or resource["costPerMonth"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
