#!/usr/bin/env python3
"""
Extended tests for DiagnosticAgent and RemediationAgent.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.diagnostic_agent import DiagnosticAgent
from agents.remediation_agent import RemediationAgent


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory with knowledge base."""
    kb_dir = tmp_path / "agents" / "knowledge_base"
    kb_dir.mkdir(parents=True)

    known_issues = {
        "version": "1.0.0",
        "patterns": [
            {
                "type": "rosanetwork_stuck_deletion",
                "pattern": "FAILED - RETRYING.*(?:rosanetwork|ROSANetwork).*(?:delet|still exists)",
                "severity": "high",
                "auto_fix": True,
            },
            {
                "type": "rosacontrolplane_stuck_deletion",
                "pattern": "FAILED - RETRYING.*(?:rosacontrolplane|ROSAControlPlane).*(?:delet|still exists)",
                "severity": "high",
                "auto_fix": True,
            },
            {
                "type": "rosaroleconfig_stuck_deletion",
                "pattern": "FAILED - RETRYING.*(?:rosaroleconfig|ROSARoleConfig).*(?:delet|still exists)",
                "severity": "high",
                "auto_fix": True,
            },
            {
                "type": "cloudformation_deletion_failure",
                "pattern": "CloudFormation stack DELETE_FAILED:.*",
                "severity": "high",
                "auto_fix": True,
            },
            {
                "type": "ocm_auth_failure",
                "pattern": ".*(ocm|openshift cluster manager).*(401|403|unauthorized).*",
                "severity": "medium",
                "auto_fix": True,
            },
            {
                "type": "capi_not_installed",
                "pattern": ".*(capi|cluster.*api).*(not found|does not exist).*",
                "severity": "high",
                "auto_fix": False,
            },
            {
                "type": "api_rate_limit",
                "pattern": "^(?!.*(?:Pattern matched|Issue detected)).*(?:HTTP.*429|rate.limit.exceed).*",
                "severity": "low",
                "auto_fix": True,
            },
            {
                "type": "repeated_timeouts",
                "pattern": "^(?!.*(?:Pattern matched|Issue detected)).*(?:timed?.out|timeout.*exceeded).*",
                "severity": "medium",
                "auto_fix": False,
            },
        ],
    }
    with open(kb_dir / "known_issues.json", "w") as f:
        json.dump(known_issues, f)

    return tmp_path


@pytest.fixture
def diag(tmp_project):
    return DiagnosticAgent(tmp_project, enabled=True, verbose=False)


@pytest.fixture
def remed(tmp_project):
    return RemediationAgent(tmp_project, enabled=True, verbose=False)


@pytest.fixture
def remed_dry(tmp_project):
    return RemediationAgent(tmp_project, enabled=True, verbose=False, dry_run=True)


# ---------------------------------------------------------------------------
# DiagnosticAgent tests
# ---------------------------------------------------------------------------

class TestDiagnosticDiagnoseDispatch:
    def test_diagnose_disabled(self, tmp_project):
        agent = DiagnosticAgent(tmp_project, enabled=False)
        result = agent.diagnose("rosanetwork_stuck_deletion", {})
        assert result is None

    def test_diagnose_dispatches_to_generic_for_unknown(self, diag):
        result = diag.diagnose("some_unknown_issue", {"buffer": []})
        assert result is not None
        assert result["issue_type"] == "some_unknown_issue"
        assert result["recommended_fix"] == "log_and_continue"
        assert result["confidence"] == 0.3

    def test_diagnose_dispatches_to_ocm_auth(self, diag):
        result = diag.diagnose("ocm_auth_failure", {"buffer": []})
        assert result["issue_type"] == "ocm_auth_failure"
        assert result["recommended_fix"] == "refresh_ocm_token"
        assert result["confidence"] == 0.85

    def test_diagnose_dispatches_to_rate_limit(self, diag):
        result = diag.diagnose("api_rate_limit", {"buffer": []})
        assert result["issue_type"] == "api_rate_limit"
        assert result["recommended_fix"] == "backoff_and_retry"

    def test_diagnose_dispatches_to_timeouts(self, diag):
        result = diag.diagnose("repeated_timeouts", {"buffer": []})
        assert result["issue_type"] == "repeated_timeouts"
        assert result["recommended_fix"] == "increase_timeout_and_monitor"

    @patch("subprocess.run")
    def test_diagnose_dispatches_to_rosaroleconfig(self, mock_run, diag):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
        result = diag.diagnose("rosaroleconfig_stuck_deletion", {"buffer": []})
        assert result["issue_type"] == "rosaroleconfig_stuck_deletion"
        assert result["recommended_fix"] == "remove_finalizers"

    @patch("subprocess.run")
    def test_diagnose_dispatches_to_capi_missing(self, mock_run, diag):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        result = diag.diagnose("capi_not_installed", {"buffer": []})
        assert result["issue_type"] == "capi_not_installed"
        assert result["recommended_fix"] == "install_capi_capa"


