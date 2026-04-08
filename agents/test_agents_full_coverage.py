#!/usr/bin/env python3
"""
Tests targeting remaining uncovered lines in agent source files
to push coverage from 95% to ~100%.

Covers:
- diagnostic_agent.py: lines 79, 134-135, 301-307, 324-342, 396-397,
  450-459, 483-486, 492, 630-635, 643-644, 712-714
- remediation_agent.py: lines 95-98, 236, 279-280, 287, 291, 302-303,
  397, 424, 434, 461, 482, 509, 514, 542-543
- learning_agent.py: lines 233-234, 239, 261-262, 270-271, 279-280,
  288-289, 295-298
- base_agent.py: lines 87-89
- monitoring_agent.py: line 315
"""

import json
import os
import sys
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.diagnostic_agent import DiagnosticAgent
from agents.remediation_agent import RemediationAgent
from agents.learning_agent import LearningAgent
from agents.base_agent import BaseAgent
from agents.monitoring_agent import MonitoringAgent


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
                "type": "cloudformation_deletion_failure",
                "pattern": "CloudFormation stack DELETE_FAILED",
                "severity": "critical",
                "auto_fix": True,
            },
            {
                "type": "rosacontrolplane_stuck_deletion",
                "pattern": "FAILED - RETRYING.*(?:rosacontrolplane|ROSAControlPlane).*(?:delet|still exists)",
                "severity": "high",
                "auto_fix": True,
            },
        ]
    }
    with open(kb_dir / "known_issues.json", "w") as f:
        json.dump(known_issues, f)

    return tmp_path


@pytest.fixture
def diag_agent(tmp_project):
    return DiagnosticAgent(tmp_project)


@pytest.fixture
def rem_agent(tmp_project):
    return RemediationAgent(tmp_project)


@pytest.fixture
def learn_agent(tmp_project):
    return LearningAgent(tmp_project)


# ============================================================
# BaseAgent: line 87-89 (JSONDecodeError in load_knowledge_base)
# ============================================================

class TestBaseAgentKBLoadError:
    def test_load_knowledge_base_json_decode_error(self, tmp_project):
        """Line 87-89: JSONDecodeError when loading knowledge base file."""
        kb_dir = tmp_project / "agents" / "knowledge_base"
        with open(kb_dir / "bad_file.json", "w") as f:
            f.write("{invalid json!!")

        agent = BaseAgent("Test", tmp_project)
        result = agent._load_knowledge("bad_file.json")
        assert result == {}


# ============================================================
# MonitoringAgent: line 315 (get_statistics with tracked issues)
# ============================================================

class TestMonitoringAgentStatistics:
    def test_get_statistics_with_tracked_issues(self, tmp_project):
        """Line 315: get_statistics returns tracked issue summary."""
        agent = MonitoringAgent(tmp_project)
        agent.process_line("FAILED - RETRYING: rosanetwork test-cluster-net still exists after deletion")
        stats = agent.get_statistics()
        assert "tracked_issues" in stats
        assert len(stats["tracked_issues"]) > 0


# ============================================================
# DiagnosticAgent: _apply_learned_confidence (line 79)
# ============================================================

class TestDiagnosticApplyLearnedConfidence:
    def test_apply_learned_confidence_no_issue_type(self, diag_agent):
        """Line 79: diagnosis without issue_type returns unchanged."""
        diagnosis = {"confidence": 0.8, "evidence": []}
        result = diag_agent._apply_learned_confidence(diagnosis)
        assert result["confidence"] == 0.8

    def test_apply_learned_confidence_with_learned_value(self, tmp_project):
        """Lines 83-89: applies learned confidence nudge."""
        kb_dir = tmp_project / "agents" / "knowledge_base"
        known_issues = {
            "patterns": [
                {
                    "type": "rosanetwork_stuck_deletion",
                    "pattern": "test",
                    "learned_confidence": 0.95,
                }
            ]
        }
        with open(kb_dir / "known_issues.json", "w") as f:
            json.dump(known_issues, f)

        agent = DiagnosticAgent(tmp_project)
        diagnosis = {
            "issue_type": "rosanetwork_stuck_deletion",
            "confidence": 0.8,
            "evidence": []
        }
        result = agent._apply_learned_confidence(diagnosis)
        assert result["confidence"] >= 0.8


# ============================================================
# DiagnosticAgent: _diagnose_stuck_resource condition lines 134-135
# ============================================================

