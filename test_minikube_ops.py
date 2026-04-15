"""Tests for minikube_ops.py shared module."""

import json
import subprocess
import time
from unittest.mock import patch, MagicMock

import pytest

import minikube_ops


@pytest.fixture(autouse=True)
def clear_cache():
    """Reset the profile cache before each test."""
    minikube_ops._profile_cache["data"] = None
    minikube_ops._profile_cache["timestamp"] = 0.0
    yield


# ============================================================================
# is_minikube_installed
# ============================================================================
class TestIsMinikubeInstalled:
    @patch("minikube_ops.subprocess.run")
    def test_installed(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        assert minikube_ops.is_minikube_installed() is True

    @patch("minikube_ops.subprocess.run")
    def test_not_installed(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        assert minikube_ops.is_minikube_installed() is False

    @patch("minikube_ops.subprocess.run")
    def test_bad_return_code(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        assert minikube_ops.is_minikube_installed() is False

    @patch("minikube_ops.subprocess.run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="minikube", timeout=10)
        assert minikube_ops.is_minikube_installed() is False


# ============================================================================
# invalidate_cache
# ============================================================================
class TestInvalidateCache:
    def test_resets_timestamp(self):
        minikube_ops._profile_cache["timestamp"] = 999.0
        minikube_ops.invalidate_cache()
        assert minikube_ops._profile_cache["timestamp"] == 0.0


# ============================================================================
# list_profiles
# ============================================================================
class TestListProfiles:
    @patch("minikube_ops.is_minikube_installed", return_value=False)
    def test_minikube_not_installed(self, _):
        result = minikube_ops.list_profiles()
        assert result["minikube_installed"] is False
        assert result["clusters"] == []

    @patch("minikube_ops.is_minikube_installed", return_value=True)
    @patch("minikube_ops.subprocess.run")
    def test_no_profiles(self, mock_run, _):
        mock_run.return_value = MagicMock(returncode=1)
        result = minikube_ops.list_profiles()
        assert result["minikube_installed"] is True
        assert result["clusters"] == []
        assert "No Minikube clusters found" in result["message"]

    @patch("minikube_ops.is_minikube_installed", return_value=True)
    @patch("minikube_ops.subprocess.run")
    def test_with_profiles(self, mock_run, _):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"valid": [{"Name": "test-1"}, {"Name": "test-2"}]}),
        )
        result = minikube_ops.list_profiles()
        assert result["clusters"] == ["test-1", "test-2"]
        assert result["minikube_installed"] is True
        assert "2 Minikube cluster(s)" in result["message"]

    @patch("minikube_ops.is_minikube_installed", return_value=True)
    @patch("minikube_ops.subprocess.run")
    def test_cache_hit(self, mock_run, _):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"valid": [{"Name": "cached"}]}),
        )
        result1 = minikube_ops.list_profiles()
        result2 = minikube_ops.list_profiles()
        assert result1 is result2
        assert mock_run.call_count == 1  # only called once due to cache

    @patch("minikube_ops.is_minikube_installed", return_value=True)
    @patch("minikube_ops.subprocess.run")
    def test_cache_bypass(self, mock_run, _):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"valid": [{"Name": "fresh"}]}),
        )
        minikube_ops.list_profiles()
        minikube_ops.list_profiles(use_cache=False)
        assert mock_run.call_count == 2

    @patch("minikube_ops.is_minikube_installed", return_value=True)
    @patch("minikube_ops.subprocess.run")
    def test_json_decode_error(self, mock_run, _):
        mock_run.return_value = MagicMock(returncode=0, stdout="not json")
        result = minikube_ops.list_profiles()
        assert result["clusters"] == []
        assert "Failed to parse" in result["message"]

    @patch("minikube_ops.is_minikube_installed", return_value=True)
    @patch("minikube_ops.subprocess.run")
    def test_exception(self, mock_run, _):
        mock_run.side_effect = Exception("boom")
        result = minikube_ops.list_profiles()
        assert result["minikube_installed"] is False
        assert "boom" in result["message"]