class TestDiagnosticStuckRosanetwork:
    @patch("subprocess.run")
    def test_cf_delete_failed(self, mock_run, diag):
        """CF stack DELETE_FAILED -> recommend retry_cloudformation_delete."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if cmd[0] == "oc" and "get" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps({
                        "metadata": {},
                        "status": {"stackStatus": "DELETE_FAILED"},
                        "spec": {"region": "us-west-2"},
                    }),
                    stderr="",
                )
            if "describe-stacks" in cmd_str:
                return MagicMock(returncode=0, stdout="DELETE_FAILED\n", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="")

        mock_run.side_effect = side_effect
        context = {"buffer": ["oc get rosanetwork my-net -n my-ns"]}
        result = diag.diagnose("rosanetwork_stuck_deletion", context)
        assert result["recommended_fix"] == "retry_cloudformation_delete"
        assert result["confidence"] == 0.95

    @patch("subprocess.run")
    def test_cf_gone(self, mock_run, diag):
        """CF stack gone -> recommend remove_finalizers."""
        def side_effect(cmd, **kwargs):
            if "describe-stacks" in cmd:
                return MagicMock(returncode=1, stdout="", stderr="does not exist")
            if cmd[0] == "oc" and "get" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps({
                        "metadata": {"deletionTimestamp": "2026-01-01T00:00:00Z", "finalizers": ["test"]},
                        "status": {},
                        "spec": {},
                    }),
                    stderr="",
                )
            return MagicMock(returncode=1, stdout="", stderr="")

        mock_run.side_effect = side_effect
        context = {"buffer": ["oc get rosanetwork my-net -n my-ns"]}
        result = diag.diagnose("rosanetwork_stuck_deletion", context)
        assert result["recommended_fix"] == "remove_finalizers"

    @patch("subprocess.run")
    def test_cf_unknown_status(self, mock_run, diag):
        """Unknown CF status -> log_and_continue (don't remove finalizers)."""
        def side_effect(cmd, **kwargs):
            if cmd[0] == "oc":
                return MagicMock(returncode=1, stdout="", stderr="not found")
            raise FileNotFoundError("aws not found")

        mock_run.side_effect = side_effect
        context = {"buffer": ["oc get rosanetwork my-net -n my-ns"]}
        result = diag.diagnose("rosanetwork_stuck_deletion", context)
        assert result["recommended_fix"] == "log_and_continue"
        assert result["confidence"] == 0.4

    @patch("subprocess.run")
    def test_cf_delete_in_progress_with_blockers(self, mock_run, diag):
        """CF DELETE_IN_PROGRESS with blocking SGs -> retry_cloudformation_delete."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "describe-stacks" in cmd_str:
                return MagicMock(returncode=0, stdout="DELETE_IN_PROGRESS\n", stderr="")
            if cmd[0] == "oc" and "get" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps({
                        "metadata": {},
                        "status": {"stackStatus": "DELETE_IN_PROGRESS", "vpcId": "vpc-123"},
                        "spec": {"region": "us-west-2"},
                    }),
                    stderr="",
                )
            if "describe-security-groups" in cmd_str:
                return MagicMock(returncode=0, stdout="sg-123\tvpce-private-router\n", stderr="")
            if "describe-vpc-endpoints" in cmd_str:
                return MagicMock(returncode=0, stdout="vpce-abc\tavailable\n", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        context = {"buffer": ["oc get rosanetwork my-net -n my-ns"]}
        result = diag.diagnose("rosanetwork_stuck_deletion", context)
        assert result["recommended_fix"] == "retry_cloudformation_delete"

    @patch("subprocess.run")
    def test_cf_delete_in_progress_no_blockers(self, mock_run, diag):
        """CF DELETE_IN_PROGRESS without blockers -> log_and_continue."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if cmd[0] == "oc" and "get" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps({
                        "metadata": {},
                        "status": {"stackStatus": "DELETE_IN_PROGRESS", "vpcId": "vpc-123"},
                        "spec": {"region": "us-west-2"},
                    }),
                    stderr="",
                )
            if "describe-security-groups" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")
            if "describe-vpc-endpoints" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        context = {"buffer": ["oc get rosanetwork my-net -n my-ns"]}
        result = diag.diagnose("rosanetwork_stuck_deletion", context)
        assert result["recommended_fix"] == "log_and_continue"
        assert result["confidence"] == 0.5