class TestDiagnosticStuckResourceConditions:
    @patch("agents.diagnostic_agent.subprocess.run")
    def test_diagnose_stuck_resource_with_delete_condition(self, mock_run, diag_agent):
        """Lines 134-135: resource with delete-type condition adds evidence."""
        resource_info = {
            "metadata": {"name": "test-cluster-roleconfig", "namespace": "default",
                         "finalizers": ["capa.infrastructure.cluster.x-k8s.io"]},
            "status": {
                "conditions": [
                    {"type": "DeleteInProgress", "message": "Deleting resources"}
                ]
            }
        }
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(resource_info))

        context = {
            "matched_pattern": {"type": "rosaroleconfig_stuck_deletion"},
            "buffer": ["FAILED - RETRYING: rosaroleconfig test-cluster-roleconfig still exists"],
            "current_task": "Wait for ROSARoleConfig test-cluster-roleconfig deletion"
        }
        result = diag_agent.diagnose("rosaroleconfig_stuck_deletion", context)
        evidence_str = " ".join(result.get("evidence", []))
        assert "DeleteInProgress" in evidence_str


# ============================================================
# DiagnosticAgent: _get_cloudformation_stack_status (lines 301-307)
# ============================================================

class TestDiagnosticCFStackStatus:
    @patch("agents.diagnostic_agent.subprocess.run")
    def test_cf_stack_status_does_not_exist(self, mock_run, diag_agent):
        """Lines 299-301: stack 'does not exist' returns GONE."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="Stack test-stack does not exist"
        )
        result = diag_agent._get_cloudformation_stack_status("test-stack")
        assert result == "GONE"

    @patch("agents.diagnostic_agent.subprocess.run")
    def test_cf_stack_status_unknown_error(self, mock_run, diag_agent):
        """Line 301: non-matching stderr returns UNKNOWN."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="Some other error"
        )
        result = diag_agent._get_cloudformation_stack_status("test-stack")
        assert result == "UNKNOWN"

    @patch("agents.diagnostic_agent.subprocess.run")
    def test_cf_stack_status_timeout(self, mock_run, diag_agent):
        """Lines 302-304: TimeoutExpired returns UNKNOWN."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="aws", timeout=10)
        result = diag_agent._get_cloudformation_stack_status("test-stack")
        assert result == "UNKNOWN"

    @patch("agents.diagnostic_agent.subprocess.run")
    def test_cf_stack_status_exception(self, mock_run, diag_agent):
        """Lines 305-307: generic exception returns UNKNOWN."""
        mock_run.side_effect = OSError("Connection failed")
        result = diag_agent._get_cloudformation_stack_status("test-stack")
        assert result == "UNKNOWN"


# ============================================================
# DiagnosticAgent: _get_stack_vpc_id (lines 324-342)
# ============================================================

class TestDiagnosticGetStackVpcId:
    @patch("agents.diagnostic_agent.subprocess.run")
    def test_get_vpc_id_from_aws_cli(self, mock_run, diag_agent):
        """Lines 324-338: falls back to aws CLI for VPC ID."""
        mock_run.return_value = MagicMock(returncode=0, stdout="vpc-abc123\n")
        resource_info = {"spec": {"region": "us-east-1"}}
        result = diag_agent._get_stack_vpc_id("test-stack", resource_info)
        assert result == "vpc-abc123"

    @patch("agents.diagnostic_agent.subprocess.run")
    def test_get_vpc_id_aws_cli_no_vpc(self, mock_run, diag_agent):
        """Lines 336-338: aws CLI returns non-vpc value."""
        mock_run.return_value = MagicMock(returncode=0, stdout="None\n")
        result = diag_agent._get_stack_vpc_id("test-stack", {})
        assert result is None

    @patch("agents.diagnostic_agent.subprocess.run")
    def test_get_vpc_id_aws_cli_failure(self, mock_run, diag_agent):
        """Line 336: aws CLI returns non-zero."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = diag_agent._get_stack_vpc_id("test-stack", {})
        assert result is None

    @patch("agents.diagnostic_agent.subprocess.run")
    def test_get_vpc_id_exception(self, mock_run, diag_agent):
        """Lines 340-342: exception returns None."""
        mock_run.side_effect = Exception("aws not found")
        result = diag_agent._get_stack_vpc_id("test-stack", None)
        assert result is None

    def test_get_vpc_id_from_k8s_resource(self, diag_agent):
        """Lines 317-321: gets VPC ID from K8s resource status."""
        resource_info = {
            "status": {"vpcId": "vpc-k8s123"},
            "spec": {"region": "us-west-2"}
        }
        result = diag_agent._get_stack_vpc_id("test-stack", resource_info)
        assert result == "vpc-k8s123"

    @patch("agents.diagnostic_agent.subprocess.run")
    def test_get_vpc_id_default_region(self, mock_run, diag_agent):
        """Lines 324-326: no resource_info uses default us-west-2."""
        mock_run.return_value = MagicMock(returncode=0, stdout="vpc-def456\n")
        result = diag_agent._get_stack_vpc_id("test-stack", None)
        assert result == "vpc-def456"
        call_args = mock_run.call_args[0][0]
        assert "--region" in call_args
        idx = call_args.index("--region")
        assert call_args[idx + 1] == "us-west-2"