# ============================================================================
# get_profile_status
# ============================================================================
class TestGetProfileStatus:
    @patch("minikube_ops.subprocess.run")
    def test_profile_running(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"Host": "Running", "Kubelet": "Running", "APIServer": "Running", "Driver": "podman"}),
        )
        result = minikube_ops.get_profile_status("test")
        assert result["exists"] is True
        assert result["is_running"] is True
        assert result["driver"] == "podman"

    @patch("minikube_ops.subprocess.run")
    def test_profile_stopped(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"Host": "Stopped"}),
        )
        result = minikube_ops.get_profile_status("test")
        assert result["exists"] is True
        assert result["is_running"] is False

    @patch("minikube_ops.subprocess.run")
    def test_profile_not_found(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        result = minikube_ops.get_profile_status("nonexistent")
        assert result["exists"] is False

    @patch("minikube_ops.subprocess.run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="minikube", timeout=30)
        result = minikube_ops.get_profile_status("test")
        assert result["exists"] is False
        assert "timed out" in result["message"]


# ============================================================================
# create_profile
# ============================================================================
class TestCreateProfile:
    def test_invalid_name(self):
        result = minikube_ops.create_profile("INVALID NAME!")
        assert result["success"] is False
        assert "Invalid" in result["message"]

    @patch("minikube_ops.is_minikube_installed", return_value=False)
    def test_minikube_not_installed(self, _):
        result = minikube_ops.create_profile("test")
        assert result["success"] is False
        assert "not installed" in result["message"]

    @patch("minikube_ops.is_minikube_installed", return_value=True)
    @patch("minikube_ops.get_profile_status")
    def test_already_exists(self, mock_status, _):
        mock_status.return_value = {"exists": True}
        result = minikube_ops.create_profile("test")
        assert result["success"] is False
        assert "already exists" in result["message"]

    @patch("minikube_ops.is_minikube_installed", return_value=True)
    @patch("minikube_ops.get_profile_status", return_value={"exists": False})
    @patch("minikube_ops.subprocess.Popen")
    @patch("minikube_ops.subprocess.run")
    def test_success(self, mock_run, mock_popen, *_):
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = ["Starting...\n", "Done\n", ""]
        mock_process.returncode = 0
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process
        mock_run.return_value = MagicMock(returncode=0)  # kubectl verify
        result = minikube_ops.create_profile("my-cluster")
        assert result["success"] is True
        assert result["verified"] is True

    @patch("minikube_ops.is_minikube_installed", return_value=True)
    @patch("minikube_ops.get_profile_status", return_value={"exists": False})
    @patch("minikube_ops.subprocess.Popen")
    def test_creation_fails(self, mock_popen, *_):
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = ["error\n", ""]
        mock_process.returncode = 1
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process
        result = minikube_ops.create_profile("my-cluster")
        assert result["success"] is False

    @patch("minikube_ops.is_minikube_installed", return_value=True)
    @patch("minikube_ops.get_profile_status", return_value={"exists": False})
    @patch("minikube_ops.subprocess.Popen")
    def test_timeout(self, mock_popen, *_):
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = [""]
        mock_process.returncode = 0
        mock_process.wait.side_effect = subprocess.TimeoutExpired(cmd="minikube", timeout=300)
        mock_popen.return_value = mock_process
        result = minikube_ops.create_profile("my-cluster")
        assert result["success"] is False
        assert "timed out" in result["message"]

    @patch("minikube_ops.is_minikube_installed", return_value=True)
    @patch("minikube_ops.get_profile_status", return_value={"exists": False})
    @patch("minikube_ops.subprocess.Popen")
    @patch("minikube_ops.subprocess.run")
    def test_output_callback(self, mock_run, mock_popen, *_):
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = ["line1\n", "line2\n", ""]
        mock_process.returncode = 0
        mock_process.wait.return_value = None
        mock_popen.return_value = mock_process
        mock_run.return_value = MagicMock(returncode=0)
        lines = []
        minikube_ops.create_profile("test", on_output=lines.append)
        assert lines == ["line1", "line2"]


# ============================================================================
# delete_profile
# ============================================================================
class TestDeleteProfile:
    @patch("minikube_ops.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Deleted")
        result = minikube_ops.delete_profile("test")
        assert result["success"] is True

    @patch("minikube_ops.subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="not found")
        result = minikube_ops.delete_profile("test")
        assert result["success"] is False

    @patch("minikube_ops.subprocess.run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="minikube", timeout=120)
        result = minikube_ops.delete_profile("test")
        assert result["success"] is False
        assert "timed out" in result["message"]


# ============================================================================
# get_current_context / switch_context
# ============================================================================
class TestContext:
    @patch("minikube_ops.subprocess.run")
    def test_get_current_context(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="my-cluster\n")
        result = minikube_ops.get_current_context()
        assert result["success"] is True
        assert result["current_context"] == "my-cluster"

    @patch("minikube_ops.subprocess.run")
    def test_get_current_context_none(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        result = minikube_ops.get_current_context()
        assert result["success"] is False

    @patch("minikube_ops.subprocess.run")
    def test_switch_context_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        result = minikube_ops.switch_context("test")
        assert result["success"] is True

    @patch("minikube_ops.subprocess.run")
    def test_switch_context_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="not found")
        result = minikube_ops.switch_context("bad")
        assert result["success"] is False


# ============================================================================
# get_active_profile
# ============================================================================
class TestGetActiveProfile:
    @patch("minikube_ops.subprocess.run")
    def test_no_profiles(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        result = minikube_ops.get_active_profile()
        assert result["success"] is False

    @patch("minikube_ops._get_api_url", return_value="https://192.168.49.2:8443")
    @patch("minikube_ops.subprocess.run")
    def test_running_profile_found(self, mock_run, _):
        # First call: profile list; second call: status
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({"valid": [{"Name": "mk1"}]})),
            MagicMock(returncode=0, stdout=json.dumps({"Host": "Running"})),
        ]
        result = minikube_ops.get_active_profile()
        assert result["success"] is True
        assert result["profile"]["name"] == "mk1"

    @patch("minikube_ops.subprocess.run")
    def test_no_running_profile(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps({"valid": [{"Name": "mk1"}]})),
            MagicMock(returncode=0, stdout=json.dumps({"Host": "Stopped"})),
        ]
        result = minikube_ops.get_active_profile()
        assert result["success"] is False
        assert "No running" in result["message"]


# ============================================================================
# verify_cluster
# ============================================================================
class TestVerifyCluster:
    def test_empty_name(self):
        result = minikube_ops.verify_cluster("")
        assert result["exists"] is False

    @patch("minikube_ops.is_minikube_installed", return_value=False)
    def test_minikube_not_installed(self, _):
        result = minikube_ops.verify_cluster("test")
        assert result["exists"] is False
        assert "not installed" in result["message"]

    @patch("minikube_ops.is_minikube_installed", return_value=True)
    @patch("minikube_ops.get_profile_status")
    def test_profile_not_found(self, mock_status, _):
        mock_status.return_value = {"exists": False}
        result = minikube_ops.verify_cluster("test")
        assert result["exists"] is False
        assert "does not exist" in result["message"]

    @patch("minikube_ops.is_minikube_installed", return_value=True)
    @patch("minikube_ops.get_profile_status")
    def test_not_running(self, mock_status, _):
        mock_status.return_value = {"exists": True, "is_running": False}
        result = minikube_ops.verify_cluster("test")
        assert result["exists"] is True
        assert result["accessible"] is False

    @patch("minikube_ops._check_components", return_value={"checks_passed": 2, "warnings": 0, "failed": 0, "details": []})
    @patch("minikube_ops._build_cluster_info", return_value={"name": "test"})
    @patch("minikube_ops.subprocess.run")
    @patch("minikube_ops.is_minikube_installed", return_value=True)
    @patch("minikube_ops.get_profile_status")
    def test_fully_accessible(self, mock_status, _, mock_run, *__):
        mock_status.return_value = {"exists": True, "is_running": True}
        mock_run.return_value = MagicMock(returncode=0)  # kubectl cluster-info
        result = minikube_ops.verify_cluster("test")
        assert result["exists"] is True
        assert result["accessible"] is True

    @patch("minikube_ops.subprocess.run")
    @patch("minikube_ops.is_minikube_installed", return_value=True)
    @patch("minikube_ops.get_profile_status")
    def test_kubectl_fails(self, mock_status, _, mock_run):
        mock_status.return_value = {"exists": True, "is_running": True}
        mock_run.return_value = MagicMock(returncode=1, stderr="connection refused")
        result = minikube_ops.verify_cluster("test")
        assert result["exists"] is True
        assert result["accessible"] is False


# ============================================================================
# get_tool_versions
# ============================================================================
class TestGetToolVersions:
    @patch("minikube_ops.subprocess.run")
    def test_all_tools_installed(self, mock_run):
        def side_effect(cmd, **kwargs):
            tool = cmd[0]
            if tool == "clusterctl":
                return MagicMock(returncode=0, stdout="v1.9.0")
            elif tool == "minikube":
                return MagicMock(returncode=0, stdout="v1.34.0")
            elif tool == "kubectl":
                return MagicMock(returncode=0, stdout=json.dumps({"clientVersion": {"gitVersion": "v1.32.0"}}))
            elif tool == "podman":
                return MagicMock(returncode=0, stdout="5.3.1")
            return MagicMock(returncode=1)

        mock_run.side_effect = side_effect
        result = minikube_ops.get_tool_versions()
        tools = result["tools"]
        assert tools["clusterctl"]["installed"] is True
        assert tools["minikube"]["installed"] is True
        assert tools["kubectl"]["installed"] is True
        assert tools["podman"]["installed"] is True

    @patch("minikube_ops.subprocess.run")
    def test_no_tools_installed(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        result = minikube_ops.get_tool_versions()
        for tool in ["clusterctl", "minikube", "kubectl", "podman"]:
            assert result["tools"][tool]["installed"] is False

    @patch("minikube_ops.subprocess.run")
    def test_clusterctl_fallback_version(self, mock_run):
        call_count = [0]
        def side_effect(cmd, **kwargs):
            if cmd[0] != "clusterctl":
                return MagicMock(returncode=1)
            call_count[0] += 1
            if call_count[0] == 1:
                return MagicMock(returncode=1)  # -o short fails
            return MagicMock(returncode=0, stdout='clusterctl version: GitVersion:"v1.8.0"')

        mock_run.side_effect = side_effect
        result = minikube_ops.get_tool_versions()
        assert result["tools"]["clusterctl"]["installed"] is True
        assert result["tools"]["clusterctl"]["version"] == "v1.8.0"


# ============================================================================
# _calculate_age
# ============================================================================
class TestCalculateAge:
    def test_recent(self):
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        age = minikube_ops._calculate_age(ts)
        assert "s" in age

    def test_invalid(self):
        assert minikube_ops._calculate_age("not-a-date") == "unknown"

    def test_empty(self):
        assert minikube_ops._calculate_age("") == "unknown"


# ============================================================================
# _determine_resource_status
# ============================================================================
class TestDetermineResourceStatus:
    def test_rosa_control_plane_ready(self):
        assert minikube_ops._determine_resource_status("ROSAControlPlane", {"ready": True}) == "Ready"

    def test_rosa_control_plane_ready_string(self):
        assert minikube_ops._determine_resource_status("ROSAControlPlane", {"ready": "true"}) == "Ready"

    def test_rosa_control_plane_condition(self):
        status = {"conditions": [{"type": "ROSAControlPlaneReady", "status": "True"}]}
        assert minikube_ops._determine_resource_status("ROSAControlPlane", status) == "Ready"

    def test_rosa_control_plane_provisioning(self):
        assert minikube_ops._determine_resource_status("ROSAControlPlane", {}) == "Provisioning"

    def test_rosa_network_ready(self):
        assert minikube_ops._determine_resource_status("ROSANetwork", {"ready": True}) == "Ready"

    def test_rosa_network_provisioning(self):
        assert minikube_ops._determine_resource_status("ROSANetwork", {}) == "Provisioning"

    def test_cluster_provisioned(self):
        assert minikube_ops._determine_resource_status("Cluster", {"phase": "Provisioned"}) == "Ready"

    def test_cluster_other(self):
        assert minikube_ops._determine_resource_status("Cluster", {"phase": "Pending"}) == "Pending"

    def test_machine_pool(self):
        assert minikube_ops._determine_resource_status("MachinePool", {"phase": "Running"}) == "Running"

    def test_unknown_kind(self):
        assert minikube_ops._determine_resource_status("SomethingElse", {}) == "Active"


# ============================================================================
# get_capi_resources
# ============================================================================
class TestGetCapiResources:
    def test_empty_context(self):
        result = minikube_ops.get_capi_resources("")
        assert result["success"] is False

    @patch("minikube_ops.subprocess.run")
    def test_with_resources(self, mock_run):
        bulk_data = {
            "items": [
                {
                    "kind": "ROSAControlPlane",
                    "metadata": {"name": "my-cluster", "creationTimestamp": "2026-01-01T00:00:00Z"},
                    "spec": {"version": "4.17.0"},
                    "status": {"ready": True},
                },
            ]
        }
        ns_data = {
            "metadata": {"name": "ns-rosa-hcp", "creationTimestamp": "2026-01-01T00:00:00Z"},
            "status": {"phase": "Active"},
        }
        identity_data = {
            "items": [
                {"metadata": {"name": "default", "creationTimestamp": "2026-01-01T00:00:00Z"}},
            ]
        }

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=json.dumps(bulk_data)),
            MagicMock(returncode=0, stdout=json.dumps(ns_data)),
            MagicMock(returncode=0, stdout=json.dumps(identity_data)),
        ]

        result = minikube_ops.get_capi_resources("my-mk")
        assert result["success"] is True
        assert result["count"] == 3
        types = [r["type"] for r in result["resources"]]
        assert "ROSAControlPlane" in types
        assert "Namespace" in types
        assert "AWSClusterControllerIdentity" in types

    @patch("minikube_ops.subprocess.run")
    def test_no_resources(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=1),  # bulk fetch fails
            MagicMock(returncode=1),  # namespace fails
            MagicMock(returncode=1),  # identity fails
        ]
        result = minikube_ops.get_capi_resources("my-mk")
        assert result["success"] is True
        assert result["count"] == 0