class TestDiagnosticStuckRosacontrolplane:
    @patch("subprocess.run")
    def test_always_log_and_continue(self, mock_run, diag):
        """ROSAControlPlane should never remove finalizers."""
        mock_run.return_value = MagicMock(returncode=1, stderr="not found")
        context = {"buffer": ["oc get rosacontrolplane my-cp -n my-ns"]}
        result = diag.diagnose("rosacontrolplane_stuck_deletion", context)
        assert result["recommended_fix"] == "log_and_continue"
        assert result["confidence"] == 0.4


class TestDiagnosticCloudformationFailure:
    @patch("subprocess.run")
    def test_stack_name_from_buffer(self, mock_run, diag):
        """Extract stack name from buffer and confirm DELETE_FAILED."""
        def side_effect(cmd, **kwargs):
            if "describe-stacks" in cmd:
                return MagicMock(returncode=0, stdout="DELETE_FAILED\n", stderr="")
            return MagicMock(returncode=1, stdout="", stderr="")

        mock_run.side_effect = side_effect
        context = {
            "buffer": ["CloudFormation stack DELETE_FAILED: my-stack-name"],
        }
        result = diag.diagnose("cloudformation_deletion_failure", context)
        assert result["recommended_fix"] == "retry_cloudformation_delete"
        assert result["fix_parameters"]["stack_name"] == "my-stack-name"

    @patch("subprocess.run")
    def test_stack_already_gone(self, mock_run, diag):
        """Stack already deleted -> log_and_continue."""
        def side_effect(cmd, **kwargs):
            if "describe-stacks" in cmd:
                return MagicMock(returncode=1, stdout="", stderr="does not exist")
            return MagicMock(returncode=1, stdout="", stderr="")

        mock_run.side_effect = side_effect
        context = {
            "buffer": ["CloudFormation stack DELETE_FAILED: my-stack"],
        }
        result = diag.diagnose("cloudformation_deletion_failure", context)
        assert result["recommended_fix"] == "log_and_continue"

    def test_no_stack_name_fallback(self, diag):
        """No stack name extractable -> manual cleanup."""
        result = diag.diagnose("cloudformation_deletion_failure", {"buffer": []})
        assert result["recommended_fix"] == "manual_cloudformation_cleanup"


class TestDiagnosticGetCloudformationStatus:
    def test_from_k8s_resource(self, diag):
        resource_info = {"status": {"stackStatus": "DELETE_IN_PROGRESS"}, "spec": {}}
        status = diag._get_cloudformation_stack_status("my-stack", resource_info)
        assert status == "DELETE_IN_PROGRESS"

    @patch("subprocess.run")
    def test_from_aws_cli(self, mock_run, diag):
        mock_run.return_value = MagicMock(returncode=0, stdout="CREATE_COMPLETE\n", stderr="")
        status = diag._get_cloudformation_stack_status("my-stack", None)
        assert status == "CREATE_COMPLETE"

    @patch("subprocess.run")
    def test_stack_does_not_exist(self, mock_run, diag):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="does not exist")
        status = diag._get_cloudformation_stack_status("my-stack", None)
        assert status == "GONE"

    def test_no_stack_name(self, diag):
        assert diag._get_cloudformation_stack_status(None) == "UNKNOWN"

    @patch("subprocess.run")
    def test_timeout(self, mock_run, diag):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="aws", timeout=10)
        status = diag._get_cloudformation_stack_status("my-stack", None)
        assert status == "UNKNOWN"