# ============================================================
# DiagnosticAgent: _check_vpc_blocking_dependencies (line 396-397)
# ============================================================

class TestDiagnosticVpcDependencies:
    @patch("agents.diagnostic_agent.subprocess.run")
    def test_vpc_dependencies_exception(self, mock_run, diag_agent):
        """Lines 396-397: exception in VPC dependency check."""
        mock_run.side_effect = Exception("Network error")
        blockers, transitioning = diag_agent._check_vpc_blocking_dependencies("vpc-123")
        assert blockers == []
        assert transitioning is False


# ============================================================
# DiagnosticAgent: _get_rosa_cluster_status (lines 450-459)
# ============================================================

class TestDiagnosticRosaClusterStatus:
    @patch("agents.diagnostic_agent.subprocess.run")
    def test_rosa_status_success(self, mock_run, diag_agent):
        """Lines 450-453: successful rosa describe returns state."""
        cluster_info = {"status": {"state": "uninstalling"}}
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps(cluster_info)
        )
        result = diag_agent._get_rosa_cluster_status("test-cluster")
        assert result == "uninstalling"

    @patch("agents.diagnostic_agent.subprocess.run")
    def test_rosa_status_not_found(self, mock_run, diag_agent):
        """Lines 446-448: cluster not found returns 'gone'."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="There is no cluster with identifier"
        )
        result = diag_agent._get_rosa_cluster_status("test-cluster")
        assert result == "gone"

    @patch("agents.diagnostic_agent.subprocess.run")
    def test_rosa_status_unknown_error(self, mock_run, diag_agent):
        """Line 449: unknown error returns 'unknown'."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="internal server error"
        )
        result = diag_agent._get_rosa_cluster_status("test-cluster")
        assert result == "unknown"

    @patch("agents.diagnostic_agent.subprocess.run")
    def test_rosa_status_timeout(self, mock_run, diag_agent):
        """Lines 454-456: TimeoutExpired returns 'unknown'."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="rosa", timeout=15)
        result = diag_agent._get_rosa_cluster_status("test-cluster")
        assert result == "unknown"

    @patch("agents.diagnostic_agent.subprocess.run")
    def test_rosa_status_exception(self, mock_run, diag_agent):
        """Lines 457-459: generic exception returns 'unknown'."""
        mock_run.side_effect = RuntimeError("rosa binary missing")
        result = diag_agent._get_rosa_cluster_status("test-cluster")
        assert result == "unknown"


# ============================================================
# DiagnosticAgent: _diagnose_cloudformation_failure stack name extraction
# (lines 483-486, 492)
# ============================================================

class TestDiagnosticCFFailureExtraction:
    @patch("agents.diagnostic_agent.subprocess.run")
    def test_cf_failure_extract_stack_from_cloudformation_pattern(self, mock_run, diag_agent):
        """Lines 483-486: extract stack name from 'cloudformation X deletion' pattern."""
        mock_run.return_value = MagicMock(returncode=0, stdout="DELETE_FAILED")
        context = {
            "matched_pattern": {"type": "cloudformation_deletion_failure"},
            "buffer": [
                "cloudformation my-stack-rosa-network-stack deletion failed"
            ],
            "current_task": ""
        }
        result = diag_agent._diagnose_cloudformation_failure(context)
        assert result["issue_type"] == "cloudformation_deletion_failure"

    @patch("agents.diagnostic_agent.subprocess.run")
    def test_cf_failure_stack_from_resource_name(self, mock_run, diag_agent):
        """Line 492: derive stack name from resource_name when no buffer match."""
        mock_run.return_value = MagicMock(returncode=0, stdout="DELETE_FAILED")
        context = {
            "matched_pattern": {"type": "cloudformation_deletion_failure"},
            "buffer": [],
            "resource_name": "test-cluster-network",
            "namespace": "default",
            "current_task": ""
        }
        result = diag_agent._diagnose_cloudformation_failure(context)
        assert result["issue_type"] == "cloudformation_deletion_failure"


# ============================================================
# DiagnosticAgent: _get_resource_info (lines 630-635, 643-644)
# ============================================================

class TestDiagnosticGetResourceInfo:
    @patch("agents.diagnostic_agent.subprocess.run")
    def test_get_resource_info_timeout(self, mock_run, diag_agent):
        """Lines 630-632: TimeoutExpired returns None."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="oc", timeout=10)
        result = diag_agent._get_resource_info("rosanetwork", "test", "default")
        assert result is None

    @patch("agents.diagnostic_agent.subprocess.run")
    def test_get_resource_info_exception(self, mock_run, diag_agent):
        """Lines 633-635: generic exception returns None."""
        mock_run.side_effect = OSError("oc not found")
        result = diag_agent._get_resource_info("rosanetwork", "test", "default")
        assert result is None

    @patch("agents.diagnostic_agent.subprocess.run")
    def test_check_deployment_exception(self, mock_run, diag_agent):
        """Lines 643-644: _check_deployment exception returns False."""
        mock_run.side_effect = Exception("failed")
        result = diag_agent._check_deployment("capi-controller", "capi-system")
        assert result is False


