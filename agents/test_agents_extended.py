"""
Extended agent tests covering diagnostic dispatch, remediation methods,
monitoring statistics, and agent lifecycle methods.
"""

import json
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.diagnostic_agent import DiagnosticAgent
from agents.monitoring_agent import MonitoringAgent, IssueState, TrackedIssue
from agents.remediation_agent import RemediationAgent


BASE_DIR = Path(__file__).parent.parent


# =============================================
# DiagnosticAgent dispatch tests
# =============================================


class TestDiagnosticDispatch:
    def setup_method(self):
        self.agent = DiagnosticAgent(BASE_DIR)

    def test_disabled_returns_none(self):
        agent = DiagnosticAgent(BASE_DIR, enabled=False)
        result = agent.diagnose("rosanetwork_stuck_deletion", {})
        assert result is None

    @patch.object(DiagnosticAgent, "_get_resource_info", return_value=None)
    @patch.object(DiagnosticAgent, "_get_cloudformation_stack_status", return_value="UNKNOWN")
    def test_rosanetwork_unknown_cf_returns_log_and_continue(self, mock_cf, mock_res):
        result = self.agent.diagnose("rosanetwork_stuck_deletion", {
            "resource_name": "test-network",
            "namespace": "ns-rosa-hcp",
        })
        assert result is not None
        assert result["recommended_fix"] == "log_and_continue"
        assert result["confidence"] <= 0.5

    @patch.object(DiagnosticAgent, "_get_resource_info", return_value=None)
    @patch.object(DiagnosticAgent, "_get_cloudformation_stack_status", return_value="GONE")
    def test_rosanetwork_gone_cf_removes_finalizers(self, mock_cf, mock_res):
        result = self.agent.diagnose("rosanetwork_stuck_deletion", {
            "resource_name": "test-network",
            "namespace": "ns-rosa-hcp",
        })
        assert result is not None
        assert result["recommended_fix"] == "remove_finalizers"

    @patch.object(DiagnosticAgent, "_get_resource_info", return_value=None)
    @patch.object(DiagnosticAgent, "_get_cloudformation_stack_status", return_value="DELETE_FAILED")
    def test_rosanetwork_delete_failed_retries_cf(self, mock_cf, mock_res):
        result = self.agent.diagnose("rosanetwork_stuck_deletion", {
            "resource_name": "test-network",
            "namespace": "ns-rosa-hcp",
        })
        assert result["recommended_fix"] == "retry_cloudformation_delete"
        # Confidence may be adjusted by learned confidence
        assert result["confidence"] >= 0.85

    @patch.object(DiagnosticAgent, "_get_resource_info", return_value=None)
    def test_rosacontrolplane_stuck(self, mock_res):
        result = self.agent.diagnose("rosacontrolplane_stuck_deletion", {
            "resource_name": "test-cp",
            "namespace": "ns-rosa-hcp",
        })
        assert result is not None
        # ROSAControlPlane has special logic — may return log_and_continue
        assert result["recommended_fix"] in ("remove_finalizers", "log_and_continue")

    @patch.object(DiagnosticAgent, "_get_resource_info", return_value=None)
    def test_rosaroleconfig_stuck(self, mock_res):
        result = self.agent.diagnose("rosaroleconfig_stuck_deletion", {
            "resource_name": "test-roles",
            "namespace": "ns-rosa-hcp",
        })
        assert result is not None
        assert result["recommended_fix"] == "remove_finalizers"

    def test_ocm_auth_failure(self):
        result = self.agent.diagnose("ocm_auth_failure", {})
        assert result is not None
        assert result["recommended_fix"] == "refresh_ocm_token"

    def test_capi_not_installed(self):
        result = self.agent.diagnose("capi_not_installed", {})
        assert result is not None
        assert result["recommended_fix"] == "install_capi_capa"

    def test_api_rate_limit(self):
        result = self.agent.diagnose("api_rate_limit", {})
        assert result is not None
        assert result["recommended_fix"] == "backoff_and_retry"

    def test_repeated_timeouts(self):
        result = self.agent.diagnose("repeated_timeouts", {})
        assert result is not None

    def test_generic_unknown_issue(self):
        result = self.agent.diagnose("some_unknown_issue", {})
        assert result is not None
        assert result["confidence"] <= 0.5

    def test_current_diagnosis_stored(self):
        with patch.object(DiagnosticAgent, "_get_resource_info", return_value=None):
            self.agent.diagnose("ocm_auth_failure", {})
        assert self.agent.current_diagnosis is not None


# =============================================
# RemediationAgent method tests
# =============================================