class TestDiagnosticCheckVpcBlockingDependencies:
    @patch("subprocess.run")
    def test_blockers_found(self, mock_run, diag):
        def side_effect(cmd, **kwargs):
            if "describe-security-groups" in cmd:
                return MagicMock(returncode=0, stdout="sg-123\tvpce-router\n", stderr="")
            if "describe-vpc-endpoints" in cmd:
                return MagicMock(returncode=0, stdout="vpce-456\tavailable\n", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        blockers, transitioning = diag._check_vpc_blocking_dependencies("vpc-123")
        assert len(blockers) == 2
        assert not transitioning

    @patch("subprocess.run")
    def test_transitioning_endpoints(self, mock_run, diag):
        def side_effect(cmd, **kwargs):
            if "describe-security-groups" in cmd:
                return MagicMock(returncode=0, stdout="", stderr="")
            if "describe-vpc-endpoints" in cmd:
                return MagicMock(returncode=0, stdout="vpce-789\tdeleting\n", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        blockers, transitioning = diag._check_vpc_blocking_dependencies("vpc-123")
        assert transitioning is True

    @patch("subprocess.run")
    def test_no_blockers(self, mock_run, diag):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        blockers, transitioning = diag._check_vpc_blocking_dependencies("vpc-123")
        assert blockers == []
        assert not transitioning


class TestDiagnosticGetDiagnosisSummary:
    def test_no_diagnosis(self, diag):
        assert diag.get_diagnosis_summary() is None

    def test_with_diagnosis(self, diag):
        diag.current_diagnosis = {
            "issue_type": "test",
            "root_cause": "testing",
            "severity": "low",
            "confidence": 0.9,
            "evidence": ["ev1"],
            "recommended_fix": "log_and_continue",
        }
        summary = diag.get_diagnosis_summary()
        assert "test" in summary
        assert "90%" in summary


class TestDiagnosticApplyLearnedConfidence:
    def test_boost_confidence(self, tmp_project):
        """Learned confidence higher than diagnostic -> nudge up."""
        kb_dir = tmp_project / "agents" / "knowledge_base"
        with open(kb_dir / "known_issues.json", "r") as f:
            ki = json.load(f)
        for p in ki["patterns"]:
            if p["type"] == "ocm_auth_failure":
                p["learned_confidence"] = 1.0
        with open(kb_dir / "known_issues.json", "w") as f:
            json.dump(ki, f)

        agent = DiagnosticAgent(tmp_project, enabled=True)
        diagnosis = {
            "issue_type": "ocm_auth_failure",
            "confidence": 0.85,
            "evidence": [],
        }
        result = agent._apply_learned_confidence(diagnosis)
        assert result["confidence"] == 0.95  # 0.85 + 0.1 cap

    def test_no_learned_confidence(self, diag):
        diagnosis = {"issue_type": "ocm_auth_failure", "confidence": 0.85}
        result = diag._apply_learned_confidence(diagnosis)
        assert result["confidence"] == 0.85


# ---------------------------------------------------------------------------
# RemediationAgent tests
# ---------------------------------------------------------------------------

class TestRemediationDispatch:
    def test_disabled(self, tmp_project):
        agent = RemediationAgent(tmp_project, enabled=False)
        success, msg = agent.remediate({"recommended_fix": "remove_finalizers"})
        assert not success
        assert "disabled" in msg

    def test_dry_run(self, remed_dry):
        diagnosis = {
            "recommended_fix": "remove_finalizers",
            "fix_parameters": {"resource_type": "rosanetwork", "resource_name": "x", "namespace": "y"},
            "issue_type": "test",
        }
        success, msg = remed_dry.remediate(diagnosis)
        assert success
        assert "DRY RUN" in msg

    def test_unknown_fix(self, remed):
        diagnosis = {
            "recommended_fix": "nonexistent_method",
            "fix_parameters": {},
            "issue_type": "test",
        }
        success, msg = remed.remediate(diagnosis)
        assert not success
        assert "No fix method" in msg

    def test_log_and_continue(self, remed):
        diagnosis = {
            "recommended_fix": "log_and_continue",
            "fix_parameters": {},
            "issue_type": "test",
        }
        success, msg = remed.remediate(diagnosis)
        assert success

    def test_increase_timeout(self, remed):
        diagnosis = {
            "recommended_fix": "increase_timeout_and_monitor",
            "fix_parameters": {"suggested_timeout_increase": "3x"},
            "issue_type": "test",
        }
        success, msg = remed.remediate(diagnosis)
        assert success
        assert "3x" in msg


class TestRemediationRemoveFinalizers:
    @patch("subprocess.run")
    def test_success(self, mock_run, remed):
        mock_run.return_value = MagicMock(returncode=0, stdout="patched", stderr="")
        diagnosis = {
            "recommended_fix": "remove_finalizers",
            "fix_parameters": {
                "resource_type": "rosanetwork",
                "resource_name": "my-net",
                "namespace": "my-ns",
            },
            "issue_type": "rosanetwork_stuck_deletion",
        }
        success, msg = remed.remediate(diagnosis)
        assert success
        assert "Successfully" in msg

    @patch("subprocess.run")
    def test_already_deleted(self, mock_run, remed):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="NotFound")
        diagnosis = {
            "recommended_fix": "remove_finalizers",
            "fix_parameters": {
                "resource_type": "rosanetwork",
                "resource_name": "my-net",
                "namespace": "my-ns",
            },
            "issue_type": "rosanetwork_stuck_deletion",
        }
        success, msg = remed.remediate(diagnosis)
        assert success
        assert "already deleted" in msg

    @patch("subprocess.run")
    def test_failure(self, mock_run, remed):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="internal error")
        diagnosis = {
            "recommended_fix": "remove_finalizers",
            "fix_parameters": {
                "resource_type": "rosanetwork",
                "resource_name": "my-net",
                "namespace": "my-ns",
            },
            "issue_type": "rosanetwork_stuck_deletion",
        }
        success, msg = remed.remediate(diagnosis)
        assert not success

    @patch("subprocess.run")
    def test_timeout(self, mock_run, remed):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="oc", timeout=30)
        diagnosis = {
            "recommended_fix": "remove_finalizers",
            "fix_parameters": {
                "resource_type": "rosanetwork",
                "resource_name": "my-net",
                "namespace": "my-ns",
            },
            "issue_type": "rosanetwork_stuck_deletion",
        }
        success, msg = remed.remediate(diagnosis)
        assert not success
        assert "Timeout" in msg