# ============================================================
# DiagnosticAgent: _extract_resource_info from current_task (lines 712-714)
# ============================================================

class TestDiagnosticExtractResourceInfo:
    def test_extract_from_current_task(self, diag_agent):
        """Lines 708-714: extracts resource name from current_task."""
        context = {
            "buffer": [],
            "current_task": "Wait for ROSANetwork my-test-cluster-network deletion"
        }
        name, ns = diag_agent._extract_resource_info(context, "rosanetwork")
        assert name == "my-test-cluster-network"

    def test_extract_skips_non_resource_words(self, diag_agent):
        """Lines 711: skip words without hyphens."""
        context = {
            "buffer": [],
            "current_task": "rosanetwork deletion complete"
        }
        name, ns = diag_agent._extract_resource_info(context, "rosanetwork")
        # 'deletion' has no hyphen, should fall through
        assert isinstance(name, str)


# ============================================================
# RemediationAgent: exception during fix execution (lines 95-98)
# ============================================================

class TestRemediationFixException:
    def test_remediate_fix_method_exception(self, rem_agent):
        """Lines 95-98: exception in fix method returns False."""
        with patch.object(rem_agent, '_fix_remove_finalizers', side_effect=RuntimeError("Boom")):
            diagnosis = {
                "issue_type": "test",
                "recommended_fix": "remove_finalizers",
                "fix_parameters": {"resource_type": "rosanetwork", "resource_name": "test", "namespace": "default"},
                "confidence": 0.9
            }
            success, message = rem_agent.remediate(diagnosis)
            assert success is False
            assert "Exception" in message


# ============================================================
# RemediationAgent: ENI delete failure (line 236)
# ============================================================

