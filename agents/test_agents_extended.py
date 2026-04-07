#!/usr/bin/env python3
"""
Extended tests for the AI agent framework.

Covers untested methods in:
    - DiagnosticAgent: diagnose() dispatch, all _diagnose_* methods
    - RemediationAgent: remediate() dispatch, all _fix_* methods
    - MonitoringAgent: _detect_issue(), get_statistics(), reset()
    - LearningAgent: record_outcome(), end_of_run_summary(), confidence adjustments
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.diagnostic_agent import DiagnosticAgent
from agents.remediation_agent import RemediationAgent
from agents.monitoring_agent import MonitoringAgent, IssueState, TrackedIssue
from agents.learning_agent import LearningAgent
from agents.base_agent import BaseAgent


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


@pytest.fixture
def monitor(tmp_project):
    return MonitoringAgent(tmp_project, enabled=True, verbose=False)


@pytest.fixture
def learner(tmp_project):
    return LearningAgent(tmp_project, enabled=True, verbose=False)


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
                # Return resource info with stackStatus so K8s path is used
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


# ---------------------------------------------------------------------------
# MonitoringAgent tests
# ---------------------------------------------------------------------------

class TestMonitoringDetectIssue:
    def test_detect_rosanetwork_stuck(self, monitor):
        line = "FAILED - RETRYING: ROSANetwork my-net still exists after deletion"
        issue = monitor._detect_issue(line)
        assert issue is not None
        assert issue["type"] == "rosanetwork_stuck_deletion"

    def test_detect_rosacontrolplane_stuck(self, monitor):
        line = "FAILED - RETRYING: ROSAControlPlane my-cp deletion stuck"
        issue = monitor._detect_issue(line)
        assert issue is not None
        assert issue["type"] == "rosacontrolplane_stuck_deletion"

    def test_detect_rosaroleconfig_stuck(self, monitor):
        line = "FAILED - RETRYING: ROSARoleConfig my-rc still exists"
        issue = monitor._detect_issue(line)
        assert issue is not None
        assert issue["type"] == "rosaroleconfig_stuck_deletion"

    def test_detect_cloudformation_failure(self, monitor):
        line = "CloudFormation stack DELETE_FAILED: my-stack"
        issue = monitor._detect_issue(line)
        assert issue is not None
        assert issue["type"] == "cloudformation_deletion_failure"

    def test_detect_ocm_auth(self, monitor):
        line = "ocm API returned 401 unauthorized"
        issue = monitor._detect_issue(line)
        assert issue is not None
        assert issue["type"] == "ocm_auth_failure"

    def test_detect_rate_limit(self, monitor):
        line = "HTTP 429 rate limit exceeded for API call"
        issue = monitor._detect_issue(line)
        assert issue is not None
        assert issue["type"] == "api_rate_limit"

    def test_no_match(self, monitor):
        line = "Everything is fine"
        issue = monitor._detect_issue(line)
        assert issue is None


class TestMonitoringStatistics:
    def test_empty_stats(self, monitor):
        stats = monitor.get_statistics()
        assert stats["patterns_detected"] == 0
        assert stats["interventions_performed"] == 0
        assert stats["tracked_issues"] == {}

    def test_stats_after_detection(self, monitor):
        monitor.patterns_detected.append({"type": "test"})
        monitor.current_task = "Test task"
        stats = monitor.get_statistics()
        assert stats["patterns_detected"] == 1
        assert stats["current_task"] == "Test task"


class TestMonitoringReset:
    def test_reset_clears_state(self, monitor):
        monitor.line_buffer.append("test")
        monitor.patterns_detected.append({"type": "test"})
        monitor.current_task = "task"
        monitor.waiting_for_resource = "ROSANetwork"
        monitor._tracked_issues["test:key"] = TrackedIssue("test", "key", {})
        monitor._structured_context["resource_name"] = "test"

        monitor.reset()

        assert len(monitor.line_buffer) == 0
        assert len(monitor.patterns_detected) == 0
        assert monitor.current_task is None
        assert monitor.waiting_for_resource is None
        assert len(monitor._tracked_issues) == 0
        assert len(monitor._structured_context) == 0


class TestMonitoringProcessLine:
    def test_disabled(self, tmp_project):
        agent = MonitoringAgent(tmp_project, enabled=False)
        assert agent.process_line("anything") is False

    def test_updates_task_context(self, monitor):
        monitor.process_line("TASK [Wait for ROSANetwork deletion]")
        assert monitor.current_task == "Wait for ROSANetwork deletion"

    def test_updates_waiting_for(self, monitor):
        monitor.process_line("Waiting for ROSANetwork to be deleted")
        assert monitor.waiting_for_resource == "ROSANetwork"

    def test_waiting_for_controlplane(self, monitor):
        monitor.process_line("waiting for ROSAControlPlane deletion")
        assert monitor.waiting_for_resource == "ROSAControlPlane"

    def test_waiting_for_roleconfig(self, monitor):
        monitor.process_line("Waiting for ROSARoleConfig to finish")
        assert monitor.waiting_for_resource == "ROSARoleConfig"

    def test_triggers_callback(self, monitor):
        callback = MagicMock()
        monitor.set_issue_callback(callback)
        line = "CloudFormation stack DELETE_FAILED: my-stack"
        monitor.process_line(line)
        callback.assert_called_once()

    def test_no_callback_without_auto_fix(self, monitor):
        callback = MagicMock()
        monitor.set_issue_callback(callback)
        # capi_not_installed has auto_fix=False
        line = "capi controller not found in cluster"
        monitor.process_line(line)
        callback.assert_not_called()

    def test_buffer_limit(self, monitor):
        for i in range(60):
            monitor.process_line(f"line {i}")
        assert len(monitor.line_buffer) == 50


class TestMonitoringStructuredContext:
    def test_parse_agent_context(self, monitor):
        line = '#AGENT_CONTEXT: resource_name=my-net namespace=my-ns resource_type=rosanetwork'
        monitor._parse_structured_context(line)
        assert monitor._structured_context["resource_name"] == "my-net"
        assert monitor._structured_context["namespace"] == "my-ns"

    def test_context_in_ansible_debug(self, monitor):
        line = '"msg": "#AGENT_CONTEXT: resource_name=test namespace=ns"'
        monitor._parse_structured_context(line)
        assert monitor._structured_context["resource_name"] == "test"


class TestMonitoringIssueStateMachine:
    def test_mark_resolved(self, monitor):
        tracked = TrackedIssue("test", "key", {})
        monitor._tracked_issues["test:key"] = tracked
        monitor.mark_issue_resolved("test", "key")
        assert tracked.state == IssueState.RESOLVED

    def test_mark_failed(self, monitor):
        tracked = TrackedIssue("test", "key", {})
        monitor._tracked_issues["test:key"] = tracked
        monitor.mark_issue_failed("test", "key")
        assert tracked.state == IssueState.FAILED

    def test_build_resource_key_from_context(self, monitor):
        monitor._structured_context = {"resource_name": "my-res", "namespace": "my-ns"}
        key = monitor._build_resource_key()
        assert key == "my-ns/my-res"

    def test_build_resource_key_fallback(self, monitor):
        monitor.waiting_for_resource = "ROSANetwork"
        key = monitor._build_resource_key()
        assert key == "ROSANetwork"


class TestTrackedIssue:
    def test_can_retry_failed(self):
        t = TrackedIssue("test", "key", {})
        t.state = IssueState.FAILED
        t.attempts = 1
        assert t.can_retry() is True

    def test_cannot_retry_max_attempts(self):
        t = TrackedIssue("test", "key", {})
        t.state = IssueState.FAILED
        t.attempts = 3
        assert t.can_retry() is False

    def test_should_intervene_detected(self):
        t = TrackedIssue("test", "key", {})
        assert t.should_intervene() is True

    def test_should_not_intervene_diagnosing(self):
        t = TrackedIssue("test", "key", {})
        t.state = IssueState.DIAGNOSING
        assert t.should_intervene() is False

    def test_should_intervene_resolved_after_cooldown(self):
        t = TrackedIssue("test", "key", {})
        t.state = IssueState.RESOLVED
        t.attempts = 1
        t.last_updated = time.time() - 130  # past 120s cooldown
        assert t.should_intervene() is True

    def test_should_not_intervene_resolved_within_cooldown(self):
        t = TrackedIssue("test", "key", {})
        t.state = IssueState.RESOLVED
        t.attempts = 1
        t.last_updated = time.time()
        assert t.should_intervene() is False


# ---------------------------------------------------------------------------
# LearningAgent tests
# ---------------------------------------------------------------------------

class TestLearningRecordOutcome:
    def test_record_success(self, learner):
        learner.record_outcome(
            issue_type="test_issue",
            diagnosis={"confidence": 0.9, "root_cause": "testing"},
            fix_applied="remove_finalizers",
            success=True,
            resource_key="ns/res",
        )
        assert len(learner.session_outcomes) == 1
        assert learner.session_outcomes[0]["success"] is True

    def test_record_failure(self, learner):
        learner.record_outcome(
            issue_type="test_issue",
            diagnosis={"confidence": 0.5},
            fix_applied="remove_finalizers",
            success=False,
        )
        assert learner.session_outcomes[0]["success"] is False

    def test_disabled(self, tmp_project):
        agent = LearningAgent(tmp_project, enabled=False)
        agent.record_outcome("t", {}, "f", True)
        assert len(agent.session_outcomes) == 0


class TestLearningEndOfRunSummary:
    def test_empty_session(self, learner):
        summary = learner.end_of_run_summary()
        assert summary["adjustments"] == []

    def test_summary_with_outcomes(self, learner):
        for _ in range(4):
            learner.record_outcome("test_issue", {"confidence": 0.9}, "fix_a", True)
        summary = learner.end_of_run_summary()
        assert summary["session_outcomes"] == 4
        assert "test_issue:fix_a" in summary["fix_stats"]

    def test_persists_outcomes(self, learner):
        learner.record_outcome("test_issue", {"confidence": 0.9}, "fix_a", True)
        learner.end_of_run_summary()
        # Session should be cleared after persist
        assert len(learner.session_outcomes) == 0
        # File should exist
        assert learner.outcomes_file.exists()
        with open(learner.outcomes_file) as f:
            data = json.load(f)
        assert len(data) == 1


class TestLearningConfidenceAdjustments:
    def test_boost_on_consecutive_successes(self, learner):
        outcomes = [
            {"issue_type": "t", "success": True, "timestamp": f"2026-01-0{i}"}
            for i in range(1, 6)
        ]
        adjustments = learner._calculate_confidence_adjustments(outcomes)
        assert len(adjustments) == 1
        assert adjustments[0]["action"] == "boost"
        assert adjustments[0]["delta"] == 0.05

    def test_reduce_on_consecutive_failures(self, learner):
        outcomes = [
            {"issue_type": "t", "success": False, "timestamp": f"2026-01-0{i}"}
            for i in range(1, 4)
        ]
        adjustments = learner._calculate_confidence_adjustments(outcomes)
        assert len(adjustments) == 1
        assert adjustments[0]["action"] == "reduce"
        assert adjustments[0]["delta"] == -0.1

    def test_no_change_on_mixed(self, learner):
        outcomes = [
            {"issue_type": "t", "success": True, "timestamp": "2026-01-01"},
            {"issue_type": "t", "success": False, "timestamp": "2026-01-02"},
            {"issue_type": "t", "success": True, "timestamp": "2026-01-03"},
        ]
        adjustments = learner._calculate_confidence_adjustments(outcomes)
        assert len(adjustments) == 0


class TestLearningApplyConfidenceAdjustments:
    def test_applies_adjustment(self, learner):
        adjustments = [{"issue_type": "ocm_auth_failure", "action": "boost", "delta": 0.05, "reason": "test"}]
        learner._apply_confidence_adjustments(adjustments)
        with open(learner.kb_dir / "known_issues.json") as f:
            ki = json.load(f)
        for p in ki["patterns"]:
            if p["type"] == "ocm_auth_failure":
                assert "learned_confidence" in p
                break

    def test_respects_bounds(self, learner):
        # Set existing learned_confidence to 0.3
        ki_file = learner.kb_dir / "known_issues.json"
        with open(ki_file) as f:
            ki = json.load(f)
        for p in ki["patterns"]:
            if p["type"] == "ocm_auth_failure":
                p["learned_confidence"] = 0.3
        with open(ki_file, "w") as f:
            json.dump(ki, f)

        adjustments = [{"issue_type": "ocm_auth_failure", "action": "reduce", "delta": -0.1, "reason": "test"}]
        learner._apply_confidence_adjustments(adjustments)
        with open(ki_file) as f:
            ki = json.load(f)
        for p in ki["patterns"]:
            if p["type"] == "ocm_auth_failure":
                assert p["learned_confidence"] >= 0.3


class TestLearningOutcomesCap:
    def test_caps_at_500(self, learner):
        # Pre-populate with 498 outcomes
        existing = [{"issue_type": "old", "success": True, "timestamp": f"2026-01-{i:04d}"} for i in range(498)]
        with open(learner.outcomes_file, "w") as f:
            json.dump(existing, f)

        for i in range(10):
            learner.record_outcome("new", {}, "fix", True)
        learner._append_outcomes()

        with open(learner.outcomes_file) as f:
            data = json.load(f)
        assert len(data) == 500


class TestLearningSuggestNewPattern:
    def test_creates_pending(self, learner):
        learner.suggest_new_pattern(
            log_line="some error line",
            diagnosis={"issue_type": "new_issue", "severity": "high", "root_cause": "test", "confidence": 0.8, "evidence": [], "recommended_fix": "fix"},
            fix_applied="fix",
            success=True,
        )
        assert learner.pending_file.exists()
        with open(learner.pending_file) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["status"] == "pending_review"
        assert data[0]["suggested_pattern"]["auto_fix"] is False


class TestLearningStats:
    def test_empty_stats(self, learner):
        stats = learner.get_learning_stats()
        assert stats["total_outcomes"] == 0

    def test_stats_with_data(self, learner):
        outcomes = [
            {"issue_type": "a", "recommended_fix": "fix1", "success": True, "timestamp": "t1"},
            {"issue_type": "a", "recommended_fix": "fix1", "success": False, "timestamp": "t2"},
        ]
        with open(learner.outcomes_file, "w") as f:
            json.dump(outcomes, f)
        stats = learner.get_learning_stats()
        assert stats["total_outcomes"] == 2
        assert "fix1" in stats["fix_stats"]
        assert stats["fix_stats"]["fix1"]["success_rate"] == "50%"


# ---------------------------------------------------------------------------
# BaseAgent tests
# ---------------------------------------------------------------------------

class TestBaseAgent:
    def test_match_pattern(self, tmp_project):
        agent = BaseAgent("Test", tmp_project)
        patterns = [{"type": "test", "pattern": "error.*fatal"}]
        assert agent.match_pattern("error is fatal", patterns) is not None
        assert agent.match_pattern("all good", patterns) is None

    def test_should_intervene(self, tmp_project):
        agent = BaseAgent("Test", tmp_project, enabled=True)
        assert agent.should_intervene({"auto_fix": True}) is True
        assert agent.should_intervene({"auto_fix": False}) is False
        assert agent.should_intervene({}) is False

    def test_should_not_intervene_disabled(self, tmp_project):
        agent = BaseAgent("Test", tmp_project, enabled=False)
        assert agent.should_intervene({"auto_fix": True}) is False

    def test_record_intervention(self, tmp_project):
        agent = BaseAgent("Test", tmp_project)
        agent.record_intervention("test_fix", {"key": "val"})
        assert len(agent.interventions) == 1
        assert agent.interventions[0]["type"] == "test_fix"

    def test_update_and_get_context(self, tmp_project):
        agent = BaseAgent("Test", tmp_project)
        agent.update_context("key", "value")
        assert agent.get_context("key") == "value"
        assert agent.get_context("missing", "default") == "default"

    def test_load_knowledge_missing_file(self, tmp_project):
        agent = BaseAgent("Test", tmp_project)
        result = agent._load_knowledge("nonexistent.json")
        assert result == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