# ============================================================================
# configure_capi
# ============================================================================
class TestConfigureCapi:
    def test_playbook_not_found(self, tmp_path):
        result = minikube_ops.configure_capi("test", str(tmp_path))
        assert result["success"] is False
        assert "not found" in result["message"]

    @patch("minikube_ops.switch_context", return_value={"success": False, "message": "fail"})
    def test_context_switch_fails(self, _, tmp_path):
        (tmp_path / "tasks").mkdir()
        (tmp_path / "tasks" / "clusterctl_install_capi.yml").write_text("---")
        result = minikube_ops.configure_capi("test", str(tmp_path))
        assert result["success"] is False

    @patch("minikube_ops._load_credentials", return_value={})
    @patch("minikube_ops.switch_context", return_value={"success": True})
    @patch("minikube_ops.subprocess.Popen")
    def test_success(self, mock_popen, *_, tmp_path=None):
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "tasks"))
            with open(os.path.join(tmpdir, "tasks", "clusterctl_install_capi.yml"), "w") as f:
                f.write("---")

            mock_process = MagicMock()
            mock_process.stdout.readline.side_effect = ["installing...\n", ""]
            mock_process.returncode = 0
            mock_process.wait.return_value = None
            mock_popen.return_value = mock_process

            lines = []
            result = minikube_ops.configure_capi("test", tmpdir, on_output=lines.append)
            assert result["success"] is True
            assert lines == ["installing..."]

    @patch("minikube_ops._load_credentials", return_value={})
    @patch("minikube_ops.switch_context", return_value={"success": True})
    @patch("minikube_ops.subprocess.Popen")
    def test_playbook_fails(self, mock_popen, *_):
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "tasks"))
            with open(os.path.join(tmpdir, "tasks", "clusterctl_install_capi.yml"), "w") as f:
                f.write("---")

            mock_process = MagicMock()
            mock_process.stdout.readline.side_effect = [""]
            mock_process.returncode = 2
            mock_process.wait.return_value = None
            mock_popen.return_value = mock_process

            result = minikube_ops.configure_capi("test", tmpdir)
            assert result["success"] is False
            assert "exit code" in result["message"]