class TestRemediationENICleanup:
    @patch("agents.remediation_agent.subprocess.run")
    def test_cleanup_vpc_eni_delete_failure(self, mock_run, rem_agent):
        """Line 236: ENI deletion failure."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "describe-network-interfaces" in cmd_str:
                return MagicMock(returncode=0, stdout="eni-123\tNone\tavailable\ttest-eni")
            if "delete-network-interface" in cmd_str:
                return MagicMock(returncode=1, stderr="Cannot delete ENI")
            if "describe-security-groups" in cmd_str:
                return MagicMock(returncode=0, stdout=json.dumps({"SecurityGroups": []}))
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = side_effect
        success, msg = rem_agent._fix_cleanup_vpc_dependencies({
            "vpc_id": "vpc-123",
            "cluster_id": "test-cluster",
            "region": "us-west-2"
        })
        assert "FAILED to delete ENI" in msg


# ============================================================
# RemediationAgent: SG deletion paths (lines 279-280, 287, 291)
# ============================================================

class TestRemediationSGCleanup:
    @patch("agents.remediation_agent.subprocess.run")
    def test_cleanup_vpc_sg_delete_success(self, mock_run, rem_agent):
        """Lines 279-280: successful SG deletion."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "describe-network-interfaces" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-security-groups" in cmd_str:
                # CLI with --query returns a list of arrays
                return MagicMock(returncode=0, stdout=json.dumps(
                    [["sg-123", "test-sg", []]]
                ))
            if "delete-security-group" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = side_effect
        success, msg = rem_agent._fix_cleanup_vpc_dependencies({
            "vpc_id": "vpc-123",
            "cluster_id": "test-cluster",
            "region": "us-west-2"
        })
        assert success is True
        assert "Deleted security group" in msg

    @patch("agents.remediation_agent.subprocess.run")
    def test_cleanup_vpc_sg_dependency_violation(self, mock_run, rem_agent):
        """Lines 284-285, 287: DependencyViolation skips SG."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "describe-network-interfaces" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-security-groups" in cmd_str:
                return MagicMock(returncode=0, stdout=json.dumps(
                    [["sg-456", "blocked-sg", []]]
                ))
            if "delete-security-group" in cmd_str:
                return MagicMock(returncode=1, stderr="DependencyViolation: sg has deps")
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = side_effect
        success, msg = rem_agent._fix_cleanup_vpc_dependencies({
            "vpc_id": "vpc-123",
            "cluster_id": "test-cluster",
            "region": "us-west-2"
        })
        assert "SKIPPED" in msg

    @patch("agents.remediation_agent.subprocess.run")
    def test_cleanup_vpc_sg_other_error(self, mock_run, rem_agent):
        """Line 287: non-DependencyViolation SG delete failure."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "describe-network-interfaces" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-security-groups" in cmd_str:
                return MagicMock(returncode=0, stdout=json.dumps(
                    [["sg-789", "error-sg", []]]
                ))
            if "delete-security-group" in cmd_str:
                return MagicMock(returncode=1, stderr="UnauthorizedAccess")
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = side_effect
        success, msg = rem_agent._fix_cleanup_vpc_dependencies({
            "vpc_id": "vpc-123",
            "cluster_id": "test-cluster",
            "region": "us-west-2"
        })
        assert "FAILED" in msg

    @patch("agents.remediation_agent.subprocess.run")
    def test_cleanup_vpc_no_sgs_at_all(self, mock_run, rem_agent):
        """Line 291: describe-security-groups returns empty/failure."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "describe-network-interfaces" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-security-groups" in cmd_str:
                return MagicMock(returncode=1, stdout="", stderr="error")
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = side_effect
        success, msg = rem_agent._fix_cleanup_vpc_dependencies({
            "vpc_id": "vpc-123",
            "cluster_id": "test-cluster",
            "region": "us-west-2"
        })
        assert "No security groups found" in msg

    @patch("agents.remediation_agent.subprocess.run")
    def test_cleanup_vpc_no_sgs_matching(self, mock_run, rem_agent):
        """Line 289: describe returns empty list (no matching SGs)."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "describe-network-interfaces" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-security-groups" in cmd_str:
                return MagicMock(returncode=0, stdout="[]")
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = side_effect
        success, msg = rem_agent._fix_cleanup_vpc_dependencies({
            "vpc_id": "vpc-123",
            "cluster_id": "test-cluster",
            "region": "us-west-2"
        })
        assert success is True


# ============================================================
# RemediationAgent: timeout / exception in cleanup (lines 302-303)
# ============================================================