class TestRemediationRefreshOcmToken:
    def test_returns_false(self, remed):
        diagnosis = {
            "recommended_fix": "refresh_ocm_token",
            "fix_parameters": {},
            "issue_type": "ocm_auth_failure",
        }
        success, msg = remed.remediate(diagnosis)
        assert not success
        assert "manual" in msg.lower()


class TestRemediationBackoffRetry:
    def test_advisory(self, remed):
        diagnosis = {
            "recommended_fix": "backoff_and_retry",
            "fix_parameters": {"backoff_seconds": 30, "max_retries": 2},
            "issue_type": "api_rate_limit",
        }
        success, msg = remed.remediate(diagnosis)
        assert success
        assert "30" in msg


class TestRemediationCleanupVpc:
    def test_missing_vpc_id(self, remed):
        diagnosis = {
            "recommended_fix": "cleanup_vpc_dependencies",
            "fix_parameters": {},
            "issue_type": "vpc_deletion_failure",
        }
        success, msg = remed.remediate(diagnosis)
        assert not success
        assert "VPC ID" in msg

    def test_missing_cluster_id(self, remed):
        diagnosis = {
            "recommended_fix": "cleanup_vpc_dependencies",
            "fix_parameters": {"vpc_id": "vpc-123"},
            "issue_type": "vpc_deletion_failure",
        }
        success, msg = remed.remediate(diagnosis)
        assert not success
        assert "Cluster ID" in msg

    @patch("subprocess.run")
    def test_cleanup_with_enis(self, mock_run, remed):
        call_count = [0]

        def side_effect(cmd, **kwargs):
            call_count[0] += 1
            cmd_str = " ".join(cmd)
            if "describe-network-interfaces" in cmd_str:
                return MagicMock(returncode=0, stdout="eni-123\tNone\tavailable\ttest desc", stderr="")
            if "delete-network-interface" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")
            if "describe-security-groups" in cmd_str:
                return MagicMock(returncode=0, stdout="[]", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        diagnosis = {
            "recommended_fix": "cleanup_vpc_dependencies",
            "fix_parameters": {"vpc_id": "vpc-123", "cluster_id": "my-cluster"},
            "issue_type": "vpc_deletion_failure",
        }
        success, msg = remed.remediate(diagnosis)
        assert success


class TestRemediationRetryCloudformationDelete:
    def test_missing_stack_name(self, remed):
        diagnosis = {
            "recommended_fix": "retry_cloudformation_delete",
            "fix_parameters": {},
            "issue_type": "cloudformation_deletion_failure",
        }
        success, msg = remed.remediate(diagnosis)
        assert not success
        assert "Stack name" in msg

    @patch("subprocess.run")
    def test_stack_already_deleted(self, mock_run, remed):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="does not exist")
        diagnosis = {
            "recommended_fix": "retry_cloudformation_delete",
            "fix_parameters": {"stack_name": "my-stack"},
            "issue_type": "cloudformation_deletion_failure",
        }
        success, msg = remed.remediate(diagnosis)
        assert success
        assert "already deleted" in msg

    @patch("subprocess.run")
    def test_unexpected_state(self, mock_run, remed):
        mock_run.return_value = MagicMock(returncode=0, stdout="CREATE_COMPLETE\n", stderr="")
        diagnosis = {
            "recommended_fix": "retry_cloudformation_delete",
            "fix_parameters": {"stack_name": "my-stack"},
            "issue_type": "cloudformation_deletion_failure",
        }
        success, msg = remed.remediate(diagnosis)
        assert not success
        assert "unexpected state" in msg


