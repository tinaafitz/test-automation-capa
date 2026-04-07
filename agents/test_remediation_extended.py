#!/usr/bin/env python3
"""
Extended tests for RemediationAgent — covers the full CloudFormation retry
flow, VPC cleanup with security groups, and edge cases not in the original tests.
"""

import json
import os
import sys
import subprocess as subprocess_mod
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

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
                "type": "cloudformation_deletion_failure",
                "pattern": "CloudFormation.*DELETE_FAILED",
                "severity": "critical",
                "auto_fix": True,
            },
        ],
    }
    with open(kb_dir / "known_issues.json", "w") as f:
        json.dump(known_issues, f)
    with open(kb_dir / "remediation_outcomes.json", "w") as f:
        json.dump([], f)
    return tmp_path


@pytest.fixture
def remed(tmp_project):
    return RemediationAgent(tmp_project, enabled=True)


# ---------------------------------------------------------------------------
# _fix_retry_cloudformation_delete — full flow
# ---------------------------------------------------------------------------

class TestRetryCloudformationDeleteFullFlow:
    """Test the complete CF retry with VPC cleanup chain."""

    @patch("subprocess.run")
    @patch("time.sleep")
    def test_delete_failed_with_vpc_cleanup(self, mock_sleep, mock_run, remed):
        """Full flow: DELETE_FAILED -> cleanup VPC endpoints, ENIs, SGs -> retry delete."""
        call_count = [0]

        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            call_count[0] += 1

            # 1. Check stack status -> DELETE_FAILED
            if "describe-stacks" in cmd_str and call_count[0] <= 2:
                return MagicMock(returncode=0, stdout="DELETE_FAILED\n", stderr="")

            # 2. List stack resources -> VPC
            if "list-stack-resources" in cmd_str:
                return MagicMock(returncode=0, stdout="vpc-abc123\n", stderr="")

            # 3. Describe VPC endpoints
            if "describe-vpc-endpoints" in cmd_str:
                return MagicMock(returncode=0, stdout="vpce-001 vpce-002\n", stderr="")

            # 4. Delete VPC endpoints
            if "delete-vpc-endpoints" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")

            # 5. Describe ENIs
            if "describe-network-interfaces" in cmd_str:
                return MagicMock(returncode=0, stdout="eni-111\teni-attach-aaa\tin-use\n", stderr="")

            # 6. Detach ENI
            if "detach-network-interface" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")

            # 7. Delete ENI
            if "delete-network-interface" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")

            # 8. Describe security groups
            if "describe-security-groups" in cmd_str:
                return MagicMock(returncode=0, stdout="sg-001\ttest-sg\n", stderr="")

            # 9. Delete security group
            if "delete-security-group" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")

            # 10. Describe subnets
            if "describe-subnets" in cmd_str:
                return MagicMock(returncode=0, stdout="subnet-001\n", stderr="")

            # 11. Delete subnet
            if "delete-subnet" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")

            # 12. Describe internet gateways
            if "describe-internet-gateways" in cmd_str:
                return MagicMock(returncode=0, stdout="igw-001\n", stderr="")

            # 13. Detach IGW
            if "detach-internet-gateway" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")

            # 14. Delete IGW
            if "delete-internet-gateway" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")

            # 15. Delete stack (retry)
            if "delete-stack" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")

            # 16. Recheck status -> DELETE_IN_PROGRESS (success)
            if "describe-stacks" in cmd_str:
                return MagicMock(returncode=0, stdout="DELETE_IN_PROGRESS\n", stderr="")

            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect

        diagnosis = {
            "recommended_fix": "retry_cloudformation_delete",
            "fix_parameters": {"stack_name": "my-stack", "region": "us-west-2"},
            "issue_type": "cloudformation_deletion_failure",
        }
        success, msg = remed.remediate(diagnosis)
        assert success
        assert "Cleaned up" in msg or "my-stack" in msg

    @patch("subprocess.run")
    @patch("time.sleep")
    def test_delete_failed_retry_re_enters_failed(self, mock_sleep, mock_run, remed):
        """Stack re-enters DELETE_FAILED after retry -> should fail."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "describe-stacks" in cmd_str:
                return MagicMock(returncode=0, stdout="DELETE_FAILED\n", stderr="")
            if "list-stack-resources" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")
            if "delete-stack" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        diagnosis = {
            "recommended_fix": "retry_cloudformation_delete",
            "fix_parameters": {"stack_name": "stuck-stack"},
            "issue_type": "cloudformation_deletion_failure",
        }
        success, msg = remed.remediate(diagnosis)
        assert not success
        assert "DELETE_FAILED" in msg

    @patch("subprocess.run")
    def test_delete_in_progress_no_retry_needed(self, mock_run, remed):
        """DELETE_IN_PROGRESS with no VPC -> just cleanup, no retry delete-stack call."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "describe-stacks" in cmd_str:
                return MagicMock(returncode=0, stdout="DELETE_IN_PROGRESS\n", stderr="")
            if "list-stack-resources" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")  # No VPC
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        diagnosis = {
            "recommended_fix": "retry_cloudformation_delete",
            "fix_parameters": {"stack_name": "deleting-stack"},
            "issue_type": "cloudformation_deletion_failure",
        }
        success, msg = remed.remediate(diagnosis)
        assert success

    @patch("subprocess.run")
    def test_cf_timeout(self, mock_run, remed):
        mock_run.side_effect = subprocess_mod.TimeoutExpired(cmd="aws", timeout=10)
        diagnosis = {
            "recommended_fix": "retry_cloudformation_delete",
            "fix_parameters": {"stack_name": "my-stack"},
            "issue_type": "cloudformation_deletion_failure",
        }
        success, msg = remed.remediate(diagnosis)
        assert not success
        assert "Timeout" in msg

    @patch("subprocess.run")
    def test_cf_describe_stacks_fail(self, mock_run, remed):
        """describe-stacks returns non-zero (not 'does not exist')."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="access denied")
        diagnosis = {
            "recommended_fix": "retry_cloudformation_delete",
            "fix_parameters": {"stack_name": "my-stack"},
            "issue_type": "cloudformation_deletion_failure",
        }
        success, msg = remed.remediate(diagnosis)
        assert not success
        assert "Failed to check" in msg

    @patch("subprocess.run")
    def test_cf_delete_stack_fails(self, mock_run, remed):
        """delete-stack returns non-zero."""
        call_idx = [0]

        def side_effect(cmd, **kwargs):
            call_idx[0] += 1
            cmd_str = " ".join(cmd)
            if "describe-stacks" in cmd_str:
                return MagicMock(returncode=0, stdout="DELETE_FAILED\n", stderr="")
            if "list-stack-resources" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")
            if "delete-stack" in cmd_str:
                return MagicMock(returncode=1, stdout="", stderr="InternalError")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        diagnosis = {
            "recommended_fix": "retry_cloudformation_delete",
            "fix_parameters": {"stack_name": "fail-stack"},
            "issue_type": "cloudformation_deletion_failure",
        }
        success, msg = remed.remediate(diagnosis)
        assert not success
        assert "Failed to retry" in msg


# ---------------------------------------------------------------------------
# _fix_cleanup_vpc_dependencies — security group edge cases
# ---------------------------------------------------------------------------

class TestCleanupVpcSgEdgeCases:
    @patch("subprocess.run")
    def test_sg_dependency_violation(self, mock_run, remed):
        """Security group with DependencyViolation -> skipped, not failed."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "describe-network-interfaces" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")
            if "describe-security-groups" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps([["sg-001", "test-sg", []]]),
                    stderr="",
                )
            if "delete-security-group" in cmd_str:
                return MagicMock(returncode=1, stdout="", stderr="DependencyViolation: sg has deps")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        diagnosis = {
            "recommended_fix": "cleanup_vpc_dependencies",
            "fix_parameters": {"vpc_id": "vpc-123", "cluster_id": "cl-1"},
            "issue_type": "vpc_deletion_failure",
        }
        success, msg = remed.remediate(diagnosis)
        assert success
        assert "SKIPPED" in msg

    @patch("subprocess.run")
    def test_cleanup_timeout(self, mock_run, remed):
        mock_run.side_effect = subprocess_mod.TimeoutExpired(cmd="aws", timeout=30)
        diagnosis = {
            "recommended_fix": "cleanup_vpc_dependencies",
            "fix_parameters": {"vpc_id": "vpc-123", "cluster_id": "cl-1"},
            "issue_type": "vpc_deletion_failure",
        }
        success, msg = remed.remediate(diagnosis)
        assert not success
        assert "Timeout" in msg

    @patch("subprocess.run")
    def test_eni_with_lambda_skipped(self, mock_run, remed):
        """ENIs from lambda services should be skipped."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "describe-network-interfaces" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout="eni-111\tNone\tavailable\tAWS Lambda VPC ENI",
                    stderr="",
                )
            if "describe-security-groups" in cmd_str:
                return MagicMock(returncode=0, stdout="[]", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        diagnosis = {
            "recommended_fix": "cleanup_vpc_dependencies",
            "fix_parameters": {"vpc_id": "vpc-123", "cluster_id": "cl-1"},
            "issue_type": "vpc_deletion_failure",
        }
        success, msg = remed.remediate(diagnosis)
        assert success
        assert "Skipping" in msg or "lambda" in msg.lower() or "0 ENI" in msg

    @patch("subprocess.run")
    def test_eni_detach_and_delete(self, mock_run, remed):
        """ENI attached -> detach then delete."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "describe-network-interfaces" in cmd_str:
                return MagicMock(
                    returncode=0,
                    stdout="eni-222\teni-attach-bbb\tin-use\ttest ENI",
                    stderr="",
                )
            if "detach-network-interface" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")
            if "delete-network-interface" in cmd_str:
                return MagicMock(returncode=0, stdout="", stderr="")
            if "describe-security-groups" in cmd_str:
                return MagicMock(returncode=0, stdout="[]", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        diagnosis = {
            "recommended_fix": "cleanup_vpc_dependencies",
            "fix_parameters": {"vpc_id": "vpc-123", "cluster_id": "cl-1"},
            "issue_type": "vpc_deletion_failure",
        }
        success, msg = remed.remediate(diagnosis)
        assert success
        assert "1 ENI" in msg


# ---------------------------------------------------------------------------
# _fix_cloudformation_manual
# ---------------------------------------------------------------------------

class TestCloudformationManual:
    def test_manual_with_message(self, remed):
        diagnosis = {
            "recommended_fix": "manual_cloudformation_cleanup",
            "fix_parameters": {"message": "Stack needs manual inspection"},
            "issue_type": "cloudformation_deletion_failure",
        }
        success, msg = remed.remediate(diagnosis)
        assert success
        assert "manual" in msg.lower()

    def test_manual_default_message(self, remed):
        diagnosis = {
            "recommended_fix": "manual_cloudformation_cleanup",
            "fix_parameters": {},
            "issue_type": "cloudformation_deletion_failure",
        }
        success, msg = remed.remediate(diagnosis)
        assert success


# ---------------------------------------------------------------------------
# _fix_install_capi — both installed
# ---------------------------------------------------------------------------

class TestInstallCapiBothInstalled:
    def test_both_installed(self, remed):
        diagnosis = {
            "recommended_fix": "install_capi_capa",
            "fix_parameters": {"capi_installed": True, "capa_installed": True},
            "issue_type": "capi_not_installed",
        }
        success, msg = remed.remediate(diagnosis)
        assert success
        assert "verified" in msg.lower()


# ---------------------------------------------------------------------------
# Success rate tracking through remediate()
# ---------------------------------------------------------------------------

class TestSuccessRateTracking:
    @patch("subprocess.run")
    def test_success_increments(self, mock_run, remed):
        mock_run.return_value = MagicMock(returncode=0, stdout="patched", stderr="")
        diagnosis = {
            "recommended_fix": "remove_finalizers",
            "fix_parameters": {
                "resource_type": "rosanetwork",
                "resource_name": "net-1",
                "namespace": "ns",
            },
            "issue_type": "rosanetwork_stuck_deletion",
        }
        remed.remediate(diagnosis)
        remed.remediate(diagnosis)
        stats = remed.get_success_rate("remove_finalizers")
        assert stats["successes"] == 2
        assert stats["failures"] == 0

    @patch("subprocess.run")
    def test_failure_increments(self, mock_run, remed):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        diagnosis = {
            "recommended_fix": "remove_finalizers",
            "fix_parameters": {
                "resource_type": "rosanetwork",
                "resource_name": "net-1",
                "namespace": "ns",
            },
            "issue_type": "rosanetwork_stuck_deletion",
        }
        remed.remediate(diagnosis)
        stats = remed.get_success_rate("remove_finalizers")
        assert stats["failures"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