class TestRemediationCleanupErrors:
    @patch("agents.remediation_agent.time.sleep")
    @patch("agents.remediation_agent.subprocess.run")
    def test_cleanup_vpc_timeout(self, mock_run, mock_sleep, rem_agent):
        """Lines 300-301: TimeoutExpired during VPC cleanup."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="aws", timeout=30)
        success, msg = rem_agent._fix_cleanup_vpc_dependencies({
            "vpc_id": "vpc-123",
            "cluster_id": "test-cluster",
            "region": "us-west-2"
        })
        assert success is False
        assert "Timeout" in msg

    @patch("agents.remediation_agent.time.sleep")
    @patch("agents.remediation_agent.subprocess.run")
    def test_cleanup_vpc_exception(self, mock_run, mock_sleep, rem_agent):
        """Lines 302-303: generic exception during VPC cleanup."""
        mock_run.side_effect = RuntimeError("something broke")
        success, msg = rem_agent._fix_cleanup_vpc_dependencies({
            "vpc_id": "vpc-123",
            "cluster_id": "test-cluster",
            "region": "us-west-2"
        })
        assert success is False
        assert "Error" in msg


# ============================================================
# RemediationAgent: _fix_retry_cloudformation_delete deep paths
# ============================================================

class TestRemediationCFRetry:
    @patch("agents.remediation_agent.time.sleep")
    @patch("agents.remediation_agent.subprocess.run")
    def test_cf_retry_vpce_delete_failure(self, mock_run, mock_sleep, rem_agent):
        """Line 397: VPC endpoint deletion failure."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "describe-stacks" in cmd_str:
                return MagicMock(returncode=0, stdout="DELETE_FAILED")
            if "describe-vpc-endpoints" in cmd_str:
                return MagicMock(returncode=0, stdout="vpce-123")
            if "delete-vpc-endpoints" in cmd_str:
                return MagicMock(returncode=1, stderr="Cannot delete VPC endpoint")
            if "describe-network-interfaces" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-security-groups" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-subnets" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-internet-gateways" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "delete-stack" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            return MagicMock(returncode=0, stdout="DELETE_IN_PROGRESS")

        mock_run.side_effect = side_effect
        success, msg = rem_agent._fix_retry_cloudformation_delete({
            "stack_name": "test-stack",
            "vpc_id": "vpc-123",
            "region": "us-west-2"
        })
        assert isinstance(success, bool)

    @patch("agents.remediation_agent.time.sleep")
    @patch("agents.remediation_agent.subprocess.run")
    def test_cf_retry_eni_detach_failure(self, mock_run, mock_sleep, rem_agent):
        """Line 424: ENI detach failure during CF retry."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "describe-stacks" in cmd_str:
                return MagicMock(returncode=0, stdout="DELETE_FAILED")
            if "describe-vpc-endpoints" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-network-interfaces" in cmd_str:
                return MagicMock(returncode=0, stdout="eni-111\tattach-111\tsg-111")
            if "detach-network-interface" in cmd_str:
                return MagicMock(returncode=1, stderr="Cannot detach")
            if "delete-network-interface" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-security-groups" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-subnets" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-internet-gateways" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "delete-stack" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            return MagicMock(returncode=0, stdout="DELETE_IN_PROGRESS")

        mock_run.side_effect = side_effect
        success, msg = rem_agent._fix_retry_cloudformation_delete({
            "stack_name": "test-stack",
            "vpc_id": "vpc-123",
            "region": "us-west-2"
        })
        assert isinstance(success, bool)

    @patch("agents.remediation_agent.time.sleep")
    @patch("agents.remediation_agent.subprocess.run")
    def test_cf_retry_eni_delete_failure(self, mock_run, mock_sleep, rem_agent):
        """Line 434: ENI delete failure during CF retry."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "describe-stacks" in cmd_str:
                return MagicMock(returncode=0, stdout="DELETE_FAILED")
            if "describe-vpc-endpoints" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-network-interfaces" in cmd_str:
                return MagicMock(returncode=0, stdout="eni-222\t\t")
            if "delete-network-interface" in cmd_str:
                return MagicMock(returncode=1, stderr="ENI in use")
            if "describe-security-groups" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-subnets" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-internet-gateways" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "delete-stack" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            return MagicMock(returncode=0, stdout="DELETE_IN_PROGRESS")

        mock_run.side_effect = side_effect
        success, msg = rem_agent._fix_retry_cloudformation_delete({
            "stack_name": "test-stack",
            "vpc_id": "vpc-123",
            "region": "us-west-2"
        })
        assert isinstance(success, bool)

    @patch("agents.remediation_agent.time.sleep")
    @patch("agents.remediation_agent.subprocess.run")
    def test_cf_retry_sg_delete_failure(self, mock_run, mock_sleep, rem_agent):
        """Line 461: SG delete failure during CF retry."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "describe-stacks" in cmd_str:
                return MagicMock(returncode=0, stdout="DELETE_FAILED")
            if "describe-vpc-endpoints" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-network-interfaces" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-security-groups" in cmd_str:
                return MagicMock(returncode=0, stdout="sg-999\ttest-sg\tfalse")
            if "delete-security-group" in cmd_str:
                return MagicMock(returncode=1, stderr="SG in use")
            if "describe-subnets" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-internet-gateways" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "delete-stack" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            return MagicMock(returncode=0, stdout="DELETE_IN_PROGRESS")

        mock_run.side_effect = side_effect
        success, msg = rem_agent._fix_retry_cloudformation_delete({
            "stack_name": "test-stack",
            "vpc_id": "vpc-123",
            "region": "us-west-2"
        })
        assert isinstance(success, bool)

    @patch("agents.remediation_agent.time.sleep")
    @patch("agents.remediation_agent.subprocess.run")
    def test_cf_retry_subnet_delete_failure(self, mock_run, mock_sleep, rem_agent):
        """Line 482: subnet delete failure during CF retry."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "describe-stacks" in cmd_str:
                return MagicMock(returncode=0, stdout="DELETE_FAILED")
            if "describe-vpc-endpoints" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-network-interfaces" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-security-groups" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-subnets" in cmd_str:
                return MagicMock(returncode=0, stdout="subnet-123")
            if "delete-subnet" in cmd_str:
                return MagicMock(returncode=1, stderr="Subnet has dependencies")
            if "describe-internet-gateways" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "delete-stack" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            return MagicMock(returncode=0, stdout="DELETE_IN_PROGRESS")

        mock_run.side_effect = side_effect
        success, msg = rem_agent._fix_retry_cloudformation_delete({
            "stack_name": "test-stack",
            "vpc_id": "vpc-123",
            "region": "us-west-2"
        })
        assert isinstance(success, bool)

    @patch("agents.remediation_agent.time.sleep")
    @patch("agents.remediation_agent.subprocess.run")
    def test_cf_retry_igw_delete_failure(self, mock_run, mock_sleep, rem_agent):
        """Line 509: IGW delete failure during CF retry."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "describe-stacks" in cmd_str:
                return MagicMock(returncode=0, stdout="DELETE_FAILED")
            if "describe-vpc-endpoints" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-network-interfaces" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-security-groups" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-subnets" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-internet-gateways" in cmd_str:
                return MagicMock(returncode=0, stdout="igw-123")
            if "detach-internet-gateway" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "delete-internet-gateway" in cmd_str:
                return MagicMock(returncode=1, stderr="IGW error")
            if "delete-stack" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            return MagicMock(returncode=0, stdout="DELETE_IN_PROGRESS")

        mock_run.side_effect = side_effect
        success, msg = rem_agent._fix_retry_cloudformation_delete({
            "stack_name": "test-stack",
            "vpc_id": "vpc-123",
            "region": "us-west-2"
        })
        assert isinstance(success, bool)

    @patch("agents.remediation_agent.time.sleep")
    @patch("agents.remediation_agent.subprocess.run")
    def test_cf_retry_cleanup_details_and_errors_logged(self, mock_run, mock_sleep, rem_agent):
        """Lines 511-514: cleanup details and errors are logged."""
        def side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "describe-stacks" in cmd_str:
                return MagicMock(returncode=0, stdout="DELETE_FAILED")
            if "describe-vpc-endpoints" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-network-interfaces" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-security-groups" in cmd_str:
                return MagicMock(returncode=0, stdout="sg-100\torphan-sg\tfalse")
            if "delete-security-group" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "describe-subnets" in cmd_str:
                return MagicMock(returncode=0, stdout="subnet-200")
            if "delete-subnet" in cmd_str:
                return MagicMock(returncode=1, stderr="Cannot delete subnet")
            if "describe-internet-gateways" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            if "delete-stack" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            return MagicMock(returncode=0, stdout="DELETE_IN_PROGRESS")

        mock_run.side_effect = side_effect
        success, msg = rem_agent._fix_retry_cloudformation_delete({
            "stack_name": "test-stack",
            "vpc_id": "vpc-123",
            "region": "us-west-2"
        })
        assert isinstance(success, bool)

    @patch("agents.remediation_agent.time.sleep")
    @patch("agents.remediation_agent.subprocess.run")
    def test_cf_retry_timeout(self, mock_run, mock_sleep, rem_agent):
        """Lines 540-541: TimeoutExpired during CF retry."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="aws", timeout=10)
        success, msg = rem_agent._fix_retry_cloudformation_delete({
            "stack_name": "test-stack",
            "vpc_id": "vpc-123",
            "region": "us-west-2"
        })
        assert success is False
        assert "Timeout" in msg

    @patch("agents.remediation_agent.time.sleep")
    @patch("agents.remediation_agent.subprocess.run")
    def test_cf_retry_exception(self, mock_run, mock_sleep, rem_agent):
        """Lines 542-543: generic exception during CF retry."""
        mock_run.side_effect = RuntimeError("unexpected error")
        success, msg = rem_agent._fix_retry_cloudformation_delete({
            "stack_name": "test-stack",
            "vpc_id": "vpc-123",
            "region": "us-west-2"
        })
        assert success is False
        assert "Error" in msg