class TestRemediationInstallCapi:
    def test_neither_installed(self, remed):
        diagnosis = {
            "recommended_fix": "install_capi_capa",
            "fix_parameters": {"capi_installed": False, "capa_installed": False},
            "issue_type": "capi_not_installed",
        }
        success, msg = remed.remediate(diagnosis)
        assert not success
        assert "not installed" in msg.lower()

    def test_capi_only_missing(self, remed):
        diagnosis = {
            "recommended_fix": "install_capi_capa",
            "fix_parameters": {"capi_installed": False, "capa_installed": True},
            "issue_type": "capi_not_installed",
        }
        success, msg = remed.remediate(diagnosis)
        assert not success
        assert "CAPI" in msg

    def test_capa_only_missing(self, remed):
        diagnosis = {
            "recommended_fix": "install_capi_capa",
            "fix_parameters": {"capi_installed": True, "capa_installed": False},
            "issue_type": "capi_not_installed",
        }
        success, msg = remed.remediate(diagnosis)
        assert not success
        assert "CAPA" in msg


class TestRemediationGetSuccessRate:
    def test_no_data(self, remed):
        stats = remed.get_success_rate("remove_finalizers")
        assert stats["total_attempts"] == 0

    def test_with_data(self, remed):
        remed.fix_success_rate["remove_finalizers"] = {"successes": 3, "failures": 1}
        stats = remed.get_success_rate("remove_finalizers")
        assert stats["total_attempts"] == 4
        assert "75.0%" in stats["success_rate"]

    def test_all_fix_types(self, remed):
        remed.fix_success_rate["a"] = {"successes": 1, "failures": 0}
        remed.fix_success_rate["b"] = {"successes": 0, "failures": 2}
        stats = remed.get_success_rate()
        assert "a" in stats
        assert "b" in stats


class TestRemediationExceptionHandling:
    @patch("subprocess.run")
    def test_exception_during_fix(self, mock_run, remed):
        mock_run.side_effect = RuntimeError("boom")
        diagnosis = {
            "recommended_fix": "remove_finalizers",
            "fix_parameters": {
                "resource_type": "rosanetwork",
                "resource_name": "x",
                "namespace": "y",
            },
            "issue_type": "test",
        }
        success, msg = remed.remediate(diagnosis)
        assert not success
        assert "Error" in msg or "Exception" in msg