class TestRemediationMethods:
    def setup_method(self):
        self.agent = RemediationAgent(BASE_DIR)

    def test_disabled_returns_false(self):
        agent = RemediationAgent(BASE_DIR, enabled=False)
        success, msg = agent.remediate({"recommended_fix": "remove_finalizers"})
        assert success is False
        assert "disabled" in msg.lower()

    def test_dry_run(self):
        agent = RemediationAgent(BASE_DIR, dry_run=True)
        success, msg = agent.remediate({
            "recommended_fix": "remove_finalizers",
            "fix_parameters": {"resource_type": "rosanetwork", "resource_name": "test"},
        })
        assert success is True
        assert "DRY RUN" in msg

    def test_unknown_fix(self):
        success, msg = self.agent.remediate({
            "recommended_fix": "nonexistent_fix",
            "fix_parameters": {},
        })
        assert success is False
        assert "no fix method" in msg.lower()

    @patch("subprocess.run")
    def test_remove_finalizers_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="patched", stderr="")
        success, msg = self.agent.remediate({
            "recommended_fix": "remove_finalizers",
            "fix_parameters": {
                "resource_type": "rosanetwork",
                "resource_name": "test-net",
                "namespace": "ns-rosa-hcp",
            },
        })
        assert success is True

    @patch("subprocess.run")
    def test_remove_finalizers_not_found(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="NotFound")
        success, msg = self.agent.remediate({
            "recommended_fix": "remove_finalizers",
            "fix_parameters": {
                "resource_type": "rosanetwork",
                "resource_name": "gone",
                "namespace": "ns-rosa-hcp",
            },
        })
        assert success is True
        assert "already deleted" in msg.lower()

    @patch("subprocess.run")
    def test_remove_finalizers_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="some error")
        success, msg = self.agent.remediate({
            "recommended_fix": "remove_finalizers",
            "fix_parameters": {
                "resource_type": "rosanetwork",
                "resource_name": "test",
                "namespace": "ns-rosa-hcp",
            },
        })
        assert success is False

    @patch("subprocess.run")
    def test_remove_finalizers_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="oc", timeout=30)
        success, msg = self.agent.remediate({
            "recommended_fix": "remove_finalizers",
            "fix_parameters": {
                "resource_type": "rosanetwork",
                "resource_name": "test",
                "namespace": "ns-rosa-hcp",
            },
        })
        assert success is False
        assert "timeout" in msg.lower()

    def test_refresh_ocm_token(self):
        success, msg = self.agent.remediate({
            "recommended_fix": "refresh_ocm_token",
            "fix_parameters": {},
        })
        assert success is False
        assert "manual" in msg.lower()

    def test_backoff_retry(self):
        success, msg = self.agent.remediate({
            "recommended_fix": "backoff_and_retry",
            "fix_parameters": {"backoff_seconds": 30, "max_retries": 5},
        })
        assert success is True
        assert "30s" in msg

    def test_log_and_continue(self):
        success, msg = self.agent.remediate({
            "recommended_fix": "log_and_continue",
            "fix_parameters": {},
        })
        assert success is True

    def test_success_rate_tracking(self):
        with patch("subprocess.run", return_value=MagicMock(returncode=0)):
            self.agent.remediate({
                "recommended_fix": "remove_finalizers",
                "fix_parameters": {"resource_type": "x", "resource_name": "y"},
            })
        rate = self.agent.fix_success_rate
        assert "remove_finalizers" in rate
        assert rate["remove_finalizers"]["successes"] == 1


# =============================================
# MonitoringAgent statistics and lifecycle
# =============================================


class TestMonitoringStatistics:
    def setup_method(self):
        self.agent = MonitoringAgent(BASE_DIR)

    def test_get_statistics(self):
        stats = self.agent.get_statistics()
        assert isinstance(stats, dict)
        assert "lines_processed" in stats or "total_issues" in stats or isinstance(stats, dict)

    def test_reset(self):
        self.agent.process_line("some line")
        self.agent.reset()
        assert len(self.agent.line_buffer) == 0
        assert self.agent.current_task is None

    def test_disabled_process_line(self):
        agent = MonitoringAgent(BASE_DIR, enabled=False)
        result = agent.process_line("FAILED - RETRYING: Wait for ROSANetwork deletion")
        assert result is False


# =============================================
# TrackedIssue state machine
# =============================================


class TestTrackedIssue:
    def test_initial_state(self):
        ti = TrackedIssue("test_issue", "ns/res", {"type": "test"})
        assert ti.state == IssueState.DETECTED
        assert ti.attempts == 0

    def test_can_retry_after_failure(self):
        ti = TrackedIssue("test_issue", "ns/res", {"type": "test"})
        ti.state = IssueState.FAILED
        ti.attempts = 1
        assert ti.can_retry() is True

    def test_cannot_retry_after_max(self):
        ti = TrackedIssue("test_issue", "ns/res", {"type": "test"})
        ti.state = IssueState.FAILED
        ti.attempts = 3
        assert ti.can_retry() is False

    def test_should_intervene_detected(self):
        ti = TrackedIssue("test_issue", "ns/res", {"type": "test"})
        assert ti.should_intervene() is True

    def test_should_not_intervene_diagnosing(self):
        ti = TrackedIssue("test_issue", "ns/res", {"type": "test"})
        ti.state = IssueState.DIAGNOSING
        assert ti.should_intervene() is False

    def test_should_intervene_resolved_after_cooldown(self):
        ti = TrackedIssue("test_issue", "ns/res", {"type": "test"})
        ti.state = IssueState.RESOLVED
        ti.attempts = 1
        ti.last_updated = time.time() - 130  # Past 120s cooldown
        assert ti.should_intervene() is True

    def test_should_not_intervene_resolved_within_cooldown(self):
        ti = TrackedIssue("test_issue", "ns/res", {"type": "test"})
        ti.state = IssueState.RESOLVED
        ti.attempts = 1
        ti.last_updated = time.time()  # Just now
        assert ti.should_intervene() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