# ============================================================================
# _load_credentials
# ============================================================================
class TestLoadCredentials:
    def test_file_not_found(self, tmp_path):
        result = minikube_ops._load_credentials(str(tmp_path))
        assert result == {}

    def test_loads_credentials(self, tmp_path):
        vars_dir = tmp_path / "vars"
        vars_dir.mkdir()
        (vars_dir / "user_vars.yml").write_text(
            "AWS_ACCESS_KEY_ID: AKID\nAWS_SECRET_ACCESS_KEY: SECRET\n"
        )
        result = minikube_ops._load_credentials(str(tmp_path))
        assert result["AWS_ACCESS_KEY_ID"] == "AKID"
        assert result["AWS_SECRET_ACCESS_KEY"] == "SECRET"
        assert result["AWS_REGION"] == "us-west-2"  # default

    def test_invalid_yaml(self, tmp_path):
        vars_dir = tmp_path / "vars"
        vars_dir.mkdir()
        (vars_dir / "user_vars.yml").write_text(": bad: yaml: {{")
        result = minikube_ops._load_credentials(str(tmp_path))
        assert result == {}


# ============================================================================
# _get_api_url
# ============================================================================
class TestGetApiUrl:
    @patch("minikube_ops.subprocess.run")
    def test_extracts_url(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Kubernetes control plane is running at https://192.168.49.2:8443\n",
        )
        assert minikube_ops._get_api_url("test") == "https://192.168.49.2:8443"

    @patch("minikube_ops.subprocess.run")
    def test_no_match(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="nothing relevant\n")
        assert minikube_ops._get_api_url("test") == ""

    @patch("minikube_ops.subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        assert minikube_ops._get_api_url("test") == ""