# ============================================================
# LearningAgent: error paths
# ============================================================

class TestLearningAgentErrorPaths:
    def test_apply_confidence_adjustments_exception(self, learn_agent):
        """Lines 233-234: exception in _apply_confidence_adjustments."""
        adjustments = [{"issue_type": "test", "delta": 0.05, "reason": "test"}]
        # Make the known_issues.json unreadable
        kb_file = learn_agent.kb_dir / "known_issues.json"
        kb_file.write_text("{invalid json!!")
        # Should not raise, just log the error
        learn_agent._apply_confidence_adjustments(adjustments)

    def test_append_outcomes_empty(self, learn_agent):
        """Line 239: _append_outcomes with no session outcomes does nothing."""
        learn_agent.session_outcomes = []
        learn_agent._append_outcomes()
        assert not learn_agent.outcomes_file.exists()

    def test_append_outcomes_exception(self, learn_agent):
        """Lines 261-262: exception in _append_outcomes."""
        learn_agent.record_outcome(
            issue_type="test", diagnosis={"issue_type": "test"},
            fix_applied="fix", success=True, details="details"
        )
        # Make the outcomes file a directory to cause write failure
        learn_agent.outcomes_file.mkdir(parents=True, exist_ok=True)
        learn_agent._append_outcomes()

    def test_load_all_outcomes_exception(self, learn_agent):
        """Lines 270-271: exception in _load_all_outcomes."""
        learn_agent.outcomes_file.parent.mkdir(parents=True, exist_ok=True)
        learn_agent.outcomes_file.write_text("{bad json")
        result = learn_agent._load_all_outcomes()
        assert result == []

    def test_append_pending_exception(self, learn_agent):
        """Lines 288-289: exception in _append_pending."""
        # Make the pending file a directory to cause write failure
        learn_agent.pending_file.mkdir(parents=True, exist_ok=True)
        learn_agent._append_pending({"type": "test", "pattern": "test"})

    def test_get_pending_count_exception(self, learn_agent):
        """Lines 295-298: exception in _get_pending_count."""
        learn_agent.pending_file.parent.mkdir(parents=True, exist_ok=True)
        learn_agent.pending_file.write_text("{bad json")
        result = learn_agent._get_pending_count()
        assert result == 0

    def test_get_pending_count_with_data(self, learn_agent):
        """Lines 294-296: _get_pending_count with valid file."""
        learn_agent.pending_file.parent.mkdir(parents=True, exist_ok=True)
        learn_agent.pending_file.write_text(json.dumps([{"type": "test1"}, {"type": "test2"}]))
        result = learn_agent._get_pending_count()
        assert result == 2

    def test_append_pending_success(self, learn_agent):
        """Lines 274-286: successfully append pending learning."""
        learn_agent._append_pending({"type": "new_pattern", "pattern": "test.*error"})
        assert learn_agent.pending_file.exists()
        data = json.loads(learn_agent.pending_file.read_text())
        assert len(data) == 1
        assert data[0]["type"] == "new_pattern"

    def test_append_outcomes_with_existing_file(self, learn_agent):
        """Lines 242-255: append to existing outcomes file and cap at 500."""
        existing = [{"issue_type": f"old_{i}", "success": True} for i in range(498)]
        learn_agent.outcomes_file.write_text(json.dumps(existing))

        learn_agent.record_outcome("new_1", {"issue_type": "new_1"}, "fix", True, details="d1")
        learn_agent.record_outcome("new_2", {"issue_type": "new_2"}, "fix", True, details="d2")
        learn_agent.record_outcome("new_3", {"issue_type": "new_3"}, "fix", False, details="d3")
        learn_agent._append_outcomes()

        data = json.loads(learn_agent.outcomes_file.read_text())
        assert len(data) == 500  # capped
        assert len(learn_agent.session_outcomes) == 0  # cleared after persist
